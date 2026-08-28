# 板块 6 · Production Layer (`pipeline/production/`)

全字段生产编排层。消费冻结的板块 5 wf8 LLM（7 字段）+ 远程
`rule_ml_extraction_from_promote/rule_extraction_pack` 规则/ML，按异步 Wave DAG
编排合并，产出 `experiment[]`（对齐 `experiment_v1.schema.json`）。

## 快速开始

```bash
# 1. import 自检
venv/Scripts/python.exe -c "from pipeline.production.orchestrator import run_production_workflow; print('ok')"

# 2. dry-run（无 GPU / 无服务，不跑文本管线，全 stub）
venv/Scripts/python.exe pipeline/production/runners/run_single.py \
  --paper 53e9a3fbb7602d9702d13e26 --workflow prod-wf1-async-v1 --dry-run

# 3. 单篇 smoke（需 BERT:5000 + Ollama:11434）
venv/Scripts/python.exe pipeline/production/runners/run_single.py \
  --paper 53e9a3fbb7602d9702d13e26 --workflow prod-wf1-async-v1
```

## CLI 全表

所有 runner 默认 manifest = dev_10（`pipeline/evaluation/fixtures/dev_10/manifest.json`）。
md 本地解析（`data/md → dev_10/md → eval md_cache` 三级），dev_10 不触网。dry-run 不跑文本管线。

```bash
# 单篇（prod-wf1-async-v1）
venv/Scripts/python.exe pipeline/production/runners/run_single.py \
  --paper 53e9a3fbb7602d9702d13e26 --workflow prod-wf1-async-v1 [--dry-run] [--run-id ...]

# 批量 wf1（异步 Wave DAG）
venv/Scripts/python.exe pipeline/production/runners/batch_run.py \
  --workflow prod-wf1-async-v1 --limit 10 [--dry-run] [--run-id ...]

# 批量 wf2（跨篇 BERT∥LLM 两槽流水线）
venv/Scripts/python.exe pipeline/production/runners/batch_run_pipeline.py \
  --workflow prod-wf2-batch-pipeline --limit 10 \
  --bert-concurrency 1 --llm-concurrency 1 [--dry-run] [--run-id ...]

# 批量 wf3（跨篇 /filter/batch，当前生产批量最优）
venv/Scripts/python.exe pipeline/production/runners/batch_run_bert_pipeline.py \
  --workflow prod-wf3-batch-bert-pipeline --limit 10 \
  --bert-batch-size 32 --bert-chunk-papers 0 --llm-concurrency 1 [--dry-run] [--run-id ...]

# 批量 wf4（实验线：LLM 直抽 datasets，8 字段，非 canonical）
venv/Scripts/python.exe pipeline/production/runners/batch_run_wf4.py \
  --workflow prod-wf4-llm-datasets-experiment \
  --manifest pipeline/evaluation/fixtures/dev_10/manifest.json \
  --limit 10 --bert-batch-size 32 --run-id prod-dev10-wf4-v0.1.0

# wf3 vs wf4 对比报告（读两个 run dir + handoff，写 wf3_wf4_compare.md）
venv/Scripts/python.exe pipeline/production/runners/compare_wf3_wf4.py \
  --wf3-run prod-dev10-wf3-v0.1.0 --wf4-run prod-dev10-wf4-v0.1.0

# wf4 model sweep（仅换 Ollama model，冻结 prompt）
venv/Scripts/python.exe pipeline/production/runners/batch_run_wf4.py \
  --workflow prod-wf4-llm-datasets-nuextract-t15 \
  --manifest pipeline/evaluation/fixtures/dev_10/manifest.json \
  --run-id prod-dev10-wf4-nuextract-t15-v0.1.0 \
  --ollama-model nuextract-tiny-v1.5:q4_k_xl --bert-batch-size 32 --llm-concurrency 1

# wf4 多 model 横评（速度 + v7 + datasets recall）
venv/Scripts/python.exe pipeline/production/runners/compare_wf4_models.py \
  --runs prod-dev10-wf4-v0.1.0,prod-dev10-wf4-nuextract-t15-v0.1.0,prod-dev10-wf4-nuextract-sroecker-v0.1.0 \
  --baseline prod-dev10-wf4-v0.1.0

# 一键 sweep（跳过已存在 run）
venv/Scripts/python.exe pipeline/production/runners/sweep_wf4_models.py
```

### workflow 速查

