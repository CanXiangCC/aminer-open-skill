# Evaluation 评测规范

本目录用于主项目正式 evaluation 体系。评测输入按 **Gold / Prediction / Stage trace / Reference trace** 解耦，运行产物写入 `output/runs/eval/{run_id}/` 或 CLI 指定的 run 目录。

本 evaluation 体系不依赖 `bulk_extraction/`。

## 数据关系

- Gold = 人工或指定 Gold set 的正确答案，只包含 experiment array，不写入 latency/token/score。
- Prediction = 某个 strategy 抽取出的 experiment array，用于和 Gold 对比 accuracy。
- Stage trace = 某个 strategy 的实际运行成本，用于统计 actual latency/token。
- Reference trace = Gold/reference 侧固定成本 sidecar，用于稳定 benchmark cost score。

```text
accuracy = prediction vs gold
latency/token score = actual stage trace vs fixed reference trace
total_score = accuracy_score、latency_score、token_score 的加权组合
```

## 输入目录

```text
data/gold/{batch}/{gold_set}/{paper_id}.json
data/gold/{batch}/{gold_set}/traces/{paper_id}.json
data/predictions/{batch}/{strategy}/{paper_id}.json
output/runs/eval/{batch}/manual_{strategy}/traces/{strategy}/{paper_id}.json
```

| 类型 | 位置 | 含义 |
|------|------|------|
| Reference trace | `data/gold/{batch}/{gold_set}/traces/` | 数据集固定成本基准 |
| Stage trace | `output/runs/eval/{batch}/manual_{strategy}/traces/{strategy}/` | 被评测 strategy 的实际成本（strategy runner 默认路径） |
| Prediction | `data/predictions/{batch}/{strategy}/` | 被评测 strategy 的抽取结果 |

Gold 和 Prediction 的 experiment 对象以 `schemas/experiment_v1.schema.json` 为准，顶层仍是 experiment 对象数组。不要改变现有 Gold 文件结构；reference cost 使用 sidecar reference trace 目录。

## Stage trace 按 batch 隔离

**Prediction 与 Stage trace 都必须与 `--batch` 对齐**，否则 evaluation 会把不同 batch 的 paper_id 并集起来，出现 `missing prediction` 等误报。

| 产物 | 默认路径 | 是否含 `{batch}` |
|------|----------|------------------|
| Prediction | `data/predictions/{batch}/{strategy}/` | 是 |
| Stage trace | `output/runs/eval/{batch}/manual_{strategy}/traces/{strategy}/` | 是 |
| Reference trace | `data/gold/{batch}/{gold_set}/traces/` | 是 |

Strategy runner（如 `section_union_glm45_airx`、`full_text_glm45_airx`）和 baseline（`src/baselines/full_text_glm5_2.py`）在未指定 `--trace-dir` 时，会写入上述 **batch 级** stage trace 目录。目录内每篇论文一个 `{paper_id}.json`，同一 strategy 跑 `dev_10` 与 `dev_20` 不会混写。

```powershell
# dev_10 → output/runs/eval/dev_10/manual_section_union_glm45_airx/traces/section_union_glm45_airx/
python -m src.strategies.runners.section_union_glm45_airx --batch dev_10

# dev_20 → output/runs/eval/dev_20/manual_section_union_glm45_airx/traces/section_union_glm45_airx/
python -m src.strategies.runners.section_union_glm45_airx --batch dev_20
```

Evaluation JSON config 里的 `strategies.{strategy}.trace_dir` 必须指向**同一 batch** 下的 stage trace，并与 `prediction_dir` 的 batch 一致。例如 `configs/evaluation/dev_10_section_union_glm45_airx.json`：

```json
"strategies": {
  "section_union_glm45_airx": {
    "prediction_dir": "data/predictions/dev_10/section_union_glm45_airx",
    "trace_dir": "output/runs/eval/dev_10/manual_section_union_glm45_airx/traces/section_union_glm45_airx"
  }
}
```

