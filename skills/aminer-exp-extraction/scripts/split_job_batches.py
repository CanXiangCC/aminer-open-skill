#!/usr/bin/env python3
"""Split AI2000 CSV into job_batch_XXX.json manifests (paper_id + md_url)."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = PROD_ROOT / "data" / "ai2000" / "ai2000_has_md_only.csv"
DEFAULT_OUT = PROD_ROOT / "manifests" / "job_batches"


def load_rows(csv_path: Path) -> list[dict]:
    rows: list[dict] = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            pid = (r.get("id") or r.get("paper_id") or "").strip()
            url = (r.get("md_url") or "").strip()
            if not pid or not url:
                continue
            rows.append({"paper_id": pid, "md_url": url})
    return rows


def write_batches(
    rows: list[dict],
    out_dir: Path,
    size: int,
    *,
    machine: str | None = None,
    machine_count: int = 1,
    machine_index: int = 0,
) -> list[Path]:
    if machine_count < 1:
        raise ValueError("machine_count must be >= 1")
    if not (0 <= machine_index < machine_count):
        raise ValueError("machine_index out of range")

    # Steady shard by index for multi-machine (disjoint paper sets).
    if machine_count > 1:
        rows = [r for i, r in enumerate(rows) if i % machine_count == machine_index]

    out_dir = out_dir / machine if machine else out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("job_batch_*.json"):
        old.unlink()

    paths: list[Path] = []
    for bi, start in enumerate(range(0, len(rows), size)):
        chunk = rows[start : start + size]
        name = f"job_batch_{bi:03d}.json"
        path = out_dir / name
        payload = {
            "job_batch_id": f"job_batch_{bi:03d}",
            "batch_index": bi,
            "size": len(chunk),
            "machine": machine,
            "machine_index": machine_index if machine_count > 1 else None,
            "machine_count": machine_count if machine_count > 1 else None,
            "papers": chunk,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--size", type=int, default=500, help="papers per job_batch")
    ap.add_argument(
        "--machine",
        type=str,
        default=None,
        help="optional machine name; writes under out/<machine>/",
    )
    ap.add_argument("--machine-count", type=int, default=1)
    ap.add_argument("--machine-index", type=int, default=0)
    args = ap.parse_args()

    rows = load_rows(args.csv)
    paths = write_batches(
        rows,
        args.out,
        args.size,
        machine=args.machine,
        machine_count=args.machine_count,
        machine_index=args.machine_index,
    )
    print(f"csv_rows_usable={len(rows)}")
    print(f"job_batches={len(paths)} size={args.size} out={paths[0].parent if paths else args.out}")


if __name__ == "__main__":
    main()
