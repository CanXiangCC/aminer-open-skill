#!/usr/bin/env python3
"""v0.7 Phase 6 layered sweep runner (TODO-V07-07).

Single-layer execution: builds one config snapshot per experiment (frozen
semantic keys copied verbatim from configs/default.yaml; ONLY Class-B
scheduling parameters overridden), then invokes pipeline_cli.py run with a
phase6-* run_id, samples process-tree RSS alongside, snapshots LLM/BERT
service state before/after, and appends one provenance row per run to
pipeline_output/production/phase6/phase6_runs.jsonl.

Layers (see docs/V07_PHASE6_REPORT.md):
  smoke  A1/A2/A3 mechanics check on the smoke10 manifest (1 round each)
  A      scheduler/BERT-mode baseline: a1-def-chunk / a2-def-gb / a3-staged,
         llm=30 post=8 prep=4, 2 interleaved rounds (A1->A3->A2->A1->A3->A2)
  B      llm_concurrency sweep 30/64/128 (+192 opt-in) on a fixed mode,
         2 interleaved rounds
  C      post_workers sweep 4/8/16 on a fixed mode + fixed llm
  D      prep_workers sweep 2/4/8 (only when PREP proved a bottleneck)
  E      bert_batch_max_wait_ms 20/50/100 (limited contrast, NOT the final
         TODO-V07-09 capacity matrix)

Discipline (frozen by tests/test_phase6_sweep.py):
  - configs/default.yaml is NEVER written (read-only base)
  - semantic keys in every snapshot equal default.yaml verbatim
  - only Class-B keys may be overridden, within validated ranges
  - run ids unique; snapshots land under a gitignored runtime dir unless
    --emit-dir points elsewhere (configs/phase6 for committed provenance)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))

import yaml  # noqa: E402

DEFAULT_CONFIG = PROJ / "configs" / "default.yaml"
PIPELINE_CLI = PROJ / "scripts" / "pipeline_cli.py"
RUNS_ROOT = PROJ / "pipeline_output" / "production" / "runs"
LOGS_ROOT = PROJ / "pipeline_output" / "production" / "logs"
PHASE6_ROOT = PROJ / "pipeline_output" / "production" / "phase6"
DEFAULT_RUNTIME_EMIT_DIR = PHASE6_ROOT / "configs"
DEFAULT_MANIFEST = PROJ / "manifests" / "lilaoshi_aminer_p50"
SMOKE_MANIFEST = PROJ / "manifests" / "lilaoshi_aminer_smoke10"

# ------------------------------------------------------------------ parameter classes

# Class-B scheduling parameters: the ONLY keys a condition may override.
SWEEP_KEYS = {
    "scheduler_mode",
    "bert_pipeline_mode",
    "llm_concurrency",
    "post_workers",
    "prep_workers",
    "prep_queue_maxsize",
    "bert_queue_maxsize",
    "llm_queue_maxsize",
    "post_queue_maxsize",
    "write_queue_maxsize",
    "bert_batch_max_papers",
    "bert_batch_max_sentences",
    "bert_batch_max_chars",
    "bert_batch_max_wait_ms",
}

# (min, max) inclusive bounds for validated Class-B keys.
SWEEP_RANGES = {
    "llm_concurrency": (1, 256),
    "post_workers": (1, 64),
    "prep_workers": (1, 64),
    "prep_queue_maxsize": (1, 100_000),
    "bert_queue_maxsize": (0, 100_000),
    "llm_queue_maxsize": (1, 100_000),
    "post_queue_maxsize": (1, 100_000),
    "write_queue_maxsize": (1, 100_000),
    "bert_batch_max_papers": (1, 64),
    "bert_batch_max_sentences": (100, 10_000),
    "bert_batch_max_chars": (10_000, 1_000_000),
    "bert_batch_max_wait_ms": (1, 500),
}

# Semantic keys frozen at default.yaml values (temperature/num_predict live in
# the client, not YAML; enable_thinking/bert_threshold/bert_batch_size etc.
# ARE yaml keys and are covered by this check). Keys that default.yaml itself
# does not carry (mode keys, queue/worker/batch-budget keys, monitor flag) are
# structural and validated separately.
STRUCTURAL_KEYS = SWEEP_KEYS | {"write_per_paper_monitor", "pipeline_mode", "workflow"}

# Frozen defaults for the Phase-1 batch budgets: a snapshot must carry them
# verbatim except the single key a condition explicitly sweeps (layer E).
FROZEN_BATCH_BUDGETS = {
    "bert_batch_max_papers": 16,
    "bert_batch_max_sentences": 1500,
    "bert_batch_max_chars": 300000,
    "bert_batch_max_wait_ms": 20,
}

# Explicit stage topology written into every snapshot (Phase 2 first-pass
# values; the layer-specific sweep keys override the relevant subset).
STAGE_BASELINE = {
    "prep_queue_maxsize": 128,
    "bert_queue_maxsize": 0,
    "llm_queue_maxsize": 512,
    "post_queue_maxsize": 256,
    "write_queue_maxsize": 128,
    "prep_workers": 4,
    "post_workers": 8,
}

MODE_COMBO = {
    "def-chunk": {"scheduler_mode": "default", "bert_pipeline_mode": "chunked_overlap"},
    "def-gb": {"scheduler_mode": "default", "bert_pipeline_mode": "global_batch"},
    "staged": {"scheduler_mode": "staged", "bert_pipeline_mode": "global_batch"},
}


# ------------------------------------------------------------------ experiment matrix

def build_conditions(layer: str, *, mode: str = "staged", llm: int = 30,
                     post: int = 8) -> list[dict]:
    """Ordered experiment list for one layer. Each item:
    {"cond": str, "manifest": Path, "overrides": dict, "rounds": int}
    Interleaving is expressed by the ORDER of the returned list.
    """
    mode_combo = MODE_COMBO[mode]
    base = dict(STAGE_BASELINE)
    base.update(mode_combo)
    base["llm_concurrency"] = llm
    base["post_workers"] = post

    def _cond(name: str, manifest: Path, rounds: int, **over) -> dict:
        ov = dict(base)
        ov.update(over)
        return {"cond": name, "manifest": manifest, "rounds": rounds, "overrides": ov}

    if layer == "smoke":
        return [
            _cond("s-chunk", SMOKE_MANIFEST, 1, scheduler_mode="default",
                  bert_pipeline_mode="chunked_overlap"),
            _cond("s-gb", SMOKE_MANIFEST, 1, scheduler_mode="default",
                  bert_pipeline_mode="global_batch"),
            _cond("s-staged", SMOKE_MANIFEST, 1, scheduler_mode="staged",
                  bert_pipeline_mode="global_batch"),
        ]
    if layer == "A":
        ordered = []
        for round_no in (1, 2):
            for name in ("a1-def-chunk", "a3-staged", "a2-def-gb"):
                combo = {"a1-def-chunk": MODE_COMBO["def-chunk"],
                         "a2-def-gb": MODE_COMBO["def-gb"],
                         "a3-staged": MODE_COMBO["staged"]}[name]
                ov = dict(base)
                ov.update(combo)
                ov["llm_concurrency"] = 30
                ov["post_workers"] = 8
                ov["prep_workers"] = 4
                ordered.append({"cond": name, "manifest": DEFAULT_MANIFEST,
                                "rounds": 0, "overrides": ov, "round": round_no})
        return ordered
    if layer == "B":
        ordered = []
        for round_no in (1, 2):
            for q in (30, 64, 128):
                ordered.append({"cond": f"b-q{q}", "manifest": DEFAULT_MANIFEST,
                                "rounds": 0, "overrides": {**base, "llm_concurrency": q},
                                "round": round_no})
        return ordered
    if layer == "B192":
        ordered = []
        for round_no in (1, 2):
            ordered.append({"cond": "b-q192", "manifest": DEFAULT_MANIFEST,
                            "rounds": 0, "overrides": {**base, "llm_concurrency": 192},
                            "round": round_no})
        return ordered
    if layer == "B256":
        ordered = []
        for round_no in (1, 2):
            ordered.append({"cond": "b-q256", "manifest": DEFAULT_MANIFEST,
                            "rounds": 0, "overrides": {**base, "llm_concurrency": 256},
                            "round": round_no})
        return ordered
    if layer == "C":
        ordered = []
        for round_no in (1, 2):
            for p in (4, 8, 16):
                ordered.append({"cond": f"c-post{p}", "manifest": DEFAULT_MANIFEST,
                                "rounds": 0, "overrides": {**base, "post_workers": p},
                                "round": round_no})
        return ordered
    if layer == "D":
        ordered = []
        for round_no in (1, 2):
            for p in (2, 4, 8):
                ordered.append({"cond": f"d-prep{p}", "manifest": DEFAULT_MANIFEST,
                                "rounds": 0, "overrides": {**base, "prep_workers": p},
                                "round": round_no})
        return ordered
    if layer == "E":
        ordered = []
        for round_no in (1, 2):
            for w in (20, 50, 100):
                ordered.append({"cond": f"e-w{w}", "manifest": DEFAULT_MANIFEST,
                                "rounds": 0, "overrides": {**base, "bert_batch_max_wait_ms": w},
                                "round": round_no})
        return ordered
    raise SystemExit(f"unknown layer: {layer!r}")


# ------------------------------------------------------------------ snapshot build

def load_default_config() -> dict:
    return yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8")) or {}


def build_snapshot(default_cfg: dict, overrides: dict) -> dict:
    """Full config snapshot: default.yaml verbatim + monitor on + explicit
    structural keys + the condition's Class-B overrides. Deterministic."""
    snap = dict(default_cfg)
    snap["write_per_paper_monitor"] = True  # observability knob, not semantic
    snap.update(STAGE_BASELINE)
    snap.update(FROZEN_BATCH_BUDGETS)
    snap.update(MODE_COMBO["def-chunk"])  # explicit modes; overridden below
    snap.update(overrides)
    return snap


