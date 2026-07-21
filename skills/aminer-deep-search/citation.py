from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Sequence

import requests

from _utils import (
    aminer_get_paper_info_batch,
    dedupe_preserve_order,
    extract_paper_id,
    get_aminer_key,
    normalize_paper_detail,
    safe_int,
)


AMINER_CITATION_URL = "https://datacenter.aminer.cn/gateway/open_platform/api/paper/relation"


def _auth_headers() -> dict[str, str]:
    return {"Authorization": get_aminer_key()}


def _fetch_pub_relation(paper_id: str) -> list[dict[str, Any]]:
    try:
        response = requests.get(
            AMINER_CITATION_URL,
            params={"id": paper_id},
            headers=_auth_headers(),
            timeout=(10, 30),
        )
        if response.status_code != 200:
            print(
                f"AMiner reference request failed: status={response.status_code}, detail={response.text[:300]}",
                file=sys.stderr,
            )
            return []
        data = response.json().get("data", [])
    except (requests.RequestException, ValueError) as exc:
        print(f"AMiner reference request failed: {exc}", file=sys.stderr)
        return []
    return data if isinstance(data, list) else []


def _extract_cited_id(cited_item: Any) -> str:
    if isinstance(cited_item, dict):
        return str(cited_item.get("_id") or cited_item.get("id") or "").strip()
    return str(cited_item or "").strip()


def fetch_references(paper_id: str, *, size: int = 20) -> list[str]:
    """Return the AMiner IDs of the papers referenced (cited) by `paper_id`."""
    reference_ids: list[str] = []
    for item in _fetch_pub_relation(paper_id):
        if not isinstance(item, dict):
            continue
        cited = item.get("cited") or []
        if not isinstance(cited, list):
            continue
        for cited_item in cited:
            cited_id = _extract_cited_id(cited_item)
            if cited_id:
                reference_ids.append(cited_id)
    deduped = dedupe_preserve_order(reference_ids)
    return deduped[: max(1, int(size))] if size else deduped


def get_reference_papers(
    aminer_ids: Sequence[str],
    *,
    topic: str = "",
    size_per_paper: int = 20,
    max_workers: int = 8,
) -> list[dict[str, Any]]:
    seed_ids = dedupe_preserve_order(aminer_ids)
    if not seed_ids:
        return []

    id_to_sources: dict[str, set[str]] = {}
    ordered_ids: list[str] = []
    seed_id_set = set(seed_ids)
    seen: set[str] = set(seed_id_set)

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(seed_ids)))) as executor:
        future_to_seed = {
            executor.submit(fetch_references, seed_id, size=size_per_paper): seed_id
            for seed_id in seed_ids
        }
        for future in as_completed(future_to_seed):
            seed_id = future_to_seed[future]
            try:
                related_ids = future.result()
            except Exception as exc:
                print(f"Failed to fetch references for `{seed_id}`: {exc}", file=sys.stderr)
                continue
            for paper_id in related_ids:
                if not paper_id or paper_id in seed_id_set:
                    continue
                id_to_sources.setdefault(paper_id, set()).add(seed_id)
                if paper_id in seen:
                    continue
                seen.add(paper_id)
                ordered_ids.append(paper_id)

    details = aminer_get_paper_info_batch(ordered_ids)
    detail_by_id = {
        extract_paper_id(detail): detail
        for detail in details
        if extract_paper_id(detail)
    }

    papers: list[dict[str, Any]] = []
    for paper_id in ordered_ids:
        detail = detail_by_id.get(paper_id)
        if not detail:
            continue
        normalized = normalize_paper_detail(detail, query=topic)
        normalized["source_paper_ids"] = sorted(id_to_sources.get(paper_id, []))
        if normalized["id"] and normalized["title"]:
            papers.append(normalized)

    papers.sort(key=lambda item: (float(item.get("score", 0.0)), safe_int(item.get("n_citation"), 0)), reverse=True)
    return papers


def citation_adding(
    total_paper_details: Sequence[Any] | None,
    uncited_paper_details: Sequence[Any] | None,
    topic: str,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    existing_ids = {
        extract_paper_id(item)
        for item in (total_paper_details or [])
        if extract_paper_id(item)
    }
    seed_ids = [
        extract_paper_id(item)
        for item in (uncited_paper_details or [])
        if extract_paper_id(item)
    ]
    papers = get_reference_papers(seed_ids, topic=topic, **kwargs)
    return [paper for paper in papers if paper["id"] not in existing_ids]


citations_adding = citation_adding


def _main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="AMiner backward-reference expansion (usable directly by the backing model when no LLM key is set)."
    )
    parser.add_argument("--ids", nargs="+", required=True, help="Seed AMiner paper IDs to expand references from.")
    parser.add_argument("--topic", default="", help="Optional topic used for relevance scoring.")
    parser.add_argument("--size-per-paper", type=int, default=20, help="Max references fetched per seed paper.")
    parser.add_argument("--include-abstracts", action="store_true")
    args = parser.parse_args()

    papers = get_reference_papers(args.ids, topic=args.topic, size_per_paper=args.size_per_paper)
    compact = []
    for paper in papers:
        item = {
            "id": paper.get("id"),
            "title": paper.get("title"),
            "year": paper.get("year"),
            "n_citation": paper.get("n_citation"),
        }
        if args.include_abstracts and paper.get("abstract"):
            item["abstract"] = paper["abstract"]
        compact.append(item)
    print(json.dumps(compact, ensure_ascii=False, indent=2))


__all__ = [
    "citation_adding",
    "citations_adding",
    "fetch_references",
    "get_reference_papers",
]


if __name__ == "__main__":
    _main()
