"""
v1_broadcast assignment baseline.

Every experiment receives a full copy of paper_datasets. No cooccurrence
logic. Used as a naive baseline to answer whether v1_cooccurrence actually
beats broadcast.
"""

from __future__ import annotations

from typing import Any

from .base import AssignStrategy


class AssignV1Broadcast(AssignStrategy):
    name = "v1_broadcast"

    def assign(
        self,
        paper_datasets: list[dict[str, Any]],
        experiments: list[dict[str, Any]],
        md_text: str,
        *,
        paper_id: str = "",
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for exp in experiments:
            out.append({**exp, "datasets": [dict(d) for d in paper_datasets],
                        "assignment_trace": {
                            "strategy": self.name,
                            "rule_hits": [
                                {"dataset": d.get("name"), "rule": "broadcast"}
                                for d in paper_datasets
                            ],
                            "fallback_used": "broadcast",
                            "broadcast_triggered": True,
                        }})
        return out
