#!/usr/bin/env python3
"""Unified production CLI (v0.7 Phase 4, TODO-V07-05).

One entry point for the whole production line:

  check-services  -> LLM + BERT endpoint health/contract checks (no production run)
  prepare         -> passthrough to scripts/prepare_aminer_manifest_pub_id.py
  ingest          -> online CSV -> manifest incremental publish (Phase 5)
  run             -> validate -> service check -> bulk -> merge -> report (one shot)
  merge           -> passthrough to scripts/merge_flat_experiments.py
  report          -> passthrough to scripts/collect_phase_metrics.py

Design rules (docs/V07_PHASE45_REPORT.md):
  - Thin wrapper only: every stage delegates to existing scripts/modules;
    no pipeline logic is reimplemented here.
  - Config precedence: CLI flag > environment (BERT_SERVER_URL /
    LLM_CHAT_URL / LLM_MODEL, the only env keys run_bulk honors) > YAML
    config > code defaults inside run_bulk. The CLI folds that precedence
    itself into a derived config YAML passed to run_bulk, and scrubs the
    three env keys from the child process so run_bulk's env-overrides-yaml
    step cannot invert the precedence.
  - Default modes stay scheduler_mode=default + bert_pipeline_mode=
    chunked_overlap; staged requires global_batch (clear error, no silent
    downgrade — same rule run_bulk enforces at run time).
  - Semantic parameters (temperature/num_predict/enable_thinking/
    bert_threshold/bert_batch_size/...) are deliberately NOT exposed here.
  - Exit codes: 0 success; 1 service-check/manifest/merge failure;
    2 config/usage error; run_bulk's own codes (2 window failure, 3 gate
    pause, 130 SIGINT) propagate as-is.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
if str(PROD_ROOT) not in sys.path:
    sys.path.insert(0, str(PROD_ROOT))

import yaml  # noqa: E402

from pipeline.benchmark.config import BERT_SERVER_URL, LLM_MODEL  # noqa: E402

LOGS_ROOT = PROD_ROOT / "pipeline_output" / "production" / "logs"
EXPORTS_DIR = PROD_ROOT / "pipeline_output" / "production" / "exports"
BULK_STATE_PATH = PROD_ROOT / "pipeline_output" / "production" / "bulk_state.json"
RUN_BULK = PROD_ROOT / "scripts" / "run_bulk.py"
MERGE_FLAT = PROD_ROOT / "scripts" / "merge_flat_experiments.py"
COLLECT_METRICS = PROD_ROOT / "scripts" / "collect_phase_metrics.py"
PREPARE_AMINER = PROD_ROOT / "scripts" / "prepare_aminer_manifest_pub_id.py"

# The only env keys run_bulk lets override YAML (run_bulk._load_config).
ENV_OVERRIDES = {
    "bert_server_url": "BERT_SERVER_URL",
    "llm_api_url": "LLM_CHAT_URL",
    "llm_model_tag": "LLM_MODEL",
}
# CLI flags that override config (flag name -> (yaml key, argparse type)).
FLAG_OVERRIDES = {
    "scheduler_mode": ("scheduler_mode", str),
    "bert_pipeline_mode": ("bert_pipeline_mode", str),
    "llm_concurrency": ("llm_concurrency", int),
    "llm_timeout": ("llm_timeout", float),
    "post_workers": ("post_workers", int),
    "prep_workers": ("prep_workers", int),
}

# No built-in endpoint: set configs/default.yaml or the LLM_CHAT_URL env var.
DEFAULT_QWEN_CHAT_URL = ""

SCHEMA_ERR_RE = re.compile(r"schema-invalid experiments: \*\*(\d+)\*\*")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- config


def load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def resolve_config(args) -> dict:
    """CLI flag > env > YAML. Code defaults stay inside run_bulk (absent keys)."""
    cfg = load_yaml(Path(args.config))
    for key, env in ENV_OVERRIDES.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    for flag, (key, _typ) in FLAG_OVERRIDES.items():
        val = getattr(args, flag, None)
        if val is not None:
            cfg[key] = val
    return cfg


def effective_modes(cfg: dict) -> tuple[str, str]:
    return cfg.get("scheduler_mode", "default"), cfg.get("bert_pipeline_mode", "chunked_overlap")


def validate_modes(cfg: dict) -> None:
    sched, bpm = effective_modes(cfg)
    if sched not in ("default", "staged"):
        raise SystemExit(
            f"config error: scheduler_mode must be 'default' or 'staged' (got {sched!r})"
        )
    if bpm not in ("chunked_overlap", "global_batch"):
        raise SystemExit(
            "config error: bert_pipeline_mode must be 'chunked_overlap' or 'global_batch' "
            f"(got {bpm!r})"
        )
    if sched == "staged" and bpm != "global_batch":
        raise SystemExit(
            "config error: scheduler_mode=staged requires bert_pipeline_mode=global_batch "
            "(refusing to silently downgrade)"
        )


def write_derived_config(cfg: dict, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=True)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------------- manifest


def validate_manifest_dir(manifest_dir: Path) -> list[Path]:
    """All job_batch files parse and carry paper_id+md_url; else SystemExit(1)."""
    if not manifest_dir.is_dir():
        raise SystemExit(f"manifest dir not found: {manifest_dir}")
    files = sorted(manifest_dir.glob("job_batch_*.json"))
    if not files:
        raise SystemExit(f"no job_batch_*.json under {manifest_dir}")
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"manifest invalid ({f.name}): not parseable JSON: {exc}") from exc
        papers = data.get("papers")
        if not isinstance(papers, list) or not papers:
            raise SystemExit(f"manifest invalid ({f.name}): empty/missing 'papers'")
        for i, item in enumerate(papers):
            if not item.get("paper_id") or not item.get("md_url"):
                raise SystemExit(
                    f"manifest invalid ({f.name}): paper #{i} missing paper_id/md_url"
                )
    return files


def manifest_hash(files: list[Path]) -> str:
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode("utf-8"))
        h.update(f.read_bytes())
    return h.hexdigest()


def planned_papers(files: list[Path]) -> int:
    return sum(len(json.loads(f.read_text(encoding="utf-8"))["papers"]) for f in files)


# ------------------------------------------------------------------- service checks


def _qwen_base(chat_url: str) -> str:
    return chat_url[: -len("/chat/completions")] if chat_url.endswith("/chat/completions") else chat_url


def _check(name: str, fn) -> dict:
    t0 = time.perf_counter()
    try:
        detail = fn()
        return {
            "name": name,
            "ok": True,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "detail": detail,
        }
    except Exception as exc:  # noqa: BLE001 — report, never crash the checker
        return {
            "name": name,
            "ok": False,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            "error": f"{type(exc).__name__}: {exc}",
        }


def check_qwen(cfg: dict, timeout: float = 15.0) -> list[dict]:
    """One tiny chat completion via the production client (the only LLM API
    registered on the gateway; /models is not)."""
    from pipeline.benchmark.stages.openai_chat_llm_client import OpenAIChatLLMClient

    chat_url = cfg.get("llm_api_url") or DEFAULT_QWEN_CHAT_URL
    model = cfg.get("llm_model_tag") or LLM_MODEL

    def chat() -> str:
        client = OpenAIChatLLMClient(api_url=chat_url, timeout=int(timeout), default_model=model)
        out = client.generate("Reply with the single word: ok", num_predict=16)
        return f"reply={out.get('raw_output', '')[:40]!r} elapsed={out.get('elapsed_sec'):.2f}s"

    return [
        _check("llm POST /chat/completions", chat),
    ]


def check_bert(cfg: dict, timeout: float = 15.0) -> list[dict]:
    """/filter/batch via the production client (the only BERT API registered
    on the gateway; /health and /stats are not)."""
    from pipeline.production.adapters.bert_batch_client import filter_papers_batch

    base = (cfg.get("bert_server_url") or BERT_SERVER_URL).rstrip("/")
    threshold = float(cfg.get("bert_threshold", 0.6))

    def filt_batch() -> str:
        d = filter_papers_batch(
            [{"paper_id": "svc-check", "sentences": ["service check sentence one.", "another sentence."]}],
            threshold=threshold,
            batch_size=32,
            url=base,
            timeout=int(timeout),
            retries=0,
        )
        return f"papers={d.get('paper_count')} sentences={d.get('total_sentences')}"

    return [
        _check("bert POST /filter/batch", filt_batch),
    ]


def run_service_checks(cfg: dict, only: str, timeout: float) -> tuple[list[dict], bool]:
    results: list[dict] = []
    if only in ("llm", "all"):
        results += check_qwen(cfg, timeout)
    if only in ("bert", "all"):
        results += check_bert(cfg, timeout)
    return results, all(r["ok"] for r in results)


# ------------------------------------------------------------------------ run bulk


def _child_env() -> dict:
    """Copy of os.environ minus the YAML-override keys (already folded by CLI)."""
    return {k: v for k, v in os.environ.items() if k not in {e for e in ENV_OVERRIDES.values()}}


def _schema_violations(run_id: str) -> int | None:
    """Sum schema-invalid counts from run_bulk's merge_report files, if any."""
    tag = run_id.replace("/", "_")
    reports = list(EXPORTS_DIR.glob(f"merge_report.{tag}*.md"))
    if not reports:
        return None
    total = 0
    for rp in reports:
        m = SCHEMA_ERR_RE.search(rp.read_text(encoding="utf-8"))
        if m:
            total += int(m.group(1))
    return total


