---
name: aminer-deep-search
version: 1.0.0
author: AMiner
contact: report@aminer.cn
description: >
  Activate this skill when the user wants deep, multi-round academic paper collection for a survey or literature review using AMiner data and a ReAct-style LLM controller.
  Use this skill for broad topic exploration, survey bibliography construction, automatic keyword search plus backward-reference snowballing, and collecting hundreds of candidate papers with AMiner IDs and titles.
  The controller can be the model already running this skill or an optional external OpenAI-compatible chat model. It uses AMiner keyword search plus paper reference APIs as tools. This skill is not intended for simple single-paper lookup or lightweight recommendations; use aminer-free-academic or aminer-daily-paper for those simpler tasks.
metadata:
  {
    "openclaw":
      {
        "requires": {
          "bins": ["python3"],
          "env": ["AMINER_API_KEY"]
        },
        "primaryEnv": "AMINER_API_KEY"
      }
  }
---

# AMiner Deep Search

ReAct-style survey paper collection using the backing model or an external OpenAI-compatible model with AMiner search/reference APIs.

Use this skill when the user asks to collect papers for a research topic, build a large literature list, run citation snowballing, or prepare survey references.

## What This Skill Does

The framework runs an LLM-controlled loop with these tools:

- `search`: AMiner keyword search, returning up to 20 papers per query.
- `get_reference`: AMiner backward-reference expansion for selected seed papers.
- `add_to_paper_set`: deduplicated paper collection by AMiner paper ID.
- `END`: terminate and output `[{"id": "...", "title": "..."}, ...]`.

The controller prompt asks the model to expand queries, prioritize high-quality seed papers, use reference snowballing, and terminate within 50 rounds. The target collection size is 400+ papers when AMiner results support it; it must not fabricate papers.

## Required Environment Variables

Check the AMiner key before running:

```bash
[ -z "${AMINER_API_KEY:-}" ] && echo "AMINER_API_KEY missing" || echo "AMINER_API_KEY exists"
```

If `AMINER_API_KEY` is missing, stop and ask the user to provide or set it. Never print the key. The code does not contain a built-in AMiner token.

## LLM Configuration

The ReAct controller can be driven in two ways:

1. **External LLM (optional).** If the user provides an OpenAI-compatible LLM key, the skill runs `react_agent.py`, which lets that model autonomously decide every tool call.
2. **Backing-model fallback (default when no key).** If no LLM key is configured, do **not** error. Fall back to the model already running this skill (for example, Claude Code itself) as the controller: drive the collection loop manually by calling the tool CLIs (`search.py`, `citation.py`) and applying the strategy in `prompt.py`.

The external-LLM mode reads the following environment variables (the underscore-style names are recommended; the dotted legacy names are still accepted for backward compatibility):

- `LLM_API_KEY` (legacy: `llm.api_key`): LLM API key. Optional. When absent, use the backing-model fallback instead of prompting.
- `LLM_BASE_URL` (legacy: `llm.base_url`): LLM base URL. Optional when OpenClaw provides a default; otherwise pass `--base-url`.
- `LLM_MODEL` (legacy: `llm.model`): LLM model name. Required only for the external-LLM mode (or pass `--models`).

Underscore-style names are recommended because POSIX shells (bash/zsh) do not allow `.` in variable names, so `export llm.api_key=...` will fail with `not a valid identifier`. Use the underscore names with `export`, or fall back to `env "llm.api_key=..." python ...` for the legacy names.

Detect which mode to use by checking whether an LLM key is available:

```bash
if [ -z "${LLM_API_KEY:-$(printenv 'llm.api_key')}" ]; then
  echo "No LLM key: use the backing-model fallback (drive tools manually)."
else
  echo "LLM key present: run react_agent.py in external-LLM mode."
fi
```

Never print any key. Do not hard-code provider-specific tokens, base URLs, or default model names in this skill.

### Quick setup examples

