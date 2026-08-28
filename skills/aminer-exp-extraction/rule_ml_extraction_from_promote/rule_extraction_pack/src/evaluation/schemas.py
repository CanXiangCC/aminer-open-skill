"""Data structures and JSON helpers for evaluation inputs and reports."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TypedDict

DOMAIN_VALUES = {
    "computer_science",
    "medicine",
    "biology",
    "chemistry",
    "physics",
    "materials",
    "engineering",
    "economics",
    "education",
    "energy",
    "environment",
    "social_science",
    "other",
}
EXPERIMENT_TYPE_VALUES = {
    "benchmark",
    "comparison",
    "ablation",
    "simulation",
    "survey",
    "human_study",
    "field_study",
    "lab_experiment",
    "clinical_trial",
    "case_study",
    "empirical_study",
    "data_analysis",
    "other",
}
DATASET_TYPE_VALUES = {
    "text",
    "image",
    "video",
    "audio",
    "multimodal",
    "tabular",
    "timeseries",
    "sensor",
    "medical",
    "biological",
    "chemical",
    "material",
    "simulation",
    "industrial",
    "other",
}
EXPERIMENT_DEFAULTS: dict[str, Any] = {
    "_id": None,
    "paper_id": "",
    "experiment_name": "",
    "research_problem": "",
    "research_goal": "",
    "experiment_subject": [],
    "method": "",
    "datasets": [],
    "sample_size": None,
    "metrics": [],
    "key_results": [],
    "conclusion": "",
    "limitations": "",
    "evidence": [],
    "domain": "other",
    "experiment_type": "other",
    "experiment_history": [],
    "score": 0.0,
}
DATASET_DEFAULTS: dict[str, Any] = {
    "name": "",
    "aliases": [],
    "dataset_type": "other",
    "description": "",
    "sample_size": None,
    "is_public": None,
    "is_self_collected": None,
    "urls": [],
    "github_urls": [],
    "doi_list": [],
    "cstr_list": [],
}
EXPERIMENT_LIST_FIELDS = {
    "experiment_subject",
    "datasets",
    "metrics",
    "key_results",
    "evidence",
    "experiment_history",
}
DATASET_LIST_FIELDS = {"aliases", "urls", "github_urls", "doi_list", "cstr_list"}
OLD_EXPERIMENT_FIELDS = {"dataset", "baselines", "setup"}


class DatasetDict(TypedDict, total=False):
    """Dataset object in the authoritative experiment schema."""

    name: str
    aliases: list[str]
    dataset_type: str
    description: str
    sample_size: float | int | None
    is_public: bool | None
    is_self_collected: bool | None
    urls: list[str]
    github_urls: list[str]
    doi_list: list[str]
    cstr_list: list[str]


class ExperimentDict(TypedDict, total=False):
    """Experiment object used by Gold and Prediction files."""

    _id: str | None
    paper_id: str
    experiment_name: str
    research_problem: str
    research_goal: str
    experiment_subject: list[str]
    method: str
    datasets: list[DatasetDict]
    sample_size: float | int | None
    metrics: list[str]
    key_results: list[str]
    conclusion: str
    limitations: str
    evidence: list[str]
    domain: str
    experiment_type: str
    experiment_history: list[str]
    score: float


@dataclass
class LatencyTrace:
    """Per-paper latency trace, in milliseconds."""

    load: float = 0.0
    chunk: float = 0.0
    process: float = 0.0
    llm: float = 0.0
    total: float = 0.0

    def normalized(self) -> "LatencyTrace":
        total = self.total if self.total else self.load + self.chunk + self.process + self.llm
        return LatencyTrace(
            load=self.load,
            chunk=self.chunk,
            process=self.process,
            llm=self.llm,
            total=total,
        )


@dataclass
class TokenTrace:
    """Per-paper token usage trace."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    llm_call_count: int = 0

    def normalized(self) -> "TokenTrace":
        total = self.total_tokens if self.total_tokens else self.input_tokens + self.output_tokens
        return TokenTrace(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            total_tokens=total,
            llm_call_count=self.llm_call_count,
        )


