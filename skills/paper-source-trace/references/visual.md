# Visual Source Trace Modes / 可视化来源追踪模式

The Skill supports two static SVG modes plus one single-file HTML graph. Use the English rules for English output and the Chinese rules for Chinese output. Mode names remain `current`, `example`, `all`, and `hybrid`.

本 Skill 支持两个静态 SVG 模式和一个单文件 HTML 图谱。英文输出使用英文规则，中文输出使用中文规则。模式名保持 `current`、`example`、`all` 和 `hybrid`。

## English Rules

### SVG Mode Decision

| User request | Output behavior |
| --- | --- |
| `current`, `current mode`, `original SVG`, `原 SVG`, `当前模式` | Generate only current mode as `citation_map.svg` |
| `example`, `reference image`, `mind map`, `例图`, `参考图`, `思维导图` | Generate only example mode as `citation_map.svg` |
| `all` | Generate current mode as `citation_map.svg` and example mode as `citation_map_example.svg` |
| `hybrid`, `expandable knowledge graph`, `混合`, `可展开知识图谱` | Generate `citation_map.html` as the interactive graph and `citation_map.svg` as a static fallback; do not output a fake hybrid SVG |
| No explicit mode and asking is possible | Ask which mode the user wants |
| No explicit mode and asking is not possible | Generate both current and example |

### Current Mode: Grouped Radial SVG

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

### Example Mode: Reference-Image Mind Map

Use this mode for a right-side target paper with left-side layered citation chains. Start from a wide canvas such as `2400 x 1000`, then grow height dynamically with citation count.

- Preserve every citation where `show_on_map` is not `false` whenever a static SVG can remain readable.
- Prefer dynamic height, wide lanes, multi-column packing, and generous spacing over dropping nodes.
- Use `+N citations` only as an extreme fallback; full records must remain in `json/graph/citation_graph.json`.
- Draw edges behind nodes and keep edge labels in small badges near chain hubs or open whitespace.
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

Node text priority: `target_claim`, `cited_work_role`, shortened `evidence`, shortened `citation_sentence`, then reference label from `reference_id`.

### Shared Color Palette

| Intent group | Color |
| --- | --- |
| Problem/background | `#cf6f6f` |
| Core/supporting methods | `#ef6c2f` |
| Data/metrics | `#8a5cf6` |
| Baselines/results | `#d18a19` |
| Limits/future | `#4f9c56` |
| Unmatched/uncertain | `#9aa3ad` |

### SVG Requirements

- Include a visible target paper node labeled with the paper title or short title.
- Include a visible legend explaining color-to-intent mapping.
- Use deterministic layout; do not use random force-directed placement.
- Use text labels in addition to color.
- Keep main labels at least `16px` and secondary labels at least `12px`.
- Avoid long verbatim citation sentences in nodes; use short evidence labels.
- If AMiner enrichment is shown, mark it as metadata enrichment rather than citation-context evidence.

### HTML Graph Requirements

Generate `citation_map.html` whenever enough graph data exists. It is a standard artifact, not a replacement for `citation_map.svg`.

- Make it a single self-contained HTML file with inline CSS, inline JavaScript, and an embedded graph data snapshot.
- Do not depend on CDN assets, external scripts, external stylesheets, package installs, or a local HTTP server.
- Provide one page that can switch between `current` and `example` views when both layouts are available; use one `citation_map.html` even when SVG mode is `all`.
- Include a visible legend, intent-group toggles, claim/source trace viewer, node details panel, search/filter controls, and AMiner metadata badges when enrichment exists.
- Display AMiner as metadata enrichment only; do not present AMiner-only links as local citation-context evidence.
- Keep JSON keys and labels from `json/graph/citation_graph.json` unchanged inside embedded data; visible UI labels should follow the output language.
- If a view cannot be rendered cleanly, keep the data visible in a details panel and record the limitation in `analysis.md` or `citation_map_spec.md`.

### Hybrid Mode Reservation

Hybrid means an expandable, interactive graph that reveals details on demand. Use `citation_map.html` for this behavior; it is not a fixed SVG mode.

When requested now, do not generate a fake static hybrid SVG. Still provide `citation_map.svg` as a readable static fallback and `json/graph/citation_graph.json` as the HTML graph data source.

## 中文规则

### SVG 模式选择

| 用户请求 | 输出行为 |
| --- | --- |
| `current`, `current mode`, `original SVG`, `原 SVG`, `当前模式` | 只生成 current 模式的 `citation_map.svg` |
| `example`, `reference image`, `mind map`, `例图`, `参考图`, `思维导图` | 只生成 example 模式的 `citation_map.svg` |
| `all` | 生成 current 模式的 `citation_map.svg` 和 example 模式的 `citation_map_example.svg` |
| `hybrid`, `expandable knowledge graph`, `混合`, `可展开知识图谱` | 生成交互图 `citation_map.html`，并提供 `citation_map.svg` 作为静态 fallback；不要伪造 hybrid SVG |
| 未明确模式且可以询问 | 询问用户使用哪种模式 |
| 未明确模式且无法询问 | 同时生成 current 和 example |

