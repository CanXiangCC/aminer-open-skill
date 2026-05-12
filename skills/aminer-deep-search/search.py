from __future__ import annotations

import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable, Sequence

import requests


AMINER_SEARCH_URL = "https://datacenter.aminer.cn/gateway/api/v3/paper/search/paper/SearchPro"
AMINER_PAPER_DETAIL_URL = "https://datacenter.aminer.cn/gateway/api/v3/paper/detail/batch"


def get_aminer_key() -> str:
    aminer_key = os.getenv("AMINER_API_KEY") or os.getenv("AMINER_KEY")
    if not aminer_key:
        raise ValueError("AMINER_API_KEY is required for AMiner API calls.")
    return aminer_key


def _auth_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json;charset=utf-8",
        "Authorization": f"Bearer {get_aminer_key()}",
    }


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = str(item).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def _chunks(items: Sequence[Any], chunk_size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(items), chunk_size):
        yield items[index : index + chunk_size]


def _extract_paper_id(detail: Any) -> str:
    if isinstance(detail, dict):
        return str(detail.get("id") or detail.get("_id") or "")
    if detail is None:
        return ""
    return str(detail)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_authors(authors: Any) -> list[str]:
    if not isinstance(authors, list):
        return []
    normalized: list[str] = []
    for author in authors:
        if isinstance(author, dict):
            name = author.get("name") or author.get("name_zh")
        else:
            name = str(author)
        if name:
            normalized.append(str(name))
    return normalized


def normalize_paper_detail(detail: dict[str, Any], *, query: str = "") -> dict[str, Any]:
    venue = detail.get("venue")
    if isinstance(venue, dict):
        venue_text = venue.get("raw") or venue.get("name") or ""
    else:
        venue_text = venue or detail.get("venue_name") or ""

    orgs = detail.get("orgs") or detail.get("organizations") or detail.get("affiliations") or []
    if isinstance(orgs, str):
        organizations = [orgs]
    elif isinstance(orgs, list):
        organizations = [str(org) for org in orgs if org]
    else:
        organizations = []

    normalized = dict(detail)
    normalized["id"] = _extract_paper_id(detail)
    normalized["title"] = detail.get("title") or detail.get("title_zh") or ""
    normalized["abstract"] = detail.get("abstract") or detail.get("abstract_zh") or ""
    normalized["authors"] = _normalize_authors(detail.get("authors"))
    normalized["organization"] = organizations
    normalized["venue"] = str(venue_text)
    normalized["year"] = detail.get("year")
    normalized["n_citation"] = _safe_int(detail.get("n_citation") or detail.get("num_citation"), 0)
    normalized["keywords"] = detail.get("keywords") or []
    normalized["score"] = round(rule_based_score(normalized, query=query), 4)
    return normalized


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{1,}", text.lower())


def rule_based_score(paper: dict[str, Any], *, query: str = "") -> float:
    query_tokens = set(_tokenize(query))
    title = str(paper.get("title") or "")
    abstract = str(paper.get("abstract") or "")
    keywords = " ".join(str(item) for item in paper.get("keywords") or [])
    haystack = f"{title} {abstract} {keywords}"
    haystack_tokens = set(_tokenize(haystack))

    lexical = 0.0
    if query_tokens:
        lexical = len(query_tokens & haystack_tokens) / max(1, len(query_tokens))

    phrase_bonus = 0.2 if query and query.lower() in haystack.lower() else 0.0
    citation_score = min(0.3, math.log1p(_safe_int(paper.get("n_citation"), 0)) / 30.0)
    year = _safe_int(paper.get("year"), 0)
    recency_score = 0.1 if year >= 2020 else 0.05 if year >= 2015 else 0.0
    return min(1.0, lexical * 0.55 + phrase_bonus + citation_score + recency_score)


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


def _request_paper_detail_batch(paper_ids: Sequence[str]) -> list[dict[str, Any]]:
    ids = _dedupe_preserve_order(paper_ids)
    if not ids:
        return []
    try:
        response = requests.post(
            AMINER_PAPER_DETAIL_URL,
            json={"ids": ids},
            headers=_auth_headers(),
            timeout=(10, 30),
        )
        if response.status_code != 200:
            print(f"AMiner detail request failed: status={response.status_code}, detail={response.text[:300]}")
            return []
        data = response.json().get("data", [])
    except (requests.RequestException, ValueError) as exc:
        print(f"AMiner detail request failed: {exc}")
        return []

    if isinstance(data, dict):
        data = data.get("data") or data.get("items") or []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def aminer_get_paper_info_batch(
    paper_ids: Sequence[str],
    detail_batch_size: int = 50,
    max_workers: int = 8,
) -> list[dict[str, Any]]:
    ids = _dedupe_preserve_order(paper_ids)
    if not ids:
        return []
    batches = list(_chunks(ids, max(1, int(detail_batch_size))))
    if len(batches) == 1:
        return _request_paper_detail_batch(batches[0])

    results_by_index: dict[int, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(batches)))) as executor:
        future_to_index = {
            executor.submit(_request_paper_detail_batch, batch): index
            for index, batch in enumerate(batches)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                results_by_index[index] = future.result()
            except Exception as exc:
                print(f"Failed to fetch AMiner detail batch: {exc}")
                results_by_index[index] = []

    details: list[dict[str, Any]] = []
    for index in range(len(batches)):
        details.extend(results_by_index.get(index, []))
    return details


def search_papers(query: str, *, size: int = 20, year: int | None = None) -> list[dict[str, Any]]:
    size = max(1, min(int(size), 20))
    raw_items = aminer_pro_search(query, use_topic=True, year=year, size=size, offset=0)
    if not raw_items:
        return []

    ids = _dedupe_preserve_order(_extract_paper_id(item) for item in raw_items)
    details_by_id = {
        _extract_paper_id(detail): detail
        for detail in aminer_get_paper_info_batch(ids)
        if _extract_paper_id(detail)
    }

    papers: list[dict[str, Any]] = []
    for raw in raw_items:
        paper_id = _extract_paper_id(raw)
        merged = dict(raw)
        if paper_id in details_by_id:
            merged.update(details_by_id[paper_id])
        normalized = normalize_paper_detail(merged, query=query)
        if normalized["id"] and normalized["title"]:
            papers.append(normalized)

    papers.sort(key=lambda item: (float(item.get("score", 0.0)), _safe_int(item.get("n_citation"), 0)), reverse=True)
    return papers[:size]


def search_adding(
    keyword_list: Sequence[str],
    topic: str,
    total_paper_details: Sequence[Any] | None = None,
    **_: Any,
) -> list[dict[str, Any]]:
    existing_ids = {
        _extract_paper_id(item)
        for item in (total_paper_details or [])
        if _extract_paper_id(item)
    }
    papers: list[dict[str, Any]] = []
    seen = set(existing_ids)
    for keyword in keyword_list:
        for paper in search_papers(str(keyword), size=20):
            paper_id = _extract_paper_id(paper)
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
