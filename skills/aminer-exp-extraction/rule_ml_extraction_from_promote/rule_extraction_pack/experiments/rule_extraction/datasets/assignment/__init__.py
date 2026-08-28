"""
Datasets per-experiment assignment.

Two-stage pipeline:
    strategies/   : (md_text, paper_id) -> paper_datasets[]
    assignment/   : (paper_datasets, experiments[], md_text) -> experiments_with_datasets[]

Strategies registry mirrors test_runner.STRATEGIES so the runner can dispatch
by string id.
"""

from __future__ import annotations

from .base import AssignStrategy, run_assignment
from .v1_cooccurrence import AssignV1Cooccurrence
from .v1_broadcast import AssignV1Broadcast
from .v2_type_aware import AssignV2TypeAware

ASSIGN_STRATEGIES = {
    "v1_cooccurrence": AssignV1Cooccurrence,
    "v1_broadcast": AssignV1Broadcast,
    "v2_type_aware": AssignV2TypeAware,
}

ASSIGN_STRATEGY_NAMES = {
    "v1_cooccurrence": "assignment--v1--共现匹配 (dataset 提及 ±400 字符窗口 + experiment_type 约束)",
    "v1_broadcast": "assignment--v1--broadcast 对照基线 (每 experiment 复制 paper_datasets)",
    "v2_type_aware": "assignment--v2--类型感知 [当前最优] (field_study 强屏蔽 + ablation 继承主实验 + section 路由)",
}

__all__ = [
    "AssignStrategy",
    "run_assignment",
    "ASSIGN_STRATEGIES",
    "ASSIGN_STRATEGY_NAMES",
]
