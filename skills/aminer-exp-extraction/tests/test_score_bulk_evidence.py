"""score_bulk_evidence._score_prediction per-experiment evidence write-back.

Plus TODO-EV-02 coverage for the --manifests-dir parameter: default keeps the
legacy manifests/job_batches path, per-corpus layouts resolve, and a same-named
job_batch_000.json in another directory is never misread.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

from dataset_evidence import score_bulk_evidence as sbe  # noqa: E402
from dataset_evidence.score_bulk_evidence import _score_prediction  # noqa: E402


class _FakeEvidenceRuleV4:
    """Stands in for the vendored EvidenceRuleV4; returns per-experiment results."""

    @staticmethod
    def extract_for_paper(raw_md: str, experiments: list[dict], input_mode: str):
        assert input_mode == "full_text"
        # Mirror the real contract: one result per input experiment, in order.
        return [
            {**exp, "evidence": [f"ev-{i}-{j}" for j in range(i + 1)]}
            for i, exp in enumerate(experiments)
        ]


def _two_exp_prediction() -> dict:
    return {
        "paper_id": "p1",
        "experiments": [
            {"experiment_name": "Main", "methods": []},
            {"experiment_name": "Ablation", "methods": []},
        ],
    }


def test_writes_evidence_to_every_experiment(tmp_path: Path) -> None:
    md = tmp_path / "p1.md"
    md.write_text("paper body", encoding="utf-8")
    pred = _two_exp_prediction()

    scored, status = _score_prediction(pred, md, _FakeEvidenceRuleV4, force=False)

    assert status["success"] is True
    assert scored["experiments"][0]["evidence"] == ["ev-0-0"]
    assert scored["experiments"][1]["evidence"] == ["ev-1-0", "ev-1-1"]
    # Total across all experiments, not just experiments[0].
    assert status["evidence_count"] == 3


def test_partial_evidence_is_not_skipped(tmp_path: Path) -> None:
    """exp0 has evidence but exp1 does not -> paper must be processed, not skipped."""
    md = tmp_path / "p1.md"
    md.write_text("paper body", encoding="utf-8")
    pred = _two_exp_prediction()
    pred["experiments"][0]["evidence"] = ["old-ev"]

    scored, status = _score_prediction(pred, md, _FakeEvidenceRuleV4, force=False)

    assert status.get("skipped") is not True
    assert scored["experiments"][0]["evidence"] == ["ev-0-0"]
    assert scored["experiments"][1]["evidence"] == ["ev-1-0", "ev-1-1"]


def test_all_experiments_have_evidence_is_skipped(tmp_path: Path) -> None:
    md = tmp_path / "p1.md"
    md.write_text("paper body", encoding="utf-8")
    pred = _two_exp_prediction()
    pred["experiments"][0]["evidence"] = ["a"]
    pred["experiments"][1]["evidence"] = ["b", "c"]

    scored, status = _score_prediction(pred, md, _FakeEvidenceRuleV4, force=False)

    assert status.get("skipped") is True
    assert scored["experiments"][0]["evidence"] == ["a"]
    assert scored["experiments"][1]["evidence"] == ["b", "c"]
    assert status["evidence_count"] == 3


def _write_manifest(corpus_dir: Path, batch_id: str, papers: dict[str, str]) -> Path:
    """Write a job_batch manifest into corpus_dir; returns corpus_dir."""
    corpus_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "job_batch_id": batch_id,
        "batch_index": 0,
        "size": len(papers),
        "papers": [
            {"paper_id": pid, "md_url": url} for pid, url in papers.items()
        ],
    }
    (corpus_dir / f"{batch_id}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    return corpus_dir


def _mk_run_target(tmp_path: Path, pid: str) -> dict:
    """Fake session/job_batch run tree with one prediction for pid."""
    run_dir = tmp_path / "sess" / "job_batch_000"
    pred_dir = run_dir / "predictions"
    pred_dir.mkdir(parents=True, exist_ok=True)
    pred = _two_exp_prediction()
    pred["paper_id"] = pid
    (pred_dir / f"{pid}.json").write_text(json.dumps(pred), encoding="utf-8")
    return {
        "logical_run_id": "sess/job_batch_000",
        "job_batch_id": "job_batch_000",
        "run_dir": run_dir,
        "predictions_dir": pred_dir,
    }


def _patch_offline(monkeypatch, tmp_path: Path) -> Path:
    """Point MD cache at tmp and inject the fake evidence rule; returns cache."""
    cache = tmp_path / "md_cache"
    cache.mkdir(exist_ok=True)
    monkeypatch.setattr(sbe, "MD_CACHE_DIR", cache)
    monkeypatch.setattr(sbe, "get_evidence_v4", lambda: _FakeEvidenceRuleV4)
    return cache


def test_manifests_dir_default_is_legacy_path(tmp_path: Path, monkeypatch) -> None:
    """Without --manifests-dir, _process_run receives the legacy hardcoded path."""
    import pipeline.production.run_paths as run_paths

    sess = tmp_path / "runs" / "sess"
    (sess / "job_batch_000").mkdir(parents=True)
    captured: dict = {}

    def fake_process_run(target, concurrency, retries, dry_run, force, manifests_dir=None):
        captured["manifests_dir"] = manifests_dir
        return {"run_id": target["logical_run_id"], "total_papers": 0}

    monkeypatch.setattr(sbe, "PREDICTIONS_BASE", tmp_path / "runs")
    monkeypatch.setattr(run_paths, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(sbe, "_process_run", fake_process_run)
    monkeypatch.setattr(
        sys, "argv", ["prog", "--session-run-id", "sess", "--dry-run"]
    )
    sbe.main()

    assert captured["manifests_dir"] == sbe.MANIFESTS_DIR


def test_manifests_dir_custom_layout_resolves(tmp_path: Path, monkeypatch) -> None:
    """A per-corpus manifests dir resolves the run's manifest and scores in place."""
    pid = "p1"
    corpus = _write_manifest(
        tmp_path / "corpus_a", "job_batch_000", {pid: "http://example/p1.md"}
    )
    target = _mk_run_target(tmp_path, pid)
    cache = _patch_offline(monkeypatch, tmp_path)
    (cache / f"{pid}.md").write_text("paper body", encoding="utf-8")

    stats = sbe._process_run(
        target, concurrency=1, retries=1, dry_run=False, force=True,
        manifests_dir=corpus,
    )

    assert stats["processed"] == 1
    on_disk = json.loads(
        (target["predictions_dir"] / f"{pid}.json").read_text(encoding="utf-8")
    )
    assert on_disk["experiments"][0]["evidence"] == ["ev-0-0"]
    assert on_disk["experiments"][1]["evidence"] == ["ev-1-0", "ev-1-1"]


