"""Shared manifest loader for production batch runners.

Supports:
- list of paper_id strings
- list of {"paper_id": ...} dicts
- dict with "paper_ids" / "papers" list
- dict mapping paper_id -> meta (keys taken as ids)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _load_paper_ids(manifest_path: Path, limit: int | None) -> list[str]:
    if not manifest_path.exists():
        print(f"Error: manifest not found: {manifest_path}")
        sys.exit(1)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    ids: list[str] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("paper_id"):
                ids.append(str(item["paper_id"]))
            elif isinstance(item, str):
                ids.append(item)
            else:
                print(f"Warning: skipping unrecognised manifest entry: {item!r}")
    elif isinstance(data, dict):
        raw = data.get("paper_ids", data.get("papers", []))
        for item in raw:
            if isinstance(item, dict) and item.get("paper_id"):
                ids.append(str(item["paper_id"]))
            else:
                ids.append(str(item))
        if not ids:
            ids = [str(k) for k in data.keys()]
    if limit:
        ids = ids[:limit]
    return ids
