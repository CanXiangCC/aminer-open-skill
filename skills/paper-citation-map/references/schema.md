# Citation Graph Schema

This file defines the canonical `citation_graph.json` structure for `paper-citation-map`.

`citation_graph.json` is the minimum required artifact. Save it even when SVG generation fails.

## Top-Level Object

```json
{
  "schema_version": "0.2.0",
  "paper": {},
  "references": [],
  "citations": [],
  "entities": [],
  "relations": [],
  "visual_groups": [],
  "metadata": {}
}
```

## `paper`

Required fields:

| Field | Type | Description |
| --- | --- | --- |
| `paper_id` | string | Stable local ID, usually `target-paper` |
| `title` | string | Target paper title; use `unknown` if unavailable |
| `authors` | array[string] | Authors when available |
| `year` | string or number | Publication year when available |
| `abstract` | string | Abstract or concise summary |
| `core_contributions` | array[string] | Main contributions grounded in target paper text |

Optional AMiner fields: `aminer_paper_id`, `aminer_url`.

## `references[]`

Required fields:

| Field | Type | Description |
| --- | --- | --- |
| `reference_id` | string | Stable ID, e.g. `ref-001` |
| `marker` | string | In-text marker, e.g. `[1]` or `Smith et al., 2020` |
| `title` | string | Reference title; use `unknown` if not recoverable |
| `authors` | array[string] | Reference authors when available |
| `year` | string or number | Reference year when available |
| `raw_reference` | string | Original bibliography entry or best available text |

Optional fields: `venue`, `doi`, `url`, `notes`, `aminer_paper_id`, `aminer_url`, `match_confidence`.

`match_confidence` is a number from `0.0` to `1.0` describing how confidently a reference entry was matched to AMiner metadata.

## `citations[]`

Required fields:

| Field | Type | Description |
| --- | --- | --- |
| `citation_id` | string | Stable ID, e.g. `cit-001` |
| `reference_id` | string or null | Matched reference ID; null only if unmatched |
| `unmatched_reference` | boolean | True when marker cannot be matched to a reference |
| `marker` | string | Citation marker in the text |
| `section` | string | Section where citation appears |
| `citation_sentence` | string | Sentence containing the citation |
| `context` | string | Citation sentence plus local neighboring evidence |
| `intent` | string | One allowed intent label |
| `confidence` | number | 0.0 to 1.0 confidence |
| `evidence` | string | Short grounded explanation in the output language |

Optional fields:

- `secondary_intents`: array of allowed intent labels.
- `entity_ids`: linked entity IDs.
- `coarse_intent`: one of `background`, `method`, `result`.
- `notes`: uncertainty or extraction notes.
- `show_on_map`: boolean.
- `target_claim`: target-paper claim, method choice, dataset choice, or result interpretation supported by the citation.
- `cited_work_role`: role of the cited work.
- `intent_rationale`: why the selected intent label is more appropriate than nearby labels.
- `confidence_reason`: why the confidence value is high, medium, or low.

Validation rule: every citation must include `intent`, `evidence`, `confidence`, and either a non-empty `reference_id` or `unmatched_reference: true`.

Allowed `intent` values:

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

## `entities[]`

Required fields:

| Field | Type | Description |
| --- | --- | --- |
| `entity_id` | string | Stable ID, e.g. `ent-001` |
| `name` | string | Entity surface name |
| `type` | string | Entity type |
| `description` | string | Description grounded in target paper text or citation evidence |
| `source_citation_ids` | array[string] | Supporting citation IDs |

Allowed `type` values:

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

Required fields:

| Field | Type | Description |
| --- | --- | --- |
| `relation_id` | string | Stable ID, e.g. `rel-001` |
| `source_id` | string | Paper, citation, reference, or entity ID |
| `target_id` | string | Paper, citation, reference, or entity ID |
| `relation_type` | string | Relationship category |
| `intent` | string or null | Citation intent when relation is citation-related |
| `evidence` | string | Grounded explanation |

Recommended `relation_type` values:

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

Required fields:

| Field | Type | Description |
| --- | --- | --- |
| `group_id` | string | Stable group ID |
| `label` | string | Display label in the output language |
| `intent_filters` | array[string] | Intents included in this group |
| `node_ids` | array[string] | Citation/entity/reference IDs shown in this group |
| `color` | string | Hex color for the group |

Default groups:

| `group_id` | English label | Chinese label | Intents |
| --- | --- | --- | --- |
| `problem-background` | Problem/background | 问题背景 | `background`, `problem`, `theory` |
| `method-core` | Core methods | 核心方法 | `core-method`, `supporting-method`, `tool-resource` |
| `data-eval` | Data/evaluation | 数据与评估 | `dataset`, `metric` |
| `baseline-result` | Baselines/results | 基线与结果 | `baseline`, `result-evidence` |
| `limits-future` | Limits/future | 局限与未来 | `limitation`, `future-work` |

## `metadata`

Recommended fields:

| Field | Type | Description |
| --- | --- | --- |
| `source_file` | string | Relative input filename only; avoid private absolute paths |
| `created_at` | string | ISO-like timestamp if available |
| `extraction_method` | string | `manual`, `llm`, `cli`, or `hybrid` |
| `output_language` | string | `zh`, `en`, or another language tag |
| `coverage_notes` | string | Missing sections, noisy PDF text, or reference matching caveats |
| `aminer_enrichment` | object | AMiner enrichment metadata |

Recommended `metadata.aminer_enrichment` fields:

| Field | Type | Description |
| --- | --- | --- |
| `enabled` | boolean | Whether AMiner enrichment was requested and used |
| `api_chain` | array[string] | APIs called or planned |
| `cost_summary` | string | Human-readable cost summary |
| `matched_target` | boolean | Whether target paper was matched |
| `matched_references_count` | number | Number of references enriched through AMiner |
| `notes` | string | Missing token, skipped paid calls, ambiguous matches, or other caveats |

## Minimal Example

```json
{
  "schema_version": "0.2.0",
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
      "confidence_reason": "The citation sentence and reference match are both clear."
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
