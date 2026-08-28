"""Handoff manifest 读取 + md_url 懒缓存。

仅按本次 batch 的篇拉取 md，写入 ``pipeline_output/evaluation/md_cache/{paper_id}.md``。
**禁止**预下载 1325 篇到 ``data/md/``。已缓存的篇跳过网络请求。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from pipeline.evaluation.config import MD_CACHE_DIR


def load_handoff_batch(manifest_path: str | Path) -> list[dict[str, str]]:
    """读 handoff batch manifest → list of {"paper_id", "md_url"}.

    md_url 可缺（predictions-only 验证用 dev10 manifest 时可能无 md_url）。
    支持结构：
    - dict with "papers"/"paper_ids": [{"paper_id","md_url"}, ...]
    - list of {"paper_id":...} 或纯字符串
    """
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    papers: list[dict[str, str]] = []
    if isinstance(data, dict):
        raw = data.get("papers", data.get("paper_ids", []))
    elif isinstance(data, list):
        raw = data
    else:
        raw = []
    for item in raw:
        if isinstance(item, dict) and item.get("paper_id"):
            papers.append({
                "paper_id": str(item["paper_id"]),
                "md_url": str(item.get("md_url") or ""),
            })
        elif isinstance(item, str):
            papers.append({"paper_id": item, "md_url": ""})
    return papers


def ensure_cached(paper_id: str, md_url: str, cache_dir: Path | None = None) -> tuple[Path | None, str | None]:
    """确保 md 已缓存到 cache_dir/{paper_id}.md。

    Returns:
        (path, None) 成功；(None, err) 失败。
    """
    cache_dir = cache_dir or MD_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{paper_id}.md"
    if target.exists() and target.stat().st_size > 0:
        return target, None
    try:
        resp = requests.get(md_url, timeout=60)
        resp.raise_for_status()
        text = resp.text
        if not text.strip():
            return None, "empty md content"
        target.write_text(text, encoding="utf-8")
        return target, None
    except Exception as exc:  # noqa: BLE001 — 网络失败需记录而非中断整批
        return None, f"{type(exc).__name__}: {exc}"


def fetch_batch(
    papers: list[dict[str, str]],
    cache_dir: Path | None = None,
) -> tuple[dict[str, Path], dict[str, Any]]:
    """批量懒缓存。返回 (paper_id->path, stats)。

    stats: {total, cached, fetched, failed, failures:{paper_id: err}}
    """
    cache_dir = cache_dir or MD_CACHE_DIR
    resolved: dict[str, Path] = {}
    failures: dict[str, str] = {}
    skipped_no_url = 0
    fetched = 0
    cached = 0
    for p in papers:
        pid, url = p["paper_id"], p["md_url"]
        if not url:
            skipped_no_url += 1
            continue
        target = cache_dir / f"{pid}.md"
        already = target.exists() and target.stat().st_size > 0
        path, err = ensure_cached(pid, url, cache_dir)
        if path is not None:
            resolved[pid] = path
            if already:
                cached += 1
            else:
                fetched += 1
        else:
            failures[pid] = err or "unknown"
    stats = {
        "total": len(papers),
        "cached": cached,
        "fetched": fetched,
        "failed": len(failures),
        "skipped_no_url": skipped_no_url,
        "failures": failures,
    }
    return resolved, stats
