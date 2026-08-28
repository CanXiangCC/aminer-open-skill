# Assignment v1 报告 — cooccurrence 分配策略

> **历史基线**（已被 [v2_type_aware](v2_report.md) 取代为当前最优 assignment 方案）
> v1 dev_20：fuzzy F1 36.10%；v2 提升至 37.45%（+1.35 pp），field_study_empty_rate 0%→100%。

> 策略：`v1_cooccurrence`（+ 对照基线 `v1_broadcast`）
> 实现：`experiments/rule_extraction/datasets/assignment/v1_cooccurrence.py`
> 评估：dev_20 (主) + dev_10 (smoke)

## 1. 策略说明

两阶段流水线：

```
md_text ──v4.3 extract──▶ paper_datasets[]
                              │
   Gold1 experiments[] (stripped) ──┐
   md_text ────────────────────────┤
                                   ▼
                          v1_cooccurrence.assign
                                   │
                                   ▼
                   experiments_with_datasets[]  ──▶ per-experiment eval (Gold1)
```

### 规则优先级（详见 DESIGN.md）

1. **单 experiment 短路**：直接把 paper_datasets 赋给唯一 experiment。
2. **共现匹配（主规则）**：
   - **blob 命中（强信号）**：dataset 名（+ alias，经 `normalize_fuzzy` 归一）出现在 experiment 的 `method` / `key_results` / `evidence` 文本中。
   - **md 窗口命中（弱信号）**：dataset 在 md 中提及位置 ±400 字符窗口内出现 experiment_name 关键词 token（去停用词）。
   - 若 blob 命中非空，仅分配到 blob 命中 experiment；否则用窗口命中。
3. **experiment_type 约束**：`ablation` 仅分共现到的 dataset；`field_study` 默认 `[]`。
4. **主实验兜底**：未匹配 dataset → 第一个 `comparison`，或 experiment_name 含 `evaluation`/`benchmark`/`comparison`/`main`/`overall` 的 `other`。
5. **broadcast 兜底**：以上全失败且无 field_study → paper_datasets 复制到每个 experiment。

### 关键设计决策

- **blob 优先于 window**：短 md 中 ±400 窗口会跨 section 串入相邻 experiment，blob 命中是更强的「该 experiment 确实用了该 dataset」信号。实测（`6632f3d20` case）证明该决策有效抑制了窗口泄漏。
- **`other` 类不作为主兜底目标**：避免把未匹配 dataset 灌进任意 experiment；只有名称含 fallback 关键词的 `other` 才接收兜底，否则走 broadcast/drop。

## 2. 评估指标

### 2.1 dev_20 主评估（Gold1 per_experiment, 20 papers / 28 experiments）

| 维度 | 指标 | v1_cooccurrence | v1_broadcast | Δ |
|------|------|----------------:|-------------:|---:|
| **总体** | strict F1 | 31.05% | 27.27% | +3.78 pp |
| | strict R / P | 51.19 / 22.28 | 51.19 / 18.18 | 0 / +4.10 |
| | **fuzzy F1** | **36.10%** | 31.35% | **+4.75 pp** |
| | fuzzy R / P | 59.52 / 25.91 | 59.52 / 21.28 | 0 / +4.63 |
| **multi-exp** (5 papers / 13 exps) | strict F1 | 28.17% | 20.41% | +7.76 pp |
| | **fuzzy F1** | **33.80%** | 21.24% | **+12.56 pp** |
| | fuzzy R / P | 54.55 / 24.49 | 54.55 / 13.19 | 0 / +11.30 |

### 2.2 dev_10 smoke test（Gold2 paper_union, extract-only）

| 策略 | fuzzy R / P / F1 |
|------|------------------|
| v4.3 (paper-level, 未走 assign) | 58.54 / 53.93 / **56.14%** |

✅ paper_union 流程未被破坏，与历史 v4.3 baseline 一致。

### 2.3 兜底统计

| 指标 | v1_cooccurrence | v1_broadcast |
|------|----------------:|-------------:|
| broadcast 触发 experiment | 2 | 28 (全部) |
| broadcast 触发 paper | 1 (`628304515…`) | 20 (全部) |
| field_study experiment 总数 | 2 | 2 |
| field_study 空集命中 (gold=[] & pred=[]) | 0 | 0 |
| **field_study 空集命中率** | **0%** | 0% |

## 3. 假设与限制

### 假设
- **A1**：paper 级 v4.3 提取的 dataset 名是 assign 阶段可用的全部候选；assign 无法补回 extract 漏抽的 dataset。
  → 实测：assign fuzzy Recall (59.52%) ≤ extract paper-level fuzzy Recall (dev_20 v4.3 paper_union 约 60% 量级)，Recall 上界由 extract 决定。
- **A2**：experiment 的 `method` / `key_results` / `evidence` 文本能可靠指示其使用的 dataset。
  → 大部分成立，但 ablation / field_study experiment 的文本常不含 dataset 名（仅含组件名），导致 ablation 全 0 命中（`66bac1ca` 3 个 ablation）。
