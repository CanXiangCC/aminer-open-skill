---
name: aminer-daily-paper
version: 1.2.0
description: "Personalized academic paper recommendation via AMiner rec5 API. Activate this skill whenever the user asks for paper recommendations. When invoked: use the model to extract and normalize structured intent first, then call handle_trigger.py with a structured payload. Do not send raw natural language to the script."
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

**When to activate**: any time the user asks for paper recommendations.

This skill now follows a strict contract:

- The model is responsible for extracting user intent.
- The model must normalize the request into a structured payload.
- The script is not responsible for raw natural-language understanding.
- Do not pass raw natural language into `handle_trigger.py`.

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
| `author_name` | string | conditional | Scholar name (Chinese or English, e.g. `唐杰` or `Jie Tang`). The backend searches both `name` and `name_zh` fields. Use the name the scholar is commonly known by. |
| `author_org` | string | optional | Scholar institution (Chinese or English full name, e.g. `清华大学` or `Tsinghua University`). Helps disambiguate when the name is ambiguous. |
| `topics` | string[] | conditional | Research topic phrases. **Use the user’s wording** (Chinese, English, or mixed). The API accepts multi-language topic strings. |
| `size` | int | optional | Number of papers per call (1–20). Omit to let the model decide (see below). |
| `offset` | int | optional | Pagination offset (0–100, default 0). |
| `language_sort` | string | optional | `zh` or `en` **only when the user explicitly asks** for Chinese- or English-biased ranking (e.g. “优先中文论文” / “prefer English papers”). Otherwise omit; the request will not include this field. |

At least one of `author_name` or `topics` should be provided. When none are given, the API returns personalized recommendations based on the account associated with `AMINER_API_KEY`.

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

## Structured Input Contract

The model must normalize the user request into one of four structured modes:

- `personalized`
- `topic`
- `scholar`
- `author`

Payload schema:

```json
{
  "query_mode": "topic",
  "aminer_author_id": "",
  "scholar_name": "",
  "scholar_org": "",
  "topics": ["multimodal agents", "tool use"],
  "paper_titles": [],
  "papers_file": "",
  "language_sort": "en",
  "size": 5
}
```

Field rules:

- `query_mode`: required, one of `personalized`, `topic`, `scholar`, `author`
- `aminer_author_id`: required only for `author`; must be a 24-char hex string
- `scholar_name`: required only for `scholar`; can be Chinese or English (e.g. `唐杰` or `Jie Tang`); backend searches both `name` and `name_zh`
- `scholar_org`: optional, but recommended for `scholar` when disambiguation may be needed; can be Chinese or English (e.g. `清华大学` or `Tsinghua University`)
- `topics`: required for `topic`; preserve user intent and do not replace it with an unrelated field
- `paper_titles`: optional supporting evidence for `topic` or `scholar`
- `papers_file`: optional JSON file inside the skill directory
- `language_sort`: optional `zh` or `en` only when the user explicitly asked for a language preference
- `size`: optional integer 1 to 20

Mode rules:

- `personalized`: no topics, scholar, or author identifiers
- `topic`: at least one topic, or at least one `paper_titles`
- `scholar`: `scholar_name` required, `topics` optional
- `author`: `aminer_author_id` required, `topics` optional

### Model Responsibilities

1. Extract intent from the user's message.
2. Normalize names, institutions, topics, and language preference.
3. Choose the correct `query_mode`.
4. Ask the user for clarification when extraction is unsafe.
5. Call the script with structured payload.

### Important

- Do not send raw natural language to the script.
- Do not ask the script to infer topics from free text.
- Do not rely on the script to guess scholar names or institutions.
- If the user writes Chinese topics, keep those topic strings unless you are adding a faithful alias on the model side.

---

## Call Strategy

You decide `size` and whether to make multiple calls based on the structured request:

| Scenario | Action |
|----------|--------|
| Single topic or scholar, casual request | 1 call, omit `size` (default 10) |
| User explicitly asks for a number (e.g. "give me 5") | 1 call, honor the number (max 20) |
| Multiple distinct topics (e.g. RAG + multimodal agents) | 1 call per topic group, `size: 5` each |
| Broad open-ended request with no topics | 1 call, omit `size` (default 10) |

**Multi-call rules:**
- Call `handle_trigger.py` once per topic group, passing a focused `topics` subset each time.
- Keep each `topics:` list to 1–3 closely related terms for precision.
- Make calls sequentially; present all results together after all calls finish.
- Total papers across all calls should not exceed ~15 unless the user asks for more.

---

## Execution

Primary entrypoints:

```bash
python3 "{baseDir}/scripts/handle_trigger.py" \
  --base-dir "{baseDir}" \
  --payload-json '<structured payload json>' \
  [--config /path/to/config.yaml]
```

```bash
python3 "{baseDir}/scripts/handle_trigger.py" \
  --base-dir "{baseDir}" \
  --payload-file /path/to/payload.json \
  [--config /path/to/config.yaml]
```

Legacy compatibility entrypoint:

```bash
python3 "{baseDir}/scripts/handle_trigger.py" \
  --base-dir "{baseDir}" \
  --text "/aminer-dp topics: multimodal agents, tool-use size: 5"
```

`--text` is legacy-only and now supports:

- `/aminer-dp`
- explicit structured commands with labels such as `topics:`, `scholar:`, `org:`

`--text` does **not** support raw natural-language input anymore.

`handle_trigger.py` validates the payload, calls the rec5 API, and returns JSON including `reply_text` (Markdown) for you to show to the user.

---

## Contract

- Every explicit invocation is a new run.
- Do not answer with status-only text.
- Do not search, install, or repair skills.
- Treat the structured payload as the source of truth.
- After running `handle_trigger.py`, check `final_response` in the JSON output:
  - `TEXT` — Normal path. Present `reply_text` (Markdown) to the user. Optional: you may still refine wording for the active channel; `prompts/enrich.md` is a reference for Chinese enrichment if you want richer copy.
  - Any error → report the `reply_text` (or error detail) to the user.

**Note:** The skill only returns JSON with `reply_text`; it does not implement channel-specific sending.

---

## Error Handling

- `AMINER_API_KEY` missing → stop, prompt user to set it.
- Missing required structured fields → fix the payload or ask the user for clarification.
- Raw natural-language `--text` input → do not use it; convert it to structured payload first.
- API error → report the error stage; do not fall back to other skills.
