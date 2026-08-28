#!/usr/bin/env python3
"""Read-only phase metrics aggregator (v0.7 Phase 0 / Phase 1 comparison).

Aggregates, for one or more session run ids, the artifacts a bulk run already
writes — no runs are modified:

  runs/<run_id>/job_batch_*/progress.jsonl      per-paper status + llm_elapsed_sec
  runs/<run_id>/job_batch_*/monitors/*_monitor.json  per-stage timings
                                                 (write_per_paper_monitor: true)
  runs/<run_id>/job_batch_*/bert_batch_monitor.json  BERT chunk/batch stats
  production_run_history.jsonl                  per-batch totals

Prints a markdown report (per run + combined) and optionally writes JSON.

Usage:
    python scripts/collect_phase_metrics.py --run-id prod-lilaoshi-163-phase0-20260820 \
        [--label phase0-163] [--json-out /tmp/phase0.json]
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROD_ROOT / "pipeline_output" / "production" / "runs"
RUN_HISTORY_PATH = PROD_ROOT / "pipeline_output" / "production" / "production_run_history.jsonl"


def pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    idx = min(int(round(p / 100.0 * (len(s) - 1))), len(s) - 1)
    return s[idx]


def dist(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "mean": round(sum(values) / len(values), 4),
        "p50": round(pct(values, 50), 4),
        "p90": round(pct(values, 90), 4),
        "p95": round(pct(values, 95), 4),
        "max": round(max(values), 4),
    }


def collect_run(run_id: str) -> dict:
    run_dir = RUNS_DIR / run_id
    if not run_dir.is_dir():
        raise SystemExit(f"run dir not found: {run_dir}")

    statuses: dict[str, int] = {}
    error_classes: dict[str, int] = {}
    llm_elapsed: list[float] = []
    n_progress = 0
    for pf in sorted(glob.glob(str(run_dir / "job_batch_*" / "progress.jsonl"))):
        with open(pf, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                n_progress += 1
                statuses[o.get("status", "?")] = statuses.get(o.get("status", "?"), 0) + 1
                if o.get("status") == "error":
                    error_classes[o.get("error_class", "unknown")] = (
                        error_classes.get(o.get("error_class", "unknown"), 0) + 1
                    )
                v = o.get("llm_elapsed_sec")
                if isinstance(v, (int, float)):
                    llm_elapsed.append(float(v))

    stage_metrics: dict[str, list[float]] = {
        k: [] for k in (
            "paper_wall_sec", "prep_elapsed_sec", "bert_amortized_sec",
            "llm_wait_sec", "llm_elapsed_sec", "post_llm_elapsed_sec",
            # v0.7 Phase 2 staged keys (absent in phase0/phase1 runs — fine)
            "prep_queue_wait", "llm_queue_wait", "llm_http_elapsed",
            "post_queue_wait", "post_elapsed", "write_queue_wait",
            # bert inbound wait (submit -> batch HTTP start); write_elapsed_sec
            # never reaches paper monitors (serialized mid-commit) so it is
            # not listed here
            "bert_queue_wait",
        )
    }
    n_monitors = 0
    for mf in sorted(glob.glob(str(run_dir / "job_batch_*" / "monitors" / "*_monitor.json"))):
        try:
            d = json.loads(Path(mf).read_text(encoding="utf-8"))
        except Exception:
            continue
        ps = d.get("pipeline_stages") or {}
        n_monitors += 1
        for k in stage_metrics:
            v = ps.get(k)
            if isinstance(v, (int, float)):
                stage_metrics[k].append(float(v))

    bert: dict = {"pipeline_mode": None, "chunks": []}
    for bf in sorted(glob.glob(str(run_dir / "job_batch_*" / "bert_batch_monitor.json"))):
        try:
            d = json.loads(Path(bf).read_text(encoding="utf-8"))
        except Exception:
            continue
        bert["pipeline_mode"] = bert["pipeline_mode"] or d.get("pipeline_mode")
        # chunked_overlap writes "chunks" (per-window OVERWRITE — only the last
        # window survives); global_batch appends "batches" across windows.
        bert["chunks"].extend(d.get("batches") or d.get("chunks") or [])
    chunk_paper_counts = [
        c.get("paper_count") for c in bert["chunks"] if c.get("paper_count")
    ]
    chunk_client_sec = [
        c.get("bert_client_sec") for c in bert["chunks"] if c.get("bert_client_sec") is not None
    ]
    chunk_sentence_counts = [
        c.get("sentence_count", c.get("total_sentences"))
        for c in bert["chunks"]
        if c.get("sentence_count", c.get("total_sentences")) is not None
    ]
    chunk_chars = [c.get("char_count") for c in bert["chunks"] if c.get("char_count") is not None]

    history = []
    if RUN_HISTORY_PATH.is_file():
        with open(RUN_HISTORY_PATH, encoding="utf-8") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                rid = o.get("run_id", "")
                if rid.startswith(run_id + "/"):
                    history.append(o)

    # v0.7 Phase 2: staged_pipeline_monitor.json (per job_batch, appended windows)
    staged: dict = {}
    staged_windows: list[dict] = []
    for sf in sorted(glob.glob(str(run_dir / "job_batch_*" / "staged_pipeline_monitor.json"))):
        try:
            d = json.loads(Path(sf).read_text(encoding="utf-8"))
            staged_windows.extend(d.get("windows") or [d])
        except Exception:
            continue
    if staged_windows:
        windows = staged_windows
        staged = {
            "window_count": len(windows),
            "wall_sec_total": round(
                sum(float(w.get("wall_sec") or 0.0) for w in windows), 4
            ),
            "paper_count_total": sum(int(w.get("paper_count") or 0) for w in windows),
            "queue_depth_max": {
                q: max(int((w.get("queue_depth_max") or {}).get(q) or 0) for w in windows)
                for q in ("prep", "bert", "llm", "post", "write")
            },
            "stage_active_peak": {
                s: max(int((w.get("stage_active_peak") or {}).get(s) or 0) for w in windows)
                for s in ("prep", "llm_http", "post", "write")
            },
            "commit_counts": {
                k: sum(int((w.get("commit_counts") or {}).get(k) or 0) for w in windows)
                for k in ("success", "error", "writer_error", "defensive")
            },
            "duplicate_commit_attempts": sum(
                len(w.get("duplicate_commit_attempts") or []) for w in windows
            ),
            "writer_errors": [e for w in windows for e in (w.get("writer_errors") or [])],
        }

    out = {
        "run_id": run_id,
        "progress_rows": n_progress,
        "statuses": statuses,
        "error_classes": error_classes,
        "monitors": n_monitors,
        "stage_metrics": {k: dist(v) for k, v in stage_metrics.items()},
        "bert": {
            "pipeline_mode": bert["pipeline_mode"],
            "chunk_count": len(bert["chunks"]),
            "paper_count_dist": dist([float(x) for x in chunk_paper_counts]),
            "client_sec_dist": dist([float(x) for x in chunk_client_sec]),
            "sentence_count_dist": dist([float(x) for x in chunk_sentence_counts]),
            "char_count_dist": dist([float(x) for x in chunk_chars]),
        },
        "run_history": [
            {
                "run_id": h.get("run_id"),
                "total_elapsed_sec": h.get("total_elapsed_sec"),
                "critical_path_sec": h.get("critical_path_sec"),
                "experiment_count": h.get("experiment_count"),
                "papers_ok": h.get("papers_ok"),
                "papers_error": h.get("papers_error"),
            }
            for h in history
        ],
    }
    if staged:
        out["staged"] = staged
    return out


def fmt_md(m: dict) -> str:
    lines = [f"## {m['run_id']}", ""]
    lines.append(f"- progress rows: {m['progress_rows']}; statuses: {m['statuses']}")
    if m["error_classes"]:
        lines.append(f"- error classes: {m['error_classes']}")
    lines.append(f"- per-paper monitors parsed: {m['monitors']}")
    b = m["bert"]
    lines.append(
        f"- BERT mode={b['pipeline_mode']} chunks={b['chunk_count']} "
        f"paper_count={b['paper_count_dist'].get('p50')}/{b['paper_count_dist'].get('max')} (p50/max) "
        f"client_sec={b['client_sec_dist'].get('p50')}/{b['client_sec_dist'].get('max')} (p50/max)"
    )
    if b["sentence_count_dist"].get("count"):
        lines.append(
            f"- BERT sentence_count p50/p90/max: {b['sentence_count_dist'].get('p50')}/"
            f"{b['sentence_count_dist'].get('p90')}/{b['sentence_count_dist'].get('max')}"
        )
    lines.append("- stage timings (sec, mean/p50/p90/p95/max):")
    for k, d in m["stage_metrics"].items():
        if d.get("count"):
            lines.append(
                f"  - {k}: {d['mean']}/{d['p50']}/{d['p90']}/{d['p95']}/{d['max']}  (n={d['count']})"
            )
    for h in m["run_history"]:
        lines.append(
            f"- history {h['run_id']}: total={h['total_elapsed_sec']}s "
            f"crit={h['critical_path_sec']}s ok={h['papers_ok']} err={h['papers_error']}"
        )
    s = m.get("staged")
    if s:
        lines.append(
            f"- staged: windows={s['window_count']} wall_total={s['wall_sec_total']}s "
            f"papers={s['paper_count_total']} commits={s['commit_counts']} "
            f"duplicate_commit_attempts={s['duplicate_commit_attempts']}"
        )
        lines.append(f"  - queue_depth_max: {s['queue_depth_max']}")
        lines.append(f"  - stage_active_peak: {s['stage_active_peak']}")
        if s["writer_errors"]:
            lines.append(f"  - writer_errors: {s['writer_errors']}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-id", action="append", required=True, help="session run id (repeatable)")
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    results = [collect_run(rid) for rid in args.run_id]
    for m in results:
        print(fmt_md(m))
        print()
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"json written: {args.json_out}", file=sys.stderr)


if __name__ == "__main__":
    main()
