"""CLI: batch-run prod-wf4-llm-datasets-experiment (wf4 /filter/batch + LLM, 8 fields).

Mirrors ``batch_run_bert_pipeline.py`` (wf3) with:
  - default --workflow = prod-wf4-llm-datasets-experiment
  - scheduler = BatchBertPipelineSchedulerWf4
  - batch_summary adds: llm_mode, datasets_source="llm", avg_datasets_count,
    parse_error_count, vs_wf3_baseline_run_id="prod-dev10-wf3-v0.1.0".

Examples:
  venv/Scripts/python.exe pipeline/production/runners/batch_run_wf4.py \\
    --workflow prod-wf4-llm-datasets-experiment --limit 10 \\
    --manifest pipeline/evaluation/fixtures/dev_10/manifest.json \\
    --run-id prod-dev10-wf4-v0.1.0 --bert-batch-size 32

Whole batch shares one --run-id. Needs BERT:5000 + Ollama:11434.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.evaluation.md_resolver import fetch_batch, load_handoff_batch
from pipeline.production.batch_bert_pipeline_wf4 import BatchBertPipelineSchedulerWf4
from pipeline.production.config import (
    DEV10_MANIFEST,
    DEV10_MD_DIR,
    DATA_MD_DIR,
    EVAL_MD_CACHE_DIR,
    RUNS_DIR,
    WF4_LLM_EXTRACTOR_ID,
    WF4_WORKFLOW_ID,
)
from pipeline.production.manifest import write_run_manifest
from pipeline.production.monitor import append_history, utc_now
from pipeline.production.runners._manifest import _load_paper_ids
from pipeline.production.workflows.spec import get_workflow

WF3_BASELINE_TOTAL_SEC = 28.37
WF3_BASELINE_RUN_ID = "prod-dev10-wf3-v0.1.0"
WF1_BASELINE_TOTAL_SEC = 51.51
WF2_BASELINE_TOTAL_SEC = 29.51
WF2_BASELINE_AVG_BERT_SEC = 2.45


def _resolve_md(paper_id: str, md_dir: Path | None = None) -> Path | None:
    cands = []
    if md_dir is not None:
        cands.append(Path(md_dir) / f"{paper_id}.md")
    cands.extend((
        DATA_MD_DIR / f"{paper_id}.md",
        DEV10_MD_DIR / f"{paper_id}.md",
        EVAL_MD_CACHE_DIR / f"{paper_id}.md",
    ))
    for cand in cands:
        if cand.exists():
            return cand
    return None


def _wf4_llm_meta(monitor: dict) -> dict:
    """Pull the wf4 LLM extractor metadata from a paper monitor."""
    for e in monitor.get("extractors") or []:
        if e.get("extractor_id") == WF4_LLM_EXTRACTOR_ID:
            return e.get("metadata") or {}
    return {}


def _build_batch_summary(
    run_id: str, spec, results, total_wall_sec: float,
    bert_batch_monitor, bert_batch_size: int, llm_concurrency: int,
    *,
    llm_model_tag: str | None = None,
    model_slug: str | None = None,
    parent_workflow_id: str | None = None,
    ollama_format: str | None = None,
    num_predict_override: int | None = None,
    prompt_adapter: str | None = None,
) -> dict:
    per_paper = []
    sum_paper_wall = 0.0
    llm_secs: list[float] = []
    prep_secs: list[float] = []
    amort_secs: list[float] = []
    ok = 0
    parse_error_count = 0
    datasets_counts: list[int] = []
    llm_eval_counts: list[int] = []
    tokens_per_sec_list: list[float] = []
    fallback_trigger_count = 0
    fallback_char_counts: list[int] = []
    for r in results:
        ps = r.monitor.get("pipeline_stages", {}) or {}
        wall = ps.get("paper_wall_sec", r.monitor.get("total_elapsed_sec", 0.0))
        sum_paper_wall += float(wall)
        llm_sec = float(ps.get("llm_elapsed_sec", 0.0))
        llm_secs.append(llm_sec)
        prep_secs.append(float(ps.get("prep_elapsed_sec", 0.0)))
        amort_secs.append(float(ps.get("bert_amortized_sec", 0.0)))
        ok += 0 if r.error else 1
        llm_meta = _wf4_llm_meta(r.monitor)
        if llm_meta.get("parse_error"):
            parse_error_count += 1
        datasets_counts.append(int(llm_meta.get("datasets_count", 0)))
        fb_triggered = bool(llm_meta.get("dataset_fallback_triggered"))
        if fb_triggered:
            fallback_trigger_count += 1
        fb_chars = int(llm_meta.get("dataset_fallback_char_count", 0) or 0)
        if fb_triggered:
            fallback_char_counts.append(fb_chars)
        ec = llm_meta.get("llm_eval_count")
        if ec is not None:
            llm_eval_counts.append(int(ec))
        tps = llm_meta.get("tokens_per_sec")
        if tps is not None:
            tokens_per_sec_list.append(float(tps))
        elif ec is not None and llm_sec > 0:
            tokens_per_sec_list.append(float(ec) / llm_sec)
        per_paper.append(
            {
                "paper_id": r.paper_id,
                "wall_sec": round(float(wall), 4),
                "prep_sec": round(float(ps.get("prep_elapsed_sec", 0.0)), 4),
                "bert_mode": ps.get("bert_mode", "batch"),
                "input_path": ps.get("input_path"),
                "num_ctx": ps.get("num_ctx"),
                "prompt_adapter": ps.get("prompt_adapter"),
                "nobert_prompt_chars": ps.get("nobert_prompt_chars"),
                "bert_struct_prompt_chars": ps.get("bert_struct_prompt_chars"),
                "selected_by_block": ps.get("selected_by_block"),
                "max_llm_sentences": ps.get("max_llm_sentences"),
                "dedup_removed_count": ps.get("dedup_removed_count"),
                "input_sentence_count_pre_dedup": ps.get("input_sentence_count_pre_dedup"),
                "input_sentence_count_post_dedup": ps.get("input_sentence_count_post_dedup"),
                "bert_amortized_sec": round(float(ps.get("bert_amortized_sec", 0.0)), 4),
                "bert_batch_chunk": ps.get("bert_batch_chunk", 0),
                "llm_sec": round(llm_sec, 4),
                "llm_wait_sec": round(float(ps.get("llm_wait_sec", 0.0)), 4),
                "llm_eval_count": ec,
                "tokens_per_sec": llm_meta.get("tokens_per_sec"),
                "llm_model_tag": llm_meta.get("llm_model_tag"),
                "datasets_count": int(llm_meta.get("datasets_count", 0)),
                "parse_error": bool(llm_meta.get("parse_error")),
                "dataset_fallback_triggered": fb_triggered,
                "dataset_fallback_char_count": fb_chars,
                "status": "ok" if not r.error else "error",
                "error": r.error,
            }
        )
    n = max(1, len(results))
    bb = bert_batch_monitor or {}
    avg_datasets_count = round(sum(datasets_counts) / n, 4) if datasets_counts else 0.0
    total_qwen_eval_count = sum(llm_eval_counts) if llm_eval_counts else 0
    avg_qwen_eval_count = round(total_qwen_eval_count / n, 4) if llm_eval_counts else None
    avg_tokens_per_sec = (
        round(sum(tokens_per_sec_list) / len(tokens_per_sec_list), 4)
        if tokens_per_sec_list else None
    )
    summary = {
        "type": "batch_summary",
        "run_id": run_id,
        "workflow_id": spec.workflow_id,
        "workflow_version": spec.workflow_version,
        "experimental": True,
        "paper_count": len(results),
        "total_wall_sec": round(total_wall_sec, 4),
        "sum_paper_wall_sec": round(sum_paper_wall, 4),
        "pipeline_speedup_vs_serial": round(sum_paper_wall / total_wall_sec, 4) if total_wall_sec else 0.0,
        "vs_wf1_baseline": {"total_sec": WF1_BASELINE_TOTAL_SEC},
        "vs_wf2_baseline": {"total_sec": WF2_BASELINE_TOTAL_SEC, "avg_bert_sec": WF2_BASELINE_AVG_BERT_SEC},
        "vs_wf3_baseline": {"total_sec": WF3_BASELINE_TOTAL_SEC, "run_id": WF3_BASELINE_RUN_ID},
        "bert_batch_total_sec": round(float(bb.get("total_client_sec", 0.0)), 4),
        "bert_batch_chunks": int(bb.get("chunk_count", 0)),
        "bert_batch_inference_ms": round(float(bb.get("total_inference_ms", 0.0)), 2),
        "bert_batch_client_elapsed_sec": round(float(bb.get("total_client_sec", 0.0)), 4),
        "bert_batch_total_sentences": int(bb.get("total_sentences", 0)),
        "bert_batch_total_kept": int(bb.get("total_kept", 0)),
        "llm_pipeline_total_sec": round(sum(llm_secs), 4),
        "avg_prep_sec": round(sum(prep_secs) / n, 4),
        "avg_qwen_sec": round(sum(llm_secs) / n, 4),
        "avg_qwen_wait_sec": round(sum([float(ps.get("llm_wait_sec", 0.0)) for ps in [r.monitor.get("pipeline_stages", {}) or {} for r in results]]) / n, 4),
        "avg_bert_amortized_sec": round(sum(amort_secs) / n, 4),
        "bert_batch_size": bert_batch_size,
        "llm_concurrency": llm_concurrency,
        "ok_count": ok,
        "error_count": len(results) - ok,
        # --- wf4-specific ---
        "llm_mode": "wf4_8field_datasets",
        "datasets_source": "llm",
        "avg_datasets_count": avg_datasets_count,
        "parse_error_count": parse_error_count,
        "dataset_fallback_trigger_count": fallback_trigger_count,
        "dataset_fallback_trigger_rate": round(fallback_trigger_count / n, 4),
        "avg_fallback_char_count": (
            round(sum(fallback_char_counts) / len(fallback_char_counts), 4)
            if fallback_char_counts else 0.0
        ),
        "vs_wf3_baseline_run_id": WF3_BASELINE_RUN_ID,
        "per_paper": per_paper,
    }
    # nobert structured-input ablation aggregates (only when skip-bert was used).
    if bb.get("mode") == "nobert_struct":
        summary["nobert_struct"] = True
        summary["nobert_struct_count"] = int(bb.get("nobert_struct_count", 0))
        summary["bert_fallback_count"] = int(bb.get("bert_fallback_count", 0))
        summary["avg_dedup_removed_count"] = bb.get("avg_dedup_removed_count", 0)
        summary["nobert_total_prompt_chars"] = int(bb.get("total_prompt_chars", 0))
    # bert-struct-60 structured-input axis aggregates (only when --bert-struct used).
    if bb.get("mode") == "bert_struct":
        summary["bert_struct"] = True
        summary["bert_struct_count"] = int(bb.get("bert_struct_count", 0))
        summary["bert_struct_max_qwen_sentences"] = int(bb.get("max_llm_sentences", 60))
        summary["avg_dedup_removed_count"] = bb.get("avg_dedup_removed_count", 0)
        summary["bert_struct_avg_selected_sentences"] = bb.get("avg_selected_sentences", 0)
        summary["bert_struct_total_prompt_chars"] = int(bb.get("total_prompt_chars", 0))
    # bert-flat input-axis aggregates (when --bert-flat-50 or --bert-flat-60 used).
    if bb.get("mode") == "bert_flat":
        max_qwen = int(bb.get("max_llm_sentences", 60))
        summary["bert_flat_max_qwen_sentences"] = max_qwen
        if max_qwen == 50:
            summary["bert_flat_50"] = True
        else:  # default 60 or other values
            summary["bert_flat_60"] = True
    # chunked_overlap pipeline mode (when --bert-pipeline-batch-size > 0).
    if bb.get("pipeline_mode") == "chunked_overlap":
        summary["pipeline_mode"] = "chunked_overlap"
        summary["bert_pipeline_batch_size"] = bb.get("bert_pipeline_batch_size", 0)
        summary["chunk_count"] = bb.get("chunk_count", 0)
        summary["sum_chunk_bert_sec"] = bb.get("sum_chunk_bert_sec", 0.0)
    # global_batch pipeline mode (v0.7 Phase 1).
    elif bb.get("pipeline_mode") == "global_batch":
        summary["pipeline_mode"] = "global_batch"
        summary["bert_batch_count"] = bb.get("batch_count", 0)
        summary["bert_batch_max_papers"] = bb.get("bert_batch_max_papers", 16)
        summary["bert_batch_max_sentences"] = bb.get("bert_batch_max_sentences", 1500)
        summary["bert_batch_max_chars"] = bb.get("bert_batch_max_chars", 300000)
        summary["bert_batch_max_wait_ms"] = bb.get("bert_batch_max_wait_ms", 20)
        summary["sum_batch_bert_sec"] = bb.get("sum_batch_bert_sec", 0.0)
    # legacy_global_bert pipeline mode (default).
    elif bb.get("pipeline_mode") == "legacy_global_bert":
        summary["pipeline_mode"] = "legacy_global_bert"
    # v0.7 Phase 2: always mirror the scheduling mode next to pipeline_mode so
    # run artifacts never leave ambiguity about which path executed.
    summary["scheduler_mode"] = bb.get("scheduler_mode") or "default"
    if llm_model_tag:
        summary["llm_model_tag"] = llm_model_tag
    if model_slug:
        summary["model_slug"] = model_slug
    if parent_workflow_id:
        summary["parent_workflow_id"] = parent_workflow_id
    if ollama_format:
        summary["ollama_format"] = ollama_format
    if num_predict_override is not None:
        summary["num_predict_override"] = num_predict_override
    if prompt_adapter:
        summary["prompt_adapter"] = prompt_adapter
    if avg_qwen_eval_count is not None:
        summary["avg_qwen_eval_count"] = avg_qwen_eval_count
        summary["total_qwen_eval_count"] = total_qwen_eval_count
    if avg_tokens_per_sec is not None:
        summary["avg_tokens_per_sec"] = avg_tokens_per_sec
    return summary


def _write_batch_summary_md(summary: dict, path: Path) -> None:
    lines = [
        f"# Batch Summary (wf4 LLM-datasets) — `{summary['run_id']}`",
        "",
        f"- workflow: `{summary['workflow_id']}` v{summary['workflow_version']} (experimental)",
        f"- papers: {summary['paper_count']} (ok={summary['ok_count']}, error={summary['error_count']})",
        f"- total wall: **{summary['total_wall_sec']}s**  (sum paper wall={summary['sum_paper_wall_sec']}s, "
        f"speedup vs serial={summary['pipeline_speedup_vs_serial']}x)",
        f"- vs wf3: {summary['vs_wf3_baseline']['total_sec']}s ({summary['vs_wf3_baseline_run_id']}) | "
        f"vs wf2: {summary['vs_wf2_baseline']['total_sec']}s | vs wf1: {summary['vs_wf1_baseline']['total_sec']}s",
        f"- bert batch: total={summary['bert_batch_total_sec']}s, inference={summary['bert_batch_inference_ms']}ms, "
        f"chunks={summary['bert_batch_chunks']}, sentences={summary['bert_batch_total_sentences']}, kept={summary['bert_batch_total_kept']}",
        f"- avg prep={summary['avg_prep_sec']}s | avg llm={summary['avg_qwen_sec']}s | avg llm_wait={summary['avg_qwen_wait_sec']}s | avg bert_amortized={summary['avg_bert_amortized_sec']}s",
        f"- wf4: llm_mode={summary['llm_mode']}, datasets_source={summary['datasets_source']}, "
        f"avg_datasets={summary['avg_datasets_count']}, parse_errors={summary['parse_error_count']}",
    ]
    if summary.get("llm_model_tag"):
        lines.append(f"- llm_model: `{summary['llm_model_tag']}`")
    if summary.get("model_slug"):
        lines.append(f"- model_slug: `{summary['model_slug']}`")
    if summary.get("avg_tokens_per_sec") is not None:
        lines.append(
            f"- llm tokens: avg_eval_count={summary.get('avg_qwen_eval_count')} "
            f"avg_tokens_per_sec={summary['avg_tokens_per_sec']}"
        )
    lines += [
        "",
        "| paper_id | wall | prep | bert_amort | llm | llm_wait | datasets | parse_err | status |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for p in summary["per_paper"]:
        lines.append(
            f"| {p['paper_id']} | {p['wall_sec']} | {p['prep_sec']} | {p['bert_amortized_sec']} | "
            f"{p['llm_sec']} | {p['llm_wait_sec']} | {p['datasets_count']} | {p['parse_error']} | {p['status']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _progress_row(job, run_id: str, default_llm_model_tag: str | None) -> dict:
    """Build one extraction_progress.jsonl row from a finished PaperJob."""
    monitor = {}
    if job.result is not None and getattr(job.result, "monitor", None):
        monitor = job.result.monitor or {}
    ps = monitor.get("pipeline_stages", {}) or {}
    llm_meta = _wf4_llm_meta(monitor)
    return {
        "ts": utc_now(),
        "event": "paper_done",
        "run_id": run_id,
        "paper_id": job.paper_id,
        "status": "error" if job.error else "ok",
        "md_source": str(job.md_path) if job.md_path else None,
        "timing_sec": {
            "prep": ps.get("prep_elapsed_sec"),
            "bert_amortized": ps.get("bert_amortized_sec"),
            "llm": ps.get("llm_elapsed_sec"),
            "paper_wall": ps.get("paper_wall_sec"),
        },
        "llm": {
            "llm_model_tag": llm_meta.get("llm_model_tag", default_llm_model_tag),
            "parse_error": bool(llm_meta.get("parse_error")),
            "llm_eval_count": llm_meta.get("llm_eval_count"),
            "datasets_count": int(llm_meta.get("datasets_count", 0)),
            "dataset_fallback_triggered": bool(llm_meta.get("dataset_fallback_triggered")),
            "dataset_fallback_char_count": int(llm_meta.get("dataset_fallback_char_count", 0) or 0),
        },
        "error": job.error,
    }


class ProgressLogger:
    """Append-only JSONL per-paper progress log (live + crash-safe)."""

    def __init__(self, path: Path | None, run_id: str, llm_model_tag: str | None) -> None:
        self.run_id = run_id
        self.llm_model_tag = llm_model_tag
        self._lock = threading.Lock()
        if path is None:
            self._fh = None
            self.path = None
            return
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")

    @property
    def enabled(self) -> bool:
        return self._fh is not None

    def _write(self, row: dict) -> None:
        if self._fh is None:
            return
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with self._lock:
            self._fh.write(line)
            self._fh.flush()

    def log_job(self, job) -> None:
        self._write(_progress_row(job, self.run_id, self.llm_model_tag))

    def log_skip(self, paper_id: str, reason: str) -> None:
        self._write({
            "ts": utc_now(),
            "event": "paper_skipped",
            "run_id": self.run_id,
            "paper_id": paper_id,
            "status": "skipped_missing_md",
            "md_source": None,
            "timing_sec": {"prep": None, "bert_amortized": None, "llm": None, "paper_wall": None},
            "llm": {
                "llm_model_tag": self.llm_model,
                "parse_error": False,
                "llm_eval_count": None,
                "datasets_count": 0,
            },
            "error": reason,
        })

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except Exception:  # noqa: BLE001
                pass
            self._fh = None


def _write_human_progress_log(jsonl_path: Path, out_log: Path) -> None:
    """Render extraction_progress.jsonl into a human-readable dev500_extraction.log."""
    if not jsonl_path.exists():
        return
    rows = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    lines = [f"# dev500 extraction progress — {len(rows)} rows", ""]
    lines.append(f"{'paper_id':26} {'status':20} {'wall':>7} {'llm':>7} {'prep':>7} {'ds':>3} {'pe':>2}  md_source")
    lines.append("-" * 110)
    for r in rows:
        ts = r.get("timing_sec", {}) or {}
        llm = r.get("llm", {}) or {}
        wall = ts.get("paper_wall")
        llm = ts.get("llm")
        prep = ts.get("prep")
        md = r.get("md_source") or "-"
        lines.append(
            f"{r.get('paper_id',''):26} {r.get('status',''):20} "
            f"{(f'{wall}' if wall is not None else '-'):>7} "
            f"{(f'{llm}' if llm is not None else '-'):>7} "
            f"{(f'{prep}' if prep is not None else '-'):>7} "
            f"{str(llm.get('datasets_count','-')):>3} "
            f"{'1' if llm.get('parse_error') else '0':>2}  {md}"
        )
        if r.get("error"):
            lines.append(f"    error: {r['error']}")
    out_log.parent.mkdir(parents=True, exist_ok=True)
    out_log.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch-run prod-wf4-llm-datasets-experiment")
    parser.add_argument("--workflow", default=WF4_WORKFLOW_ID)
    parser.add_argument("--manifest", default=str(DEV10_MANIFEST))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--bert-batch-size", type=int, default=32)
    parser.add_argument("--bert-chunk-papers", type=int, default=0, help="0=auto (one shot unless large)")
    parser.add_argument("--llm-concurrency", type=int, default=1)
    parser.add_argument("--ollama-model", default=None, help="Override Ollama model tag (CLI > spec.metadata)")
    parser.add_argument("--dry-run", action="store_true")
    # --- dev500-scale extensions (no wf4 logic change) ---
    parser.add_argument("--md-dir", default=None, help="extra md candidate dir (prepended to _resolve_md)")
    parser.add_argument("--prefetch-md", action="store_true",
                        help="prefetch md_url from manifest into eval md_cache before running")
    parser.add_argument("--skip-missing-md", action="store_true",
                        help="skip papers whose md is missing (log + continue) instead of exit(1)")
    parser.add_argument("--progress-log", default=None,
                        help="append JSONL per-paper progress log path (live, crash-safe)")
    # --- nobert structured-input ablation (skip SciBERT) ---
    parser.add_argument("--skip-bert-filter", action="store_true",
                        help="skip SciBERT /filter/batch; feed LLM the full marker-structured "
                             "+ cross-block-deduped sentence list (no 40-cap). Papers whose "
                             "structured prompt exceeds --nobert-max-prompt-chars fall back to "
                             "the BERT path (V0 + 40 sentences).")
    parser.add_argument("--nobert-num-ctx", type=int, default=32768,
                        help="Ollama num_ctx for nobert-path papers (default 32768)")
    parser.add_argument("--nobert-max-prompt-chars", type=int, default=100_000,
                        help="char budget for the structured prompt; exceeding it routes a "
                             "paper to the BERT fallback path (default 100000)")
    # --- bert-struct-60 structured-input axis (keep SciBERT + block structure + 60) ---
    parser.add_argument("--bert-struct", action="store_true",
                        help="bert-struct-60 input axis: KEEP SciBERT /filter/batch but feed "
                             "the LLM marker-structured + cross-block-deduped sentences with a "
                             "60-sentence cap (vs flat 40). Mutually exclusive with "
                             "--skip-bert-filter.")
    parser.add_argument("--bert-struct-max-sentences", type=int, default=60,
                        help="sentence cap for the bert-struct path (default 60; markers not counted)")
    parser.add_argument("--bert-struct-num-ctx", type=int, default=8192,
                        help="Ollama num_ctx for bert-struct papers (default 8192; headroom for "
                             "the larger 60-sentence structured prompt)")
    # --- bert-flat-60 input axis (keep SciBERT + flat V0 prompt + 60-sentence cap) ---
    parser.add_argument("--bert-flat-60", action="store_true",
                        help="bert-flat-60 input axis: KEEP SciBERT /filter/batch and the flat V0 "
                             "numbered prompt (no block structure, no dedup), only raise the "
                             "sentence cap from 40 to 60. Isolates the sentence-cap variable vs "
                             "bert-flat-40 / bert-struct-60. Mutually exclusive with --bert-struct "
                             "and --skip-bert-filter.")
    parser.add_argument("--bert-flat-max-sentences", type=int, default=60,
                        help="sentence cap for the bert-flat-60 path (default 60)")
    parser.add_argument("--bert-flat-num-ctx", type=int, default=8192,
                        help="Ollama num_ctx for bert-flat-60 papers (default 8192; headroom for "
                             "the larger 60-sentence flat prompt)")
    # --- bert-flat-50 input axis (keep SciBERT + flat V0 prompt + 50-sentence cap) ---
    parser.add_argument("--bert-flat-50", action="store_true",
                        help="bert-flat-50 input axis: same as bert-flat-60 but with 50 sentence cap. "
                             "Mutually exclusive with --bert-flat-60, --bert-struct, --skip-bert-filter.")
    # --- bert-pipeline chunked overlap mode ---
    parser.add_argument("--bert-pipeline-batch-size", type=int, default=0,
                        help="Pipeline batch size for BERT overlap (0=legacy global, >0=chunked, recommend 10)")
    # --- v0.7 Phase 1: global single-flight BERT batcher mode ---
    parser.add_argument("--bert-pipeline-mode", default="chunked_overlap",
                        choices=["chunked_overlap", "global_batch"],
                        help="BERT pipeline mode: chunked_overlap (default) or global_batch "
                             "(v0.7 Phase 1: one bounded queue + single-flight batcher, "
                             "cross-chunk groups)")
    parser.add_argument("--bert-batch-max-papers", type=int, default=16,
                        help="global_batch: flush budget — papers per BERT batch")
    parser.add_argument("--bert-batch-max-sentences", type=int, default=1500,
                        help="global_batch: flush budget — sentence count (token approximation)")
    parser.add_argument("--bert-batch-max-chars", type=int, default=300000,
                        help="global_batch: flush budget — total chars (token approximation)")
    parser.add_argument("--bert-batch-max-wait-ms", type=int, default=20,
                        help="global_batch: flush budget — oldest pending paper wait (ms)")
    # --- v0.7 Phase 2: staged (stage-decoupled) scheduler mode ---
    parser.add_argument("--scheduler-mode", default="default",
                        choices=["default", "staged"],
                        help="Scheduling mode: default (legacy thread/queue structure) or "
                             "staged (bounded prep/bert/llm/post/write queues + single "
                             "writer; requires --bert-pipeline-mode global_batch)")
    parser.add_argument("--prep-queue-maxsize", type=int, default=128,
                        help="staged: bounded PREP queue capacity")
    parser.add_argument("--bert-queue-maxsize", type=int, default=0,
                        help="staged: BERT batcher inbound capacity (0 = Phase 1 default 2*max_papers)")
    parser.add_argument("--llm-queue-maxsize", type=int, default=512,
                        help="staged: bounded LLM dispatch queue capacity")
    parser.add_argument("--post-queue-maxsize", type=int, default=256,
                        help="staged: bounded POST queue capacity")
    parser.add_argument("--write-queue-maxsize", type=int, default=128,
                        help="staged: bounded write queue capacity")
    parser.add_argument("--prep-workers", type=int, default=4,
                        help="staged: PREP worker pool size (paper-level)")
    parser.add_argument("--post-workers", type=int, default=8,
                        help="staged: POST worker pool size (paper-level; writer is always 1)")
    # --- remote service overrides ---
    parser.add_argument("--bert-server-url", default=None,
                        help="Override BERT server URL (env BERT_SERVER_URL)")
    parser.add_argument("--llm-api-url", default=None,
                        help="LLM API URL for openai_chat backend (env LLM_CHAT_URL)")
    parser.add_argument("--llm-model", default=None,
                        help="LLM model for openai_chat backend payload (env LLM_MODEL)")
    parser.add_argument("--llm-backend", default="ollama",
                        choices=["ollama", "openai_chat"],
                        help="LLM backend: ollama (default) or openai_chat")
    args = parser.parse_args()

    if args.bert_struct and args.skip_bert_filter:
        print("Error: --bert-struct and --skip-bert-filter are mutually exclusive "
              "(bert-struct keeps SciBERT; skip-bert-filter drops it).")
        sys.exit(1)
    # Guard for bert-flat-50
    if args.bert_flat_50 and (args.skip_bert_filter or args.bert_struct or args.bert_flat_60):
        print("Error: --bert-flat-50 is mutually exclusive with --skip-bert-filter, "
              "--bert-struct, and --bert-flat-60 (only one input axis at a time).")
        sys.exit(1)
    if args.bert_flat_60 and (args.skip_bert_filter or args.bert_struct or args.bert_flat_50):
        print("Error: --bert-flat-60 is mutually exclusive with --skip-bert-filter "
              "and --bert-struct and --bert-flat-50 (only one input axis at a time).")
        sys.exit(1)

    # Set default max_sentences for bert-flat-50 (cap=50 instead of 60)
    if args.bert_flat_50:
        args.bert_flat_max_sentences = 50

    spec = get_workflow(args.workflow)
    run_id = args.run_id or f"prod-wf4-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    llm_model = args.llm_model or spec.metadata.get("llm_model_tag")
    model_slug = spec.metadata.get("model_slug")
    parent_workflow_id = spec.metadata.get("parent_workflow")
    # Per-model calling-convention overrides (wf4 model-sweep fix). Absent => None
    # => downstream uses production defaults (V0 prompt, no format, num_predict=2048).
    ollama_format = spec.metadata.get("ollama_format")
    num_predict_override = spec.metadata.get("num_predict")
    prompt_adapter = spec.metadata.get("prompt_adapter")

    paper_ids = _load_paper_ids(Path(args.manifest), args.limit)
    if not paper_ids:
        print("No paper ids to run.")
        sys.exit(1)

    progress = ProgressLogger(
        Path(args.progress_log) if args.progress_log else None, run_id, llm_model_tag
    )

    # --- optional prefetch: pull md_url from manifest into eval md_cache -------
    if args.prefetch_md:
        try:
            all_papers = load_handoff_batch(Path(args.manifest))
        except Exception as exc:  # noqa: BLE001
            all_papers = []
            print(f"warning: prefetch could not read manifest md_url: {exc}")
        prefetch_papers = [p for p in all_papers if p.get("paper_id") in set(paper_ids)]
        if prefetch_papers:
            EVAL_MD_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _, pf_stats = fetch_batch(prefetch_papers, EVAL_MD_CACHE_DIR)
            print(f"prefetch-md: {pf_stats.get('cached')} cached, "
                  f"{pf_stats.get('fetched')} fetched, {pf_stats.get('failed')} failed "
                  f"(of {pf_stats.get('total')})")

    # --- md resolution --------------------------------------------------------
    md_paths: dict[str, Path] = {}
    missing = []
    for pid in paper_ids:
        mp = _resolve_md(pid, Path(args.md_dir) if args.md_dir else None)
        if mp is None:
            missing.append(pid)
        else:
            md_paths[pid] = mp
    if missing:
        msg = f"md not found for {len(missing)} paper(s): {missing[:10]}{'...' if len(missing) > 10 else ''}"
        if args.skip_missing_md:
            print(f"warning: {msg} — skipping (--skip-missing-md)")
            for pid in missing:
                progress.log_skip(pid, "md not found in data/md | dev10 | eval md_cache")
        else:
            print(f"Error: {msg}")
            progress.close()
            sys.exit(1)
    run_paper_ids = list(md_paths.keys())

    print(f"=== prod-wf4 batch: {len(run_paper_ids)} papers (of {len(paper_ids)} requested), "
          f"run_id={run_id}, bert_batch_size={args.bert_batch_size} chunk_papers={args.bert_chunk_papers}"
          f"{f', llm_model_tag={llm_model_tag}' if llm_model_tag else ''} ===")
    if not run_paper_ids:
        print("No runnable papers after md resolution.")
        progress.close()
        sys.exit(1)

    # nobert ablation: PREP (prepare_llm_inputs_wf4) reads this env to stash the
    # marker-structured merged_text; the scheduler reads skip_bert_filter to route
    # Phase 2 through the structured builder. Set before scheduler.run() (PREP
    # runs inside run()).
    if args.skip_bert_filter:
        os.environ["WF4_SKIP_BERT_FILTER"] = "1"
        print(f"nobert: skip-bert-filter ON (num_ctx={args.nobert_num_ctx}, "
              f"max_prompt_chars={args.nobert_max_prompt_chars}; overflow -> BERT fallback)")
    if args.bert_struct:
        print(f"bert-struct-60: KEEP SciBERT + block structure + 60 cap "
              f"(num_ctx={args.bert_struct_num_ctx}, max_sentences={args.bert_struct_max_sentences})")
    if args.bert_flat_60:
        print(f"bert-flat-60: KEEP SciBERT + flat V0 prompt + 60 cap "
              f"(num_ctx={args.bert_flat_num_ctx}, max_sentences={args.bert_flat_max_sentences})")
    if args.bert_flat_50:
        print(f"bert-flat-50: KEEP SciBERT + flat V0 prompt + 50 cap "
              f"(num_ctx={args.bert_flat_num_ctx}, max_sentences={args.bert_flat_max_sentences})")
    if args.bert_pipeline_batch_size > 0:
        print(f"bert-pipeline: chunked_overlap mode (batch_size={args.bert_pipeline_batch_size})")
    if args.bert_pipeline_mode == "global_batch":
        print(f"bert-pipeline: global_batch mode (prep_chunk={args.bert_pipeline_batch_size or 10}, "
              f"max_papers={args.bert_batch_max_papers}, "
              f"max_sentences={args.bert_batch_max_sentences}, "
              f"max_chars={args.bert_batch_max_chars}, "
              f"max_wait_ms={args.bert_batch_max_wait_ms}, endpoint_concurrency=1)")
    if args.scheduler_mode == "staged":
        if args.bert_pipeline_mode != "global_batch":
            print("Error: --scheduler-mode staged requires --bert-pipeline-mode global_batch.")
            sys.exit(1)
        print(f"scheduler: staged mode (prep_queue={args.prep_queue_maxsize}, "
              f"bert_queue={args.bert_queue_maxsize or 2 * args.bert_batch_max_papers}, "
              f"llm_queue={args.llm_queue_maxsize}, post_queue={args.post_queue_maxsize}, "
              f"write_queue={args.write_queue_maxsize}; prep_workers={args.prep_workers}, "
              f"llm_concurrency={args.llm_concurrency}, post_workers={args.post_workers}, writer=1)")

    # Print backend info
    print(f"llm_backend: {args.llm_backend}")
    if args.llm_backend == "openai_chat":
        print(f"  llm_api_url: {args.llm_api_url or os.environ.get('LLM_CHAT_URL', '')}")
        print(f"  llm_model: {args.llm_model or os.environ.get('LLM_MODEL', '')}")
    bert_url = args.bert_server_url or os.environ.get("BERT_SERVER_URL", "")
    print(f"bert_server_url: {bert_url}")

    scheduler_kwargs = dict(
        paper_ids=run_paper_ids,
        md_paths=md_paths,
        run_id=run_id,
        spec=spec,
        llm_concurrency=args.llm_concurrency,
        bert_batch_size=args.bert_batch_size,
        bert_chunk_papers=args.bert_chunk_papers,
        dry_run=args.dry_run,
        llm_model_tag=llm_model_tag,
        ollama_format=ollama_format,
        num_predict_override=num_predict_override,
        prompt_adapter=prompt_adapter,
        skip_bert_filter=args.skip_bert_filter,
        nobert_num_ctx=args.nobert_num_ctx,
        nobert_max_prompt_chars=args.nobert_max_prompt_chars,
        bert_struct=args.bert_struct,
        bert_struct_max_sentences=args.bert_struct_max_sentences,
        bert_struct_num_ctx=args.bert_struct_num_ctx,
        bert_flat_60=args.bert_flat_60,
        bert_flat_max_sentences=args.bert_flat_max_sentences,
        bert_flat_num_ctx=args.bert_flat_num_ctx,
        bert_flat_50=args.bert_flat_50,
        llm_backend=args.llm_backend,
        llm_api_url=args.llm_api_url,
        llm_model=args.llm_model,
        bert_server_url=args.bert_server_url,
        bert_pipeline_batch_size=args.bert_pipeline_batch_size,
        bert_pipeline_mode=args.bert_pipeline_mode,
        bert_batch_max_papers=args.bert_batch_max_papers,
        bert_batch_max_sentences=args.bert_batch_max_sentences,
        bert_batch_max_chars=args.bert_batch_max_chars,
        bert_batch_max_wait_ms=args.bert_batch_max_wait_ms,
        on_paper_done=progress.log_job if progress.enabled else None,
    )
    if args.scheduler_mode == "staged":
        from pipeline.production.staged_pipeline_wf4 import StagedPipelineWf4

        scheduler = StagedPipelineWf4(
            **scheduler_kwargs,
            scheduler_mode="staged",
            prep_queue_maxsize=args.prep_queue_maxsize,
            bert_queue_maxsize=args.bert_queue_maxsize or None,
            llm_queue_maxsize=args.llm_queue_maxsize,
            post_queue_maxsize=args.post_queue_maxsize,
            write_queue_maxsize=args.write_queue_maxsize,
            prep_workers=args.prep_workers,
            post_workers=args.post_workers,
        )
    else:
        scheduler = BatchBertPipelineSchedulerWf4(
            **scheduler_kwargs, scheduler_mode="default"
        )
    batch_start = time.perf_counter()
    results = scheduler.run()
    total_wall = time.perf_counter() - batch_start
    progress.close()

    write_run_manifest(
        spec, run_id, paper_ids=run_paper_ids,
        extra={
            k: v for k, v in {
                "llm_model_tag": llm_model,
                "model_slug": model_slug,
                "parent_workflow_id": parent_workflow_id,
            }.items() if v
        },
    )
    summary = _build_batch_summary(
        run_id, spec, results, total_wall, scheduler.batch_monitor,
        args.bert_batch_size, args.llm_concurrency,
        llm_model_tag=llm_model_tag,
        model_slug=model_slug,
        parent_workflow_id=parent_workflow_id,
        ollama_format=ollama_format,
        num_predict_override=num_predict_override,
        prompt_adapter=prompt_adapter,
    )

    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "batch_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _write_batch_summary_md(summary, run_dir / "batch_summary.md")
    append_history(summary)

    # --- human-readable progress log (derived from JSONL) ---------------------
    if progress.path is not None and progress.path.exists():
        _write_human_progress_log(progress.path, run_dir / "dev500_extraction.log")

    print(f"\n=== batch summary: {summary['ok_count']}/{summary['paper_count']} ok | run_id={run_id} ===")
    pipeline_mode = summary.get("pipeline_mode", "unknown")
    print(f"scheduler_mode: {summary.get('scheduler_mode', 'default')}")
    print(f"pipeline_mode: {pipeline_mode}")
    if pipeline_mode == "chunked_overlap":
        print(f"  batch_size: {summary.get('bert_pipeline_batch_size', 0)}, "
              f"chunks: {summary.get('chunk_count', 0)}, "
              f"sum_chunk_bert_sec: {summary.get('sum_chunk_bert_sec', 0)}s")
    elif pipeline_mode == "global_batch":
        print(f"  batches: {summary.get('bert_batch_count', 0)}, "
              f"max_papers: {summary.get('bert_batch_max_papers', 16)}, "
              f"max_sentences: {summary.get('bert_batch_max_sentences', 1500)}, "
              f"max_chars: {summary.get('bert_batch_max_chars', 300000)}, "
              f"max_wait_ms: {summary.get('bert_batch_max_wait_ms', 20)}, "
              f"sum_batch_bert_sec: {summary.get('sum_batch_bert_sec', 0)}s")
    print(f"total wall: {summary['total_wall_sec']}s (vs wf3 {WF3_BASELINE_TOTAL_SEC}s / wf2 {WF2_BASELINE_TOTAL_SEC}s / wf1 {WF1_BASELINE_TOTAL_SEC}s)")
    print(f"bert batch: {summary['bert_batch_total_sec']}s (inference {summary['bert_batch_inference_ms']}ms, "
          f"chunks={summary['bert_batch_chunks']}, {summary['bert_batch_total_kept']}/{summary['bert_batch_total_sentences']} kept)")
    print(f"avg prep={summary['avg_prep_sec']}s llm={summary['avg_qwen_sec']}s llm_wait={summary['avg_qwen_wait_sec']}s")
    print(f"wf4: avg_datasets={summary['avg_datasets_count']} parse_errors={summary['parse_error_count']}")
    for p in summary["per_paper"]:
        print(f"  {p['paper_id']}: wall={p['wall_sec']}s prep={p['prep_sec']}s bert_amort={p['bert_amortized_sec']}s "
              f"llm={p['llm_sec']}s wait={p['llm_wait_sec']}s ds={p['datasets_count']} pe={p['parse_error']} — {p['status']}")


if __name__ == "__main__":
    main()
