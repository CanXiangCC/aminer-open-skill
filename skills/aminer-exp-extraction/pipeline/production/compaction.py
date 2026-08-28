"""Per-session incremental prediction-file compaction (TODO-V07-11).

Every ``compaction_every_n_papers`` durable per-paper predictions (config
key; code default 0 = disabled), a full window compaction runs at a
job_batch boundary (writer already joined): the four per-paper artifact
types are merged into an audit window directory, dual-verified
(authoritative wf4_experiment_v1 schema + conservation), the session stable
flat is atomically republished, and ONLY THEN are the per-paper sources
deleted (四类全清, user ruling 2026-08-21: predictions + per-paper monitors
+ partials + history lines).

Layout under ``runs/<session_run_id>/compaction/``::

  state.json                        registered windows (lean: counts + shas)
  flat_experiments.json             stable flat: rows of ALL published windows
  window_NNNN/window.json           member manifest + status (written FIRST)
  window_NNNN/predictions.jsonl     one original prediction per line (audit)
  window_NNNN/flat_experiments.json flat rows of this window
  window_NNNN/monitors.jsonl        one original paper monitor per line
                                    (missing monitor files are counted, not
                                    fatal — PROD_SKIP_PAPER_MONITOR runs)
  window_NNNN/partials/<eid>.jsonl  per-extractor partial payloads
                                    (run_id-guarded: only this session's)
  window_NNNN/history.jsonl         extracted global-history lines

State machine (each step atomic or idempotent; crash windows A-F are
enumerated in tests/test_compaction.py):

  select -> window.json -> ledger backfill -> merged copies (predictions /
  flat / monitors / partials) -> dual verify -> publish stable flat ->
  register in state.json -> delete sources (predictions, monitors,
  run_id-guarded partials, history lines under flock) -> record freed stats

Invariant: no per-paper source is deleted before [window.json + full merged
copies + verified flat + published stable flat + complete ledger rows] all
exist and the window is registered in state.json. Unregistered window dirs
are stale selections and are deleted whole with originals untouched; a
registered window whose deletion was interrupted is re-deleted idempotently
by ``finalize_compaction`` at the next trigger (or via the CLI).

Resume semantics after compaction come from the completion ledger:
``run_paths.prediction_ok`` treats "file deleted + last ledger row ok" as
done and "file deleted + last ledger row error/missing" as retry.
"""

from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pipeline.production import completion_ledger
from pipeline.production import config as config_mod
from pipeline.production import run_paths
from pipeline.production.schema import validate_wf4_experiment

COMPACTION_DIR_NAME = "compaction"
STATE_NAME = "state.json"
STABLE_FLAT_NAME = "flat_experiments.json"
WINDOW_PREFIX = "window_"
WINDOW_JSON_NAME = "window.json"
PREDICTIONS_JSONL = "predictions.jsonl"
MONITORS_JSONL = "monitors.jsonl"
HISTORY_JSONL = "history.jsonl"
GLOBAL_LOCK_NAME = "_compaction.lock"

LogFn = Callable[[str], None]


class CompactionError(RuntimeError):
    """Verification failed — originals must be kept, nothing deleted."""


@dataclass
class SelectedPaper:
    paper_id: str
    job_batch_id: str
    pred_path: Path
    payload: dict[str, Any]
    raw_text: str
    sha256: str
    status: str  # "ok" | "error"
    experiments: int


# --------------------------------------------------------------------------
# paths & small helpers
# --------------------------------------------------------------------------

def compaction_dir(session_run_id: str) -> Path:
    return run_paths.RUNS_DIR / session_run_id / COMPACTION_DIR_NAME


