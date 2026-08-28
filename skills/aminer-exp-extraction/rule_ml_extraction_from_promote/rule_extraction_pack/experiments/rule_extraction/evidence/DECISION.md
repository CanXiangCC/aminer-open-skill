# Evidence 字段 — 实验最优方案记录

**日期**: 2026-07-07  
**状态**: 实验阶段拍板（**未接入** `merger.py` / orchestrator）  
**结论**: 规则提取实验 **最优策略为 v4**；生产主管线仍由 LLM 输出 `evidence`（`merger.py` → `LLM_FIELDS`）。

---

## 决策

| 项 | 内容 |
|----|------|
| 字段 | `evidence: string[]`（per-experiment，原文 md 子串） |
| **实验最优策略** | **`evidence--策略v4--clean_mswr_rerank_dynamic`** |
| 实现 | `strategies/v4_clean_mswr.py` + `shared/sentence_clean.py`（wf8 **R1–R4**） |
| 选句内核 | v3 MSWR：Jaccard cheap top-20 → Jaccard rerank → dynamic k → query 配额 → fill pass |
| 成功标准 | **Product track**（非 Gold recall）：`noise_rate`≤15%、`relevance_mean`≥20%、`traceable_rate`≥95% |
| 参考 run | `runs/20260707_evidence_v4_dev10/` |

## dev_10 最优 run 指标（v4）

| 指标 | 值 |
|------|-----|
| product_pass | **YES** |
| noise_rate | **4.92%** |
| relevance_mean | **40.98%** |
| traceable_rate | **100%** |
| semantic_recall@5（回归） | 19.40% |

## 理由（相对 v1 / v2 / v3 / v4.1）

1. **Product 全面优于 v1/v3**：v4 noise 4.92% vs v3 9.84%；二者 Gold recall 同为 19.4%，v4 噪声更低。
2. **v2 不采纳**：hard filter + 洗句叠加，dev_10 recall 16.4%，低于 v1/v3/v4。
3. **v4.1 不采纳为默认**：R5 + 扩展 R4（LaTeX/bib）候选池删句过激，noise/relevance/recall 均差于 v4（run `20260707_evidence_v4_1_dev10`）。
4. **与 metrics 不同**：evidence 适合「洗句 + 字段回溯 MSWR」；Gold ~40% 非 verbatim，故 **不以 Gold recall gate pass**。
5. **hybrid 假设**：输入为 LLM/Gold 的 `key_results` + `method`；输出必须 raw md verbatim。

## 未采纳 / 存档

| 策略 | run / 说明 |
|------|------------|
| v1 | `20260706_evidence_v1_dev10` — MSWR 基线，noise ~10% |
| v2 | `20260706_evidence_v2_dev10` — 低于 v1 |
| v3 | `20260707_evidence_v3_compare` — 与 v4 同 recall，noise 更高 |
| v4.1 洗句补丁 | `20260707_evidence_v4_1_dev10` — 未超过 v4 |

## 生产路径（当前未变）

- Prompt：`src/llm/*_baseline.txt`
- Merger：`src/rule_extraction/merger.py` → `evidence` ∈ `LLM_FIELDS`
- 集成 v4 规则：见 [ROADMAP.md](ROADMAP.md) M3（待 dev_20 + 人工 spot-check）

## 运行最优策略

```bash
python -m experiments.rule_extraction.evidence.test_runner \
  --strategy v4 \
  --batch dev_10 \
  --run-id 20260707_evidence_v4_dev10
```