```bash
# Recommended: underscore-style env vars (works with `export`)
export LLM_API_KEY="sk-xxx"
export LLM_BASE_URL="https://api.deepseek.com/v1"
export LLM_MODEL="deepseek-chat"
export AMINER_API_KEY="xxx"
python3 react_agent.py --topic "your research topic"
```

```bash
# Legacy dotted names still work via `env` (cannot use `export`)
env "llm.api_key=sk-xxx" \
    "llm.base_url=https://api.deepseek.com/v1" \
    "llm.model=deepseek-chat" \
    "AMINER_API_KEY=xxx" \
    python3 react_agent.py --topic "your research topic"
```

## Environment Setup

From this skill directory, install dependencies into the Python environment used by `python3`:

```bash
python3 -m pip install -r requirements.txt
```

If you prefer an isolated conda environment, create and activate one first, then install the dependencies:

```bash
CONDA_PKGS_DIRS="$(pwd)/.conda_pkgs" conda create -p "$(pwd)/.conda" python=3.11 pip -y
conda activate "$(pwd)/.conda"
PIP_CACHE_DIR="$(pwd)/.pip_cache" python3 -m pip install -r requirements.txt
```

Backing-model mode only requires `requests`. External-LLM mode requires both `openai` and `requests`.

## Execution

### External-LLM mode (LLM key provided)

Run the main collector from this skill directory:

```bash
python3 react_agent.py \
  --topic "<research topic>" \
  --timeout 300 \
  --max-tool-calls 20 \
  --max-rounds 50
```

Useful options:

- `--api-key`: LLM API key. Defaults to `LLM_API_KEY` (legacy: `llm.api_key`).
- `--base-url`: LLM base URL. Defaults to `LLM_BASE_URL` (legacy: `llm.base_url`).
- `--models`: model fallback list. Required unless `LLM_MODEL` (legacy: `llm.model`) is configured.
- `--timeout`: per-model-call timeout in seconds. Default is 300.
- `--target-size`: desired final paper count. Default is 400.
- `--include-abstracts`: include abstracts in the final saved JSON when available.

The script prints the final JSON list and saves a copy under `outputs/`.

### Backing-model fallback mode (no LLM key)

When no LLM key is configured, act as the controller yourself. Follow the collection strategy in `prompt.py` and call the tool CLIs directly (they only need `AMINER_API_KEY`):

```bash
# Keyword search — returns up to 20 papers as JSON
python3 search.py --query "<query>" --size 20 --order n_citation

# Backward-reference expansion from seed AMiner paper IDs
python3 citation.py --ids <id1> <id2> --topic "<research topic>"
```

Search excludes papers after the current UTC year by default. Use `--year <yyyy>` for an older inclusive cutoff. Each keyword search scans at most 20 AMiner result pages; raise `--max-pages <n>` only when the older cutoff requires a larger, intentional request budget.

Iterate: expand queries, prioritize high-quality seeds, snowball references, deduplicate by AMiner paper ID, and stop once you reach the target size (400+ when results allow) or the results are exhausted. Output the final list as `[{"id": "...", "title": "..."}, ...]` and never fabricate papers.

## Operating Rules

1. Use this skill only for deep collection workflows. For one-off lookup or normal AMiner Q&A, route to the simpler AMiner skills.
2. Do not expose `LLM_API_KEY` (legacy `llm.api_key`) or `AMINER_API_KEY`.
3. Keep model/tool-call budgets under control; default `--max-tool-calls 20` and `--max-rounds 50`.
4. If AMiner returns too few papers, report the actual collected count instead of inventing missing papers.
5. If a run is likely to be expensive or long, tell the user the planned topic, controller mode, external model when applicable, timeout, max tool calls, and output location before starting.

## File Map

- `react_agent.py`: external-LLM ReAct loop and CLI.
- `api_client.py`: OpenAI-compatible client with external model fallback.
- `prompt.py`: paper-collection system prompt.
- `search.py`: AMiner keyword search and paper detail normalization.
- `citation.py`: AMiner reference expansion.
- `paper_set.py`: deduplicated collection and final JSON output.
