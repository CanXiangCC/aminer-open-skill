from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))

import search  # noqa: E402


def paper(index: int, *, year: int | None = 2020) -> dict[str, object]:
    item: dict[str, object] = {"id": str(index), "title": f"Paper {index}"}
    if year is not None:
        item["year"] = year
    return item


class AminerProSearchTests(unittest.TestCase):
    def test_offset_keeps_the_intra_page_remainder(self) -> None:
        pages = {
            1: [paper(index) for index in range(10)],
            2: [paper(index) for index in range(10, 20)],
        }

        with patch.object(
            search,
            "_fetch_search_page",
            side_effect=lambda _query, *, page, **_: pages.get(page, []),
        ):
            results = search.aminer_pro_search("topic", size=4, offset=7)

        self.assertEqual([item["id"] for item in results], ["7", "8", "9", "10"])

    def test_page_aligned_offset_starts_at_the_requested_page(self) -> None:
        with patch.object(
            search,
            "_fetch_search_page",
            return_value=[paper(index) for index in range(10, 20)],
        ) as fetch:
            results = search.aminer_pro_search("topic", size=2, offset=10)

        self.assertEqual([item["id"] for item in results], ["10", "11"])
        self.assertEqual(fetch.call_args.kwargs["page"], 2)

    def test_year_filters_before_applying_offset(self) -> None:
        page_items = [
            paper(0, year=2026),
            paper(1, year=2020),
            paper(2, year=2019),
            paper(3, year=2025),
            paper(4, year=2018),
        ]

        with patch.object(search, "_fetch_search_page", return_value=page_items):
            results = search.aminer_pro_search("topic", year=2020, size=2, offset=1)

        self.assertEqual([item["id"] for item in results], ["2", "4"])

    def test_unknown_year_is_not_discarded(self) -> None:
        page_items = [paper(0, year=None), paper(1, year=2021), paper(2, year=2019)]

        with patch.object(search, "_fetch_search_page", return_value=page_items):
            results = search.aminer_pro_search("topic", year=2020, size=2)

        self.assertEqual([item["id"] for item in results], ["0", "2"])


if __name__ == "__main__":
    unittest.main()
