from __future__ import annotations

import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable, Sequence

import requests


AMINER_PAPER_DETAIL_URL = "https://datacenter.aminer.cn/gateway/api/v3/paper/detail/batch"


def get_aminer_key() -> str:
    aminer_key = os.getenv("AMINER_API_KEY") or os.getenv("AMINER_KEY")
    if not aminer_key:
        raise ValueError("AMINER_API_KEY is required for AMiner API calls.")
    return aminer_key


def json_auth_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json;charset=utf-8",
        "Authorization": f"Bearer {get_aminer_key()}",
    }


def dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = str(item).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def chunks(items: Sequence[Any], chunk_size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(items), chunk_size):
        yield items[index : index + chunk_size]


def extract_paper_id(detail: Any) -> str:
    if isinstance(detail, dict):
        return str(detail.get("id") or detail.get("_id") or "")
    if detail is None:
        return ""
    return str(detail)


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_authors(authors: Any) -> list[str]:
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
    normalized["id"] = extract_paper_id(detail)
    normalized["title"] = detail.get("title") or detail.get("title_zh") or ""
    normalized["abstract"] = detail.get("abstract") or detail.get("abstract_zh") or ""
    normalized["authors"] = normalize_authors(detail.get("authors"))
    normalized["organization"] = organizations
    normalized["venue"] = str(venue_text)
    normalized["year"] = detail.get("year")
    normalized["n_citation"] = safe_int(detail.get("n_citation") or detail.get("num_citation"), 0)
    normalized["keywords"] = detail.get("keywords") or []
    normalized["score"] = round(rule_based_score(normalized, query=query), 4)
    return normalized


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{1,}", text.lower())


def rule_based_score(paper: dict[str, Any], *, query: str = "") -> float:
    query_tokens = set(tokenize(query))
    title = str(paper.get("title") or "")
    abstract = str(paper.get("abstract") or "")
    keywords = " ".join(str(item) for item in paper.get("keywords") or [])
    haystack = f"{title} {abstract} {keywords}"
    haystack_tokens = set(tokenize(haystack))

    lexical = 0.0
    if query_tokens:
        lexical = len(query_tokens & haystack_tokens) / max(1, len(query_tokens))

    phrase_bonus = 0.2 if query and query.lower() in haystack.lower() else 0.0
    citation_score = min(0.3, math.log1p(safe_int(paper.get("n_citation"), 0)) / 30.0)
    year = safe_int(paper.get("year"), 0)
    recency_score = 0.1 if year >= 2020 else 0.05 if year >= 2015 else 0.0
    return min(1.0, lexical * 0.55 + phrase_bonus + citation_score + recency_score)


def request_paper_detail_batch(paper_ids: Sequence[str]) -> list[dict[str, Any]]:
    ids = dedupe_preserve_order(paper_ids)
    if not ids:
        return []
    try:
        response = requests.post(
            AMINER_PAPER_DETAIL_URL,
            json={"ids": ids},
            headers=json_auth_headers(),
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
    ids = dedupe_preserve_order(paper_ids)
    if not ids:
        return []
    batches = list(chunks(ids, max(1, int(detail_batch_size))))
    if len(batches) == 1:
        return request_paper_detail_batch(batches[0])

    results_by_index: dict[int, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(batches)))) as executor:
        future_to_index = {
            executor.submit(request_paper_detail_batch, batch): index
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