def test_same_batch_id_not_misread_across_manifest_dirs(
    tmp_path: Path, monkeypatch
) -> None:
    """Two corpora share job_batch_000.json; the pointed-at dir is the only source."""
    pid = "p1"
    corpus_a = _write_manifest(
        tmp_path / "corpus_a", "job_batch_000", {pid: "http://example/p1.md"}
    )
    # corpus_b has the SAME batch file name but only knows p2.
    corpus_b = _write_manifest(
        tmp_path / "corpus_b", "job_batch_000", {"p2": "http://example/p2.md"}
    )
    target = _mk_run_target(tmp_path, pid)
    cache = _patch_offline(monkeypatch, tmp_path)
    pred_path = target["predictions_dir"] / f"{pid}.json"
    before = pred_path.read_text(encoding="utf-8")

    # Pointing at corpus_b with nothing cached: p1 is not in its manifest, so
    # the (mocked-away) download path records no_md_url and the file is
    # untouched. Cached MDs bypass the manifest, so the md must be absent to
    # exercise the manifest-driven mapping.
    stats_b = sbe._process_run(
        target, concurrency=1, retries=1, dry_run=False, force=True,
        manifests_dir=corpus_b,
    )
    assert stats_b["processed"] == 0
    assert stats_b["failures"][pid] == "no_md_url_in_manifest"
    assert pred_path.read_text(encoding="utf-8") == before

    # Pointing at corpus_a: p1 resolves (cached md present) and is scored.
    (cache / f"{pid}.md").write_text("paper body", encoding="utf-8")
    stats_a = sbe._process_run(
        target, concurrency=1, retries=1, dry_run=False, force=True,
        manifests_dir=corpus_a,
    )
    assert stats_a["processed"] == 1


if __name__ == "__main__":
    test_writes_evidence_to_every_experiment(Path("/tmp/sbe-t1"))
    test_partial_evidence_is_not_skipped(Path("/tmp/sbe-t2"))
    test_all_experiments_have_evidence_is_skipped(Path("/tmp/sbe-t3"))
    print("OK: all score_bulk_evidence multi-exp tests passed")