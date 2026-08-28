"""
Abstract interface and orchestration entry for per-experiment dataset assignment.

Boundary:
    strategies/   : (md_text, paper_id) -> paper_datasets[]      (unchanged, paper-level)
    assignment/   : (paper_datasets, experiments[], md_text)
                   -> experiments_with_datasets[]                (post-processing)

`experiments` passed in MUST already have their `datasets` field stripped by
the caller (see test_runner.load_gold_experiments_stripped) so the assignment
strategy cannot cheat by reading gold datasets.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AssignStrategy(ABC):
    """Abstract per-experiment assignment strategy."""

    name: str = "base"

    @abstractmethod
    def assign(
        self,
        paper_datasets: list[dict[str, Any]],
        experiments: list[dict[str, Any]],
        md_text: str,
        *,
        paper_id: str = "",
    ) -> list[dict[str, Any]]:
        """Assign paper-level datasets to individual experiments.

        Args:
            paper_datasets: datasets extracted at paper level (from v4.3 etc.)
            experiments: gold experiments with `datasets` already stripped;
                each carries experiment_name / method / key_results / evidence
                / experiment_type / experiment_subject for cooccurrence.
            md_text: full paper markdown (for mention-window matching).
            paper_id: for trace tagging.

        Returns:
            A list (same order as `experiments`) where each experiment dict is
            copied and augmented with:
              - `datasets`: list[dict] assigned to this experiment
              - `assignment_trace`: dict with rule hits / fallback flags
        """
        raise NotImplementedError


def run_assignment(
    strategy: AssignStrategy,
    paper_datasets: list[dict[str, Any]],
    experiments: list[dict[str, Any]],
    md_text: str,
    *,
    paper_id: str = "",
) -> list[dict[str, Any]]:
    """Thin orchestrator: invoke a strategy's assign() with timing trace.

    Keeps the call site in test_runner uniform across strategies and records
    wall-clock time so runs/ traces can compare assignment cost vs extraction.
    """
    import time

    t0 = time.perf_counter()
    out = strategy.assign(paper_datasets, experiments, md_text, paper_id=paper_id)
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    # Annotate each experiment's trace with timing if the strategy did not.
    for exp in out:
        tr = exp.get("assignment_trace") or {}
        if "assign_ms" not in tr:
            tr["assign_ms"] = elapsed_ms
            tr["strategy"] = strategy.name
            exp["assignment_trace"] = tr
    return out
