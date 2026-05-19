---
description: Paper Source Trace 论文来源追踪与引用意图分析
argument-hint: [file: <pdf-or-text-path> output: <output-dir> mode: current|example|all|hybrid template: yes|no aminer: on|off | natural language | 自然语言]
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# /paper-source-trace - Paper Source Trace

User invoked the Paper Source Trace skill with:

```text
$ARGUMENTS
```

## Language Routing / 语言路由

- If `$ARGUMENTS` or the conversation is mainly Chinese, follow **中文命令流程**.
- Otherwise follow **English Command Flow**.
- Parameter names stay English: `file`, `output`, `mode`, `template`, `aminer`.
- JSON keys, intent labels, relation types, and source roles stay English.
- 如果 `$ARGUMENTS` 或当前对话主要是中文，使用 **中文命令流程**。
- 否则使用 **English Command Flow**。

## English Command Flow

### 1. Task

Read and follow `${CLAUDE_PLUGIN_ROOT}/SKILL.md`. This command is an orchestration entrypoint, not a standalone parser or renderer.

Produce the standard artifacts when evidence allows:

- `analysis.md`
- `json/graph/citation_graph.json`
- `citation_map.svg`
- `citation_map.html`
- `citation_map_example.svg` only when `mode: all`
- `citation_map_spec.md` only when SVG generation has caveats or fails

### 2. Startup Confirmation

Before reading the paper, checking `AMINER_API_KEY`, calling AMiner, or generating SVG, ask the user to confirm both settings:

- SVG mode: `current`, `example`, `all`, or `hybrid`
- AMiner enrichment: `on` or `off`

If `$ARGUMENTS` already contains `mode` or `aminer`, restate the provisional values and ask for final confirmation. Stop until the user answers.

### 3. Parse Arguments

Accept structured fields and natural language together:

| Field | Values | Meaning |
| --- | --- | --- |
| `file` | PDF path, text path, or citation-context file path | Primary input |
| `output` | directory path | Artifact output directory |
| `mode` | `current`, `example`, `all`, `hybrid` | Visual mode |
| `template` | `yes`, `no` | Whether to use `references/analysis_template.md` |
| `aminer` | `on`, `off` | Whether AMiner enrichment is explicitly requested |

Preserve the user's language preference, output requirements, AMiner opt-in, template request, and visual mode.

### 4. Input Guard

If no PDF path, text path, pasted paper text, citation contexts, reference list, or usable paper evidence is available, ask the user to provide input. Do not fabricate `analysis.md`, `json/graph/citation_graph.json`, SVG/HTML content, citations, references, claims, or source traces.

### 5. AMiner Opt-In

Default: `aminer: off`.

Check `AMINER_API_KEY` only when `aminer: on` or the user explicitly requests AMiner enrichment. Never print the token. If the token is missing, skip AMiner enrichment, continue local analysis when local evidence exists, and record the skipped reason.

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
citation_map_example.svg        # only when mode is all
citation_map_spec.md            # only when SVG generation has caveats or fails
json/graph/citation_graph.json
json/aminer/*.json              # only when AMiner raw results are saved
json/extraction/*.json          # only when structured intermediates are saved
```

Read referenced files only as needed: `references/schema.md`, `references/evidence_protocol.md`, `references/analysis_template.md` for explicit template mode, and `references/visual.md` before SVG/HTML work.

## 中文命令流程

### 1. 任务

读取并遵循 `${CLAUDE_PLUGIN_ROOT}/SKILL.md`。这个命令只是编排入口，不是独立解析器或渲染器。

证据允许时生成标准产物：

- `analysis.md`
- `json/graph/citation_graph.json`
- `citation_map.svg`
- `citation_map.html`
- `citation_map_example.svg`，仅在 `mode: all` 时生成
- `citation_map_spec.md`，仅在 SVG 生成存在限制或失败时生成

### 2. 启动确认

在读取论文、检查 `AMINER_API_KEY`、调用 AMiner 或生成 SVG 之前，先请用户确认两个设置：

- SVG 模式：`current`、`example`、`all` 或 `hybrid`
- AMiner 增强：`on` 或 `off`

如果 `$ARGUMENTS` 已包含 `mode` 或 `aminer`，先复述为暂定值，再请求最终确认。用户回答前停止执行。

### 3. 解析参数

同时接受结构化字段和自然语言：

| 字段 | 取值 | 含义 |
| --- | --- | --- |
| `file` | PDF 路径、文本路径或 citation-context 文件路径 | 主要输入 |
| `output` | 目录路径 | 产物输出目录 |
| `mode` | `current`, `example`, `all`, `hybrid` | 可视化模式 |
| `template` | `yes`, `no` | 是否使用 `references/analysis_template.md` |
| `aminer` | `on`, `off` | 是否显式开启 AMiner 增强 |

保留用户的语言偏好、产物要求、AMiner opt-in、模板请求和可视化模式。

### 4. 输入保护

如果没有 PDF 路径、文本路径、粘贴的论文文本、citation contexts、参考文献列表或可用论文证据，提示用户补充输入。不要伪造 `analysis.md`、`json/graph/citation_graph.json`、SVG/HTML、citations、references、claims 或 source traces。

### 5. AMiner Opt-In

默认：`aminer: off`。

只有 `aminer: on` 或用户明确要求 AMiner 增强时，才检查 `AMINER_API_KEY`。绝不打印 token。如果缺少 token，跳过 AMiner 增强；在有本地证据时继续本地分析，并记录跳过原因。

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
citation_map_example.svg        # only when mode is all
citation_map_spec.md            # only when SVG generation has caveats or fails
json/graph/citation_graph.json
json/aminer/*.json              # only when AMiner raw results are saved
json/extraction/*.json          # only when structured intermediates are saved
```

只在需要时读取参考文件：`references/schema.md`、`references/evidence_protocol.md`、显式模板模式下的 `references/analysis_template.md`，以及生成 SVG/HTML 前的 `references/visual.md`。
