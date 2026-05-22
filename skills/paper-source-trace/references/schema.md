# Citation Graph Schema / 引用图谱 Schema

This file defines the canonical `citation_graph.json` structure for `paper-source-trace`.

Operational note: save the canonical graph as `json/graph/citation_graph.json`. Save it even when SVG or HTML generation fails. Raw AMiner responses and structured extraction intermediates, when retained, should live under `json/aminer/` and `json/extraction/`.

本文件定义 `paper-source-trace` 的规范 `citation_graph.json` 结构。规范图谱必须保存为 `json/graph/citation_graph.json`；即使 SVG 或 HTML 生成失败，也要保存该 JSON。保留 AMiner 原始响应或结构化抽取中间结果时，分别放入 `json/aminer/` 和 `json/extraction/`。

## Language Routing / 语言路由

- Use English field explanations when the user uses English or does not request Chinese output.
- Use Chinese field explanations when the user mainly uses Chinese or explicitly requests Chinese output.
- JSON keys, intent labels, relation types, source roles, IDs, and file paths remain English in both languages.
- 用户使用英文或未要求中文输出时，使用英文字段说明。
- 用户主要使用中文或明确要求中文输出时，使用中文字段说明。
- 无论输出语言如何，JSON key、intent label、relation type、source role、ID 和文件路径都保持英文。

## Top-Level Object / 顶层对象

```json
{
  "schema_version": "0.3.0",
  "paper": {},
  "references": [],
  "citations": [],
  "source_traces": [],
  "entities": [],
  "relations": [],
  "visual_groups": [],
  "metadata": {}
}
```

## `paper`

Required fields / 必需字段：

| Field | Type | Description / 说明 |
| --- | --- | --- |
| `paper_id` | string | Stable local ID, usually `target-paper` / 稳定本地 ID，通常为 `target-paper` |
| `title` | string | Target paper title; use `unknown` if unavailable / 目标论文标题；不可得时用 `unknown` |
| `authors` | array[string] | Authors when available / 可获得时填写作者 |
| `year` | string or number | Publication year when available / 可获得时填写发表年份 |
| `abstract` | string | Abstract or concise summary / 摘要或简明概述 |
| `core_contributions` | array[string] | Main contributions grounded in target paper text / 基于目标论文文本的主要贡献 |

Optional AMiner fields / 可选 AMiner 字段：`aminer_paper_id`, `aminer_url`.

## `references[]`

Required fields / 必需字段：

| Field | Type | Description / 说明 |
| --- | --- | --- |
| `reference_id` | string | Stable ID, e.g. `ref-001` / 稳定 ID，例如 `ref-001` |
| `marker` | string | In-text marker, e.g. `[1]` or `Smith et al., 2020` / 文内引用标记，例如 `[1]` 或 `Smith et al., 2020` |
| `title` | string | Reference title; use `unknown` if not recoverable / 参考文献标题；不可恢复时用 `unknown` |
| `authors` | array[string] | Reference authors when available / 可获得时填写参考文献作者 |
| `year` | string or number | Reference year when available / 可获得时填写参考文献年份 |
| `raw_reference` | string | Original bibliography entry or best available text / 原始参考文献条目或最佳可用文本 |

Optional fields / 可选字段：`venue`, `doi`, `url`, `notes`, `aminer_paper_id`, `aminer_url`, `match_confidence`.

`match_confidence` is a number from `0.0` to `1.0` describing how confidently a reference entry was matched to AMiner metadata. `match_confidence` 表示参考文献条目与 AMiner 元数据匹配的置信度。

## `citations[]`

Required fields / 必需字段：

| Field | Type | Description / 说明 |
| --- | --- | --- |
| `citation_id` | string | Stable ID, e.g. `cit-001` / 稳定 ID，例如 `cit-001` |
| `reference_id` | string or null | Matched reference ID; null only if unmatched / 匹配到的参考文献 ID；只有未匹配时为 null |
| `unmatched_reference` | boolean | True when marker cannot be matched to a reference / citation marker 无法匹配参考文献时为 true |
| `marker` | string | Citation marker in the text / 文中的 citation marker |
| `section` | string | Section where citation appears / citation 出现的章节 |
| `citation_sentence` | string | Exact sentence containing the citation, preserved in the target paper's source language / 包含 citation 的原句，保留目标论文原文语言 |
| `context` | string | Exact local citation sentence plus neighboring source-language text; do not translate / citation sentence 及其邻近原文片段，保留原文语言，不要翻译 |
| `intent` | string | One allowed intent label / 一个允许的 intent label |
| `confidence` | number | 0.0 to 1.0 confidence / 0.0 到 1.0 的置信度 |
| `evidence` | string | Short grounded explanation in the output language / 使用输出语言撰写的简短证据解释 |

