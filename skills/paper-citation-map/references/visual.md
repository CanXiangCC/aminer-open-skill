# Visual Citation Map Modes

The skill supports two static SVG modes and one reserved interactive mode. Labels should follow the user's primary language.

## Mode Decision

| User request | Output behavior |
| --- | --- |
| `current`, `current mode`, `original SVG`, `原 SVG`, `当前模式` | Generate only current mode as `citation_map.svg` |
| `example`, `reference image`, `mind map`, `例图`, `参考图`, `思维导图` | Generate only example mode as `citation_map.svg` |
| `all` | Generate current mode as `citation_map.svg` and example mode as `citation_map_example.svg` |
| `hybrid`, `expandable knowledge graph`, `混合`, `可展开知识图谱` | Explain that hybrid is reserved for future interactive Web graph rendering; do not output fixed hybrid SVG |
| No explicit mode and asking is possible | Ask which mode the user wants |
| No explicit mode and asking is not possible | Generate both current and example |

## Current Mode: Grouped Radial SVG

- Target paper stays in the center.
- Citation intent groups are arranged around the target paper.
- Group hubs use stable colors and deterministic positions.
- Group nodes show high-priority citations first.
- `show_on_map=false` citations are omitted from SVG but retained in JSON.
- Dense groups render 3 to 5 high-priority nodes and summarize overflow as `+N citations`.

Recommended group positions:

| Group | Position | Intents |
| --- | --- | --- |
| Problem/background | Upper left | `background`, `problem`, `theory` |
| Core/supporting methods | Upper right | `core-method`, `supporting-method`, `tool-resource` |
| Data/evaluation | Right or middle | `dataset`, `metric` |
| Baselines/results | Lower left | `baseline`, `result-evidence` |
| Limits/future | Bottom or far left | `limitation`, `future-work` |

## Example Mode: Reference-Image Mind Map

Use this mode for a right-side target paper with left-side layered citation chains.

Canvas recommendation: start from a wide canvas such as `2400 x 1000`, then grow height dynamically with citation count.

Readability and preservation rules:

- Preserve every citation where `show_on_map` is not `false` whenever a static SVG can remain readable.
- Prefer dynamic height, wide lanes, multi-column packing, and generous spacing over dropping nodes.
- Use `+N citations` only as an extreme fallback; full records must remain in `citation_graph.json`.
- Draw edges behind nodes.
- Keep edge labels in small badges near chain hubs or open whitespace.
- Wrap node titles with multiple text lines instead of shrinking below readable size.

Required structure:

- Target paper node on the right side, vertically centered.
- Left-side first-level chain hubs:
  - Problem chain: `background`, `problem`, `theory`
  - Method chain: `core-method`, `supporting-method`, `tool-resource`
  - Data chain: `dataset`, `metric`
  - Baseline chain: `baseline`, `result-evidence`
  - Limits/future chain: `limitation`, `future-work`
- Main edge labels in the output language.
- Second-level nodes show method components, datasets, baselines, or key author-year references.
- Dashed cross-links can show secondary roles.

Node text priority:

1. `target_claim`
2. `cited_work_role`
3. Shortened `evidence`
4. Shortened `citation_sentence`
5. Reference label from `reference_id`

## Shared Color Palette

| Intent group | Color |
| --- | --- |
| Problem/background | `#cf6f6f` |
| Core/supporting methods | `#ef6c2f` |
| Data/metrics | `#8a5cf6` |
| Baselines/results | `#d18a19` |
| Limits/future | `#4f9c56` |
| Unmatched/uncertain | `#9aa3ad` |

## SVG Requirements

- Include a visible target paper node labeled with the paper title or short title.
- Include a visible legend explaining color-to-intent mapping.
- Use deterministic layout; do not use random force-directed placement.
- Use text labels in addition to color.
- Keep main labels at least `16px` and secondary labels at least `12px`.
- Avoid long verbatim citation sentences in nodes; use short evidence labels.
- If AMiner enrichment is shown, mark it as metadata enrichment rather than citation-context evidence.

## Hybrid Mode Reservation

Hybrid means an expandable, interactive graph that reveals details on demand. It is not a fixed SVG mode yet.

When requested now:

- Do not generate a fake static hybrid SVG.
- Explain that the mode is reserved for future Web integration.
- Still provide `citation_graph.json`, because it is the data source for the future hybrid graph.
