#!/usr/bin/env python3
"""Backfill error / missing papers from finished (or crashed) bulk runs.

Error set = papers the run saw on disk (progress.jsonl ∪ predictions/ ∪
monitors/) minus durable-ok papers (prediction file ok, or ledger.jsonl
last-row ok — forward-compatible with TODO-V07-11 compaction). Every
error-set paper is classified from its prediction-file state + the latest
progress.jsonl row:

  ok                file parses, no top-level ``error``      → excluded
  ledger_ok         file missing but ledger last row ok      → excluded
  md_fetch          latest progress error classifies md/prep → excluded by
                    default (dead links rarely heal; --include-md-fetch adds)
  parse_error / llm_timeout / llm_http / bert / post_llm / other
                    retryable service-side classes            → included
  missing_prediction file missing, latest progress ok/absent → included
                    (kill -9 between stages, deleted files, torn runs)
  corrupt           file present but unparseable              → included

Default mode is a dry-run: classification list + durable-rate estimate +
the exact run_bulk command, zero writes. ``--apply`` writes
``<source-manifest-dir>/backfill/<run>_<ts>/job_batch_backfill_000.json``
(atomic tmp+replace) + ``backfill_meta.json``; ``--run`` additionally
launches run_bulk with a NEW session run id so backfill predictions stay
out of official exports/merges (guardrail: this tool never invokes
merge/export itself).

Usage:
    python scripts/backfill_errors.py --run-id <session_run_id> [--run-id ...]
        [--source-manifest-dir manifests] [--include-md-fetch] [--apply] [--run]
        [--new-run-id <id>] [--config configs/default.yaml]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROD_ROOT / "pipeline_output" / "production" / "runs"
DEFAULT_MANIFEST_ROOT = PROD_ROOT / "manifests"
DEFAULT_CONFIG = PROD_ROOT / "configs" / "default.yaml"

MD_FETCH_CLASSES = {"md_fetch"}
_classify_error_ref = None


def _classify_error(err: str | None) -> str:
    """Reuse run_bulk._classify_error (single source of truth for classes)."""
    global _classify_error_ref
    if _classify_error_ref is None:
        spec = importlib.util.spec_from_file_location(
            "_backfill_run_bulk_ref", PROD_ROOT / "scripts" / "run_bulk.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _classify_error_ref = mod._classify_error
    return _classify_error_ref(err)


# ---------------------------------------------------------------- scanning


def _scan_universe(session_dir: Path) -> dict[str, str]:
    """paper_id -> job_batch_id from progress lines, predictions, monitors."""
    seen: dict[str, str] = {}
    batches = sorted(p for p in session_dir.glob("job_batch_*") if p.is_dir())
    for jb in batches:
        prog = jb / "progress.jsonl"
        if prog.exists():
            for line in prog.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:  # noqa: BLE001 - torn tail line
                    continue
                pid = row.get("paper_id")
                if pid:
                    seen[pid] = jb.name
        for sub in ("predictions", "monitors"):
            for f in (jb / sub).glob("*.json") if (jb / sub).is_dir() else []:
                pid = f.name[: -len("_monitor.json")] if sub == "monitors" else f.stem
                if pid and pid not in seen:
                    seen[pid] = jb.name
    return seen


def _file_state(pred_path: Path) -> tuple[str, str | None]:
    """("ok"|"missing"|"corrupt"|"error_marker", error-string-or-None)."""
    if not pred_path.exists() or pred_path.stat().st_size == 0:
        return "missing", None
    try:
        data = json.loads(pred_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return "corrupt", None
    err = data.get("error")
    return ("error_marker", str(err)) if err else ("ok", None)


def _latest_progress(session_dir: Path) -> dict[str, dict]:
    """paper_id -> latest progress row (append order, last wins)."""
    latest: dict[str, dict] = {}
    for jb in sorted(p for p in session_dir.glob("job_batch_*") if p.is_dir()):
        prog = jb / "progress.jsonl"
        if not prog.exists():
            continue
        for line in prog.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if row.get("paper_id"):
                latest[row["paper_id"]] = row
    return latest


def _ledger_ok_map(session_dir: Path) -> dict[str, bool]:
    """paper_id -> last-row-is-ok from runs/<session>/ledger.jsonl (optional)."""
    ledger = session_dir / "ledger.jsonl"
    if not ledger.exists():
        return {}
    ok: dict[str, bool] = {}
    for line in ledger.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001
            continue
        pid = row.get("paper_id")
        if pid:
            ok[pid] = row.get("status") == "ok"
    return ok


def build_md_url_index(root: Path) -> tuple[dict[str, str], int]:
    """paper_id -> md_url across all job_batch_*.json under root (recursive);
    generated backfill dirs are excluded. Returns (index, conflict_count)."""
    index: dict[str, str] = {}
    conflicts = 0
    for path in sorted(root.rglob("job_batch_*.json")):
        if "backfill" in path.relative_to(root).parts:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for paper in data.get("papers") or []:
            pid, url = paper.get("paper_id"), paper.get("md_url")
            if not pid or not url:
                continue
            old = index.get(pid)
            if old is not None and old != url:
                conflicts += 1
                # Same OSS object re-published under a new path shows up as an
                # http-vs-https conflict across corpora; keep the https variant
                # (the re-published live URL — the http one is the dead link).
                if url.startswith("https://") and not old.startswith("https://"):
                    index[pid] = url
            else:
                index.setdefault(pid, url)
    return index, conflicts


# ------------------------------------------------------------- analysis


def analyze_run(run_id: str, runs_dir: Path, md_index: dict[str, str],
                *, include_md_fetch: bool = False) -> dict:
    """Classify every paper the run saw; returns a report dict."""
    session_dir = runs_dir / run_id
    if not session_dir.is_dir():
        raise SystemExit(f"error: run dir not found: {session_dir}")
    universe = _scan_universe(session_dir)
    progress = _latest_progress(session_dir)
    ledger_ok = _ledger_ok_map(session_dir)

    ok_count = 0
    excluded: dict[str, int] = {}
    included: dict[str, list[str]] = {}
    no_md_url: list[str] = []
    for pid, jb in sorted(universe.items()):
        state, err = _file_state(session_dir / jb / "predictions" / f"{pid}.json")
        if state == "ok":
            ok_count += 1
            continue
        cls = None
        if state == "corrupt":
            cls = "corrupt"
        elif state == "missing":
            if ledger_ok.get(pid):
                ok_count += 1  # durable per ledger (compaction support)
                excluded["ledger_ok"] = excluded.get("ledger_ok", 0) + 1
                continue
            row = progress.get(pid)
            if row is None or row.get("status") == "ok":
                cls = "missing_prediction"
            else:
                cls = _classify_error(row.get("error"))
        else:  # error_marker
            row = progress.get(pid) or {}
            cls = _classify_error(err or row.get("error"))
        if cls in MD_FETCH_CLASSES:
            if include_md_fetch:
                included.setdefault("md_fetch", []).append(pid)
            else:
                excluded["md_fetch"] = excluded.get("md_fetch", 0) + 1
            continue
        if pid not in md_index:
            no_md_url.append(pid)
            continue
        included.setdefault(cls or "other", []).append(pid)

    n = len(universe)
    backfill = [pid for pids in included.values() for pid in pids]
    before = ok_count / n if n else 0.0
    after = (ok_count + len(backfill)) / n if n else 0.0
    return {
        "run_id": run_id,
        "universe": universe,
        "ok_count": ok_count,
        "excluded": excluded,
        "included": {k: sorted(v) for k, v in sorted(included.items())},
        "no_md_url": sorted(no_md_url),
        "backfill_papers": sorted(backfill),
        "durable_before": before,
        "durable_after_projected": after,
    }


def default_new_run_id(run_ids: list[str]) -> str:
    return f"{run_ids[0]}-bf{time.strftime('%Y%m%d')}"


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def print_report(reports: list[dict], new_run_id: str, backfill_dir: Path | None,
                 cfg: Path, *, will_apply: bool) -> int:
    total_ok = total_n = total_bf = 0
    for rep in reports:
        n, ok = len(rep["universe"]), rep["ok_count"]
        total_ok += ok
        total_n += n
        total_bf += len(rep["backfill_papers"])
        print(f"run {rep['run_id']}: universe={n} durable_ok={ok} "
              f"(durable {_fmt_pct(ok / n if n else 0)})")
        for cls, pids in rep["included"].items():
            print(f"  include {cls}: {len(pids)} ({', '.join(pids[:8])}"
                  f"{' ...' if len(pids) > 8 else ''})")
        for cls, cnt in rep["excluded"].items():
            print(f"  exclude {cls}: {cnt}")
        if rep["no_md_url"]:
            print(f"  WARN no md_url in manifest index, skipped: "
                  f"{len(rep['no_md_url'])} ({', '.join(rep['no_md_url'][:8])})")
    if total_n:
        print(f"TOTAL: durable {total_ok}/{total_n} ({_fmt_pct(total_ok / total_n)}) -> "
              f"projected ({total_ok}+{total_bf})/{total_n} "
              f"({_fmt_pct((total_ok + total_bf) / total_n)}) after backfill")
    if not total_bf:
        print("nothing to backfill — no manifest written")
        return 0
    print(f"\nbackfill manifest{' (dry-run, NOT written)' if not will_apply else ''}:")
    print(f"  {backfill_dir / 'job_batch_backfill_000.json'}  ({total_bf} papers)")
    print(f"run command (separate session id; never enters official merges):")
    print(f"  .venv/bin/python scripts/run_bulk.py --manifest-dir {backfill_dir} "
          f"--config {cfg} --run-id {new_run_id}")
    return 0


# ----------------------------------------------------------------- output


def apply_manifest(reports: list[dict], md_index: dict[str, str],
                   backfill_dir: Path, run_ids: list[str], new_run_id: str,
                   cfg: Path) -> Path:
    papers = []
    seen: set[str] = set()
    for rep in reports:
        for pid in rep["backfill_papers"]:
            if pid not in seen:
                seen.add(pid)
                papers.append({"paper_id": pid, "md_url": md_index[pid]})
    backfill_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "job_batch_id": "job_batch_backfill_000",
        "batch_index": 0,
        "size": len(papers),
        "machine": None,
        "machine_index": None,
        "machine_count": None,
        "papers": papers,
    }
    tmp = backfill_dir / "job_batch_backfill_000.json.tmp"
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    tmp.replace(backfill_dir / "job_batch_backfill_000.json")
    meta = {
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_run_ids": run_ids,
        "new_run_id": new_run_id,
        "papers": len(papers),
        "classes": {r["run_id"]: {"included": {k: len(v) for k, v in r["included"].items()},
                                  "excluded": r["excluded"],
                                  "no_md_url": r["no_md_url"]} for r in reports},
        "config": str(cfg),
        "guardrail": "backfill session is separate; never merged into official exports",
    }
    mtmp = backfill_dir / "backfill_meta.json.tmp"
    mtmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    mtmp.replace(backfill_dir / "backfill_meta.json")
    return backfill_dir / "job_batch_backfill_000.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run-id", action="append", required=True,
                    help="session run id under runs/ (repeatable)")
    ap.add_argument("--source-manifest-dir", type=Path, default=DEFAULT_MANIFEST_ROOT,
                    help="root for the paper->md_url index (default: manifests/)")
    ap.add_argument("--include-md-fetch", action="store_true",
                    help="also backfill md_fetch/prep errors (default: excluded)")
    ap.add_argument("--apply", action="store_true",
                    help="write the backfill manifest (default: dry-run, zero writes)")
    ap.add_argument("--run", action="store_true",
                    help="write manifest + launch run_bulk with a NEW session run id")
    ap.add_argument("--new-run-id", default=None,
                    help=f"default: <run-id>-bf<YYYYMMDD>")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--runs-dir", type=Path, default=None,
                    help="override runs/ root (offline copies, tests)")
    args = ap.parse_args(argv)

    runs_dir = args.runs_dir or RUNS_DIR
    md_index, conflicts = build_md_url_index(args.source_manifest_dir)
    if conflicts:
        print(f"WARN: {conflicts} md_url conflicts in manifest index (first wins)")
    if not md_index:
        print(f"warning: empty md_url index under {args.source_manifest_dir} "
              f"— every error paper will be skipped as no-md_url")

    reports = [analyze_run(r, runs_dir, md_index,
                           include_md_fetch=args.include_md_fetch)
               for r in args.run_id]
    new_run_id = args.new_run_id or default_new_run_id(args.run_id)
    will_apply = args.apply or args.run
    total_bf = sum(len(r["backfill_papers"]) for r in reports)
    base = args.run_id[0]
    backfill_dir = (args.source_manifest_dir / "backfill"
                    / f"{base}-{time.strftime('%Y%m%d-%H%M%S')}")

    rc = print_report(reports, new_run_id, backfill_dir, args.config,
                      will_apply=will_apply and total_bf > 0)
    if not will_apply or not total_bf:
        return rc

    manifest_path = apply_manifest(reports, md_index, backfill_dir,
                                   args.run_id, new_run_id, args.config)
    print(f"wrote {manifest_path}")
    if not args.run:
        return 0
    cmd = [sys.executable, str(PROD_ROOT / "scripts" / "run_bulk.py"),
           "--manifest-dir", str(backfill_dir), "--config", str(args.config),
           "--run-id", new_run_id]
    print(f"launching: {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=str(PROD_ROOT)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
