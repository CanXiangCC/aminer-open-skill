"""Tests for dataset confidence scoring — URL quality gates + identifier verify."""

from __future__ import annotations

import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

from pipeline.production.adapters.dataset_confidence import (  # noqa: E402
    _is_code_host,
    _name_to_slug,
    _passes_url_name_coverage,
    _url_path_extension,
    score_datasets_confidence,
)

WATERMARK_PNG = (
    "https://maas-watermark-prod-new.cn-wlcb.ufileos.com/"
    "ocr%2Fcrop%2F2026080411044364f890d181924801%2Fcrop_1_1785812728827.png"
)


def _base_ds(**overrides: object) -> dict:
    d: dict = {
        "name": "ImageNet",
        "aliases": [],
        "dataset_type": "image",
        "description": "A large image dataset.",
        "sample_size": None,
        "is_public": True,
        "is_self_collected": False,
        "urls": [],
        "github_urls": [],
        "doi_list": [],
        "cstr_list": [],
    }
    d.update(overrides)
    return d


def test_url_path_extension_and_denylist_helpers() -> None:
    assert _url_path_extension(WATERMARK_PNG) == "png"
    assert _url_path_extension("https://example.com/data.pdf?x=1") == "pdf"
    assert _url_path_extension("https://image-net.org/download") == ""
    assert _name_to_slug("Terminal-Bench 2.0") == "terminalbench"
    assert _is_code_host("https://github.com/org/imagenet")
    assert _is_code_host("https://gitlab.com/org/repo")
    assert not _is_code_host("https://example.com/org/repo")


def test_name_coverage_scheme_a() -> None:
    assert _passes_url_name_coverage(
        "https://www.image-net.org/challenges/LSVRC/",
        "ImageNet",
        [],
    )
    assert not _passes_url_name_coverage(WATERMARK_PNG, "Terminal-Bench 2.0", [])
    # All slugs < 3 → skip name gate
    assert _passes_url_name_coverage("https://example.com/x", "AB", [])


def test_png_url_cleared_even_if_verbatim() -> None:
    text = f"We evaluate on ImageNet. See {WATERMARK_PNG} for figure."
    scored = score_datasets_confidence(
        [_base_ds(urls=[WATERMARK_PNG])],
        text,
        sort=False,
    )
    assert scored[0]["urls"] == []
    assert scored[0]["confidence_breakdown"]["fake_identifier"] is True
    assert scored[0]["confidence_breakdown"]["identifier_hit"] is False


def test_pdf_url_cleared() -> None:
    pdf = "https://example.com/papers/imagenet.pdf"
    text = f"ImageNet paper at {pdf}"
    scored = score_datasets_confidence(
        [_base_ds(urls=[pdf])],
        text,
        sort=False,
    )
    assert scored[0]["urls"] == []
    assert scored[0]["confidence_breakdown"]["fake_identifier"] is True


def test_legitimate_url_with_name_substring_kept() -> None:
    url = "https://www.image-net.org/index.html"
    text = f"We use ImageNet from {url}."
    scored = score_datasets_confidence(
        [_base_ds(urls=[url])],
        text,
        sort=False,
    )
    assert scored[0]["urls"] == [url]
    assert scored[0]["confidence_breakdown"]["identifier_hit"] is True
    assert scored[0]["confidence_breakdown"]["fake_identifier"] is False


def test_github_non_code_host_cleared() -> None:
    bad = "https://bitbucket.org/org/imagenet"
    text = f"Code at {bad} for ImageNet."
    scored = score_datasets_confidence(
        [_base_ds(github_urls=[bad])],
        text,
        sort=False,
    )
    assert scored[0]["github_urls"] == []
    assert scored[0]["confidence_breakdown"]["fake_identifier"] is True


def test_github_with_name_in_path_kept() -> None:
    gh = "https://github.com/pytorch/vision/tree/main/imagenet"
    text = f"ImageNet loaders: {gh}"
    scored = score_datasets_confidence(
        [_base_ds(github_urls=[gh])],
        text,
        sort=False,
    )
    assert scored[0]["github_urls"] == [gh]
    assert scored[0]["confidence_breakdown"]["identifier_hit"] is True


def test_doi_verbatim_only_no_name_in_doi() -> None:
    doi = "10.5281/zenodo.123456"
    text = f"Dataset DOI: {doi}. We train on ImageNet."
    scored = score_datasets_confidence(
        [_base_ds(doi_list=[doi])],
        text,
        sort=False,
    )
    assert scored[0]["doi_list"] == [doi]
    assert scored[0]["confidence_breakdown"]["identifier_hit"] is True
    assert scored[0]["confidence_breakdown"]["fake_identifier"] is False


def test_empty_urls_not_fake() -> None:
    text = "We evaluate on ImageNet in all experiments."
    scored = score_datasets_confidence(
        [_base_ds(urls=[], github_urls=[], doi_list=[])],
        text,
        sort=False,
    )
    assert scored[0]["urls"] == []
    assert scored[0]["confidence_breakdown"]["fake_identifier"] is False
    assert scored[0]["confidence_breakdown"]["identifier_hit"] is False


def test_deepseek_terminal_bench_watermark_cleared() -> None:
    text = (
        "Results on Terminal-Bench 2.0 are strong. "
        f"Watermark asset: {WATERMARK_PNG}"
    )
    scored = score_datasets_confidence(
        [
            _base_ds(
                name="Terminal-Bench 2.0",
                dataset_type="point_cloud",
                description="A benchmark for evaluating reasoning and knowledge tasks.",
                is_public=None,
                is_self_collected=None,
                urls=[WATERMARK_PNG],
            )
        ],
        text,
        sort=False,
    )
    assert scored[0]["urls"] == []
    assert scored[0]["name"] == "Terminal-Bench 2.0"
    assert scored[0]["confidence_breakdown"]["fake_identifier"] is True
    assert scored[0]["confidence_breakdown"]["identifier_hit"] is False


if __name__ == "__main__":
    test_url_path_extension_and_denylist_helpers()
    test_name_coverage_scheme_a()
    test_png_url_cleared_even_if_verbatim()
    test_pdf_url_cleared()
    test_legitimate_url_with_name_substring_kept()
    test_github_non_code_host_cleared()
    test_github_with_name_in_path_kept()
    test_doi_verbatim_only_no_name_in_doi()
    test_empty_urls_not_fake()
    test_deepseek_terminal_bench_watermark_cleared()
    print("OK: all dataset_confidence tests passed")
