---
name: aminer-pdf2xml
version: 1.0.0
author: AMiner
contact: report@aminer.cn
description: >
  [Activation] Use this skill when the user provides a local scholarly PDF path and asks to convert, parse, or extract it into XML / TEI, for example "convert this PDF to XML", "turn this paper into TEI", or "run GROBID on this PDF".
  [Capability] Uploads the PDF to a GROBID-compatible AMiner API service, requests full-text TEI XML with common coordinate annotations, validates the response, and writes the XML to disk.
  [Routing] Do not use this skill for reference hallucination checks, citation fact verification, paper search, scholar lookup, or literature review collection. Use pdf-citation-verifier, aminer-academic-search, aminer-free-academic, or aminer-deep-search for those tasks. This skill only performs PDF-to-TEI XML structural conversion.
metadata:
  {
    "openclaw":
      {
        "emoji": "📄",
        "requires": {
          "bins": ["python3"],
          "env": []
        }
      }
  }
---

# PDF to XML

Convert a scholarly PDF into TEI XML by calling a GROBID-compatible API service. Invoke via natural language or `/pdf2xml`.

## What This Skill Does

GROBID parses a scholarly PDF and returns a TEI XML document containing metadata, abstract, body sections, figures, formulas, references, and bibliography entries. This skill is a small API client that:

- POSTs the PDF to `{GROBID_BASE_URL}/api/processFulltextDocument`.
- Requests TEI coordinates for `persName`, `figure`, `ref`, `formula`, and `biblStruct` by default.
- Validates the response is non-empty and not marked as bad input.
- Writes the returned TEI XML next to the PDF or to a user-provided output path.

By default, the script uses the AMiner/GROBID API service at `http://36.103.177.237:8088`, matching the legacy `parse_pdf_origin.py` parser. Set `GROBID_BASE_URL` or pass `--base-url` to point at another compatible service. Do not print environment variable values in user-facing output.

## File Map

- `SKILL.md` / `SKILL.zh.md` - English / Chinese skill definitions.
- `commands/pdf2xml.md` - slash command entry.
- `scripts/pdf_to_xml.py` - API client: check service, upload PDF, write TEI XML.
- `requirements.txt` - Python dependencies.
- `README_DEPLOYMENT.md` - operational notes and manual verification steps.

## Pre-flight

Run these checks before invoking the conversion. Stop and surface the error to the user if a required check fails.

**1. Optional API endpoint override**

```bash
[ -z "${GROBID_BASE_URL+x}" ] && echo "GROBID_BASE_URL missing; using default AMiner/GROBID API" || echo "GROBID_BASE_URL exists"
```

`GROBID_BASE_URL` is optional. Never print its value.

**2. Python dependency**

```bash
python3 - <<'PY'
import importlib.util
missing = [name for name in ("requests",) if importlib.util.find_spec(name) is None]
print("Missing: " + ", ".join(missing) if missing else "Python dependencies exist")
PY
```

If missing, instruct: `pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`.

**3. API service reachability**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" --check
```

If using a one-off endpoint instead of `GROBID_BASE_URL`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --base-url "<GROBID_API_BASE_URL>" \
  --check
```

If the check fails, stop. Tell the user the API service is unreachable and that they can retry later or set `GROBID_BASE_URL` to another running GROBID-compatible endpoint.

**4. PDF input**

The user must supply an existing local `.pdf` file path. If they only describe a paper without a file, ask for the local PDF path. Do not invent or download a PDF.

## Execution Examples

Basic conversion. The script writes `<pdf-stem>.xml` next to the PDF:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --pdf "/abs/path/to/paper.pdf"
```

Write XML to a specific path or directory:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --pdf "/abs/path/to/paper.pdf" \
  --output "/abs/path/to/out/paper.xml"

python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --pdf "/abs/path/to/paper.pdf" \
  --output-dir "outputs/pdf2xml"
```

Point at an API service for a single command:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --base-url "<GROBID_API_BASE_URL>" \
  --pdf "/abs/path/to/paper.pdf"
```

Disable coordinate annotations when a downstream consumer needs smaller XML:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --pdf "/abs/path/to/paper.pdf" \
  --no-coordinates
```

Enable GROBID consolidation when the configured service supports external metadata lookup:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --pdf "/abs/path/to/paper.pdf" \
  --consolidate-header 1 \
  --consolidate-citations 1
```

## Parameters

| Flag | Default | Notes |
| --- | --- | --- |
| `--pdf` | required unless `--check` | Local `.pdf` file path. |
| `--output` | none | Explicit output `.xml` path. Overrides `--output-dir`. |
| `--output-dir` | none | Directory for the `.xml`; filename is derived from the PDF. |
| `--base-url` | `$GROBID_BASE_URL` or `http://36.103.177.237:8088` | GROBID-compatible API base URL. |
| `--request-timeout` | 300 | Per-request timeout in seconds. |
| `--consolidate-header` | none | GROBID `consolidateHeader` flag, one of `0`, `1`, `2`. |
| `--consolidate-citations` | none | GROBID `consolidateCitations` flag, one of `0`, `1`, `2`. |
| `--no-coordinates` | off | Do not request TEI coordinates. |
| `--check` | off | Probe `/api/isalive` and exit. |

## Environment Variables

| Var | Required | Purpose |
| --- | --- | --- |
| `GROBID_BASE_URL` | no | Override the default AMiner/GROBID API base URL. |

## Runtime Constraints

- Always run dependency and reachability checks before conversion.
- Do not require users to start local Docker for the default workflow; the default path is API-based.
- On success, stdout is the single output XML path; human-readable status goes to stderr. Report the written path to the user.
- Never fabricate XML output. If the script exits non-zero, surface the classified error verbatim: `pdf_not_found`, `not_a_pdf`, `empty_response`, `bad_input_data`, `http_<code>`, `request_timeout`, or `request_failed`.
- `bad_input_data` means the API service could not parse the PDF, commonly because it is corrupt, scanned without a text layer, or not a real PDF.
- Large PDFs can be slow. Increase `--request-timeout` for legitimate long-running conversions instead of assuming a hang.

## Output Presentation

After the script returns, tell the user:

- The output `.xml` path that was written.
- That the format is TEI XML produced by a GROBID-compatible API.
- On failure, the exact error code from stderr and the most likely cause.
