# Evidence Protocol / 证据协议

Use this protocol before writing `analysis.md` and before finalizing `json/graph/citation_graph.json`.

在写入 `analysis.md` 和最终确定 `json/graph/citation_graph.json` 前，使用本协议。

## Language Routing / 语言路由

- Use the English rules when the user writes in English or does not request Chinese output.
- Use the Chinese rules when the user mainly writes in Chinese or explicitly asks for Chinese output.
- Keep JSON keys, intent labels, relation types, source roles, and IDs in English.
- 用户主要使用中文或明确要求中文输出时，使用中文规则。
- 其他情况使用英文规则。
- JSON key、intent label、relation type、source role 和 ID 保持英文。

## English Rules

### Evidence Sources

Use only:

- supplied PDF text;
- extracted paper text;
- citation contexts;
- reference entries;
- user-provided notes;
- explicitly requested AMiner metadata or citation relationships.

Do not fill gaps with domain memory, plausible bibliography guesses, or AMiner-only citation links.

### Evidence Anchors

For each important citation, capture as many anchors as possible:

| Anchor | Meaning |
| --- | --- |
| `citation_context` | Local sentence or short paragraph where the citation appears |
| `section` | Target paper section or nearby heading |
| `target_claim` | Target-paper claim, method choice, dataset choice, or result interpretation supported by the citation |
| `cited_work_role` | Role of the cited work, such as problem origin, method component, dataset source, baseline, tool, theory, result evidence, or limitation |
| `intent_rationale` | Why this citation belongs to its selected intent label instead of a nearby label |
| `confidence_reason` | Why confidence is high, medium, or low |

### Claim-Centered Source Tracing

Use source tracing to answer: which cited sources support, motivate, supply, contrast, or limit a target-paper claim?

For each important claim or contribution:

1. Identify the claim from the target paper text, not outside memory.
2. Link the claim to one or more local citation contexts.
3. Assign each cited source a `source_role`, such as `foundation`, `method-origin`, `method-adaptation`, `dataset-source`, `metric-source`, `baseline-comparison`, `evidence-support`, `contrast`, `limitation-source`, or `future-direction`.
4. Explain how the cited source supports the claim using visible evidence.
5. Record uncertainty when the claim is clear but the citation context is weak, noisy, or indirect.

Build `source_traces[]` only when at least one local citation context supports the trace. AMiner metadata can enrich IDs, URLs, and candidate matches, but cannot by itself prove a claim-to-source relationship.

### Citation Context Rules

- Prefer citation sentences and adjacent context over abstract-level summaries.
- Preserve `citation_sentence` and `context` in the target paper's original language. Do not translate, paraphrase, or localize them.
- Use the output language only for explanation fields such as `evidence`, `intent_rationale`, `confidence_reason`, `summary`, and `notes`.
- If a citation appears only in a table, figure caption, or noisy PDF extraction, mark the noise in `notes`.
- If the cited title or reference entry cannot be matched reliably, use `unmatched_reference: true`.
- Do not copy long source passages into `analysis.md`; summarize evidence and keep short anchors.
- AMiner metadata can improve reference matching but cannot create local citation evidence.

### Confidence Policy

| Level | Range | Use when |
| --- | ---: | --- |
| high | `0.80-1.00` | Citation sentence, reference match, and target claim are all clear |
| medium | `0.55-0.79` | Intent is likely but section context, reference match, or cited-work role is incomplete |
| low | `0.10-0.54` | Evidence is noisy, table-derived, ambiguous, or weakly connected |

Do not use high confidence when only the reference title or AMiner metadata is known but the local citation context is missing.

### No-Evidence Handling

If an expected intent, method chain, dataset link, or baseline link has no reliable evidence, write `No reliable evidence found`.

If a target-paper claim has no reliable citation-backed source trace, write `No reliable source trace found`.

When generating `analysis.md`, explicitly distinguish evidence-backed conclusions, plausible but uncertain interpretations, missing/noisy evidence, AMiner metadata enrichment, and claim-to-source traces supported by local citation contexts.

## 中文规则

### 证据来源

只能使用：

