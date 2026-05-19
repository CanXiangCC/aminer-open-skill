# Citation Graph Schema

This file defines the canonical `citation_graph.json` structure for `paper-source-trace`.

Operational note: save the canonical graph as `json/graph/citation_graph.json`. Save it even when SVG or HTML generation fails. Raw AMiner responses and structured extraction intermediates, when retained, should live under `json/aminer/` and `json/extraction/`.

## Top-Level Object

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
- `trace_ids`: array of source trace IDs that use this citation as evidence.

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

## `source_traces[]`

Optional claim-centered traces. Use this section when the supplied paper text supports tracing target-paper claims or contributions back to local citation contexts and cited-source roles.

Required fields:

| Field | Type | Description |
| --- | --- | --- |
| `trace_id` | string | Stable ID, e.g. `trace-001` |
| `claim_id` | string | Stable local claim ID, e.g. `claim-001` |
| `target_claim` | string | Target-paper claim, contribution, method choice, dataset choice, result interpretation, or limitation being traced |
| `claim_type` | string | One allowed claim type |
| `summary` | string | Source-trace summary in the output language |
| `source_steps` | array[object] | Ordered or grouped evidence steps linking the claim to cited sources |
| `confidence` | number | 0.0 to 1.0 confidence for the full trace |
| `notes` | string | Missing evidence, noisy extraction, AMiner-only metadata caveats, or uncertainty |

Allowed `claim_type` values:

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

Required `source_steps[]` fields:

| Field | Type | Description |
| --- | --- | --- |
| `citation_id` | string | Citation ID supporting this step |
| `reference_id` | string or null | Reference ID when matched; null only if unmatched |
| `source_role` | string | Role of the cited source in this trace |
| `intent` | string | One allowed citation intent label |
| `relation_type` | string | Relationship between the claim and source |
| `evidence` | string | Grounded explanation in the output language |
| `confidence` | number | 0.0 to 1.0 confidence for this step |

Recommended `source_role` values:

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

Validation rule: every source trace must be supported by at least one local citation context. AMiner metadata can enrich IDs and URLs, but cannot be the sole evidence for `source_traces[]`.

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
| `source_trace` | object | Claim-centered source trace metadata |
| `aminer_enrichment` | object | AMiner enrichment metadata |

Recommended `metadata.source_trace` fields:

| Field | Type | Description |
| --- | --- | --- |
| `enabled` | boolean | Whether claim-centered source tracing was performed |
| `strategy` | string | Use `claim-centered` |
| `claims_traced_count` | number | Number of target-paper claims traced |
| `source_steps_count` | number | Total number of source steps across traces |
| `coverage_notes` | string | Missing claims, weak evidence, noisy citation contexts, or trace limitations |

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
