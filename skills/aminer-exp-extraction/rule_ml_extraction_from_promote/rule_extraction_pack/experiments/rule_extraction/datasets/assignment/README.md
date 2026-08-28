# Datasets per-experiment assignment

## 目录职责

把 paper 级 dataset 列表 **后处理** 分配到各 `experiment_name`。与 `../strategies/`
解耦：

```
strategies/   : (md_text, paper_id) -> paper_datasets[]        # 不改 v4.3 核心
assignment/   : (paper_datasets, experiments[], md_text)
              -> experiments_with_datasets[]                    # 本目录职责
```

`shared/dataset_evaluator.py` 继续服务 paper_union 评估；per-experiment 评估放
`evaluator.py`。

## API

```python
from experiments.rule_extraction.datasets.assignment import (
    ASSIGN_STRATEGIES, run_assignment,
)

strategy = ASSIGN_STRATEGIES["v2_type_aware"]()
experiments_with_datasets = run_assignment(
    strategy,
    paper_datasets,        # v4.3 输出
    experiments_stripped,  # Gold1 experiments，datasets 字段已剥
    md_text,
    paper_id="6632f3d201d2a3fbfc5b36bb",
)
# 返回 list[dict]，与输入 experiments 同序，每项 = 原 experiment 字段 + datasets + assignment_trace
```

## 策略

| id | 类 | 说明 |
|----|----|------|
| `v2_type_aware` | `AssignV2TypeAware` | **当前最优**：field_study 强屏蔽 + ablation 继承主实验 + section 路由 |
| `v1_cooccurrence` | `AssignV1Cooccurrence` | 历史基线：共现匹配 + experiment_type 约束 + 主实验兜底 + broadcast |
| `v1_broadcast` | `AssignV1Broadcast` | 对照基线：每 experiment 复制 paper_datasets |

## 与 test_runner 参数

```bash
# v2 推荐（field_study 强屏蔽 + ablation 继承主实验）
python -m experiments.rule_extraction.datasets.test_runner \
  --strategy v4_3 \
  --assign-strategy v2_type_aware \
  --stage both \
  --batch dev_20 \
  --gold-set per_experiment \
  --run-id 20260706_assign_v2_dev20 \
  --eval-modes strict,fuzzy

# v1 对照
python -m experiments.rule_extraction.datasets.test_runner \
  --strategy v4_3 \
  --assign-strategy v1_cooccurrence \
  --stage both \
  --batch dev_20 \
  --gold-set per_experiment \
  --run-id 20260706_assign_v1_dev20 \
  --eval-modes strict,fuzzy
```

- `--stage extract|assign|both`：`extract` 只跑 paper 级（原流程）；`assign`/`both`
  跑 v4.3 extract → assign → per-experiment 评估
- `--extract-strategy`（默认 `v4_3`）：paper 级提取策略
- `--assign-strategy`（默认 `v2_type_aware`，**当前最优**）：assignment 策略 id
- `--gold-set per_experiment`：assignment 评估必用 Gold1

## Experiment 列表来源

assignment 需要每个 experiment 的 `experiment_name` / `method` / `key_results` /
`evidence` / `experiment_type` / `experiment_subject`，但**不能读取 gold 的
`datasets` 字段**。来源链：

```
data/gold/{batch}/full_text_glm5_2/{paper_id}.json   (主项目 gold，只读)
  ↓ build_gold_sets.py
data/gold/{batch}/per_experiment/{paper_id}.json     (Gold1，含 datasets)
  ↓ test_runner.load_gold_experiments_stripped()
experiments[] with `datasets` field removed           (喂给 assignment)
```

评估时仍用 Gold1 完整 experiment（含 gold datasets）作对照。

## 设计文档

详细规则优先级 / fallback / IO schema / 已知失败模式见 [`DESIGN.md`](DESIGN.md)。
策略实现说明 + 指标见 [`v1_report.md`](v1_report.md)、[`v2_report.md`](v2_report.md)。
