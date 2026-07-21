# LLM Prompt Reference / LLM Prompt 参考

Use these prompts when the workflow needs LLM-assisted extraction. Replace placeholders before use.

当工作流需要 LLM 辅助抽取时使用这些 prompts。使用前替换占位符。

## Language Routing / 语言路由

- Use the English prompts when the user writes in English or does not request Chinese output.
- Use the Chinese prompts when the user mainly writes in Chinese or explicitly asks for Chinese output.
- Keep `json/graph/citation_graph.json` keys, intent labels, relation types, source roles, and IDs in English.
- Write explanations in `{{output_language}}`.
- 用户主要使用中文或明确要求中文输出时，使用中文 prompts。
- 其他情况使用英文 prompts。
- `json/graph/citation_graph.json` 的 key、intent label、relation type、source role 和 ID 保持英文。
- 解释性文本使用 `{{output_language}}`。

## English Prompts

### System Prompt

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
8. Keep `citation_sentence` and `context` in the target paper's source language; do not translate them to {{output_language}}.
9. Output a complete object that can be saved as json/graph/citation_graph.json after validation.
```

### Citation Extraction Prompt

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
      "citation_sentence": "exact source-language citation sentence",
      "context": "short source-language local context",
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

### Source Trace Extraction Prompt

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

### Entity and Relation Prompt

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

### Graph Grouping Prompt

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

### JSON Repair Prompt

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

### Quality Review Prompt

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

## 中文 Prompts

### System Prompt

```text
你是学术论文分析助手。请从一篇目标论文中抽取 citation intents、claim-centered source traces、entities 和 relations。

规则：
1. 只使用提供的目标论文文本、citation contexts、参考文献列表、用户笔记，以及用户明确要求的 AMiner 元数据。
2. 只使用允许的 intent labels。
3. 每个 citation intent 都必须由 citation sentence、本地上下文、章节名或参考文献条目支撑。
4. AMiner 元数据可以补充 ID 和 URL，但不能替代 citation context evidence。
5. 每条 source trace 至少要由一个本地 citation context 支撑；AMiner 元数据不能单独证明 trace。
6. 如果证据较弱，降低 confidence，并用 {{output_language}} 解释不确定性。
7. JSON keys 和 labels 保持英文。
8. `citation_sentence` 和 `context` 保留目标论文原文语言，不要翻译为 {{output_language}}。
8. 输出一个完整对象，验证后可保存为 json/graph/citation_graph.json。
```

### Citation Extraction Prompt

```text
任务：从目标论文文本中抽取 citation records。

证据和解释的输出语言：{{output_language}}

允许的 intent labels：
background, problem, core-method, supporting-method, dataset, metric, baseline, tool-resource, theory, result-evidence, limitation, future-work

只返回 JSON，结构如下：

{
  "citations": [
    {
      "citation_id": "cit-001",
      "reference_id": "ref-001 or null",
      "unmatched_reference": false,
      "marker": "citation marker",
      "section": "section name",
      "citation_sentence": "exact source-language citation sentence",
      "context": "short source-language local context",
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

### Source Trace Extraction Prompt

```text
任务：从目标论文中构建以 claim 为中心的 source traces。

只使用目标论文 claims、citation records、reference entries 和用户明确要求的 AMiner 元数据。AMiner 元数据可以补充 ID 和 URL，但不能作为 trace 的唯一证据。

summary、evidence 和 notes 的输出语言：{{output_language}}

允许的 claim_type values：
problem, method, dataset, evaluation, result, limitation, future-work, contribution

推荐 source_role values：
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

只返回 JSON：
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

### Entity and Relation Prompt

```text
任务：将 citation records 转换为 graph entities 和 relations。

只使用 citation records 和目标论文摘要中的证据。
description 和 evidence 的输出语言：{{output_language}}

<citations>
{{citations_json}}
</citations>

只返回 JSON：
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

### Graph Grouping Prompt

```text
任务：为静态 citation map 对图节点分组。

使用确定性分组。可见 label 使用 {{output_language}}。

<citation_graph>
{{citation_graph_json}}
</citation_graph>

只返回 JSON：
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

### JSON Repair Prompt

```text
请修复下面的 JSON，使其符合 citation graph schema。

规则：
1. 只返回 JSON。
2. 不要编造新的 citations、references、entities 或 labels。
3. 保留不确定性说明。
4. intent labels 必须属于允许列表。
5. 确保每条 citation 都有 intent、evidence、confidence，并且有 reference_id 或 unmatched_reference=true。

<broken_json>
{{broken_json}}
</broken_json>
```

### Quality Review Prompt

```text
任务：审查 citation graph 是否存在 schema 或证据支撑问题。

检查：
1. 每条 citation 都有 intent、evidence、confidence，并且有 reference_id 或 unmatched_reference=true。
2. 每个 intent 都属于允许列表。
3. 每个 entity 至少由一条 citation 支撑。
4. AMiner 元数据没有被单独用作 intent evidence。
5. 每条 source trace 至少由一个本地 citation context 支撑，并在可用时链接到 citation_id/reference_id。
6. AMiner 元数据没有作为 source_traces 的唯一证据。
7. 弱证据、噪声证据或表格来源证据没有被报告为 high confidence。
8. visual_groups 和 show_on_map 信息足以支持 SVG 或确定性 fallback。

用 {{output_language}} 返回简洁问题列表。
```
