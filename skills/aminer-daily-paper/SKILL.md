---
name: aminer-daily-paper
version: 1.1.2
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
| `author_name` | string | conditional | Scholar name (English). The backend resolves it to a scholar ID via person search. |
| `author_org` | string | optional | Scholar institution (English full name). Required for disambiguation when the name is ambiguous. |
| `topics` | string[] | conditional | Research topics list (English). |
| `size` | int | optional | Number of papers per call (1–20). Omit to let the model decide (see below). |
| `offset` | int | optional | Pagination offset (0–100, default 0). |
| `language_sort` | string | optional | Language preference for sorting: `zh` or `en`. |

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

## Input Formats

Structured commands or plain natural language — both are valid.

```
/aminer-dp
/aminer-dp topics: multimodal agents, tool-use
/aminer-dp scholar: Jie Tang org: Tsinghua papers: OAG-Bench | RPC-Bench
recommend me recent papers on RAG
```

`/aminer-dp` with no parameters calls the API with only the token — the API uses `AMINER_API_KEY` to identify the account and returns personalized recommendations.

**Natural language input** — you (the model) must parse it into backend-consumable fields before calling the script:

1. Extract `topics`, `author_name`, and/or `author_org` from the text. Apply the following rules:
   - **English only**: All field values must be in English. `author_name` → scholar's commonly used English name (e.g. `唐杰` → `Jie Tang`, `李飞飞` → `Fei-Fei Li`). `author_org` → institution's full English name (e.g. `清华大学` → `Tsinghua University`, `UIUC` → `University of Illinois at Urbana-Champaign`). `topics` → English research terms. The backend person search and paper retrieval APIs operate in English.
   - **Expand abbreviations**: Always use the full official English name for institutions (e.g. `MIT` → `Massachusetts Institute of Technology`, `ETH` → `ETH Zurich`, `PKU` → `Peking University`). The backend uses substring matching and cannot match abbreviations.
   - **Disambiguate scholars**: If the scholar name is ambiguous (common name, multiple matches likely), you MUST also provide `author_org`. If the user did not specify an org, ask them before proceeding — the backend will reject requests with ambiguous names and no org.
   - **Unknown English name**: If you cannot confidently determine the scholar's English name, ask the user to provide it or describe their research direction instead.
2. Decide `size` and whether to make multiple calls (see **Call Strategy** below).
3. Reconstruct the trigger with explicit fields, then call `handle_trigger.py`.

Example:
- User: `/aminer-dp 我做多模态智能体和 tool-use，帮我推荐最近论文`
- You extract: `topics: multimodal agents, tool-use`
- You call: `handle_trigger.py --text "/aminer-dp topics: multimodal agents, tool-use size: 5"`

Example (scholar):
- User: `/aminer-dp 我是唐杰，清华大学，做多模态和知识图谱`
- You extract: `scholar: Jie Tang, org: Tsinghua University, topics: multimodal, knowledge graph`
- You call: `handle_trigger.py --text "/aminer-dp scholar: Jie Tang org: Tsinghua University topics: multimodal, knowledge graph"`

Example (ambiguous name, ask user):
- User: `/aminer-dp 推荐张伟方向的论文`
- You: "张伟是一个常见名字，请提供机构信息以便精确匹配，例如：张伟，北京大学。或者直接提供 aminer_author_id。"

**`papers` field**: representative paper titles (e.g. `papers: OAG-Bench | RPC-Bench`) accompany `scholar`/`author_name` for disambiguation context. They do not map directly to an API field.

---

## Call Strategy

You decide `size` and whether to make multiple calls based on the input:

| Scenario | Action |
|----------|--------|
| Single topic or scholar, casual request | 1 call, omit `size` (default 10) |
| User explicitly asks for a number (e.g. "give me 5") | 1 call, honor the number (max 20) |
| Multiple distinct topics (e.g. RAG + multimodal agents) | 1 call per topic group, `size: 5` each |
| Broad open-ended request with no topics | 1 call, omit `size` (default 10) |

**Multi-call rules:**
- Call `handle_trigger.py` once per topic group, passing a focused `topics:` subset each time.
- Keep each `topics:` list to 1–3 closely related terms for precision.
- Make calls sequentially; present all results together after all calls finish.
- Total papers across all calls should not exceed ~15 unless the user asks for more.

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

`handle_trigger.py` parses the fields, calls the rec5 API, and returns results. It does **not** dispatch Feishu cards directly — that is a separate step.

---

## Contract

- Every explicit invocation is a new run.
- Do not answer with status-only text.
- Do not search, install, or repair skills.
- After running `handle_trigger.py`, check `final_response` in the JSON output:
  - `ENRICH_AND_DISPATCH` → Papers fetched, Feishu target detected. **You must enrich and dispatch** (see below).
  - `TEXT` → No Feishu target. Present `reply_text` to the user directly.
  - Any error → Report the `reply_text` detail to the user.

### `ENRICH_AND_DISPATCH` flow

When `final_response` is `ENRICH_AND_DISPATCH`, follow these steps:

1. **Read papers**: Load the file at `artifacts.papers_path` (a JSON file with a `papers` array).
2. **Enrich**: For each paper whose `summary` is empty or English-only, generate Chinese content following the instructions in `{baseDir}/prompts/enrich.md`:
   - `summary`: 1–2 sentence Chinese summary starting with "本文". Keep English terms as-is.
   - `keywords`: 2–4 Chinese keywords.
   - `comment`: Conference/journal tier annotation if applicable (e.g. "已发表在 AAAI（CCF-A）"), otherwise empty.
   - Do NOT fabricate information. Do NOT modify `famous_authors`.
3. **Write back**: Save the enriched data back to the same `artifacts.papers_path`.
4. **Dispatch**: Run the dispatch script:
   ```bash
   python3 "{baseDir}/scripts/dispatch_papers.py" \
     --base-dir "{baseDir}" \
     --papers-path "{artifacts.papers_path}" \
     --target "{delivery_route.target}" \
     --account "{delivery_route.account_id}"
   ```
5. **Return**: If dispatch succeeds, return exactly `NO_REPLY`. Say nothing else.

---

## Error Handling

- `AMINER_API_KEY` missing → stop, prompt user to set it.
- No profile input → prompt user to provide topics, scholar name, or `aminer_author_id`.
- API error → report the error stage; do not fall back to other skills.