| workflow_id | 定位 | runner |
|---|---|---|
| `prod-wf1-async-v1` | 单篇异步基线（DEFAULT_WORKFLOW） | run_single / batch_run |
| `prod-wf2-batch-pipeline` | 批量 BERT∥LLM 流水线 | batch_run_pipeline |
| `prod-wf3-batch-bert-pipeline` | **批量最优**（/filter/batch） | batch_run_bert_pipeline |
| `prod-wf4-llm-datasets-experiment` | 实验线（LLM 直抽 datasets，非 canonical） | batch_run_wf4 |
| `prod-wf4-llm-datasets-nuextract-t15` | wf4 model sweep（NuExtract q4_k_xl） | batch_run_wf4 |
| `prod-wf4-llm-datasets-nuextract-sroecker` | wf4 model sweep（NuExtract sroecker tag） | batch_run_wf4 |

> dev_10 实测墙钟：wf3 28.37s < wf2 29.51s < wf1 51.51s；wf4 实验线 36.34s（含 8 字段代价）。

## 目录

```
pipeline/production/
├── config.py            # PACK_ROOT, 输出目录, wf8 冻结配置
├── schema.py            # LLM/RULE/META 字段表, FieldResult, empty_experiment
├── context.py           # PaperContext
├── registry.py          # extractor 注册表（可拆卸）
├── orchestrator.py      # 异步 Wave DAG 调度
├── merge.py             # production Merger（字段所有权不相交）
├── manifest.py          # run 级 manifest
├── monitor.py           # 单篇 monitor + history jsonl
├── adapters/            # rule_pack.py (sys.path 隔离) + wf8_llm.py
├── extractors/          # meta/ llm/ rules/ ml/
├── workflows/           # spec.py + prod_wf1/wf2/wf3/wf4 specs
├── runners/             # run_single, batch_run, batch_run_pipeline, batch_run_bert_pipeline, batch_run_wf4, compare_wf3_wf4, compare_wf4_models, sweep_wf4_models
└── docs/                # ARCHITECTURE / FIELD_DEPENDENCIES / STRATEGY_PROD_WF* / WORKFLOW_PROD_WF*
```

## 关键约束

- **只读消费**：不修改 `pipeline/benchmark/**`、`rule_ml_extraction_from_promote/**`
  业务逻辑（仅 import）、`preprocess/**`、`scibert_package/**`、`bert_service/**`。
- **禁用 wf9** / 8 字段 LLM sample_size 方案；禁 `max(datasets[].sample_size)` 填
  top-level；禁复制规则算法进 preprocess；禁移动/重命名 `rule_extraction_pack/`。
- **可拆卸**：换 extractor 版本仅改 `registry.py`，orchestrator 不动。

## 文档

- [STRATEGY_PROD_WF1.md](docs/STRATEGY_PROD_WF1.md) — prod-wf1 算法 + 编排逻辑（A/B 基线）
- [STRATEGY_PROD_WF2.md](docs/STRATEGY_PROD_WF2.md) — prod-wf2 跨篇 BERT∥LLM 流水线（算法+编排+timing）
- [STRATEGY_PROD_WF3.md](docs/STRATEGY_PROD_WF3.md) — prod-wf3 跨篇 /filter/batch（算法+编排+timing+归因）
- [STRATEGY_PROD_WF4.md](docs/STRATEGY_PROD_WF4.md) — prod-wf4 LLM 直抽 datasets（实验线，单变量 diff + 风险 + 验收）
- [STRATEGY_PROD_WF4_MODEL_SWEEP.md](docs/STRATEGY_PROD_WF4_MODEL_SWEEP.md) — wf4 Ollama model 扫参（dev_10 速度+准确性）
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — DAG + 关键路径 + 设计偏离
- [FIELD_DEPENDENCIES.md](docs/FIELD_DEPENDENCIES.md) — 字段分工 + sample_size 策略
- [EXTRACTOR_CONTRACT.md](docs/EXTRACTOR_CONTRACT.md) — Extractor 接口 + 替换流程
- [MONITORING.md](docs/MONITORING.md) — monitor/manifest/history
- [WORKFLOW_PROD_WF1.md](docs/WORKFLOW_PROD_WF1.md) — prod-wf1 详细
- [WORKFLOW_PROD_WF2.md](docs/WORKFLOW_PROD_WF2.md) — prod-wf2 详细
- [WORKFLOW_PROD_WF3.md](docs/WORKFLOW_PROD_WF3.md) — prod-wf3 详细
- [WORKFLOW_PROD_WF4.md](docs/WORKFLOW_PROD_WF4.md) — prod-wf4 详细（含 dev_10 结果 + 采纳结论）
