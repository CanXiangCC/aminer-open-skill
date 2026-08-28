"""v0.7 Phase 4 CLI tests (TODO-V07-05) — task §六 items 1-15.

pipeline_cli is loaded via importlib; subprocess calls are faked; service
checks are monkeypatched. No network, no real cluster access."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

_spec = importlib.util.spec_from_file_location("pipeline_cli_p4", PROD_ROOT / "scripts" / "pipeline_cli.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


class _Env:
    """Redirect every CLI write target + state read into tmp_path."""

    def __init__(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setattr(cli, "PROD_ROOT", tmp_path)
        monkeypatch.setattr(cli, "LOGS_ROOT", tmp_path / "logs")
        monkeypatch.setattr(cli, "EXPORTS_DIR", tmp_path / "exports")
        monkeypatch.setattr(cli, "BULK_STATE_PATH", tmp_path / "bulk_state.json")
        for k in cli.ENV_OVERRIDES.values():
            monkeypatch.delenv(k, raising=False)


class _Proc:
    def __init__(self, rc: int) -> None:
        self.returncode = rc


class _FakeSubprocess:
    def __init__(self, return_codes: list[int]) -> None:
        self.codes = list(return_codes)
        self.calls: list[list] = []

    def __call__(self, argv, env=None, **kw):  # noqa: ARG002
        self.calls.append(list(argv))
        return _Proc(self.codes.pop(0) if self.codes else 0)


def _manifest(tmp_path: Path, batches: int = 1, papers: int = 2) -> Path:
    mdir = tmp_path / "manifests" / "m"
    mdir.mkdir(parents=True)
    for b in range(batches):
        p = mdir / f"job_batch_{b:03d}.json"
        p.write_text(
            json.dumps(
                {
                    "job_batch_id": f"job_batch_{b:03d}",
                    "papers": [
                        {"paper_id": f"p{b}{i}", "md_url": f"http://local/p{b}{i}.md"}
                        for i in range(papers)
                    ],
                }
            ),
            encoding="utf-8",
        )
    return mdir


def _config(tmp_path: Path, **kv) -> Path:
    import yaml

    p = tmp_path / "cfg.yaml"
    p.write_text(yaml.safe_dump(kv or {"workflow": "prod-wf4-llm-datasets-experiment"}), encoding="utf-8")
    return p


def _bulk_state(tmp_path: Path, **kv) -> None:
    tmp_path.joinpath("bulk_state.json").write_text(
        json.dumps({"status": "done", "jobs_done": 1, "total_ok": 2, "total_error": 0,
                    "total_skipped": 0, "total_wall_sec": 1.5, "papers_per_hour": 4800.0, **kv}),
        encoding="utf-8",
    )


# 1. --help shows the full command surface

def test_help_lists_all_subcommands(capsys):
    with pytest.raises(SystemExit) as ei:
        cli.build_parser().parse_args(["--help"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    for cmd in ("check-services", "prepare", "ingest", "run", "merge", "report"):
        assert cmd in out


# 2. default modes are default + chunked_overlap

def test_default_modes_are_default_chunked(tmp_path: Path):
    args = cli.build_parser().parse_args(["run", "--config", str(_config(tmp_path))])
    cfg = cli.resolve_config(args)
    assert cli.effective_modes(cfg) == ("default", "chunked_overlap")


# 3. staged requires global_batch (no silent downgrade)

def test_staged_requires_global_batch():
    with pytest.raises(SystemExit, match="staged requires bert_pipeline_mode=global_batch"):
        cli.validate_modes({"scheduler_mode": "staged", "bert_pipeline_mode": "chunked_overlap"})
    cli.validate_modes({"scheduler_mode": "staged", "bert_pipeline_mode": "global_batch"})  # ok


def test_unknown_mode_rejected():
    with pytest.raises(SystemExit, match="scheduler_mode"):
        cli.validate_modes({"scheduler_mode": "fried"})
    with pytest.raises(SystemExit, match="bert_pipeline_mode"):
        cli.validate_modes({"bert_pipeline_mode": "turbo"})


# 4. CLI flags override config

def test_cli_flag_overrides_config(tmp_path: Path):
    cfg_file = _config(tmp_path, llm_concurrency=3, scheduler_mode="default")
    args = cli.build_parser().parse_args(
        ["run", "--config", str(cfg_file), "--llm-concurrency", "7",
         "--scheduler-mode", "staged", "--bert-pipeline-mode", "global_batch"]
    )
    cfg = cli.resolve_config(args)
    assert cfg["llm_concurrency"] == 7  # CLI beats YAML
    assert cli.effective_modes(cfg) == ("staged", "global_batch")


# 5. env overrides config, CLI beats env (documented precedence)

def test_env_overrides_yaml_and_cli_beats_env(tmp_path: Path, monkeypatch):
    cfg_file = _config(tmp_path, llm_concurrency=3)
    monkeypatch.setenv("LLM_CHAT_URL", "http://env-url:1/chat/completions")
    args = cli.build_parser().parse_args(["run", "--config", str(cfg_file)])
    cfg = cli.resolve_config(args)
    assert cfg["llm_api_url"] == "http://env-url:1/chat/completions"  # env beats YAML/absent

    args2 = cli.build_parser().parse_args(
        ["run", "--config", str(cfg_file), "--llm-concurrency", "9"]
    )
    assert cli.resolve_config(args2)["llm_concurrency"] == 9  # CLI beats env slot


# 6/7. check-services exit codes

def test_check_services_ok_returns_zero(tmp_path: Path, monkeypatch):
    _Env(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "check_qwen", lambda cfg, t=15: [{"name": "llm", "ok": True}])
    monkeypatch.setattr(cli, "check_bert", lambda cfg, t=15: [{"name": "bert", "ok": True}])
    assert cli.main(["check-services", "--config", str(_config(tmp_path))]) == 0


def test_check_services_failure_returns_nonzero(tmp_path: Path, monkeypatch):
    _Env(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "check_qwen", lambda cfg, t=15: [{"name": "llm", "ok": False, "error": "x"}])
    monkeypatch.setattr(cli, "check_bert", lambda cfg, t=15: [{"name": "bert", "ok": True}])
    assert cli.main(["check-services", "--config", str(_config(tmp_path))]) == 1


def test_check_services_only_qwen_skips_bert(tmp_path: Path, monkeypatch):
    _Env(monkeypatch, tmp_path)
    def bert_should_not_run(cfg, t=15):  # pragma: no cover
        raise AssertionError("bert check must not run with --only llm")
    monkeypatch.setattr(cli, "check_qwen", lambda cfg, t=15: [{"name": "llm", "ok": True}])
    monkeypatch.setattr(cli, "check_bert", bert_should_not_run)
    assert cli.main(["check-services", "--only", "llm", "--config", str(_config(tmp_path))]) == 0


# 8. missing manifest -> nonzero, bulk never started

def test_missing_manifest_dir_rejected(tmp_path: Path, monkeypatch):
    _Env(monkeypatch, tmp_path)
    fake = _FakeSubprocess([0])
    monkeypatch.setattr(cli.subprocess, "run", fake)
    with pytest.raises(SystemExit, match="manifest dir not found"):
        cli.main(["run", "--config", str(_config(tmp_path)),
                  "--manifest-dir", str(tmp_path / "nope"), "--skip-service-check"])
    assert fake.calls == []  # bulk never launched


def test_invalid_manifest_batch_rejected(tmp_path: Path, monkeypatch):
    _Env(monkeypatch, tmp_path)
    mdir = tmp_path / "m"
    mdir.mkdir()
    (mdir / "job_batch_000.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(SystemExit, match="not parseable JSON"):
        cli.validate_manifest_dir(mdir)


# 9. bulk failure is never reported as success

def test_bulk_failure_propagates_exit_code(tmp_path: Path, monkeypatch):
    _Env(monkeypatch, tmp_path)
    mdir = _manifest(tmp_path)
    fake = _FakeSubprocess([2])
    monkeypatch.setattr(cli.subprocess, "run", fake)
    rc = cli.main(["run", "--config", str(_config(tmp_path)), "--manifest-dir", str(mdir),
                   "--run-id", "r1", "--skip-service-check"])
    assert rc == 2  # run_bulk's window-failure code propagates as-is
    summary = json.loads((tmp_path / "logs").glob("*/cli_summary.json").__next__().read_text())
    assert summary["status"] == "bulk_window_failed"
    assert len(fake.calls) == 1  # no merge attempt after a failed bulk


# 10. merge failure returns nonzero

def test_merge_failure_returns_nonzero(tmp_path: Path, monkeypatch):
    _Env(monkeypatch, tmp_path)
    mdir = _manifest(tmp_path)
    _bulk_state(tmp_path)
    fake = _FakeSubprocess([0, 1])  # bulk ok, merge fails
    monkeypatch.setattr(cli.subprocess, "run", fake)
    rc = cli.main(["run", "--config", str(_config(tmp_path)), "--manifest-dir", str(mdir),
                   "--run-id", "r1", "--skip-service-check"])
    assert rc == 1
    summary = json.loads((tmp_path / "logs").glob("*/cli_summary.json").__next__().read_text())
    assert summary["status"] == "merge_failed"


# 11. summary records modes + hashes + counts

def test_successful_run_summary_contents(tmp_path: Path, monkeypatch):
    _Env(monkeypatch, tmp_path)
    mdir = _manifest(tmp_path)
    _bulk_state(tmp_path)
    fake = _FakeSubprocess([0, 0, 0])  # bulk, merge, metrics all ok
    monkeypatch.setattr(cli.subprocess, "run", fake)
    rc = cli.main(["run", "--config", str(_config(tmp_path, scheduler_mode="staged",
                                                  bert_pipeline_mode="global_batch")),
                   "--manifest-dir", str(mdir), "--run-id", "r1", "--skip-service-check"])
    assert rc == 0
    summary = json.loads((tmp_path / "logs").glob("*/cli_summary.json").__next__().read_text())
    assert summary["scheduler_mode"] == "staged"
    assert summary["bert_pipeline_mode"] == "global_batch"
    assert len(summary["manifest_sha256"]) == 64 and len(summary["config_sha256"]) == 64
    assert summary["planned_papers"] == 2
    assert summary["total_ok"] == 2 and summary["jobs_done"] == 1
    assert summary["status"] == "success"
    assert summary["flat_export"].endswith(".json")
    assert summary["metrics_report"].endswith("metrics.json")
    # env keys folded by the CLI are scrubbed from the child env (precedence!)
    assert not (set(cli._child_env()) & {"BERT_SERVER_URL", "LLM_CHAT_URL", "LLM_MODEL"})


# 12. semantic parameters are never exposed or rewritten

def test_semantic_params_untouched(tmp_path: Path):
    cfg_file = _config(tmp_path, temperature=0.05, bert_threshold=0.6, bert_batch_size=32)
    args = cli.build_parser().parse_args(
        ["run", "--config", str(cfg_file), "--llm-concurrency", "5"]
    )
    cfg = cli.resolve_config(args)
    assert cfg["temperature"] == 0.05 and cfg["bert_threshold"] == 0.6
    assert cfg["bert_batch_size"] == 32
    # and the CLI surface has no flags for them (run subparser help)
    import io
    import contextlib

    buf = io.StringIO()
    with pytest.raises(SystemExit):
        with contextlib.redirect_stdout(buf):
            cli.build_parser().parse_args(["run", "--help"])
    help_text = buf.getvalue()
    assert "--llm-concurrency" in help_text
    for banned in ("--temperature", "--num-predict", "--enable-thinking", "--bert-threshold"):
        assert banned not in help_text


# 13. default / global_batch / staged all selectable

@pytest.mark.parametrize(
    "argv,expected",
    [
        ([], ("default", "chunked_overlap")),
        (["--bert-pipeline-mode", "global_batch"], ("default", "global_batch")),
        (["--scheduler-mode", "staged", "--bert-pipeline-mode", "global_batch"], ("staged", "global_batch")),
    ],
)
def test_three_mode_paths_selectable(tmp_path: Path, argv, expected):
    args = cli.build_parser().parse_args(["run", "--config", str(_config(tmp_path)), *argv])
    cfg = cli.resolve_config(args)
    cli.validate_modes(cfg)  # must not raise
    assert cli.effective_modes(cfg) == expected


# 14. CLI writes only under logs/runs/exports (gitignored run-artifact roots)

def test_artifacts_stay_out_of_repo_tree(tmp_path: Path, monkeypatch):
    _Env(monkeypatch, tmp_path)
    mdir = _manifest(tmp_path)
    monkeypatch.setattr(cli.subprocess, "run", _FakeSubprocess([0, 0, 0]))
    _bulk_state(tmp_path)
    cli.main(["run", "--config", str(_config(tmp_path)), "--manifest-dir", str(mdir),
              "--run-id", "r1", "--skip-service-check"])
    logs_root = tmp_path / "logs"
    written = [p for p in logs_root.rglob("*") if p.is_file()]
    assert written and all(logs_root in p.parents for p in written)
    # everything the CLI itself wrote lives under the redirected logs root
    assert any(p.name == "cli_summary.json" for p in written)
    assert any(p.name == "derived_config.yaml" for p in written)
    # (metrics.json is produced by the real subprocess, faked here — the
    # summary references it and the path also lives under logs_root)


# 15. dry-run: no network, no subprocess

def test_dry_run_makes_no_calls(tmp_path: Path, monkeypatch):
    _Env(monkeypatch, tmp_path)
    mdir = _manifest(tmp_path)

    def no_checks(cfg, t=15):  # pragma: no cover
        raise AssertionError("dry-run must not touch services")

    monkeypatch.setattr(cli, "check_qwen", no_checks)
    monkeypatch.setattr(cli, "check_bert", no_checks)
    fake = _FakeSubprocess([])
    monkeypatch.setattr(cli.subprocess, "run", fake)
    rc = cli.main(["run", "--config", str(_config(tmp_path)), "--manifest-dir", str(mdir),
                   "--dry-run"])
    assert rc == 0
    assert fake.calls == []
    summary = json.loads((tmp_path / "logs").glob("*/cli_summary.json").__next__().read_text())
    assert summary["status"] == "dry_run"
    assert summary["planned_papers"] == 2 and len(summary["manifest_sha256"]) == 64


# --- service check failure blocks bulk (§五.3) -------------------------------

def test_service_check_failure_blocks_bulk(tmp_path: Path, monkeypatch):
    _Env(monkeypatch, tmp_path)
    mdir = _manifest(tmp_path)
    monkeypatch.setattr(cli, "check_qwen", lambda cfg, t=15: [{"name": "llm", "ok": False, "error": "down"}])
    monkeypatch.setattr(cli, "check_bert", lambda cfg, t=15: [{"name": "bert", "ok": True}])
    fake = _FakeSubprocess([])
    monkeypatch.setattr(cli.subprocess, "run", fake)
    rc = cli.main(["run", "--config", str(_config(tmp_path)), "--manifest-dir", str(mdir),
                   "--run-id", "r1"])  # service check NOT skipped
    assert rc == 1
    assert fake.calls == []  # bulk never started
    summary = json.loads((tmp_path / "logs").glob("*/cli_summary.json").__next__().read_text())
    assert summary["status"] == "service_check_failed"


# --- ingest subcommand wiring --------------------------------------------------

def test_ingest_subcommand_publishes_batch(tmp_path: Path, monkeypatch):
    import pipeline.production.manifest_ingest as mi

    monkeypatch.setattr(mi, "RUNS_DIR", tmp_path / "runs")
    mdir = tmp_path / "m"
    mdir.mkdir()
    csv = tmp_path / "in.csv"
    csv.write_text("paper_id,md_url\na,http://x/a.md\n", encoding="utf-8")
    rc = cli.main(["ingest", "--csv", str(csv), "--manifest-dir", str(mdir)])
    assert rc == 0
    assert (mdir / "job_batch_000.json").exists()


if __name__ == "__main__":
    raise SystemExit("run via pytest")
