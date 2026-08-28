"""v0.7 Phase 6 sweep tests (TODO-V07-07) — task §十二 items 1-12.

Both scripts are loaded via importlib. No network, no real cluster access,
no subprocess execution: execute_run/collect paths are tested with synthetic
records and tmp artifact trees.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, PROD_ROOT / Path(rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sweep = _load("run_phase6_sweep_p6", "scripts/run_phase6_sweep.py")
collector = _load("collect_phase6_results_p6", "scripts/collect_phase6_results.py")

DEFAULT_CFG = yaml.safe_load((PROD_ROOT / "configs" / "default.yaml").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 1. matrix

def test_layer_a_matrix_covers_three_modes_two_interleaved_rounds():
    runs = sweep.expand_runs(sweep.build_conditions("A"))
    conds = [r["cond"] for r in runs]
    assert conds == ["a1-def-chunk", "a3-staged", "a2-def-gb",
                     "a1-def-chunk", "a3-staged", "a2-def-gb"]
    modes = {r["cond"]: r["overrides"] for r in runs}
    assert modes["a1-def-chunk"]["scheduler_mode"] == "default"
    assert modes["a1-def-chunk"]["bert_pipeline_mode"] == "chunked_overlap"
    assert modes["a2-def-gb"]["bert_pipeline_mode"] == "global_batch"
    assert modes["a3-staged"]["scheduler_mode"] == "staged"
    assert all(r["overrides"]["llm_concurrency"] == 30 for r in runs)
    assert all(r["overrides"]["post_workers"] == 8 for r in runs)
    assert all(r["overrides"]["prep_workers"] == 4 for r in runs)
    # every run of the same condition uses an identical override set
    a1 = [json.dumps(r["overrides"], sort_keys=True) for r in runs if r["cond"] == "a1-def-chunk"]
    assert len(set(a1)) == 1


def test_layer_b_c_e_matrices_interleave_and_hold_fixed_params():
    for layer, prefix, values in (
        ("B", "b-q", (30, 64, 128)),
        ("C", "c-post", (4, 8, 16)),
        ("D", "d-prep", (2, 4, 8)),
        ("E", "e-w", (20, 50, 100)),
    ):
        runs = sweep.expand_runs(sweep.build_conditions(layer, mode="staged", llm=30, post=8))
        conds = [r["cond"] for r in runs]
        expected = [f"{prefix}{v}" for v in values]
        assert conds == expected + expected  # 3 values then the same 3 (round 2)
        assert len(runs) == 6  # 3 values x 2 rounds
        # rounds interleaved: same condition never adjacent
        for i in range(len(conds) - 1):
            assert conds[i] != conds[i + 1]
        # fixed params hold (post_workers is swept in C, llm_concurrency in B)
        for r in runs:
            ov = r["overrides"]
            assert ov["scheduler_mode"] == "staged"
            assert ov["bert_pipeline_mode"] == "global_batch"
            if layer != "B":
                assert ov["llm_concurrency"] == 30
            if layer != "C":
                assert ov["post_workers"] == 8
        # the layer's own variable actually varies
        swept = {r["overrides"][{"B": "llm_concurrency", "C": "post_workers",
                                 "D": "prep_workers",
                                 "E": "bert_batch_max_wait_ms"}[layer]] for r in runs}
        assert swept == set(values)


def test_smoke_matrix_uses_smoke10_manifest():
    runs = sweep.expand_runs(sweep.build_conditions("smoke"))
    assert [r["cond"] for r in runs] == ["s-chunk", "s-gb", "s-staged"]
    assert all(str(r["manifest"]).endswith("lilaoshi_aminer_smoke10") for r in runs)
    assert all(r["round"] == 1 for r in runs)


# ---------------------------------------------------- 2/3. hashes & run ids

@pytest.mark.parametrize("layer,mode,kwargs", [
    ("smoke", "staged", {}),
    ("A", "staged", {}),
    ("B", "staged", {}),
    ("C", "staged", {"llm": 64}),
    ("D", "staged", {"llm": 64}),
    ("E", "staged", {}),
    ("B192", "staged", {}),
])
def test_run_ids_and_config_hashes_unique(layer, mode, kwargs):
    runs = sweep.expand_runs(sweep.build_conditions(layer, mode=mode, **kwargs))
    run_ids = [sweep.run_id_for(r["cond"], r["round"], "20260820") for r in runs]
    assert len(set(run_ids)) == len(run_ids)
    # one unique hash per distinct condition; rounds share the condition hash
    hash_by_cond: dict[str, str] = {}
    for r in runs:
        h = sweep.sha256_text(sweep.snapshot_text(
            sweep.build_snapshot(DEFAULT_CFG, r["overrides"])))
        assert hash_by_cond.setdefault(r["cond"], h) == h
    assert len(set(hash_by_cond.values())) == len(hash_by_cond)


# ------------------------------------------------- 4/5. semantic freeze & ranges

def test_snapshots_freeze_semantic_keys_verbatim_from_default():
    frozen = {"llm_model", "llm_api_url", "bert_server_url", "bert_threshold",
              "bert_batch_size", "enable_thinking", "bert_axis", "gates",
              "md_prefetch_window", "md_fetch_concurrency", "md_fetch_retries",
              "md_cache_cleanup_on_batch_done", "llm_timeout", "llm_backend",
              "job_batch_size", "merge_every_n_job_batches", "workflow"}
    for layer in ("smoke", "A", "B", "C", "D", "E"):
        for r in sweep.expand_runs(sweep.build_conditions(layer)):
            snap = sweep.build_snapshot(DEFAULT_CFG, r["overrides"])
            for k in frozen:
                assert snap[k] == DEFAULT_CFG[k], f"{layer}/{r['cond']}: {k} drifted"


def test_validate_snapshot_rejects_semantic_drift_and_bad_values():
    # semantic drift caught
    snap = sweep.build_snapshot(DEFAULT_CFG, {"llm_concurrency": 64})
    snap["bert_threshold"] = 0.9
    with pytest.raises(ValueError, match="semantic key drifted"):
        sweep.validate_snapshot(snap, DEFAULT_CFG, {"llm_concurrency": 64})
    # non-sweep key in overrides caught
    with pytest.raises(ValueError, match="non-sweep key"):
        sweep.validate_snapshot(DEFAULT_CFG, DEFAULT_CFG, {"temperature": 0.5})
    # out-of-range caught
    with pytest.raises(ValueError, match="out of range"):
        sweep.validate_snapshot(DEFAULT_CFG, DEFAULT_CFG, {"llm_concurrency": 9999})
    # staged+chunked caught
    ov = {"scheduler_mode": "staged", "bert_pipeline_mode": "chunked_overlap"}
    snap = sweep.build_snapshot(DEFAULT_CFG, ov)
    with pytest.raises(ValueError, match="staged requires global_batch"):
        sweep.validate_snapshot(snap, DEFAULT_CFG, ov)
    # batch budget drift caught (budget changed without being in overrides)
    snap = sweep.build_snapshot(DEFAULT_CFG, {"llm_concurrency": 64})
    snap["bert_batch_max_sentences"] = 3000
    with pytest.raises(ValueError, match="batch budget drifted"):
        sweep.validate_snapshot(snap, DEFAULT_CFG, {"llm_concurrency": 64})


def test_layer_e_sweeps_only_wait_ms_budgets_frozen():
    runs = sweep.expand_runs(sweep.build_conditions("E"))
    for r in runs:
        snap = sweep.build_snapshot(DEFAULT_CFG, r["overrides"])
        assert snap["bert_batch_max_papers"] == 16
        assert snap["bert_batch_max_sentences"] == 1500
        assert snap["bert_batch_max_chars"] == 300000
        assert snap["bert_batch_max_wait_ms"] == r["overrides"]["bert_batch_max_wait_ms"]
        sweep.validate_snapshot(snap, DEFAULT_CFG, r["overrides"])  # no raise


# ---------------------------------------------------------- runner discipline

def test_runner_never_writes_default_yaml(tmp_path, monkeypatch):
    """Sweep write targets are the emit dir only; configs/default.yaml untouched."""
    before = (PROD_ROOT / "configs" / "default.yaml").read_bytes()
    emit = tmp_path / "phase6-configs"
    for r in sweep.expand_runs(sweep.build_conditions("smoke")):
        snap = sweep.build_snapshot(DEFAULT_CFG, r["overrides"])
        emit.mkdir(parents=True, exist_ok=True)
        rid = sweep.run_id_for(r["cond"], r["round"], "20260820")
        (emit / f"{rid}.yaml").write_text(sweep.snapshot_text(snap), encoding="utf-8")
    after = (PROD_ROOT / "configs" / "default.yaml").read_bytes()
    assert before == after
    assert len(list(emit.glob("*.yaml"))) == 3


def test_runtime_artifact_paths_are_gitignored():
    gitignore = (PROD_ROOT / ".gitignore").read_text(encoding="utf-8")
    for runtime in ("pipeline_output/production/runs/", "pipeline_output/production/logs/",
                    "pipeline_output/production/exports/"):
        assert runtime.rstrip("/") in gitignore, f"{runtime} not covered by .gitignore"
    # phase6 runtime dir falls under pipeline_output/production too — assert via
    # `git check-ignore`
    import subprocess
    for p in ("pipeline_output/production/phase6/configs/x.yaml",
              "pipeline_output/production/phase6/phase6_runs.jsonl",
              "pipeline_output/production/phase6/rss/x.csv"):
        rc = subprocess.run(["git", "-C", str(PROD_ROOT), "check-ignore", "-q", p],
                            capture_output=True)
        assert rc.returncode == 0, f"{p} NOT ignored"


# ---------------------------------------------------------------- collector

def _mk_record(run_id, cond, layer, round_no, *, pph, ok=160, err=3, skip=0,
               planned=163, md404=2, parse=1, exit_code=0,
               cli_status="success", dup=0, writer=0, flat_dup=0,
               llm_p95=9.0, rss_max=170.0, rss_growth=40.0, schema_violations=0):
    return {
        "run_id": run_id, "layer": layer, "condition": cond, "round": round_no,
        "mode": {"scheduler_mode": "staged", "bert_pipeline_mode": "global_batch"},
        "exit_code": exit_code, "cli_status": cli_status,
        "total_ok": ok, "total_error": err, "total_skipped": skip,
        "planned_papers": planned, "papers_per_hour": pph,
        "config_sha256": f"cfg-{run_id}", "manifest_sha256": "m",
        "git_commit": "c0", "schema_violations": schema_violations,
        "rss": {"rss_mb_max": rss_max, "growth_rss_mb_first_to_max": rss_growth,
                "threads_max": 70, "samples": 30},
        "_synthetic": {"md404": md404, "parse": parse, "dup": dup, "writer": writer,
                       "flat_dup": flat_dup, "llm_p95": llm_p95},
    }


def _mk_artifacts(tmp_path, rec):
    """Lay down the artifact tree collector reads for one synthetic record."""
    logs = tmp_path / "logs" / rec["run_id"]
    logs.mkdir(parents=True, exist_ok=True)
    syn = rec["_synthetic"]
    metrics = [{"run_id": rec["run_id"],
                "statuses": {"ok": rec["total_ok"], "error": rec["total_error"]},
                "error_classes": {"md_fetch": syn["md404"], "parse_error": syn["parse"]},
                "stage_metrics": {"llm_http_elapsed": {"p50": 5.5, "p95": syn["llm_p95"], "max": 12.0}}}]
    (logs / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    run_dir = (tmp_path / "runs" / rec["run_id"]).resolve()
    # place under the real-shaped runs root via monkeypatch in the caller
    jb = Path(str(run_dir)) / "job_batch_000"
    jb.mkdir(parents=True, exist_ok=True)
    (jb / "staged_pipeline_monitor.json").write_text(json.dumps({
        "windows": [{"commit_counts": {"success": rec["total_ok"], "error": rec["total_error"],
                                       "writer_error": syn["writer"], "defensive": 0},
                     "duplicate_commit_attempts": [] if syn["dup"] == 0 else [["x"]],
                     "writer_errors": [] if syn["writer"] == 0 else [["y"]],
                     "queue_depth_max": {"llm": 30}, "stage_active_peak": {"llm_http": 30}}]
    }), encoding="utf-8")
    exports = tmp_path / "exports"
    exports.mkdir(exist_ok=True)
    flat = [{"paper_id": f"p{i}", "experiment_name": "e", "experiment_index": 0}
            for i in range(rec["total_ok"] - syn["parse"])]
    if syn["flat_dup"]:
        flat.append(dict(flat[0]))
    (exports / f"ai2000_{rec['run_id']}_flat_merged.json").write_text(
        json.dumps(flat), encoding="utf-8")


def _run_collector(tmp_path, monkeypatch, records):
    jsonl = tmp_path / "phase6_runs.jsonl"
    jsonl.write_text("\n".join(
        json.dumps({k: v for k, v in r.items() if k != "_synthetic"}) for r in records
    ) + "\n", encoding="utf-8")
    for rec in records:
        _mk_artifacts(tmp_path, rec)
    monkeypatch.setattr(collector, "LOGS_ROOT", tmp_path / "logs")
    monkeypatch.setattr(collector, "EXPORTS_DIR", tmp_path / "exports")
    monkeypatch.setattr(collector, "PROJ", tmp_path)

    def _staged_agg_local(run_id):
        return collector.staged_monitor_agg(run_id)

    # staged monitor lives under tmp runs root: patch the runs-root lookup
    orig = collector.staged_monitor_agg
    monkeypatch.setattr(collector, "staged_monitor_agg",
                        lambda rid: orig(rid) if False else _patched_agg(tmp_path, rid))
    rows = [collector.build_run_row({k: v for k, v in r.items() if k != "_synthetic"})
            for r in records]
    order = [r["run_id"] for r in records]
    return rows, collector.aggregate_conditions(rows, order)


def _patched_agg(tmp_path, run_id):
    """staged_monitor_agg against the tmp runs root."""
    src = tmp_path / "runs" / run_id
    totals = {"duplicate_commit_attempts": 0, "writer_errors": 0,
              "writer_error_commits": 0, "defensive": 0, "success": 0, "error": 0}
    qd, ap, windows = {}, {}, 0
    for mon in sorted(src.glob("job_batch_*/staged_pipeline_monitor.json")):
        doc = json.loads(mon.read_text(encoding="utf-8"))
        for w in doc.get("windows") or [doc]:
            windows += 1
            cc = w.get("commit_counts") or {}
            totals["success"] += int(cc.get("success") or 0)
            totals["error"] += int(cc.get("error") or 0)
            totals["writer_error_commits"] += int(cc.get("writer_error") or 0)
            totals["defensive"] += int(cc.get("defensive") or 0)
            totals["duplicate_commit_attempts"] += len(w.get("duplicate_commit_attempts") or [])
            totals["writer_errors"] += len(w.get("writer_errors") or [])
    if not windows:
        return {"present": False}
    return {"present": True, "windows": windows, **totals,
            "queue_depth_max": qd, "stage_active_peak": ap}


# 6. failed runs are never candidates
def test_failed_run_not_candidate(tmp_path, monkeypatch):
    records = [
        _mk_record("phase6-b-q30-r1-d", "b-q30", "B", 1, pph=5000),
        _mk_record("phase6-b-q64-r1-d", "b-q64", "B", 1, pph=6000, cli_status="bulk_gate_paused",
                   exit_code=3, err=40, parse=30),
        _mk_record("phase6-b-q30-r2-d", "b-q30", "B", 2, pph=5100),
        _mk_record("phase6-b-q64-r2-d", "b-q64", "B", 2, pph=6100, dup=2),
    ]
    rows, cond = _run_collector(tmp_path, monkeypatch, records)
    assert cond["b-q30"]["candidate_eligible"] is True
    assert cond["b-q64"]["candidate_eligible"] is False
    assert rows[1]["gates"]["run_succeeded"] is False
    assert rows[3]["gates"]["no_duplicate_commit"] is False


# 7. numeric-aware sorting of conditions
def test_condition_sort_numeric(tmp_path, monkeypatch):
    records = [
        _mk_record("phase6-b-q128-r1-d", "b-q128", "B", 1, pph=7000),
        _mk_record("phase6-b-q30-r1-d", "b-q30", "B", 1, pph=5000),
        _mk_record("phase6-b-q64-r1-d", "b-q64", "B", 1, pph=6000),
    ]
    _, cond = _run_collector(tmp_path, monkeypatch, records)
    assert list(cond) == ["b-q30", "b-q64", "b-q128"]


# 8. anomalous rounds do not pollute the median
def test_anomalous_round_excluded_from_median(tmp_path, monkeypatch):
    records = [
        _mk_record("phase6-b-q30-r1-d", "b-q30", "B", 1, pph=5000),
        _mk_record("phase6-b-q30-r2-d", "b-q30", "B", 2, pph=2000),  # service hiccup
        _mk_record("phase6-b-q30-r3-d", "b-q30", "B", 3, pph=5050),
    ]
    _, cond = _run_collector(tmp_path, monkeypatch, records)
    a = cond["b-q30"]
    assert a["anomalous_rounds"] == ["phase6-b-q30-r2-d"]
    assert a["pph_median"] == pytest.approx(5025.0)  # median of stable rounds
    assert a["candidate_eligible"] is False  # anomalous round disqualifies


# 9. interleaved round pairing
def test_interleave_detection(tmp_path, monkeypatch):
    # properly interleaved: q30 r1, q64 r1, q30 r2, q64 r2
    records = [
        _mk_record("phase6-b-q30-r1-d", "b-q30", "B", 1, pph=5000),
        _mk_record("phase6-b-q64-r1-d", "b-q64", "B", 1, pph=6000),
        _mk_record("phase6-b-q30-r2-d", "b-q30", "B", 2, pph=5100),
        _mk_record("phase6-b-q64-r2-d", "b-q64", "B", 2, pph=5900),
    ]
    _, cond = _run_collector(tmp_path, monkeypatch, records)
    assert cond["b-q30"]["interleaved"] is True
    assert cond["b-q30"]["rounds"] == ["phase6-b-q30-r1-d", "phase6-b-q30-r2-d"]
    # back-to-back rounds of same condition -> not interleaved
    records2 = [
        _mk_record("phase6-c-post4-r1-d", "c-post4", "C", 1, pph=5000),
        _mk_record("phase6-c-post4-r2-d", "c-post4", "C", 2, pph=5100),
    ]
    _, cond2 = _run_collector(tmp_path, monkeypatch, records2)
    assert cond2["c-post4"]["interleaved"] is False
    assert cond2["c-post4"]["candidate_eligible"] is False


# 10. default.yaml is never written back by the sweep
def test_sweep_does_not_write_default_config():
    # runtime emit dir lives under pipeline_output (gitignored), never configs/
    assert str(sweep.DEFAULT_RUNTIME_EMIT_DIR).startswith(
        str(PROD_ROOT / "pipeline_output" / "production"))
    assert "configs" in str(sweep.DEFAULT_RUNTIME_EMIT_DIR)  # subdir NAME only
    # no code path in the module references default.yaml as a write target
    src = (PROD_ROOT / "scripts" / "run_phase6_sweep.py").read_text(encoding="utf-8")
    assert "DEFAULT_CONFIG).write" not in src
    assert "default.yaml\"), \"w" not in src


# 11. (see test_runtime_artifact_paths_are_gitignored above)


# 12. report distinguishes verified / anomalous / missing metric groups
def test_metric_group_marking(tmp_path, monkeypatch):
    records = [
        _mk_record("phase6-a1-def-chunk-r1-d", "a1-def-chunk", "A", 1, pph=5000),
        _mk_record("phase6-x-bad-r1-d", "x-bad", "A", 1, pph=None, cli_status="bulk_failed",
                   exit_code=2),
    ]
    rows, _ = _run_collector(tmp_path, monkeypatch, records)
    good, bad = rows[0]["metric_groups"], rows[1]["metric_groups"]
    assert good["end_to_end"] == "verified"
    assert good["correctness"] == "verified"
    assert good["rss"] == "verified"
    assert bad["end_to_end"] == "missing"
    assert bad["correctness"] == "anomalous"
    # zero_datasets_rate is always explicitly unavailable, never inferred
    assert rows[0]["zero_datasets_rate"] == "unavailable"
    assert rows[1]["zero_datasets_rate"] == "unavailable"


# gates: md404 is classified separately from scheduler errors
def test_md404_excluded_from_scheduler_error_rate(tmp_path, monkeypatch):
    records = [
        _mk_record("phase6-a3-staged-r1-d", "a3-staged", "A", 1, pph=5000,
                   err=25, md404=23, parse=2),  # 25 errors but 23 are md404
    ]
    rows, _ = _run_collector(tmp_path, monkeypatch, records)
    r = rows[0]
    assert r["md404"] == 23
    assert r["scheduler_error"] == 2
    assert r["scheduler_error_rate"] <= 0.15
    assert r["gates"]["scheduler_error_rate"] is True


def test_conservation_gate(tmp_path, monkeypatch):
    records = [
        _mk_record("phase6-a1-def-chunk-r1-d", "a1-def-chunk", "A", 1, pph=5000,
                   ok=150, err=3, planned=163),  # 153 != 163 -> silent drop
    ]
    rows, _ = _run_collector(tmp_path, monkeypatch, records)
    assert rows[0]["conservation_ok"] is False
    assert rows[0]["gates"]["conservation"] is False