- **A3**：`experiment_type` 字段可信。
  → dev_20 5 篇均标注，但 `other` 类（`628304515`）信息缺失，无法区分 GNN/CNN 子任务。

### 已知限制
- **L1**：field_study 默认空集未生效。`659e2146` (Real-World Aerial) 与 `661ddba8` (TurtleBot Anomaly) 均被分到 4 个 dataset，原因：blob 命中（dataset 名出现在 field_study experiment 文本）绕过了 field_study 屏蔽。
- **L2**：±400 字符窗口在短 md 跨 section，导致 `6632f3d20` 的 `kgefromthehighd` 串入 Pedestrian experiment。
- **L3**：ablation 子实验默认仅分共现 dataset，但 ablation 文本常不含 dataset 名 → 全 0 命中（`66bac1ca` 3 个 ablation 全 0）。
- **L4**：paper 级 v4.3 的噪声 dataset 名（`sgraf`/`following`/`sgpa`/`spd`/`wang`/`dmim`/`fdmer`）被共现匹配分到子实验，拉低 Precision。这是 extract 阶段问题，但 assign 无法过滤。
- **L5**：`other` 类 experiment 无 `experiment_type` 信号时退化为 broadcast（`628304515`）。

## 4. 与 broadcast 基线对比

v1_cooccurrence 在所有维度均优于 naive broadcast：

- **总体 fuzzy F1** +4.75 pp（36.10% vs 31.35%），增益全来自 Precision（+4.63 pp），Recall 持平。
- **multi-experiment fuzzy F1** +12.56 pp（33.80% vs 21.24%），Precision +11.30 pp —— 共现分配对多 experiment 论文收益最大（broadcast 把所有 paper dataset 灌进每个子实验，Precision 崩塌）。
- **broadcast 触发率** 5% (1/20) vs 100% (20/20)，证明 v1 规则链在绝大多数论文成功避免兜底。

## 5. 下一步 (assign_v2)

1. **section 就近分配**（核心）：复用 `dataset_preprocess._parse_sections`，把 dataset 提及定位到具体 section，按 experiment_name 与 section header 的就近关系分配，替代 ±400 字符窗口。预期修复 L2、L5。
2. **field_study 强屏蔽**：`experiment_class == "field_study"` 时无条件 `datasets=[]`，忽略 blob/window 命中。预期修复 L1，把 field_study 空集命中率从 0% 拉到 ≥50%。
3. **ablation 继承主 comparison 子集**：ablation experiment 若与主 comparison 在同一 section 群，继承主 experiment 的 dataset 子集（按 ablation 文本中出现的组件名筛选）。预期修复 L3。
4. **extract 联动**：与 v4.x recall 改进并行推进，过滤 method-name 噪声（`sgraf`/`following` 等），提升 assign Precision 上界。预期修复 L4。
5. **`other` 类共现放宽**：`other` experiment 也参与 blob/window 匹配（v1 已支持，但需在无共现时退化为 section 就近而非 broadcast）。

## 6. 复现命令

```bash
# dev_20 v1_cooccurrence (主结果)
python -m experiments.rule_extraction.datasets.test_runner \
  --strategy v4_3 --extract-strategy v4_3 --assign-strategy v1_cooccurrence \
  --stage both --batch dev_20 --gold-set per_experiment \
  --run-id 20260706_assign_v1_dev20 --eval-modes strict,fuzzy

# dev_20 broadcast 基线
python -m experiments.rule_extraction.datasets.test_runner \
  --strategy v4_3 --extract-strategy v4_3 --assign-strategy v1_broadcast \
  --stage both --batch dev_20 --gold-set per_experiment \
  --run-id 20260706_assign_broadcast_dev20 --eval-modes strict,fuzzy

# dev_10 smoke (paper_union, extract-only)
python -m experiments.rule_extraction.datasets.test_runner \
  --strategy v4_3 --stage extract --batch dev_10 --gold-set paper_union \
  --run-id 20260706_assign_smoke_dev10 --eval-modes fuzzy

# 单测
pytest experiments/rule_extraction/datasets/assignment/ -q
```

## 7. 产物路径

| 产物 | 路径 |
|------|------|
| v1_cooccurrence 结果 | `runs/20260706_assign_v1_dev20/results/assign_v1_cooccurrence_on_dev_20.json` |
| broadcast 基线结果 | `runs/20260706_assign_broadcast_dev20/results/assign_v1_broadcast_on_dev_20.json` |
| 对比报告 | `runs/20260706_assign_v1_dev20/analysis/comparison.md` |
| 多 experiment case study | `runs/20260706_assign_v1_dev20/analysis/per_experiment_breakdown.md` |
| 单测 | `assignment/test_v1_cooccurrence.py` (13 passed) |
