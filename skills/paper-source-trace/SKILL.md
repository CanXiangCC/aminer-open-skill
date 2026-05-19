---
name: paper-source-trace
description: Use when a user provides an academic paper PDF, extracted paper text, citation contexts, or references and asks for Paper Source Trace workflows, claim-centered source tracing, citation intent extraction, entity/relation extraction, contribution mapping, citation graph JSON, SVG/HTML citation maps, or optional AMiner metadata/citation enrichment.
---

# Paper Source Trace

Use this skill to trace how one academic paper uses its sources and turn that evidence into grounded, claim-centered citation artifacts:

- `analysis.md`: a report in the user's primary language.
- `json/graph/citation_graph.json`: machine-readable citation graph data.
- `citation_map.svg`: static citation map when SVG generation is possible.
- `citation_map.html`: single-file interactive graph when graph data is available.

Source tracing is claim-centered: identify the target paper's key claims or contributions, then trace which citation contexts, reference roles, and evidence steps support, inherit, adapt, contrast, or limit each claim.

Default behavior is local and evidence-first. Do not call AMiner unless the user explicitly asks for AMiner enrichment.

## Invocation

Activate this skill from either natural language or the slash-command entry:

- Natural language: requests such as `请做论文来源追踪`, `identify citation intents`, `trace the sources for these claims`, or `generate json/graph/citation_graph.json`.
- Slash command: `/paper-source-trace file: <pdf-or-text-path> output: <output-dir> mode: current|example|all|hybrid template: yes|no aminer: on|off`.

When `/paper-source-trace` is used, follow `commands/paper-source-trace.md` for argument handling, then continue with the workflow in this file. If no file, pasted paper text, citation contexts, or reference list are available, ask for input and do not fabricate artifacts.

## Startup Confirmation

Before doing any extraction, AMiner lookup, or SVG generation, ask the user to confirm these two settings:

- SVG generation mode: `current`, `example`, `all`, or `hybrid`
- AMiner enrichment: `on` or `off`

If the user already provided one or both settings, restate the provisional choice and still confirm the final pair before proceeding. Do not inspect the paper, classify citations, call AMiner, or draw SVG until the user has answered.

## Core Rules

1. Use only supplied paper text, citation contexts, reference entries, user notes, or explicitly requested AMiner results as evidence.
2. Do not infer citation intent from domain memory alone.
3. Keep `json/graph/citation_graph.json` keys, intent labels, and relation types in English.
4. Write `analysis.md`, SVG labels, evidence explanations, and final user-facing prose in the user's primary language.
5. Always preserve uncertainty. Lower confidence when citation context, section, or reference matching is incomplete.
6. If a file can be written, do not stop at a chat-only summary.

## Output Directory

Use this priority:

1. User-specified output directory.
2. `outputs/paper-source-trace/<safe-paper-stem>/` in the current workspace.
3. `<safe-paper-stem>-source-trace/` beside the source file if the workspace path is not writable.
4. If no target is writable, explain the limitation and provide inline Markdown, JSON, and SVG-ready content.

Preferred output layout:

```text
outputs/paper-source-trace/<safe-paper-stem>/
  analysis.md
  citation_map.svg
  citation_map.html
  citation_map_example.svg        # only when mode is all
  citation_map_spec.md            # only when SVG generation has caveats or fails
  json/
    graph/
      citation_graph.json
    aminer/                       # optional, only when AMiner raw results are saved
    extraction/                   # optional, only when structured intermediates are saved
```

## Standard Artifacts

- `analysis.md`: required report covering target paper, intent groups, evidence chains, entity/relation interpretation, coverage limits, and uncertainty.
- `json/graph/citation_graph.json`: required JSON following `references/schema.md`; this must exist even if SVG or HTML fails. Include `source_traces[]` when claim-centered source tracing is requested or clearly useful from the supplied evidence.
- `citation_map.svg`: required when static SVG generation is possible.
- `citation_map.html`: required when graph data is available; provide the single-file interactive graph.
- `citation_map_example.svg`: required only when visual mode is `all`.
- `citation_map_spec.md`: fallback when SVG cannot be generated; include render-ready layout notes and the failure reason.

## AMiner Enrichment

AMiner enrichment is explicit opt-in only. Trigger it when the user says phrases such as:

- `AMiner 增强`
- `用 AMiner 补全`
- `查 AMiner 引用链`
- `补全 paper_id`
- `enhance with AMiner`
- `use AMiner metadata`

When AMiner enrichment is not explicitly requested, do not check or require `AMINER_API_KEY`.

When enrichment is requested:

1. Check whether `AMINER_API_KEY` exists; never print the token.
2. If missing, continue local citation analysis and state that AMiner enrichment was skipped.
3. Use the shortest viable chain:
   - `paper_search` or `paper_search_pro` to locate the target paper.
   - `paper_detail` to enrich target metadata.
   - `paper_relation` to retrieve AMiner cited papers.
   - `paper_info` to batch-enrich cited paper basics.