Optional fields / 可选字段：

- `secondary_intents`: array of allowed intent labels.
- `entity_ids`: linked entity IDs.
- `coarse_intent`: one of `background`, `method`, `result`.
- `notes`: uncertainty or extraction notes.
- `show_on_map`: boolean.
- `target_claim`: target-paper claim, method choice, dataset choice, or result interpretation supported by the citation.
- `cited_work_role`: role of the cited work.
- `intent_rationale`: why the selected intent label is more appropriate than nearby labels.
- `confidence_reason`: why the confidence value is high, medium, or low.
- `trace_ids`: array of source trace IDs that use this citation as evidence.

Validation rule: every citation must include `intent`, `evidence`, `confidence`, and either a non-empty `reference_id` or `unmatched_reference: true`. 校验规则：每条 citation 必须包含 `intent`、`evidence`、`confidence`，并且有非空 `reference_id` 或 `unmatched_reference: true`。

Allowed `intent` values / 允许的 `intent` 取值：

```text
background
problem
core-method
supporting-method
dataset
metric
baseline
tool-resource
theory
result-evidence
limitation
future-work
```

## `source_traces[]`

Optional claim-centered traces. Use this section when the supplied paper text supports tracing target-paper claims or contributions back to local citation contexts and cited-source roles.

可选的 claim-centered traces。当提供的论文文本足以把目标论文 claim 或 contribution 追溯到本地 citation contexts 和被引来源角色时，使用本字段。

Required fields / 必需字段：

| Field | Type | Description / 说明 |
| --- | --- | --- |
| `trace_id` | string | Stable ID, e.g. `trace-001` / 稳定 ID，例如 `trace-001` |
| `claim_id` | string | Stable local claim ID, e.g. `claim-001` / 稳定本地 claim ID，例如 `claim-001` |
| `target_claim` | string | Target-paper claim, contribution, method choice, dataset choice, result interpretation, or limitation being traced / 被追踪的目标论文 claim、贡献、方法选择、数据集选择、结果解释或局限 |
| `claim_type` | string | One allowed claim type / 一个允许的 claim type |
| `summary` | string | Source-trace summary in the output language / 使用输出语言撰写的来源追踪总结 |
| `source_steps` | array[object] | Ordered or grouped evidence steps linking the claim to cited sources / 将 claim 连接到被引来源的有序或分组证据步骤 |
| `confidence` | number | 0.0 to 1.0 confidence for the full trace / 整条 trace 的 0.0 到 1.0 置信度 |
| `notes` | string | Missing evidence, noisy extraction, AMiner-only metadata caveats, or uncertainty / 缺失证据、抽取噪声、AMiner-only 元数据限制或不确定性 |

Allowed `claim_type` values / 允许的 `claim_type` 取值：

```text
problem
method
dataset
evaluation
result
limitation
future-work
contribution
```

Required `source_steps[]` fields / 必需 `source_steps[]` 字段：

| Field | Type | Description / 说明 |
| --- | --- | --- |
| `citation_id` | string | Citation ID supporting this step / 支撑该步骤的 citation ID |
| `reference_id` | string or null | Reference ID when matched; null only if unmatched / 匹配到的 reference ID；只有未匹配时为 null |
| `source_role` | string | Role of the cited source in this trace / 被引来源在该 trace 中的角色 |
| `intent` | string | One allowed citation intent label / 一个允许的 citation intent label |
| `relation_type` | string | Relationship between the claim and source / claim 与 source 之间的关系 |
| `evidence` | string | Grounded explanation in the output language / 使用输出语言撰写的证据解释 |
| `confidence` | number | 0.0 to 1.0 confidence for this step / 该步骤的 0.0 到 1.0 置信度 |

Recommended `source_role` values / 推荐 `source_role` 取值：

```text
foundation
method-origin
method-adaptation
dataset-source
metric-source
baseline-comparison
evidence-support
contrast
limitation-source
future-direction
```

Validation rule: every source trace must be supported by at least one local citation context. AMiner metadata can enrich IDs and URLs, but cannot be the sole evidence for `source_traces[]`. 校验规则：每条 source trace 至少由一个本地 citation context 支撑。AMiner 元数据可以补充 ID 和 URL，但不能作为 `source_traces[]` 的唯一证据。

## `entities[]`

Required fields / 必需字段：

| Field | Type | Description / 说明 |
| --- | --- | --- |
| `entity_id` | string | Stable ID, e.g. `ent-001` / 稳定 ID，例如 `ent-001` |
| `name` | string | Entity surface name / 实体表面名称 |
| `type` | string | Entity type / 实体类型 |
| `description` | string | Description grounded in target paper text or citation evidence / 基于目标论文文本或引用证据的描述 |
| `source_citation_ids` | array[string] | Supporting citation IDs / 支撑该实体的 citation IDs |

