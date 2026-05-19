# LLM Prompt Reference

Use these prompts when the workflow needs LLM-assisted extraction. Replace placeholders before use.

Keep `citation_graph.json` keys, intent labels, and relation types in English. Write explanations in `{{output_language}}`.

## System Prompt

```text
You are an academic paper analysis assistant. Extract citation intents, entities, and relations from one target paper.

Rules:
1. Use only the supplied target paper text, citation contexts, reference list, user notes, and explicitly requested AMiner metadata.
2. Use only the allowed intent labels.
3. Ground every citation intent in a citation sentence, local context, section name, or reference entry.
4. AMiner metadata may enrich IDs and URLs but cannot replace citation context evidence.
5. If evidence is weak, lower confidence and explain uncertainty in {{output_language}}.
6. Keep JSON keys and labels in English.
7. Output a complete object that can be saved as citation_graph.json after validation.
```

## Citation Extraction Prompt

```text
Task: Extract citation records from the target paper text.

Output language for evidence and explanations: {{output_language}}

Allowed intent labels:
background, problem, core-method, supporting-method, dataset, metric, baseline, tool-resource, theory, result-evidence, limitation, future-work

Return JSON only with this shape:

{
  "citations": [
    {
      "citation_id": "cit-001",
      "reference_id": "ref-001 or null",
      "unmatched_reference": false,
      "marker": "citation marker",
      "section": "section name",
      "citation_sentence": "exact citation sentence",
      "context": "short local context",
      "intent": "one allowed label",
      "confidence": 0.0,
      "evidence": "grounded explanation in output language",
      "target_claim": "claim supported by this citation, or unknown",
      "cited_work_role": "role of the cited work, or unknown",
      "intent_rationale": "why this label fits",
      "confidence_reason": "why confidence is high, medium, or low",
      "secondary_intents": [],
      "entity_ids": [],
      "coarse_intent": "background/method/result"
    }
  ]
}
```

## Entity and Relation Prompt

```text
Task: Convert citation records into graph entities and relations.

Use only evidence from citation records and target paper summary.
Output language for descriptions and evidence: {{output_language}}

<citations>
{{citations_json}}
</citations>

Return JSON only:
{
  "entities": [
    {
      "entity_id": "ent-001",
      "name": "surface name",
      "type": "problem/method/component/dataset/metric/task/baseline/tool-resource/theory/result/limitation/future-work",
      "description": "grounded description",
      "source_citation_ids": ["cit-001"]
    }
  ],
  "relations": [
    {
      "relation_id": "rel-001",
      "source_id": "target-paper",
      "target_id": "ent-001",
      "relation_type": "uses-method",
      "intent": "one allowed intent label or null",
      "evidence": "grounded explanation"
    }
  ]
}
```

## Graph Grouping Prompt

```text
Task: Group graph nodes for a static citation map.

Use deterministic groups. Labels should be in {{output_language}}.

<citation_graph>
{{citation_graph_json}}
</citation_graph>

Return JSON only:
{
  "visual_groups": [
    {
      "group_id": "method-core",
      "label": "display label",
      "intent_filters": ["core-method", "supporting-method", "tool-resource"],
      "node_ids": ["cit-001", "ent-001"],
      "color": "#ef5b45"
    }
  ]
}
```

## JSON Repair Prompt

```text
Repair the following JSON so that it follows the citation graph schema.

Rules:
1. Return JSON only.
2. Do not invent new citations, references, entities, or labels.
3. Preserve uncertainty notes.
4. Keep intent labels in the allowed list.
5. Ensure every citation has intent, evidence, confidence, and reference_id or unmatched_reference=true.

<broken_json>
{{broken_json}}
</broken_json>
```

## Quality Review Prompt

```text
Task: Review the citation graph for schema and grounding problems.

Check:
1. Every citation has intent, evidence, confidence, and reference_id or unmatched_reference=true.
2. Every intent is allowed.
3. Every entity is supported by at least one citation.
4. AMiner metadata is not used as intent evidence by itself.
5. Weak, noisy, or table-derived evidence is not reported as high confidence.
6. visual_groups and show_on_map cues are sufficient for SVG or a deterministic fallback.

Return a concise issue list in {{output_language}}.
```
