"""Offline evaluation runner for Gold, Prediction, and Stage trace files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.config.settings import PROJECT_ROOT
from src.evaluation.metrics import compute_run_metrics
from src.evaluation.reporter import write_report
from src.evaluation.schemas import parse_stage_trace, read_experiment_array, write_json
from src.evaluation.scoring import DEFAULT_WEIGHTS, ScoreWeights
from src.evaluation.semantic import DEFAULT_SEMANTIC_MODEL, SemanticScorer

DEFAULT_SEMANTIC_CONFIG = {
    "type": "embedding",
    "model": DEFAULT_SEMANTIC_MODEL,
    "device": "cpu",
    "similarity": "cosine",
}
DEFAULT_SCORING_CONFIG = {
    "weights": {
        "accuracy": DEFAULT_WEIGHTS.accuracy,
        "latency": DEFAULT_WEIGHTS.latency,
        "token": DEFAULT_WEIGHTS.token,
    },
    "cost_score": {
        "formula": "min(1, reference/actual)",
        "missing_reference": "null_total_score",
    },
}


def _project_path(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else PROJECT_ROOT / value


def _paper_id_from_path(path: Path) -> str:
    return path.stem


def _relative_or_absolute(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def load_evaluation_records(
    *,
    batch: str,
    strategies: list[str],
    gold_dir: Path,
    prediction_dirs: dict[str, Path],
    trace_dirs: dict[str, Path],
    reference_trace_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Load records from the available file union without fabricating Gold."""
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    gold_files = {
        _paper_id_from_path(path): path
        for path in sorted(gold_dir.glob("*.json"))
        if gold_dir.exists()
    }
    gold_ids = set(gold_files)

    for strategy in strategies:
        prediction_dir = prediction_dirs[strategy]
        strategy_trace_dir = trace_dirs[strategy]
        prediction_ids = {
            _paper_id_from_path(path)
            for path in sorted(prediction_dir.glob("*.json"))
            if prediction_dir.exists()
        }
        trace_ids = {
            _paper_id_from_path(path)
            for path in sorted(strategy_trace_dir.glob("*.json"))
            if strategy_trace_dir.exists()
        }
        paper_ids = sorted(gold_ids | prediction_ids | trace_ids)
        if not paper_ids:
            failures.append(
                {
                    "paper_id": "",
                    "strategy": strategy,
                    "reason": (
                        "no gold, prediction, or trace files found for "
                        f"{strategy} in batch {batch}"
                    ),
                }
            )
            continue

        for paper_id in paper_ids:
            pred_path = prediction_dir / f"{paper_id}.json"
            stage_trace_path = strategy_trace_dir / f"{paper_id}.json"
            gold_path = gold_files.get(paper_id)

            if not stage_trace_path.exists():
                failures.append(
                    {
                        "paper_id": paper_id,
                        "strategy": strategy,
                        "reason": f"missing trace: {stage_trace_path}",
                    }
                )
                continue

            try:
                trace = parse_stage_trace(
                    stage_trace_path,
                    paper_id=paper_id,
                    strategy=strategy,
                )
            except ValueError as exc:
                failures.append(
                    {"paper_id": paper_id, "strategy": strategy, "reason": str(exc)}
                )
                continue

            if pred_path.exists():
                try:
                    pred_experiments = read_experiment_array(pred_path)
                except ValueError as exc:
                    failures.append(
                        {"paper_id": paper_id, "strategy": strategy, "reason": str(exc)}
                    )
                    pred_experiments = []
            else:
                failures.append(
                    {
                        "paper_id": paper_id,
                        "strategy": strategy,
                        "reason": f"missing prediction: {pred_path}",
                    }
                )
                pred_experiments = []

            if gold_path is None:
                gold_experiments = None
            else:
                try:
                    gold_experiments = read_experiment_array(gold_path)
                except ValueError as exc:
                    failures.append(
                        {"paper_id": paper_id, "strategy": strategy, "reason": str(exc)}
                    )
                    continue

            reference_trace = None
            if reference_trace_dir is not None:
                reference_path = reference_trace_dir / f"{paper_id}.json"
                if reference_path.exists():
                    try:
                        reference_trace = parse_stage_trace(
                            reference_path,
                            paper_id=paper_id,
                            strategy=f"gold_reference_{strategy}",
                        )
                    except ValueError as exc:
                        failures.append(
                            {
                                "paper_id": paper_id,
                                "strategy": strategy,
                                "reason": f"invalid reference trace: {exc}",
                            }
                        )

            records.append(
                {
                    "paper_id": paper_id,
                    "strategy": strategy,
                    "gold_experiments": gold_experiments,
                    "pred_experiments": pred_experiments,
                    "trace": trace,
                    "reference_trace": reference_trace,
                }
            )
    return records, failures