def validate_snapshot(snap: dict, default_cfg: dict, overrides: dict) -> None:
    """Raise on any discipline violation. Pure function (test-covered)."""
    # 1. overrides touch only Class-B keys
    bad = set(overrides) - SWEEP_KEYS
    if bad:
        raise ValueError(f"non-sweep key in overrides: {sorted(bad)}")
    # 2. values within ranges / enums
    for key, val in overrides.items():
        if key == "scheduler_mode":
            if val not in ("default", "staged"):
                raise ValueError(f"scheduler_mode invalid: {val!r}")
        elif key == "bert_pipeline_mode":
            if val not in ("chunked_overlap", "global_batch"):
                raise ValueError(f"bert_pipeline_mode invalid: {val!r}")
        else:
            lo, hi = SWEEP_RANGES[key]
            if not (lo <= int(val) <= hi):
                raise ValueError(f"{key}={val} out of range [{lo}, {hi}]")
    # 3. staged requires global_batch
    if snap.get("scheduler_mode") == "staged" and snap.get("bert_pipeline_mode") != "global_batch":
        raise ValueError("staged requires global_batch")
    # 4. semantic keys identical to default.yaml
    for key, val in default_cfg.items():
        if key in STRUCTURAL_KEYS or key in SWEEP_KEYS:
            continue
        if snap.get(key) != val:
            raise ValueError(f"semantic key drifted: {key}: {snap.get(key)!r} != {val!r}")
    # 5. batch budgets frozen unless explicitly swept
    for key, frozen in FROZEN_BATCH_BUDGETS.items():
        if key in overrides:
            continue
        if snap.get(key) != frozen:
            raise ValueError(f"batch budget drifted: {key}: {snap.get(key)!r} != {frozen!r}")
    # 6. queue/worker topology frozen unless the layer sweeps it
    for key, frozen in STAGE_BASELINE.items():
        if key in overrides:
            continue
        if snap.get(key) != frozen:
            raise ValueError(f"stage baseline drifted: {key}: {snap.get(key)!r} != {frozen!r}")