Allowed `type` values / 允许的 `type` 取值：

```text
problem
method
component
dataset
metric
task
baseline
tool-resource
theory
result
limitation
future-work
```

## `relations[]`

Required fields / 必需字段：

| Field | Type | Description / 说明 |
| --- | --- | --- |
| `relation_id` | string | Stable ID, e.g. `rel-001` / 稳定 ID，例如 `rel-001` |
| `source_id` | string | Paper, citation, reference, or entity ID / paper、citation、reference 或 entity ID |
| `target_id` | string | Paper, citation, reference, or entity ID / paper、citation、reference 或 entity ID |
| `relation_type` | string | Relationship category / 关系类别 |
| `intent` | string or null | Citation intent when relation is citation-related / 与 citation 相关时填写 citation intent |
| `evidence` | string | Grounded explanation / 有证据支撑的解释 |

Recommended `relation_type` values / 推荐 `relation_type` 取值：

```text
cites-for
uses-method
uses-dataset
evaluates-with
compares-against
extends
contrasts-with
supports-claim
reveals-limitation
motivates
```

## `visual_groups[]`

Required fields / 必需字段：

| Field | Type | Description / 说明 |
| --- | --- | --- |
| `group_id` | string | Stable group ID / 稳定分组 ID |
| `label` | string | Display label in the output language / 使用输出语言的显示标签 |
| `intent_filters` | array[string] | Intents included in this group / 该分组包含的 intents |
| `node_ids` | array[string] | Citation/entity/reference IDs shown in this group / 该分组展示的 citation/entity/reference IDs |
| `color` | string | Hex color for the group / 该分组的十六进制颜色 |

Default groups / 默认分组：

| `group_id` | English label | Chinese label | Intents |
| --- | --- | --- | --- |
| `problem-background` | Problem/background | 问题背景 | `background`, `problem`, `theory` |
| `method-core` | Core methods | 核心方法 | `core-method`, `supporting-method`, `tool-resource` |
| `data-eval` | Data/evaluation | 数据与评估 | `dataset`, `metric` |
| `baseline-result` | Baselines/results | 基线与结果 | `baseline`, `result-evidence` |
| `limits-future` | Limits/future | 局限与未来 | `limitation`, `future-work` |

## `metadata`

Recommended fields / 推荐字段：

| Field | Type | Description / 说明 |
| --- | --- | --- |
| `source_file` | string | Relative input filename only; avoid private absolute paths / 只写相对输入文件名，避免私有绝对路径 |
| `created_at` | string | ISO-like timestamp if available / 可获得时填写 ISO 风格时间戳 |
| `extraction_method` | string | `manual`, `llm`, `cli`, or `hybrid` / `manual`、`llm`、`cli` 或 `hybrid` |
| `output_language` | string | `zh`, `en`, or another language tag / `zh`、`en` 或其他语言标签 |
| `coverage_notes` | string | Missing sections, noisy PDF text, or reference matching caveats / 缺失章节、PDF 文本噪声或参考文献匹配风险 |
| `source_trace` | object | Claim-centered source trace metadata / claim-centered source trace 元数据 |
| `aminer_enrichment` | object | AMiner enrichment metadata / AMiner 增强元数据 |

Recommended `metadata.source_trace` fields / 推荐 `metadata.source_trace` 字段：

| Field | Type | Description / 说明 |
| --- | --- | --- |
| `enabled` | boolean | Whether claim-centered source tracing was performed / 是否执行 claim-centered source tracing |
| `strategy` | string | Use `claim-centered` / 使用 `claim-centered` |
| `claims_traced_count` | number | Number of target-paper claims traced / 已追踪的目标论文 claims 数量 |
| `source_steps_count` | number | Total number of source steps across traces / 所有 traces 中 source steps 的总数 |
| `coverage_notes` | string | Missing claims, weak evidence, noisy citation contexts, or trace limitations / 缺失 claim、弱证据、噪声 citation contexts 或 trace 限制 |

Recommended `metadata.aminer_enrichment` fields / 推荐 `metadata.aminer_enrichment` 字段：

| Field | Type | Description / 说明 |
| --- | --- | --- |
| `enabled` | boolean | Whether AMiner enrichment was requested and used / 是否请求并使用了 AMiner 增强 |
| `api_chain` | array[string] | APIs called or planned / 已调用或计划调用的 APIs |
| `cost_summary` | string | Human-readable cost summary / 面向人阅读的成本摘要 |
| `matched_target` | boolean | Whether target paper was matched / 是否匹配到目标论文 |
| `matched_references_count` | number | Number of references enriched through AMiner / 通过 AMiner 增强的参考文献数量 |
| `notes` | string | Missing token, skipped paid calls, ambiguous matches, or other caveats / 缺失 token、跳过付费调用、匹配歧义或其他限制 |

