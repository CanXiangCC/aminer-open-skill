"""TODO-V07-10 §6.2 window byte-compat characterization.

Rolling must be invisible to window runs: a config WITHOUT admission_mode and
one with EXPLICIT admission_mode=window must produce byte-identical run trees
(predictions, progress.jsonl, staged/batch monitors) and identical stats,
under a frozen clock. Also spies the structural invariants the plan freezes:
_window_prefetch still does the batch MD fetch, one fresh scheduler per
window, and the rolling runner is never routed.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))
sys.path.insert(0, str(PROD_ROOT / "scripts"))

import pipeline.production.batch_bert_pipeline_wf4 as batch_bert_mod  # noqa: E402
import pipeline.production.config as config_mod  # noqa: E402
import pipeline.production.monitor as monitor_mod  # noqa: E402
import pipeline.production.post_llm as post_llm  # noqa: E402
import pipeline.production.run_paths as run_paths  # noqa: E402
import pipeline.production.staged_pipeline_wf4 as staged_mod  # noqa: E402
import run_bulk  # noqa: E402
from pipeline.production.post_llm import PaperFinalization  # noqa: E402
from pipeline.production.staged_pipeline_wf4 import StagedPipelineWf4  # noqa: E402

WF = "prod-wf4-llm-datasets-experiment"
FIXED_TS = "2026-08-21T00:00:00Z"
_REAL_WINDOW_PREFETCH = run_bulk._window_prefetch  # captured before any patching

WINDOW_CFG = {
    "scheduler_mode": "staged",
    "bert_pipeline_mode": "global_batch",
    "workflow": WF,
    "llm_concurrency": 1,
    "llm_timeout": 30,
    "bert_batch_size": 32,
    "bert_batch_max_papers": 2,  # both papers cross-batch deterministically
    "bert_batch_max_sentences": 1500,
    "bert_batch_max_chars": 300000,
    "bert_batch_max_wait_ms": 20,
    "bert_endpoint_concurrency": 1,
    "prep_queue_maxsize": 8,
    "llm_queue_maxsize": 8,
    "post_queue_maxsize": 8,
    "write_queue_maxsize": 8,
    "prep_workers": 1,
    "post_workers": 1,
    "md_fetch_concurrency": 2,
    "md_fetch_retries": 1,
}


class _FlatClock:
    """perf_counter always returns the same instant: every wait/elapsed is 0
    regardless of thread interleaving — the only way two multi-threaded runs
    can be compared byte-for-byte."""

    @staticmethod
    def perf_counter() -> float:
        return 12345.6

    @staticmethod
    def monotonic() -> float:
        return 12345.6

    @staticmethod
    def time() -> float:
        return 1800000000.0

    @staticmethod
    def sleep(_s: float) -> None:
        return None


class _SpyPipe(StagedPipelineWf4):
    constructions = 0

    def __init__(self, *args, **kwargs) -> None:
        type(self).constructions += 1
        super().__init__(*args, **kwargs)

    def _staged_sampler(self, stop_event, queues, heartbeat=None) -> None:
        # keep the thread/join contract; skip depth sampling (sampling races
        # would make queue_depth_max nondeterministic across runs)
        stop_event.wait(0.02)


def _install_stage_fakes(monkeypatch, tmp_path: Path) -> None:
    def fake_prep(self, pid: str) -> None:
        job = self.jobs[pid]
        job.paper_start_perf = _FlatClock.perf_counter()
        job.ctx = SimpleNamespace(
            paper_id=pid, md_path=Path("d.md"), run_id="x", workflow_id=WF,
            dry_run=False, raw_md="md", partials={}, set=lambda r: None,
        )
        job.prepared = SimpleNamespace(english_sentences=["s1 s2"], clean_stats={})

    def fake_bert(self, prepared_map):
        return {pid: SimpleNamespace(timings={"bert_amortized_sec": 0.0}) for pid in prepared_map}

    def fake_qwen(job, **kw):
        job.timings["llm_wait_sec"] = 0.0
        job.timings["llm_elapsed_sec"] = 0.5

    def fake_post(job, **kw):
        pred = {
            "paper_id": job.paper_id,
            "run_id": "compat/job_batch_000",
            "workflow_id": WF,
            "experiments": [{"experiment_name": "E1"}],
        }
        base = tmp_path / "compat/job_batch_000"
        fin = PaperFinalization(
            paper_id=job.paper_id,
            run_id="compat/job_batch_000",
            workflow_id=WF,
            dry_run=False,
            prediction=pred,
            monitor={"paper_id": job.paper_id, "pipeline_stages": {}},
            pred_path=base / "predictions" / f"{job.paper_id}.json",
            mon_path=base / "monitors" / f"{job.paper_id}_monitor.json",
            experiments=pred["experiments"],
            provenance=[],
            error=None,
        )
        job.timings["post_llm_elapsed_sec"] = 0.25
        job.timings["paper_wall_sec"] = 0.75
        return fin

    monkeypatch.setattr(StagedPipelineWf4, "_prep_paper", fake_prep)
    monkeypatch.setattr(StagedPipelineWf4, "_global_batch_fn", fake_bert)
    monkeypatch.setattr(staged_mod, "run_qwen_http_stage", fake_qwen)
    monkeypatch.setattr(staged_mod, "run_post_stage", fake_post)


def _run_window_once(
    monkeypatch, tmp_path: Path, *, cfg: dict, spy: dict
) -> dict:
    for mod in (post_llm, config_mod, run_paths):
        monkeypatch.setattr(mod, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "PARTIALS_DIR", tmp_path / "partials")
    monkeypatch.setattr(monitor_mod, "RUN_HISTORY_PATH", tmp_path / "history.jsonl")
    monkeypatch.setenv("PROD_SKIP_PAPER_MONITOR", "1")

    flat = _FlatClock()
    monkeypatch.setattr(staged_mod, "time", flat)
    monkeypatch.setattr(batch_bert_mod, "time", flat)
    monkeypatch.setattr(run_bulk, "_utc", lambda: FIXED_TS)
    monkeypatch.setattr(staged_mod, "utc_now", lambda: FIXED_TS)
    monkeypatch.setattr(batch_bert_mod, "utc_now", lambda: FIXED_TS)  # bert_started/finished_at
    monkeypatch.setattr(run_bulk, "EVAL_MD_CACHE_DIR", tmp_path / "mdcache")
    monkeypatch.setattr(run_bulk, "_prediction_ok", lambda *a: False)

    def fake_ensure_cached(pid, url, cache_dir):
        p = Path(cache_dir) / f"{pid}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("markdown body", encoding="utf-8")
        return p, None

    monkeypatch.setattr(run_bulk, "ensure_cached", fake_ensure_cached)

    real_prefetch = _REAL_WINDOW_PREFETCH  # import-time original; re-patching
    # the module attr within one test would otherwise wrap the previous spy

    def spy_prefetch(papers, cache_dir, *, concurrency, retries):
        spy["prefetch_calls"] += 1
        spy["prefetch_papers"] += len(papers)
        return real_prefetch(papers, cache_dir, concurrency=concurrency, retries=retries)

    monkeypatch.setattr(run_bulk, "_window_prefetch", spy_prefetch)

    def _no_rolling(**kw):
        raise AssertionError("window admission must never route to _run_window_rolling")

    monkeypatch.setattr(run_bulk, "_run_window_rolling", _no_rolling)
    _SpyPipe.constructions = 0
    monkeypatch.setattr(staged_mod, "StagedPipelineWf4", _SpyPipe)

    _install_stage_fakes(monkeypatch, tmp_path)
    papers = [
        {"paper_id": "wp0", "md_url": "http://x/wp0.md"},
        {"paper_id": "wp1", "md_url": "http://x/wp1.md"},
    ]
    return run_bulk._run_window(
        paper_items=papers,
        session_run_id="compat",
        job_batch_id="job_batch_000",
        cfg=dict(cfg),
        force=False,
    )


def _tree_bytes(root: Path) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = p.read_bytes()
    return out


def test_window_absent_vs_explicit_admission_mode_byte_identical(
    tmp_path: Path, monkeypatch
) -> None:
    spy_a: dict = {"prefetch_calls": 0, "prefetch_papers": 0}
    spy_b: dict = {"prefetch_calls": 0, "prefetch_papers": 0}

    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    st_a = _run_window_once(monkeypatch, root_a, cfg=dict(WINDOW_CFG), spy=spy_a)
    st_b = _run_window_once(
        monkeypatch, root_b, cfg=dict(WINDOW_CFG, admission_mode="window"), spy=spy_b
    )

    # identical stats (window accounting, rates, batch monitor)
    assert st_a == st_b
    assert st_a["attempted"] == 2 and st_a["ok"] == 2 and st_a["skipped"] == 0
    assert st_a["batch_monitor"]["scheduler_mode"] == "staged"

    # structural spies: legacy window mechanics only
    for spy in (spy_a, spy_b):
        assert spy["prefetch_calls"] == 1  # batch MD prefetch still used
        assert spy["prefetch_papers"] == 2
    assert _SpyPipe.constructions == 1  # counted during run B (last run)

    # byte-identical run trees: predictions, progress, staged+batch monitors
    tree_a = _tree_bytes(root_a / "compat/job_batch_000")
    tree_b = _tree_bytes(root_b / "compat/job_batch_000")
    assert tree_a and tree_a == tree_b
    rel = set(tree_a)
    assert "progress.jsonl" in rel
    assert "staged_pipeline_monitor.json" in rel
    assert any(r.startswith("predictions/") for r in rel)

    # window monitor keeps the windows[] append shape; rolling keys never leak
    mon = json.loads(tree_a["staged_pipeline_monitor.json"])
    assert "windows" in mon and mon["window_count"] == 1
    assert "admission_mode" not in mon["windows"][0]
    assert "admission" not in mon["windows"][0]


def test_window_two_calls_append_second_window(tmp_path: Path, monkeypatch) -> None:
    """Same run dir, second _run_window call -> windows[] appends (per-window
    scheduler, unchanged append semantics)."""
    spy: dict = {"prefetch_calls": 0, "prefetch_papers": 0}
    root = tmp_path / "r"
    cfg = dict(WINDOW_CFG)
    _run_window_once(monkeypatch, root, cfg=cfg, spy=spy)
    _run_window_once(monkeypatch, root, cfg=cfg, spy=spy)
    mon = json.loads((root / "compat/job_batch_000/staged_pipeline_monitor.json").read_text())
    assert mon["window_count"] == 2
    assert [w["paper_count"] for w in mon["windows"]] == [2, 2]
    assert spy["prefetch_calls"] == 2


def test_validate_window_mode_has_no_rolling_keys() -> None:
    absent = run_bulk._validate_admission_config({})
    explicit = run_bulk._validate_admission_config({"admission_mode": "window"})
    assert absent == explicit == {"admission_mode": "window"}
    # the main() router keys off exactly this value; window never adds keys
    assert "rolling_target" not in absent and "md_prefetch_lookahead" not in absent


def test_scheduler_ctor_rejects_rolling_without_staged_global_batch() -> None:
    """Rolling constructors fail fast on non-staged/global_batch wiring."""
    from pipeline.production.workflows.spec import get_workflow

    spec = get_workflow(WF)
    for bad in (
        dict(rolling=True, rolling_target=4),
        dict(rolling=True, rolling_target=4, scheduler_mode="staged"),
    ):
        try:
            StagedPipelineWf4(
                [], {}, "compat/job_batch_000", spec, llm_concurrency=1, **bad
            )
            raise AssertionError(f"expected ValueError for {bad}")
        except ValueError:
            pass
    # sanity: correct wiring constructs an empty rolling scheduler
    pipe = StagedPipelineWf4(
        [], {},
        "compat/job_batch_000",
        spec,
        llm_concurrency=1,
        rolling=True,
        rolling_target=4,
        scheduler_mode="staged",
        bert_pipeline_mode="global_batch",
    )
    assert pipe.jobs == {} and pipe.paper_ids == []


def test_bert_axis_warn(tmp_path: Path) -> None:
    """V07-08 hardening: explicit snapshot configs missing bert_axis WARN (l4 lesson)."""
    # explicit snapshot without the key -> warn, naming the flat-50 fallback
    snap = tmp_path / "snapshot.yaml"
    snap.write_text("scheduler_mode: staged\n", encoding="utf-8")
    msg = run_bulk._bert_axis_warn({"scheduler_mode": "staged"}, snap)
    assert msg is not None and "bert-flat-50" in msg and str(snap) in msg
    # default.yaml path is exempt even if the key were ever removed there
    default_path = run_bulk.PROD_ROOT / "configs" / "default.yaml"
    assert run_bulk._bert_axis_warn({}, default_path) is None
    # config carrying the key never warns, whatever the path
    assert run_bulk._bert_axis_warn({"bert_axis": "bert-flat-60"}, snap) is None
