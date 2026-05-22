---
description: Paper Source Trace 论文来源追踪与引用意图分析
argument-hint: [file: <pdf-or-text-path> output: <output-dir> svg: radial|chain|both template: yes|no aminer: on|off | legacy mode: current|example|all | natural language | 自然语言]
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# /paper-source-trace - Paper Source Trace

User invoked the Paper Source Trace skill with:

```text
$ARGUMENTS
```

## Language Routing / 语言路由

- If `$ARGUMENTS` or the conversation is mainly Chinese, follow **中文命令流程** and read `${CLAUDE_PLUGIN_ROOT}/SKILL.zh.md`.
- Otherwise follow **English Command Flow** and read `${CLAUDE_PLUGIN_ROOT}/SKILL.md`.
- Parameter names stay English: `file`, `output`, `svg`, `template`, `aminer`; legacy `mode` is accepted only as an alias.
- JSON keys, intent labels, relation types, and source roles stay English.
- 如果 `$ARGUMENTS` 或当前对话主要是中文，使用 **中文命令流程**。
- 否则使用 **English Command Flow**。

## English Command Flow

### 1. Task

Read and follow `${CLAUDE_PLUGIN_ROOT}/SKILL.md`. This command is an orchestration entrypoint. For `citation_map.html` and static SVG maps, use the standard renderer at `${CLAUDE_PLUGIN_ROOT}/scripts/render_html.py`; do not hand-write ad hoc SVG or HTML.

Produce the standard artifacts when evidence allows:

- `analysis.md`
- `json/graph/citation_graph.json`
- `citation_map.svg`
- `citation_map.html`
- `citation_map_chain.svg` only when `svg: both`
- `citation_map_spec.md` only when SVG generation has caveats or fails

### 2. Startup Confirmation

Before reading the paper, checking `AMINER_API_KEY`, calling AMiner, or generating SVG, ask the user to confirm both settings:

- SVG output: `radial`, `chain`, or `both`
- AMiner enrichment: `on` or `off`

If `$ARGUMENTS` already contains `svg`, legacy `mode`, or `aminer`, restate the provisional values and ask for final confirmation. Stop until the user answers. Map legacy `mode: current` to `svg: radial`, `mode: example` to `svg: chain`, and `mode: all` to `svg: both`. If `svg` and `mode` conflict, ask the user to choose one. Treat `hybrid`, `interactive graph`, or `expandable knowledge graph` as a request for the standard `citation_map.html`, not as an SVG mode.

If interactive confirmation is genuinely impossible, use the recommended defaults: `svg: both` and `aminer: on`. Keep the high-cost AMiner confirmation rule: ask before any estimated cost reaches `¥5` or more.

### 3. Parse Arguments

Accept structured fields and natural language together:

| Field | Values | Meaning |
| --- | --- | --- |
| `file` | PDF path, text path, or citation-context file path | Primary input |
| `output` | directory path | Artifact output directory |
| `svg` | `radial`, `chain`, `both` | Static SVG output |
| `mode` | `current`, `example`, `all` | Legacy alias for `svg` |
| `template` | `yes`, `no` | Whether to use `references/analysis_template.md` |
| `aminer` | `on`, `off` | Whether AMiner enrichment is explicitly requested |

Preserve the user's language preference, output requirements, AMiner opt-in, template request, and SVG output.

### 4. Input Guard

If no PDF path, text path, pasted paper text, citation contexts, reference list, or usable paper evidence is available, ask the user to provide input. Do not fabricate `analysis.md`, `json/graph/citation_graph.json`, SVG/HTML content, citations, references, claims, or source traces.

### 5. AMiner Opt-In

Check `AMINER_API_KEY` only when `aminer: on`, the user explicitly requests AMiner enrichment, or interactive confirmation is genuinely impossible and the recommended `aminer: on` fallback is being used. Never print the token. If the token is missing, skip AMiner enrichment, continue local analysis when local evidence exists, and record the skipped reason.

AMiner may enrich metadata, paper IDs, URLs, candidate reference matching, and external citation relationships. It must not be the sole evidence for citation intent or `source_traces[]`.

### 6. Output and Execution

Use `output` when provided; otherwise use:

```text
outputs/paper-source-trace/<safe-paper-stem>/
```

Output layout:

```text
analysis.md
citation_map.svg
citation_map.html
citation_map_chain.svg          # only when svg is both
citation_map_spec.md            # only when SVG generation has caveats or fails
json/graph/citation_graph.json
json/aminer/*.json              # only when AMiner raw results are saved
json/extraction/*.json          # only when structured intermediates are saved
```

Read referenced files only as needed: `references/schema.md`, `references/evidence_protocol.md`, `references/analysis_template.md` for explicit template mode, and `references/visual.md` before SVG/HTML work.