- 用户提供的 PDF 文本；
- 抽取后的论文文本；
- citation contexts；
- reference entries；
- 用户提供的笔记；
- 用户明确要求的 AMiner 元数据或引用关系。

不要用领域记忆、看似合理的参考文献猜测，或仅来自 AMiner 的引用链接来补证据缺口。

### 证据锚点

对每条重要 citation，尽量记录以下锚点：

| 锚点 | 含义 |
| --- | --- |
| `citation_context` | citation 出现处的本地句子或短段落 |
| `section` | 目标论文中的章节或附近标题 |
| `target_claim` | 该 citation 支撑的目标论文 claim、方法选择、数据集选择或结果解释 |
| `cited_work_role` | 被引工作的角色，例如问题来源、方法组件、数据集来源、baseline、tool、theory、result evidence 或 limitation |
| `intent_rationale` | 为什么该 citation 属于所选 intent label，而不是相近标签 |
| `confidence_reason` | 为什么置信度是 high、medium 或 low |

### 以 Claim 为中心的来源追踪

Source tracing 回答的问题是：哪些被引来源支撑、启发、提供、对比或限制了目标论文中的某个 claim？

对每个重要 claim 或 contribution：

1. 从目标论文文本中识别 claim，不从外部记忆中补充。
2. 将 claim 连接到一个或多个本地 citation contexts。
3. 给每个被引来源分配 `source_role`，例如 `foundation`、`method-origin`、`method-adaptation`、`dataset-source`、`metric-source`、`baseline-comparison`、`evidence-support`、`contrast`、`limitation-source` 或 `future-direction`。
4. 用可见证据解释该被引来源如何支撑 claim。
5. 如果 claim 清楚但 citation context 弱、噪声大或关系间接，记录不确定性。

只有至少一个本地 citation context 支撑 trace 时，才构建 `source_traces[]`。AMiner 元数据可以补充 ID、URL 和候选匹配，但不能单独证明 claim-to-source 关系。

### Citation Context 规则

- 优先使用 citation sentence 和邻近上下文，而不是摘要级概括。
- `citation_sentence` 和 `context` 必须保留目标论文原文语言，不要翻译、意译或按用户语言改写。
- 只有 `evidence`、`intent_rationale`、`confidence_reason`、`summary` 和 `notes` 等解释性字段跟随输出语言。
- 如果 citation 只出现在表格、图注或噪声 PDF 抽取结果中，在 `notes` 中说明噪声。
- 如果被引标题或参考文献条目无法可靠匹配，使用 `unmatched_reference: true`。
- 不要在 `analysis.md` 中复制长段原文；应概括证据并保留短锚点。
- AMiner 元数据可以改善 reference matching，但不能创造本地 citation evidence。

### 置信度策略

| 等级 | 范围 | 使用条件 |
| --- | ---: | --- |
| high | `0.80-1.00` | citation sentence、reference match 和 target claim 都清楚 |
| medium | `0.55-0.79` | intent 较可能成立，但章节上下文、reference match 或 cited-work role 不完整 |
| low | `0.10-0.54` | 证据有噪声、来自表格、语义模糊或连接较弱 |

如果只有参考文献标题或 AMiner 元数据，而缺少本地 citation context，不要给 high confidence。

### 无证据处理

如果预期的 intent、方法链、数据集链接或 baseline 链接没有可靠证据，写 `未发现可靠证据`。

如果某个目标论文 claim 没有 citation-backed source trace，写 `未发现可靠溯源证据`。

生成 `analysis.md` 时，明确区分：有证据支撑的结论、合理但不确定的解释、缺失或噪声证据、不能证明 intent 的 AMiner 元数据增强，以及由本地 citation context 支撑的 claim-to-source traces。

## Shared JSON Note / 共享 JSON 说明

When generating `json/graph/citation_graph.json`, preserve uncertainty in `notes`, `intent_rationale`, `confidence_reason`, or `source_traces[].notes`.

生成 `json/graph/citation_graph.json` 时，在 `notes`、`intent_rationale`、`confidence_reason` 或 `source_traces[].notes` 中保留不确定性。
