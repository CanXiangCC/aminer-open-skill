---
name: aminer-deep-search
version: 1.0.0
author: AMiner
contact: report@aminer.cn
description: >
  Activate this skill when the user wants deep, multi-round academic paper collection for a survey or literature review using AMiner data and a ReAct-style LLM controller.
  Use this skill for broad topic exploration, survey bibliography construction, automatic keyword search plus backward-reference snowballing, and collecting hundreds of candidate papers with AMiner IDs and titles.
  This skill calls a Yunwu/OpenAI-compatible chat model to decide tool calls, and uses AMiner keyword search plus paper reference APIs as tools. It is not intended for simple single-paper lookup or lightweight recommendations; use aminer-free-academic or aminer-daily-paper for those simpler tasks.
metadata:
  {
    "openclaw":
      {
        "requires": {
          "bins": ["python"],
          "env": ["YUNWU_API_KEY", "AMINER_API_KEY"]
        },
        "primaryEnv": "YUNWU_API_KEY"
      }
  }
---

# AMiner Deep Search

ReAct-style survey paper collection using Yunwu model calls and AMiner search/reference APIs.

Use this skill when the user asks to collect papers for a research topic, build a large literature list, run citation snowballing, or prepare survey references.

## What This Skill Does

The framework runs an LLM-controlled loop with these tools:

- `search`: AMiner keyword search, returning up to 20 papers per query.
- `get_reference`: AMiner backward-reference expansion for selected seed papers.
- `add_to_paper_set`: deduplicated paper collection by AMiner paper ID.
- `END`: terminate and output `[{"id": "...", "title": "..."}, ...]`.

The controller prompt asks the model to expand queries, prioritize high-quality seed papers, use reference snowballing, and terminate within 50 rounds. The target collection size is 400+ papers when AMiner results support it; it must not fabricate papers.

## Required Environment Variables

Check the Yunwu key before running:

```bash
[ -z "${YUNWU_API_KEY+x}" ] && echo "YUNWU_API_KEY missing" || echo "YUNWU_API_KEY exists"
```

If `YUNWU_API_KEY` is missing, stop and ask the user to provide or set it. Never print the key.

Check the AMiner key before running:

```bash
[ -z "${AMINER_API_KEY+x}" ] && echo "AMINER_API_KEY missing" || echo "AMINER_API_KEY exists"
```

If `AMINER_API_KEY` is missing, stop and ask the user to provide or set it. Never print the key. The code does not contain a built-in AMiner token.

## Environment Setup

From this skill directory:

```bash
CONDA_PKGS_DIRS="$(pwd)/.conda_pkgs" conda create -p "$(pwd)/.conda" python=3.11 pip -y
PIP_CACHE_DIR="$(pwd)/.pip_cache" "$(pwd)/.conda/bin/pip" install -r requirements.txt
```

Activate:

```bash
conda activate "$(pwd)/.conda"
```

If a compatible Python environment already has `openai` and `requests`, it may run the script directly without recreating the conda environment.

## Execution

Run the main collector from this skill directory:

```bash
"$(pwd)/.conda/bin/python" react_agent.py \
  --topic "<research topic>" \
  --models gemini-3-pro-preview \
  --timeout 300 \
  --max-tool-calls 20 \
  --max-rounds 50
```

Useful options:

- `--models`: model fallback list. Default list is in `api_client.py`.
- `--timeout`: per-model-call timeout in seconds. Default is 300.
- `--target-size`: desired final paper count. Default is 400.
- `--include-abstracts`: include abstracts in the final saved JSON when available.

The script prints the final JSON list and saves a copy under `outputs/`.

## Operating Rules

1. Use this skill only for deep collection workflows. For one-off lookup or normal AMiner Q&A, route to the simpler AMiner skills.
2. Do not expose `YUNWU_API_KEY` or `AMINER_API_KEY`.
3. Keep model/tool-call budgets under control; default `--max-tool-calls 20` and `--max-rounds 50`.
4. If AMiner returns too few papers, report the actual collected count instead of inventing missing papers.
5. If a run is likely to be expensive or long, tell the user the planned topic, model, timeout, max tool calls, and output location before starting.

## File Map

- `react_agent.py`: ReAct loop and CLI.
- `api_client.py`: Yunwu/OpenAI-compatible client with model fallback.
- `prompt.py`: paper-collection system prompt.
- `search.py`: AMiner keyword search and paper detail normalization.
- `citation.py`: AMiner reference expansion.
- `paper_set.py`: deduplicated collection and final JSON output.