After `json/graph/citation_graph.json` exists, generate HTML and the confirmed SVG output with one renderer command:

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/render_html.py" --graph "<output>/json/graph/citation_graph.json" --output "<output>/citation_map.html" --svg "<radial|chain|both>" --language auto
```

The renderer owns both SVG modes and the HTML views. Do not generate separate ad hoc SVG layouts, extra cross-links, or mixed-language labels.

## 中文命令流程

### 1. 任务

读取并遵循 `${CLAUDE_PLUGIN_ROOT}/SKILL.zh.md`。这个命令是编排入口。生成 `citation_map.html` 和静态 SVG 图谱时必须使用 `${CLAUDE_PLUGIN_ROOT}/scripts/render_html.py` 标准渲染器，不要临场手写 SVG 或 HTML。

证据允许时生成标准产物：

- `analysis.md`
- `json/graph/citation_graph.json`
- `citation_map.svg`
- `citation_map.html`
- `citation_map_chain.svg`，仅在 `svg: both` 时生成
- `citation_map_spec.md`，仅在 SVG 生成存在限制或失败时生成

### 2. 启动确认

在读取论文、检查 `AMINER_API_KEY`、调用 AMiner 或生成 SVG 之前，先请用户确认两个设置：

- SVG 输出：`radial`、`chain` 或 `both`
- AMiner 增强：`on` 或 `off`

如果 `$ARGUMENTS` 已包含 `svg`、旧参数 `mode` 或 `aminer`，先复述为暂定值，再请求最终确认。用户回答前停止执行。旧参数 `mode: current` 映射为 `svg: radial`，`mode: example` 映射为 `svg: chain`，`mode: all` 映射为 `svg: both`。如果 `svg` 和 `mode` 冲突，必须请用户选择。`hybrid`、`interactive graph`、`expandable knowledge graph`、`交互图谱` 或 `可展开知识图谱` 表示需要标准产物 `citation_map.html`，不是 SVG 模式。

如果确实无法进行交互确认，使用推荐默认值：`svg: both` 和 `aminer: on`。保留 AMiner 高成本确认规则：预估成本达到或超过 `¥5` 时必须先询问。

### 3. 解析参数

同时接受结构化字段和自然语言：

| 字段 | 取值 | 含义 |
| --- | --- | --- |
| `file` | PDF 路径、文本路径或 citation-context 文件路径 | 主要输入 |
| `output` | 目录路径 | 产物输出目录 |
| `svg` | `radial`, `chain`, `both` | 静态 SVG 输出 |
| `mode` | `current`, `example`, `all` | `svg` 的旧别名 |
| `template` | `yes`, `no` | 是否使用 `references/analysis_template.md` |
| `aminer` | `on`, `off` | 是否显式开启 AMiner 增强 |

保留用户的语言偏好、产物要求、AMiner opt-in、模板请求和 SVG 输出选择。

### 4. 输入保护

如果没有 PDF 路径、文本路径、粘贴的论文文本、citation contexts、参考文献列表或可用论文证据，提示用户补充输入。不要伪造 `analysis.md`、`json/graph/citation_graph.json`、SVG/HTML、citations、references、claims 或 source traces。

### 5. AMiner Opt-In

只有 `aminer: on`、用户明确要求 AMiner 增强，或确实无法交互确认并采用推荐 `aminer: on` fallback 时，才检查 `AMINER_API_KEY`。绝不打印 token。如果缺少 token，跳过 AMiner 增强；在有本地证据时继续本地分析，并记录跳过原因。

AMiner 只能补充元数据、paper ID、URL、候选参考文献匹配和外部引用关系，不能作为 citation intent 或 `source_traces[]` 的唯一证据。

### 6. 输出与执行

如果用户指定 `output`，使用该目录；否则使用：

```text
outputs/paper-source-trace/<safe-paper-stem>/
```

输出结构：

```text
analysis.md
citation_map.svg
citation_map.html
citation_map_chain.svg          # only when svg is both
citation_map_spec.md            # only when SVG generation has caveats or fails
json/graph/citation_graph.json
json/aminer/*.json              # only when AMiner raw results are saved
json/extraction/*.json          # only when structured intermediates are saved
```

只在需要时读取参考文件：`references/schema.md`、`references/evidence_protocol.md`、显式模板模式下的 `references/analysis_template.md`，以及生成 SVG/HTML 前的 `references/visual.md`。

当 `json/graph/citation_graph.json` 已存在后，用同一条渲染命令生成 HTML 和已确认的 SVG 输出：

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/render_html.py" --graph "<output>/json/graph/citation_graph.json" --output "<output>/citation_map.html" --svg "<radial|chain|both>" --language auto
```

渲染器统一负责两种 SVG 模式和 HTML 视图。不要额外生成临场 SVG 布局、无效 cross-link 或中英文混杂标签。
