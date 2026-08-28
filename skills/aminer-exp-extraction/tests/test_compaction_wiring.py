"""TODO-V07-11 c3 wiring: run_bulk hook + default.yaml key + consumer
compatibility (merge_flat compacted runs, phase7 monitors.jsonl)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

import pipeline.production.compaction as cmp_mod  # noqa: E402
import pipeline.production.config as config_mod  # noqa: E402
import pipeline.production.monitor as monitor_mod  # noqa: E402
import pipeline.production.run_paths as run_paths  # noqa: E402
from pipeline.production import completion_ledger as cl  # noqa: E402
from pipeline.production.schema import empty_experiment  # noqa: E402

import yaml  # noqa: E402


def _load_script(module_name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(
        module_name, PROD_ROOT / "scripts" / f"{file_name}.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Env:
    def __init__(self, monkeypatch, tmp_path: Path, session: str = "wiring1") -> None:
        self.session = session
        self.runs = tmp_path / "runs"
        monkeypatch.setattr(run_paths, "RUNS_DIR", self.runs)
        monkeypatch.setattr(config_mod, "RUNS_DIR", self.runs)
        monkeypatch.setattr(config_mod, "PARTIALS_DIR", tmp_path / "partials")
        monkeypatch.setattr(config_mod, "RUN_HISTORY_PATH", tmp_path / "history.jsonl")
        monkeypatch.setattr(monitor_mod, "RUN_HISTORY_PATH", tmp_path / "history.jsonl")
        cl.reset_cache()

    def write_prediction(self, pid: str, jb: str = "job_batch_000", n_exp: int = 1,
                         title: str | None = None) -> Path:
        exps = []
        for j in range(n_exp):
            e = empty_experiment(pid)
            e.pop("research_problem", None)
            e["experiment_name"] = f"E{j}"
            exps.append(e)
        pred = {
            "paper_id": pid,
            "run_id": f"{self.session}/{jb}",
            "workflow_id": "prod-wf4-llm-datasets-experiment",
            "workflow_version": "0.7.0",
            "paper_title": title or f"Title {pid}",
            "research_problem": "RP",
            "research_problem_description": "RPD",
            "research_problem_aliases": [],
            "experiments": exps,
        }
        d = self.runs / self.session / jb / "predictions"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{pid}.json"
        p.write_text(json.dumps(pred, indent=2) + "\n", encoding="utf-8")
        return p

    def write_monitor(self, pid: str, jb: str = "job_batch_000", chars: int = 77) -> None:
        d = self.runs / self.session / jb / "monitors"
        d.mkdir(parents=True, exist_ok=True)
        mon = {"paper_id": pid, "run_id": f"{self.session}/{jb}",
               "extractors": [{"extractor_id": "llm.wf4_dev20_v2_wash_datasets",
                               "metadata": {"prompt_chars": chars}}]}
        (d / f"{pid}_monitor.json").write_text(json.dumps(mon), encoding="utf-8")


# ---------------------------------------------------------------------------
# config & run_bulk hook
# ---------------------------------------------------------------------------

def test_default_yaml_opts_in_at_20000() -> None:
    cfg = yaml.safe_load((PROD_ROOT / "configs" / "default.yaml").read_text(encoding="utf-8"))
    assert cfg["compaction_every_n_papers"] == 20000


def test_run_bulk_hook_code_default_disabled(monkeypatch, tmp_path: Path) -> None:
    run_bulk = _load_script("run_bulk_wiring1", "run_bulk")
    monkeypatch.setattr(run_bulk, "RUNS_DIR", tmp_path / "runs")
    calls: list[tuple] = []
    monkeypatch.setattr(run_bulk.compaction, "maybe_compact",
                        lambda *a, **kw: calls.append((a, kw)) or None)
    blog = type("B", (), {"line": staticmethod(lambda msg: None)})()

    run_bulk._maybe_compact_after_batch({}, "sess", blog=blog)          # key absent -> 0
    run_bulk._maybe_compact_after_batch({"compaction_every_n_papers": 0}, "sess", blog=blog)
    assert calls == []

    run_bulk._maybe_compact_after_batch({"compaction_every_n_papers": 5}, "sess", blog=blog)
    assert len(calls) == 1
    assert calls[0][0] == ("sess", 5)  # (session, every); log passed as kwarg


def test_run_id_predictions_alive(monkeypatch, tmp_path: Path) -> None:
    run_bulk = _load_script("run_bulk_wiring2", "run_bulk")
    monkeypatch.setattr(run_bulk, "RUNS_DIR", tmp_path / "runs")
    pred = tmp_path / "runs" / "sess" / "job_batch_000" / "predictions" / "a.json"
    pred.parent.mkdir(parents=True)

    assert run_bulk._run_id_predictions_alive("sess/job_batch_000") is False
    pred.write_text("{}", encoding="utf-8")
    assert run_bulk._run_id_predictions_alive("sess/job_batch_000") is True
    pred.unlink()
    assert run_bulk._run_id_predictions_alive("sess/job_batch_000") is False


# ---------------------------------------------------------------------------
# merge_flat compacted-run support
# ---------------------------------------------------------------------------

def test_merge_flat_compacted_run_base_plus_tail_override(tmp_path: Path, monkeypatch,
                                                          capsys) -> None:
    env = _Env(monkeypatch, tmp_path)
    env.write_prediction("a", n_exp=1, title="A old")
    env.write_prediction("b", jb="job_batch_000", n_exp=2, title="B old")
    env.write_prediction("c", jb="job_batch_000", n_exp=1, title="C old")
    res = cmp_mod.compact_session(env.session)
    assert res["papers"] == 3 and res["flat_rows"] == 4

    # post-compaction rerun of paper b lands on disk in a later batch
    env.write_prediction("b", jb="job_batch_001", n_exp=1, title="B new")

    mf = _load_script("merge_flat_wiring1", "merge_flat_experiments")
    out = tmp_path / "out" / "merged.json"
    monkeypatch.setattr(sys, "argv", [
        "merge_flat_experiments.py",
        "--run-dir", str(env.runs / env.session),
        "--out", str(out),
    ])
    mf.main()

    rows = json.loads(out.read_text(encoding="utf-8"))
    assert len(rows) == 3  # a(1) + c(1) from compaction base + b(1) from disk
    by_pid: dict[str, list[dict]] = {}
    for r in rows:
        by_pid.setdefault(r["paper_id"], []).append(r)
    assert set(by_pid) == {"a", "b", "c"}
    assert len(by_pid["b"]) == 1                       # disk overrode base's 2 rows
    assert by_pid["b"][0]["paper_title"] == "B new"
    assert by_pid["a"][0]["paper_title"] == "A old"    # base rows intact
    assert not out.with_name(out.name + ".tmp").exists()  # atomic write, no residue
    assert "compaction base: 3 papers (4 rows)" in capsys.readouterr().out


def test_merge_flat_plain_run_unchanged(tmp_path: Path, monkeypatch) -> None:
    """No compaction dir -> behavior identical to the pre-V07-11 path."""
    env = _Env(monkeypatch, tmp_path)
    env.write_prediction("a", n_exp=1)
    env.write_prediction("b", jb="job_batch_001", n_exp=2)

    mf = _load_script("merge_flat_wiring2", "merge_flat_experiments")
    out = tmp_path / "out" / "merged.json"
    monkeypatch.setattr(sys, "argv", [
        "merge_flat_experiments.py",
        "--run-dir", str(env.runs / env.session),
        "--out", str(out),
    ])
    mf.main()
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert len(rows) == 3


# ---------------------------------------------------------------------------
# phase7 prompt_chars loader reads window monitors.jsonl
# ---------------------------------------------------------------------------

def test_phase7_load_prompt_chars_reads_window_jsonl(tmp_path: Path, monkeypatch) -> None:
    env = _Env(monkeypatch, tmp_path)
    env.write_prediction("a", n_exp=1)
    env.write_monitor("a", chars=111)
    env.write_prediction("b", n_exp=1)
    env.write_monitor("b", chars=222)
    cmp_mod.compact_session(env.session)  # monitors move into window monitors.jsonl

    p7 = _load_script("phase7_wiring1", "phase7_compare_predictions")
    monkeypatch.setattr(p7, "RUNS", env.runs)
    got = p7.load_prompt_chars(env.session)
    assert got == {"a": 111, "b": 222}


if __name__ == "__main__":
    raise SystemExit("run via pytest")
