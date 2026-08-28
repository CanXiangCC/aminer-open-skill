# Assignment v2 报告 — type-aware 分配策略（当前最优）

> **当前最优 assignment 方案** (dev_20 Gold1, fuzzy F1 = 37.45%, multi-exp F1 = 39.34%)
> 相对 v1_cooccurrence (+1.35 pp overall, +5.54 pp multi-exp)；field_study_empty_rate 100%。
> v1 仍可作为对照基线，详见 [v1_report.md](v1_report.md)。

> 策略：`v2_type_aware`（对照 `v1_cooccurrence`）
> 实现：`assignment/v2_type_aware.py` + `pairing.py` + `helpers.py`
> 评估：dev_20 (主) + dev_10 smoke

## 1. 策略说明

v2 在 v1 两阶段流水线基础上增加三项核心改进：

1. **field_study 强屏蔽**：`experiment_class == field_study` 时无条件 `datasets=[]`，
   在共现/继承/broadcast **之前**执行，修复 v1 中 blob 绕过空集的问题。
2. **ablation 三级继承**：blob 共现子集 → 继承配对主实验 `main.datasets`（已路由）→
   单主线退化 → 空集。禁止 ablation 拿 raw `paper_datasets` 全量或参与 broadcast。
3. **section 路由**：window 命中限定在 dataset mention 所在 section 内，丢弃跨 section
   ±400 字符泄漏。

### ablation 继承 main 而非 paper 并集的设计理由

主 comparison 实验经 Pass A（共现 + 主兜底）后，`main.datasets` 代表该主线**实际使用**
的 dataset 子集。Ablation 是对主线的组件消融，应继承主线的 dataset 范围，而非 paper 级
提取的全量（含噪声 dataset 名如 `sgraf`/`following`）。继承的是**已路由结果**，
不是未分配的 `paper_datasets`。

## 2. v1 vs v2 指标（dev_20 Gold1, 28 experiments）

| 维度 | v1_cooccurrence | v2_type_aware | Δ |
|------|----------------:|--------------:|---:|
| **overall fuzzy F1** | 36.10% | **37.45%** | **+1.35 pp** |
| overall fuzzy R / P | 59.52 / 25.91 | 59.52 / 27.32 | 0 / +1.41 |
| overall strict F1 | 31.05% | 32.21% | +1.16 pp |
| **multi-exp fuzzy F1** | 33.80% | **39.34%** | **+5.54 pp** |
| multi-exp fuzzy R / P | 54.55 / 24.49 | 54.55 / 30.77 | 0 / +6.28 |
| multi-exp strict F1 | 28.17% | 32.79% | +4.62 pp |
| **field_study_empty_rate** | 0% (0/2) | **100% (2/2)** | **+100 pp** |
| broadcast 触发 papers | 1 | 1 | — |
| ablation avg fuzzy recall | 33.33% (3 exps) | 33.33% (3 exps) | 0 |

Recall 与 v1 持平（上界由 v4.3 extract 决定）；增益全部来自 **Precision** 提升
（field_study 不再误分、ablation 继承 main 子集而非噪声）。

### dev_10 smoke（paper_union extract-only）

| 策略 | fuzzy F1 |
|------|----------|
| v4.3 paper-level | **56.14%**（与历史 baseline 一致，未回归） |

## 3. 关键 case 改善

### field_study 强屏蔽（L1 修复）

| paper_id | experiment | v1 pred | v2 pred |
|----------|-----------|---------|---------|
| `659e2146939a5f4082894306` | Real-World Aerial Robot | 4 datasets | **0** |
| `661ddba813fb2c6cf6b5d7e6` | TurtleBot Anomaly | 4 datasets | **0** |

`field_study_empty_rate` 从 0% → **100%**。

### ablation 继承主实验

| paper_id | experiment | v1 | v2 | 说明 |
|----------|-----------|----|----|------|
| `659e2146…` | Ablation Studies | pred=6, F1=0.50 | pred=4, **F1=0.67** | 继承 main 的 NOCS/Wild6D 子集，去掉噪声 |
| `66bac1ca…` | DisNCL Ablation | pred=2 (噪声) | pred=0 | 主实验 recall 低，继承为空；优于误分噪声 |

`66bac1ca` 3 个 ablation 仍 0 recall：主 comparison 仅命中 COCO，gold 期望
Flickr30K/CC152K — **extract 漏抽**，assign 无法补回。v2.1 方向：extract recall 改进 +
ablation 继承后按 ablation 文本筛子集。

### 未改善 case

| paper_id | 问题 | 原因 |
|----------|------|------|
| `6632f3d20…` | Pedestrian 漏 JAAD | extract 未抽到 JAAD |
| `628304515…` | GNN/CNN 互斥失败 | `other` 类无共现 → broadcast 兜底（同 v1） |
| `66bac1ca…` | ablation 0 recall | main 仅 COCO，gold 要 Flickr30K/CC152K |

## 4. 假设与限制

- **Recall 上界 = extract recall**：v2 不改变 paper 级提取，assign 无法补回漏抽 dataset。
- **ablation 继承质量依赖 main 路由质量**：main recall 低时 ablation 继承也为低/空。
- **section 路由最小版**：仅限制 window 命中范围；blob 仍全局。对 `628304515` 等
  `other` 类无文本共现论文帮助有限。
- **main 配对**：多 comparison 时用 section title + name Jaccard；极端短标题可能配对错。

## 5. v2.1 方向

1. **ML experiment_type**：`ml_classification/scripts/predict.py` 桥接，替换关键词分类。
2. **ablation 继承后筛子集**：继承 main.datasets 后，按 ablation 文本提到的组件名过滤。
3. **section 完整路由**：dataset → section → experiment 三级映射，替代 blob 全局扫描。
4. **extract 联动**：v4.x recall 改进（Flickr30K/CC152K/JAAD 漏抽）与 assign 并行推进。

## 6. 复现命令

```bash
python -m experiments.rule_extraction.datasets.test_runner \
  --strategy v4_3 --extract-strategy v4_3 --assign-strategy v2_type_aware \
  --stage both --batch dev_20 --gold-set per_experiment \
  --run-id 20260706_assign_v2_dev20 --eval-modes strict,fuzzy

pytest experiments/rule_extraction/datasets/assignment/ -q
```

## 7. 产物路径

| 产物 | 路径 |
|------|------|
| v2 结果 | `runs/20260706_assign_v2_dev20/results/assign_v2_type_aware_on_dev_20.json` |
| v1 对照 | `runs/20260706_assign_v1_dev20/results/assign_v1_cooccurrence_on_dev_20.json` |
| 对比报告 | `runs/20260706_assign_v2_dev20/analysis/comparison.md` |
| case study | `runs/20260706_assign_v2_dev20/analysis/per_experiment_breakdown.md` |
| 单测 | 20 passed（v1: 13, v2: 7） |
