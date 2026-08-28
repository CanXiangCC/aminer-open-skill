#!/usr/bin/env python3
"""v0.7 Phase 6 read-only results aggregator (TODO-V07-07).

Reads pipeline_output/production/phase6/phase6_runs.jsonl (written by
scripts/run_phase6_sweep.py) plus each run's own artifacts:

  logs/<run_id>/cli_summary.json          totals, hashes, schema violations
  logs/<run_id>/metrics.json              collect_phase_metrics output
  runs/<run_id>/job_batch_*/staged_pipeline_monitor.json (staged modes)
  exports/ai2000_<run_id>_flat_merged.json flat export duplicate check
  phase6/rss/<run_id>.csv                  already summarized in the record

and produces:

  <out-dir>/phase6_summary.json   per-run rows + per-condition aggregates +
                                  gate verdicts + candidate eligibility +
                                  layer-B knee analysis + verified/anomalous/
                                  missing marking per metric group
  <out-dir>/phase6_summary.csv    one row per run, numeric-friendly
  markdown tables on stdout

No file outside <out-dir> is written. This script never proposes changing
configs/default.yaml; candidate output is a RECOMMENDATION ONLY.
"""

from __future__ import annotations

import argparse
import csv as csv_mod
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
PHASE6_ROOT = PROJ / "pipeline_output" / "production" / "phase6"
LOGS_ROOT = PROJ / "pipeline_output" / "production" / "logs"
EXPORTS_DIR = PROJ / "pipeline_output" / "production" / "exports"

# quality gates (task §九); md_fetch (deterministic OSS 404) is classified
# separately and never counted as a scheduler error.
GATE_SCHEDULER_ERROR_RATE = 0.15
GATE_PARSE_ERROR_RATE = 0.10
GATE_ZERO_DATASETS_RATE = 0.25

_COND_NUM_RE = re.compile(r"(\d+)")


def _num_key(cond: str):
    """Numeric-aware condition sort: 'b-q30' < 'b-q64' < 'b-q128'."""
    m = _COND_NUM_RE.search(cond)
    if not m:
        return (cond, 0)
    return (cond[: m.start()], int(m.group(1)))


def load_records(jsonl_path: Path) -> list[dict]:
    records = []
    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def dist_get(metrics_run: dict, key: str, field: str):
    d = (metrics_run.get("stage_metrics") or {}).get(key)
    if not d:
        return None
    return d.get(field)


def staged_monitor_agg(run_id: str) -> dict:
    """Aggregate staged_pipeline_monitor.json windows for one run."""
    totals = {"duplicate_commit_attempts": 0, "writer_errors": 0,
              "writer_error_commits": 0, "defensive": 0,
              "success": 0, "error": 0}
    qd_max: dict[str, int] = {}
    active_peak: dict[str, int] = {}
    windows = 0
    for mon in sorted((PROJ / "pipeline_output" / "production" / "runs" / run_id).glob(
            "job_batch_*/staged_pipeline_monitor.json")):
        doc = load_json(mon)
        if not doc:
            continue
        for w in doc.get("windows") or [doc]:
            windows += 1
            cc = w.get("commit_counts") or {}
            totals["success"] += int(cc.get("success") or 0)
            totals["error"] += int(cc.get("error") or 0)
            totals["writer_error_commits"] += int(cc.get("writer_error") or 0)
            totals["defensive"] += int(cc.get("defensive") or 0)
            totals["duplicate_commit_attempts"] += len(w.get("duplicate_commit_attempts") or [])
            totals["writer_errors"] += len(w.get("writer_errors") or [])
            for k, v in (w.get("queue_depth_max") or {}).items():
                qd_max[k] = max(qd_max.get(k, 0), v)
            for k, v in (w.get("stage_active_peak") or {}).items():
                active_peak[k] = max(active_peak.get(k, 0), v)
    if not windows:
        return {"present": False}
    return {"present": True, "windows": windows, **totals,
            "queue_depth_max": qd_max, "stage_active_peak": active_peak}


