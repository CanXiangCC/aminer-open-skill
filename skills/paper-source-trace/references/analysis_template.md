# Fixed `analysis.md` Templates / 固定 `analysis.md` 模板

Use this file only when the user explicitly requests a template, compliance format, standard format, or fixed structure.

只有用户明确要求模板、规范格式、标准格式或固定结构时，才使用本文件。

## Language Routing / 语言路由

- Use the English template when the user writes in English or does not request Chinese output.
- Use the Chinese template when the user mainly writes in Chinese or explicitly asks for Chinese output.
- Keep JSON field names, intent labels, relation types, and source roles in English.
- 用户主要使用中文或明确要求中文输出时，使用中文模板。
- 其他情况使用英文模板。
- JSON 字段名、intent label、relation type 和 source role 始终保持英文。

Do not invent citations to fill a section. If no reliable evidence supports an intent or row, write `No reliable evidence found` or `未发现可靠证据`, matching the output language.

不要为了填满模板而编造引用。如果某一项没有可靠证据，按输出语言写 `No reliable evidence found` 或 `未发现可靠证据`。

## English Template

```markdown
# Citation Intent Analysis: <paper_title>

## 1. Overall Conclusion

- Target paper:
- Citation structure judgment:
- Citation chains worth reading first:
- Main uncertainty:

## 2. Target Paper Core Content

| Item | Content |
| --- | --- |
| Research problem |  |
| Core method |  |
| Data / benchmark |  |
| Main result |  |
| Limitation |  |

## 3. Citation Intent Overview

| Intent label | Count | Representative references | Role in understanding the paper |
| --- | ---: | --- | --- |

## 4. Intent-Grouped Citation Analysis

### 4.x `<intent>`: <display label>

| Item | Content |
| --- | --- |
| Judgment basis |  |
| Key citations |  |
| Evidence anchors |  |
| Role in the paper's argument |  |
| Uncertainty |  |

Repeat only for intents with reliable evidence. Summarize absent expected intents briefly instead of fabricating citations.

## 5. Core Method Citation Chain

| Method component | Supporting reference | Borrowed idea | Role in this paper | Evidence and uncertainty |
| --- | --- | --- | --- | --- |

## 6. Claim-to-Source Trace

| Target claim | Claim type | Source role | Supporting citation / reference | Evidence anchor | Confidence and uncertainty |
| --- | --- | --- | --- | --- | --- |

For key claims with reliable evidence, explain the reading path from target-paper claim to cited source. If a claim has no citation-backed trace, write `No reliable source trace found`.

## 7. Dataset, Metric, and Baseline Citations

| Evaluation target | Dataset / metric / baseline | Supporting reference | Role in result interpretation | Evidence and uncertainty |
| --- | --- | --- | --- | --- |

## 8. Entity and Relation Graph Interpretation

- Main entities:
- Main relations:
- Recommended reading path through `citation_map.html` or `citation_map.svg`:
- AMiner enrichment impact, if any:

## 9. Coverage, Noise, and Uncertainty

- Coverage:
- Missing or noisy evidence:
- Reference matching caveats:
- Source trace coverage:
- AMiner enrichment caveats:
- SVG generation status:

## 10. Output File Checklist

| File | Status | Notes |
| --- | --- | --- |
| `analysis.md` | Generated | Report in the requested language |
| `json/graph/citation_graph.json` | Generated | Must parse as JSON; includes `source_traces[]` when trace evidence exists |
| `citation_map.svg` | Generated / not generated | Static citation map |
| `citation_map.html` | Generated / not generated | Single-file interactive graph |
| `citation_map_chain.svg` | Generated / not used | Only for `svg: both` |
| `citation_map_spec.md` | Optional / not used | Fallback if SVG generation fails |
```

## 中文模板

```markdown
# 引用意图与论文来源追踪分析：<paper_title>

## 1. 总体结论

- 目标论文：
- 引用结构判断：
- 最值得优先阅读的引用链：
- 主要不确定性：

## 2. 目标论文核心内容

| 项目 | 内容 |
| --- | --- |
| 研究问题 |  |
| 核心方法 |  |
| 数据 / 基准 |  |
| 主要结果 |  |
| 局限性 |  |

## 3. 引用意图概览

| Intent label | 数量 | 代表性参考文献 | 对理解论文的作用 |
| --- | ---: | --- | --- |

## 4. 按意图分组的引用分析

### 4.x `<intent>`：<中文显示标签>

| 项目 | 内容 |
| --- | --- |
| 判断依据 |  |
| 关键引用 |  |
| 证据锚点 |  |
| 在论文论证中的作用 |  |
| 不确定性 |  |

只对有可靠证据的 intent 分组展开。对缺失但预期存在的意图，简要说明证据不足，不要编造引用。

## 5. 核心方法引用链

| 方法组件 | 支撑参考文献 | 借鉴内容 | 在本文中的作用 | 证据与不确定性 |
| --- | --- | --- | --- | --- |

## 6. Claim-to-Source Trace

| 目标 claim | Claim type | Source role | 支撑 citation / reference | 证据锚点 | 置信度与不确定性 |
| --- | --- | --- | --- | --- | --- |

对有可靠证据的关键 claim，说明从目标论文 claim 到被引来源的阅读路径。若某个 claim 没有 citation-backed trace，写 `未发现可靠溯源证据`。

## 7. Dataset、Metric 与 Baseline 引用

| 评估对象 | Dataset / metric / baseline | 支撑参考文献 | 对结果解释的作用 | 证据与不确定性 |
| --- | --- | --- | --- | --- |

## 8. 实体与关系图谱解读

- 主要实体：
- 主要关系：
- 建议通过 `citation_map.html` 或 `citation_map.svg` 阅读的路径：
- AMiner 增强影响，如有：

## 9. 覆盖范围、噪声与不确定性

- 覆盖范围：
- 缺失或噪声证据：
- 参考文献匹配风险：
- Source trace 覆盖情况：
- AMiner 增强限制：
- SVG 生成状态：

## 10. 输出文件检查表

| 文件 | 状态 | 说明 |
| --- | --- | --- |
| `analysis.md` | 已生成 | 使用请求语言撰写的报告 |
| `json/graph/citation_graph.json` | 已生成 | 必须可解析为 JSON；有 trace 证据时包含 `source_traces[]` |
| `citation_map.svg` | 已生成 / 未生成 | 静态引用图谱 |
| `citation_map.html` | 已生成 / 未生成 | 单文件交互图谱 |
| `citation_map_chain.svg` | 已生成 / 未使用 | 仅用于 `svg: both` |
| `citation_map_spec.md` | 可选 / 未使用 | SVG 生成失败时的降级说明 |
```

## Quality Rules / 质量规则

- Keep the section order in the selected language.
- Preserve all records in `json/graph/citation_graph.json`; the Markdown report may summarize dense groups.
- Each intent group must explain how the group supports the target paper's problem, method, experiment, or limitation.
- Each source trace must connect a target-paper claim to local citation evidence and a cited-source role.
- AMiner-enriched metadata must be labeled as metadata, not as local citation evidence.
- 按所选语言保持章节顺序。
- `json/graph/citation_graph.json` 必须保留完整记录，Markdown 报告可以概括密集分组。
- 每个 intent 分组都要说明其如何支撑目标论文的问题、方法、实验或局限。
- 每条 source trace 必须把目标论文 claim 连接到本地引用证据和被引来源角色。
- AMiner 增强元数据必须标注为 metadata，不能写成本地 citation evidence。
