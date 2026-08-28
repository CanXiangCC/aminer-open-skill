#!/usr/bin/env python3
"""v0.7 Phase 3 long-run sampler + aggregator (TODO-V07-04) — read-only.

Two subcommands:

  sample    Poll /proc/<pid> for RSS + thread count while a run_bulk (or any)
            process is alive; append rows to a CSV. Run this alongside each
            long-run round.

            .venv/bin/python scripts/phase3_longrun_monitor.py sample \
                --pid 12345 --interval 10 --out logs/phase3-long/r1.csv

  summarize Aggregate the staged_pipeline_monitor.json of every window of
            every round under a runs session prefix (queue depth peaks, stage
            active peaks, commit counts, duplicate commits, writer errors,
            error rate, prediction count) + the RSS/threads CSVs.

            .venv/bin/python scripts/phase3_longrun_monitor.py summarize \
                --session-prefix prod-lilaoshi-163-phase3-long \
                --csv-glob 'logs/phase3-long/*.csv' \
                --out logs/phase3-long/summary.json
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
RUNS_ROOT = PROJ / "pipeline_output" / "production" / "runs"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_status(status_path: Path) -> dict | None:
    """Parse /proc/<pid>/status key-value lines only.

    VmRSS/PPid/Threads come from unambiguous ``Key:\\tvalue`` lines, so no
    /proc/<pid>/stat field-index parsing is involved (stat's comm field may
    contain spaces/parens, which shifts every later index — the source of a
    past mis-sampling bug; see docs/V07_WINDOW_PROBE_20260821.md).
    """
    try:
        text = status_path.read_text(encoding="utf-8")
    except OSError:
        return None
    rss_kb = ppid = threads = None
    for line in text.splitlines():
        if line.startswith("VmRSS:"):
            rss_kb = int(line.split()[1])
        elif line.startswith("PPid:"):
            ppid = int(line.split()[1])
        elif line.startswith("Threads:"):
            threads = int(line.split()[1])
    if rss_kb is None:
        return None
    return {"rss_kb": rss_kb, "ppid": ppid, "threads": threads}


def _proc_stats(pid: int, proc_root: str | Path = "/proc") -> dict | None:
    info = _read_status(Path(proc_root) / str(pid) / "status")
    if info is None:
        return None
    return {"rss_kb": info["rss_kb"], "threads": info["threads"]}


def _proc_tree_stats(root_pid: int, proc_root: str | Path = "/proc") -> dict | None:
    """Sum VmRSS/threads over root_pid plus all descendants.

    Descendant edges come from each status file's PPid line. Processes whose
    status is unreadable or lacks VmRSS (kernel threads) are skipped. Returns
    None when the root itself is gone.
    """
    root = Path(proc_root)
    procs: dict[int, dict] = {}
    try:
        entries = list(root.iterdir())
    except OSError:
        return None
    for d in entries:
        if not d.name.isdigit():
            continue
        info = _read_status(d / "status")
        if info is None:
            continue
        procs[int(d.name)] = info
    if root_pid not in procs:
        return None
    keep = {root_pid}
    grew = True
    while grew:
        grew = False
        for pid, info in procs.items():
            if info.get("ppid") in keep and pid not in keep:
                keep.add(pid)
                grew = True
    return {
        "rss_kb": sum(procs[p]["rss_kb"] for p in keep),
        "threads": sum(procs[p]["threads"] or 0 for p in keep),
        "pids": len(keep),
    }


def cmd_sample(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    new = not out.exists()
    tree_mode = bool(getattr(args, "tree", False))
    # match the existing header width when appending to an old CSV
    has_pids_col = tree_mode and new
    if not new:
        with out.open("r", newline="", encoding="utf-8") as f:
            first = f.readline().strip().split(",")
            has_pids_col = tree_mode and first == ["ts_utc", "pid", "rss_kb", "threads", "tree_pids"]
    deadline = time.time() + args.duration if args.duration else None
    with out.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(
                ["ts_utc", "pid", "rss_kb", "threads", "tree_pids"] if has_pids_col
                else ["ts_utc", "pid", "rss_kb", "threads"]
            )
        while True:
            if tree_mode:
                st = _proc_tree_stats(args.pid)
            else:
                st = _proc_stats(args.pid)
            if st is None:
                print(f"[sample] pid {args.pid} gone; stopping")
                break
            row = [_utc(), args.pid, st["rss_kb"], st["threads"]]
            if has_pids_col:
                row.append(st.get("pids", ""))
            w.writerow(row)
            f.flush()
            if deadline and time.time() >= deadline:
                break
            time.sleep(args.interval)
    return 0



def cmd_summarize(args: argparse.Namespace) -> int:
    sessions = sorted(
        p for p in RUNS_ROOT.iterdir()
        if p.is_dir() and p.name.startswith(args.session_prefix)
    ) if RUNS_ROOT.exists() else []
    agg: dict = {
        "generated_at": _utc(),
        "session_prefix": args.session_prefix,
        "rounds": [],
        "totals": {
            "windows": 0, "papers": 0, "success": 0, "error": 0,
            "writer_error": 0, "defensive": 0,
            "duplicate_commit_attempts": 0, "writer_error_events": 0,
        },
        "queue_depth_max": {}, "stage_active_peak": {},
    }
    for sess in sessions:
        for jb in sorted(sess.glob("job_batch_*")):
            mon_path = jb / "staged_pipeline_monitor.json"
            if not mon_path.exists():
                continue
            try:
                doc = json.loads(mon_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            windows = doc.get("windows") or [doc]
            for w in windows:
                agg["rounds"].append({
                    "session": sess.name, "job_batch": jb.name,
                    "wall_sec": w.get("wall_sec"),
                    "paper_count": w.get("paper_count"),
                    "commit_counts": w.get("commit_counts"),
                    "terminal_states": w.get("terminal_states"),
                    "queue_depth_max": w.get("queue_depth_max"),
                    "stage_active_peak": w.get("stage_active_peak"),
                })
                t = agg["totals"]
                t["windows"] += 1
                t["papers"] += int(w.get("paper_count") or 0)
                for k in ("success", "error", "writer_error", "defensive"):
                    t[k] += int((w.get("commit_counts") or {}).get(k) or 0)
                t["duplicate_commit_attempts"] += len(w.get("duplicate_commit_attempts") or [])
                t["writer_error_events"] += len(w.get("writer_errors") or [])
                for k, v in (w.get("queue_depth_max") or {}).items():
                    agg["queue_depth_max"][k] = max(agg["queue_depth_max"].get(k, 0), v)
                for k, v in (w.get("stage_active_peak") or {}).items():
                    agg["stage_active_peak"][k] = max(agg["stage_active_peak"].get(k, 0), v)

    done = agg["totals"]["success"] + agg["totals"]["error"]
    agg["totals"]["error_rate"] = round(agg["totals"]["error"] / done, 4) if done else None
    agg["totals"]["prediction_count"] = done + agg["totals"]["defensive"]

    rss_rows: list[dict] = []
    for path in sorted(glob.glob(str(PROJ / args.csv_glob))):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("rss_kb"):
                    rss_rows.append(row)
    if rss_rows:
        rss = sorted(int(r["rss_kb"]) for r in rss_rows)
        threads = sorted(int(r["threads"]) for r in rss_rows if r.get("threads"))
        agg["rss_threads"] = {
            "samples": len(rss),
            "rss_mb_max": round(rss[-1] / 1024, 1),
            "rss_mb_mean": round(sum(rss) / len(rss) / 1024, 1),
            "threads_max": threads[-1] if threads else None,
            "growth_rss_mb_first_to_max": round((rss[-1] - rss[0]) / 1024, 1),
        }
    else:
        agg["rss_threads"] = {"samples": 0}

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(agg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: agg[k] for k in ("totals", "queue_depth_max", "stage_active_peak", "rss_threads")}, indent=2))
    print(f"summary -> {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("sample")
    p1.add_argument("--pid", type=int, required=True)
    p1.add_argument("--interval", type=float, default=10.0)
    p1.add_argument("--duration", type=float, default=None, help="max seconds (default: until process exits)")
    p1.add_argument("--out", required=True)
    p1.add_argument("--tree", action="store_true",
                    help="sum VmRSS/threads over the pid and all descendants (CSV gains a tree_pids column)")
    p1.set_defaults(fn=cmd_sample)

    p2 = sub.add_parser("summarize")
    p2.add_argument("--session-prefix", required=True)
    p2.add_argument("--csv-glob", default="pipeline_output/production/logs/**/*.csv")
    p2.add_argument("--out", required=True)
    p2.set_defaults(fn=cmd_summarize)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