def flat_export_stats(run_id: str) -> dict:
    path = EXPORTS_DIR / f"ai2000_{run_id}_flat_merged.json"
    doc = load_json(path)
    if not isinstance(doc, list):
        return {"present": False}
    keys = [(e.get("paper_id"), e.get("experiment_name"), e.get("experiment_index"))
            for e in doc if isinstance(e, dict)]
    return {
        "present": True,
        "experiments": len(doc),
        "papers": len({k[0] for k in keys}),
        "duplicate_experiments": len(keys) - len(set(keys)),
    }


def error_class_counts(metrics_runs: list[dict]) -> dict:
    out: dict[str, int] = defaultdict(int)
    for m in metrics_runs:
        for cls, n in (m.get("error_classes") or {}).items():
            out[cls] += int(n)
    return dict(out)


def build_run_row(rec: dict) -> dict:
    run_id = rec["run_id"]
    metrics_doc = load_json(LOGS_ROOT / run_id / "metrics.json") or []
    metrics_runs = [m for m in (metrics_doc if isinstance(metrics_doc, list) else [])
                    if m.get("run_id", run_id).startswith(run_id)]
    m0 = metrics_runs[0] if metrics_runs else {}

    ok = int(rec.get("total_ok") or 0)
    err = int(rec.get("total_error") or 0)
    skip = int(rec.get("total_skipped") or 0)
    done = ok + err
    planned = rec.get("planned_papers")
    classes = error_class_counts(metrics_runs)
    md404 = int(classes.get("md_fetch") or 0)
    parse_err = int(classes.get("parse_error") or 0)
    scheduler_err = max(err - md404, 0)

    row = {
        "run_id": run_id,
        "layer": rec.get("layer"),
        "condition": rec.get("condition"),
        "round": rec.get("round"),
        "mode": rec.get("mode"),
        "exit_code": rec.get("exit_code"),
        "cli_status": rec.get("cli_status", "missing"),
        "config_sha256": rec.get("config_sha256"),
        "manifest_sha256": rec.get("manifest_sha256"),
        "git_commit": rec.get("git_commit"),
        "planned_papers": planned,
        "ok": ok, "error": err, "skipped": skip,
        "conservation_ok": (planned is None and "unavailable") or (done + skip == planned),
        "error_classes": classes,
        "md404": md404,
        "parse_error": parse_err,
        "scheduler_error": scheduler_err,
        "parse_error_rate": round(parse_err / done, 4) if done else None,
        "scheduler_error_rate": round(scheduler_err / done, 4) if done else None,
        "papers_per_hour": rec.get("papers_per_hour"),
        "bulk_wall_sec": rec.get("bulk_wall_sec"),
        "schema_violations": rec.get("schema_violations"),
        "llm_p50": dist_get(m0, "llm_elapsed_sec", "p50") or dist_get(m0, "llm_http_elapsed", "p50"),
        "llm_p95": dist_get(m0, "llm_elapsed_sec", "p95") or dist_get(m0, "llm_http_elapsed", "p95"),
        "llm_max": dist_get(m0, "llm_elapsed_sec", "max") or dist_get(m0, "llm_http_elapsed", "max"),
        "bert_p50": dist_get(m0, "bert_amortized_sec", "p50"),
        "bert_p95": dist_get(m0, "bert_amortized_sec", "p95"),
        "post_p50": dist_get(m0, "post_llm_elapsed_sec", "p50") or dist_get(m0, "post_elapsed", "p50"),
        "post_p95": dist_get(m0, "post_llm_elapsed_sec", "p95") or dist_get(m0, "post_elapsed", "p95"),
        "prep_qwait_p95": dist_get(m0, "prep_queue_wait", "p95"),
        "llm_qwait_p95": dist_get(m0, "llm_queue_wait", "p95"),
        "post_qwait_p95": dist_get(m0, "post_queue_wait", "p95"),
        "bert_batch_count": ((m0.get("bert") or {}).get("chunk_count")),
        "bert_papers_per_batch_mean": ((m0.get("bert") or {}).get("paper_count_dist") or {}).get("mean"),
        "rss_mb_max": (rec.get("rss") or {}).get("rss_mb_max"),
        "rss_growth_mb": (rec.get("rss") or {}).get("growth_rss_mb_first_to_max"),
        "threads_max": (rec.get("rss") or {}).get("threads_max"),
        "zero_datasets_rate": "unavailable",  # enforced at runtime by run_bulk gates, not re-aggregated
    }

    st = staged_monitor_agg(run_id)
    row["staged_monitor"] = st
    if st.get("present"):
        row["duplicate_commit_attempts"] = st["duplicate_commit_attempts"]
        row["writer_errors"] = st["writer_errors"]
    else:
        row["duplicate_commit_attempts"] = "unavailable"
        row["writer_errors"] = "unavailable"

    fe = flat_export_stats(run_id)
    row["flat_export"] = fe
    row["flat_duplicate_experiments"] = fe.get("duplicate_experiments", "unavailable") if fe.get("present") else "unavailable"

    # metric-group provenance marking
    groups = {}
    groups["end_to_end"] = "verified" if row["papers_per_hour"] is not None else "missing"
    groups["correctness"] = "verified" if row["cli_status"] in ("success", "partial_success") else "anomalous"
    groups["llm_latency"] = "verified" if row["llm_p95"] is not None else ("missing" if not metrics_runs else "missing")
    groups["staged_queues"] = "verified" if st.get("present") else "missing"
    groups["rss"] = "verified" if row["rss_mb_max"] is not None else "missing"
    groups["flat_export"] = "verified" if fe.get("present") else "missing"
    groups["zero_datasets_rate"] = "missing"
    row["metric_groups"] = groups

    row["gates"] = run_gates(row)
    return row


