from __future__ import annotations

import json
from typing import Any, Sequence

import requests

from _utils import (
    aminer_get_paper_info_batch,
    dedupe_preserve_order,
    extract_paper_id,
    get_aminer_key,
    normalize_paper_detail,
    rule_based_score,
    safe_int,
)


AMINER_SEARCH_URL = "https://datacenter.aminer.cn/gateway/api/v3/paper/search/paper/SearchPro"


def _auth_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json;charset=utf-8",
        "Authorization": f"Bearer {get_aminer_key()}",
    }


def _extract_search_items(response_json: dict[str, Any]) -> list[dict[str, Any]]:
    data = response_json.get("data", [])
    if isinstance(data, dict):
        data = data.get("data") or data.get("items") or data.get("results") or []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def aminer_pro_search(
    query: str,
    use_topic: bool = True,
    year: int | None = None,
    size: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "use_topic": use_topic,
        "query": query,
        "size": max(1, min(int(size), 100)),
        "offset": max(0, int(offset)),
        "end_year": int(year or 2026),
    }
    try:
        response = requests.post(
            AMINER_SEARCH_URL,
            headers=_auth_headers(),
            data=json.dumps(payload),
            timeout=(10, 30),
        )
        if response.status_code != 200:
            print(f"AMiner search failed: status={response.status_code}, detail={response.text[:300]}")
            return []
        return _extract_search_items(response.json())
    except (requests.RequestException, ValueError) as exc:
        print(f"AMiner search failed for query `{query}`: {exc}")
        return []


def search_papers(query: str, *, size: int = 20, year: int | None = None) -> list[dict[str, Any]]:
    size = max(1, min(int(size), 20))
    raw_items = aminer_pro_search(query, use_topic=True, year=year, size=size, offset=0)
    if not raw_items:
        return []

    ids = dedupe_preserve_order(extract_paper_id(item) for item in raw_items)
    details_by_id = {
        extract_paper_id(detail): detail
        for detail in aminer_get_paper_info_batch(ids)
        if extract_paper_id(detail)
    }

    papers: list[dict[str, Any]] = []
    for raw in raw_items:
        paper_id = extract_paper_id(raw)
        merged = dict(raw)
        if paper_id in details_by_id:
            merged.update(details_by_id[paper_id])
        normalized = normalize_paper_detail(merged, query=query)
        if normalized["id"] and normalized["title"]:
            papers.append(normalized)

    papers.sort(key=lambda item: (float(item.get("score", 0.0)), safe_int(item.get("n_citation"), 0)), reverse=True)
    return papers[:size]


def search_adding(
    keyword_list: Sequence[str],
    topic: str,
    total_paper_details: Sequence[Any] | None = None,
    **_: Any,
) -> list[dict[str, Any]]:
    existing_ids = {
        extract_paper_id(item)
        for item in (total_paper_details or [])
        if extract_paper_id(item)
    }
    papers: list[dict[str, Any]] = []
    seen = set(existing_ids)
    for keyword in keyword_list:
        for paper in search_papers(str(keyword), size=20):
            paper_id = extract_paper_id(paper)
            if not paper_id or paper_id in seen:
                continue
            paper["topic"] = topic
            seen.add(paper_id)
            papers.append(paper)
    return papers


keywords_adding = search_adding


__all__ = [
    "aminer_get_paper_info_batch",
    "aminer_pro_search",
    "get_aminer_key",
    "keywords_adding",
    "normalize_paper_detail",
    "rule_based_score",
    "search_adding",
    "search_papers",
]
