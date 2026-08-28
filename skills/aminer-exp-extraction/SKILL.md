---
name: aminer-exp-extraction
version: 1.0.0
author: AMiner
contact: report@aminer.cn
description: >
  [Activation] Use when the user asks to operate the paper-extraction
  pipeline: start/restart a bulk run ("run extraction", watch mode), append
  papers from CSV, check run progress/errors, backfill error papers
  ("补数"/"回填"), compact finished runs to reclaim disk, or run the test
  suite. [Scope] Self-contained skill package: vendored runtime (pipeline,
  scripts, configs, rule/ML pack, tests) plus operating procedures for six
  operations — run-extraction, ingest-csv, monitor-run, backfill-errors,
  compact-run, run-tests — each with pre-flight checks, exact commands, exit
  codes, and guardrails. [Routing] One operation per request: start/restart
  runs → §run-extraction; feed more papers into a live watch run →
  §ingest-csv; "how is the run going" → §monitor-run (read-only, always the
  safe first step); re-run error papers of a finished run → §backfill-errors;
  reclaim disk of finished runs → §compact-run; verify the repo is green →
  §run-tests. Do not mix: backfill before compaction, monitor before any
  state-changing decision, backfill/experiment runs never enter official
  export/merge.
metadata:
  {
    "openclaw":
      {
        "emoji": "🦞",
        "requires":
          {
            "anyBins": ["uv", "python3"],
            "env": []
          },
        "install":
          [
            {
              "id": "uv",
              "kind": "uv",
              "bins": ["uv"],
              "label": "Install uv (Python package manager)"
            }
          ]
      }
  }
---

# aminer-exp-extraction — paper-extraction pipeline operations

Self-contained skill package for the production LLM paper-extraction
pipeline. The directory this SKILL.md lives in ("the skill root", referenced
below as `{baseDir}`) bundles the complete vendored runtime: `pipeline/`,
`preprocess/`, `scripts/` (14 entry/utility CLIs), `configs/`, the frozen
rule/ML pack, `tests/`, and `requirements.txt`. Nothing outside `{baseDir}`
is needed at run time; service endpoints come from `configs/default.yaml` or
environment variables (never built in).