@dataclass
class StageTrace:
    """Per-paper strategy trace used for latency and token metrics."""

    paper_id: str
    strategy: str
    model: str = ""
    status: str = ""
    prediction_path: str = ""
    error: str | None = None
    latency_ms: LatencyTrace = field(default_factory=LatencyTrace)
    tokens: TokenTrace = field(default_factory=TokenTrace)


@dataclass
class PaperMetrics:
    """Per-paper per-strategy evaluation metrics."""

    paper_id: str
    strategy: str
    gold_status: str = "available"
    accuracy_available: bool = True
    paper_accuracy: float | None = 0.0
    accuracy_score: float | None = 0.0
    domain_score: float | None = None
    datasets_score: float | None = None
    metrics_score: float | None = None
    key_results_score: float | None = None
    exp_semantic_score: float | None = None
    latency_total_ms: float = 0.0
    reference_latency_total_ms: float | None = None
    latency_ratio: float | None = None
    latency_score: float | None = None
    total_tokens: int = 0
    reference_total_tokens: int | None = None
    token_ratio: float | None = None
    token_score: float | None = None
    reference_cost_available: bool = False
    total_score: float | None = 0.0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyMetrics:
    """Aggregated metrics for one strategy."""

    strategy: str
    paper_count: int = 0
    accuracy_available_count: int = 0
    accuracy_unavailable_count: int = 0
    accuracy_score: float | None = 0.0
    reference_cost_available_count: int = 0
    reference_cost_unavailable_count: int = 0
    latency_score: float | None = None
    token_score: float | None = None
    total_score: float | None = 0.0
    latency_mean_ms: float = 0.0
    latency_sum_ms: float = 0.0
    reference_latency_mean_ms: float | None = None
    latency_ratio_mean: float | None = None
    token_mean: float = 0.0
    token_sum: int = 0
    reference_token_mean: float | None = None
    token_ratio_mean: float | None = None


@dataclass
class GlobalMetrics:
    """Global metrics across selected strategies."""

    strategy_count: int = 0
    paper_metric_count: int = 0
    accuracy_available_count: int = 0
    accuracy_unavailable_count: int = 0
    reference_cost_available_count: int = 0
    reference_cost_unavailable_count: int = 0
    total_score: float | None = 0.0


def dataclass_to_dict(value: Any) -> dict[str, Any]:
    """Convert a dataclass value to a plain JSON-serializable dict."""
    return asdict(value)


def read_json(path: str | Path) -> Any:
    """Read JSON from a path using UTF-8."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any) -> None:
    """Write JSON to a path using UTF-8 and stable formatting."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _string(value: Any) -> str:
    return "" if value is None else str(value)


def _sample_size(value: Any) -> float | int | None:
    return value if isinstance(value, (int, float)) and value >= 0 else None


def _score(value: Any) -> float:
    if not isinstance(value, (int, float)):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def normalize_dataset(dataset: Any) -> DatasetDict:
    """Normalize one dataset object to the authoritative dataset fields."""
    if isinstance(dataset, str):
        payload: dict[str, Any] = DATASET_DEFAULTS.copy()
        payload["name"] = dataset
    elif isinstance(dataset, dict):
        payload = DATASET_DEFAULTS.copy()
        for key in DATASET_DEFAULTS:
            if key in dataset:
                payload[key] = dataset[key]
    else:
        payload = DATASET_DEFAULTS.copy()

    payload["name"] = _string(payload.get("name"))
    payload["description"] = _string(payload.get("description"))
    payload["sample_size"] = _sample_size(payload.get("sample_size"))
    for key in DATASET_LIST_FIELDS:
        payload[key] = [_string(item) for item in _list(payload.get(key)) if item is not None]
    if payload.get("dataset_type") not in DATASET_TYPE_VALUES:
        payload["dataset_type"] = "other"
    if not isinstance(payload.get("is_public"), bool):
        payload["is_public"] = None
    if not isinstance(payload.get("is_self_collected"), bool):
        payload["is_self_collected"] = None
    return payload


