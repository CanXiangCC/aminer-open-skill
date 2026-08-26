---
name: aminer-pdf-ocr
version: 3.0.0
author: AMiner
contact: report@aminer.cn
description: >
  [Activation] Use when the user provides a PDF and requests OCR, Markdown conversion, or structured experiment extraction.
  [Scope] Submit the PDF to the AMiner MinerU open platform, poll the asynchronous job, download and unpack its ZIP, then let the Agent extract experiments from result.md using references/experiment_prompt.md.
  [Routing] Use pdf-citation-verifier for citation verification and aminer-academic-search / aminer-free-academic for literature search.
metadata:
  {"openclaw": {"emoji": "📄", "requires": {"bins": ["python3"], "env": ["OPEN_PLATFORM_TOKEN"]}, "primaryEnv": "OPEN_PLATFORM_TOKEN"}}
---

# PDF OCR + Experiment Extraction

The Python wrapper validates a PDF, uploads it to the AMiner MinerU open platform, handles queue backoff, polls the asynchronous job, downloads the temporary result ZIP, and writes compatible local artifacts. The Agent then reads `result.md` and follows `references/experiment_prompt.md` to create `experiments.json`.

## Pre-flight

1. Confirm `OPEN_PLATFORM_TOKEN` exists. Never print its value.
2. Install `requests` and `pypdf` from `requirements.txt`.
3. Confirm the input is a local PDF or an HTTP(S) URL. The open platform accepts only unencrypted PDFs of 1-30 pages and at most 10 MiB.

## Run

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ocr.py" --input "/abs/path/to/paper.pdf"
```

Options include `--output-dir`, `--request-timeout`, `--poll-timeout`, `--max-upload-attempts`, `--no-save-images`, and `--output`. The old synchronous `MINERU_BASE_URL`, backend, page-range, formula, and table options are not supported.

## API contract

- Upload and polling use the same token.
- Upload `code: 202` means queued, not completed. A reused upload may return `code: 200`; always use its returned `job_id`.
- Do not use `success`, HTTP status, or `code` alone to decide success. Inspect `data.status` and `data.is_finish`.
- `preparing`, `queued`, and `running` are polled. `success` downloads the ZIP. `failed`, `timeout`, `queue_timeout`, `expired`, and `unknown` stop.
- `data.queue_full` is retried with bounded backoff using `retry_after_seconds`.
- The temporary download URL is fetched directly without Authorization and is not saved in `response.json`.
- ZIP entries are discovered by `.md` and `_middle.json` suffixes; `document/` is not a protocol.

## Experiment extraction

Unless OCR-only is explicitly requested, read the complete `result.md`, follow `references/experiment_prompt.md`, write one JSON object to `experiments.json`, and show the same full JSON in the response. Do not add `justification` fields or invent unsupported experiments, datasets, metrics, or scores. If OCR fails, report the error and do not fabricate extraction output.

## Real example

The default local sample is `data/pdf/applsci-14-11736.pdf` (untracked; place it yourself). The live test is opt-in: set `RUN_MINERU_LIVE=1` together with `OPEN_PLATFORM_TOKEN`. It is skipped by default and never runs without both the credential and fixture.
