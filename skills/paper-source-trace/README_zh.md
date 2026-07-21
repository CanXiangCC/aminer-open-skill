# Paper Source Trace

`paper-source-trace` 中文说明。英文说明见 `README.md`。

`paper-source-trace` 是同一个 Skill 下的双语说明。用户使用英文或未指定中文时使用 `SKILL.md`；用户主要使用中文或明确要求中文输出时使用 `SKILL.zh.md`。

## 快速开始

使用自然语言：

```text
请围绕这篇论文的核心 claim 做来源追踪，识别引用意图，并生成 analysis.md、json/graph/citation_graph.json、citation_map.svg 和 citation_map.html。
```

使用 slash command：

```text
/paper-source-trace file: papers/demo.pdf output: outputs/paper-source-trace/demo svg: both template: no aminer: on
```

开始分析前必须确认 `svg` 和 `aminer`。推荐设置为 `svg: both` 和 `aminer: on`；如果确实无法交互确认，使用这两个推荐默认值。旧参数 `mode: current|example|all` 仍兼容，分别映射到 `svg: radial|chain|both`。如果 AMiner 开启但缺少 token，跳过增强并继续本地分析。

## 使用场景

当用户提供论文 PDF、抽取后的论文文本、引用上下文或参考文献，并要求以下任务时使用本 Skill：

- 引用意图识别；
- 围绕关键 claim 和贡献做来源追踪；
- 实体与关系抽取；
- 论文贡献图谱；
- `json/graph/citation_graph.json`；
- SVG 和 HTML 引用图谱；
- 可选 AMiner 元数据或引用关系增强。

## 产物

| 产物 | 说明 |
| --- | --- |
| `analysis.md` | 使用用户输出语言撰写的报告，覆盖引用意图、claim-to-source trace、图谱解读和不确定性 |
| `json/graph/citation_graph.json` | 稳定的机器可读图谱，key、intent label 和可选 `source_traces[]` 保持英文 |
| `citation_map.svg` | 由 `scripts/render_html.py` 生成的静态径向图；`svg: chain` 时为链式图 |
| `citation_map.html` | 有图谱数据时由 `scripts/render_html.py` 生成的单文件交互图谱 |
| `citation_map_chain.svg` | 仅在 `svg: both` 时由 `scripts/render_html.py` 输出的链式来源追踪 SVG |
| `citation_map_spec.md` | SVG 无法干净生成时的降级说明 |

SVG 和 HTML 图谱使用同一个固定渲染器，共享 canonical groups、配色、语言包、节点排序、文字换行和减少边线布局。HTML 额外包含 radial/chain 布局切换、搜索、筛选、缩放、平移、可拖动 citation 节点、重置布局、节点详情、来源追踪，以及用于解释角色、意图、置信度、AMiner 元数据和 trace steps 的内置 hover/focus `!` 提示。

## AMiner 规则

AMiner 是可选增强。本地来源追踪不需要 AMiner token 或 `AMINER_API_KEY`。

只有用户明确要求时才使用 AMiner，例如 `aminer:on`、`AMiner 增强`、`用 AMiner 补全`、`查 AMiner 引用链` 或 `enhance with AMiner`。

AMiner 只能补充 ID、URL、候选参考文献和外部引用元数据，不能替代本地 citation context，也不能单独证明 citation intent 或 `source_traces[]`。

## Token 配置

下面的仓库配置工具仅面向 Claude Code、Codex 等对话式 Skill 使用场景。它们会为这些会话使用的本地用户环境配置 `AMINER_API_KEY`。

Windows 可运行：

```powershell
.\tools\setup-aminer-token.cmd
```

macOS/Linux 可运行：

```bash
./tools/setup-aminer-token.sh
```

检查 token 状态时不会打印 token：

```powershell
.\tools\setup-aminer-token.ps1 -Status
```

这些工具不会配置 OpenClaw 命令运行、独立 CLI 任务、CI、定时任务或其他命令运行环境。这些环境需要在各自运行上下文中额外配置 `AMINER_API_KEY`。如果宿主环境使用 OpenClaw 风格配置，也可以在 Skill 外配置环境变量：

```bash
openclaw config set env.vars.AMINER_API_KEY "<YOUR_TOKEN>"
```

不要提交真实 token、包含 token 的截图，或打印 token 的日志。

## 参数

| 参数 | 取值 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `file` | PDF 或文本路径 | 无 | 输入论文、抽取文本、引用上下文或参考文献 |
| `output` | 输出目录 | `outputs/paper-source-trace/<safe-paper-stem>/` | 输出根目录；JSON 产物进入 `json/graph/`、`json/aminer/` 和 `json/extraction/` |
| `svg` | `radial`, `chain`, `both` | 先确认；无法确认时为 `both` | 静态 SVG 输出 |
| `mode` | `current`, `example`, `all` | 无 | 旧别名：`current -> radial`、`example -> chain`、`all -> both` |
| `template` | `yes`, `no` | `no` | 仅在明确要求时使用固定 `analysis.md` 模板 |
| `aminer` | `on`, `off` | 先确认；无法确认时为 `on` | 启用 AMiner 增强或无法确认并采用推荐默认值时检查 `AMINER_API_KEY` |

## 参考文件

- `references/schema.md`：规范 `citation_graph.json` schema，保存位置为 `json/graph/citation_graph.json`。
- `references/evidence_protocol.md`：证据链和不确定性规则。
- `references/prompts.md`：中英文抽取与审查 prompts。
- `references/visual.md`：SVG 和 HTML 图谱布局规则。
- `references/analysis_template.md`：显式模板请求使用的中英文固定报告模板。
- `scripts/render_html.py`：稳定生成 `citation_map.html`、`citation_map.svg` 和 `citation_map_chain.svg` 的标准渲染器。
