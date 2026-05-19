---
name: paper-source-trace
description: Use when a user provides an academic paper PDF, extracted paper text, citation contexts, or references and asks for Paper Source Trace workflows, claim-centered source tracing, citation intent extraction, entity/relation extraction, contribution mapping, citation graph JSON, SVG/HTML citation maps, or optional AMiner metadata/citation enrichment. 当用户提供论文 PDF、论文文本、引用上下文或参考文献，并要求论文来源追踪、引用意图识别、证据链、实体关系图谱、SVG/HTML 图谱或 AMiner 增强时使用。
---

# Paper Source Trace

Paper Source Trace turns one target paper into grounded, claim-centered source-tracing artifacts. It keeps one canonical skill name, `paper-source-trace`, while providing two execution sections below.

Paper Source Trace 将单篇目标论文转换为以 claim 为中心、证据可追溯的来源追踪产物。本 Skill 只有一个规范名称：`paper-source-trace`，但下面提供英文和中文两套执行说明。

Invoke it through natural language or `/paper-source-trace`. 你可以用自然语言或 `/paper-source-trace` 触发本 Skill。

## Language Routing / 语言路由

- Use **中文工作流** when the user mainly writes in Chinese or explicitly requests Chinese output.
- Use **English Workflow** for all other requests.
- Keep `json/graph/citation_graph.json` keys, intent labels, relation types, source roles, and parameter names in English in both workflows.
- 用户主要使用中文，或明确要求中文输出时，使用 **中文工作流**。
- 其他情况使用 **English Workflow**。
- 无论使用哪种语言，`json/graph/citation_graph.json` 的 key、intent label、relation type、source role 和参数名都保持英文。

## English Workflow

### Standard Artifacts

Produce these artifacts when evidence and filesystem access allow:

- `analysis.md`: human-readable report.
- `json/graph/citation_graph.json`: canonical machine-readable graph following `references/schema.md`.
- `citation_map.svg`: static citation map when SVG generation is possible.
- `citation_map.html`: single-file interactive graph when graph data is available.
- `citation_map_example.svg`: only when visual mode is `all`.
- `citation_map_spec.md`: only when SVG generation has caveats or fails.

Default output directory:

```text
outputs/paper-source-trace/<safe-paper-stem>/
```

Preferred layout:

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

### Startup Confirmation

Before reading the paper, extracting citations, checking `AMINER_API_KEY`, calling AMiner, or generating SVG, ask the user to confirm:

- SVG mode: `current`, `example`, `all`, or `hybrid`.
- AMiner enrichment: `on` or `off`.

If the user already supplied one or both values, restate them as provisional and still ask for final confirmation. Stop until the user answers.

### Core Rules

1. Use only supplied paper text, citation contexts, reference entries, user notes, or explicitly requested AMiner results as evidence.
2. Do not infer citation intent from domain memory alone.
3. AMiner enrichment is explicit opt-in only. Do not check `AMINER_API_KEY` unless requested.
4. AMiner may enrich IDs, URLs, candidate reference matches, and external citation relationships, but it cannot replace local citation contexts or prove intent/source traces by itself.
5. Preserve uncertainty; lower confidence when citation context, reference matching, or source role evidence is incomplete.
6. If output files can be written, do not stop at a chat-only summary.

### AMiner Enrichment

Treat AMiner as `off` by default. Enable it only for `aminer:on` or explicit wording such as `enhance with AMiner`, `use AMiner metadata`, `AMiner 增强`, `用 AMiner 补全`, `查 AMiner 引用链`, or `补全 paper_id`.

When enabled:

1. Check only whether `AMINER_API_KEY` exists; never print the token.
2. If missing, continue local analysis and record that enrichment was skipped.
3. Use the shortest viable chain: `paper_search` or `paper_search_pro`, `paper_detail`, `paper_relation`, and `paper_info`.
4. Output a cost summary for all planned or completed AMiner calls.
5. If estimated cost is `¥5` or more, ask for explicit confirmation before paid calls.
6. Record enrichment metadata under `metadata.aminer_enrichment` in `json/graph/citation_graph.json`.

### Intent Labels

Use only these labels unless the user explicitly extends the taxonomy:

`background`, `problem`, `core-method`, `supporting-method`, `dataset`, `metric`, `baseline`, `tool-resource`, `theory`, `result-evidence`, `limitation`, `future-work`.

### Execution Steps

1. Ask the startup confirmation question and wait for the answer.
2. Resolve input evidence and output directory.
3. Extract reliable paper text, reference entries, and citation contexts.
4. Read `references/evidence_protocol.md` before important classification or source tracing.
5. Classify citations with the allowed intent labels.
6. Extract key target-paper claims or contributions when supported by text.
7. Build `source_traces[]` by linking claims to local citation contexts, cited-source roles, and evidence steps.
8. Extract entities and relations that explain the target paper.
9. If AMiner is enabled, enrich metadata without replacing local evidence.
10. Write `json/graph/citation_graph.json` before visual artifacts.
11. Write `analysis.md`; use `references/analysis_template.md` only for explicit template or fixed-format requests.
12. Generate SVG and `citation_map.html` according to the confirmed mode and `references/visual.md`.
13. Validate artifacts before the final reply.

### Reference Files

- `references/schema.md`: canonical schema and JSON example.
- `references/evidence_protocol.md`: evidence and uncertainty rules.
- `references/prompts.md`: English and Chinese extraction/review prompts.
- `references/visual.md`: SVG and HTML graph rules.
- `references/analysis_template.md`: fixed report templates for explicit template mode.

