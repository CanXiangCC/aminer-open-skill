from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))

import _utils  # noqa: E402
import citation  # noqa: E402
import search  # noqa: E402


class ApiErrorStreamTests(unittest.TestCase):
    def assert_stderr_only(self, call, expected_text: str) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            call()

        self.assertEqual(stdout.getvalue(), "")
        self.assertIn(expected_text, stderr.getvalue())

    def test_search_failure_uses_stderr(self) -> None:
        response = Mock(status_code=500, text="search failure")
        with (
            patch.object(search, "_auth_headers", return_value={}),
            patch.object(search.requests, "get", return_value=response),
        ):
            self.assert_stderr_only(
                lambda: search._fetch_search_page("topic", page=1, size=10),
                "AMiner search failed",
            )

    def test_reference_failure_uses_stderr(self) -> None:
        response = Mock(status_code=500, text="reference failure")
        with (
            patch.object(citation, "_auth_headers", return_value={}),
            patch.object(citation.requests, "get", return_value=response),
        ):
            self.assert_stderr_only(
                lambda: citation._fetch_pub_relation("paper-id"),
                "AMiner reference request failed",
            )

    def test_detail_failure_uses_stderr(self) -> None:
        response = Mock(status_code=500, text="detail failure")
        with (
            patch.object(_utils, "auth_headers", return_value={}),
            patch.object(_utils.requests, "get", return_value=response),
        ):
            self.assert_stderr_only(
                lambda: _utils.request_paper_detail("paper-id"),
                "AMiner detail request failed",
            )


if __name__ == "__main__":
    unittest.main()
