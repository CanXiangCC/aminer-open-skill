# paper-citation-map

`paper-citation-map` turns one academic paper into citation-intent analysis artifacts. It is the unified successor to the earlier English and Chinese citation-map skills.

## Use Cases

Use this skill when a user provides a paper PDF, extracted paper text, citation contexts, or references and asks for:

- citation intent extraction;
- entity and relation extraction;
- paper contribution mapping;
- `citation_graph.json`;
- static SVG citation maps;
- optional AMiner metadata or citation-relation enrichment.

## Standard Outputs

| Output | Description |
| --- | --- |
| `analysis.md` | Report in the user's primary language, covering citation intent groups, evidence, graph interpretation, and uncertainty |
| `citation_graph.json` | Stable machine-readable graph with English keys and allowed intent labels |
| `citation_map.svg` | Static citation map when SVG generation is possible |
| `citation_map_example.svg` | Extra example-mode SVG only when visual mode is `all` |
| `citation_map_spec.md` | Fallback notes when SVG cannot be generated |

## AMiner Enrichment

AMiner is optional. Local citation analysis does not require `AMINER_API_KEY`.

AMiner enrichment is used only when explicitly requested with phrases such as `AMiner 增强`, `用 AMiner 补全`, `查 AMiner 引用链`, or `enhance with AMiner`.

When enabled, the recommended API chain is:

1. `paper_search` or `paper_search_pro` to locate the target paper.
2. `paper_detail` to enrich target metadata.
3. `paper_relation` to retrieve AMiner cited papers.
4. `paper_info` to batch-enrich cited paper basics.

AMiner data can enrich IDs, URLs, candidate references, and external cited-paper metadata. It must not replace local citation contexts or justify citation-intent labels by itself.

## Language Policy

- `analysis.md`, SVG labels, evidence explanations, and final prose follow the user's primary language.
- `citation_graph.json` keys, intent labels, relation types, and schema fields remain English.

## References

- `references/schema.md`: canonical `citation_graph.json` schema.
- `references/evidence_protocol.md`: evidence and uncertainty policy.
- `references/prompts.md`: extraction and review prompts.
- `references/visual.md`: static SVG layout rules.
- `references/analysis_template.md`: fixed report template for explicit template requests.