def run_gates(row: dict) -> dict:
    """Task §九 elimination gates for a single run."""
    g: dict[str, bool | str] = {}
    for key, rate, limit in (("scheduler_error_rate", "scheduler_error_rate", GATE_SCHEDULER_ERROR_RATE),
                             ("parse_error_rate", "parse_error_rate", GATE_PARSE_ERROR_RATE)):
        v = row.get(rate)
        g[key] = "unavailable" if v is None else bool(v <= limit)
    cons = row["conservation_ok"]
    g["conservation"] = True if cons is True else ("unavailable" if cons in ("unavailable", None) else False)
    g["schema_violations_zero"] = (row.get("schema_violations") in (0, None) and row.get("schema_violations") != "unavailable")
    g["no_duplicate_commit"] = (row["duplicate_commit_attempts"] == 0) if isinstance(row["duplicate_commit_attempts"], int) else "unavailable"
    g["no_writer_errors"] = (row["writer_errors"] == 0) if isinstance(row["writer_errors"], int) else "unavailable"
    g["no_flat_duplicates"] = (row["flat_duplicate_experiments"] == 0) if isinstance(row["flat_duplicate_experiments"], int) else "unavailable"
    g["rss_bounded"] = True if row.get("rss_growth_mb") is not None and row["rss_growth_mb"] < 500 else ("unavailable" if row.get("rss_growth_mb") is None else False)
    g["run_succeeded"] = row["cli_status"] in ("success", "partial_success") and row["exit_code"] == 0
    return g


def run_passed(row: dict) -> bool:
    g = row["gates"]
    hard = ["run_succeeded", "conservation", "schema_violations_zero",
            "no_duplicate_commit", "no_writer_errors", "no_flat_duplicates", "rss_bounded"]
    for k in hard:
        if g.get(k) is False:
            return False
    for k in ("scheduler_error_rate", "parse_error_rate"):
        if g.get(k) is False:
            return False
    return True