def _bulk_final_state() -> dict:
    try:
        return json.loads(BULK_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def cmd_run(args) -> int:
    t0 = time.perf_counter()
    cfg = resolve_config(args)
    validate_modes(cfg)
    sched, bpm = effective_modes(cfg)

    manifest_dir = Path(args.manifest_dir)
    batch_files = validate_manifest_dir(manifest_dir)
    manifest_h = manifest_hash(batch_files)
    planned = planned_papers(batch_files)

    session_id = args.session_id or f"cli-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    log_dir = LOGS_ROOT / session_id
    config_h = write_derived_config(cfg, log_dir / "derived_config.yaml")

    summary = {
        "started_at_utc": _utc(),
        "run_id": None,  # filled below
        "session_id": session_id,
        "manifest_dir": str(manifest_dir),
        "manifest_sha256": manifest_h,
        "config_sha256": config_h,
        "derived_config": str(log_dir / "derived_config.yaml"),
        "scheduler_mode": sched,
        "bert_pipeline_mode": bpm,
        "planned_papers": planned,
        "status": None,
    }

    run_id = args.run_id or f"prod-cli-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    summary["run_id"] = run_id

    if args.dry_run:
        summary["status"] = "dry_run"
        summary["wall_sec"] = round(time.perf_counter() - t0, 3)
        _write_summary(log_dir, summary)
        print(f"[dry-run] mode ok: scheduler_mode={sched} bert_pipeline_mode={bpm}")
        print(f"[dry-run] manifest ok: {len(batch_files)} batch(es), {planned} paper(s)")
        print(f"[dry-run] no service check, no bulk run, no network calls")
        print(f"[dry-run] summary: {log_dir / 'cli_summary.json'}")
        return 0

    if not args.skip_service_check:
        results, ok = run_service_checks(cfg, args.check_only, args.check_timeout)
        for r in results:
            print(_fmt_check(r))
        summary["service_checks"] = results
        if not ok:
            summary["status"] = "service_check_failed"
            summary["wall_sec"] = round(time.perf_counter() - t0, 3)
            _write_summary(log_dir, summary)
            print("service check FAILED — not starting bulk", file=sys.stderr)
            return 1

    argv = [
        sys.executable, str(RUN_BULK),
        "--config", str(log_dir / "derived_config.yaml"),
        "--manifest-dir", str(manifest_dir),
        "--run-id", run_id,
        "--session-id", session_id,
    ]
    if args.start_from:
        argv += ["--start-from", args.start_from]
    for jb in args.job_batches or []:
        argv += ["--job-batches", jb]
    if args.watch_manifest:
        argv += ["--watch-manifest", "--poll-interval", str(args.poll_interval),
                 "--watch-idle-timeout", str(args.watch_idle_timeout)]
    print(f"[run] bulk: {' '.join(argv)}")
    proc = subprocess.run(argv, env=_child_env())
    summary["bulk_exit_code"] = proc.returncode
    if proc.returncode != 0:
        summary["status"] = {2: "bulk_window_failed", 3: "bulk_gate_paused", 130: "bulk_sigint"}.get(
            proc.returncode, "bulk_failed"
        )
        final = _bulk_final_state()
        summary["completed_papers"] = (final.get("total_ok", 0) or 0) + (final.get("total_error", 0) or 0)
        _absorb_bulk_state(summary)
        summary["wall_sec"] = round(time.perf_counter() - t0, 3)
        _write_summary(log_dir, summary)
        return proc.returncode

    # incremental merge -> flat export (reuses the standard merge script)
    out_flat = EXPORTS_DIR / f"ai2000_{run_id.replace('/', '_')}_flat_merged.json"
    merge_argv = [
        sys.executable, str(MERGE_FLAT), "--session-run-id", run_id, "--out", str(out_flat),
    ]
    print(f"[run] merge: {' '.join(merge_argv)}")
    merge_rc = subprocess.run(merge_argv, env=_child_env()).returncode
    if merge_rc != 0:
        summary["status"] = "merge_failed"
        _absorb_bulk_state(summary)
        summary["wall_sec"] = round(time.perf_counter() - t0, 3)
        _write_summary(log_dir, summary)
        print("merge FAILED — reporting failure", file=sys.stderr)
        return 1
    summary["flat_export"] = str(out_flat)

    metrics_json = log_dir / "metrics.json"
    metrics_argv = [
        sys.executable, str(COLLECT_METRICS), "--run-id", run_id, "--json-out", str(metrics_json),
    ]
    print(f"[run] report: {' '.join(metrics_argv)}")
    subprocess.run(metrics_argv, env=_child_env())
    summary["metrics_report"] = str(metrics_json)

    _absorb_bulk_state(summary)
    summary["prediction_dir"] = str(PROD_ROOT / "pipeline_output" / "production" / "runs" / run_id)
    summary["schema_violations"] = _schema_violations(run_id)
    jobs = int(summary.get("jobs_done") or 0)
    summary["status"] = "success" if jobs >= len(batch_files) else "partial_success"
    summary["wall_sec"] = round(time.perf_counter() - t0, 3)
    _write_summary(log_dir, summary)
    print(f"[run] status={summary['status']} ok={summary.get('total_ok')} err={summary.get('total_error')} "
          f"wall={summary['wall_sec']}s")
    print(f"[run] summary: {log_dir / 'cli_summary.json'}")
    return 0


def _absorb_bulk_state(summary: dict) -> None:
    final = _bulk_final_state()
    for k_src, k_dst in [
        ("jobs_done", "jobs_done"),
        ("total_ok", "total_ok"),
        ("total_error", "total_error"),
        ("total_skipped", "total_skipped"),
        ("total_wall_sec", "bulk_wall_sec"),
        ("papers_per_hour", "papers_per_hour"),
    ]:
        if final.get(k_src) is not None:
            summary[k_dst] = final[k_src]
    summary["completed_papers"] = (final.get("total_ok") or 0) + (final.get("total_error") or 0)


def _write_summary(log_dir: Path, summary: dict) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "cli_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------- ingest


def cmd_ingest(args) -> int:
    from pipeline.production.manifest_ingest import ingest_csv

    report = ingest_csv(
        Path(args.csv),
        Path(args.manifest_dir),
        run_ids=args.run_ids or [],
        include_retry=bool(args.include_retry),
        size=args.size,
        source_name=args.source_name,
    )
    c = report.counts
    print(
        f"[ingest] rows={sum(c.values())} new={c['new']} duplicate={c['duplicate']} "
        f"invalid={c['invalid']} retry={c['retry']} conflict={c['conflict']}"
    )
    for r in report.rows:
        if r.status in ("invalid", "conflict"):
            print(f"  line {r.line_no}: {r.status}: {r.reason}")
        elif r.status == "retry" and not args.include_retry:
            print(f"  line {r.line_no}: retry (skipped; --include-retry to re-queue): {r.reason}")
    for b in report.published:
        print(f"[ingest] published: {b}")
    if not report.published:
        print("[ingest] nothing to publish (no new/retry-queued rows)")
    return 0


# ----------------------------------------------------------------------- passthrough


def _passthrough(script: Path, rest: list[str]) -> int:
    argv = [sys.executable, str(script), *rest]
    print(f"[cli] {' '.join(argv)}")
    return subprocess.run(argv).returncode


# ------------------------------------------------------------------------------ main


def _fmt_check(r: dict) -> str:
    return (f"  {'OK ' if r['ok'] else 'FAIL'} {r['name']} ({r.get('latency_ms', '?')}ms)  "
            f"{r.get('detail') or r.get('error')}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pipeline_cli.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check-services", help="LLM/BERT endpoint checks (no production run)")
    p.add_argument("--config", type=Path, default=PROD_ROOT / "configs" / "default.yaml")
    p.add_argument("--only", choices=["llm", "bert", "all"], default="all")
    p.add_argument("--timeout", type=float, default=15.0)
    for flag, (_key, typ) in FLAG_OVERRIDES.items():
        p.add_argument(f"--{flag.replace('_', '-')}", type=typ)

    p = sub.add_parser("prepare", help="passthrough: prepare_aminer_manifest_pub_id.py")
    p.add_argument("rest", nargs=argparse.REMAINDER)

    p = sub.add_parser("ingest", help="online CSV -> manifest incremental publish (Phase 5)")
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--manifest-dir", type=Path, required=True)
    p.add_argument("--run-id", action="append", dest="run_ids",
                   help="run id whose predictions participate in dedup (repeatable)")
    p.add_argument("--include-retry", action="store_true",
                   help="re-queue rows whose only prediction is an error (default: report only)")
    p.add_argument("--size", type=int, default=500, help="papers per new job_batch")
    p.add_argument("--source-name", default=None)

    p = sub.add_parser("run", help="one-shot: validate -> check -> bulk -> merge -> report")
    p.add_argument("--config", type=Path, default=PROD_ROOT / "configs" / "default.yaml")
    p.add_argument("--manifest-dir", type=Path, default=PROD_ROOT / "manifests" / "job_batches")
    p.add_argument("--run-id", default=None)
    p.add_argument("--session-id", default=None)
    p.add_argument("--start-from", default=None)
    p.add_argument("--job-batches", action="append", default=None)
    for flag, (_key, typ) in FLAG_OVERRIDES.items():
        p.add_argument(f"--{flag.replace('_', '-')}", type=typ)
    p.add_argument("--skip-service-check", action="store_true")
    p.add_argument("--check-only", choices=["llm", "bert", "all"], default="all",
                   help="narrow the pre-run service check scope")
    p.add_argument("--check-timeout", type=float, default=15.0)
    p.add_argument("--dry-run", action="store_true",
                   help="validate args/config/modes/manifest only; no network, no bulk")
    p.add_argument("--watch-manifest", action="store_true",
                   help="enable run_bulk watch mode (dynamic batch discovery, Phase 5)")
    p.add_argument("--poll-interval", type=float, default=5.0)
    p.add_argument("--watch-idle-timeout", type=float, default=600.0)

    p = sub.add_parser("merge", help="passthrough: merge_flat_experiments.py")
    p.add_argument("rest", nargs=argparse.REMAINDER)

    p = sub.add_parser("report", help="passthrough: collect_phase_metrics.py")
    p.add_argument("rest", nargs=argparse.REMAINDER)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "check-services":
        cfg = resolve_config(args)
        validate_modes(cfg)
        results, ok = run_service_checks(cfg, args.only, args.timeout)
        for r in results:
            print(_fmt_check(r))
        return 0 if ok else 1
    if args.cmd == "prepare":
        return _passthrough(PREPARE_AMINER, args.rest)
    if args.cmd == "ingest":
        return cmd_ingest(args)
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "merge":
        return _passthrough(MERGE_FLAT, args.rest)
    if args.cmd == "report":
        return _passthrough(COLLECT_METRICS, args.rest)
    raise SystemExit(f"unknown command: {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
