from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            default=lambda value: value.isoformat() if isinstance(value, datetime) else str(value),
        )
        + "\n",
        encoding="utf-8",
    )


def payload_degraded_reasons(payload: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    reason = str(payload.get("degraded_reason", "")).strip()
    if reason:
        reasons.append(reason)
    extra = payload.get("degraded_reasons")
    if isinstance(extra, list):
        for item in extra:
            text = str(item).strip()
            if text and text not in reasons:
                reasons.append(text)
    return reasons


# --- Structured summary helpers (used by feishu_cards and render_feishu_messages) ---

SUMMARY_SECTION_LABELS: dict[str, str] = {
    "research_problem": "研究问题",
    "research_challenge": "研究挑战",
    "research_method": "研究方法",
    "experimental_results": "实验效果",
}
SUMMARY_REQUIRED_KEYS = ("research_problem", "research_challenge", "research_method")
SUMMARY_OPTIONAL_KEYS = ("experimental_results",)
SUMMARY_ALL_KEYS = SUMMARY_REQUIRED_KEYS + SUMMARY_OPTIONAL_KEYS


def _clean_summary_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def normalize_structured_summary(value: Any) -> dict[str, str]:
    """Normalize a structured_summary dict from the API, silently dropping invalid entries."""
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for key in SUMMARY_ALL_KEYS:
        text = _clean_summary_text(value.get(key, ""))
        if text:
            normalized[key] = text
    return normalized
