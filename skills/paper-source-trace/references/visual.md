# Visual Source Trace Modes

The skill supports two static SVG modes plus one single-file HTML graph. Labels should follow the user's primary language.

## SVG Mode Decision

| User request | Output behavior |
| --- | --- |
| `current`, `current mode`, `original SVG`, `原 SVG`, `当前模式` | Generate only current mode as `citation_map.svg` |
| `example`, `reference image`, `mind map`, `例图`, `参考图`, `思维导图` | Generate only example mode as `citation_map.svg` |
| `all` | Generate current mode as `citation_map.svg` and example mode as `citation_map_example.svg` |
| `hybrid`, `expandable knowledge graph`, `混合`, `可展开知识图谱` | Generate `citation_map.html` as the interactive graph and `citation_map.svg` as a static fallback; do not output a fake hybrid SVG |
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
- Use `+N citations` only as an extreme fallback; full records must remain in `json/graph/citation_graph.json`.
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

## HTML Graph Requirements

Generate `citation_map.html` whenever enough graph data exists. It is a standard artifact, not a replacement for `citation_map.svg`.

- Make it a single self-contained HTML file with inline CSS, inline JavaScript, and an embedded graph data snapshot.
- Do not depend on CDN assets, external scripts, external stylesheets, package installs, or a local HTTP server.
- Provide one page that can switch between `current` and `example` views when both layouts are available; use one `citation_map.html` even when SVG mode is `all`.
- Include a visible legend, intent-group toggles, claim/source trace viewer, node details panel, search/filter controls, and AMiner metadata badges when enrichment exists.
- Display AMiner as metadata enrichment only; do not present AMiner-only links as local citation-context evidence.
- Keep JSON keys and labels from `json/graph/citation_graph.json` unchanged inside embedded data; visible UI labels should follow the user's primary language.
- If a view cannot be rendered cleanly, keep the data visible in a details panel and record the limitation in `analysis.md` or `citation_map_spec.md`.

## Hybrid Mode Reservation

Hybrid means an expandable, interactive graph that reveals details on demand. Use `citation_map.html` for this behavior; it is not a fixed SVG mode.

When requested now:

- Do not generate a fake static hybrid SVG.
- Still provide `citation_map.svg` as a readable static fallback.
- Still provide `json/graph/citation_graph.json`, because it is the data source for the HTML graph.
