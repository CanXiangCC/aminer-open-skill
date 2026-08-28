# Evidence Field Rule Extraction

Per-experiment **verbatim evidence sentences** (md substrings) via **MSWR** (Multi-query Sentence Weighted Retrieval).

## 最优策略（2026-07-07）

| 项 | 值 |
|----|-----|
| **策略 ID** | `evidence--策略v4--clean_mswr_rerank_dynamic` |
| **文件** | `strategies/v4_clean_mswr.py` |
| **洗句** | `shared/sentence_clean.py` — wf8 **R1–R4**（v4 baseline run） |
| **选句** | v3 MSWR：Jaccard rerank + dynamic k + query 配额 |
| **参考 run** | `runs/20260707_evidence_v4_dev10/` |

详见 [DECISION.md](DECISION.md)。**v4.1 洗句补丁（R5 + 扩展 R4）未采纳为默认**（指标低于 v4）。

### dev_10 最优指标（Product）

| Gate | 值 | 阈值 |
|------|-----|------|
| product_pass | **YES** | 三 gate 全过 |
| noise_rate | **4.92%** | ≤ 15% |
| relevance_mean | **40.98%** | ≥ 20% |
| traceable_rate | **100%** | ≥ 95% |
| semantic_recall@5 | 19.40% | 回归 only |

## Success Criteria (Product)

Engineering pass/fail uses **product track**, not gold recall:

| Gate | Metric | Threshold |
|------|--------|-----------|
| 低噪声 | `noise_rate` | ≤ 15% |
| 高相关 | `relevance_mean` | ≥ 20% |
| 可溯源 | `traceable_rate` | ≥ 95% |
| 人工可接受 | `human_acceptable` | manual spot-check |

Gold `semantic_recall@5` remains in reports for regression only.

## Strategies

| ID | File | Description | 状态 |
|----|------|-------------|------|
| v1 | `strategies/v1_field_backtrace_mswr.py` | Full-corpus argmax, fixed k=5 | 基线 |
| v2 | `strategies/v2_field_backtrace_mswr.py` | Hard filter + rerank + dynamic k | 存档，不采纳 |
| v3 | `strategies/v3_field_backtrace_mswr.py` | v1 + rerank + dynamic k + fill pass | 被 v4 包含 |
| **v4** | `strategies/v4_clean_mswr.py` | **v3 + wf8 R1–R4 洗句** | **✅ 实验最优** |

## Run

```bash
cd d:\Zhipu_Intern\experiment_points_extraction

# 最优策略 v4（推荐）
python -m experiments.rule_extraction.evidence.test_runner \
  --strategy v4 \
  --batch dev_10 \
  --run-id 20260707_evidence_v4_dev10

# 与 v1 对比 delta
python -m experiments.rule_extraction.evidence.test_runner \
  --strategy v4 --batch dev_10 --compare-v1

# 历史基线
python -m experiments.rule_extraction.evidence.test_runner \
  --strategy v1 --batch dev_10 --run-id 20260706_evidence_v1_dev10
```

Outputs under `runs/{run_id}/`: manifest, steps, results, traces, analysis.

## Evaluation metrics

**Product (gates pass):** `noise_rate`, `relevance_mean`, `traceable_rate`, `human_acceptable`

**Benchmark (regression):** dual-track gold recall, buckets, normalized recall, `delta_vs_v1`

## Tests

```bash
pytest tests/experiments/test_evidence_v1_mswr.py \
  tests/experiments/test_evidence_v3_mswr.py \
  tests/experiments/test_evidence_v4_mswr.py \
  tests/experiments/test_evidence_sentence_clean.py \
  tests/experiments/test_evidence_product_metrics.py -q
```

See [DESIGN.md](DESIGN.md) for algorithm details.
