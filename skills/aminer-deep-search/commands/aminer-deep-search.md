---
description: AMiner deep multi-round paper collection for survey references
argument-hint: [research topic | topic: ... target-size: 400]
allowed-tools: Read, Bash, Glob, Grep
---

# /aminer-deep-search - AMiner Deep Search

User invoked the AMiner deep paper collection skill with the following arguments:

```text
$ARGUMENTS
```

## Your task

Follow `${CLAUDE_PLUGIN_ROOT}/SKILL.md`. Use this command only for deep survey-style paper collection, not for simple paper lookup or lightweight recommendations.

### 1. Pre-flight

Verify the AMiner API key:

```bash
[ -z "${AMINER_API_KEY:-}" ] && echo "AMINER_API_KEY missing" || echo "AMINER_API_KEY exists"
```

If missing, stop and tell the user to set `AMINER_API_KEY`. Do not call the script.

Verify the LLM key:

```bash
if [ -z "$(printenv 'llm.api_key')" ]; then
  echo "LLM API key missing"
else
  echo "LLM API key exists"
fi
```

If missing and `$ARGUMENTS` does not include `--api-key`, stop and ask the user to configure OpenClaw `llm.api_key` or pass `--api-key`. Never print the key.

Verify the LLM model:

```bash
[ -z "$(printenv 'llm.model')" ] && echo "LLM model missing" || echo "LLM model exists"
```

If missing and `$ARGUMENTS` does not include `--models`, stop and ask the user to configure OpenClaw `llm.model` or pass `--models`.

Verify the Python dependencies:

```bash
python3 - <<'PY'
import importlib.util
missing = [name for name in ("openai", "requests") if importlib.util.find_spec(name) is None]
if missing:
    print("Missing Python packages: " + ", ".join(missing))
else:
    print("Python dependencies exist")
PY
```

If dependencies are missing, stop and ask the user to install them with the setup command in `${CLAUDE_PLUGIN_ROOT}/SKILL.md`. Do not call the script.

### 2. Parse `$ARGUMENTS`

Extract:

- `topic`: required research topic. Preserve the user's wording.
- `target-size`: optional final paper target, default 400.
- `timeout`: optional per-model-call timeout, default 300.
- `max-tool-calls`: optional ordinary tool-call budget, default 20.
- `max-rounds`: optional controller round budget, default 50.
- `include-abstracts`: optional boolean flag.
- `api-key`, `base-url`, `models`: optional LLM CLI overrides when OpenClaw does not inject `llm.api_key`, `llm.base_url`, or `llm.model`.

If the topic is absent or too vague, ask the user to provide a concrete research topic.

### 3. Run the collector

Tell the user the planned topic, timeout, max tool calls, max rounds, target size, and output location before starting.

Run from the skill root:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/react_agent.py" \
  --topic "<research topic>" \
  --timeout 300 \
  --max-tool-calls 20 \
  --max-rounds 50 \
  --target-size 400
```

Only include optional CLI flags when the user supplied them. Do not hard-code provider-specific LLM tokens, base URLs, or model names.

### 4. Present the result

Render the final JSON summary path and collected paper count. If the run fails due to missing configuration or API errors, show the actionable error without exposing secrets.