自定义 run 仍可用 `--trace-dir` 覆盖默认路径（dry-run、smoke test 等）。旧路径 `output/runs/eval/manual_{strategy}/traces/{strategy}/`（不含 batch）已弃用；若目录里已有混 batch 的 trace，请迁移或在新路径重跑后再评测。

## Semantic Scorer

默认 semantic scorer 使用本地 `sentence-transformers` 模型 `BAAI/bge-m3`，适合中文 Gold 与英文 Prediction 的跨语言匹配。

安装依赖：

```bash
pip install sentence-transformers
```

首次运行会由 `sentence-transformers` 下载模型；也可以提前缓存到本地。代码不会自动安装依赖。缺少依赖时会报错：

```text
sentence-transformers is required for embedding semantic scoring. Install with: pip install sentence-transformers
```

也可用 `--semantic-type jaccard` 或 config 中 `"type": "jaccard"` 启用 token Jaccard fallback/debug。

## Accuracy

如果 Gold 存在，runner 计算：

- experiment alignment similarity：`experiment_name + research_goal + method + conclusion` 的 semantic similarity。
- `domain_score = 1 if gold.domain == prediction.domain else 0`。
- `datasets_score` 使用 dataset `name` 集合 F1。
- `metrics_score` 使用 metrics 集合 F1，保留 `acc` / `accuracy` 同义归一化。
- `key_results_score` 使用 `key_results` 拼接文本的 semantic similarity。
- `exp_semantic_score` 使用 `experiment_name + research_problem + research_goal + method + conclusion` 的 semantic similarity。

```text
exp_accuracy =
    0.15 * domain_score
  + 0.20 * datasets_score
  + 0.15 * metrics_score
  + 0.25 * key_results_score
  + 0.25 * exp_semantic_score

paper_accuracy = mean(matched_exp_accuracy) * count_alignment_factor
count_alignment_factor = matched_count / max(gold_count, pred_count, 1)
```

## Reference Trace

Reference cost 从 `gold_set.reference_trace_dir/{paper_id}.json` 读取（默认 `{gold_set.path}/traces`）。格式复用 StageTrace；`reference_cost_source` 在 `run_config.json` 中记为 `dataset_fixed`。

```json
{
  "paper_id": "5b1643ba8fbcbf6e5a9bc884",
  "strategy": "gold_reference_full_text_glm5_2",
  "model": "glm-5.2",
  "status": "success",
  "prediction_path": "data/gold/dev_10/full_text_glm5_2/5b1643ba8fbcbf6e5a9bc884.json",
  "error": null,
  "latency_ms": {
    "load": 0,
    "chunk": 0,
    "process": 0,
    "llm": 0,
    "total": 161910.2251000004
  },
  "tokens": {
    "input_tokens": 47130,
    "output_tokens": 11329,
    "total_tokens": 58459,
    "llm_call_count": 1
  }
}
```

如果 reference trace 缺失，评测继续，但 reference cost 字段、latency/token score 为 null，`total_score` 也为 null，避免伪造效率分。

## Stable Cost Score

Latency/token 不再使用当前 batch 内 min-max。稳定 benchmark 分数固定对比 reference cost：

```text
latency_ratio = actual_latency_total_ms / reference_latency_total_ms
latency_score = min(1.0, reference_latency_total_ms / actual_latency_total_ms)

token_ratio = actual_total_tokens / reference_total_tokens
token_score = min(1.0, reference_total_tokens / actual_total_tokens)
```

边界：`actual <= 0` 或 `reference <= 0` 时对应 ratio/score 为 null。若 actual 低于 reference，score cap 到 1.0。

默认总分公式：

```text
total_score =
    0.60 * accuracy_score
  + 0.20 * latency_score
  + 0.20 * token_score
```

只有 `accuracy_score`、`latency_score`、`token_score` 都非 null 时才计算 `total_score`。

