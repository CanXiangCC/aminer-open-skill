#!/usr/bin/env python3
"""Long-lived AI2000 bulk runner: loop job_batches, window md, gates."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

from pipeline.evaluation.md_resolver import ensure_cached  # noqa: E402
from pipeline.production.batch_bert_pipeline_wf4 import (  # noqa: E402
    BatchBertPipelineSchedulerWf4,
)
from pipeline.production.config import EVAL_MD_CACHE_DIR, RUNS_DIR  # noqa: E402
from pipeline.production import compaction  # noqa: E402
from pipeline.production.run_paths import (  # noqa: E402
    format_job_run_id,
    job_batch_run_dir,
    prediction_ok,
    session_run_dir,
)
from pipeline.production.workflows.spec import get_workflow  # noqa: E402

STOP = threading.Event()
LOGS_ROOT = PROD_ROOT / "pipeline_output" / "production" / "logs"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")

# Cleared at startup so requests to LAN BERT/LLM do not go through a local proxy.
_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
)


def _clear_proxy_env() -> dict[str, str]:
    """Unset proxy env vars; set NO_PROXY for BERT/LLM hosts. Returns cleared map."""
    cleared: dict[str, str] = {}
    for k in _PROXY_ENV_KEYS:
        if k in os.environ:
            cleared[k] = os.environ.pop(k)
    # Always bypass proxy for loopback/localhost hosts (service hosts are
    # deployment-specific; add yours to NO_PROXY if you sit behind a proxy).
    extra = "127.0.0.1,localhost"
    prev = os.environ.get("NO_PROXY") or os.environ.get("no_proxy") or ""
    merged = ",".join(x for x in (prev, extra) if x)
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged
    return cleared


def _ts_pair() -> tuple[str, str]:
    """Return (local Asia/Shanghai, UTC) timestamp strings."""
    now_utc = datetime.now(timezone.utc)
    local = now_utc.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S%z")
    # +0800 -> +08:00 for readability
    if len(local) >= 5 and local[-5] in "+-" and local[-3] != ":":
        local = f"{local[:-2]}:{local[-2:]}"
    utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    return local, utc


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class BulkSessionLog:
    """Session log directory; bulk.log is append-only and multi-process safe (pid-tagged)."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.pid = os.getpid()
        self.dir = LOGS_ROOT / session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "bulk.log"
        self._lock = threading.Lock()
        # Append only — do not truncate (allows multiple processes to share one bulk.log).
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def write_session_json(self, meta: dict[str, Any]) -> None:
        # Per-pid session fingerprint to avoid multi-process clobber.
        path = self.dir / f"session.pid{self.pid}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        # Also refresh a latest pointer for humans.
        latest = self.dir / "session.json"
        tmp2 = latest.with_suffix(".tmp")
        tmp2.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp2, latest)

    def line(self, msg: str = "", *, also_print: bool = True, level: str = "INFO") -> None:
        local, utc = _ts_pair()
        # Distinct per-process tag so interleaved writers are obvious.
        prefix = f"{local} | {utc} | pid={self.pid} | {level}"
        text = f"{prefix} | {msg}" if msg else prefix
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(text + "\n")
        if also_print:
            print(text if msg else "", flush=True)

    def section(self, title: str) -> None:
        self.line("")
        self.line(f"=== {title} ===")

    def process_begin(self, detail: str = "") -> None:
        bar = "#" * 72
        self.line(bar)
        self.line(f"PROCESS START pid={self.pid}  {detail}".rstrip())
        self.line(bar)

    def process_end(self, detail: str = "") -> None:
        bar = "#" * 72
        self.line(bar)
        self.line(f"PROCESS END pid={self.pid}  {detail}".rstrip())
        self.line(bar)

    def write_job_summary(self, job_batch_id: str, summary: dict[str, Any]) -> None:
        summary = {**summary, "pid": self.pid}
        path = self.dir / f"{job_batch_id}.pid{self.pid}.summary.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)


def _load_config(path: Path) -> dict[str, Any]:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg["bert_server_url"] = os.environ.get("BERT_SERVER_URL") or cfg.get("bert_server_url")
    cfg["llm_api_url"] = os.environ.get("LLM_CHAT_URL") or cfg.get("llm_api_url")
    cfg["llm_model"] = os.environ.get("LLM_MODEL") or cfg.get("llm_model_tag")
    return cfg


def _bert_axis_warn(cfg: dict[str, Any], config_path: Path) -> str | None:
    """WARN text when an explicit snapshot config omits bert_axis.

    l4 lesson (V07-13 §15): a snapshot missing bert_axis silently falls back
    to flat-50 in _bert_axis_flags, shifting every kept-set (cap 60→50) without
    failing any gate. default.yaml always carries the key, so only explicit
    snapshot paths can trigger this.
    """
    if "bert_axis" in cfg:
        return None
    if Path(config_path).resolve() == (PROD_ROOT / "configs" / "default.yaml").resolve():
        return None
    return (
        f"config {config_path} has no 'bert_axis'; run_bulk will default to "
        "bert-flat-50 (sentence cap 50, NOT the production flat-60). Add an "
        "explicit bert_axis to the snapshot."
    )


def _load_vendor_meta() -> dict[str, Any]:
    p = PROD_ROOT / "VENDOR_MANIFEST.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _prediction_ok(session_run_id: str, job_batch_id: str, paper_id: str) -> bool:
    # Kept as a thin alias so call sites stay unchanged; see run_paths.prediction_ok.
    return prediction_ok(session_run_id, job_batch_id, paper_id)


def _normalize_job_batch_id(raw: str) -> str:
    s = raw.strip()
    if s.startswith("job_batch_"):
        return s
    if s.isdigit():
        return f"job_batch_{int(s):03d}"
    return s


def _list_job_batches(manifest_dir: Path, start_from: str | None) -> list[Path]:
    paths = sorted(manifest_dir.glob("job_batch_*.json"))
    if not start_from:
        return paths
    out = []
    started = False
    norm = _normalize_job_batch_id(start_from)
    for p in paths:
        if p.stem == norm or p.stem == start_from or p.name.startswith(start_from):
            started = True
        if started:
            out.append(p)
    if not out:
        raise SystemExit(f"--start-from {start_from} matched no manifests in {manifest_dir}")
    return out


def _resolve_job_batch_paths(manifest_dir: Path, job_batch_ids: list[str]) -> list[Path]:
    paths: list[Path] = []
    for raw in job_batch_ids:
        jid = _normalize_job_batch_id(raw)
        p = manifest_dir / f"{jid}.json"
        if not p.exists():
            raise SystemExit(f"manifest not found for --job-batches {raw!r}: {p}")
        paths.append(p)
    return paths


