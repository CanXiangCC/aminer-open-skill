---
description: AMiner deep multi-round paper collection for survey references
argument-hint: "[research topic | topic: ... target-size: 400]"
allowed-tools: Read, Bash, Glob, Grep
---

# /aminer-deep-search - AMiner Deep Search

User invoked the AMiner deep paper collection skill with the following arguments:

```text
$ARGUMENTS
```

## Your task

Follow `${CLAUDE_PLUGIN_ROOT}/SKILL.md`. Use this command only for deep survey-style paper collection, not for simple paper lookup or lightweight recommendations.

### 1. Parse `$ARGUMENTS`

Extract:

- `topic`: required research topic. Preserve the user's wording.
- `target-size`: optional final paper target, default 400.
- `timeout`: optional per-model-call timeout, default 300.
- `max-tool-calls`: optional ordinary tool-call budget, default 20.
- `max-rounds`: optional controller round budget, default 50.
- `include-abstracts`: optional boolean flag.
- `api-key`, `base-url`, `models`: optional external-LLM CLI overrides.

If the topic is absent or too vague, ask the user to provide a concrete research topic.

### 2. Select the controller mode

Use **external-LLM mode** when `LLM_API_KEY` (legacy: `llm.api_key`) is set or `$ARGUMENTS` contains `--api-key`. Otherwise, use **backing-model mode**: the Claude Code, Codex, OpenClaw, or other model currently executing this command acts as the controller and calls the tool CLIs itself.

An LLM key is optional for the skill as a whole. It is only required when running `react_agent.py` in external-LLM mode. Never print any key.

### 3. Pre-flight

Verify the AMiner API key:

```bash
[ -z "${AMINER_API_KEY:-}" ] && echo "AMINER_API_KEY missing" || echo "AMINER_API_KEY exists"
```

If missing, stop and tell the user to set `AMINER_API_KEY`. Do not call the script.

In external-LLM mode, verify that a model is available through `LLM_MODEL` (legacy: `llm.model`) or `--models`. If neither is available, stop and ask the user to provide one.

Then verify the external-LLM dependencies:

```bash
python3 - <<'PY'
import importlib.util
missing = [name for name in ("openai", "requests") if importlib.util.find_spec(name) is None]
print("Missing Python packages: " + ", ".join(missing) if missing else "External-LLM dependencies exist")
PY
```

In backing-model mode, do not require an LLM key, model name, or the `openai` package. Verify only the AMiner tool dependency:

```bash
python3 - <<'PY'
import importlib.util
print("requests missing" if importlib.util.find_spec("requests") is None else "Backing-model dependencies exist")
PY
```

If dependencies are missing, stop and ask the user to install them with the setup command in `${CLAUDE_PLUGIN_ROOT}/SKILL.md`. Do not call the script.

### 4. Run the collector

Tell the user the planned topic, timeout, max tool calls, max rounds, target size, and output location before starting.

#### External-LLM mode

Run `react_agent.py` from the skill root:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/react_agent.py" \
  --topic "<research topic>" \
  --timeout 300 \
  --max-tool-calls 20 \
  --max-rounds 50 \
  --target-size 400
```

Only include optional CLI flags when the user supplied them. Do not hard-code provider-specific LLM tokens, base URLs, or model names.

#### Backing-model mode

Do not run `react_agent.py`. Read the collection strategy in `${CLAUDE_PLUGIN_ROOT}/prompt.py`, act as the controller, and iteratively call:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/search.py" --query "<query>" --size 20 --order n_citation
python3 "${CLAUDE_PLUGIN_ROOT}/citation.py" --ids <id1> <id2> --topic "<research topic>"
```

Expand queries, select strong seeds, snowball backward references, and maintain a collection deduplicated by AMiner paper ID. Respect `max-tool-calls`, `max-rounds`, and `target-size`; stop early when results are exhausted. Save the final `[{"id": "...", "title": "..."}, ...]` list under `${CLAUDE_PLUGIN_ROOT}/outputs/`. Never fabricate papers.

### 5. Present the result

Render the final JSON summary path and collected paper count. If the run fails due to missing configuration or API errors, show the actionable error without exposing secrets.
