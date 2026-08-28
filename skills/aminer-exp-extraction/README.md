# aminer-exp-extraction

Standalone, self-contained **OpenClaw skill** for the production LLM
paper-extraction pipeline. This directory is one skill in the
[aminer-exp-skill](../../README.md) collection: `SKILL.md` at its root
(standard OpenClaw format), with the complete **vendored runtime** (pipeline
code, scripts, configs, rule/ML pack, tests) bundled inside — clone or
install it alone and everything works, no reference to the upstream project
at run time.

Service endpoints and model names are **not** built in: bring your own
BERT/LLM endpoints via config or environment variables.

## Install (OpenClaw)

One command — install this skill directory (the directory containing this
README, `SKILL.md` at its root):

```bash
# from a clone of the aminer-exp-skill repository:
openclaw skills install ./skills/aminer-exp-extraction
```

The install copies the whole directory (runtime included), so the skill is
self-contained in the workspace. Run artifacts then land under
`pipeline_output/production/` inside the installed copy — fine for
lightweight operations; for long-lived heavy production runs prefer a
dedicated `git clone` of the repository.

## Quick Start (from a clone)

Setup is just uv + endpoints — no venv to create or manage; every command
resolves Python 3.12 and dependencies automatically via `uv run` (cached
after first use).

```bash
git clone <aminer-exp-skill-repo> && cd aminer-exp-skill/skills/aminer-exp-extraction
# Install uv if missing (user-level, no sudo): curl -LsSf https://astral.sh/uv/install.sh | sh

# Configure your service endpoints — either edit configs/default.yaml:
#   bert_server_url / llm_api_url / llm_model
# or export env vars (take precedence over the yaml):
#   BERT_SERVER_URL / LLM_CHAT_URL / LLM_MODEL

uv run --with-requirements requirements.txt --python 3.12 python scripts/pipeline_cli.py check-services   # probe both services
# Prepare manifests from your CSV:
uv run --with-requirements requirements.txt --python 3.12 python scripts/pipeline_cli.py ingest --csv <papers.csv> \
    --manifest-dir manifests/myset --run-id my-run-1
# Run extraction (calls your BERT/LLM services):
uv run --with-requirements requirements.txt --python 3.12 python scripts/run_bulk.py --manifest-dir manifests/myset \
    --run-id my-run-1 --config configs/default.yaml
```

Optional self-check: `uv run --with-requirements requirements.txt --with-requirements requirements-dev.txt --python 3.12 -m pytest tests/ -q` → **336 passed +
1 skipped** out of the box (the live-service tests in `tests/test_LLM.py`
auto-skip unless `LLM_CHAT_URL` / `BERT_SERVER_URL` are set; with them set
and services reachable the baseline is 341 passed).

## Operations (see SKILL.md for full procedures)

| User intent | Section in SKILL.md | Script |
|---|---|---|
| Start / restart a bulk run (snapshot or watch mode) | §1 run-extraction | `scripts/run_bulk.py` |
| Append papers from CSV into a manifest dir | §2 ingest-csv | `scripts/pipeline_cli.py ingest` |
| Read-only run monitoring (progress, errors, exit codes) | §3 monitor-run | log-surface reads |
| Re-run error papers, raise durable rate | §4 backfill-errors | `scripts/backfill_errors.py` |
| Reclaim disk space of finished runs | §5 compact-run | `scripts/compact_run.py` |
| Verify the repo is still green | §6 run-tests | pytest |

Routing at a glance: start or restart a run → §1; feed it more papers → §2;
"how is the run doing?" → §3 (read-only, always safe); error papers need
re-running → §4 (never enters official export); finished run, reclaim disk
→ §5 (destructive; dry-run first); verify green → §6.

## Directory layout

```
├── SKILL.md / SKILL.zh.md      # the skill definition (EN/ZH) — OpenClaw entry point
├── pipeline/                   # vendored runtime: production/benchmark/evaluation packages
├── preprocess/                 # vendored runtime: preprocessing stages
├── scripts/                    # 14 entry/utility scripts (run_bulk, pipeline_cli, backfill, ...)
├── configs/default.yaml        # pipeline config (endpoints to be filled in)
├── rule_ml_extraction_from_promote/   # frozen rule/ML extraction pack (incl. models)
├── reference_detector.py       # reference-strip detector used by preprocess
├── dataset_evidence/           # evidence scoring (test dependency)
├── tests/                      # 341-test suite (self-bootstrapping, offline except test_LLM.py)
├── pipeline_output/            # runtime outputs (gitignored; one fixture run is tracked)
├── manifests/                  # your job_batch manifests (gitignored; create via ingest)
├── requirements.txt / requirements-dev.txt
├── VENDOR_MANIFEST.json        # vendoring provenance + sanitization record
└── CONTRIBUTING.zh.md          # skill standard for this repository
```

## Vendored runtime

The runtime was copied from the upstream `exp-extraction-project` repository
(commit recorded in `VENDOR_MANIFEST.json`) and sanitized for redistribution:
all intranet endpoints and model paths were removed — values must come from
`configs/default.yaml` or the `BERT_SERVER_URL` / `LLM_CHAT_URL` /
`LLM_MODEL` environment variables. Prediction semantics are unchanged since
upstream 0.7.1 (workflow version 0.8.0). See `PLAN.md` for the full vendoring
and sanitization record.

## Safety guardrails (apply to every operation)

- **Semantic parameters are frozen**: never change LLM prompt/model/temperature, `bert_threshold`, or schema/normalize/merge/commit settings.
- Backfill and experiment runs **never enter official export/merge**.
- Destructive actions (`--apply`, `--run`, compaction, file deletion) require a dry-run or an explicit impact statement first.
- Never print secret values; never hardcode intranet endpoints or model names.
- Steps that call the real BERT/LLM services are explicitly marked "will call the services — confirm before executing".

## Contributing

See `CONTRIBUTING.zh.md` for the skill standard (SKILL.md spec, Python
rules, PR checklist).
