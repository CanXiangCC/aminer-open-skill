---
name: aminer-deep-search
version: 1.0.0
author: AMiner
contact: report@aminer.cn
description: >
  Activate this skill when the user wants deep, multi-round academic paper collection for a survey or literature review using AMiner data and a ReAct-style LLM controller.
  Use this skill for broad topic exploration, survey bibliography construction, automatic keyword search plus backward-reference snowballing, and collecting hundreds of candidate papers with AMiner IDs and titles.
  This skill calls an OpenAI-compatible chat model to decide tool calls, and uses AMiner keyword search plus paper reference APIs as tools. It is not intended for simple single-paper lookup or lightweight recommendations; use aminer-free-academic or aminer-daily-paper for those simpler tasks.
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

ReAct-style survey paper collection using OpenAI-compatible model calls and AMiner search/reference APIs.

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

The LLM can use OpenClaw-provided settings or a user-provided OpenAI-compatible endpoint:

- `llm.api_key`: LLM API key. Check at runtime and prompt if neither OpenClaw nor the user supplies a key.
- `llm.base_url`: LLM base URL. Optional when OpenClaw provides a default; otherwise pass `--base-url`.
- `llm.model`: LLM model name. Required unless `--models` is passed.

Before running, check whether an LLM key is available:

```bash
if [ -z "$(printenv 'llm.api_key')" ]; then
  echo "LLM API key missing"
else
  echo "LLM API key exists"
fi
```

If no LLM key is available, stop and ask the user to configure OpenClaw `llm.api_key` or pass `--api-key`. Never print the key. Do not hard-code provider-specific tokens or base URLs in this skill.

Check whether an LLM model is available:

```bash
[ -z "$(printenv 'llm.model')" ] && echo "LLM model missing" || echo "LLM model exists"
```

If no LLM model is available, ask the user to configure OpenClaw `llm.model` or pass `--models`. There is no provider-specific default model list.

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

Any compatible Python 3 environment may run the script as long as it has `openai` and `requests`.

## Execution

Run the main collector from this skill directory:

```bash
python3 react_agent.py \
  --topic "<research topic>" \
  --timeout 300 \
  --max-tool-calls 20 \
  --max-rounds 50
```

Useful options:

- `--api-key`: LLM API key. Defaults to `llm.api_key`.
- `--base-url`: LLM base URL. Defaults to `llm.base_url`.
- `--models`: model fallback list. Required unless `llm.model` is configured.
- `--timeout`: per-model-call timeout in seconds. Default is 300.
- `--target-size`: desired final paper count. Default is 400.
- `--include-abstracts`: include abstracts in the final saved JSON when available.

The script prints the final JSON list and saves a copy under `outputs/`.

## Operating Rules

1. Use this skill only for deep collection workflows. For one-off lookup or normal AMiner Q&A, route to the simpler AMiner skills.
2. Do not expose `llm.api_key` or `AMINER_API_KEY`.
3. Keep model/tool-call budgets under control; default `--max-tool-calls 20` and `--max-rounds 50`.
4. If AMiner returns too few papers, report the actual collected count instead of inventing missing papers.
5. If a run is likely to be expensive or long, tell the user the planned topic, model, timeout, max tool calls, and output location before starting.

## File Map

- `react_agent.py`: ReAct loop and CLI.
- `api_client.py`: OpenAI-compatible client with model fallback.
- `prompt.py`: paper-collection system prompt.
- `search.py`: AMiner keyword search and paper detail normalization.
- `citation.py`: AMiner reference expansion.
- `paper_set.py`: deduplicated collection and final JSON output.
