from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from _utils import aminer_get_paper_info_batch, normalize_paper_detail


def paper_id_of(paper: Any) -> str:
    if isinstance(paper, dict):
        return str(paper.get("id") or paper.get("_id") or "")
    return str(paper or "")


class PaperSet:
    def __init__(self) -> None:
        self._papers: dict[str, dict[str, Any]] = {}

    def __len__(self) -> int:
        return len(self._papers)

    def add_papers(self, papers: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        for paper in papers:
            paper_id = paper_id_of(paper).strip()
            title = str(paper.get("title") or paper.get("title_zh") or "").strip()
            if not paper_id or not title:
                continue
            if paper_id in self._papers:
                self._papers[paper_id].update({k: v for k, v in paper.items() if v not in (None, "", [])})
            else:
                self._papers[paper_id] = dict(paper)
        return self.all_papers()

    def add_ids(self, ids: Iterable[str], paper_cache: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        missing_ids: list[str] = []
        papers: list[dict[str, Any]] = []
        for paper_id in ids:
            cleaned = str(paper_id).strip()
            if not cleaned:
                continue
            if cleaned in paper_cache:
                papers.append(paper_cache[cleaned])
            else:
                missing_ids.append(cleaned)

        if missing_ids:
            for detail in aminer_get_paper_info_batch(missing_ids):
                normalized = normalize_paper_detail(detail)
                if normalized["id"]:
                    paper_cache[normalized["id"]] = normalized
                    papers.append(normalized)

        return self.add_papers(papers)

    def all_papers(self) -> list[dict[str, Any]]:
        return sorted(
            self._papers.values(),
            key=lambda item: (float(item.get("score", 0.0) or 0.0), int(item.get("n_citation") or 0)),
            reverse=True,
        )

    def output(self, *, include_abstracts: bool = False) -> list[dict[str, Any]]:
        papers: list[dict[str, Any]] = []
        for paper in self.all_papers():
            item = {"id": paper["id"], "title": paper["title"]}
            if include_abstracts and paper.get("abstract"):
                item["abstract"] = paper["abstract"]
            papers.append(item)
        return papers

    def save(self, path: Path, *, include_abstracts: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(self.output(include_abstracts=include_abstracts), file, ensure_ascii=False, indent=2)