## 输出字段

Per paper 输出包含：

- `accuracy_score` 和 `domain_score`、`datasets_score`、`metrics_score`、`key_results_score`、`exp_semantic_score`
- `latency_total_ms`、`reference_latency_total_ms`、`latency_ratio`、`latency_score`
- `total_tokens`、`reference_total_tokens`、`token_ratio`、`token_score`
- `total_score`

Per strategy 会汇总均值，包括 `reference_latency_mean_ms`、`latency_ratio_mean`、`reference_token_mean`、`token_ratio_mean`、accuracy coverage 和 reference cost coverage。

Global 输出包含 `strategy_count`、`paper_metric_count`、`accuracy_available_count`、`reference_cost_available_count`、`total_score`。

## 输出产物

```text
output/runs/eval/{run_id}/
├── per_paper_metrics.json
├── per_strategy_metrics.json
├── global_metrics.json
├── failures.json
├── run_config.json
├── traces/
└── report.md
```

`run_config.json` 记录实际生效配置，包括 config path、Gold set、reference trace dir、semantic scorer、scoring weights/formula、resolved prediction/trace dirs、output_dir 和 run_id。

## JSON Config 运行方式

示例：

```json
{
  "name": "dev_10_full_text_glm5_2_smoke",
  "batch": "dev_10",
  "manifest": "data/fixtures/dev_10/manifest.json",
  "gold_set": {
    "name": "full_text_glm5_2",
    "type": "model_generated",
    "model": "glm-5.2",
    "path": "data/gold/dev_10/full_text_glm5_2",
    "reference_trace_dir": "data/gold/dev_10/full_text_glm5_2/traces",
    "reference_cost_source": "dataset_fixed",
    "notes": "Reference content and fixed reference cost for dev_10."
  },
  "semantic_scorer": {
    "type": "embedding",
    "model": "BAAI/bge-m3",
    "device": "cpu",
    "similarity": "cosine"
  },
  "scoring": {
    "weights": {
      "accuracy": 0.60,
      "latency": 0.20,
      "token": 0.20
    },
    "cost_score": {
      "formula": "min(1, reference/actual)",
      "missing_reference": "null_total_score"
    }
  },
  "strategies": {
    "full_text_glm5_2": {
      "prediction_dir": "data/predictions/dev_10/full_text_glm5_2",
      "trace_dir": "output/runs/eval/dev_10/smoke_full_text_glm5_2/traces/full_text_glm5_2"
    }
  },
  "output_dir": "output/runs/eval/smoke_full_text_glm5_2"
}
```

运行：

```bash
python -m src.evaluation.runner --config configs/evaluation/dev_10_full_text_glm5_2.json
```

`full_text_glm45_airx` 抽取与评测：

```bash
python -m src.strategies.runners.full_text_glm45_airx --batch dev_10 --skip-existing
python -m src.evaluation.runner --config configs/evaluation/dev_10_full_text_glm45_airx.json
```

CLI 参数优先级高于 config：

- `--batch`
- `--strategy` / `--strategies`
- `--gold-dir`
- `--reference-trace-dir`
- `--prediction-dir` / `--trace-dir`，仍只允许单 strategy
- `--semantic-model`
- `--semantic-device`
- `--semantic-type embedding|jaccard`
- `--output-dir` / `--run-id`

旧 CLI 仍可用：

```bash
python -m src.evaluation.runner \
  --batch dev_10 \
  --strategy full_text_glm5_2 \
  --gold-dir data/gold/dev_10/full_text_glm5_2 \
  --prediction-dir data/predictions/dev_10/full_text_glm5_2 \
  --trace-dir output/runs/eval/dev_10/smoke_full_text_glm5_2/traces/full_text_glm5_2 \
  --reference-trace-dir data/gold/dev_10/full_text_glm5_2/traces \
  --semantic-type jaccard \
  --output-dir output/runs/eval/smoke_full_text_glm5_2
```