## Minimal Example / 最小示例

```json
{
  "schema_version": "0.3.0",
  "paper": {
    "paper_id": "target-paper",
    "title": "Attention Is All You Need",
    "authors": ["Ashish Vaswani", "Noam Shazeer"],
    "year": 2017,
    "abstract": "A sequence transduction model based entirely on attention mechanisms.",
    "core_contributions": ["Introduces the Transformer architecture", "Replaces recurrence with self-attention"],
    "aminer_paper_id": "53e9a82db7602d970317d3d8",
    "aminer_url": "https://www.aminer.cn/pub/53e9a82db7602d970317d3d8"
  },
  "references": [
    {
      "reference_id": "ref-001",
      "marker": "[1]",
      "title": "Neural Machine Translation by Jointly Learning to Align and Translate",
      "authors": ["Dzmitry Bahdanau", "Kyunghyun Cho", "Yoshua Bengio"],
      "year": 2014,
      "raw_reference": "Bahdanau et al. Neural Machine Translation by Jointly Learning to Align and Translate. 2014.",
      "aminer_paper_id": "53e9b0f4b7602d9703b6a4f2",
      "aminer_url": "https://www.aminer.cn/pub/53e9b0f4b7602d9703b6a4f2",
      "match_confidence": 0.92
    }
  ],
  "citations": [
    {
      "citation_id": "cit-001",
      "reference_id": "ref-001",
      "unmatched_reference": false,
      "marker": "[1]",
      "section": "Introduction",
      "citation_sentence": "Attention mechanisms have become an integral part of sequence modeling and transduction models [1].",
      "context": "Attention mechanisms have become an integral part of sequence modeling and transduction models [1].",
      "intent": "core-method",
      "confidence": 0.86,
      "evidence": "The citation introduces attention as a method foundation for the target paper.",
      "secondary_intents": ["background"],
      "entity_ids": ["ent-001"],
      "coarse_intent": "method",
      "target_claim": "The target paper builds sequence transduction around attention mechanisms.",
      "cited_work_role": "method foundation",
      "intent_rationale": "The cited work is not only background; it directly supports the target method choice.",
      "confidence_reason": "The citation sentence and reference match are both clear.",
      "trace_ids": ["trace-001"]
    }
  ],
  "source_traces": [
    {
      "trace_id": "trace-001",
      "claim_id": "claim-001",
      "target_claim": "The target paper builds sequence transduction around attention mechanisms instead of recurrence.",
      "claim_type": "method",
      "summary": "The target method claim is traced to a cited attention-based translation model that supplies method foundation evidence.",
      "source_steps": [
        {
          "citation_id": "cit-001",
          "reference_id": "ref-001",
          "source_role": "foundation",
          "intent": "core-method",
          "relation_type": "uses-method",
          "evidence": "The citation sentence identifies attention mechanisms as integral to sequence modeling and transduction.",
          "confidence": 0.86
        }
      ],
      "confidence": 0.84,
      "notes": "Minimal example; the trace uses local citation context as evidence, while AMiner only enriches IDs and URLs."
    }
  ],
  "entities": [
    {
      "entity_id": "ent-001",
      "name": "attention mechanism",
      "type": "method",
      "description": "A sequence modeling method foundation used by the target paper.",
      "source_citation_ids": ["cit-001"]
    }
  ],
  "relations": [
    {
      "relation_id": "rel-001",
      "source_id": "target-paper",
      "target_id": "ent-001",
      "relation_type": "uses-method",
      "intent": "core-method",
      "evidence": "The target paper builds its architecture around attention mechanisms."
    }
  ],
  "visual_groups": [
    {
      "group_id": "method-core",
      "label": "Core methods",
      "intent_filters": ["core-method", "supporting-method", "tool-resource"],
      "node_ids": ["cit-001", "ent-001"],
      "color": "#ef5b45"
    }
  ],
  "metadata": {
    "source_file": "attention-is-all-you-need.pdf",
    "created_at": "2026-05-19T00:00:00Z",
    "extraction_method": "llm",
    "output_language": "en",
    "coverage_notes": "Minimal schema example only.",
    "source_trace": {
      "enabled": true,
      "strategy": "claim-centered",
      "claims_traced_count": 1,
      "source_steps_count": 1,
      "coverage_notes": "Only one method claim is traced in this minimal example."
    },
    "aminer_enrichment": {
      "enabled": true,
      "api_chain": ["paper_search", "paper_detail", "paper_relation", "paper_info"],
      "cost_summary": "Estimated ¥0.11 total plus free calls",
      "matched_target": true,
      "matched_references_count": 1,
      "notes": "AMiner metadata enriched IDs and URLs only; intent classification used local citation context."
    }
  }
}
```