### Quality Checks

- Every citation has `intent`, `evidence`, `confidence`, and either `reference_id` or `unmatched_reference: true`.
- Every intent label is in the allowed list.
- Key citations trace back to a citation sentence or local context.
- Every entity is supported by at least one citation.
- Every source trace is grounded in at least one local citation context; AMiner metadata cannot be the sole support.
- `json/graph/citation_graph.json` remains complete even if Markdown, SVG, or HTML has caveats.

## 中文工作流

### 标准产物

在证据和文件系统权限允许时，生成以下产物：

- `analysis.md`：面向人阅读的中文分析报告。
- `json/graph/citation_graph.json`：遵循 `references/schema.md` 的规范机器可读图谱。
- `citation_map.svg`：可生成时输出静态引用图谱。
- `citation_map.html`：有图谱数据时输出单文件交互图谱。
- `citation_map_example.svg`：仅在 visual mode 为 `all` 时输出。
- `citation_map_spec.md`：仅在 SVG 生成存在限制或失败时输出。

默认输出目录：

```text
outputs/paper-source-trace/<safe-paper-stem>/
```

推荐目录结构：

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

### 启动确认

在读取论文、抽取引用、检查 `AMINER_API_KEY`、调用 AMiner 或生成 SVG 之前，必须先请用户确认：

- SVG 模式：`current`、`example`、`all` 或 `hybrid`。
- AMiner 增强：`on` 或 `off`。

如果用户已经给出其中一个或两个设置，先复述为暂定选择，再请求最终确认。用户回答前不要继续执行。

### 核心规则

1. 只使用用户提供的论文文本、引用上下文、参考文献、用户笔记，或用户明确要求的 AMiner 结果作为证据。
2. 不凭领域记忆推断 citation intent。
3. AMiner 增强必须显式开启；未请求时不检查 `AMINER_API_KEY`。
4. AMiner 只能补充 paper ID、URL、候选参考文献匹配和外部引用关系，不能替代本地 citation context，也不能单独证明 intent 或 source trace。
5. 保留不确定性；当引用上下文、参考文献匹配或来源角色证据不完整时降低置信度。
6. 如果可以写入文件，不要只给聊天摘要。

### AMiner 增强

默认 `aminer: off`。只有出现 `aminer:on` 或明确措辞时才开启，例如 `AMiner 增强`、`用 AMiner 补全`、`查 AMiner 引用链`、`补全 paper_id`、`enhance with AMiner`、`use AMiner metadata`。

开启后：

1. 只检查 `AMINER_API_KEY` 是否存在，绝不打印 token。
2. 如果缺少 token，继续本地分析，并记录 AMiner 增强已跳过。
3. 使用最短可行链路：`paper_search` 或 `paper_search_pro`、`paper_detail`、`paper_relation`、`paper_info`。
4. 对所有计划或完成的 AMiner 调用输出成本摘要。
5. 预估成本达到或超过 `¥5` 时，先请求用户明确确认。
6. 在 `json/graph/citation_graph.json` 的 `metadata.aminer_enrichment` 中记录增强元数据。

### Intent Labels

除非用户明确扩展分类体系，只使用以下 12 类标签：

`background`, `problem`, `core-method`, `supporting-method`, `dataset`, `metric`, `baseline`, `tool-resource`, `theory`, `result-evidence`, `limitation`, `future-work`。

### 执行步骤

1. 先询问启动确认问题，并等待用户回答。
2. 确认输入证据和输出目录。
3. 抽取可靠的论文文本、参考文献条目和 citation contexts。
4. 重要分类或来源追踪前，读取 `references/evidence_protocol.md`。
5. 使用允许的 intent labels 分类每条引用。
6. 在文本支持时抽取目标论文的关键 claims 或 contributions。
7. 构建 `source_traces[]`，把目标 claim 连接到本地 citation contexts、被引文献角色和证据步骤。
8. 抽取解释目标论文的 entities 和 relations。
9. 如果启用 AMiner，只补充元数据，不替代本地证据。
10. 先写入 `json/graph/citation_graph.json`，再生成可视化产物。
11. 写入 `analysis.md`；只有用户明确要求模板或固定格式时才使用 `references/analysis_template.md`。
12. 按确认的模式和 `references/visual.md` 生成 SVG 和 `citation_map.html`。
13. 最终回复前验证产物。

### Reference Files

- `references/schema.md`：规范 schema 和 JSON 示例。
- `references/evidence_protocol.md`：证据链和不确定性规则。
- `references/prompts.md`：中英文抽取与审查 prompts。
- `references/visual.md`：SVG 和 HTML 图谱规则。
- `references/analysis_template.md`：显式模板模式下使用的固定报告模板。

### 质量检查

- 每条 citation 都有 `intent`、`evidence`、`confidence`，并且有 `reference_id` 或 `unmatched_reference: true`。
- 每个 intent label 都属于允许的 12 类。
- 关键引用能追溯到 citation sentence 或本地上下文。
- 每个 entity 至少由一条 citation 支撑。
- 每条 source trace 至少由一个本地 citation context 支撑；AMiner 元数据不能作为唯一支撑。
- 即使 Markdown、SVG 或 HTML 有限制，`json/graph/citation_graph.json` 仍必须完整。
