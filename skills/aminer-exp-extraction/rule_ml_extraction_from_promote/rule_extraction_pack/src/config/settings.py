"""
模块名称：全局配置与 Stage Gate 阈值
Phase：Foundation（全阶段共用）

职责：
    集中定义路径配置、chunk 参数、Stage Gate 阈值常量，
    以及从 .env 加载的 LLM / API 相关配置。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_ZHIPUAI_CHAT_COMPLETIONS_URL = (
    "https://open.bigmodel.cn/api/paas/v4/chat/completions"
)
DEFAULT_VLLM_QWEN_BASE_URL = "http://127.0.0.1:8000/llm/v1"


def normalize_zhipu_api_url(url: str) -> str:
    """Accept either full chat/completions URL or OpenAI-compatible /v4 base URL."""
    normalized = url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v4"):
        return f"{normalized}/chat/completions"
    return normalized


def normalize_vllm_api_url(url: str) -> str:
    """Accept either full chat/completions URL or OpenAI-compatible /v1 base URL."""
    normalized = url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


# --- 路径常量 ---

OUTPUT_DEBUG_DIR = "output/debug"
OUTPUT_RUNS_DIR = "output/runs"
DATA_FIXTURES_MANIFEST = "data/fixtures/manifest.json"
DATA_GOLD_DIR = "data/gold"
DATA_EXAMPLES_DIR = "data/examples"
EXTRACTIONS_DEMO_BATCH = "data/examples/extractions_demo.batch.json"
PAPER_MD_CSV = "data/paper_md_result_matched_20260612.csv"
SCHEMA_EXPERIMENT_V1 = "schemas/experiment_v1.schema.json"
SCHEMA_EXPERIMENT_V1_REFERENCE = "schemas/experiment_v1.reference.md"

# --- Stage Gate 阈值 ---

STRUCTURE_CONFIDENCE_DEGRADED_THRESHOLD = 0.5
# structure confidence < 0.5 -> degraded=True，orchestrator 建议 full text

CHUNK_COVERAGE_MIN = 0.3
# chunk coverage < 0.3 -> ok=False 或 degraded=True
# orchestrator 策略：优先 degraded + full text fallback；若 chunk 完全失败则 ok=False

RETRIEVAL_MIN_CANDIDATES = 1
# retrieval 候选数 < 1 -> degraded=True，fallback full text

PREFLIGHT_PASS_REQUIRED = True
# preflight 未通过 -> 禁止调用 LLM（abort 或 expand context 后重试）

# --- Chunk 参数 ---

CHUNK_TOKEN_MIN = 300
CHUNK_TOKEN_MAX = 800
CHUNK_OVERLAP = 150
TOP_K_CHUNKS = 10
SLIDING_WINDOW_SIZE = 600

# --- LLM 参数（从 .env 加载） ---

ZHIPUAI_API_KEY: str | None = os.getenv("ZHIPUAI_API_KEY") or None
ZHIPUAI_API_URL: str = normalize_zhipu_api_url(
    os.getenv("ZHIPUAI_API_URL", DEFAULT_ZHIPUAI_CHAT_COMPLETIONS_URL)
)
LLM_MODEL: str = os.getenv("LLM_MODEL", "glm-4-flash")
LLM_MAX_INPUT_TOKENS: int | None = (
    int(os["LLM_MAX_INPUT_TOKENS"]) if os.getenv("LLM_MAX_INPUT_TOKENS") else None
)
LLM_TIMEOUT_SECONDS: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))

VLLM_QWEN_BASE_URL: str = os.getenv("VLLM_QWEN_BASE_URL", DEFAULT_VLLM_QWEN_BASE_URL)
VLLM_QWEN_API_URL: str = normalize_vllm_api_url(VLLM_QWEN_BASE_URL)
VLLM_QWEN_API_KEY: str = os.getenv("VLLM_QWEN_API_KEY") or "EMPTY"
VLLM_QWEN_MODEL: str | None = os.getenv("VLLM_QWEN_MODEL") or None

# --- Section-Union 参数 ---

SECTION_UNION_CONFIDENCE_MIN = 0.7
SECTION_UNION_KEYWORD_MIN_HITS = 5
SECTION_UNION_CHAR_BUDGET = 80_000
SECTION_UNION_CHAR_BUDGET_RATIO = 0.45
SECTION_UNION_MAX_INPUT_RATIO = 0.45
SECTION_UNION_ENABLE_KEYWORD_SUPPLEMENT = False
SECTION_UNION_MAX_CHUNKS_PER_SECTION = 2
SECTION_UNION_MAX_SELECTED_CHUNKS = 12

SECTION_TITLE_PHRASE_KEYWORDS = (
    "experimental results",
    "experimental setup",
    "experimental settings",
    "main results",
    "performance evaluation",
    "empirical evaluation",
    "empirical results",
    "benchmark results",
    "ablation study",
    "ablation studies",
    "implementation details",
    "training setup",
    "testing setup",
    "training dataset",
    "test dataset",
    "materials and methods",
)

SECTION_TITLE_WORD_KEYWORDS = (
    "experiment",
    "experiments",
    "experimental",
    "method",
    "methods",
    "methodology",
    "results",
    "evaluation",
    "benchmark",
    "benchmarks",
    "dataset",
    "datasets",
)

# Backward-compatible alias (phrase + word lists)
SECTION_TITLE_KEYWORDS = SECTION_TITLE_PHRASE_KEYWORDS + SECTION_TITLE_WORD_KEYWORDS

SECTION_KEYWORD_BODY_TERMS = (
    "benchmark",
    "metric",
    "metrics",
    "baseline",
    "baselines",
    "accuracy",
    "f1",
    "dataset",
    "datasets",
    "ablation",
    "evaluation",
    "experiment",
    "results",
)

SECTION_UNION_EXCLUDE_TITLES = (
    "introduction",
    "related work",
    "background",
    "abstract",
    "conclusion",
    "acknowledgment",
    "acknowledgement",
)

USE_EMBEDDING_RETRIEVAL = os.getenv("USE_EMBEDDING_RETRIEVAL", "").strip().lower() in {
    "1",
    "true",
    "yes",
}

# --- Retrieval 参数 ---

HYBRID_SECTION_TITLE_WEIGHT = 0.3
HYBRID_KEYWORD_WEIGHT = 0.35
HYBRID_EMBEDDING_WEIGHT = 0.35
RETRIEVAL_QUERY = "experiment dataset evaluation setup metrics baseline"