def aggregate_conditions(rows: list[dict], execution_order: list[str]) -> dict:
    """Group per condition, pair interleaved rounds, robust median."""
    by_cond: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cond[r["condition"]].append(r)
    out: dict[str, dict] = {}
    for cond in sorted(by_cond, key=_num_key):
        crows = sorted(by_cond[cond], key=lambda r: r["round"])
        pphs = [r["papers_per_hour"] for r in crows if r["papers_per_hour"] is not None]
        med = statistics.median(pphs) if pphs else None
        anomalous_rounds = []
        stable_pphs = []
        for r in crows:
            v = r["papers_per_hour"]
            if v is not None and med and abs(v - med) / med > 0.30:
                anomalous_rounds.append(r["run_id"])
            elif v is not None:
                stable_pphs.append(v)
        robust_med = statistics.median(stable_pphs) if stable_pphs else med
        # interleaving check: consecutive executions of the same condition
        # should be separated by other conditions in execution order
        idxs = [i for i, rid in enumerate(execution_order) if rid in {r["run_id"] for r in crows}]
        interleaved = all(b - a > 1 for a, b in zip(idxs, idxs[1:])) if len(idxs) > 1 else True
        passed = [run_passed(r) for r in crows]
        out[cond] = {
            "layer": crows[0]["layer"],
            "rounds": [r["run_id"] for r in crows],
            "n_rounds": len(crows),
            "all_rounds_passed": all(passed) and len(passed) >= 1,
            "pph_per_round": pphs,
            "pph_median": robust_med if robust_med is not None else med,
            "pph_min": min(pphs) if pphs else None,
            "pph_max": max(pphs) if pphs else None,
            "anomalous_rounds": anomalous_rounds,
            "interleaved": interleaved,
            "candidate_eligible": (
                len(crows) >= 2
                and all(passed)
                and not anomalous_rounds
                and interleaved
            ),
            "llm_p95_per_round": [r["llm_p95"] for r in crows],
            "rss_mb_max": max((r["rss_mb_max"] for r in crows if r["rss_mb_max"] is not None), default=None),
        }
    return out


def knee_analysis(cond_agg: dict, layer: str) -> dict | None:
    """Layer-B knee: pph growth <10% or p95 worsening >25% at higher concurrency."""
    if layer != "B":
        return None
    conds = sorted((c for c, a in cond_agg.items() if a["layer"] == "B"), key=_num_key)
    steps = []
    for prev, cur in zip(conds, conds[1:]):
        p0, p1 = cond_agg[prev]["pph_median"], cond_agg[cur]["pph_median"]
        s0 = [x for x in cond_agg[prev]["llm_p95_per_round"] if x is not None]
        s1 = [x for x in cond_agg[cur]["llm_p95_per_round"] if x is not None]
        growth = round((p1 - p0) / p0, 4) if (p0 and p1) else None
        p95_ratio = round(statistics.median(s1) / statistics.median(s0), 4) if (s0 and s1) else None
        near_knee = (growth is not None and growth < 0.10) or (p95_ratio is not None and p95_ratio > 1.25)
        steps.append({"from": prev, "to": cur, "pph_growth": growth,
                      "llm_p95_ratio": p95_ratio, "near_knee": near_knee})
    return {"steps": steps}


def fmt_v(v):
    if v is None:
        return "unavailable"
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def print_markdown(rows: list[dict], cond_agg: dict) -> None:
    print("\n## Per-run results\n")
    hdr = ["run_id", "pph", "ok/err", "sched_err_rate", "parse_rate", "llm_p95",
           "llm_max", "rss_max_mb", "dup_commit", "writer_err", "flat_dup", "passed"]
    print("| " + " | ".join(hdr) + " |")
    print("|" + "---|" * len(hdr))
    for r in rows:
        print("| " + " | ".join([
            r["run_id"], fmt_v(r["papers_per_hour"]),
            f"{r['ok']}/{r['error']}",
            fmt_v(r["scheduler_error_rate"]), fmt_v(r["parse_error_rate"]),
            fmt_v(r["llm_p95"]), fmt_v(r["llm_max"]), fmt_v(r["rss_mb_max"]),
            fmt_v(r["duplicate_commit_attempts"]), fmt_v(r["writer_errors"]),
            fmt_v(r["flat_duplicate_experiments"]),
            "PASS" if run_passed(r) else "FAIL",
        ]) + " |")
    print("\n## Per-condition aggregates (interleaved rounds)\n")
    print("| condition | rounds | pph/round | pph_median | interleaved | candidate_eligible |")
    print("|---|---|---|---|---|---|")
    for cond, a in cond_agg.items():
        print(f"| {cond} | {a['n_rounds']} | {a['pph_per_round']} | "
              f"{fmt_v(a['pph_median'])} | {a['interleaved']} | {a['candidate_eligible']} |")