def snapshot_text(snap: dict) -> str:
    return yaml.safe_dump(snap, allow_unicode=True, sort_keys=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ service snapshot

def service_snapshot(cfg: dict, timeout: float = 10.0) -> dict:
    """Read-only LLM /models + BERT /health + /stats. Raises on failure."""
    import requests

    chat_url = cfg.get("llm_api_url") or ""
    llm_base = chat_url[: -len("/chat/completions")] if chat_url.endswith("/chat/completions") else chat_url
    bert_base = (cfg.get("bert_server_url") or "").rstrip("/")
    out: dict = {"taken_at_utc": _utc()}
    r = requests.get(f"{llm_base}/models", timeout=timeout)
    r.raise_for_status()
    out["llm_models"] = [m.get("id") for m in r.json().get("data", [])]
    r = requests.get(f"{bert_base}/health", timeout=timeout)
    r.raise_for_status()
    out["bert_health"] = r.json()
    r = requests.get(f"{bert_base}/stats", timeout=timeout)
    r.raise_for_status()
    out["bert_stats"] = r.json()
    # GPU utilization / per-instance vLLM health are NOT exposed by the
    # backend -> recorded as unavailable; never inferred.
    out["gpu_utilization"] = "unavailable"
    out["llm_instance_health"] = "unavailable"
    return out


# ------------------------------------------------------------------ RSS sampler

def _proc_tree_stats(root_pid: int) -> dict | None:
    """Sum VmRSS over root_pid and all descendants; max threads seen."""
    try:
        tasks = Path("/proc").glob("[0-9]*/stat")
        ppid_of: dict[int, int] = {}
        rss_kb: dict[int, int] = {}
        threads: dict[int, int] = {}
        for t in tasks:
            try:
                raw = t.read_text(encoding="utf-8")
            except OSError:
                continue
            # pid (comm) state ppid ... — comm may contain spaces
            close = raw.rfind(")")
            fields = raw[close + 2:].split()
            pid = int(raw[: raw.index("(")])
            ppid_of[pid] = int(fields[1])
            # stat(5) after comm: [0]=state [1]=ppid ... [17]=num_threads
            # [20]=vsize(bytes) [21]=rss(pages)
            rss_kb[pid] = int(fields[21]) * 4  # pages -> KB (4 KiB pages)
            threads[pid] = int(fields[17])
    except Exception:  # noqa: BLE001
        return None
    if root_pid not in ppid_of:
        return None
    keep, frontier = set(), [root_pid]
    while frontier:
        p = frontier.pop()
        if p in keep:
            continue
        keep.add(p)
        frontier.extend(c for c, pp in ppid_of.items() if pp == p)
    return {
        "rss_kb": sum(rss_kb[p] for p in keep),
        "threads": max(threads[p] for p in keep),
        "procs": len(keep),
    }


class RssSampler:
    """Background process-tree sampler; CSV rows ts,pid,rss_kb,threads,procs."""

    def __init__(self, pid: int, out_csv: Path, interval: float = 2.0) -> None:
        self.pid = pid
        self.out_csv = out_csv
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.samples = 0

    def _run(self) -> None:
        self.out_csv.parent.mkdir(parents=True, exist_ok=True)
        new = not self.out_csv.exists()
        with self.out_csv.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["ts_utc", "pid", "rss_kb", "threads", "procs"])
            while not self._stop.is_set():
                st = _proc_tree_stats(self.pid)
                if st is None:
                    break
                w.writerow([_utc(), self.pid, st["rss_kb"], st["threads"], st["procs"]])
                f.flush()
                self.samples += 1
                self._stop.wait(self.interval)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> dict:
        self._stop.set()
        self._thread.join(timeout=self.interval + 5)
        return self.summarize()

    def summarize(self) -> dict:
        rows = []
        if self.out_csv.exists():
            with self.out_csv.open(newline="", encoding="utf-8") as f:
                rows = [r for r in csv.DictReader(f) if r.get("rss_kb")]
        if not rows:
            return {"samples": 0}
        rss = sorted(int(r["rss_kb"]) for r in rows)
        thr = [int(r["threads"]) for r in rows if r.get("threads")]
        return {
            "samples": len(rss),
            "rss_mb_max": round(rss[-1] / 1024, 1),
            "rss_mb_mean": round(sum(rss) / len(rss) / 1024, 1),
            "rss_mb_first": round(rss[0] / 1024, 1),
            "growth_rss_mb_first_to_max": round((rss[-1] - rss[0]) / 1024, 1),
            "threads_max": max(thr) if thr else None,
        }


