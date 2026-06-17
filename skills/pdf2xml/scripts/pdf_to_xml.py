#!/usr/bin/env python3
"""Convert a paper PDF to TEI XML using the AMiner/GROBID API service.

This is a thin HTTP client around the GROBID full-text endpoint:
    POST {GROBID_BASE_URL}/api/processFulltextDocument

GROBID returns a TEI XML document on success. This script wraps that call
with input validation, timeout/retry handling, error classification, and a
small CLI so it can be driven by the pdf2xml skill or run standalone.

The default service base URL matches the AMiner GROBID endpoint used by the
legacy parser. Override it with GROBID_BASE_URL or --base-url when needed.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import requests

DEFAULT_BASE_URL = "http://36.103.177.237:8088"
FULLTEXT_PATH = "/api/processFulltextDocument"
ISALIVE_PATH = "/api/isalive"
DEFAULT_TEI_COORDINATES = ("persName", "figure", "ref", "formula", "biblStruct")

# GROBID can take a while on large PDFs; retry only on transient failures.
DEFAULT_REQUEST_TIMEOUT = 300
MAX_RETRIES = 2
RETRYABLE_HTTP_STATUS = {408, 429, 500, 502, 503, 504}
BAD_INPUT_MARKER = "[BAD_INPUT_DATA]"


def _resolve_base_url(base_url: str | None = None) -> str:
    return (base_url or os.environ.get("GROBID_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def check_service(base_url: str, *, timeout: int = 10) -> tuple[bool, str]:
    """Return (alive, detail). GROBID /api/isalive returns 'true' when ready."""
    url = base_url + ISALIVE_PATH
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        return (
            False,
            f"cannot reach configured GROBID API service: {type(exc).__name__}",
        )
    if resp.status_code != 200:
        return False, f"GROBID {ISALIVE_PATH} returned HTTP {resp.status_code}"
    if resp.text.strip().lower() != "true":
        return False, f"GROBID {ISALIVE_PATH} returned: {resp.text.strip()!r}"
    return True, "GROBID API service is alive"


def convert_pdf(
    pdf_path: Path,
    *,
    base_url: str | None = None,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    max_retries: int = MAX_RETRIES,
    return_coordinates: bool = True,
    consolidate_header: int | None = None,
    consolidate_citations: int | None = None,
) -> str:
    """POST the PDF to GROBID and return the TEI XML text.

    Raises RuntimeError with a classified message on any failure.
    """
    base_url = _resolve_base_url(base_url)
    if not pdf_path.is_file():
        raise RuntimeError(f"pdf_not_found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise RuntimeError(f"not_a_pdf: {pdf_path}")

    url = base_url + FULLTEXT_PATH
    data: dict[str, str] = {}
    if consolidate_header is not None:
        data["consolidateHeader"] = str(consolidate_header)
    if consolidate_citations is not None:
        data["consolidateCitations"] = str(consolidate_citations)

    last_error = ""
    for attempt in range(1, max_retries + 1):
        try:
            with pdf_path.open("rb") as fh:
                files = []
                if return_coordinates:
                    files.extend(
                        ("teiCoordinates", (None, value))
                        for value in DEFAULT_TEI_COORDINATES
                    )
                files.append(("input", (pdf_path.name, fh, "application/pdf")))
                resp = requests.post(
                    url,
                    files=files,
                    data=data or None,
                    timeout=request_timeout,
                )
        except requests.exceptions.Timeout:
            last_error = f"request_timeout after {request_timeout}s"
        except requests.exceptions.RequestException as exc:
            last_error = f"request_failed: {type(exc).__name__}"
        else:
            if resp.status_code == 200:
                text = resp.text
                if not text.strip():
                    raise RuntimeError("empty_response: GROBID returned no content")
                if BAD_INPUT_MARKER in text:
                    raise RuntimeError("bad_input_data: GROBID could not parse the PDF")
                return text
            if resp.status_code in RETRYABLE_HTTP_STATUS:
                last_error = f"http_{resp.status_code}: {resp.text.strip()[:200]}"
            else:
                raise RuntimeError(
                    f"http_{resp.status_code}: {resp.text.strip()[:200]}"
                )
        if attempt < max_retries:
            backoff = 2 ** attempt
            _eprint(
                f"[retry {attempt}/{max_retries - 1}] "
                f"{last_error}; sleeping {backoff}s"
            )
            time.sleep(backoff)

    raise RuntimeError(last_error or "conversion_failed")


def _default_output_path(pdf_path: Path, output_dir: Path | None) -> Path:
    xml_name = pdf_path.with_suffix(".xml").name
    if output_dir is not None:
        return output_dir / xml_name
    return pdf_path.with_suffix(".xml")


def convert_to_file(
    pdf_path: Path,
    *,
    output: Path | None = None,
    output_dir: Path | None = None,
    base_url: str | None = None,
    request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    return_coordinates: bool = True,
    consolidate_header: int | None = None,
    consolidate_citations: int | None = None,
) -> Path:
    """Convert one PDF and write the TEI XML. Returns the output path."""
    xml_text = convert_pdf(
        pdf_path,
        base_url=base_url,
        request_timeout=request_timeout,
        return_coordinates=return_coordinates,
        consolidate_header=consolidate_header,
        consolidate_citations=consolidate_citations,
    )
    out_path = output if output is not None else _default_output_path(
        pdf_path, output_dir
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(xml_text, encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a paper PDF to TEI XML via a GROBID service."
    )
    parser.add_argument("--pdf", type=Path, help="Path to the input PDF file.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Explicit output .xml path. Overrides --output-dir.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for the .xml output (filename derived from the PDF).",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            "GROBID API base URL. Defaults to $GROBID_BASE_URL or "
            f"{DEFAULT_BASE_URL}."
        ),
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=DEFAULT_REQUEST_TIMEOUT,
        help=f"Per-request timeout in seconds (default {DEFAULT_REQUEST_TIMEOUT}).",
    )
    parser.add_argument(
        "--consolidate-header",
        type=int,
        choices=(0, 1, 2),
        default=None,
        help="GROBID consolidateHeader flag (0/1/2).",
    )
    parser.add_argument(
        "--consolidate-citations",
        type=int,
        choices=(0, 1, 2),
        default=None,
        help="GROBID consolidateCitations flag (0/1/2).",
    )
    parser.add_argument(
        "--no-coordinates",
        action="store_true",
        help=(
            "Do not request TEI coordinates for persName, figure, ref, "
            "formula, and biblStruct."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check whether the GROBID API service is alive, then exit.",
    )
    args = parser.parse_args()

    base_url = _resolve_base_url(args.base_url)

    if args.check:
        alive, detail = check_service(base_url)
        _eprint(detail)
        return 0 if alive else 1

    if args.pdf is None:
        _eprint("ERROR: --pdf is required unless --check is given")
        return 2

    try:
        out_path = convert_to_file(
            args.pdf,
            output=args.output,
            output_dir=args.output_dir,
            base_url=base_url,
            request_timeout=args.request_timeout,
            return_coordinates=not args.no_coordinates,
            consolidate_header=args.consolidate_header,
            consolidate_citations=args.consolidate_citations,
        )
    except RuntimeError as exc:
        _eprint(f"ERROR: {exc}")
        return 1

    print(out_path)
    _eprint(f"OK: wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
