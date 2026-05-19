# Paper Source Trace

`paper-source-trace` is one Skill with two language sections. Use the English instructions when the user writes in English or does not request Chinese. Use the Chinese instructions when the user mainly writes in Chinese or explicitly asks for Chinese output.

`paper-source-trace` 是同一个 Skill 内的双语工作流。用户使用英文或未指定中文时使用英文说明；用户主要使用中文或明确要求中文输出时使用中文说明。

## English Quick Start

Use natural language:

```text
Please trace this paper's main claims, identify citation intents, and generate analysis.md, json/graph/citation_graph.json, citation_map.svg, and citation_map.html.
```

Use the slash command:

```text
/paper-source-trace file: papers/demo.pdf output: outputs/paper-source-trace/demo mode: all template: no aminer: off
```

Before analysis begins, confirm `mode` and `aminer`. Keep `aminer: off` for local analysis. Use `aminer: on` only when you explicitly want AMiner to supplement paper IDs, URLs, metadata, or citation relationships.

### English Use Cases

Use this Skill when a user provides a paper PDF, extracted paper text, citation contexts, or references and asks for:

- citation intent extraction;
- claim-to-source tracing for key claims and contributions;
- entity and relation extraction;
- paper contribution mapping;
- `json/graph/citation_graph.json`;
- SVG and HTML citation maps;
- optional AMiner metadata or citation-relation enrichment.

### English Outputs

| Output | Description |
| --- | --- |
| `analysis.md` | Report in the user's output language, covering citation intent groups, claim-to-source traces, graph interpretation, and uncertainty |
| `json/graph/citation_graph.json` | Stable machine-readable graph with English keys, allowed intent labels, and optional `source_traces[]` |
| `citation_map.svg` | Static citation map when SVG generation is possible |
| `citation_map.html` | Single-file interactive graph when graph data is available |
| `citation_map_example.svg` | Extra example-mode SVG only when visual mode is `all` |
| `citation_map_spec.md` | Fallback notes when SVG cannot be generated cleanly |

### English AMiner Policy

AMiner is optional. Local source tracing does not require an AMiner token or `AMINER_API_KEY`.

AMiner enrichment is used only when explicitly requested with phrases such as `aminer:on`, `enhance with AMiner`, `use AMiner metadata`, `AMiner 增强`, or `用 AMiner 补全`.

When enabled, AMiner may enrich IDs, URLs, candidate references, and external cited-paper metadata. It must not replace local citation contexts or justify citation-intent labels or `source_traces[]` by itself.

## 中文快速开始

使用自然语言：

```text
请围绕这篇论文的核心 claim 做来源追踪，识别引用意图，并生成 analysis.md、json/graph/citation_graph.json、citation_map.svg 和 citation_map.html。
```

使用 slash command：

```text
/paper-source-trace file: papers/demo.pdf output: outputs/paper-source-trace/demo mode: all template: no aminer: off
```

开始分析前必须确认 `mode` 和 `aminer`。本地分析保持 `aminer: off`。只有需要 AMiner 补充 paper ID、URL、元数据或引用关系时，才使用 `aminer: on`。

### 中文使用场景

当用户提供论文 PDF、抽取后的论文文本、引用上下文或参考文献，并要求以下任务时使用本 Skill：

- 引用意图识别；
- 围绕关键 claim 和贡献做来源追踪；
- 实体与关系抽取；
- 论文贡献图谱；
- `json/graph/citation_graph.json`；
- SVG 和 HTML 引用图谱；
- 可选 AMiner 元数据或引用关系增强。

### 中文产物

| 产物 | 说明 |
| --- | --- |
| `analysis.md` | 使用用户输出语言撰写的报告，覆盖引用意图、claim-to-source trace、图谱解读和不确定性 |
| `json/graph/citation_graph.json` | 稳定的机器可读图谱，key、intent label 和可选 `source_traces[]` 保持英文 |
| `citation_map.svg` | 可生成时输出的静态引用图谱 |
| `citation_map.html` | 有图谱数据时输出的单文件交互图谱 |
| `citation_map_example.svg` | 仅在 visual mode 为 `all` 时输出的 example 模式 SVG |
| `citation_map_spec.md` | SVG 无法干净生成时的降级说明 |

### 中文 AMiner 规则

AMiner 是可选增强。本地来源追踪不需要 AMiner token 或 `AMINER_API_KEY`。

只有用户明确要求时才使用 AMiner，例如 `aminer:on`、`AMiner 增强`、`用 AMiner 补全`、`查 AMiner 引用链` 或 `enhance with AMiner`。

AMiner 只能补充 ID、URL、候选参考文献和外部引用元数据，不能替代本地 citation context，也不能单独证明 citation intent 或 `source_traces[]`。

## Token Setup / Token 配置

On Windows, run the repository helper when AMiner enrichment is needed:

```powershell
.\tools\setup-aminer-token.cmd
```

Check token status without printing the token:

```powershell
.\tools\setup-aminer-token.ps1 -Status
```

Clear the user-level token:

```powershell
.\tools\setup-aminer-token.ps1 -Clear
```

如果宿主环境使用 OpenClaw 风格配置，也可以在 Skill 外配置环境变量：

```bash
openclaw config set env.vars.AMINER_API_KEY "<YOUR_TOKEN>"
```

Never commit real tokens, screenshots containing tokens, or logs that print tokens.

## Parameters / 参数

| Parameter | Values | Default | Description / 说明 |
| --- | --- | --- | --- |
| `file` | PDF or text path | none | Input paper, extracted text, citation contexts, or reference list / 输入论文、文本、引用上下文或参考文献 |
| `output` | output directory | `outputs/paper-source-trace/<safe-paper-stem>/` | Output root; JSON artifacts go under `json/graph/`, `json/aminer/`, and `json/extraction/` / 输出根目录 |
| `mode` | `current`, `example`, `all`, `hybrid` | confirm first | Static SVG mode and HTML behavior / 静态 SVG 模式与 HTML 行为 |
| `template` | `yes`, `no` | `no` | Use fixed `analysis.md` template only when requested / 仅在明确要求时使用固定模板 |
| `aminer` | `on`, `off` | `off` | Check `AMINER_API_KEY` only when AMiner enrichment is enabled / 仅显式开启 AMiner 时检查 token |

## Self Check / 自检

Run from the repository root:

```powershell
.\tools\check-paper-source-trace.ps1
```

The check validates the skill directory, slash-command entry, marketplace entry, schema example, evals, README links, old slug cleanup, and token status without printing the token.

## References / 参考文件

- `references/schema.md`: canonical `citation_graph.json` schema saved as `json/graph/citation_graph.json`.
- `references/evidence_protocol.md`: evidence and uncertainty policy.
- `references/prompts.md`: English and Chinese extraction/review prompts.
- `references/visual.md`: SVG and HTML graph layout rules.
- `references/analysis_template.md`: fixed English and Chinese report templates for explicit template requests.
