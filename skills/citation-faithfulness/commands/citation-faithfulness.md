---
description: Check whether a paper PDF's in-text citations are faithful to the cited sources (retrieve sources from the web and judge each claim)
argument-hint: [pdf: <pdf-path> scope: all|specific-only|refs:1,12,23 max-refs: <N> output: <json-path> | 自然语言]
allowed-tools: Read, WebSearch, WebFetch, Write, Glob
---

# /citation-faithfulness — Citation Faithfulness Checker

User invoked the Citation Faithfulness skill with:

```text
$ARGUMENTS
```

## Language Routing / 语言路由

- If `$ARGUMENTS` or the conversation is mainly Chinese, follow **中文命令流程** and read `${CLAUDE_PLUGIN_ROOT}/SKILL.zh.md` + `${CLAUDE_PLUGIN_ROOT}/references/rubric.md` + `${CLAUDE_PLUGIN_ROOT}/references/output-schema.md`.
- Otherwise follow **English Command Flow** and read `${CLAUDE_PLUGIN_ROOT}/SKILL.md` + `${CLAUDE_PLUGIN_ROOT}/references/rubric.md` + `${CLAUDE_PLUGIN_ROOT}/references/output-schema.md`.
- Parameter names stay English: `pdf`, `scope`, `max-refs`, `output`.
- Verdict labels (`SUPPORTED` / `PARTIALLY_SUPPORTED` / `NOT_SUPPORTED` / `NOT_IN_SOURCE` / `UNVERIFIABLE`), `retrieval_level`, and JSON keys stay English.

## English Command Flow

### 1. Pre-flight

**Any failed check stops the flow.**

1. Confirm the user gave an existing local `.pdf` path. If not, ask for one. **Never invent or download a paper to check.**
2. Confirm `Read`, `WebSearch`, and `WebFetch` are usable. If there is no web access, warn the user that without retrieving sources every verdict will be `UNVERIFIABLE`, and ask whether to proceed.
3. This is the wrong skill if the user wants to know whether a reference *exists* / is hallucinated — route them to `/pdf-citation-verifier` instead.
4. `AMINER_API_KEY` is optional (enrichment only); do not require it and never echo its value.

### 2. Parse `$ARGUMENTS`

| Field | Values | Default | Meaning |
| --- | --- | --- | --- |
| `pdf` | absolute PDF path | required | Paper to check |
| `scope` | `all` / `specific-only` / `refs:1,12,23` | `all` | Which citations to check |
| `max-refs` | integer | none | Cap unique sources retrieved (cost guard) |
| `output` | path | – | Also write the full JSON report here |

If `pdf` is missing or the path does not exist, stop and ask. If `scope: all` on a reference-heavy paper, warn about cost (~1 web retrieval per unique source) and offer `specific-only` or `max-refs` before starting.

### 3. Run

There is no script — execute the five-stage procedure in `SKILL.md` with your own tools:

1. **S0** — `Read` the PDF (page ranges for long papers); capture body + reference list.
2. **S1** — extract `{claim_id, claim_text, citation_sentence, section, cited_refs[], claim_type}` for every in-text citation in scope.
3. **S2** — map each marker to its reference entry (title/authors/year/DOI/arXiv id); **deduplicate by cited work**.
4. **S3** — retrieve each unique source via WebFetch/WebSearch (arXiv abstract/full text → open landing page → optional AMiner); record `retrieval_level`.
5. **S4** — judge each claim–source pair with `references/rubric.md`; obey the iron rules (abstract-only body claims → `UNVERIFIABLE`; never fabricate evidence).

Honor `max-refs` and `scope`. List, don't silently drop, anything skipped.

### 4. Present the Result

Follow the Output Presentation section of `SKILL.md`:

- Summary: title, total in-text citations, unique sources checked, verdict counts, retrieval coverage (`full_text` / `abstract_only` / `not_found`), and an honesty note if coverage was shallow.
- Per-claim table for every non-`SUPPORTED` item: `claim_id` · section · claim · cited work · verdict · `retrieval_level` · `confidence` · evidence quote · reason.
- List `NOT_SUPPORTED` / `NOT_IN_SOURCE` findings in full first (these are actionable), framed as flags for human review, not final accusations.
- If `output` was given, write the complete JSON and report the path.

## 中文命令流程

### 1. Pre-flight

**任何一项失败立即停止。**

1. 确认用户给了存在的本地 `.pdf` 路径；没有就追问。**绝不自行编造或下载论文来核查。**
2. 确认 `Read`、`WebSearch`、`WebFetch` 可用。若无联网，提醒用户：取不到原文时所有判定只能是 `UNVERIFIABLE`，询问是否仍要继续。
3. 若用户想知道引用是否*真实存在*/是否幻觉，这是错的 skill——改路由到 `/pdf-citation-verifier`。
4. `AMINER_API_KEY` 可选（仅增强），不要作硬性要求，禁止回显其值。

### 2. 解析 `$ARGUMENTS`

| 字段 | 取值 | 默认 | 含义 |
| --- | --- | --- | --- |
| `pdf` | PDF 绝对路径 | 必填 | 要核查的论文 |
| `scope` | `all` / `specific-only` / `refs:1,12,23` | `all` | 核查哪些引用 |
| `max-refs` | 整数 | 无 | 检索的去重原文数上限（成本护栏） |
| `output` | 路径 | – | 同时把完整 JSON 报告写到此处 |

`pdf` 缺失或路径不存在就停下追问。若对参考很多的论文用 `scope: all`，先提醒成本（每篇去重原文约 1 次联网检索）并提供 `specific-only` 或 `max-refs`，再开始。

### 3. 运行

没有脚本——用你自己的工具执行 `SKILL.zh.md` 的五阶段流程：

1. **S0** — 用 `Read` 读 PDF（长论文按页范围）；拿到正文 + 参考文献表。
2. **S1** — 对范围内每处正文引用抽出 `{claim_id, claim_text, citation_sentence, section, cited_refs[], claim_type}`。
3. **S2** — 把每个标记映射到参考文献条目（标题/作者/年份/DOI/arXiv id）；**按被引工作去重**。
4. **S3** — 用 WebFetch/WebSearch 取每篇去重原文（arXiv 摘要/全文 → 开放落地页 → 可选 AMiner）；记录 `retrieval_level`。
5. **S4** — 用 `references/rubric.md` 判定每个「声称—原文」对；遵守铁律（仅摘要的正文级声称 → `UNVERIFIABLE`；绝不编造证据）。

遵守 `max-refs` 与 `scope`。跳过的项要列出，不许静默丢弃。

### 4. 展示结果

按 `SKILL.zh.md` 的"结果展示"节：

- 汇总：标题、正文引用总数、核查的去重原文数、各档计数、检索覆盖（`full_text` / `abstract_only` / `not_found`），覆盖较浅时加一句诚实说明。
- 逐条表覆盖每个非 `SUPPORTED` 项：`claim_id` · 章节 · 声称 · 被引工作 · 判定 · `retrieval_level` · `confidence` · 证据引句 · 理由。
- 先完整列出 `NOT_SUPPORTED` / `NOT_IN_SOURCE` 发现（可行动项），并说明这是待人工复核的标记、非最终指控。
- 若给了 `output`，写出完整 JSON 并告知路径。
