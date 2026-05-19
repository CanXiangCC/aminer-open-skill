# LLM Prompt Reference

Use these prompts when the workflow needs LLM-assisted extraction. Replace placeholders before use.

Keep `json/graph/citation_graph.json` keys, intent labels, and relation types in English. Write explanations in `{{output_language}}`.

## System Prompt

```text
You are an academic paper analysis assistant. Extract citation intents, claim-centered source traces, entities, and relations from one target paper.

Rules:
1. Use only the supplied target paper text, citation contexts, reference list, user notes, and explicitly requested AMiner metadata.
2. Use only the allowed intent labels.
3. Ground every citation intent in a citation sentence, local context, section name, or reference entry.
4. AMiner metadata may enrich IDs and URLs but cannot replace citation context evidence.
5. Ground every source trace in at least one local citation context; AMiner metadata alone cannot prove a trace.
6. If evidence is weak, lower confidence and explain uncertainty in {{output_language}}.
7. Keep JSON keys and labels in English.
8. Output a complete object that can be saved as json/graph/citation_graph.json after validation.
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

## Source Trace Extraction Prompt

```text
Task: Build claim-centered source traces from the target paper.

Use only target-paper claims, citation records, reference entries, and explicitly requested AMiner metadata. AMiner metadata may enrich IDs and URLs, but cannot be the sole evidence for a trace.

Output language for summaries, evidence, and notes: {{output_language}}

Allowed claim_type values:
problem, method, dataset, evaluation, result, limitation, future-work, contribution

Recommended source_role values:
foundation, method-origin, method-adaptation, dataset-source, metric-source, baseline-comparison, evidence-support, contrast, limitation-source, future-direction

<target_paper_summary>
{{target_paper_summary}}
</target_paper_summary>

<citations>
{{citations_json}}
</citations>

<references>
{{references_json}}
</references>

Return JSON only:
{
  "source_traces": [
    {
      "trace_id": "trace-001",
      "claim_id": "claim-001",
      "target_claim": "target-paper claim being traced",
      "claim_type": "method",
      "summary": "claim-to-source trace summary in output language",
      "source_steps": [
        {
          "citation_id": "cit-001",
          "reference_id": "ref-001 or null",
          "source_role": "foundation",
          "intent": "one allowed citation intent label",
          "relation_type": "uses-method",
          "evidence": "grounded explanation from local citation context",
          "confidence": 0.0
        }
      ],
      "confidence": 0.0,
      "notes": "uncertainty, missing evidence, or AMiner metadata caveat"
    }
  ],
  "metadata": {
    "source_trace": {
      "enabled": true,
      "strategy": "claim-centered",
      "claims_traced_count": 0,
      "source_steps_count": 0,
      "coverage_notes": "coverage summary"
    }
  }
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
5. Every source trace is supported by at least one local citation context and links to citation_id/reference_id when available.
6. AMiner metadata is not used as the sole evidence for source_traces.
7. Weak, noisy, or table-derived evidence is not reported as high confidence.
8. visual_groups and show_on_map cues are sufficient for SVG or a deterministic fallback.

Return a concise issue list in {{output_language}}.
```