def stable_flat_path(session_run_id: str) -> Path:
    return compaction_dir(session_run_id) / STABLE_FLAT_NAME


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _atomic_write_jsonl(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("".join(line if line.endswith("\n") else line + "\n" for line in lines),
                   encoding="utf-8")
    os.replace(tmp, path)


def _default_log(msg: str) -> None:
    print(msg)


_merge_flat_mod_cache: Any = None


def _merge_flat():
    """Import scripts/merge_flat_experiments.py lazily (single source of
    truth for _flatten_experiment / _verify)."""
    global _merge_flat_mod_cache
    if _merge_flat_mod_cache is None:
        path = Path(__file__).resolve().parents[2] / "scripts" / "merge_flat_experiments.py"
        spec = importlib.util.spec_from_file_location("_compaction_merge_flat", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _merge_flat_mod_cache = mod
    return _merge_flat_mod_cache


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------

def load_state(session_run_id: str) -> dict[str, Any]:
    path = compaction_dir(session_run_id) / STATE_NAME
    if not path.exists():
        return {"windows": []}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — corrupt state: treat as empty (windows re-derivable)
        return {"windows": []}
    if not isinstance(state, dict) or not isinstance(state.get("windows"), list):
        return {"windows": []}
    return state


def _save_state(session_run_id: str, state: dict[str, Any]) -> None:
    state["updated_at"] = _utc_now()
    _atomic_write_json(compaction_dir(session_run_id) / STATE_NAME, state)


def registered_paper_count(session_run_id: str) -> int:
    return sum(int(w.get("papers_count", 0)) for w in load_state(session_run_id)["windows"])


def on_disk_prediction_count(session_run_id: str) -> int:
    n = 0
    for _jb, _p in iter_on_disk_predictions(session_run_id):
        n += 1
    return n


def iter_on_disk_predictions(session_run_id: str):
    """Yield (job_batch_id, prediction_path) for every per-paper file on disk."""
    session_dir = run_paths.RUNS_DIR / session_run_id
    if not session_dir.is_dir():
        return
    for jb_dir in sorted(session_dir.iterdir()):
        if not jb_dir.is_dir() or not run_paths.is_job_batch_dir(jb_dir.name):
            continue
        pred_dir = jb_dir / "predictions"
        if not pred_dir.is_dir():
            continue
        for pf in sorted(pred_dir.glob("*.json")):
            if pf.name.endswith(".tmp"):
                continue
            yield jb_dir.name, pf


# --------------------------------------------------------------------------
# selection
# --------------------------------------------------------------------------

def select_papers(session_run_id: str, log: LogFn | None = None) -> list[SelectedPaper]:
    """All readable per-paper predictions on disk (registered windows' files
    were already deleted; a reappeared file is a post-compaction rerun and is
    legitimately re-selectable — stable-flat publish removes its old rows)."""
    papers: list[SelectedPaper] = []
    skipped_corrupt = 0
    for jb, pf in iter_on_disk_predictions(session_run_id):
        raw = pf.read_text(encoding="utf-8")
        try:
            payload = json.loads(raw)
        except Exception:  # noqa: BLE001
            skipped_corrupt += 1
            continue
        if not isinstance(payload, dict):
            skipped_corrupt += 1
            continue
        exps = payload.get("experiments")
        papers.append(
            SelectedPaper(
                paper_id=str(payload.get("paper_id") or pf.stem),
                job_batch_id=jb,
                pred_path=pf,
                payload=payload,
                raw_text=raw,
                sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                status="error" if payload.get("error") else "ok",
                experiments=len(exps) if isinstance(exps, list) else 0,
            )
        )
    if skipped_corrupt and log:
        log(f"[compaction] WARNING: {skipped_corrupt} corrupt prediction file(s) left on disk")
    papers.sort(key=lambda p: (p.job_batch_id, p.paper_id))
    return papers


def _next_window_id(session_run_id: str) -> str:
    cdir = compaction_dir(session_run_id)
    max_n = 0
    if cdir.is_dir():
        for d in cdir.iterdir():
            if d.is_dir() and d.name.startswith(WINDOW_PREFIX):
                try:
                    max_n = max(max_n, int(d.name[len(WINDOW_PREFIX):]))
                except ValueError:
                    continue
    for w in load_state(session_run_id)["windows"]:
        wid = w.get("window_id", "")
        if wid.startswith(WINDOW_PREFIX):
            try:
                max_n = max(max_n, int(wid[len(WINDOW_PREFIX):]))
            except ValueError:
                continue
    return f"{WINDOW_PREFIX}{max_n + 1:04d}"


# --------------------------------------------------------------------------
# window steps
# --------------------------------------------------------------------------

def _reconcile_ledger(session_run_id: str, papers: list[SelectedPaper], log: LogFn) -> int:
    """Backfill ledger rows for files whose last row is missing or describes
    different bytes (legacy runs without a ledger; crash gap between
    os.replace and the append)."""
    last_row: dict[str, dict[str, Any]] = {}
    for row in completion_ledger.read_rows(session_run_id):
        last_row[row.get("paper_id", "")] = row
    backfilled = 0
    for p in papers:
        row = last_row.get(p.paper_id)
        if row is not None and row.get("prediction_sha256") == p.sha256:
            continue
        completion_ledger.append_row(
            session_run_id,
            p.job_batch_id,
            f"{session_run_id}/{p.job_batch_id}",
            p.paper_id,
            p.status,
            error_class=p.payload.get("error"),
            experiments=p.experiments,
            prediction_payload=p.raw_text,
            workflow_version=p.payload.get("workflow_version"),
        )
        backfilled += 1
    if backfilled and log:
        log(f"[compaction] ledger backfill: {backfilled} row(s)")
    return backfilled


def _copy_predictions_and_flat(
    window_dir: Path, papers: list[SelectedPaper], entry: dict[str, Any]
) -> None:
    mf = _merge_flat()
    lines = [json.dumps(p.payload, ensure_ascii=False) + "\n" for p in papers]
    _atomic_write_jsonl(window_dir / PREDICTIONS_JSONL, lines)

    flat: list[dict[str, Any]] = []
    for p in papers:
        for exp in p.payload.get("experiments") or []:
            if isinstance(exp, dict):
                flat.append(mf._flatten_experiment(p.payload, exp))
    flat_path = window_dir / STABLE_FLAT_NAME
    _atomic_write_json(flat_path, flat)
    entry["flat_rows"] = len(flat)
    entry["flat_sha256"] = hashlib.sha256(flat_path.read_bytes()).hexdigest()


def _copy_monitors(
    session_run_id: str, window_dir: Path, papers: list[SelectedPaper], entry: dict[str, Any]
) -> None:
    lines: list[str] = []
    missing = 0
    for p in papers:
        mon = (
            run_paths.RUNS_DIR
            / session_run_id
            / p.job_batch_id
            / "monitors"
            / f"{p.paper_id}_monitor.json"
        )
        if mon.exists():
            lines.append(mon.read_text(encoding="utf-8").strip() + "\n")
        else:
            missing += 1
    _atomic_write_jsonl(window_dir / MONITORS_JSONL, lines)
    entry["monitors_copied"] = len(lines)
    entry["monitors_missing"] = missing


def _copy_partials(
    session_run_id: str, window_dir: Path, papers: list[SelectedPaper], entry: dict[str, Any]
) -> None:
    """Merge this session's partial payloads (run_id guard: the partials dir
    is GLOBAL and last-write-wins; another session's payload for the same
    paper_id must not enter this window nor be deleted)."""
    by_pid = {p.paper_id: p for p in papers}
    copied = 0
    partials_root = config_mod.PARTIALS_DIR
    if partials_root.is_dir():
        for eid_dir in sorted(partials_root.iterdir()):
            if not eid_dir.is_dir():
                continue
            lines: list[str] = []
            for pid in by_pid:
                pf = eid_dir / f"{pid}.json"
                if not pf.exists():
                    continue
                try:
                    payload = json.loads(pf.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                run_id = str(payload.get("run_id") or "")
                if run_id.split("/", 1)[0] != session_run_id:
                    continue
                lines.append(json.dumps(payload, ensure_ascii=False) + "\n")
                copied += 1
            if lines:
                _atomic_write_jsonl(window_dir / "partials" / f"{eid_dir.name}.jsonl", lines)
    entry["partials_copied"] = copied


def _verify_window(
    session_run_id: str, window_dir: Path, papers: list[SelectedPaper]
) -> dict[str, Any]:
    """Dual verification. Raises CompactionError on any problem; callers
    keep every original file in that case."""
    problems: list[str] = []
    mf = _merge_flat()

    # -- merged predictions audit copy ------------------------------------
    pred_lines = (window_dir / PREDICTIONS_JSONL).read_text(encoding="utf-8").splitlines()
    if len(pred_lines) != len(papers):
        problems.append(f"predictions.jsonl lines {len(pred_lines)} != selected {len(papers)}")
    parsed: list[dict[str, Any]] = []
    for i, line in enumerate(pred_lines):
        try:
            parsed.append(json.loads(line))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"predictions.jsonl[{i}] not json: {exc}")
    ids = [str(d.get("paper_id")) for d in parsed]
    if len(set(ids)) != len(ids):
        problems.append("predictions.jsonl has duplicate paper_id")
    if set(ids) != {p.paper_id for p in papers}:
        problems.append("predictions.jsonl paper_id set != selection")

    # -- authoritative schema on every experiment --------------------------
    for d in parsed:
        for j, exp in enumerate(d.get("experiments") or []):
            for err in validate_wf4_experiment(exp):
                problems.append(f"{d.get('paper_id')} experiments[{j}]: {err}")

    # -- flat conservation --------------------------------------------------
    flat_path = window_dir / STABLE_FLAT_NAME
    flat = json.loads(flat_path.read_text(encoding="utf-8"))
    expected_rows = sum(p.experiments for p in papers)
    if len(flat) != expected_rows:
        problems.append(f"flat rows {len(flat)} != sum(experiments) {expected_rows}")
    keys = {(r.get("paper_id"), r.get("experiment_name")) for r in flat}
    if len(keys) != len(flat):
        problems.append("flat has duplicate (paper_id, experiment_name)")
    if {r.get("paper_id") for r in flat} - {p.paper_id for p in papers}:
        problems.append("flat contains papers outside the window")
    try:
        mf._verify(flat_path)  # structural asserts (key order/legacy keys)
    except AssertionError as exc:
        problems.append(f"flat _verify: {exc}")

    # -- monitors within bounds ---------------------------------------------
    mon_lines = (window_dir / MONITORS_JSONL).read_text(encoding="utf-8").splitlines()
    if len(mon_lines) > len(papers):
        problems.append(f"monitors.jsonl lines {len(mon_lines)} > papers {len(papers)}")

    # -- ledger complete (post-backfill) -------------------------------------
    idx = completion_ledger.last_status_index(session_run_id)
    for p in papers:
        if p.paper_id not in idx:
            problems.append(f"ledger row missing for {p.paper_id}")
        elif idx[p.paper_id] != p.status:
            problems.append(
                f"ledger status {idx[p.paper_id]} != file status {p.status} for {p.paper_id}"
            )

    if problems:
        raise CompactionError("; ".join(problems[:10]) + (f" (+{len(problems) - 10} more)"
                                                          if len(problems) > 10 else ""))
    return {"papers": len(papers), "flat_rows": len(flat)}


def _publish_stable_flat(
    session_run_id: str, window_dir: Path, papers: list[SelectedPaper], log: LogFn
) -> str:
    """Stable flat = (old stable − window papers' rows) ∪ window rows.
    Idempotent under a re-published window (converges to the same set)."""
    stable = stable_flat_path(session_run_id)
    window_pids = {p.paper_id for p in papers}
    old_rows: list[dict[str, Any]] = []
    if stable.exists():
        try:
            old_rows = json.loads(stable.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            old_rows = []
    kept = [r for r in old_rows if r.get("paper_id") not in window_pids]
    new_rows = kept + json.loads((window_dir / STABLE_FLAT_NAME).read_text(encoding="utf-8"))
    _atomic_write_json(stable, new_rows)
    sha = hashlib.sha256(stable.read_bytes()).hexdigest()
    log(f"[compaction] stable flat: {len(new_rows)} rows, sha256={sha[:16]}…")
    return sha


def _register_window(session_run_id: str, entry: dict[str, Any]) -> None:
    state = load_state(session_run_id)
    state["windows"] = [w for w in state["windows"] if w.get("window_id") != entry["window_id"]]
    lean = {
        k: entry[k]
        for k in (
            "window_id",
            "papers_count",
            "flat_rows",
            "flat_sha256",
            "stable_flat_sha256",
            "created_at",
        )
        if k in entry
    }
    lean["status"] = "published"
    state["windows"].append(lean)
    _save_state(session_run_id, state)


def _delete_sources(
    session_run_id: str, window_dir: Path, manifest: list[dict[str, Any]], log: LogFn
) -> dict[str, int]:
    """Idempotent deletion. ``manifest`` entries carry paper_id + job_batch_id
    (+ sha) exactly as recorded in window.json; sources still present are
    re-derived from it, so an interrupted deletion resumes cleanly."""
    freed = {
        "files": 0,
        "bytes": 0,
        "predictions": 0,
        "monitors": 0,
        "partials": 0,
        "history_rows": 0,
    }
    pid_set = {m["paper_id"] for m in manifest}

    for m in manifest:
        pred = (
            run_paths.RUNS_DIR
            / session_run_id
            / m["job_batch_id"]
            / "predictions"
            / f"{m['paper_id']}.json"
        )
        if pred.exists():
            freed["bytes"] += pred.stat().st_size
            freed["files"] += 1
            freed["predictions"] += 1
            pred.unlink()
        mon = (
            run_paths.RUNS_DIR
            / session_run_id
            / m["job_batch_id"]
            / "monitors"
            / f"{m['paper_id']}_monitor.json"
        )
        if mon.exists():
            freed["bytes"] += mon.stat().st_size
            freed["files"] += 1
            freed["monitors"] += 1
            mon.unlink()

    # partials: global dir; unlink only files whose payload run_id belongs to
    # this session (guard re-checked at deletion, not trusted from copy time).
    partials_root = config_mod.PARTIALS_DIR
    if partials_root.is_dir():
        for eid_dir in sorted(partials_root.iterdir()):
            if not eid_dir.is_dir():
                continue
            for pid in pid_set:
                pf = eid_dir / f"{pid}.json"
                if not pf.exists():
                    continue
                try:
                    payload = json.loads(pf.read_text(encoding="utf-8"))
                    owns = str(payload.get("run_id") or "").split("/", 1)[0] == session_run_id
                except Exception:  # noqa: BLE001
                    owns = False
                if not owns:
                    continue
                freed["bytes"] += pf.stat().st_size
                freed["files"] += 1
                freed["partials"] += 1
                pf.unlink()

    # history: extract this window's lines, then rewrite the global log
    # without them — both under an exclusive flock, tmp + os.replace.
    history_path = config_mod.RUN_HISTORY_PATH
    if history_path.exists():
        history_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = history_path.parent / (history_path.name + ".lock")
        with open(lock_path, "w", encoding="utf-8") as lock_fh:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
            try:
                lines = history_path.read_text(encoding="utf-8").splitlines()
                matching: list[str] = []
                rest: list[str] = []
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    keep = True
                    try:
                        d = json.loads(line)
                        if (
                            str(d.get("run_id") or "").split("/", 1)[0] == session_run_id
                            and d.get("paper_id") in pid_set
                        ):
                            keep = False
                    except Exception:  # noqa: BLE001
                        pass
                    if keep:
                        rest.append(line)
                    else:
                        matching.append(line)
                if matching:
                    win_hist = window_dir / HISTORY_JSONL
                    if not win_hist.exists():
                        _atomic_write_jsonl(win_hist, matching)
                    _atomic_write_jsonl(history_path, rest)
                    freed["history_rows"] += len(matching)
            finally:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)

    if freed["files"]:
        log(
            f"[compaction] freed: {freed['files']} files "
            f"({freed['bytes'] / 1024:.1f} KiB) — preds={freed['predictions']} "
            f"monitors={freed['monitors']} partials={freed['partials']} "
            f"history_rows={freed['history_rows']}"
        )
    return freed


# --------------------------------------------------------------------------
# finalize (crash recovery) & main entry points
# --------------------------------------------------------------------------

def finalize_compaction(session_run_id: str, log: LogFn | None = None) -> dict[str, Any]:
    """Idempotent recovery: delete stale unregistered window dirs (their
    originals were never touched); complete deletions for registered windows
    whose ``sources_deleted`` marker is missing."""
    log = log or _default_log
    cdir = compaction_dir(session_run_id)
    if not cdir.is_dir():
        return {"status": "noop", "reason": "no compaction dir"}
    state = load_state(session_run_id)
    registered = {w.get("window_id"): w for w in state["windows"]}
    changed = False

    for d in sorted(cdir.iterdir()):
        if not d.is_dir() or not d.name.startswith(WINDOW_PREFIX):
            continue
        if d.name not in registered:
            log(f"[compaction] finalize: removing stale unregistered {d.name} (originals kept)")
            shutil.rmtree(d, ignore_errors=True)
            continue
        wjson_path = d / WINDOW_JSON_NAME
        if not wjson_path.exists():
            # registered but window.json lost — keep the dir (registered
            # windows are authoritative copies); nothing safe to do.
            log(f"[compaction] finalize: {d.name} registered but window.json missing; skip")
            continue
        wjson = json.loads(wjson_path.read_text(encoding="utf-8"))
        if wjson.get("status") == "sources_deleted":
            continue
        log(f"[compaction] finalize: completing deletion for {d.name}")
        freed = _delete_sources(session_run_id, d, wjson.get("papers") or [], log)
        wjson["status"] = "sources_deleted"
        wjson["freed"] = freed
        wjson["deleted_at"] = _utc_now()
        _atomic_write_json(wjson_path, wjson)
        for w in state["windows"]:
            if w.get("window_id") == d.name:
                w["status"] = "sources_deleted"
                w["freed"] = freed
                changed = True
    if changed:
        _save_state(session_run_id, state)
    return {"status": "finalized"}


def compact_session(
    session_run_id: str, *, log: LogFn | None = None
) -> dict[str, Any]:
    """One full window compaction (global flock serializes sessions)."""
    log = log or _default_log
    run_paths.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    lock_fh = open(run_paths.RUNS_DIR / GLOBAL_LOCK_NAME, "w", encoding="utf-8")
    try:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            finalize_compaction(session_run_id, log)
            papers = select_papers(session_run_id, log)
            if not papers:
                return {"status": "noop", "reason": "no eligible predictions"}

            window_id = _next_window_id(session_run_id)
            window_dir = compaction_dir(session_run_id) / window_id
            window_dir.mkdir(parents=True, exist_ok=True)

            batches = sorted({p.job_batch_id for p in papers})
            entry: dict[str, Any] = {
                "window_id": window_id,
                "session_run_id": session_run_id,
                "job_batches": batches,
                "papers_count": len(papers),
                "papers": [
                    {
                        "paper_id": p.paper_id,
                        "job_batch_id": p.job_batch_id,
                        "prediction_sha256": p.sha256,
                        "status": p.status,
                        "experiments": p.experiments,
                    }
                    for p in papers
                ],
                "created_at": _utc_now(),
                "status": "selected",
            }
            # window.json FIRST — before any copy, the marker that makes this
            # dir a "selection in progress" (deleted whole if never registered).
            _atomic_write_json(window_dir / WINDOW_JSON_NAME, entry)

            _reconcile_ledger(session_run_id, papers, log)
            _copy_predictions_and_flat(window_dir, papers, entry)
            _copy_monitors(session_run_id, window_dir, papers, entry)
            _copy_partials(session_run_id, window_dir, papers, entry)

            try:
                _verify_window(session_run_id, window_dir, papers)
            except CompactionError as exc:
                log(f"[compaction] VERIFY FAIL ({window_id}): {exc} — originals kept, "
                    f"window dir left for inspection")
                raise

            entry["stable_flat_sha256"] = _publish_stable_flat(
                session_run_id, window_dir, papers, log
            )
            entry["status"] = "published"
            _atomic_write_json(window_dir / WINDOW_JSON_NAME, entry)
            _register_window(session_run_id, entry)

            manifest = [
                {"paper_id": p.paper_id, "job_batch_id": p.job_batch_id} for p in papers
            ]
            freed = _delete_sources(session_run_id, window_dir, manifest, log)
            entry["status"] = "sources_deleted"
            entry["freed"] = freed
            entry["deleted_at"] = _utc_now()
            _atomic_write_json(window_dir / WINDOW_JSON_NAME, entry)
            state = load_state(session_run_id)
            for w in state["windows"]:
                if w.get("window_id") == window_id:
                    w["status"] = "sources_deleted"
                    w["freed"] = freed
            _save_state(session_run_id, state)

            log(
                f"[compaction] {window_id} DONE: papers={len(papers)} batches={len(batches)} "
                f"flat_rows={entry['flat_rows']} stable_sha={entry['stable_flat_sha256'][:16]}…"
            )
            return {
                "status": "compacted",
                "window_id": window_id,
                "papers": len(papers),
                "job_batches": batches,
                "flat_rows": entry["flat_rows"],
                "stable_flat_sha256": entry["stable_flat_sha256"],
                "freed": freed,
            }
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
    finally:
        lock_fh.close()


def maybe_compact(
    session_run_id: str,
    every_n: int,
    *,
    log: LogFn | None = None,
    force: bool = False,
) -> dict[str, Any] | None:
    """Batch-boundary hook: compact when [on-disk + already-compacted]
    reaches ``every_n`` (0 = disabled). ``force`` compacts regardless of the
    threshold (manual CLI). Returns None when no compaction ran."""
    log = log or _default_log
    if every_n <= 0 and not force:
        return None
    if compaction_dir(session_run_id).is_dir():
        finalize_compaction(session_run_id, log)
    if not force:
        total = on_disk_prediction_count(session_run_id) + registered_paper_count(session_run_id)
        if total < every_n:
            return None
    if on_disk_prediction_count(session_run_id) == 0:
        return None
    try:
        return compact_session(session_run_id, log=log)
    except CompactionError as exc:
        log(f"[compaction] ABORTED (verification failed, nothing deleted): {exc}")
        return {"status": "error", "reason": str(exc)}
