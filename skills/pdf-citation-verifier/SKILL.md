---
name: aminer-pdf-citation-verifier
version: 1.0.0
author: AMiner
contact: report@aminer.cn
description: >
  [Activation] Use this skill when the user provides a paper PDF (file path or upload) and asks to verify, audit, or fact-check its references / citations / bibliography — e.g. "check whether the references in this PDF are hallucinated", "find fake citations", "verify the bibliography".
  [Capability] Uploads the PDF to the AMiner pdf-citation-verifier service, polls the asynchronous job, and returns a per-reference classification (REAL / LIKELY_REAL / NEEDS_REVIEW / LIKELY_FAKE / FAKE) plus an overall hallucination summary.
  [Routing] Do NOT use for general paper search, scholar lookup, citation-intent analysis, or building a citation graph — use aminer-academic-search, aminer-free-academic, or paper-source-trace instead. This skill only verifies whether references actually exist.
metadata:
  {
    "openclaw":
      {
        "emoji": "🕵️",
        "requires": {
          "bins": ["python3"],
          "env": ["AMINER_API_KEY"]
        },
        "primaryEnv": "AMINER_API_KEY"
      }
  }
---

# PDF Citation Verifier

Verify whether the references in a paper PDF actually exist by submitting the PDF to the AMiner `pdf-citation-verifier` service, polling the asynchronous job, and returning a structured summary. Invoke via natural language or `/pdf-citation-verifier`.

## What This Skill Does

For each reference parsed from the uploaded PDF, the upstream service queries AMiner SearchPro and labels the citation with one of:

- `REAL` — high-confidence match in AMiner.
- `LIKELY_REAL` — partial match, likely genuine.
- `NEEDS_REVIEW` — evidence is inconclusive; ask a human.
- `LIKELY_FAKE` — partial mismatch, probably fabricated.
- `FAKE` — no plausible match found.

Each call to the gateway returns the standard envelope `{"code": 200, "success": true, "msg": "", "data": ..., "log_id": "..."}`. The script unwraps it before printing.

- `POST /api/v3/paper/citation/verify/upload` returns `data: {"job_id": "verify_..."}`.
- `GET /api/v3/paper/citation/result?job_id=...` returns `data: [<record>]` where the single record has top-level fields like `is_finish`, `summary`, `urls`, `url_expire_seconds`. `summary.total` is the verified-reference count and `summary.overall` carries `has_hallucination`, `hallucination_ratio`, `counts_by_status`, plus author-side checks (`counts_by_author_status`, `counts_by_author_list_status`).

The skill returns that record plus the `job_id` so the user can re-poll later.

## Authentication Model

The gateway does **not** accept a long-lived static token. Per AMiner platform docs, the user holds two pieces and the client signs a short-lived JWT per run:

1. **`AMINER_API_KEY`** — HMAC-SHA256 signing secret from the AMiner console (`API Keys`). Typically 16 characters; PyJWT will warn that this is below RFC 7518's recommended 32-byte minimum — this is normal for AMiner-issued keys.
2. **`AMINER_USER_ID`** — your AMiner user id from the console (`Account`). Not a secret; it is embedded in the JWT payload.

`scripts/verify_pdf.py` signs a 2-hour HS256 JWT at start-up and puts it in the `Authorization` header. The signing secret never leaves the process.

## File Map

- `SKILL.md` / `SKILL.zh.md` — English / Chinese skill definitions (this file).
- `commands/pdf-citation-verifier.md` — slash command entry.
- `scripts/verify_pdf.py` — HTTP client: signs JWT → upload → poll → print the unwrapped result record.
- `requirements.txt` — Python dependencies (`requests`, `PyJWT`).

## Pre-flight

Run these checks before invoking the script. Stop and surface the error to the user if any check fails.

**1. AMINER_API_KEY and AMINER_USER_ID**

```bash
[ -z "${AMINER_API_KEY+x}" ] && echo "AMINER_API_KEY missing" || echo "AMINER_API_KEY exists"
[ -z "${AMINER_USER_ID+x}" ] && echo "AMINER_USER_ID missing" || echo "AMINER_USER_ID exists"
```

If either is missing, stop and tell the user to obtain the signing secret (`API Keys`) and user id (`Account`) from https://open.aminer.cn, then `export` both. **Never print the AMINER_API_KEY value.** `AMINER_USER_ID` is not a secret but should still come from the user's own environment.