def normalize_experiment(experiment: Any, paper_id: str) -> ExperimentDict:
    """Normalize one experiment object to the authoritative experiment fields."""
    source = experiment if isinstance(experiment, dict) else {}
    payload = EXPERIMENT_DEFAULTS.copy()
    for key in EXPERIMENT_DEFAULTS:
        if key in source:
            payload[key] = source[key]
    for old_field in OLD_EXPERIMENT_FIELDS:
        payload.pop(old_field, None)

    payload["paper_id"] = paper_id or _string(payload.get("paper_id"))
    payload["_id"] = payload.get("_id") if payload.get("_id") is None else _string(payload.get("_id"))
    for key in (
        "experiment_name",
        "research_problem",
        "research_goal",
        "method",
        "conclusion",
        "limitations",
    ):
        payload[key] = _string(payload.get(key))
    for key in EXPERIMENT_LIST_FIELDS:
        payload[key] = _list(payload.get(key))
    payload["experiment_subject"] = [_string(item) for item in payload["experiment_subject"] if item is not None]
    payload["metrics"] = [_string(item) for item in payload["metrics"] if item is not None]
    payload["key_results"] = [_string(item) for item in payload["key_results"] if item is not None]
    payload["evidence"] = [_string(item) for item in payload["evidence"] if item is not None]
    payload["experiment_history"] = [_string(item) for item in payload["experiment_history"] if item is not None]
    payload["datasets"] = [normalize_dataset(item) for item in payload["datasets"]]
    payload["sample_size"] = _sample_size(payload.get("sample_size"))
    payload["domain"] = payload["domain"] if payload.get("domain") in DOMAIN_VALUES else "other"
    payload["experiment_type"] = (
        payload["experiment_type"]
        if payload.get("experiment_type") in EXPERIMENT_TYPE_VALUES
        else "other"
    )
    payload["score"] = _score(payload.get("score"))
    return payload


def normalize_experiment_array(payload: Any, paper_id: str) -> list[ExperimentDict]:
    """Validate the top-level experiment array and normalize each experiment."""
    if not isinstance(payload, list):
        raise ValueError("Top-level JSON must be an experiment object array.")
    if not all(isinstance(item, dict) for item in payload):
        raise ValueError("Experiment array contains non-object entries.")
    return [normalize_experiment(item, paper_id) for item in payload]


def read_experiment_array(path: str | Path) -> list[ExperimentDict]:
    """Read a Gold or Prediction file whose top level must be an experiment array."""
    payload = read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected top-level experiment array: {path}")
    if not all(isinstance(item, dict) for item in payload):
        raise ValueError(f"Experiment array contains non-object entries: {path}")
    return payload


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _integer(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def parse_stage_trace(path: str | Path, *, paper_id: str, strategy: str) -> StageTrace:
    """Read a stage trace file and normalize missing latency/token totals."""
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected trace object: {path}")

    latency_payload = payload.get("latency_ms") or {}
    token_payload = payload.get("tokens") or {}
    if not isinstance(latency_payload, dict):
        latency_payload = {}
    if not isinstance(token_payload, dict):
        token_payload = {}

    latency = LatencyTrace(
        load=_number(latency_payload.get("load")),
        chunk=_number(latency_payload.get("chunk")),
        process=_number(latency_payload.get("process")),
        llm=_number(latency_payload.get("llm")),
        total=_number(latency_payload.get("total")),
    ).normalized()
    tokens = TokenTrace(
        input_tokens=_integer(token_payload.get("input_tokens")),
        output_tokens=_integer(token_payload.get("output_tokens")),
        total_tokens=_integer(token_payload.get("total_tokens")),
        llm_call_count=_integer(token_payload.get("llm_call_count")),
    ).normalized()

    return StageTrace(
        paper_id=str(payload.get("paper_id") or paper_id),
        strategy=str(payload.get("strategy") or strategy),
        model=str(payload.get("model") or ""),
        status=str(payload.get("status") or ""),
        prediction_path=str(payload.get("prediction_path") or ""),
        error=payload.get("error") if payload.get("error") is None else str(payload.get("error")),
        latency_ms=latency,
        tokens=tokens,
    )