def _prediction_dir_for_strategy(
    *,
    strategy: str,
    batch: str,
    prediction_dir: str | Path | None,
    predictions_dir: str | Path,
) -> Path:
    if prediction_dir is not None:
        return _project_path(prediction_dir)
    return _project_path(predictions_dir) / batch / strategy


def _trace_dir_for_strategy(
    *,
    strategy: str,
    run_dir: Path,
    trace_dir: str | Path | None,
) -> Path:
    if trace_dir is not None:
        return _project_path(trace_dir)
    return run_dir / "traces" / strategy


def _run_dir(output_dir: str | Path, run_id: str | None) -> Path:
    output_root = _project_path(output_dir)
    return output_root / run_id if run_id else output_root


def _strategies_from_args(strategy: str | None, strategies: list[str] | None) -> list[str]:
    selected: list[str] = []
    if strategy:
        selected.append(strategy)
    if strategies:
        selected.extend(str(item) for item in strategies)
    deduped = list(dict.fromkeys(selected))
    if not deduped:
        raise ValueError("Provide --strategy or --strategies.")
    return deduped


def load_evaluation_config(config_path: str | Path | None) -> dict[str, Any]:
    """Load an optional JSON evaluation config."""
    if config_path is None:
        return {}
    path = _project_path(config_path)
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Evaluation config must be a JSON object: {path}")
    return payload


def _has_cli_strategies(strategy: str | None, strategies: list[str] | None) -> bool:
    return bool(strategy or strategies)


def _config_strategy_names(config: dict[str, Any]) -> list[str]:
    strategies = config.get("strategies") or {}
    if not isinstance(strategies, dict):
        raise ValueError("Config field 'strategies' must be an object.")
    return [str(strategy) for strategy in strategies]


def _config_strategy_dirs(
    config: dict[str, Any],
    field_name: str,
    selected_strategies: list[str],
) -> dict[str, str]:
    strategies = config.get("strategies") or {}
    if not isinstance(strategies, dict):
        return {}
    dirs: dict[str, str] = {}
    for strategy in selected_strategies:
        payload = strategies.get(strategy) or {}
        if isinstance(payload, dict) and payload.get(field_name):
            dirs[strategy] = str(payload[field_name])
    return dirs


def _semantic_config(
    config: dict[str, Any],
    *,
    semantic_type: str | None,
    semantic_model: str | None,
    semantic_device: str | None,
) -> dict[str, str | None]:
    effective = dict(DEFAULT_SEMANTIC_CONFIG)
    config_payload = config.get("semantic_scorer") or {}
    if isinstance(config_payload, dict):
        effective.update({k: v for k, v in config_payload.items() if v is not None})
    if semantic_type is not None:
        effective["type"] = semantic_type
    if semantic_model is not None:
        effective["model"] = semantic_model
    if semantic_device is not None:
        effective["device"] = semantic_device
    return effective


def _scoring_config(config: dict[str, Any]) -> dict[str, Any]:
    effective = json.loads(json.dumps(DEFAULT_SCORING_CONFIG))
    config_payload = config.get("scoring") or {}
    if isinstance(config_payload, dict):
        weights = config_payload.get("weights")
        if isinstance(weights, dict):
            effective["weights"].update(weights)
        cost_score = config_payload.get("cost_score")
        if isinstance(cost_score, dict):
            effective["cost_score"].update(cost_score)
    return effective


def _score_weights(config: dict[str, Any]) -> ScoreWeights:
    weights = config.get("weights") or {}
    return ScoreWeights(
        accuracy=float(weights.get("accuracy", DEFAULT_WEIGHTS.accuracy)),
        latency=float(weights.get("latency", DEFAULT_WEIGHTS.latency)),
        token=float(weights.get("token", DEFAULT_WEIGHTS.token)),
    )


