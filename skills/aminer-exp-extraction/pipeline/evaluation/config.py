"""冻结配置 — 板块 7 评估的全库唯一入口。

OPTIMAL_PROD_WORKFLOW_ID 是推荐的默认评估对象（CLI ``--workflow`` 的默认值），
但不再是唯一合法值——``run_batch_eval --workflow <any prod-wf*>`` 可评估任意已注册
prod workflow，以便用同一 dev_100 数据集做横向对比。eval 报告顶部标注实际 workflow_id。
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_venv_python() -> str:
    """Cross-platform interpreter for subprocess runners (.venv preferred)."""
    candidates = (
        PROJECT_ROOT / ".venv" / "bin" / "python",
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / "venv" / "bin" / "python",
        PROJECT_ROOT / "venv" / "Scripts" / "python.exe",
    )
    for path in candidates:
        if path.is_file():
            return str(path)
    return sys.executable

# --- 冻结：推荐最优 prod workflow（CLI --workflow 默认值，非唯一合法值） -------
OPTIMAL_PROD_WORKFLOW_ID = "prod-wf3-batch-bert-pipeline"
OPTIMAL_PROD_RUNNER = "pipeline/production/runners/batch_run_bert_pipeline.py"
OPTIMAL_PROD_STRATEGY_DOC = "pipeline/production/docs/STRATEGY_PROD_WF3.md"
WORKFLOW_SELECTION_REASON = (
    "latest adopted batch prod; field parity wf1/wf2 dev_10; fastest 1325-scale"
)

# workflow_id → prod runner 脚本映射（--workflow 可覆盖 OPTIMAL，run_batch_eval 据此选 runner）。
PROD_RUNNER_BY_WORKFLOW = {
    "prod-wf1-async-v1": "pipeline/production/runners/batch_run.py",
    "prod-wf2-batch-pipeline": "pipeline/production/runners/batch_run_pipeline.py",
    "prod-wf3-batch-bert-pipeline": "pipeline/production/runners/batch_run_bert_pipeline.py",
    "prod-wf4-llm-datasets-experiment": "pipeline/production/runners/batch_run_wf4.py",
    "prod-wf4-llm-datasets-nuextract-t15": "pipeline/production/runners/batch_run_wf4.py",
    "prod-wf4-llm-datasets-nuextract-sroecker": "pipeline/production/runners/batch_run_wf4.py",
    "prod-wf4-llm-datasets-gemma3-1b": "pipeline/production/runners/batch_run_wf4.py",
}

# --- Baseline（PC1 GLM5.2 Silver，方法论不同，报告须注明） -------------------
BASELINE_TYPE = "silver_glm52_fulltext"
BASELINE_PATH = "product_pipeline_pc2_handoff/extractions.batch_paper_md_result_matched_20260612.json"

# --- Handoff 包 -------------------------------------------------------------
HANDOFF_ROOT = "product_pipeline_pc2_handoff"
HANDOFF_CSV = "product_pipeline_pc2_handoff/data/paper_md_result_matched_20260612.csv"
HANDOFF_BASELINE_FULL = (
    "product_pipeline_pc2_handoff/extractions.batch_paper_md_result_matched_20260612.json"
)

# --- 评估输出区 -------------------------------------------------------------
EVAL_OUTPUT_DIR = PROJECT_ROOT / "pipeline_output" / "evaluation"
EVAL_RUNS_DIR = EVAL_OUTPUT_DIR / "runs"
MD_CACHE_DIR = PROJECT_ROOT / "pipeline_output" / "md_cache"

# --- 评估 fixtures（tracked 数据资产；md 落 MD_CACHE_DIR，见 .gitignore:39） --
EVALUATION_FIXTURES_DIR = PROJECT_ROOT / "pipeline" / "evaluation" / "fixtures"
DEV10_FIXTURE_ROOT = EVALUATION_FIXTURES_DIR / "dev_10"
DEV10_MANIFEST = DEV10_FIXTURE_ROOT / "manifest.json"
DEV100_FIXTURE_ROOT = EVALUATION_FIXTURES_DIR / "dev_100"
DEV100_MANIFEST = DEV100_FIXTURE_ROOT / "manifest.json"
DEV100_BASELINE_SLICE = DEV100_FIXTURE_ROOT / "baseline_slice.json"
DEV100_DATASET_JSON = DEV100_FIXTURE_ROOT / "dataset.json"
DEV100_META = DEV100_FIXTURE_ROOT / "meta.json"
DEV100_DATASET_ID = "dev_100"
DEV100_DATASET_VERSION = "0.1.0"
DEV100_DEFAULT_SEED = 20260709

# --- prod predictions 读取位置（板块 6 产物） --------------------------------
PROD_RUNS_DIR = PROJECT_ROOT / "pipeline_output" / "production" / "runs"

# --- venv（subprocess 调用 prod runner 用；跨平台探测 .venv / venv） ----------
VENV_PYTHON = _resolve_venv_python()

# --- composite_eval_v1 权重（provisional，可调；见 docs/EVAL_STRATEGY.md） ----
W_LLM = 0.40          # LLM 7 字段 composite_score_v7
W_ML = 0.15           # ML domain + experiment_type exact 均值
W_RULES_TEXT = 0.15   # rules conclusion + limitations word_jaccard 均值
W_DATASETS = 0.15     # datasets name recall
W_SAMPLESIZE = 0.10   # sample_size prod policy_ok
W_L1 = 0.05           # L1 结构 pass_rate
# evidence 为 product-track 监控项，不计入综合分。

# --- L1 enum：experiment_type 12 类（pack ml_classification 权威标签集） ------
# 来源：rule_ml_extraction_from_promote/rule_extraction_pack/ml_classification/
#       models/experiment_type/evaluation_report.json
EXPERIMENT_TYPE_ENUM = frozenset({
    "ablation", "benchmark", "case_study", "comparison", "data_analysis",
    "empirical_study", "field_study", "human_study", "lab_experiment",
    "other", "simulation", "survey",
})
# domain 标签空间在 pack 训练集里不闭合（仅 5 类，多为 computer_science），
# 故 domain 不做严格 enum，仅做非空监控，避免误判合法标签。
