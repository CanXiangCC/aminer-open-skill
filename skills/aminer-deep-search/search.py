from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Sequence

import requests

import _utils


AMINER_SEARCH_URL = "https://datacenter.aminer.cn/gateway/open_platform/api/paper/list/by/search/venue"

# The search endpoint caps `size` at 10 per page, so larger requests are paginated.
SEARCH_PAGE_SIZE = 10
MAX_SEARCH_PAGES = 20


def _auth_headers() -> dict[str, str]:
    return {"Authorization": _utils.get_aminer_key()}


def _extract_search_items(response_json: dict[str, Any]) -> list[dict[str, Any]]:
    data = response_json.get("data", [])
    if isinstance(data, dict):
        data = data.get("data") or data.get("items") or data.get("results") or []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _fetch_search_page(
    query: str,
    *,
    page: int,
    size: int,
    order: str | None = None,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "keyword": query,
        "page": max(1, int(page)),
        "size": max(1, min(int(size), SEARCH_PAGE_SIZE)),
    }
    if order:
        params["order"] = order
    try:
        response = requests.get(
            AMINER_SEARCH_URL,
            headers=_auth_headers(),
            params=params,
            timeout=(10, 30),
        )
        if response.status_code != 200:
            print(f"AMiner search failed: status={response.status_code}, detail={response.text[:300]}")
            return []
        return _extract_search_items(response.json())
    except (requests.RequestException, ValueError) as exc:
        print(f"AMiner search failed for query `{query}`: {exc}")
        return []


def _is_within_end_year(item: dict[str, Any], end_year: int) -> bool:
    paper_year = _utils.safe_int(item.get("year"), 0)
    return not paper_year or paper_year <= end_year


def _current_utc_year() -> int:
    return datetime.now(timezone.utc).year


def aminer_pro_search(
    query: str,
    use_topic: bool = True,
    year: int | None = None,
    size: int = 20,
    offset: int = 0,
    order: str | None = None,
    max_pages: int = MAX_SEARCH_PAGES,
) -> list[dict[str, Any]]:
    """Search papers while preserving the legacy end-year and offset semantics."""
    target = max(1, int(size))
    normalized_offset = max(0, int(offset))
    end_year = int(year) if year else _current_utc_year()
    page_budget = max(1, int(max_pages))

    # The Open Platform endpoint does not honor end_year. Scan from page one
    # and apply offset after local filtering to preserve the previous API's
    # semantics, but cap the number of HTTP requests per logical search.
    page = 1
    remaining_offset = normalized_offset

    items: list[dict[str, Any]] = []
    pages_fetched = 0
    reached_last_page = False
    while len(items) < target and pages_fetched < page_budget:
        raw_page_items = _fetch_search_page(query, page=page, size=SEARCH_PAGE_SIZE, order=order)
        pages_fetched += 1
        if not raw_page_items:
            reached_last_page = True
            break

        page_items = [item for item in raw_page_items if _is_within_end_year(item, end_year)]

        if remaining_offset:
            skipped = min(remaining_offset, len(page_items))
            page_items = page_items[skipped:]
            remaining_offset -= skipped

        items.extend(page_items)
        if len(raw_page_items) < SEARCH_PAGE_SIZE:
            reached_last_page = True
            break
        page += 1

    if len(items) < target and not reached_last_page and pages_fetched >= page_budget:
        print(
            f"AMiner search page budget exhausted after {page_budget} pages; "
            f"returning {len(items)} of {target} requested papers.",
            file=sys.stderr,
        )
    return items[:target]


def search_papers(
    query: str,
    *,
    size: int = 20,
    year: int | None = None,
    order: str | None = None,
    max_pages: int = MAX_SEARCH_PAGES,
) -> list[dict[str, Any]]:
    size = max(1, min(int(size), 20))
    raw_items = aminer_pro_search(
        query,
        use_topic=True,
        year=year,
        size=size,
        offset=0,
        order=order,
        max_pages=max_pages,
    )
    if not raw_items:
        return []

    # The search endpoint already returns full paper records, so normalize them directly.
    papers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_items:
        paper_id = _utils.extract_paper_id(raw)
        if not paper_id or paper_id in seen:
            continue
        normalized = _utils.normalize_paper_detail(raw, query=query)
        if normalized["id"] and normalized["title"]:
            seen.add(paper_id)
            papers.append(normalized)

    papers.sort(
        key=lambda item: (float(item.get("score", 0.0)), _utils.safe_int(item.get("n_citation"), 0)),
        reverse=True,
    )
    return papers[:size]


def search_adding(
    keyword_list: Sequence[str],
    topic: str,
    total_paper_details: Sequence[Any] | None = None,
    **_: Any,
) -> list[dict[str, Any]]:
    existing_ids = {
        _utils.extract_paper_id(item)
        for item in (total_paper_details or [])
        if _utils.extract_paper_id(item)
    }
    papers: list[dict[str, Any]] = []
    seen = set(existing_ids)
    for keyword in keyword_list:
        for paper in search_papers(str(keyword), size=20):
            paper_id = _utils.extract_paper_id(paper)
            if not paper_id or paper_id in seen:
                continue
            paper["topic"] = topic
            seen.add(paper_id)
            papers.append(paper)
    return papers


keywords_adding = search_adding


def _compact(paper: dict[str, Any], *, include_abstract: bool) -> dict[str, Any]:
    item = {
        "id": paper.get("id"),
        "title": paper.get("title"),
        "year": paper.get("year"),
        "n_citation": paper.get("n_citation"),
    }
    if include_abstract and paper.get("abstract"):
        item["abstract"] = paper["abstract"]
    return item


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="AMiner keyword search (usable directly by the backing model when no LLM key is set)."
    )
    parser.add_argument("--query", required=True, help="Search keyword / query.")
    parser.add_argument("--size", type=int, default=20, help="Number of papers to return (max 20).")
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Inclusive publication end year (default: current UTC year).",
    )
    parser.add_argument("--order", default=None, help="Optional sort: year or n_citation.")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=MAX_SEARCH_PAGES,
        help=f"Maximum AMiner result pages to scan (default {MAX_SEARCH_PAGES}).",
    )
    parser.add_argument("--include-abstracts", action="store_true")
    args = parser.parse_args()

    papers = search_papers(
        args.query,
        size=args.size,
        year=args.year,
        order=args.order,
        max_pages=args.max_pages,
    )
    print(json.dumps([_compact(p, include_abstract=args.include_abstracts) for p in papers], ensure_ascii=False, indent=2))


__all__ = [
    "aminer_pro_search",
    "keywords_adding",
    "search_adding",
    "search_papers",
]


if __name__ == "__main__":
    _main()