def resolve_effective_config(
    *,
    config_path: str | Path | None = None,
    batch: str | None = None,
    strategy: str | None = None,
    strategies: list[str] | None = None,
    gold_dir: str | Path | None = None,
    predictions_dir: str | Path | None = None,
    prediction_dir: str | Path | None = None,
    trace_dir: str | Path | None = None,
    reference_trace_dir: str | Path | None = None,
    semantic_type: str | None = None,
    semantic_model: str | None = None,
    semantic_device: str | None = None,
    output_dir: str | Path | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Merge config and CLI-style overrides into run_evaluation kwargs."""
    config = load_evaluation_config(config_path)
    effective_batch = str(batch or config.get("batch") or "")
    if not effective_batch:
        raise ValueError("Provide --batch or config.batch.")

    if _has_cli_strategies(strategy, strategies):
        effective_strategies = _strategies_from_args(strategy, strategies)
    else:
        effective_strategies = _config_strategy_names(config)
        if not effective_strategies:
            raise ValueError("Provide --strategy/--strategies or config.strategies.")

    gold_set = dict(config.get("gold_set") or {})
    if gold_dir is not None:
        gold_set["path"] = str(gold_dir)
    if reference_trace_dir is not None:
        gold_set["reference_trace_dir"] = str(reference_trace_dir)
    if not gold_set.get("path"):
        gold_set["path"] = f"data/gold/{effective_batch}"
    if not gold_set.get("name"):
        gold_set["name"] = Path(str(gold_set["path"])).name
    if not gold_set.get("reference_trace_dir"):
        gold_set["reference_trace_dir"] = f"{gold_set['path']}/traces"

    semantic_config = _semantic_config(
        config,
        semantic_type=semantic_type,
        semantic_model=semantic_model,
        semantic_device=semantic_device,
    )
    scoring_config = _scoring_config(config)

    return {
        "config_path": str(config_path) if config_path is not None else None,
        "batch": effective_batch,
        "strategies": effective_strategies,
        "gold_dir": gold_set["path"],
        "reference_trace_dir": gold_set.get("reference_trace_dir"),
        "output_dir": output_dir or config.get("output_dir") or "output/runs/eval",
        "run_id": run_id if run_id is not None else config.get("run_id"),
        "predictions_dir": predictions_dir or "data/predictions",
        "prediction_dir": prediction_dir,
        "trace_dir": trace_dir,
        "strategy_prediction_dirs": _config_strategy_dirs(
            config,
            "prediction_dir",
            effective_strategies,
        ),
        "strategy_trace_dirs": _config_strategy_dirs(
            config,
            "trace_dir",
            effective_strategies,
        ),
        "manifest": config.get("manifest"),
        "gold_set": gold_set,
        "semantic_scorer_config": semantic_config,
        "scoring_config": scoring_config,
        "config_name": config.get("name"),
    }


def _needs_semantic_scorer(records: list[dict[str, Any]]) -> bool:
    return any(record.get("gold_experiments") is not None for record in records)


def run_evaluation(
    *,
    batch: str,
    strategies: list[str],
    gold_dir: str | Path,
    output_dir: str | Path,
    run_id: str | None = None,
    predictions_dir: str | Path = "data/predictions",
    prediction_dir: str | Path | None = None,
    trace_dir: str | Path | None = None,
    reference_trace_dir: str | Path | None = None,
    strategy_prediction_dirs: dict[str, str | Path] | None = None,
    strategy_trace_dirs: dict[str, str | Path] | None = None,
    manifest: str | Path | None = None,
    gold_set: dict[str, Any] | None = None,
    semantic_scorer_config: dict[str, Any] | None = None,
    scoring_config: dict[str, Any] | None = None,
    config_name: str | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run offline evaluation and write metrics artifacts."""
    if prediction_dir is not None and len(strategies) != 1:
        raise ValueError("--prediction-dir can only be used with one strategy.")
    if trace_dir is not None and len(strategies) != 1:
        raise ValueError("--trace-dir can only be used with one strategy.")

    run_dir = _run_dir(output_dir, run_id)
    strategy_prediction_dirs = strategy_prediction_dirs or {}
    strategy_trace_dirs = strategy_trace_dirs or {}
    prediction_dirs = {
        strategy: (
            _project_path(strategy_prediction_dirs[strategy])
            if prediction_dir is None and strategy in strategy_prediction_dirs
            else _prediction_dir_for_strategy(
                strategy=strategy,
                batch=batch,
                prediction_dir=prediction_dir,
                predictions_dir=predictions_dir,
            )
        )
        for strategy in strategies
    }
    trace_dirs = {
        strategy: (
            _project_path(strategy_trace_dirs[strategy])
            if trace_dir is None and strategy in strategy_trace_dirs
            else _trace_dir_for_strategy(
                strategy=strategy,
                run_dir=run_dir,
                trace_dir=trace_dir,
            )
        )
        for strategy in strategies
    }

    effective_gold_set = dict(gold_set or {})
    effective_gold_set["path"] = str(gold_dir)
    if reference_trace_dir is not None:
        effective_gold_set["reference_trace_dir"] = str(reference_trace_dir)
    elif not effective_gold_set.get("reference_trace_dir"):
        effective_gold_set["reference_trace_dir"] = f"{gold_dir}/traces"
    if not effective_gold_set.get("name"):
        effective_gold_set["name"] = Path(str(gold_dir)).name
    effective_gold_set.setdefault("reference_cost_source", "dataset_fixed")

    resolved_reference_trace_dir = effective_gold_set.get("reference_trace_dir")
    reference_trace_path = (
        _project_path(resolved_reference_trace_dir) if resolved_reference_trace_dir else None
    )
    semantic_config = dict(semantic_scorer_config or DEFAULT_SEMANTIC_CONFIG)
    scoring_effective = dict(scoring_config or DEFAULT_SCORING_CONFIG)
    effective_config = {
        "config_path": str(config_path) if config_path is not None else None,
        "name": config_name,
        "batch": batch,
        "strategies": strategies,
        "manifest": str(manifest) if manifest is not None else None,
        "gold_set": effective_gold_set,
        "semantic_scorer": semantic_config,
        "scoring": scoring_effective,
        "prediction_dirs": {
            strategy: _relative_or_absolute(path)
            for strategy, path in prediction_dirs.items()
        },
        "trace_dirs": {
            strategy: _relative_or_absolute(path)
            for strategy, path in trace_dirs.items()
        },
        "output_dir": _relative_or_absolute(run_dir),
        "run_id": run_id or run_dir.name,
    }
    records, failures = load_evaluation_records(
        batch=batch,
        strategies=strategies,
        gold_dir=_project_path(gold_dir),
        prediction_dirs=prediction_dirs,
        trace_dirs=trace_dirs,
        reference_trace_dir=reference_trace_path,
    )
    semantic_scorer = (
        SemanticScorer(**semantic_config) if _needs_semantic_scorer(records) else None
    )
    weights = _score_weights(scoring_effective)
    metrics = compute_run_metrics(records, semantic_scorer=semantic_scorer, weights=weights)
    write_json(run_dir / "per_paper_metrics.json", metrics["per_paper_metrics"])
    write_json(run_dir / "per_strategy_metrics.json", metrics["per_strategy_metrics"])
    write_json(run_dir / "global_metrics.json", metrics["global_metrics"])
    write_json(run_dir / "failures.json", failures)
    write_json(run_dir / "run_config.json", effective_config)
    report_path = write_report(
        run_dir,
        metrics,
        run_id=run_id or run_dir.name,
        batch=batch,
        strategies=strategies,
        failures=failures,
    )

    return {
        "ok": not failures and bool(records),
        "run_id": run_id or run_dir.name,
        "batch": batch,
        "strategies": strategies,
        "completed_count": len(records),
        "failed_count": len(failures),
        "output_dir": _relative_or_absolute(run_dir),
        "report_path": _relative_or_absolute(report_path),
        "run_config_path": _relative_or_absolute(run_dir / "run_config.json"),
    }


def run_evaluation_batch(
    fixtures_manifest: str,
    gold_dir: str,
    strategies: list,
    output_dir: str,
) -> dict:
    """Backward-compatible wrapper for the older skeleton function."""
    return run_evaluation(
        batch="unknown",
        strategies=[str(strategy) for strategy in strategies],
        gold_dir=gold_dir,
        predictions_dir="data/predictions",
        output_dir=Path(output_dir) / "manual",
        semantic_scorer_config={"type": "jaccard", "model": DEFAULT_SEMANTIC_MODEL, "device": "cpu", "similarity": "cosine"},
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline evaluation metrics.")
    parser.add_argument("--config", default=None, help="Optional JSON evaluation config path.")
    parser.add_argument("--batch", default=None, help="Batch name, e.g. dev_10.")
    parser.add_argument("--run-id", default=None, help="Optional evaluation run ID.")
    parser.add_argument("--strategy", default=None, help="Single strategy name.")
    parser.add_argument("--strategies", nargs="+", default=None, help="Strategy names.")
    parser.add_argument("--gold-dir", default=None, help="Defaults to data/gold/{batch}.")
    parser.add_argument("--reference-trace-dir", default=None, help="Gold reference trace directory.")
    parser.add_argument("--predictions-dir", default=None, help="Prediction root directory.")
    parser.add_argument("--prediction-dir", default=None, help="Single-strategy prediction directory.")
    parser.add_argument("--trace-dir", default=None, help="Single-strategy trace directory.")
    parser.add_argument("--output-dir", default=None, help="Evaluation output directory.")
    parser.add_argument("--semantic-model", default=None, help="Semantic model name or path.")
    parser.add_argument("--semantic-device", default=None, help="Semantic model device, e.g. cpu.")
    parser.add_argument("--semantic-type", choices=["embedding", "jaccard"], default=None, help="Semantic scorer type.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_kwargs = resolve_effective_config(
        config_path=args.config,
        batch=args.batch,
        strategy=args.strategy,
        strategies=args.strategies,
        gold_dir=args.gold_dir,
        predictions_dir=args.predictions_dir,
        prediction_dir=args.prediction_dir,
        trace_dir=args.trace_dir,
        reference_trace_dir=args.reference_trace_dir,
        semantic_type=args.semantic_type,
        semantic_model=args.semantic_model,
        semantic_device=args.semantic_device,
        output_dir=args.output_dir,
        run_id=args.run_id,
    )
    result = run_evaluation(**run_kwargs)
    print(result)


if __name__ == "__main__":
    main()

