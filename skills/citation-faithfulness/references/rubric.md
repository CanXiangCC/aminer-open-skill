# Faithfulness Judging Rubric / 忠实性判定 Rubric

Adapted from `paper-source-trace/references/evidence_protocol.md`. Use this at stage **S4** to assign one verdict per claim–source pair.

改编自 `paper-source-trace/references/evidence_protocol.md`。在 **S4** 阶段用它给每个「声称—原文」对一个判定。

---

## Language Routing / 语言路由

- Keep verdict labels, `retrieval_level`, `confidence` levels, and JSON keys in English.
- Keep `evidence` (the quote from the source) in the **source's original language** — do not translate it.
- Write `reason` in the user's language.
- 判定标签、`retrieval_level`、`confidence` 等级、JSON key 保持英文。
- `evidence`（原文引句）保留**原文语言**，不要翻译。`reason` 用用户语言写。

## Evidence discipline / 证据纪律

Use only what you actually retrieved: the claim text from the PDF, and the source content you fetched (arXiv page, landing page, abstract, or full text). **Do not fill gaps with domain memory or plausible guesses about what the source "probably" says.** If you did not read it, you did not verify it.

只用你真正取到的东西：PDF 里的声称文本，以及你 fetch 到的原文内容（arXiv 页、落地页、摘要或全文）。**不要用领域记忆或"原文大概会这么说"的合理猜测来补缺口。** 没读到就是没核实。

## Verdict decision tree / 判定决策树

Ask these in order; the first match wins.

按顺序问，第一个命中即判定。

1. **Did you retrieve any usable source content?** No (`retrieval_level: not_found`, or only a title/metadata) → **`UNVERIFIABLE`**. Stop.
   **取到可用原文内容了吗？** 没有（`not_found`，或只有标题/元数据）→ **`UNVERIFIABLE`**。停。

2. **Does the claim target a body-level detail (a specific number, table value, figure, or buried result) while you only have `abstract_only`?** Yes → **`UNVERIFIABLE`** (the abstract cannot clear or convict it). Stop.
   **声称指向正文级细节（具体数字、表值、图、藏在正文里的结果），而你只有 `abstract_only`？** 是 → **`UNVERIFIABLE`**（摘要既不能证实也不能证伪）。停。

3. **Does the retrieved source explicitly state what the paper attributes to it?** Yes, fully → **`SUPPORTED`**. Quote the sentence as `evidence`.
   **取到的原文明确说了论文归因给它的内容？** 是，完整 → **`SUPPORTED`**。把该句作为 `evidence` 引出。

4. **Does the source support the gist but the paper overstates / narrows / adds unstated qualifiers / mismatches a secondary detail?** → **`PARTIALLY_SUPPORTED`**. Quote what the source actually says and name the gap.
   **原文支持大意，但论文夸大/缩小/加了原文没有的限定/次要细节对不上？** → **`PARTIALLY_SUPPORTED`**。引出原文实际说法并指明差距。

5. **Does the source address the same topic but state something different or opposite?** → **`NOT_SUPPORTED`**. This is a real misrepresentation — you MUST be able to quote the contradicting sentence.
   **原文谈了同一话题但说的是不同/相反的东西？** → **`NOT_SUPPORTED`**。这是真曲解——你**必须**能引出矛盾的原句。

6. **You have `full_text` and the claimed fact/result is simply absent from it?** → **`NOT_IN_SOURCE`**. (Only from `full_text`; with `abstract_only` this is `UNVERIFIABLE`, see step 2.)
   **你有 `full_text`，而被声称的事实/结果在里面根本不存在？** → **`NOT_IN_SOURCE`**。（仅限 `full_text`；只有摘要时归到步骤 2 的 `UNVERIFIABLE`。）

## Iron rules / 铁律

- `NOT_IN_SOURCE` requires `full_text`. Never convict on an absence you observed only in an abstract.
- `NOT_SUPPORTED` requires a quotable contradicting statement. **Absence of confirmation ≠ contradiction.**
- Never invent an `evidence` quote. No quote → the level is `not_found` and the verdict is `UNVERIFIABLE`.
- A bare "see [X]" / background pointer with no attributed content is not a checkable claim → `UNVERIFIABLE` with a note, not `SUPPORTED`.
- Mis-matched reference (`unmatched_reference: true`) → `UNVERIFIABLE`; say the marker could not be resolved.
- `NOT_IN_SOURCE` 需要 `full_text`。只在摘要里看到"没有"，绝不据此定罪。
- `NOT_SUPPORTED` 需要可引出的矛盾陈述。**缺乏佐证 ≠ 矛盾。**
- 绝不编造 `evidence` 引句。没有引句 → 层级 `not_found`、判 `UNVERIFIABLE`。
- 单纯"见 [X]"/无归因内容的背景指向不是可核查声称 → 判 `UNVERIFIABLE` 并注明，不判 `SUPPORTED`。
- 参考文献匹配错（`unmatched_reference: true`）→ `UNVERIFIABLE`；说明该标记无法解析。

## Confidence policy / 置信度策略

| Level | Range | Use when / 使用条件 |
| --- | ---: | --- |
| high | 0.80–1.00 | `full_text` retrieved, claim and source statement both unambiguous, evidence quote directly on point / 取到 `full_text`，声称与原文陈述都明确，证据引句直接对应 |
| medium | 0.55–0.79 | `abstract_only` but the abstract directly covers the claim; or `full_text` with slightly indirect phrasing / 仅摘要但摘要直接覆盖该声称；或 `full_text` 但措辞略间接 |
| low | 0.10–0.54 | noisy PDF/source extraction, weak or ambiguous match, reference match uncertain / PDF 或原文抽取有噪声、匹配弱或模糊、文献匹配不确定 |

Do not use high confidence when the verdict rests on title/metadata alone with no retrieved source text.

判定仅依赖标题/元数据、没取到原文正文时，不要给 high。

## Per-claim JSON shape / 逐条 JSON 结构

```json
{
  "claim_id": "c12",
  "section": "4.2 Results",
  "claim_text": "X reaches 92% top-1 on ImageNet",
  "citation_sentence": "<sentence from the paper, original language>",
  "cited_work": { "marker": "[12]", "title": "...", "authors": "...", "year": 2021, "doi": "...", "arxiv_id": "..." },
  "retrieval_level": "abstract_only",
  "verdict": "UNVERIFIABLE",
  "confidence": "medium",
  "evidence": "<quote from the source, original language, or empty if none>",
  "reason": "<explanation in the user's language>",
  "notes": "<noise / unmatched_reference / version mismatch, if any>"
}
```

Preserve uncertainty in `reason` / `notes`. When presenting to the user, always separate evidence-backed findings (`SUPPORTED` / `NOT_SUPPORTED` / `NOT_IN_SOURCE` with quotes) from "could-not-check" (`UNVERIFIABLE`).

在 `reason` / `notes` 中保留不确定性。向用户展示时，务必把有证据支撑的发现（带引句的 `SUPPORTED` / `NOT_SUPPORTED` / `NOT_IN_SOURCE`）与"无法核对"（`UNVERIFIABLE`）分开。