**2. Python dependencies**

```bash
python3 - <<'PY'
import importlib.util
missing = [name for name in ("requests", "jwt") if importlib.util.find_spec(name) is None]
print("Missing: " + ", ".join(missing) if missing else "Python dependencies exist")
PY
```

If missing, instruct: `pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`.

**3. PDF input**

The user must supply an existing local `.pdf` file path. If they only describe a paper without a file, ask them to provide the PDF path. Do not invent or download a PDF.

## Execution Example

Basic verification with defaults (max 50 references, auto-polls until done):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verify_pdf.py" \
  --pdf "/abs/path/to/paper.pdf"
```

Full options:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verify_pdf.py" \
  --pdf "/abs/path/to/paper.pdf" \
  --max-refs 80 \
  --strict \
  --timeout 900 \
  --poll-interval 5 \
  --output outputs/pdf-citation-verifier/<safe-paper-stem>/result.json
```

Submit-only (no polling, return `job_id` for later lookup):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verify_pdf.py" \
  --pdf "/abs/path/to/paper.pdf" --no-wait
```

Fetch the result for an existing `job_id` (no new upload):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verify_pdf.py" \
  --job-id verify_20260527T090207Z_a72c9ba5
```

## Parameters

| Flag | Default | Notes |
| --- | --- | --- |
| `--pdf` | required (unless `--job-id`) | Local `.pdf` file path. Server caps body at 50 MB. |
| `--job-id` | – | Skip upload and just fetch the result for an existing job. |
| `--max-refs` | 50 | Server hard cap is 100. |
| `--strict` | off | Stricter FAKE judgement on partial matches. |
| `--no-wait` | off | With `--pdf`: submit and return `job_id` without polling. With `--job-id`: single fetch, return immediately without looping. |
| `--timeout` | 600 | Overall polling timeout in seconds. |
| `--poll-interval` | 5 | Seconds between result polls. |
| `--request-timeout` | 120 | Per-HTTP-request timeout. |
| `--output` | - | Optional path to also write the JSON response. |

## Environment Variables

| Var | Required | Purpose |
| --- | --- | --- |
| `AMINER_API_KEY` | yes | HMAC-SHA256 signing secret. The script uses it to sign a 2-hour JWT; the secret itself is never sent over the wire. |
| `AMINER_USER_ID` | yes | AMiner user id embedded in the JWT `user_id` claim. Not a secret. |
| `PDF_CITATION_VERIFIER_BASE_URL` | no | Override the gateway base URL. Defaults to `https://datacenter.aminer.cn/gateway/open_platform`. |

## Runtime Constraints

- **Never** print, log, or echo the value of `AMINER_API_KEY`.
- **Never** fabricate verification verdicts. If the script fails or times out, surface the error verbatim — do not synthesize results.
- `urls.pdf`, `urls.report`, `urls.result` in the response point to server-side artifacts and are valid only for `url_expire_seconds` (typically 300s). Do not claim those paths exist on the user's machine. Use `--output` to keep a local JSON copy of the full record.
- Respect the per-user active job cap (server returns 429 when exceeded). If a 429 surfaces, stop and tell the user to wait for prior jobs to finish.
- Treat any `LIKELY_FAKE` / `FAKE` verdict as a flag for human review, not a final accusation. Surface `summary.overall.counts_by_status` and the author-side counts (`counts_by_author_status`, `counts_by_author_list_status`) when the response includes them.

## Output Presentation

After the script returns, summarize the result for the user with at minimum:

- `job_id`
- `summary.total` (number of references verified)
- `summary.overall.has_hallucination`, `summary.overall.hallucination_ratio`
- A short table built from `summary.overall.counts_by_status` (REAL / LIKELY_REAL / NEEDS_REVIEW / LIKELY_FAKE / FAKE)
- Optionally the author-side numbers (`author_conflict_ratio`, `counts_by_author_status`) when present
- `urls.report` / `urls.result` links, noting they expire in `url_expire_seconds` seconds
- The full JSON should be either saved (via `--output`) or echoed back to the user, never silently dropped.

If `is_finish` is `true` and the record contains an error indicator, report it and suggest re-running.
