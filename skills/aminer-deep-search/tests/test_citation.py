from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))

import citation  # noqa: E402


class ReferenceSourceTests(unittest.TestCase):
    def test_shared_reference_records_every_seed(self) -> None:
        references = {
            "seed-a": ["shared", "only-a"],
            "seed-b": ["shared", "only-b"],
        }

        def fetch_references(seed_id: str, *, size: int) -> list[str]:
            return references[seed_id][:size]

        def fetch_details(paper_ids: list[str]) -> list[dict[str, object]]:
            return [{"id": paper_id, "title": f"Paper {paper_id}"} for paper_id in paper_ids]

        with (
            patch.object(citation, "fetch_references", side_effect=fetch_references),
            patch.object(citation, "aminer_get_paper_info_batch", side_effect=fetch_details),
        ):
            papers = citation.get_reference_papers(["seed-a", "seed-b"])

        papers_by_id = {paper["id"]: paper for paper in papers}
        self.assertEqual(papers_by_id["shared"]["source_paper_ids"], ["seed-a", "seed-b"])
        self.assertEqual(papers_by_id["only-a"]["source_paper_ids"], ["seed-a"])
        self.assertEqual(papers_by_id["only-b"]["source_paper_ids"], ["seed-b"])


if __name__ == "__main__":
    unittest.main()
