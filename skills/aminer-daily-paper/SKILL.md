---
name: aminer-daily-paper
version: 1.1.1
description: "Personalized academic paper recommendation via AMiner rec5 API. Activate this skill whenever the user asks for paper recommendations, whether triggered by /aminer-dp, /skill aminer-dp, or any natural language request such as 'recommend me papers on multimodal agents'. When invoked: extract topics/scholar signals from the input yourself, call handle_trigger.py with structured fields, then dispatch results as Feishu cards (if Feishu target is available) or return Markdown text."
user-invocable: true
disable-model-invocation: false
metadata:
  {
    "openclaw":
      {
        "emoji": "📚",
        "requires": {
          "bins": ["python3"],
          "env": ["AMINER_API_KEY"]
        },
        "primaryEnv": "AMINER_API_KEY"
      }
  }
---

# aminer-daily-paper

Personalized paper recommendation via AMiner rec5 API. Token required: set `AMINER_API_KEY` env var.
- Docs: https://open.aminer.cn/open/docs | Console: https://open.aminer.cn/open/board?tab=control

**When to activate**: any time the user asks for paper recommendations — explicit command (`/aminer-dp ...`) or natural language (`recommend me papers on RAG`, `帮我推荐最近的多模态论文`).

---

## Pre-flight: Check Required Environment Variables

**`AMINER_API_KEY`** — Always required. Check before calling the script:

```bash
[ -z "${AMINER_API_KEY+x}" ] && echo "AMINER_API_KEY missing" || echo "AMINER_API_KEY exists"
```

If missing, stop and tell the user:
> `AMINER_API_KEY` is not set. Please obtain a token at https://open.aminer.cn and set it as an environment variable.

No other environment variables are required.

---

## API Endpoint

```
POST https://datacenter.aminer.cn/gateway/open_platform/api/v3/paper/rec5
Authorization: ${AMINER_API_KEY}
Content-Type: application/json;charset=utf-8
```

### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `aminer_author_id` | string | conditional | AMiner user ID (24-char hex). |
| `author_name` | string | conditional | Scholar name. |
| `author_org` | string | optional | Scholar institution (improves disambiguation). |
| `topics` | string[] | conditional | Research topics list. |
| `size` | int | optional | Number of papers (1–20, default 5). |
| `offset` | int | optional | Pagination offset (0–100, default 0). |

At least one of `aminer_author_id`, `author_name`, or `topics` must be provided.

### Response Structure

```json
{
  "code": 200,
  "success": true,
  "data": [{
    "offset": 0,
    "size": 5,
    "total": 32,
    "papers": [{
      "paper_id": "...",
      "arxiv_id": "",
      "title": "...",
      "year": 2026,
      "authors": ["Author A", "Author B"],
      "keywords": ["kw1", "kw2"],
      "summary": "...",
      "structured_summary": {
        "research_problem": "...",
        "research_challenge": "...",
        "research_method": "...",
        "experimental_results": ""
      },
      "famous_authors": [],
      "aminer_author_profiles": [],
      "author_entries": [],
      "links": {
        "aminer": "https://www.aminer.cn/pub/{paper_id}",
        "arxiv": "",
        "pdf": ""
      },
      "paper_url": "https://www.aminer.cn/pub/{paper_id}",
      "source": "local_rec5"
    }]
  }]
}
```

---

## Input Formats

Structured commands or plain natural language — both are valid.

```
/aminer-dp
/aminer-dp topics: multimodal agents, tool-use
/aminer-dp scholar: Jie Tang org: Tsinghua papers: OAG-Bench | RPC-Bench
/aminer-dp aminer_user_id: 696259801cb939bc391d3a37 topics: multimodal, tool-use
recommend me recent papers on RAG
```

`/aminer-dp` with no parameters calls the API with only the token — the API returns personalized recommendations based on the account associated with `AMINER_API_KEY`.

**Natural language input** — you (the model) must parse it yourself before calling the script:

1. Extract `topics`, `author_name`, `author_org`, or `aminer_user_id` from the text.
2. Reconstruct the trigger with explicit fields, then call `handle_trigger.py`.

Example:
- User: `/aminer-dp 我做多模态智能体和 tool-use，帮我推荐最近论文`
- You extract: `topics: 多模态智能体, tool-use`
- You call: `handle_trigger.py --text "/aminer-dp topics: multimodal agents, tool-use"`

**`papers` field**: representative paper titles (e.g. `papers: OAG-Bench | RPC-Bench`) accompany `scholar`/`author_name` for disambiguation context. They do not map directly to an API field.

---

## Execution

Only one supported entrypoint:

```bash
python3 "{baseDir}/scripts/handle_trigger.py" \
  --base-dir "{baseDir}" \
  --text "<trigger text with explicit fields>" \
  [--target "user:{sender_id}"] \
  [--account "{accountId}"]
```

- `--text`: reconstructed trigger with explicit fields (`topics:`, `scholar:`, etc.)
- `--target`: optional Feishu delivery target (e.g. `user:ou_xxx`). Pass it when you have the sender's Feishu ID from the conversation context. Omit when not in a Feishu context.
- `--account`: optional Feishu account ID (default: `default`)

`handle_trigger.py` parses the fields, uses `--target` if provided (otherwise attempts session-store inference), calls `run_pipeline.py`, then either dispatches Feishu cards (`NO_REPLY`) or returns Markdown text (`TEXT`).

---

## Contract

- Every explicit invocation is a new run.
- Do not answer with status-only text.
- Do not search, install, or repair skills.
- After running `handle_trigger.py`, check `final_response` in the JSON output:
  - `NO_REPLY` → Feishu cards were dispatched successfully. Return exactly `NO_REPLY`, say nothing else.
  - `TEXT` → No Feishu target available. Present the `reply_text` value from the output directly to the user as your response.
  - Any error → Report the `reply_text` or `pipeline.final_response` detail to the user.

---

## Error Handling

- `AMINER_API_KEY` missing → stop, prompt user to set it.
- No profile input → prompt user to provide topics, scholar name, or `aminer_user_id`.
- API error → report the error stage; do not fall back to other skills.
