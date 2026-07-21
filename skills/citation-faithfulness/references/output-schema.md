# Output / Return Value Contract / 返回值契约

This skill is **agent-driven** — there is no script and no stdout JSON. Its "return value" is the report the agent produces at stage **S5**, in two forms:

1. **On-screen presentation** — a human-readable summary + table shown to the user (see SKILL.md → Output Presentation).
2. **Full JSON report** — the complete machine-readable object, **always** written to the `output` path; when the user supplies no path, default to `citation-faithfulness-<pdf-stem>.json` in the current working directory. The presentation is rendered from this object.

This file defines the shape of that JSON object so the return value is stable and consumable by other tools.

本 skill 是 **agent 驱动**——没有脚本、没有 stdout JSON。它的"返回值"就是 agent 在 **S5** 阶段产出的报告，两种形态：

1. **屏幕展示** —— 给用户看的可读汇总 + 表格（见 SKILL.zh.md → 结果展示）。
2. **完整 JSON 报告** —— 完整的机器可读对象；**必写**到 `output` 路径，用户没给路径时默认写到当前工作目录的 `citation-faithfulness-<pdf文件名>.json`。屏幕展示由该对象渲染。

本文件定义该 JSON 对象的结构，使返回值稳定、可被其他工具消费。

---

## Top-level object / 顶层对象

```json
{
  "schema_version": "1.0",
  "paper": {
    "pdf_path": "/abs/path/to/paper.pdf",
    "title": "<paper title>",
    "pages_read": "1-40"
  },
  "run": {
    "scope": "all",
    "max_refs": null,
    "aminer_enrichment_used": false,
    "total_in_text_citations": 57,
    "unique_sources": 40,
    "sources_checked": 40,
    "sources_skipped": 0
  },
  "summary": {
    "verdict_counts": {
      "SUPPORTED": 31,
      "PARTIALLY_SUPPORTED": 4,
      "NOT_SUPPORTED": 2,
      "NOT_IN_SOURCE": 1,
      "UNVERIFIABLE": 19
    },
    "retrieval_coverage": {
      "full_text": 14,
      "abstract_only": 21,
      "metadata_only": 3,
      "not_found": 2
    },
    "honesty_note": "21/40 sources were abstract-only; body-level claims there are UNVERIFIABLE, not cleared."
  },
  "claims": [ /* array of claim records, see below */ ],
  "flagged": [ "c12", "c33", "c41" ],
  "skipped": [ /* claims/refs deliberately not checked, with reason */ ]
}
```

### Field notes / 字段说明

| Field | Meaning / 含义 |
| --- | --- |
| `schema_version` | Contract version of this JSON. / 本 JSON 的契约版本。 |
| `paper.pages_read` | Which page ranges the Read tool actually ingested. / Read 工具实际读入的页范围。 |
| `run.scope` | `all` / `specific-only` / `refs:...` as requested. / 请求的核查范围。 |
| `run.total_in_text_citations` | Every in-text citation occurrence found (before dedup). / 找到的正文引用出现次数（去重前）。 |
| `run.unique_sources` | Distinct cited works after dedup. / 去重后的被引工作数。 |
| `run.sources_skipped` | Unique sources not retrieved due to `max-refs`/`scope`. / 因 `max-refs`/`scope` 未检索的去重原文数。 |
| `summary.verdict_counts` | Count per verdict over all **claim records**. / 按判定统计所有**声称记录**。 |
| `summary.retrieval_coverage` | Count per `retrieval_level` over **unique sources**. / 按检索层级统计**去重原文**。 |
| `summary.honesty_note` | One line stating how shallow/deep the check went. / 一句话说明核查深浅。 |
| `flagged` | `claim_id`s of every `NOT_SUPPORTED` / `NOT_IN_SOURCE` item, severity-ordered. / 所有 `NOT_SUPPORTED`/`NOT_IN_SOURCE` 项的 `claim_id`，按严重度排序。 |
| `skipped` | Items deliberately not checked, each with a reason — never silently dropped. / 故意未核查的项，各带原因，绝不静默丢弃。 |

> Invariants / 不变式：
> - `sum(verdict_counts) == len(claims)`.
> - `sum(retrieval_coverage) == unique_sources`.
> - Every `flagged` id appears in `claims` with verdict `NOT_SUPPORTED` or `NOT_IN_SOURCE`.

## Claim record / 单条声称记录

Each element of `claims[]` (identical to the per-claim shape in `rubric.md`):

`claims[]` 的每个元素（与 `rubric.md` 的单条结构一致）：

```json
{
  "claim_id": "c12",
  "section": "4.2 Results",
  "claim_text": "X reaches 92% top-1 on ImageNet",
  "citation_sentence": "<sentence from the paper, original language>",
  "claim_type": "specific",
  "cited_work": {
    "marker": "[12]",
    "title": "...",
    "authors": "...",
    "year": 2021,
    "doi": "...",
    "arxiv_id": "...",
    "source_url": "https://arxiv.org/abs/....",
    "unmatched_reference": false
  },
  "retrieval_level": "abstract_only",
  "verdict": "UNVERIFIABLE",
  "confidence": "medium",
  "evidence": "<quote from the source, original language, or empty if none>",
  "reason": "<explanation in the user's language>",
  "notes": "<noise / version mismatch / etc., if any>"
}
```

### Enumerations / 枚举值

| Field | Allowed values / 允许值 |
| --- | --- |
| `claim_type` | `specific` · `method` · `background` |
| `retrieval_level` | `full_text` · `abstract_only` · `metadata_only` · `not_found` |
| `verdict` | `SUPPORTED` · `PARTIALLY_SUPPORTED` · `NOT_SUPPORTED` · `NOT_IN_SOURCE` · `UNVERIFIABLE` |
| `confidence` | `high` (0.80–1.00) · `medium` (0.55–0.79) · `low` (0.10–0.54) |

Language rule / 语言规则: `citation_sentence` and `evidence` stay in the **source's original language**; `reason` and `notes` follow the user's language. Enum labels and JSON keys stay English. / `citation_sentence` 与 `evidence` 保留**原文语言**；`reason`、`notes` 跟随用户语言；枚举标签与 JSON key 保持英文。

## What the user sees vs. what is returned / 用户所见 vs. 返回

- **Always shown**: the `summary` block, then the **full record** of every non-`SUPPORTED` item (`citation_sentence` · cited work · verdict · `retrieval_level` · `confidence` · `evidence` · `reason` · `notes`), severity-ordered with `NOT_SUPPORTED` / `NOT_IN_SOURCE` first. `SUPPORTED` items may be shown as counts only. / **必展示**：`summary` 块 → 每个非 `SUPPORTED` 项的**完整记录**（`citation_sentence`·被引工作·判定·`retrieval_level`·`confidence`·`evidence`·`reason`·`notes`），按严重度排序、`NOT_SUPPORTED`/`NOT_IN_SOURCE` 在前；`SUPPORTED` 项可只报计数。
- **Written to `output`** (always; default `citation-faithfulness-<pdf-stem>.json` in the current working directory): the entire top-level object above. / **写入 `output`**（必写；默认当前工作目录下的 `citation-faithfulness-<pdf文件名>.json`）：上面整个顶层对象。
- **Never**: fabricated verdicts or evidence. A source that could not be read is `UNVERIFIABLE` with empty `evidence`. / **绝不**：编造判定或证据。读不到的原文判 `UNVERIFIABLE`、`evidence` 留空。
