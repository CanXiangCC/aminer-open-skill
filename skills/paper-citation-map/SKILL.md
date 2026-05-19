---
name: paper-citation-map
description: Use when a user provides an academic paper PDF, extracted paper text, citation contexts, or references and asks for citation intent extraction, entity/relation extraction, contribution mapping, citation graph JSON, SVG citation maps, or optional AMiner metadata/citation enrichment.
---

# Paper Citation Map

Use this skill to turn one academic paper into grounded citation-intent artifacts:

- `analysis.md`: a report in the user's primary language.
- `citation_graph.json`: machine-readable citation graph data.
- `citation_map.svg`: static citation map when SVG generation is possible.

Default behavior is local and evidence-first. Do not call AMiner unless the user explicitly asks for AMiner enrichment.

## Core Rules

1. Use only supplied paper text, citation contexts, reference entries, user notes, or explicitly requested AMiner results as evidence.
2. Do not infer citation intent from domain memory alone.
3. Keep `citation_graph.json` keys, intent labels, and relation types in English.
4. Write `analysis.md`, SVG labels, evidence explanations, and final user-facing prose in the user's primary language.
5. Always preserve uncertainty. Lower confidence when citation context, section, or reference matching is incomplete.
6. If a file can be written, do not stop at a chat-only summary.

## Output Directory

Use this priority:

1. User-specified output directory.
2. `outputs/paper-citation-map/<safe-paper-stem>/` in the current workspace.
3. `<safe-paper-stem>-citation-map/` beside the source file if the workspace path is not writable.
4. If no target is writable, explain the limitation and provide inline Markdown, JSON, and SVG-ready content.

## Standard Artifacts

- `analysis.md`: required report covering target paper, intent groups, evidence chains, entity/relation interpretation, coverage limits, and uncertainty.
- `citation_graph.json`: required JSON following `references/schema.md`; this must exist even if SVG fails.
- `citation_map.svg`: required when static SVG generation is possible.
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
7. Record enrichment metadata in `citation_graph.json` under `metadata.aminer_enrichment`.

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

1. Extract reliable paper text: title, authors, abstract, sections, references, and citation markers.
2. Locate citation contexts: citation sentence plus neighboring sentences when available.
3. Read `references/evidence_protocol.md` before classifying important citations.
4. Classify each citation with one allowed intent label; use `secondary_intents` only when necessary.
5. Extract entities and relations that explain the target paper.
6. If AMiner enrichment was requested, enrich metadata without replacing local evidence.
7. Write `citation_graph.json` using `references/schema.md`.
8. Write `analysis.md`; use `references/analysis_template.md` only for explicit template/compliance requests.
9. Generate SVG according to the selected visual mode and `references/visual.md`.
10. Validate artifacts before the final reply.

## Visual Mode Selection

Before drawing SVG, infer the user's requested mode:

- `current`, `current mode`, `original SVG`, `原 SVG`, `当前模式`: generate `citation_map.svg` with grouped radial layout.
- `example`, `reference image`, `mind map`, `例图`, `参考图`, `思维导图`: generate `citation_map.svg` with reference-image mind-map layout.
- `all`: generate `citation_map.svg` and `citation_map_example.svg`.
- `hybrid`, `expandable knowledge graph`, `混合`, `可展开知识图谱`: reserved for future interactive Web rendering; do not fake a static hybrid SVG.
- No explicit mode and asking is possible: ask which mode to use.
- No explicit mode and asking is not possible: generate both current and example.

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

- `references/schema.md`: canonical `citation_graph.json` schema.
- `references/evidence_protocol.md`: evidence-chain and uncertainty rules.
- `references/prompts.md`: LLM extraction and review prompts.
- `references/visual.md`: SVG layout rules.
- `references/analysis_template.md`: fixed report template for explicit template mode.

## Quality Checks

- Every citation has `intent`, `evidence`, `confidence`, and either `reference_id` or `unmatched_reference: true`.
- Every intent label is in the allowed list.
- Key citations trace back to a citation sentence or context.
- Every entity is supported by at least one citation.
- `citation_graph.json` remains complete even when Markdown summarizes dense groups.
- SVG failures do not block `citation_graph.json`; record the gap in `analysis.md`.
- AMiner enrichment, when used, is recorded as metadata and never treated as local citation-context evidence.