def _merge_exports(job_run_ids: list[str], *, blog: BulkSessionLog, label: str = "merge") -> None:
    if not job_run_ids:
        return
    cmd = [
        sys.executable,
        str(PROD_ROOT / "scripts" / "merge_exports.py"),
        "--format",
        "flat",
    ]
    for rid in job_run_ids:
        cmd.extend(["--run-id", rid])
    blog.line(f"  {label}: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(PROD_ROOT), check=False)


def _load_job_batch(path: Path) -> tuple[str, list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    jid = data.get("job_batch_id") or path.stem
    papers = data.get("papers") or []
    return jid, papers


def _smoke_papers(n: int, csv_path: Path) -> list[dict]:
    rows: list[dict] = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            pid = (r.get("id") or "").strip()
            url = (r.get("md_url") or "").strip()
            if pid and url:
                rows.append({"paper_id": pid, "md_url": url})
            if len(rows) >= n:
                break
    return rows


def _run_id_predictions_alive(run_id: str) -> bool:
    """True when the job_batch run dir still holds at least one per-paper
    prediction file (False after compaction deleted them)."""
    session_run_id, _, jid = run_id.partition("/")
    pred_dir = RUNS_DIR / session_run_id / jid / "predictions"
    return bool(list(pred_dir.glob("*.json"))) if pred_dir.is_dir() else False


def _maybe_compact_after_batch(
    cfg: dict, session_run_id: str, *, blog: "BulkSessionLog"
) -> None:
    """Batch-boundary compaction hook (TODO-V07-11). Code default 0 =
    disabled; default.yaml opts in at 20000. Runs AFTER the small-batch
    merge so the just-finished batch's files are merged while alive."""
    every = int(cfg.get("compaction_every_n_papers", 0))
    if every <= 0:
        return
    result = compaction.maybe_compact(session_run_id, every, log=blog.line)
    if result is not None:
        blog.line(f"  compaction result: {result}")


def _cleanup_md_cache(paper_ids: list[str], cache_dir: Path) -> dict[str, int]:
    """Delete cached md files for the given paper_ids after a job_batch completes."""
    deleted = 0
    missing = 0
    bytes_freed = 0
    for pid in paper_ids:
        path = cache_dir / f"{pid}.md"
        if not path.exists():
            missing += 1
            continue
        try:
            nbytes = path.stat().st_size
            path.unlink()
            deleted += 1
            bytes_freed += nbytes
        except OSError:
            pass
    return {"deleted": deleted, "missing": missing, "bytes_freed": bytes_freed}


def _fetch_one_md(
    item: dict, cache_dir: Path, retries: int
) -> tuple[str, Path | None, str | None]:
    """Fetch one paper's md into cache_dir with retries. Shared by the window
    batch prefetch and the rolling continuous prefetch (TODO-V07-10)."""
    pid = item["paper_id"]
    url = item["md_url"]
    last_err = None
    for attempt in range(max(1, retries)):
        try:
            path, err = ensure_cached(pid, url, cache_dir)
            if path is not None and Path(path).exists() and Path(path).stat().st_size > 0:
                return pid, Path(path), None
            last_err = err or "empty_or_missing_cache"
        except Exception as exc:  # noqa: BLE001
            last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(min(2**attempt, 8))
    return pid, None, last_err or "md_fetch_failed"


def _window_prefetch(
    papers: list[dict],
    cache_dir: Path,
    *,
    concurrency: int,
    retries: int,
) -> tuple[dict[str, Path], dict[str, str]]:
    """Fetch md for papers with bounded concurrency. Returns paths + errors."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    resolved: dict[str, Path] = {}
    errors: dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        futs = [ex.submit(_fetch_one_md, p, cache_dir, retries) for p in papers]
        for fut in as_completed(futs):
            pid, path, err = fut.result()
            if path is not None:
                resolved[pid] = path
            else:
                errors[pid] = err or "md_fetch_failed"
    return resolved, errors


def _classify_error(err: str | None) -> str:
    if not err:
        return "ok"
    e = err.lower()
    if "md" in e or "fetch" in e or "404" in e:
        return "md_fetch"
    if "bert" in e or "filter/batch" in e:
        return "bert"
    if "timeout" in e:
        return "llm_timeout"
    if "429" in e or "http" in e or "status" in e:
        return "llm_http"
    if "parse" in e:
        return "parse_error"
    if "post" in e or "ml" in e:
        return "post_llm"
    return "other"


def _classify_result(r: Any) -> dict[str, Any]:
    """Per-result classification shared by the window batch absorb and the
    rolling terminal callback — identical counters/progress fields in both
    admission modes (TODO-V07-10)."""
    pid = getattr(r, "paper_id", None) or (r.monitor.get("paper_id") if r.monitor else None)
    mon = getattr(r, "monitor", None) or {}
    ps = mon.get("pipeline_stages") or {}
    # parse_error from extractors
    pe = False
    ds_count = None
    for e in mon.get("extractors") or []:
        if "wf4" in str(e.get("extractor_id", "")) and "datasets" in str(e.get("extractor_id", "")):
            meta = e.get("metadata") or {}
            pe = bool(meta.get("parse_error"))
            if meta.get("datasets_count") is not None:
                ds_count = int(meta["datasets_count"])
    err = getattr(r, "error", None)
    cls = None
    if err:
        cls = _classify_error(str(err))
        if cls == "ok":
            cls = "other"
    exps = getattr(r, "experiments", None) or []
    return {
        "paper_id": pid,
        "has_error": bool(err),
        "error": err,
        "error_class": cls,
        "parse_error": pe,
        "datasets_count": ds_count,
        "zero_experiments": (not err) and len(exps) == 0,
        "llm_elapsed_sec": ps.get("llm_elapsed_sec"),
    }


def _absorb_result(stats: dict[str, Any], info: dict[str, Any]) -> str:
    """Fold one classified result into a stats dict
    (ok/error/parse_errors/zero_datasets/zero_experiments/error_classes);
    returns the progress-row status ("ok" | "error")."""
    if info["parse_error"]:
        stats["parse_errors"] += 1
        stats["error_classes"]["parse_error"] += 1
    if info["has_error"]:
        stats["error"] += 1
        cls = info["error_class"]
        if cls != "parse_error":
            stats["error_classes"][cls] = stats["error_classes"].get(cls, 0) + 1
        return "error"
    stats["ok"] += 1
    if info["datasets_count"] == 0:
        stats["zero_datasets"] += 1
    if info["zero_experiments"]:
        stats["zero_experiments"] += 1
    return "ok"


def _bert_axis_flags(cfg: dict[str, Any]) -> tuple[bool, bool, int]:
    """Resolve bert_axis -> (bert_flat_50, bert_flat_60, flat_max_sentences)."""
    axis = cfg.get("bert_axis", "bert-flat-50")
    # bert-flat-N shares one path; N is the LLM sentence cap (50/60/80/...).
    m = re.fullmatch(r"bert-flat-(\d+)", str(axis or ""))
    if m:
        flat_max = int(m.group(1))
        # flat-60+ (incl. 80) enable the raised-cap flat path + num_ctx headroom.
        return flat_max == 50, flat_max >= 60, flat_max
    return False, False, 60


def _scheduler_kwargs(cfg: dict[str, Any]) -> dict[str, Any]:
    """Scheduler kwargs shared by window and rolling admission paths."""
    _bert_flat_50, _bert_flat_60, flat_max = _bert_axis_flags(cfg)
    return dict(
        llm_concurrency=int(cfg.get("llm_concurrency", 10)),
        bert_batch_size=int(cfg.get("bert_batch_size", 32)),
        bert_flat_50=_bert_flat_50,
        bert_flat_60=_bert_flat_60,
        bert_flat_max_sentences=flat_max,
        llm_backend=cfg.get("llm_backend", "openai_chat"),
        llm_api_url=cfg.get("llm_api_url"),
        llm_model=cfg.get("llm_model_tag"),
        llm_timeout=int(cfg.get("llm_timeout", 30)),
        bert_server_url=cfg.get("bert_server_url"),
        bert_pipeline_batch_size=int(cfg.get("bert_pipeline_batch_size", 10)),
        bert_timeout=int(cfg.get("bert_timeout", 30)) if cfg.get("bert_timeout") is not None else None,
        bert_retries=int(cfg.get("bert_retries", 2)) if cfg.get("bert_retries") is not None else None,
        bert_pipeline_mode=str(cfg.get("bert_pipeline_mode", "chunked_overlap")),
        bert_batch_max_papers=int(cfg.get("bert_batch_max_papers", 16)),
        bert_batch_max_sentences=int(cfg.get("bert_batch_max_sentences", 1500)),
        bert_batch_max_chars=int(cfg.get("bert_batch_max_chars", 300000)),
        bert_batch_max_wait_ms=int(cfg.get("bert_batch_max_wait_ms", 20)),
        bert_endpoint_concurrency=int(cfg.get("bert_endpoint_concurrency", 1)),
    )


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _check_gates(rates: dict[str, float], gates: dict[str, Any]) -> list[str]:
    failed = []
    for key in ("error_rate", "parse_error_rate", "zero_datasets_rate"):
        if key in gates and rates.get(key, 0.0) > float(gates[key]):
            failed.append(f"{key}={rates[key]:.4f}>{gates[key]}")
    return failed


def _run_window(
    *,
    paper_items: list[dict],
    session_run_id: str,
    job_batch_id: str,
    cfg: dict[str, Any],
    force: bool,
) -> dict[str, Any]:
    job_run_dir = job_batch_run_dir(session_run_id, job_batch_id)
    job_run_id = format_job_run_id(session_run_id, job_batch_id)
    cache_dir = EVAL_MD_CACHE_DIR
    to_run = []
    skipped = 0
    for item in paper_items:
        pid = item["paper_id"]
        if not force and _prediction_ok(session_run_id, job_batch_id, pid):
            skipped += 1
            continue
        to_run.append(item)

    md_paths, md_errors = _window_prefetch(
        to_run,
        cache_dir,
        concurrency=int(cfg.get("md_fetch_concurrency", 8)),
        retries=int(cfg.get("md_fetch_retries", 3)),
    )

    error_classes = {
        "md_fetch": 0,
        "bert": 0,
        "llm_timeout": 0,
        "llm_http": 0,
        "parse_error": 0,
        "post_llm": 0,
        "other": 0,
    }
    for pid, err in md_errors.items():
        error_classes["md_fetch"] += 1
        _append_jsonl(
            job_run_dir / "progress.jsonl",
            {
                "ts": _utc(),
                "run_id": job_run_id,
                "session_run_id": session_run_id,
                "job_batch_id": job_batch_id,
                "paper_id": pid,
                "status": "error",
                "error_class": "md_fetch",
                "error": err,
            },
        )

    runnable_ids = [p["paper_id"] for p in to_run if p["paper_id"] in md_paths]
    md_for_sched = {pid: md_paths[pid] for pid in runnable_ids}

    results = []
    batch_monitor = None
    if runnable_ids:
        spec = get_workflow(cfg.get("workflow", "prod-wf4-llm-datasets-experiment"))
        scheduler_mode = str(cfg.get("scheduler_mode", "default"))
        if scheduler_mode not in ("default", "staged"):
            raise SystemExit(
                f"config error: scheduler_mode must be 'default' or 'staged' (got {scheduler_mode!r})"
            )
        if scheduler_mode == "staged" and str(
            cfg.get("bert_pipeline_mode", "chunked_overlap")
        ) != "global_batch":
            raise SystemExit(
                "config error: scheduler_mode=staged requires bert_pipeline_mode=global_batch"
            )
        sched_kwargs = _scheduler_kwargs(cfg)
        if scheduler_mode == "staged":
            from pipeline.production.staged_pipeline_wf4 import StagedPipelineWf4

            sched = StagedPipelineWf4(
                runnable_ids,
                md_for_sched,
                job_run_id,
                spec,
                scheduler_mode="staged",
                prep_queue_maxsize=int(cfg.get("prep_queue_maxsize", 128)),
                bert_queue_maxsize=int(cfg.get("bert_queue_maxsize", 0)) or None,
                llm_queue_maxsize=int(cfg.get("llm_queue_maxsize", 512)),
                post_queue_maxsize=int(cfg.get("post_queue_maxsize", 256)),
                write_queue_maxsize=int(cfg.get("write_queue_maxsize", 128)),
                prep_workers=int(cfg.get("prep_workers", 4)),
                post_workers=int(cfg.get("post_workers", 8)),
                **sched_kwargs,
            )
        else:
            sched = BatchBertPipelineSchedulerWf4(
                runnable_ids, md_for_sched, job_run_id, spec, **sched_kwargs
            )
        results = sched.run()
        batch_monitor = sched.batch_monitor

    wstats = {
        "ok": 0,
        "error": 0,
        "parse_errors": 0,
        "zero_datasets": 0,
        "zero_experiments": 0,
        "error_classes": error_classes,
    }
    for r in results:
        info = _classify_result(r)
        status = _absorb_result(wstats, info)
        _append_jsonl(
            job_run_dir / "progress.jsonl",
            {
                "ts": _utc(),
                "run_id": job_run_id,
                "session_run_id": session_run_id,
                "job_batch_id": job_batch_id,
                "paper_id": info["paper_id"],
                "status": status,
                "error": info["error"],
                "llm_elapsed_sec": info["llm_elapsed_sec"],
            },
        )
    ok = wstats["ok"]
    err = wstats["error"]
    parse_errors = wstats["parse_errors"]
    zero_ds = wstats["zero_datasets"]
    zero_exp = wstats["zero_experiments"]

    attempted = len(to_run)
    denom = max(1, attempted)
    rates = {
        "error_rate": (err + len(md_errors)) / denom,
        "parse_error_rate": parse_errors / denom,
        "zero_datasets_rate": zero_ds / max(1, ok) if ok else (1.0 if attempted else 0.0),
        # EXT-02 monitoring only — not a gate key
        "zero_experiment_rate": zero_exp / max(1, ok) if ok else 0.0,
    }
    return {
        "attempted": attempted,
        "ok": ok,
        "error": err + len(md_errors),
        "skipped": skipped,
        "parse_errors": parse_errors,
        "zero_datasets": zero_ds,
        "zero_experiments": zero_exp,
        "error_classes": error_classes,
        "rates": rates,
        "batch_monitor": batch_monitor,
    }


# ------------------------------------------------- rolling admission (TODO-V07-10)


def _validate_admission_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Validate admission config; returns resolved admission info.

    admission_mode: window (default, byte-identical legacy path) | rolling.
    rolling requires scheduler_mode=staged + bert_pipeline_mode=global_batch,
    rolling_target >= 1, and md_prefetch_lookahead (default
    rolling_target + 2*md_fetch_concurrency) >= rolling_target."""
    mode = str(cfg.get("admission_mode", "window") or "window")
    if mode not in ("window", "rolling"):
        raise SystemExit(
            f"config error: admission_mode must be 'window' or 'rolling' (got {mode!r})"
        )
    info: dict[str, Any] = {"admission_mode": mode}
    if mode == "rolling":
        if str(cfg.get("scheduler_mode", "default")) != "staged":
            raise SystemExit("config error: admission_mode=rolling requires scheduler_mode=staged")
        if str(cfg.get("bert_pipeline_mode", "chunked_overlap")) != "global_batch":
            raise SystemExit(
                "config error: admission_mode=rolling requires bert_pipeline_mode=global_batch"
            )
        target = int(cfg.get("rolling_target", 0) or 0)
        if target < 1:
            raise SystemExit("config error: admission_mode=rolling requires rolling_target >= 1")
        md_conc = int(cfg.get("md_fetch_concurrency", 8))
        raw_look = cfg.get("md_prefetch_lookahead")
        lookahead = int(raw_look) if raw_look else target + 2 * md_conc
        if lookahead < target:
            raise SystemExit(
                "config error: md_prefetch_lookahead must be >= rolling_target "
                f"(got {lookahead} < {target})"
            )
        info["rolling_target"] = target
        info["md_prefetch_lookahead"] = lookahead
    return info


class _RollingMdPrefetch:
    """Continuous bounded-ahead MD prefetch for rolling admission.

    Holds the full ordered paper table + a cursor; always keeps about
    ``lookahead`` un-resolved papers submitted to a fixed executor. Papers
    whose prediction is already durable (skip_check) never enter the pool.
    Completion order never changes admission order: resolve_next() resolves
    the cursor paper and only advances on it."""

    def __init__(
        self,
        paper_items: list[dict],
        cache_dir: Path,
        *,
        lookahead: int,
        concurrency: int,
        retries: int,
        skip_check,
    ) -> None:
        self._items = list(paper_items)
        self._cache_dir = cache_dir
        self._lookahead = max(1, int(lookahead))
        self._retries = int(retries)
        self._skip_check = skip_check  # pid -> bool (already durable)
        self._ex = ThreadPoolExecutor(max_workers=max(1, concurrency))
        self._lock = threading.Lock()
        self._futs: dict[int, Any] = {}
        self._skip_idx: set[int] = set()
        self._next_submit = 0
        self._cursor = 0
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _top_up_locked(self) -> None:
        while (
            self._next_submit < len(self._items)
            and self._next_submit < self._cursor + self._lookahead
        ):
            i = self._next_submit
            self._next_submit += 1
            if self._skip_check(self._items[i]["paper_id"]):
                self._skip_idx.add(i)
                continue
            self._futs[i] = self._ex.submit(_fetch_one_md, self._items[i], self._cache_dir, self._retries)

    def start(self) -> None:
        with self._lock:
            self._top_up_locked()

    @property
    def cursor(self) -> int:
        with self._lock:
            return self._cursor

    def has_next(self) -> bool:
        with self._lock:
            return self._cursor < len(self._items)

    def resolve_next(self) -> tuple[dict, str, Any]:
        """Resolve the cursor paper. Returns (item, outcome, detail) with
        outcome in {"skip", "md_error", "ok"}; detail is None / the error
        string / the cached md Path."""
        with self._lock:
            i = self._cursor
            if i >= len(self._items):
                raise RuntimeError("resolve_next() called past the end of the paper table")
            fut = self._futs.get(i)
            skipped = i in self._skip_idx
        item = self._items[i]
        path: Path | None = None
        err: str | None = None
        if not skipped:
            if fut is None:  # defensive: cursor paper was never submitted
                with self._lock:
                    fut = self._futs.get(i)
                    if fut is None:
                        fut = self._ex.submit(
                            _fetch_one_md, item, self._cache_dir, self._retries
                        )
                        self._futs[i] = fut
            _, path, err = fut.result()  # blocks until the cursor paper is ready
        with self._lock:
            self._cursor += 1
            self._top_up_locked()
        if skipped:
            return item, "skip", None
        if path is not None:
            return item, "ok", path
        return item, "md_error", err or "md_fetch_failed"

    def close(self) -> None:
        self._ex.shutdown(wait=True)


class _RollingBatchController:
    """Single owner of rolling admission credits + job_batch-level stats.

    All counters mutate under one condition-var lock; in_flight = admitted -
    terminal; terminal covers pipeline durable terminals AND MD failures (an
    MD failure takes a credit and returns it immediately — it never enters
    the scheduler). Progress rows are written exactly once per paper: at MD
    error time or at the scheduler's durable-terminal callback. Rolling stats
    come solely from this controller — run() results are never re-iterated."""

    def __init__(
        self,
        *,
        session_run_id: str,
        job_batch_id: str,
        job_run_id: str,
        progress_path: Path,
        target: int,
    ) -> None:
        self._cv = threading.Condition()
        self.target = int(target)
        self._session_run_id = session_run_id
        self._job_batch_id = job_batch_id
        self._job_run_id = job_run_id
        self._progress_path = progress_path
        self._t0 = time.perf_counter()
        self.attempted = 0
        self.skipped = 0
        self.ok = 0
        self.error = 0
        self.parse_errors = 0
        self.zero_datasets = 0
        self.zero_experiments = 0
        self.error_classes: dict[str, int] = {
            "md_fetch": 0,
            "bert": 0,
            "llm_timeout": 0,
            "llm_http": 0,
            "parse_error": 0,
            "post_llm": 0,
            "other": 0,
        }
        self.admitted = 0
        self.terminal = 0
        self.cursor = 0
        self.md_failures = 0
        self._terminal_seen: set[str] = set()

    # ------------------------------------------------------------ credits
    def in_flight(self) -> int:
        with self._cv:
            return self.admitted - self.terminal

    def wait_for_credit(self, stop: threading.Event | None = None, poll: float = 0.5) -> bool:
        """Block until in_flight < target. Returns False only if `stop` fired."""
        with self._cv:
            while self.admitted - self.terminal >= self.target:
                if stop is not None and stop.is_set():
                    return False
                self._cv.wait(poll)
            return True

    def _notify_terminal_locked(self) -> None:
        self.terminal += 1
        self._cv.notify_all()

    # ------------------------------------------------------------ events
    def note_cursor(self, cursor: int) -> None:
        with self._cv:
            self.cursor = cursor

    def record_skip(self, pid: str) -> None:
        with self._cv:
            self.skipped += 1

    def take_credit(self, pid: str) -> None:
        with self._cv:
            self.admitted += 1
            self.attempted += 1

    def record_md_failure(self, pid: str, err: str) -> None:
        """MD fetch failed at the cursor: take + immediately return a credit
        (net in_flight 0), count the error, write the progress row once."""
        with self._cv:
            if pid in self._terminal_seen:
                return
            self._terminal_seen.add(pid)
            self.admitted += 1
            self.attempted += 1
            self.md_failures += 1
            self.error += 1
            self.error_classes["md_fetch"] += 1
            self._notify_terminal_locked()
        _append_jsonl(
            self._progress_path,
            {
                "ts": _utc(),
                "run_id": self._job_run_id,
                "session_run_id": self._session_run_id,
                "job_batch_id": self._job_batch_id,
                "paper_id": pid,
                "status": "error",
                "error_class": "md_fetch",
                "error": err,
            },
        )

    def record_admit_failure(self, pid: str, err: str) -> None:
        """admit_paper() raised after its internal rollback: treat as an
        immediate terminal error so the credit and cursor still balance."""
        with self._cv:
            if pid in self._terminal_seen:
                return
            self._terminal_seen.add(pid)
            self.error += 1
            self.error_classes["other"] += 1
            self._notify_terminal_locked()
        _append_jsonl(
            self._progress_path,
            {
                "ts": _utc(),
                "run_id": self._job_run_id,
                "session_run_id": self._session_run_id,
                "job_batch_id": self._job_batch_id,
                "paper_id": pid,
                "status": "error",
                "error": f"admit: {err}",
                "llm_elapsed_sec": None,
            },
        )

    def on_pipeline_terminal(self, pid: str, result: Any) -> None:
        """Scheduler durable-terminal callback (writer commit / defensive
        finalize). Single stats source for rolling runs."""
        with self._cv:
            if pid in self._terminal_seen:
                return
            self._terminal_seen.add(pid)
        info = _classify_result(result)
        stats = {
            "ok": 0,
            "error": 0,
            "parse_errors": 0,
            "zero_datasets": 0,
            "zero_experiments": 0,
            "error_classes": self.error_classes,
        }
        status = _absorb_result(stats, info)
        row = {
            "ts": _utc(),
            "run_id": self._job_run_id,
            "session_run_id": self._session_run_id,
            "job_batch_id": self._job_batch_id,
            "paper_id": pid,
            "status": status,
            "error": info["error"],
            "llm_elapsed_sec": info["llm_elapsed_sec"],
        }
        with self._cv:
            self.ok += stats["ok"]
            self.error += stats["error"]
            self.parse_errors += stats["parse_errors"]
            self.zero_datasets += stats["zero_datasets"]
            self.zero_experiments += stats["zero_experiments"]
            self._notify_terminal_locked()
        _append_jsonl(self._progress_path, row)

    # ------------------------------------------------------------ views
    def snapshot(self) -> dict[str, Any]:
        with self._cv:
            return {
                "attempted": self.attempted,
                "skipped": self.skipped,
                "ok": self.ok,
                "error": self.error,
                "parse_errors": self.parse_errors,
                "zero_datasets": self.zero_datasets,
                "zero_experiments": self.zero_experiments,
                "error_classes": dict(self.error_classes),
                "admitted": self.admitted,
                "terminal": self.terminal,
                "in_flight": self.admitted - self.terminal,
                "rolling_target": self.target,
                "cursor": self.cursor,
                "md_failures": self.md_failures,
            }

    def heartbeat_state(self, sched_snap: dict[str, Any]) -> dict[str, Any]:
        """Merge controller snapshot + scheduler sampler peaks; disk IO is the
        caller's business (never under this lock)."""
        state = self.snapshot()
        pph_cum = None
        done = self.ok + self.error
        elapsed = time.perf_counter() - self._t0
        if elapsed > 0 and done:
            pph_cum = done / elapsed * 3600.0
        state["queue_depth_max"] = dict(sched_snap.get("queue_depth_max") or {})
        state["stage_active_peak"] = dict(sched_snap.get("stage_active_peak") or {})
        state["pph_cum"] = round(pph_cum, 2) if pph_cum is not None else None
        return state

    def stats(self, *, batch_monitor: dict[str, Any] | None = None) -> dict[str, Any]:
        snap = self.snapshot()
        attempted = snap["attempted"]
        denom = max(1, attempted)
        ok = snap["ok"]
        rates = {
            "error_rate": snap["error"] / denom,
            "parse_error_rate": snap["parse_errors"] / denom,
            "zero_datasets_rate": (
                snap["zero_datasets"] / max(1, ok) if ok else (1.0 if attempted else 0.0)
            ),
            # EXT-02 monitoring only — not a gate key
            "zero_experiment_rate": snap["zero_experiments"] / max(1, ok) if ok else 0.0,
        }
        return {
            "attempted": attempted,
            "ok": ok,
            "error": snap["error"],
            "skipped": snap["skipped"],
            "parse_errors": snap["parse_errors"],
            "zero_datasets": snap["zero_datasets"],
            "zero_experiments": snap["zero_experiments"],
            "error_classes": snap["error_classes"],
            "rates": rates,
            "batch_monitor": batch_monitor,
            "admission": {
                "admission_mode": "rolling",
                "rolling_target": snap["rolling_target"],
                "admitted": snap["admitted"],
                "terminal": snap["terminal"],
                "in_flight": snap["in_flight"],
                "md_failures": snap["md_failures"],
                "cursor": snap["cursor"],
            },
        }


def _run_window_rolling(
    *,
    paper_items: list[dict],
    session_run_id: str,
    job_batch_id: str,
    cfg: dict[str, Any],
    force: bool,
    heartbeat_ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One job_batch under rolling admission (TODO-V07-10).

    Resident staged runtime + credit loop: skip durable-done papers, resolve
    MD at the cursor, admit while in_flight < rolling_target, release on each
    durable terminal. Stats come solely from the controller callbacks."""
    from pipeline.production.staged_pipeline_wf4 import StagedPipelineWf4

    if str(cfg.get("scheduler_mode", "default")) != "staged" or str(
        cfg.get("bert_pipeline_mode", "chunked_overlap")
    ) != "global_batch":
        raise SystemExit(
            "config error: admission_mode=rolling requires scheduler_mode=staged "
            "+ bert_pipeline_mode=global_batch"
        )
    target = int(cfg.get("rolling_target") or 0)
    raw_look = cfg.get("md_prefetch_lookahead")
    lookahead = int(raw_look) if raw_look else target + 2 * int(cfg.get("md_fetch_concurrency", 8))
    if target < 1 or lookahead < target:
        raise SystemExit(
            "config error: rolling_target >= 1 and md_prefetch_lookahead >= rolling_target required"
        )

    job_run_dir = job_batch_run_dir(session_run_id, job_batch_id)
    job_run_id = format_job_run_id(session_run_id, job_batch_id)
    cache_dir = EVAL_MD_CACHE_DIR

    controller = _RollingBatchController(
        session_run_id=session_run_id,
        job_batch_id=job_batch_id,
        job_run_id=job_run_id,
        progress_path=job_run_dir / "progress.jsonl",
        target=target,
    )
    prefetch = _RollingMdPrefetch(
        paper_items,
        cache_dir,
        lookahead=lookahead,
        concurrency=int(cfg.get("md_fetch_concurrency", 8)),
        retries=int(cfg.get("md_fetch_retries", 3)),
        skip_check=(lambda pid: False)
        if force
        else (lambda pid: _prediction_ok(session_run_id, job_batch_id, pid)),
    )

    def _heartbeat(sched_snap: dict[str, Any]) -> None:
        if heartbeat_ctx is None:
            return
        state = controller.heartbeat_state(sched_snap)
        pph = state.pop("pph_cum", None)
        state.update(
            {
                "session_id": heartbeat_ctx["session_id"],
                "pid": heartbeat_ctx["pid"],
                "log_dir": heartbeat_ctx["log_dir"],
                "session_run_id": session_run_id,
                "run_id": job_run_id,
                "job_batch_id": job_batch_id,
                "status": "running",
                "axis": heartbeat_ctx.get("axis"),
                "llm_concurrency": heartbeat_ctx.get("llm_concurrency"),
                "papers_total": len(paper_items),
                "papers_per_hour": pph,
                "heartbeat_at": _utc(),
            }
        )
        _write_json(heartbeat_ctx["bulk_state_path"], state)
        _write_json(heartbeat_ctx["job_run_dir"] / "job_checkpoint.json", state)

    spec = get_workflow(cfg.get("workflow", "prod-wf4-llm-datasets-experiment"))
    sched = StagedPipelineWf4(
        [],
        {},
        job_run_id,
        spec,
        rolling=True,
        rolling_target=target,
        on_paper_terminal=controller.on_pipeline_terminal,
        rolling_heartbeat_cb=_heartbeat,
        prep_queue_maxsize=int(cfg.get("prep_queue_maxsize", 128)),
        bert_queue_maxsize=int(cfg.get("bert_queue_maxsize", 0)) or None,
        llm_queue_maxsize=int(cfg.get("llm_queue_maxsize", 512)),
        post_queue_maxsize=int(cfg.get("post_queue_maxsize", 256)),
        write_queue_maxsize=int(cfg.get("write_queue_maxsize", 128)),
        prep_workers=int(cfg.get("prep_workers", 4)),
        post_workers=int(cfg.get("post_workers", 8)),
        **_scheduler_kwargs(cfg),
    )

    sched.start_rolling()
    prefetch.start()
    stopped = False
    while prefetch.has_next():
        if STOP.is_set():
            stopped = True
            break
        item, outcome, detail = prefetch.resolve_next()
        pid = item["paper_id"]
        controller.note_cursor(prefetch.cursor)
        if outcome == "skip":
            controller.record_skip(pid)
            continue
        if outcome == "md_error":
            controller.record_md_failure(pid, detail)
            continue
        if not controller.wait_for_credit(stop=STOP):
            stopped = True
            break
        controller.take_credit(pid)
        try:
            sched.admit_paper(pid, detail)
        except Exception as exc:  # noqa: BLE001 — admission rolled back; keep going
            controller.record_admit_failure(pid, f"{type(exc).__name__}: {exc}")

    # Cursor exhausted (or STOP): unchanged sentinel/drain + defensive pass.
    sched.finish_rolling_input()  # results deliberately unused: controller is the stats source
    prefetch.close()
    st = controller.stats(batch_monitor=sched.batch_monitor)
    st["stopped"] = stopped
    return st


class _ManifestFeeder:
    """Batch-boundary feeder over the startup batch snapshot.

    Default (watch=False): yields the startup snapshot in order, once —
    byte-identical to the legacy ``for`` loop over the materialized list.
    With watch=True: when the queue drains, re-glob the manifest dir and
    append unseen job_batch_*.json to the tail (sorted order => tail append;
    ingest numbering is monotonic), polling every poll_interval until
    watch_idle_timeout idle seconds elapse. Bounded: never blocks forever.
    """

    def __init__(
        self,
        batches: list,
        *,
        manifest_dir: Path | None,
        session_run_id: str,
        watch: bool,
        poll_interval: float,
        idle_timeout: float,
        log=None,
    ) -> None:
        self._queue = list(batches)
        self._pos = 0
        self._seen = {jid for jid, _, _ in batches}
        self._manifest_dir = manifest_dir
        # files already on disk at startup: rescan must never add them back
        # (e.g. batches a --start-from run deliberately skipped past)
        self._startup_files = (
            {p.name for p in manifest_dir.glob("job_batch_*.json")}
            if manifest_dir is not None
            else set()
        )
        self._session_run_id = session_run_id
        self._watch = watch
        self._poll = max(0.05, float(poll_interval))
        self._idle_timeout = float(idle_timeout)
        self._log = log
        self._idle_since: float | None = None
        self.rescans = 0

    def total(self) -> int:
        return len(self._queue)

    def _line(self, msg: str, level: str = "INFO") -> None:
        if self._log is not None:
            self._log.line(msg, level=level)

    def _rescan(self) -> int:
        if self._manifest_dir is None:
            return 0
        self.rescans += 1
        added = []
        for p in sorted(self._manifest_dir.glob("job_batch_*.json")):
            if p.stem in self._seen or p.name in self._startup_files:
                continue
            try:
                jid, papers = _load_job_batch(p)
            except Exception as exc:  # noqa: BLE001 — a bad new file must not kill the run
                self._line(f"watch rescan: skipping unreadable {p.name}: {exc}", level="WARN")
                continue
            self._seen.add(jid)
            self._queue.append((jid, papers, self._session_run_id))
            added.append(jid)
        if added:
            self._line(f"watch rescan: +{len(added)} new batch(es) appended to queue tail: {added}")
        return len(added)

    def next_batch(self):
        """Return (jid, papers, session_run_id, batch_i) or None when done."""
        while True:
            if self._pos < len(self._queue):
                self._pos += 1
                jid, papers, srid = self._queue[self._pos - 1]
                return jid, papers, srid, self._pos
            if not self._watch or STOP.is_set():
                return None
            if self._rescan() > 0:
                self._idle_since = None
                continue
            now = time.monotonic()
            if self._idle_since is None:
                self._idle_since = now
                self._line(
                    f"watch: queue empty, polling every {self._poll}s "
                    f"(idle timeout {self._idle_timeout}s)"
                )
            if now - self._idle_since >= self._idle_timeout:
                self._line("watch: idle timeout reached with no new batch, finishing")
                return None
            time.sleep(self._poll)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=PROD_ROOT / "configs" / "default.yaml")
    ap.add_argument("--manifest-dir", type=Path, default=PROD_ROOT / "manifests" / "job_batches")
    ap.add_argument("--start-from", type=str, default=None, help="job_batch_NNN")
    ap.add_argument(
        "--job-batches",
        action="append",
        default=None,
        help="explicit job_batch list in run order (repeatable; e.g. job_batch_006 or 006)",
    )
    ap.add_argument("--max-job-batches", type=int, default=None)
    ap.add_argument("--smoke", type=int, default=0, help="run first N papers from CSV then exit")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-gate", action="store_true")
    ap.add_argument("--run-id", type=str, default=None, help="session run id (parent folder under runs/)")
    ap.add_argument("--date", type=str, default=None, help="YYYYMMDD for run_id")
    ap.add_argument(
        "--session-id",
        type=str,
        default=None,
        help="log session dir name under pipeline_output/production/logs/",
    )
    ap.add_argument(
        "--no-md-cache-cleanup",
        action="store_true",
        help="keep md_cache files after each job_batch (overrides config md_cache_cleanup_on_batch_done)",
    )
    ap.add_argument(
        "--watch-manifest",
        action="store_true",
        help="after the startup batch queue drains, re-scan --manifest-dir at batch "
        "boundaries and append newly published job_batch_*.json to the queue tail; "
        "exit after watch-idle-timeout seconds with no new batch (default: process the "
        "startup snapshot once and exit, legacy behavior)",
    )
    ap.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="seconds between manifest re-scans while watching an empty queue",
    )
    ap.add_argument(
        "--watch-idle-timeout",
        type=float,
        default=600.0,
        help="watch mode exits after this many idle seconds without a new batch (bounded; "
        "never blocks forever)",
    )
    args = ap.parse_args()
    if args.job_batches and args.start_from:
        ap.error("use --job-batches OR --start-from, not both")
    if args.watch_manifest and args.job_batches:
        ap.error("--watch-manifest is incompatible with an explicit --job-batches list")
    if args.watch_manifest and args.smoke:
        ap.error("--watch-manifest is incompatible with --smoke")

    cleared_proxy = _clear_proxy_env()

    cfg = _load_config(args.config)
    admission_info = _validate_admission_config(cfg)
    vendor = _load_vendor_meta()
    if cfg.get("write_per_paper_monitor") is False:
        os.environ["PROD_SKIP_PAPER_MONITOR"] = "1"

    session_id = args.session_id or f"bulk-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    blog = BulkSessionLog(session_id)

    def _handle_sigint(signum, frame):  # noqa: ARG001
        blog.line("SIGINT: will stop after current pipeline_batch...", level="WARN")
        STOP.set()

    signal.signal(signal.SIGINT, _handle_sigint)
    if hasattr(signal, "SIGTERM"):
        try:
            signal.signal(signal.SIGTERM, _handle_sigint)
        except Exception:
            pass

    bulk_state_path = PROD_ROOT / "pipeline_output" / "production" / "bulk_state.json"
    date_str = args.date or datetime.now(timezone.utc).strftime("%Y%m%d")
    session_run_id = args.run_id or f"prod-bulk-{date_str}"
    t0 = time.perf_counter()
    total_ok = total_err = total_skip = 0
    jobs_done = 0
    n_batches_planned = 0

    # Smoke path: synthetic single job_batch
    if args.smoke and args.smoke > 0:
        csv_path = PROD_ROOT / "data" / "ai2000" / "ai2000_has_md_only.csv"
        papers = _smoke_papers(args.smoke, csv_path)
        jid = "job_batch_smoke"
        batches = [(jid, papers, session_run_id)]
    else:
        if args.job_batches:
            paths = _resolve_job_batch_paths(args.manifest_dir, args.job_batches)
        else:
            paths = _list_job_batches(args.manifest_dir, args.start_from)
        if args.max_job_batches is not None:
            paths = paths[: args.max_job_batches]
        batches = []
        for p in paths:
            jid, papers = _load_job_batch(p)
            batches.append((jid, papers, session_run_id))

    n_batches_planned = len(batches)
    window = int(cfg.get("md_prefetch_window", 30))
    merge_every = int(cfg.get("merge_every_n_job_batches", 5))
    gates = cfg.get("gates") or {}
    md_cache_cleanup = bool(cfg.get("md_cache_cleanup_on_batch_done", False)) and not args.no_md_cache_cleanup

    session_log_meta = {
        "session_id": session_id,
        "pid": blog.pid,
        "timezone_local": "Asia/Shanghai",
        "started_at_utc": _utc(),
        "started_at_local": _ts_pair()[0],
        "proxy_cleared": sorted(cleared_proxy.keys()),
        "no_proxy": os.environ.get("NO_PROXY"),
        "log_path": str(blog.path).replace("\\", "/"),
        "config_path": str(args.config).replace("\\", "/"),
        "manifest_dir": str(args.manifest_dir).replace("\\", "/"),
        "smoke": args.smoke or None,
        "start_from": args.start_from,
        "job_batches": args.job_batches,
        "max_job_batches": args.max_job_batches,
        "watch_manifest": bool(args.watch_manifest),
        "poll_interval_sec": args.poll_interval,
        "watch_idle_timeout_sec": args.watch_idle_timeout,
        "force": bool(args.force),
        "no_gate": bool(args.no_gate),
        "date": date_str,
        "session_run_id": session_run_id,
        "axis": cfg.get("bert_axis"),
        "bert_pipeline_batch_size": cfg.get("bert_pipeline_batch_size"),
        "bert_pipeline_mode": cfg.get("bert_pipeline_mode", "chunked_overlap"),
        "scheduler_mode": cfg.get("scheduler_mode", "default"),
        "staged_params": {
            k: cfg.get(k, d)
            for k, d in [
                ("prep_queue_maxsize", 128),
                ("bert_queue_maxsize", 0),
                ("llm_queue_maxsize", 512),
                ("post_queue_maxsize", 256),
                ("write_queue_maxsize", 128),
                ("prep_workers", 4),
                ("post_workers", 8),
                ]
            }
        if cfg.get("scheduler_mode") == "staged"
        else None,
        "bert_batch_max_papers": cfg.get("bert_batch_max_papers", 16),
        "bert_batch_max_sentences": cfg.get("bert_batch_max_sentences", 1500),
        "bert_batch_max_chars": cfg.get("bert_batch_max_chars", 300000),
        "bert_batch_max_wait_ms": cfg.get("bert_batch_max_wait_ms", 20),
        "bert_endpoint_concurrency": cfg.get("bert_endpoint_concurrency", 1),
        "llm_concurrency": cfg.get("llm_concurrency"),
        "bert_batch_size": cfg.get("bert_batch_size"),
        "bert_server_url": cfg.get("bert_server_url"),
        "llm_api_url": cfg.get("llm_api_url"),
        "llm_model_tag": cfg.get("llm_model_tag"),
        "bert_threshold": cfg.get("bert_threshold", 0.6),
        "md_prefetch_window": window,
        "job_batches_planned": n_batches_planned,
        "code_version": {
            "upstream_commit": vendor.get("upstream_commit"),
            "vendor_date": vendor.get("vendor_date"),
        },
    }
    if admission_info["admission_mode"] == "rolling":
        # Rolling-only key (see bulk_session.json above).
        session_log_meta["admission"] = {
            "admission_mode": admission_info["admission_mode"],
            "rolling_target": admission_info["rolling_target"],
            "md_prefetch_lookahead": admission_info["md_prefetch_lookahead"],
        }
    blog.write_session_json(session_log_meta)
    blog.process_begin(
        f"session={session_id} start_from={args.start_from} date={date_str} "
        f"batches={n_batches_planned}"
    )
    blog.section(f"bulk session {session_id}")
    blog.line(f"log: {blog.path}")
    blog.line(f"timezone: local=Asia/Shanghai + UTC dual-write; pid={blog.pid}")
    if cleared_proxy:
        blog.line(f"proxy cleared: {', '.join(sorted(cleared_proxy.keys()))}", level="WARN")
    else:
        blog.line("proxy: none set in env (NO_PROXY applied)")
    blog.line(f"NO_PROXY={os.environ.get('NO_PROXY')}")
    if "pipeline_mode" in cfg:
        # Known legacy no-op key (configs/default.yaml): the effective key is
        # bert_pipeline_mode. Warn so run artifacts never mislead.
        blog.line(
            f"WARNING: config key 'pipeline_mode={cfg['pipeline_mode']!r}' is a legacy "
            "no-op; effective mode key is bert_pipeline_mode="
            f"{cfg.get('bert_pipeline_mode', 'chunked_overlap')!r}",
            level="WARN",
        )
    bert_axis_warning = _bert_axis_warn(cfg, args.config)
    if bert_axis_warning:
        blog.line(f"WARNING: {bert_axis_warning}", level="WARN")
    blog.line(
        f"axis={cfg.get('bert_axis')} pipeline_batch={cfg.get('bert_pipeline_batch_size')} "
        f"bert_pipeline_mode={cfg.get('bert_pipeline_mode', 'chunked_overlap')} "
        f"scheduler_mode={cfg.get('scheduler_mode', 'default')} "
        f"bert_batch_max_papers={cfg.get('bert_batch_max_papers', 16)}/"
        f"sents={cfg.get('bert_batch_max_sentences', 1500)}/"
        f"chars={cfg.get('bert_batch_max_chars', 300000)}/"
        f"wait_ms={cfg.get('bert_batch_max_wait_ms', 20)} "
        f"bert_bs={cfg.get('bert_batch_size', 32)}/lanes={cfg.get('bert_endpoint_concurrency', 1)} "
        f"llm_c={cfg.get('llm_concurrency')} llm_timeout={cfg.get('llm_timeout', 30)}s "
        f"job_batches={n_batches_planned} md_cache_cleanup={md_cache_cleanup}"
    )
    if "admission_mode" in cfg:
        # Review item: make the effective admission mode explicit so run
        # snapshots never mislead (absent key = window, legacy default).
        if admission_info["admission_mode"] == "rolling":
            blog.line(
                f"admission_mode=rolling rolling_target={admission_info['rolling_target']} "
                f"md_prefetch_lookahead={admission_info['md_prefetch_lookahead']}"
            )
        else:
            blog.line(
                f"admission_mode={admission_info['admission_mode']} "
                "rolling_target=n/a md_prefetch_lookahead=n/a (windowed prefetch)"
            )
    blog.line(f"BERT={cfg.get('bert_server_url')}")
    blog.line(f"LLM={cfg.get('llm_api_url')}")
    blog.line(f"LLM model={cfg.get('llm_model')}")
    blog.line(f"session_run_id={session_run_id}")

    session_dir = session_run_dir(session_run_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    session_meta = {
        "session_id": session_id,
        "session_run_id": session_run_id,
        "started_at": _utc(),
        "date": date_str,
        "start_from": args.start_from,
        "job_batches": args.job_batches,
        "job_batches_planned": [jid for jid, _, _ in batches],
        "config_path": str(args.config).replace("\\", "/"),
        "bert_axis": cfg.get("bert_axis"),
        "llm_concurrency": cfg.get("llm_concurrency"),
        "bert_pipeline_batch_size": cfg.get("bert_pipeline_batch_size"),
        "bert_pipeline_mode": cfg.get("bert_pipeline_mode", "chunked_overlap"),
        "scheduler_mode": cfg.get("scheduler_mode", "default"),
    }
    if admission_info["admission_mode"] == "rolling":
        # Rolling-only key: window sessions keep the legacy shape (no
        # admission key at all, not an explicit null).
        session_meta["admission"] = {
            "admission_mode": admission_info["admission_mode"],
            "rolling_target": admission_info["rolling_target"],
            "md_prefetch_lookahead": admission_info["md_prefetch_lookahead"],
        }
    _write_json(
        session_dir / "bulk_session.json",
        session_meta,
    )

    exit_code = 0
    completed_job_run_ids: list[str] = []
    try:
        feeder = _ManifestFeeder(
            batches,
            manifest_dir=None if (args.smoke or args.job_batches) else args.manifest_dir,
            session_run_id=session_run_id,
            watch=bool(args.watch_manifest),
            poll_interval=args.poll_interval,
            idle_timeout=args.watch_idle_timeout,
            log=blog,
        )
        while True:
            _nxt = feeder.next_batch()
            if _nxt is None:
                break
            jid, papers, batch_session_run_id, batch_i = _nxt
            if STOP.is_set():
                break

            job_run_dir = job_batch_run_dir(batch_session_run_id, jid)
            job_run_id = format_job_run_id(batch_session_run_id, jid)

            blog.section(
                f"{jid}  session_run_id={batch_session_run_id}  job_run_id={job_run_id}  "
                f"papers={len(papers)}  batch {batch_i}/{feeder.total()}"
            )
            job_t0 = time.perf_counter()
            job_stats = {
                "attempted": 0,
                "ok": 0,
                "error": 0,
                "skipped": 0,
                "parse_errors": 0,
                "zero_datasets": 0,
                "error_classes": {
                    "md_fetch": 0,
                    "bert": 0,
                    "llm_timeout": 0,
                    "llm_http": 0,
                    "parse_error": 0,
                    "post_llm": 0,
                    "other": 0,
                },
            }
            last_monitor = None
            job_admission: dict[str, Any] | None = None

            def _log_window_failure(exc: Exception) -> None:
                traceback.print_exc()
                blog.line(f"  FAILED: {exc}", level="ERROR")
                resume_hint = (
                    f"  RESUME: --run-id {batch_session_run_id} --job-batches {jid} "
                    if args.job_batches
                    else f"  RESUME: --run-id {batch_session_run_id} --start-from {jid} "
                )
                blog.line(f"{resume_hint}--session-id {session_id}", level="ERROR")
                _write_json(
                    bulk_state_path,
                    {
                        "status": "failed",
                        "session_id": session_id,
                        "pid": blog.pid,
                        "log_dir": str(blog.dir).replace("\\", "/"),
                        "session_run_id": batch_session_run_id,
                        "run_id": job_run_id,
                        "job_batch_id": jid,
                        "error": str(exc),
                        "heartbeat_at": _utc(),
                    },
                )

            def _absorb_window(
                st: dict[str, Any],
                *,
                win_lo: int,
                win_hi: int,
                win_sec: float,
                rolling: bool = False,
            ) -> None:
                nonlocal last_monitor, job_admission
                # Instantaneous window throughput: processed papers in this window / win_sec
                win_done = int(st["ok"]) + int(st["error"]) + int(st["skipped"])
                pph_win = (win_done / win_sec * 3600.0) if win_sec > 0 else None

                for k in ("attempted", "ok", "error", "skipped", "parse_errors", "zero_datasets"):
                    job_stats[k] += st[k]
                for k, v in st["error_classes"].items():
                    job_stats["error_classes"][k] = job_stats["error_classes"].get(k, 0) + v
                last_monitor = st.get("batch_monitor") or last_monitor
                if rolling:
                    job_admission = st.get("admission") or job_admission

                elapsed = time.perf_counter() - t0
                done_papers = total_ok + total_err + job_stats["ok"] + job_stats["error"]
                pph_cum = (done_papers / elapsed * 3600.0) if elapsed > 0 else None
                denom = max(1, job_stats["attempted"])
                rates = {
                    "error_rate": job_stats["error"] / denom,
                    "parse_error_rate": job_stats["parse_errors"] / denom,
                    "zero_datasets_rate": (
                        job_stats["zero_datasets"] / max(1, job_stats["ok"])
                        if job_stats["ok"]
                        else 0.0
                    ),
                }
                label = "rolling done" if rolling else "window done"
                blog.line(
                    f"  {label}  win={win_lo}-{win_hi}  "
                    f"ok={st['ok']} err={st['error']} skip={st['skipped']}  "
                    f"job_ok={job_stats['ok']}/{len(papers)}  "
                    f"win_sec={win_sec:.1f}  "
                    f"pph_win={round(pph_win, 1) if pph_win is not None else 'n/a'}  "
                    f"pph_cum={round(pph_cum, 1) if pph_cum is not None else 'n/a'}"
                )
                state = {
                    "session_id": session_id,
                    "pid": blog.pid,
                    "log_dir": str(blog.dir).replace("\\", "/"),
                    "session_run_id": batch_session_run_id,
                    "run_id": job_run_id,
                    "job_batch_id": jid,
                    "status": "running",
                    "axis": cfg.get("bert_axis"),
                    "pipeline_mode": str(cfg.get("bert_pipeline_mode", "chunked_overlap")),
                    "bert_pipeline_batch_size": cfg.get("bert_pipeline_batch_size"),
                    "bert_batch_max_papers": cfg.get("bert_batch_max_papers", 16),
                    "bert_batch_max_sentences": cfg.get("bert_batch_max_sentences", 1500),
                    "bert_batch_max_chars": cfg.get("bert_batch_max_chars", 300000),
                    "bert_batch_max_wait_ms": cfg.get("bert_batch_max_wait_ms", 20),
                    "bert_endpoint_concurrency": cfg.get("bert_endpoint_concurrency", 1),
                    "llm_concurrency": cfg.get("llm_concurrency"),
                    "bert_batch_size": cfg.get("bert_batch_size"),
                    "bert_server_url": cfg.get("bert_server_url"),
                    "llm_api_url": cfg.get("llm_api_url"),
                    "llm_model_tag": cfg.get("llm_model_tag"),
                    "bert_threshold": cfg.get("bert_threshold", 0.6),
                    "code_version": {
                        "upstream_commit": vendor.get("upstream_commit"),
                        "vendor_date": vendor.get("vendor_date"),
                    },
                    "papers_total": len(papers),
                    "papers_ok": job_stats["ok"],
                    "papers_error": job_stats["error"],
                    "papers_skipped": job_stats["skipped"],
                    "error_classes": job_stats["error_classes"],
                    "rates": rates,
                    "heartbeat_at": _utc(),
                    "papers_per_hour": round(pph_cum, 2) if pph_cum is not None else None,
                    "pph_win": round(pph_win, 2) if pph_win is not None else None,
                    "win_sec": round(win_sec, 4),
                    "last_batch_monitor_mode": (last_monitor or {}).get("pipeline_mode"),
                }
                if rolling and st.get("admission"):
                    state["admission"] = st["admission"]
                _write_json(bulk_state_path, state)
                _write_json(job_run_dir / "job_checkpoint.json", state)

            if admission_info["admission_mode"] == "rolling":
                # One job_batch = one rolling pass over the full manifest (no
                # window loop): resident runtime + credit admission.
                if not STOP.is_set() and papers:
                    win_lo, win_hi = 0, len(papers) - 1
                    blog.line(
                        f"  rolling {win_lo}-{win_hi} prefetch+admit ...  "
                        f"job={batch_i}/{feeder.total()}"
                    )
                    win_t0 = time.perf_counter()
                    try:
                        st = _run_window_rolling(
                            paper_items=papers,
                            session_run_id=batch_session_run_id,
                            job_batch_id=jid,
                            cfg=cfg,
                            force=args.force,
                            heartbeat_ctx={
                                "session_id": session_id,
                                "pid": blog.pid,
                                "log_dir": str(blog.dir).replace("\\", "/"),
                                "bulk_state_path": bulk_state_path,
                                "job_run_dir": job_run_dir,
                                "axis": cfg.get("bert_axis"),
                                "llm_concurrency": cfg.get("llm_concurrency"),
                            },
                        )
                    except Exception as exc:  # noqa: BLE001
                        _log_window_failure(exc)
                        exit_code = 2
                        raise SystemExit(2) from exc
                    _absorb_window(
                        st,
                        win_lo=win_lo,
                        win_hi=win_hi,
                        win_sec=time.perf_counter() - win_t0,
                        rolling=True,
                    )
            else:
                for i in range(0, len(papers), window):
                    if STOP.is_set():
                        break
                    chunk = papers[i : i + window]
                    win_lo, win_hi = i, i + len(chunk) - 1
                    blog.line(
                        f"  window {win_lo}-{win_hi} prefetch+run ...  "
                        f"job={batch_i}/{feeder.total()}"
                    )
                    win_t0 = time.perf_counter()
                    try:
                        st = _run_window(
                            paper_items=chunk,
                            session_run_id=batch_session_run_id,
                            job_batch_id=jid,
                            cfg=cfg,
                            force=args.force,
                        )
                    except Exception as exc:  # noqa: BLE001
                        _log_window_failure(exc)
                        exit_code = 2
                        raise SystemExit(2) from exc
                    _absorb_window(
                        st,
                        win_lo=win_lo,
                        win_hi=win_hi,
                        win_sec=time.perf_counter() - win_t0,
                    )

            total_ok += job_stats["ok"]
            total_err += job_stats["error"]
            total_skip += job_stats["skipped"]
            jobs_done += 1

            denom = max(1, job_stats["attempted"])
            rates = {
                "error_rate": job_stats["error"] / denom,
                "parse_error_rate": job_stats["parse_errors"] / denom,
                "zero_datasets_rate": (
                    job_stats["zero_datasets"] / max(1, job_stats["ok"]) if job_stats["ok"] else 0.0
                ),
            }
            wall = time.perf_counter() - job_t0
            blog.line(
                f"  done {jid}: ok={job_stats['ok']} err={job_stats['error']} "
                f"skip={job_stats['skipped']} wall_sec={wall:.1f} rates={rates}"
            )

            if md_cache_cleanup and not STOP.is_set():
                cleanup = _cleanup_md_cache(
                    [p["paper_id"] for p in papers],
                    EVAL_MD_CACHE_DIR,
                )
                blog.line(
                    f"  md_cache_cleanup: deleted={cleanup['deleted']} "
                    f"missing={cleanup['missing']} "
                    f"freed_mb={cleanup['bytes_freed'] / (1024 * 1024):.1f}"
                )

            status = "done"
            if STOP.is_set():
                status = "stopped_sigint"
            gate_fails = [] if args.no_gate else _check_gates(rates, gates)
            job_summary = {
                "job_batch_id": jid,
                "session_run_id": batch_session_run_id,
                "run_id": job_run_id,
                "status": status if not gate_fails else "paused_gate",
                "papers_total": len(papers),
                "ok": job_stats["ok"],
                "error": job_stats["error"],
                "skipped": job_stats["skipped"],
                "rates": rates,
                "error_classes": job_stats["error_classes"],
                "job_wall_sec": round(wall, 4),
                "gate_failures": gate_fails,
                "finished_at": _utc(),
            }
            blog.write_job_summary(jid, job_summary)

            if gate_fails and status == "done":
                status = "paused_gate"
                state = {
                    "session_id": session_id,
                    "pid": blog.pid,
                    "log_dir": str(blog.dir).replace("\\", "/"),
                    "session_run_id": batch_session_run_id,
                    "run_id": job_run_id,
                    "job_batch_id": jid,
                    "status": status,
                    "gate_failures": gate_fails,
                    "rates": rates,
                    "heartbeat_at": _utc(),
                    "papers_ok": job_stats["ok"],
                    "papers_error": job_stats["error"],
                    "papers_skipped": job_stats["skipped"],
                    "error_classes": job_stats["error_classes"],
                }
                _write_json(bulk_state_path, state)
                _write_json(job_run_dir / "job_checkpoint.json", state)
                blog.line(f"GATE PAUSE: {gate_fails}", level="WARN")
                blog.line(f"See log: {blog.path}")
                exit_code = 3
                raise SystemExit(3)

            state = {
                "session_id": session_id,
                "pid": blog.pid,
                "log_dir": str(blog.dir).replace("\\", "/"),
                "session_run_id": batch_session_run_id,
                "run_id": job_run_id,
                "job_batch_id": jid,
                "status": status,
                "rates": rates,
                "heartbeat_at": _utc(),
                "papers_ok": job_stats["ok"],
                "papers_error": job_stats["error"],
                "papers_skipped": job_stats["skipped"],
                "error_classes": job_stats["error_classes"],
                "job_wall_sec": round(wall, 4),
                "total_wall_sec": round(time.perf_counter() - t0, 4),
            }
            if job_admission:
                # Rolling terminal checkpoint keeps the admission ledger the
                # heartbeat published mid-run (plan §5.1).
                state["admission"] = job_admission
            _write_json(bulk_state_path, state)
            _write_json(job_run_dir / "job_checkpoint.json", state)

            if status == "stopped_sigint":
                blog.line("stopped_sigint — checkpoint flushed", level="WARN")
                exit_code = 130
                raise SystemExit(130)

            if status == "done":
                completed_job_run_ids.append(job_run_id)

            if merge_every > 0 and jobs_done % merge_every == 0:
                _merge_exports([job_run_id], blog=blog)

            # TODO-V07-11: threshold-gated compaction at the batch boundary
            # (writer already joined). After the small-batch merge so the
            # just-finished batch merges while its files are alive.
            if status == "done" and not STOP.is_set():
                _maybe_compact_after_batch(cfg, batch_session_run_id, blog=blog)

        wall = time.perf_counter() - t0
        done_papers = total_ok + total_err
        pph = (done_papers / wall * 3600.0) if wall > 0 and done_papers else None
        final = {
            "status": "done",
            "session_id": session_id,
            "session_run_id": session_run_id,
            "pid": blog.pid,
            "log_dir": str(blog.dir).replace("\\", "/"),
            "jobs_done": jobs_done,
            "total_ok": total_ok,
            "total_error": total_err,
            "total_skipped": total_skip,
            "total_wall_sec": round(wall, 4),
            "papers_per_hour": round(pph, 2) if pph is not None else None,
            "heartbeat_at": _utc(),
        }
        _write_json(bulk_state_path, final)
        blog.section("BULK DONE")
        blog.line(
            f"jobs_done={jobs_done} ok={total_ok} err={total_err} skip={total_skip} "
            f"wall_sec={wall:.1f} pph_cum={final['papers_per_hour']}"
        )
        if completed_job_run_ids:
            alive = [rid for rid in completed_job_run_ids if _run_id_predictions_alive(rid)]
            compacted_away = len(completed_job_run_ids) - len(alive)
            if compacted_away:
                blog.line(
                    f"  final merge: skipping {compacted_away} compacted-away batch(es); "
                    f"compacted rows live in the stable flat: "
                    f"{(RUNS_DIR / session_run_id / 'compaction' / 'flat_experiments.json')}"
                )
            _merge_exports(alive, blog=blog, label="final merge")
        blog.line(f"log: {blog.path}")
        blog.process_end(f"exit=0 jobs_done={jobs_done}")
    except SystemExit as se:
        exit_code = int(se.code) if isinstance(se.code, int) else 1
        blog.process_end(f"exit={exit_code}")
        raise
    except Exception:
        exit_code = 1
        blog.process_end(f"exit={exit_code} unhandled")
        raise


if __name__ == "__main__":
    main()