All commands below are run **from the skill root** with [uv](https://docs.astral.sh/uv/)
(`uv run --with-requirements requirements.txt --python 3.12 python ...`) —
uv resolves Python 3.12 and all dependencies into its own global cache on
first use; no venv is created or managed inside the skill. Paths in
commands are relative to `{baseDir}`.

## Operation routing

| User intent | Section | Script |
|---|---|---|
| Start / restart a production run (snapshot or watch mode) | [run-extraction](#1-run-extraction--start-a-production-extraction-run) | `scripts/run_bulk.py` |
| Append papers from CSV into a manifest dir (feed a watch run) | [ingest-csv](#2-ingest-csv--append-papers-from-csv) | `scripts/pipeline_cli.py ingest` |
| "How is the run doing?" — progress, errors, exit codes | [monitor-run](#3-monitor-run--read-only-run-monitoring) | (log-surface reads only) |
| Re-run error papers of a finished run, raise durable rate | [backfill-errors](#4-backfill-errors--backfill-the-error-papers-of-a-run) | `scripts/backfill_errors.py` |
| Reclaim disk space of finished runs | [compact-run](#5-compact-run--manual-compaction-of-finished-runs) | `scripts/compact_run.py` |
| Verify the repository is still green | [run-tests](#6-run-tests--run-the-pipeline-test-suite) | pytest |

Cross-cutting ordering rules: **backfill decisions come before compaction**
(compaction changes the run directory shape; `ledger_ok` only appears in
already-compacted runs); **monitor before any state-changing decision** on a
run; never operate on a run that is still executing.

## First-time setup (fresh clone / fresh install)

Only two things: [uv](https://docs.astral.sh/uv/) on PATH, and service
endpoints. No venv is created — every command below resolves Python 3.12 +
dependencies automatically via `uv run` (first invocation downloads and
caches them, ~30s; subsequent runs start in under a second).

```bash
# 1. Install uv if missing (user-level, no sudo):
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Fill in your service endpoints — either edit configs/default.yaml:
#   bert_server_url / llm_api_url / llm_model
# or export env vars (take precedence over the yaml):
#   BERT_SERVER_URL / LLM_CHAT_URL / LLM_MODEL
```

Endpoint reachability probe (also validates the dependency resolution):

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/pipeline_cli.py check-services --config configs/default.yaml
```

## Common pre-flight (before every operation)

1. Working directory = skill root (`{baseDir}/scripts/run_bulk.py` must
   exist); `uv --version` must succeed (else see First-time setup).
2. Check optional environment overrides — **presence only, values are never
   printed**:

```bash
for v in BERT_SERVER_URL LLM_CHAT_URL LLM_MODEL; do
  if [ -z "${!v+x}" ]; then
    echo "$v: not set (configs/default.yaml value will be used)"
  else
    echo "$v: set (overrides configs/default.yaml)"
  fi
done
```

3. Operations that call services (run-extraction, backfill `--run`) require
   the check-services probe to pass first; monitoring and tests never call
   services.

## 1. run-extraction — start a production extraction run

Starts (or safely restarts) a production bulk extraction session run via
`scripts/run_bulk.py`.

### Defaults (when the user gives no explicit values)

- **manifest-dir**: if the user names a dataset informally (e.g. "p500"),
  list `{baseDir}/manifests/` and match the directory name
  (e.g. `manifests/ai2000_p500single`); if nothing matches or several do,
  ask before proceeding.
- **CSV input (from-scratch run)**: if the user provides a CSV path and no
  matching manifest exists, first prepare the manifest via the §2 ingest
  procedure — target a NEW manifest dir named after the CSV stem
  (e.g. `ai2000_test800.csv` → `manifests/ai2000_test800/`), verify the
  ingest report shows the expected `new` count and zero `invalid` /
  `conflict`, then continue with the run below. One prompt covers the
  whole CSV → ingest → run chain.
- **run-id**: `<manifest-dir-name>-<YYYYMMDD-HHMM>` (local time, taken at
  run start — e.g. `ai2000_p500single-20260821-1530`). Check
  `pipeline_output/production/runs/` first: if the id already exists, re-derive
  with the current time; reuse an existing id ONLY when the user explicitly
  asks to restart that run (same-id restart skips ok papers, retries errors).
- **Output locations** (created automatically, nothing to configure):
  predictions / checkpoints / progress under
  `pipeline_output/production/runs/<run-id>/job_batch_*/`;
  process logs under `pipeline_output/production/logs/bulk-<ts>/`;
  per-run export snapshot `pipeline_output/production/exports/<run-id>_*.json`;
  runner state `pipeline_output/production/bulk_state.json`.

With these defaults a minimal instruction like "run the p500 extraction" is
sufficient — report the derived manifest-dir and run-id back to the user
before starting.

Snapshot mode (process the manifest directory once, then exit):

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/run_bulk.py \
  --manifest-dir manifests/<source-dir> \
  --run-id <session-run-id> \
  --config configs/default.yaml
```

Watch mode (after the startup queue drains, re-scan the manifest directory
at batch boundaries and append new `job_batch_*.json`; exits after
`--watch-idle-timeout` idle seconds):

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/run_bulk.py \
  --manifest-dir manifests/<source-dir> \
  --run-id <session-run-id> \
  --config configs/default.yaml \
  --watch-manifest --poll-interval 5 --watch-idle-timeout 600
```

**These commands will call the real BERT/LLM services — confirm with the
user before executing.**

Useful additional flags (verified against `--help`): `--job-batches 006`
(repeatable, explicit batch list — mutually exclusive with `--start-from`,
rejected with `--watch-manifest`), `--smoke N` (first N papers then exit),
`--force`, `--no-gate`, `--no-md-cache-cleanup`.

Stop semantics and restart:

- **SIGINT / SIGTERM** (e.g. Ctrl-C): graceful stop. The current
  `pipeline_batch` finishes, a checkpoint is written, then the process exits
  with code **130**; md-cache cleanup and compaction are skipped on stop.
- **SIGKILL** (`kill -9`): safe by design — predictions are written
  atomically, so a killed run leaves no torn state.
- **Restart**: re-run the exact same command with the **same `--run-id`**.
  Already-ok papers are skipped; error papers are retried. This restart
  behavior is the resume mechanism.
- The only child process is a transient `merge_exports.py` at boundaries.

Exit codes: **0** normal completion; **2** quality gate (error_rate > 15%);
**3** gate pause (parse_error_rate > 10% or zero_datasets_rate > 25%;
`bulk_state.json` + `job_checkpoint.json` written); **130** stopped by
SIGINT/SIGTERM (graceful).

Constraints: one production run at a time; **semantic parameters are
frozen** (see Guardrails); do not modify or delete anything under
`pipeline_output/production/runs/` by hand — use monitor-run to inspect and
compact-run to reclaim space.

## 2. ingest-csv — append papers from CSV

Appends papers from a CSV file into a manifest directory as new
`job_batch_*.json` files via `scripts/pipeline_cli.py ingest`. Ingest
**only writes manifest files** — it never triggers extraction and never
calls any service. A watch-mode runner picks the new batches up at batch
boundaries.

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/pipeline_cli.py ingest \
  --csv <paper-list.csv> \
  --manifest-dir manifests/<source-dir> \
  --run-id <session-run-id>
```

Re-queue rows whose only prediction is an error (default is to report them
only), with explicit batch size:

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/pipeline_cli.py ingest \
  --csv <paper-list.csv> \
  --manifest-dir manifests/<source-dir> \
  --run-id <session-run-id> \
  --include-retry --size 500 --source-name <name>
```

Flags (verified against `--help`): `--csv` (required), `--manifest-dir`
(required), `--run-id` (repeatable — every listed run's predictions
participate in dedup), `--include-retry`, `--size` (papers per new
job_batch, default 500), `--source-name`.

Five-way classification, per CSV row, with this precedence:
`invalid > conflict > duplicate > retry > new`.

- **invalid** — malformed row (fix the CSV first);
- **conflict** — inconsistent metadata for a known paper;
- **duplicate** — paper already has an ok prediction in the listed run(s);
- **retry** — paper's only prediction is an error (re-queued only with
  `--include-retry`);
- **new** — goes into the newly published job_batch.

Idempotency and impact: manifests are published atomically; `job_batch`
numbering in the target directory increases monotonically — re-running the
same ingest does not duplicate papers. Impact surface: **only the target
`--manifest-dir` gains new `job_batch_*.json` files**. Do not invent or
transform paper metadata; pass the CSV through as-is — invalid/conflict
rows are upstream data problems, report them. Do not point
`--manifest-dir` at `manifests/backfill/` outputs — backfill manifests are
owned by §backfill-errors.

## 3. monitor-run — read-only run monitoring

Derives the health of a session run from the pipeline's six-layer logging
surface. Everything here is **read-only** — monitoring never modifies
anything; if action is needed, report and route to the matching section.

Run root: `pipeline_output/production/runs/<session-run-id>/`. Log session:
`pipeline_output/production/logs/bulk-<ts>/` (append-only log dir per
process start).

| Layer | Path | What it gives |
|---|---|---|
| 1 | `logs/bulk-<ts>/bulk.log` | append-only, pid-tagged, dual timezone (local +08:00 and UTC); framed by `PROCESS START` / `PROCESS END pid=... exit=N` |
| 2 | `logs/bulk-<ts>/session.pid*.json` | startup config dump (session id, pid, timezone, start times) |
| 2 | `logs/bulk-<ts>/job_batch_*.pid*.summary.json` | per-batch `papers_total / ok / error / skipped`, `rates` (error_rate, parse_error_rate, zero_datasets_rate), `error_classes` counts |
| 3 | `runs/<run-id>/<job_batch>/progress.jsonl` | one line per paper: `ts / status / error / llm_elapsed_sec` (+ run/batch/paper ids) |
| 4 | `runs/<run-id>/ledger.jsonl` | per-paper final state + `prediction_sha256` + `workflow_version` (newer runs only — older runs have no ledger) |
| 5 | `runs/<run-id>/<job_batch>/monitors/<paper_id>_monitor.json`, `staged_pipeline_monitor.json`, `bert_batch_monitor.json` | per-stage timings, merge_conflicts |
| 6 | `runs/<run-id>/<job_batch>/predictions/<paper_id>.json` | the `error` field per paper — the data source for backfill classification |

Example reads (all read-only) — find the log session and final exit code:

```bash
ls pipeline_output/production/logs/ | grep bulk | tail -n 5
grep -h "PROCESS END" pipeline_output/production/logs/bulk-<ts>/bulk.log
```

Status counts and throughput per batch from progress.jsonl:

```bash
uv run --with-requirements requirements.txt --python 3.12 python - <<'PY'
import json, glob, collections
for f in sorted(glob.glob('pipeline_output/production/runs/<run-id>/job_batch_*/progress.jsonl')):
    c, llm = collections.Counter(), []
    for line in open(f):
        r = json.loads(line)
        c[r['status']] += 1
        if r.get('llm_elapsed_sec') is not None:
            llm.append(r['llm_elapsed_sec'])
    print(f, dict(c), 'llm_avg_sec=%.2f' % (sum(llm)/len(llm) if llm else 0))
PY
```

Error-class breakdown from the ledger (`workflow_version` is read from the
ledger — do not hardcode it):

```bash
uv run --with-requirements requirements.txt --python 3.12 python - <<'PY'
import json, collections
c = collections.Counter()
for line in open('pipeline_output/production/runs/<run-id>/ledger.jsonl'):
    c[json.loads(line)['status']] += 1
print(dict(c))
PY
```

Exit-code interpretation: **0** report final ok/error/skipped counts; **2**
list error classes, route to §backfill-errors if durable rate must improve;
**3** report which gate tripped (checkpoints were written); **130** run is
restartable with the same run-id.

Diagnostic boundary: **LLM raw responses are not persisted by default.**
For `parse_error` papers only the parser's diagnostic string is retained —
report that string, do not promise raw-response dumps.

Report numbers exactly as derived from the log surface — no estimation, no
fabrication. If a layer is missing (e.g. no ledger.jsonl on an older run),
say so and fall back to the layers that exist.

## 4. backfill-errors — backfill the error papers of a run

For a given finished session run, derive the "error set" (papers the run
saw − durable-ok), generate a backfill manifest per retryable class, re-run
it under a **brand-new session run id**, then verify the durable-rate
improvement. Never touches official export/merge. Do NOT backfill while the
run is still executing — monitor first.

Additional pre-flight: the run exists
(`pipeline_output/production/runs/<session_run_id>/` contains
`job_batch_*/`); for a real re-run the services must be reachable; the
source manifest under `manifests/` must index the run's papers' `md_url`
(dry-run `no-md_url` warning count = 0; non-zero means the corpus manifest
is missing — fix the corpus first).

### 4.1 dry-run (default, zero writes)

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/backfill_errors.py --run-id <session_run_id>
```

Review checklist — confirm **every** item before `--apply`:
- [ ] universe count matches the run's scale (= papers the run saw);
- [ ] classification as expected: `parse_error / llm_timeout / llm_http /
      bert / post_llm / missing_prediction / corrupt` enter backfill;
      `md_fetch` is excluded by default (dead links are pointless to retry,
      unless the user explicitly asks for `--include-md-fetch`);
- [ ] `ledger_ok` (if any) only appears in already-compacted runs;
- [ ] `WARN no md_url` is 0;
- [ ] projected durable-rate gain is consistent with the error-set size.

### 4.2 Generate the backfill manifest

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/backfill_errors.py --run-id <session_run_id> --apply
```

Output: `manifests/backfill/<run-id>-<YYYYMMDD-HHMMSS>/job_batch_backfill_000.json`
(atomic write, includes `backfill_meta.json` provenance). That directory is
gitignored and never committed. Note the path uses **hyphen** joining
between run id and timestamp.

### 4.3 Execute the backfill run (new session id — the core guardrail)

**This step really calls the BERT/LLM services; runtime is proportional to
the error-set size. Confirm with the user before executing.**

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/backfill_errors.py --run-id <session_run_id> --run \
    --config configs/default.yaml
# equivalent to: run_bulk --manifest-dir <backfill-dir> --run-id <orig>-bf<YYYYMMDD>
```

- The new run id defaults to `<orig>-bf<YYYYMMDD>` (override with
  `--new-run-id` only if the user explicitly asks).
- One run at a time; ask the user before merging multiple runs' backfills.

### 4.4 Verify the durable rate

```bash
ls pipeline_output/production/runs/<orig>-bf<date>/job_batch_backfill_000/predictions/ | wc -l
uv run --with-requirements requirements.txt --python 3.12 python scripts/backfill_errors.py --run-id <session_run_id>   # error-set recheck, same basis
```

Pass criteria (**union basis** — the separate session is the guardrail; the
original run's error set itself is unchanged):
- the backfill run's ok predictions ≈ the number of backfilled papers;
- union durable = (orig run ok ∪ backfill run ok) / universe reaches the
  projected value (e.g. 5/10 -> 10/10).
- Cleanup note: at the end of a run, run_bulk auto-runs `merge_exports` for
  that run, producing
  `pipeline_output/production/exports/<bf-run-id>_job_batch_backfill_000.json`
  (a standalone file named by run id — it never enters any official delivery
  JSON). For backfill/experiment runs, delete that one file before reporting
  to keep `exports/` clean. Impact surface of the deletion: exactly that one
  auto-generated file, nothing else — state this to the user before deleting.

### 4.5 Report template

```
Backfill report: <orig> -> <orig>-bf<date>
- Error set: <counts per class> (md_fetch excluded N papers: dead links, upstream data fix needed)
- Durable rate: X/Y (a%) -> (X+B)/Y (b%) (actually recovered M/B)
- Remaining unrecovered: <paper_id + reason, one per line>
- Artifacts: manifests/backfill/<dir>/ (gitignored)
```

Backfill-specific guardrails (stop and explain if any is violated):
1. The backfill run id is an **independent session** — it never enters
   official export / merge_flat / merge_exports.
2. This procedure never calls the official merge/export scripts.
3. Dry-run by default; the review checklist must be completed before
   `--apply` / `--run`; execute each step exactly once, in order (dry-run →
   review → apply → run → verify → report); do not batch `--apply` and
   `--run` past an unconfirmed checklist.
4. md_fetch dead links are not backfilled by default (upstream data
   problem); including them requires an explicit user request
   (`--include-md-fetch`).
5. Backfill/experiment run artifacts live only in gitignored directories
   (`runs/`, `manifests/backfill/`).

## 5. compact-run — manual compaction of finished runs

Compacts finished session runs via `scripts/compact_run.py`. **This is a
destructive (space-reclaiming) operation: always run `--dry-run` first and
show the user what would happen before running for real.**

Additional pre-flight:
1. The run is **finished** (no live bulk process for that run — check
   `pipeline_output/production/logs/bulk-<ts>/bulk.log` ends with
   `PROCESS END`, or use §monitor-run). Never compact a running run.
2. If backfill is planned for this run, do the backfill decision first
   (§backfill-errors): compaction changes the run directory shape and
   `ledger_ok` entries only appear in already-compacted runs, which changes
   the backfill dry-run review basis.

Step 1 — dry-run (zero writes, mandatory first):

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/compact_run.py --session-run-id <session-run-id> --dry-run
```

Step 2 — real compaction (only after the user confirms the dry-run report):

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/compact_run.py --session-run-id <session-run-id>
```

Multiple runs in one invocation (`--session-run-id` is repeatable), or
offline operation on a copied runs tree:

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/compact_run.py \
  --session-run-id <run-a> --session-run-id <run-b> \
  --runs-dir <copied-runs-dir> --dry-run
```

Flags (verified against `--help`): `--session-run-id` (required,
repeatable), `--dry-run`, `--runs-dir` (override the runs root — operate on
a copy).

Exit codes: **0** compacted (or dry-run / nothing to do); **2**
verification failed — **originals kept**, nothing lost; report and stop.

Never "work around" the tool by hand-deleting files under
`pipeline_output/production/runs/`.

## 6. run-tests — run the pipeline test suite

Runs the pytest suite from the skill root. Strictly read-only with respect
to code and tests; runs fully offline against fixtures (no BERT/LLM
service calls). On a fresh install, use `requirements-dev.txt` (includes
pytest).

```bash
uv run --with-requirements requirements.txt --with-requirements requirements-dev.txt --python 3.12 -m pytest tests/ -q                       # full suite
uv run --with-requirements requirements.txt --with-requirements requirements-dev.txt --python 3.12 -m pytest tests/ -q -k backfill           # targeted by keyword
uv run --with-requirements requirements.txt --with-requirements requirements-dev.txt --python 3.12 -m pytest tests/test_backfill_errors.py -q  # targeted by file
```

Result interpretation:
- **Green** = `0 failed`, no unexpected skips. Baseline on a fresh clone
  without service env vars: **336 passed + 1 skipped** —
  `tests/test_LLM.py` auto-skips as a module when `LLM_CHAT_URL` /
  `BERT_SERVER_URL` are unset; with them set and services reachable it is
  **341 passed**. The exact count is a moving baseline — compare against
  the most recently recorded green run rather than a hardcoded number.
- **Failures** = report the failing test ids and the assertion/output
  excerpts verbatim; map each failing file to its module (e.g.
  `tests/test_backfill_errors.py` → `scripts/backfill_errors.py`).
- Do not modify tests, fixtures, or pipeline code to make a run pass. Do
  not re-run selectively to "chase" a flaky pass without reporting the
  first failure. If a test failure implicates pipeline behavior, report it
  — do not attempt fixes here.

## Run outputs & paths

All run artifacts land under `{baseDir}/pipeline_output/production/`
(`runs/`, `logs/`, `exports/`, `partials/`) and `manifests/` — those
directories are gitignored (one test fixture run is tracked). When this
skill is installed via `openclaw skills install`, that is inside the
installed skill copy (e.g. `~/.openclaw/workspace/skills/aminer-exp-extraction/`)
— fine for lightweight operations (monitor, ingest, tests, small runs). For
long-lived heavy production runs, prefer a dedicated `git clone` of the
skill repository so run artifacts stay out of the agent workspace, and
point operators there.

## Guardrails (apply to every operation — stop and explain if violated)

1. **Semantic parameters are frozen**: never change the LLM prompt, model,
   or temperature, `bert_threshold`, or any schema/normalize/merge/commit
   setting in the config.
2. Endpoints and model names come from `configs/default.yaml` or the
   environment only — never hardcode them; never print secret values.
3. Backfill and experiment runs **never enter official export/merge**
   (merge_flat_experiments / merge_exports of official deliveries).
4. Destructive actions (`--apply`, `--run`, compaction, file deletion)
   require a dry-run or an explicit impact statement first.
5. Steps that call the real BERT/LLM services are explicitly marked
   "will call the services — confirm before executing".
6. Report outcomes faithfully — numbers exactly as derived from the log
   surface; no estimation, no fabrication.

## File Map

| Path | Responsibility |
|---|---|
| `SKILL.md` / `SKILL.zh.md` | This skill definition (EN / ZH, kept in sync) |
| `scripts/` | 14 entry/utility CLIs (run_bulk, pipeline_cli, backfill_errors, compact_run, merge/collect utilities) |
| `pipeline/`, `preprocess/`, `reference_detector.py`, `rule_ml_extraction_from_promote/` | Vendored runtime (pipeline stages, preprocessing, frozen rule/ML pack) |
| `configs/default.yaml` | Pipeline config — fill in service endpoints here |
| `tests/` + `dataset_evidence/` | Offline test suite (live-service tests auto-skip without env vars) |
| `requirements.txt` / `requirements-dev.txt` | Runtime / dev dependencies (public PyPI) |
| `README.md` / `README.zh.md` | Package overview and Quick Start |
| `VENDOR_MANIFEST.json` / `PLAN.md` | Vendoring provenance, sanitization record, design history |