# ------------------------------------------------------------------ provenance log

def append_run_record(record: dict, jsonl_path: Path) -> None:
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(PROJ), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ execution

def expand_runs(conditions: list[dict]) -> list[dict]:
    """Expand interleaved conditions into an ordered run list."""
    runs = []
    for c in conditions:
        if c.get("round"):
            runs.append({"cond": c["cond"], "manifest": c["manifest"],
                         "overrides": c["overrides"], "round": c["round"]})
        else:
            for r in range(1, c["rounds"] + 1):
                runs.append({"cond": c["cond"], "manifest": c["manifest"],
                             "overrides": c["overrides"], "round": r})
    return runs


def run_id_for(cond: str, round_no: int, date: str) -> str:
    return f"phase6-{cond}-r{round_no}-{date}"


def execute_run(run: dict, *, layer: str, date: str, emit_dir: Path,
                skip_service_snapshot: bool = False) -> dict:
    """Build snapshot, run pipeline_cli, sample RSS, append record. Returns record."""
    default_cfg = load_default_config()
    overrides = run["overrides"]
    snap = build_snapshot(default_cfg, overrides)
    validate_snapshot(snap, default_cfg, overrides)

    run_id = run_id_for(run["cond"], run["round"], date)
    emit_dir.mkdir(parents=True, exist_ok=True)
    snap_path = emit_dir / f"{run_id}.yaml"
    text = snapshot_text(snap)
    snap_path.write_text(text, encoding="utf-8")
    config_sha = sha256_text(text)

    record: dict = {
        "run_id": run_id,
        "layer": layer,
        "condition": run["cond"],
        "round": run["round"],
        "manifest_dir": str(run["manifest"]),
        "snapshot_path": str(snap_path),
        "config_sha256": config_sha,
        "git_commit": git_commit(),
        "started_at_utc": _utc(),
        "mode": {"scheduler_mode": snap["scheduler_mode"],
                 "bert_pipeline_mode": snap["bert_pipeline_mode"]},
        "sweep_params": {k: snap[k] for k in sorted(overrides)},
        "gpu_metrics": "unavailable",
    }

    if not skip_service_snapshot:
        record["service_before"] = service_snapshot(snap)

    rss_csv = PHASE6_ROOT / "rss" / f"{run_id}.csv"
    argv = [sys.executable, str(PIPELINE_CLI), "run",
            "--config", str(snap_path),
            "--manifest-dir", str(run["manifest"]),
            "--run-id", run_id,
            "--session-id", run_id]
    print(f"[phase6] RUN {run_id}: {' '.join(argv[3:])}", flush=True)
    t0 = time.time()
    proc = subprocess.Popen(argv)
    sampler = RssSampler(proc.pid, rss_csv, interval=2.0)
    sampler.start()
    try:
        exit_code = proc.wait()
    finally:
        rss_summary = sampler.stop()
    record["ended_at_utc"] = _utc()
    record["wall_sec"] = round(time.time() - t0, 1)
    record["exit_code"] = exit_code
    record["rss"] = rss_summary

    if not skip_service_snapshot:
        try:
            record["service_after"] = service_snapshot(snap)
        except Exception as exc:  # noqa: BLE001
            record["service_after_error"] = f"{type(exc).__name__}: {exc}"

    # absorb pipeline_cli's own summary (manifest hash, derived-config hash,
    # totals, schema violations) when present
    cli_summary_path = LOGS_ROOT / run_id / "cli_summary.json"
    if cli_summary_path.exists():
        try:
            cs = json.loads(cli_summary_path.read_text(encoding="utf-8"))
            record["cli_status"] = cs.get("status")
            record["manifest_sha256"] = cs.get("manifest_sha256")
            record["derived_config_sha256"] = cs.get("config_sha256")
            for k in ("total_ok", "total_error", "total_skipped", "bulk_wall_sec",
                      "papers_per_hour", "schema_violations", "planned_papers"):
                if cs.get(k) is not None:
                    record[k] = cs.get(k)
        except Exception as exc:  # noqa: BLE001
            record["cli_summary_error"] = f"{type(exc).__name__}: {exc}"
    else:
        record["cli_status"] = "cli_summary_missing"

    append_run_record(record, PHASE6_ROOT / "phase6_runs.jsonl")
    print(f"[phase6] DONE {run_id}: exit={exit_code} status={record.get('cli_status')} "
          f"pph={record.get('papers_per_hour')} rss_max={record['rss'].get('rss_mb_max')}MB", flush=True)
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layer", required=True,
                    choices=["smoke", "A", "B", "B192", "B256", "C", "D", "E"])
    ap.add_argument("--mode", default="staged", choices=["def-chunk", "def-gb", "staged"],
                    help="fixed scheduler/BERT mode for layers B/C/D/E")
    ap.add_argument("--llm", type=int, default=30,
                    help="fixed llm_concurrency for layers C/D/E")
    ap.add_argument("--post", type=int, default=8,
                    help="fixed post_workers for layers B/D/E")
    ap.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y%m%d"),
                    help="run_id date suffix (default: today UTC)")
    ap.add_argument("--emit-dir", type=Path, default=DEFAULT_RUNTIME_EMIT_DIR,
                    help="where config snapshots are written (gitignored runtime "
                         "dir by default; pass configs/phase6 to materialize "
                         "committed provenance copies)")
    ap.add_argument("--dry-run", action="store_true",
                    help="build + validate snapshots and print the run plan; "
                         "no service calls, no execution")
    ap.add_argument("--skip-service-snapshot", action="store_true")
    args = ap.parse_args()

    conditions = build_conditions(args.layer, mode=args.mode, llm=args.llm, post=args.post)
    runs = expand_runs(conditions)

    default_cfg = load_default_config()
    plan = []
    for run in runs:
        snap = build_snapshot(default_cfg, run["overrides"])
        validate_snapshot(snap, default_cfg, run["overrides"])
        rid = run_id_for(run["cond"], run["round"], args.date)
        plan.append((rid, run["overrides"]))
    run_ids = [p[0] for p in plan]
    if len(set(run_ids)) != len(run_ids):
        raise SystemExit("run_id collision in plan")
    # rounds of the SAME condition legitimately share one snapshot; hashes
    # must be unique per distinct condition, not per run
    hash_by_cond: dict[str, str] = {}
    for (rid, ov) in plan:
        cond = rid.rsplit("-r", 1)[0]
        h = sha256_text(snapshot_text(build_snapshot(default_cfg, ov)))
        if hash_by_cond.setdefault(cond, h) != h:
            raise SystemExit(f"config snapshot hash drift within condition {cond}")

    print(f"[phase6] layer={args.layer} runs={len(plan)} mode={args.mode} "
          f"llm={args.llm} post={args.post} date={args.date}")
    for rid, ov in plan:
        swept = {k: v for k, v in ov.items() if k in (
            "scheduler_mode", "bert_pipeline_mode", "llm_concurrency",
            "post_workers", "prep_workers", "bert_batch_max_wait_ms")}
        print(f"[phase6]   {rid}  {swept}")

    if args.dry_run:
        args.emit_dir.mkdir(parents=True, exist_ok=True)
        for rid, ov in plan:
            snap = build_snapshot(default_cfg, ov)
            (args.emit_dir / f"{rid}.yaml").write_text(snapshot_text(snap), encoding="utf-8")
        print(f"[phase6] dry-run: {len(plan)} snapshots written to {args.emit_dir}")
        return 0

    consecutive_failures = 0
    for run in runs:
        record = execute_run(run, layer=args.layer, date=args.date,
                             emit_dir=args.emit_dir,
                             skip_service_snapshot=args.skip_service_snapshot)
        ok = record.get("exit_code") == 0 and record.get("cli_status") in ("success", "partial_success")
        consecutive_failures = 0 if ok else consecutive_failures + 1
        if consecutive_failures >= 2:
            print("[phase6] two consecutive failed runs — aborting layer", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