CSV_FIELDS = ["run_id", "layer", "condition", "round", "exit_code", "cli_status",
              "planned_papers", "ok", "error", "skipped", "conservation_ok",
              "md404", "parse_error", "scheduler_error", "parse_error_rate",
              "scheduler_error_rate", "papers_per_hour", "bulk_wall_sec",
              "schema_violations", "llm_p50", "llm_p95", "llm_max",
              "bert_p50", "bert_p95", "post_p50", "post_p95",
              "prep_qwait_p95", "llm_qwait_p95", "post_qwait_p95",
              "bert_batch_count", "bert_papers_per_batch_mean",
              "rss_mb_max", "rss_growth_mb", "threads_max",
              "duplicate_commit_attempts", "writer_errors",
              "flat_duplicate_experiments"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs-jsonl", type=Path,
                    default=PHASE6_ROOT / "phase6_runs.jsonl")
    ap.add_argument("--out-dir", type=Path, default=PHASE6_ROOT)
    ap.add_argument("--layer-filter", default=None,
                    help="restrict aggregation to one layer (e.g. B)")
    args = ap.parse_args()

    records = load_records(args.runs_jsonl)
    if args.layer_filter:
        records = [r for r in records if r.get("layer") == args.layer_filter]
    if not records:
        print(f"no phase6 run records in {args.runs_jsonl}")
        return 1

    rows = [build_run_row(r) for r in records]
    execution_order = [r["run_id"] for r in records]
    cond_agg = aggregate_conditions(rows, execution_order)
    knees = {}
    for layer in {r["layer"] for r in rows}:
        k = knee_analysis(cond_agg, layer)
        if k:
            knees[layer] = k

    eligible = [c for c, a in cond_agg.items() if a["candidate_eligible"]]
    best = None
    if eligible:
        best = max(eligible, key=lambda c: cond_agg[c]["pph_median"])

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_runs": len(rows),
        "layers": sorted({r["layer"] for r in rows}),
        "runs": rows,
        "conditions": cond_agg,
        "knee_analysis": knees,
        "candidate_conditions": eligible,
        "best_candidate": best,
        "note": "recommendation only — configs/default.yaml is NOT modified by this script",
        "zero_datasets_rate": "unavailable per run (enforced at runtime by run_bulk gates; not re-aggregated here)",
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "phase6_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (args.out_dir / "phase6_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv_mod.writer(f)
        w.writerow(CSV_FIELDS)
        for r in rows:
            w.writerow([fmt_v(r.get(k)) for k in CSV_FIELDS])

    print_markdown(rows, cond_agg)
    if knees:
        print("\n## Layer-B knee analysis\n")
        for st in knees.get("B", {}).get("steps", []):
            print(f"- {st['from']} -> {st['to']}: pph_growth={fmt_v(st['pph_growth'])} "
                  f"llm_p95_ratio={fmt_v(st['llm_p95_ratio'])} near_knee={st['near_knee']}")
    print(f"\ncandidate conditions: {eligible or 'none'}")
    if best:
        print(f"best candidate (by median pph among eligible): {best} "
              f"({fmt_v(cond_agg[best]['pph_median'])} pph) — RECOMMENDATION ONLY")
    print(f"summary -> {args.out_dir / 'phase6_summary.json'}")
    print(f"csv     -> {args.out_dir / 'phase6_summary.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
