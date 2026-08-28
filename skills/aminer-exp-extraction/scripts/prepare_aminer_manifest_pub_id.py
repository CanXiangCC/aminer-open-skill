#!/usr/bin/env python3
"""Resolve AMiner publication_id → md_url, then write job_batch manifests.

Reads a CSV with ``publication_id`` (e.g. ``data/lilaoshi_aminer/paper_list.csv``).
The CSV ``url`` column is a PDF URL and is **ignored**. Markdown URLs are resolved
via the internal AMiner API:

  GET {api_base}?pub_id={publication_id}&file_type=.md

**Requires intranet access** to ``datacenter-service-py.private.aminer.cn``.

Does not change run_bulk / ensure_cached: output is standard
``papers: [{paper_id, md_url}]`` with ``paper_id == publication_id``.

With ``--verify-only``, resolve every id and write a detail CSV + report, but
**do not** write job_batch manifests (ops check before a full prepare).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from split_job_batches import write_batches  # noqa: E402

PROD_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = PROD_ROOT / "data" / "lilaoshi_aminer" / "paper_list.csv"
DEFAULT_OUT = PROD_ROOT / "manifests" / "lilaoshi_aminer"
DEFAULT_API_BASE = (
    "http://datacenter-service-py.private.aminer.cn/paper/extracted/files"
)


@dataclass
class ResolveResult:
    publication_id: str
    status: str  # ok | empty | http_error | api_false | bad_json
    md_url: str = ""
    md_count: int = 0
    detail: str = ""


def load_csv(csv_path: Path) -> tuple[list[str], dict[str, Any]]:
    """Load unique publication_ids (first wins). Ignores PDF ``url`` column."""
    ids: list[str] = []
    seen: set[str] = set()
    csv_rows = 0
    duplicates_dropped = 0
    skipped_no_pub_id = 0

    with csv_path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            csv_rows += 1
            pub_id = (r.get("publication_id") or "").strip()
            if not pub_id:
                skipped_no_pub_id += 1
                continue
            if pub_id in seen:
                duplicates_dropped += 1
                continue
            seen.add(pub_id)
            ids.append(pub_id)

    meta = {
        "csv_rows": csv_rows,
        "unique_pub_ids": len(ids),
        "duplicates_dropped": duplicates_dropped,
        "skipped_no_pub_id": skipped_no_pub_id,
    }
    return ids, meta


def load_resolved_csv(path: Path) -> list[dict[str, str]]:
    """Load paper_id,md_url rows for --from-resolved reruns."""
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            pid = (r.get("paper_id") or r.get("publication_id") or "").strip()
            url = (r.get("md_url") or "").strip()
            if pid and url:
                rows.append({"paper_id": pid, "md_url": url})
    return rows


def resolve_one(
    pub_id: str,
    *,
    api_base: str,
    timeout: float,
    retries: int,
) -> ResolveResult:
    """GET md URL list for one publication_id; take md[0] on success."""
    last_detail = ""
    for attempt in range(max(1, retries)):
        try:
            resp = requests.get(
                api_base,
                params={"pub_id": pub_id, "file_type": ".md"},
                timeout=timeout,
            )
            if resp.status_code >= 500:
                last_detail = f"HTTP {resp.status_code}: {resp.text[:200]}"
                time.sleep(min(2**attempt, 8))
                continue
            if resp.status_code >= 400:
                return ResolveResult(
                    pub_id,
                    "http_error",
                    detail=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )
            try:
                payload = resp.json()
            except ValueError as exc:
                return ResolveResult(pub_id, "bad_json", detail=str(exc))

            if not payload.get("success", False):
                return ResolveResult(
                    pub_id,
                    "api_false",
                    detail=str(payload.get("message") or payload.get("code") or "success=false"),
                )

            data = payload.get("data") or {}
            md_list = data.get("md") if isinstance(data, dict) else None
            if not isinstance(md_list, list) or not md_list:
                return ResolveResult(pub_id, "empty", detail="data.md empty or missing")

            urls = [str(u).strip() for u in md_list if str(u).strip()]
            if not urls:
                return ResolveResult(pub_id, "empty", detail="data.md had no non-empty urls")

            return ResolveResult(
                pub_id,
                "ok",
                md_url=urls[0],
                md_count=len(urls),
            )
        except requests.RequestException as exc:
            last_detail = f"{type(exc).__name__}: {exc}"
            time.sleep(min(2**attempt, 8))

    return ResolveResult(pub_id, "http_error", detail=last_detail or "request failed")


def resolve_all(
    pub_ids: list[str],
    *,
    api_base: str,
    timeout: float,
    retries: int,
    concurrency: int,
) -> list[ResolveResult]:
    results: list[ResolveResult] = []
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        futs = {
            ex.submit(
                resolve_one,
                pid,
                api_base=api_base,
                timeout=timeout,
                retries=retries,
            ): pid
            for pid in pub_ids
        }
        for fut in as_completed(futs):
            results.append(fut.result())
    # Stable order matching input
    by_id = {r.publication_id: r for r in results}
    return [by_id[pid] for pid in pub_ids if pid in by_id]


def write_resolved_csv(path: Path, ok_rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["paper_id", "md_url", "publication_id"])
        writer.writeheader()
        for row in ok_rows:
            writer.writerow(
                {
                    "paper_id": row["paper_id"],
                    "md_url": row["md_url"],
                    "publication_id": row["paper_id"],
                }
            )


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--size", type=int, default=500, help="papers per job_batch")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--api-base", type=str, default=DEFAULT_API_BASE)
    ap.add_argument("--limit", type=int, default=None, help="cap unique pub_ids (smoke)")
    ap.add_argument(
        "--from-resolved",
        type=Path,
        default=None,
        help="skip API; read paper_id,md_url CSV and write batches only",
    )
    ap.add_argument(
        "--report",
        type=Path,
        default=None,
        help="resolve report path (default: {out}/resolve_report.json)",
    )
    ap.add_argument(
        "--verify-only",
        action="store_true",
        help="resolve all ids and write verify CSV/report; do not write job_batches",
    )
    args = ap.parse_args()

    if args.verify_only and args.from_resolved is not None:
        ap.error("--verify-only cannot be combined with --from-resolved")

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.report or (
        out_dir / ("verify_report.json" if args.verify_only else "resolve_report.json")
    )

    if args.from_resolved is not None:
        ok_rows = load_resolved_csv(args.from_resolved)
        if args.limit is not None:
            ok_rows = ok_rows[: max(0, args.limit)]
        paths = write_batches(ok_rows, out_dir, args.size)
        report = {
            "api_base": None,
            "csv": None,
            "from_resolved": str(args.from_resolved),
            "summary": {
                "ok": len(ok_rows),
                "empty": 0,
                "http_error": 0,
                "api_false": 0,
                "bad_json": 0,
            },
            "failures": [],
            "multi_md": [],
        }
        write_report(report_path, report)
        print(f"from_resolved={args.from_resolved}")
        print(f"ok={len(ok_rows)}")
        print(
            f"job_batches={len(paths)} size={args.size} "
            f"out={paths[0].parent if paths else out_dir}"
        )
        return

    pub_ids, meta = load_csv(args.csv)
    if args.limit is not None:
        pub_ids = pub_ids[: max(0, args.limit)]

    action = "Verifying" if args.verify_only else "Resolving"
    print(
        f"{action} {len(pub_ids)} publication_ids via {args.api_base} "
        f"(intranet required)...",
        flush=True,
    )
    results = resolve_all(
        pub_ids,
        api_base=args.api_base,
        timeout=args.timeout,
        retries=args.retries,
        concurrency=args.concurrency,
    )

    counts = {"ok": 0, "empty": 0, "http_error": 0, "api_false": 0, "bad_json": 0}
    failures: list[dict[str, str]] = []
    multi_md: list[dict[str, Any]] = []
    ok_rows: list[dict[str, str]] = []
    verify_rows: list[dict[str, str]] = []

    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
        if args.verify_only:
            verify_rows.append(
                {
                    "publication_id": r.publication_id,
                    "status": r.status,
                    "md_url": r.md_url,
                    "md_count": str(r.md_count),
                    "detail": r.detail,
                }
            )
        if r.status == "ok":
            ok_rows.append({"paper_id": r.publication_id, "md_url": r.md_url})
            if r.md_count > 1:
                multi_md.append(
                    {
                        "publication_id": r.publication_id,
                        "md_count": r.md_count,
                        "chosen": r.md_url,
                    }
                )
                print(
                    f"WARN multi_md publication_id={r.publication_id} "
                    f"md_count={r.md_count} chosen={r.md_url}",
                    flush=True,
                )
        else:
            failures.append(
                {
                    "publication_id": r.publication_id,
                    "status": r.status,
                    "detail": r.detail,
                }
            )

    print(f"csv_rows={meta['csv_rows']}")
    print(f"unique_pub_ids={meta['unique_pub_ids']}")
    print(f"duplicates_dropped={meta['duplicates_dropped']}")
    print(f"skipped_no_pub_id={meta['skipped_no_pub_id']}")

    if args.verify_only:
        detail_csv = out_dir / "verify_all_pub_ids.csv"
        with detail_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["publication_id", "status", "md_url", "md_count", "detail"],
            )
            writer.writeheader()
            writer.writerows(verify_rows)
        report = {
            "api_base": args.api_base,
            "csv": str(args.csv),
            "summary": {
                **meta,
                "verified": len(pub_ids),
                **counts,
            },
            "results": verify_rows,
        }
        write_report(report_path, report)
        print(f"verified={len(pub_ids)}")
        print(f"ok={counts['ok']}")
        print(f"empty={counts['empty']}")
        print(f"http_error={counts['http_error']}")
        print(f"api_false={counts['api_false']}")
        print(f"bad_json={counts.get('bad_json', 0)}")
        print(f"detail_csv={detail_csv}")
        print(f"report={report_path}")
        return

    resolved_csv = out_dir / "resolved_papers.csv"
    write_resolved_csv(resolved_csv, ok_rows)

    report = {
        "api_base": args.api_base,
        "csv": str(args.csv),
        "summary": {
            **meta,
            "resolved_requested": len(pub_ids),
            **counts,
        },
        "failures": failures,
        "multi_md": multi_md,
    }
    write_report(report_path, report)

    paths = write_batches(ok_rows, out_dir, args.size)

    print(f"resolved_requested={len(pub_ids)}")
    print(f"ok={counts['ok']}")
    print(f"empty={counts['empty']}")
    print(f"http_error={counts['http_error']}")
    print(f"api_false={counts['api_false']}")
    print(f"bad_json={counts.get('bad_json', 0)}")
    print(f"resolved_csv={resolved_csv}")
    print(f"report={report_path}")
    print(
        f"job_batches={len(paths)} size={args.size} "
        f"out={paths[0].parent if paths else out_dir}"
    )


if __name__ == "__main__":
    main()