### Current Mode：分组径向 SVG

- 目标论文位于中心。
- 引用意图分组围绕目标论文排列。
- 分组 hub 使用稳定颜色和确定性位置。
- 分组节点优先展示高优先级 citations。
- `show_on_map=false` 的 citation 不显示在 SVG 中，但保留在 JSON 中。
- 密集分组展示 3 到 5 个高优先级节点，并用 `+N citations` 概括溢出内容。

推荐分组位置：

| 分组 | 位置 | Intents |
| --- | --- | --- |
| 问题/背景 | 左上 | `background`, `problem`, `theory` |
| 核心/辅助方法 | 右上 | `core-method`, `supporting-method`, `tool-resource` |
| 数据/评估 | 右侧或中部 | `dataset`, `metric` |
| 基线/结果 | 左下 | `baseline`, `result-evidence` |
| 局限/未来 | 底部或远左 | `limitation`, `future-work` |

### Example Mode：参考图式思维导图

该模式适合右侧目标论文、左侧分层引用链。画布建议从 `2400 x 1000` 起步，并按 citation 数量动态增加高度。

- 只要静态 SVG 仍可读，就保留所有 `show_on_map` 不是 `false` 的 citation。
- 优先使用动态高度、宽 lane、多列排布和充足间距，而不是删除节点。
- 只有在极端情况下才使用 `+N citations`；完整记录必须保留在 `json/graph/citation_graph.json`。
- 边绘制在节点后方，边标签放在 chain hub 附近或空白处的小 badge 中。
- 节点标题换行显示，不要缩小到不可读。

必要结构：

- 目标论文节点在右侧垂直居中。
- 左侧一级引用链 hub：
  - 问题链：`background`, `problem`, `theory`
  - 方法链：`core-method`, `supporting-method`, `tool-resource`
  - 数据链：`dataset`, `metric`
  - 基线链：`baseline`, `result-evidence`
  - 局限/未来链：`limitation`, `future-work`
- 主要边标签使用输出语言。
- 二级节点展示方法组件、数据集、baseline 或关键 author-year 参考。
- 可用虚线 cross-link 表示 secondary roles。

节点文本优先级：`target_claim`、`cited_work_role`、缩短后的 `evidence`、缩短后的 `citation_sentence`、来自 `reference_id` 的参考文献标签。

### 共享配色

| Intent group | Color |
| --- | --- |
| Problem/background | `#cf6f6f` |
| Core/supporting methods | `#ef6c2f` |
| Data/metrics | `#8a5cf6` |
| Baselines/results | `#d18a19` |
| Limits/future | `#4f9c56` |
| Unmatched/uncertain | `#9aa3ad` |

### SVG 要求

- 包含可见的目标论文节点，标签使用论文标题或短标题。
- 包含可见图例，解释颜色与 intent 分组关系。
- 使用确定性布局，不使用随机 force-directed placement。
- 除颜色外必须使用文本标签。
- 主标签至少 `16px`，次级标签至少 `12px`。
- 不在节点中放长段 citation 原句；使用短 evidence label。
- 如果展示 AMiner 增强，必须标为 metadata enrichment，而不是 citation-context evidence。

### HTML 图谱要求

只要有足够图谱数据，就生成 `citation_map.html`。它是标准产物，不替代 `citation_map.svg`。

- 生成单文件、自包含 HTML，内联 CSS、JavaScript 和 graph data snapshot。
- 不依赖 CDN、外部脚本、外部样式、包安装或本地 HTTP server。
- 当两种布局都可用时，在一个页面内切换 `current` 和 `example` 视图；即使 SVG mode 为 `all`，也只生成一个 `citation_map.html`。
- 包含图例、intent-group 开关、claim/source trace 查看器、节点详情面板、搜索/过滤控件，以及 AMiner metadata badge。
- AMiner 只能显示为 metadata enrichment，不能把 AMiner-only links 展示成本地 citation-context evidence。
- 嵌入数据中的 `json/graph/citation_graph.json` keys 和 labels 保持不变；可见 UI 文本使用输出语言。
- 如果某个视图无法干净渲染，保留详情面板中的数据，并在 `analysis.md` 或 `citation_map_spec.md` 中记录限制。

### Hybrid Mode 保留说明

Hybrid 表示可展开、按需展示细节的交互图。当前用 `citation_map.html` 承担该行为，它不是固定 SVG 模式。

当用户请求 hybrid 时，不生成假的静态 hybrid SVG。仍提供可读的 `citation_map.svg` 作为静态 fallback，并保留 `json/graph/citation_graph.json` 作为 HTML 图谱数据源。