4. AMiner data may enrich paper IDs, URLs, candidate references, and external citation relationships.
5. AMiner data must not replace citation contexts from the target paper and must not justify intent labels by itself.
6. Output a cost summary for all AMiner calls. If estimated cost is `¥5` or more, ask for explicit confirmation before paid calls.
7. Record enrichment metadata in `json/graph/citation_graph.json` under `metadata.aminer_enrichment`.

## Intent Labels

Use only these labels unless the user explicitly extends the taxonomy:

| Intent | Use when the citation supports |
| --- | --- |
| `background` | Related work, general context, motivation, or domain facts |
| `problem` | Problem definition, challenge, bottleneck, or known limitation |
| `core-method` | A key method or idea directly forming the target paper's method |
| `supporting-method` | Auxiliary method, component, algorithm, or implementation technique |
| `dataset` | Dataset, corpus, benchmark, testbed, or data source |
| `metric` | Evaluation metric, scoring method, protocol, or measurement setup |
| `baseline` | Compared method, prior system, SOTA result, or ablation reference |
| `tool-resource` | Library, toolkit, pretrained model, annotation tool, or external resource |
| `theory` | Theoretical definition, formula, framework, or formal analysis |
| `result-evidence` | Empirical result, observed phenomenon, evidence, or conclusion |
| `limitation` | Failure case, weakness, caveat, or negative evidence |
| `future-work` | Open question, future direction, or unresolved opportunity |

## Workflow

0. Ask the startup confirmation question and wait for the user's answer.
1. Extract reliable paper text: title, authors, abstract, sections, references, and citation markers.
2. Locate citation contexts: citation sentence plus neighboring sentences when available.
3. Read `references/evidence_protocol.md` before classifying important citations or building source traces.
4. Classify each citation with one allowed intent label; use `secondary_intents` only when necessary.
5. Extract the target paper's key claims or contributions when the text supports them.
6. Build claim-to-source traces: connect each target claim to local citation contexts, cited-work roles, and source steps.
7. Extract entities and relations that explain the target paper.
8. If AMiner enrichment was requested, enrich metadata without replacing local evidence; save AMiner raw responses under `json/aminer/` when they are retained.
9. Write `json/graph/citation_graph.json` using `references/schema.md`; include optional `source_traces[]`, `citations[].trace_ids`, and `metadata.source_trace` when trace evidence exists.
10. Write `analysis.md`; summarize claim-to-source reading paths, and use `references/analysis_template.md` only for explicit template/compliance requests.
11. Generate SVG and `citation_map.html` according to the confirmed visual mode and `references/visual.md`.
12. Validate artifacts before the final reply.

## Visual Mode Selection

Before drawing SVG, infer the user's requested mode:

- `current`, `current mode`, `original SVG`, `原 SVG`, `当前模式`: generate `citation_map.svg` with grouped radial layout.
- `example`, `reference image`, `mind map`, `例图`, `参考图`, `思维导图`: generate `citation_map.svg` with reference-image mind-map layout.
- `all`: generate `citation_map.svg` and `citation_map_example.svg`.
- `hybrid`, `expandable knowledge graph`, `混合`, `可展开知识图谱`: generate `citation_map.html` as the interactive graph and keep `citation_map.svg` as the static fallback; do not fake a separate hybrid SVG.
- If the mode is still unknown after startup confirmation, ask which mode to use before proceeding.
- Do not choose a visual mode implicitly when the user has not confirmed one.

Read `references/visual.md` before writing SVG.

## Template Mode

Use the fixed `analysis.md` template only when the user explicitly asks for a template or compliance format, for example:

- `使用模板`
- `按模板`
- `符合规范`
- `标准格式`
- `固定结构`
- `规范化报告`
- `template`
- `standard format`

When triggered, read `references/analysis_template.md` and keep the required section order. Do not invent citations to fill rows.

## Reference Files

- `references/schema.md`: canonical `citation_graph.json` schema saved as `json/graph/citation_graph.json`.
- `references/evidence_protocol.md`: evidence-chain and uncertainty rules.
- `references/prompts.md`: LLM extraction and review prompts.
- `references/visual.md`: SVG layout rules.
- `references/analysis_template.md`: fixed report template for explicit template mode.

## Quality Checks

- Every citation has `intent`, `evidence`, `confidence`, and either `reference_id` or `unmatched_reference: true`.
- Every intent label is in the allowed list.
- Key citations trace back to a citation sentence or context.
- Every entity is supported by at least one citation.
- Every source trace is grounded in at least one local citation context; AMiner metadata cannot be the sole support for a trace.
- Every source trace links back to citation and reference IDs whenever those IDs are available.
- `json/graph/citation_graph.json` remains complete even when Markdown summarizes dense groups.
- SVG or HTML failures do not block `json/graph/citation_graph.json`; record the gap in `analysis.md`.
- AMiner enrichment, when used, is recorded as metadata and never treated as local citation-context evidence.
