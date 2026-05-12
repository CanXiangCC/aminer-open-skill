from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable, Sequence

import requests

from search import (
    aminer_get_paper_info_batch,
    get_aminer_key,
    normalize_paper_detail,
    rule_based_score,
)


AMINER_CITATION_URL = "https://datacenter.aminer.cn/gateway/api/v3/paper/pub_relation"


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_aminer_key()}"}


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


def _extract_paper_id(detail: Any) -> str:
    if isinstance(detail, dict):
        return str(detail.get("id") or detail.get("_id") or "")
    if detail is None:
        return ""
    return str(detail)


def _fetch_pub_relation(params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            AMINER_CITATION_URL,
            params=params,
            headers=_auth_headers(),
            timeout=(10, 30),
        )
        if response.status_code != 200:
            print(f"AMiner reference request failed: status={response.status_code}, detail={response.text[:300]}")
            return []
        data = response.json().get("data", [])
    except (requests.RequestException, ValueError) as exc:
        print(f"AMiner reference request failed: {exc}")
        return []
    return data if isinstance(data, list) else []


def fetch_references(paper_id: str, *, size: int = 20) -> list[str]:
    relations = _fetch_pub_relation({"ref": paper_id, "offset": 0, "size": max(1, int(size))})
    return _dedupe_preserve_order(
        str(item.get("cited") or "").strip()
        for item in relations
        if isinstance(item, dict) and item.get("cited")
    )


def fetch_related_papers(paper_id: str, *, size: int = 20) -> list[str]:
    reference_ids = fetch_references(paper_id, size=size)
    cited_by_relations = _fetch_pub_relation({"cited": paper_id, "offset": 0, "size": max(1, int(size))})
    citing_ids = [
        str(item.get("ref") or "").strip()
        for item in cited_by_relations
        if isinstance(item, dict) and item.get("ref")
    ]
    return _dedupe_preserve_order([*reference_ids, *citing_ids])


def get_reference_papers(
    aminer_ids: Sequence[str],
    *,
    topic: str = "",
    size_per_paper: int = 20,
    include_citing: bool = False,
    max_workers: int = 8,
) -> list[dict[str, Any]]:
    seed_ids = _dedupe_preserve_order(aminer_ids)
    if not seed_ids:
        return []

    id_to_sources: dict[str, set[str]] = {}
    ordered_ids: list[str] = []
    seen: set[str] = set(seed_ids)

    fetcher = fetch_related_papers if include_citing else fetch_references
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(seed_ids)))) as executor:
        future_to_seed = {
            executor.submit(fetcher, seed_id, size=size_per_paper): seed_id
            for seed_id in seed_ids
        }
        for future in as_completed(future_to_seed):
            seed_id = future_to_seed[future]
            try:
                related_ids = future.result()
            except Exception as exc:
                print(f"Failed to fetch references for `{seed_id}`: {exc}")
                continue
            for paper_id in related_ids:
                if not paper_id or paper_id in seen:
                    continue
                seen.add(paper_id)
                ordered_ids.append(paper_id)
                id_to_sources.setdefault(paper_id, set()).add(seed_id)

    details = aminer_get_paper_info_batch(ordered_ids)
    detail_by_id = {
        _extract_paper_id(detail): detail
        for detail in details
        if _extract_paper_id(detail)
    }

    papers: list[dict[str, Any]] = []
    for paper_id in ordered_ids:
        detail = detail_by_id.get(paper_id)
        if not detail:
            continue
        normalized = normalize_paper_detail(detail, query=topic)
        normalized["score"] = round(rule_based_score(normalized, query=topic), 4)
        normalized["source_paper_ids"] = sorted(id_to_sources.get(paper_id, []))
        if normalized["id"] and normalized["title"]:
            papers.append(normalized)

    papers.sort(key=lambda item: (float(item.get("score", 0.0)), int(item.get("n_citation") or 0)), reverse=True)
    return papers


def citation_adding(
    total_paper_details: Sequence[Any] | None,
    uncited_paper_details: Sequence[Any] | None,
    topic: str,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    existing_ids = {
        _extract_paper_id(item)
        for item in (total_paper_details or [])
        if _extract_paper_id(item)
    }
    seed_ids = [
        _extract_paper_id(item)
        for item in (uncited_paper_details or [])
        if _extract_paper_id(item)
    ]
    papers = get_reference_papers(seed_ids, topic=topic, **kwargs)
    return [paper for paper in papers if paper["id"] not in existing_ids]


citations_adding = citation_adding


__all__ = [
    "citation_adding",
    "citations_adding",
    "fetch_references",
    "fetch_related_papers",
    "get_reference_papers",
]
