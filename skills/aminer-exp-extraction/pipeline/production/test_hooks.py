"""v0.7 Phase 3 deterministic kill-point hook (TODO-V07-04) — env-gated, no-op by default.

``barrier(stage)`` is called at six stage boundaries of the production
pipeline (prep / bert_flush / llm / post / write / replace). Without the
``WF4_BARRIER_STAGE`` environment variable set it costs one ``environ`` lookup
and returns — production behavior is bit-for-bit unchanged.

Test drivers (scripts/phase3_kill_restart.py) use:

- ``WF4_BARRIER_STAGE``   stage name to arm (one stage per process)
- ``WF4_BARRIER_N``       1-based item index that trips the barrier
- ``WF4_BARRIER_SIGNAL``  path touched when the barrier trips (driver waits on it)
- ``WF4_BARRIER_RELEASE`` path whose existence releases the barrier
- ``WF4_BARRIER_TIMEOUT`` max seconds to hold (default 600; then continue)

Blocking scenarios (prep/post/write/replace) kill the process group while it
is deterministically parked at the boundary; in-flight HTTP scenarios
(bert_flush/llm) release the barrier and kill after a short delay, landing
inside the HTTP window (documented as heuristic in the Phase 3 report).
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

_STATE: dict = {"counts": {}, "lock": threading.Lock()}


def reset_counts() -> None:
    """Test helper: forget per-process trip counts."""
    with _STATE["lock"]:
        _STATE["counts"] = {}


def barrier(stage: str) -> None:
    armed = os.environ.get("WF4_BARRIER_STAGE")
    if armed != stage:
        return
    with _STATE["lock"]:
        n = _STATE["counts"].get(stage, 0) + 1
        _STATE["counts"][stage] = n
    try:
        want = int(os.environ.get("WF4_BARRIER_N", "0"))
    except ValueError:
        return
    if n < want:
        return
    signal_path = os.environ.get("WF4_BARRIER_SIGNAL")
    if signal_path:
        try:
            Path(signal_path).write_text(f"{stage}:{n}\n", encoding="utf-8")
        except OSError:
            pass
    release = Path(os.environ.get("WF4_BARRIER_RELEASE") or "/__wf4_barrier_no_release__")
    try:
        timeout = float(os.environ.get("WF4_BARRIER_TIMEOUT", "600"))
    except ValueError:
        timeout = 600.0
    deadline = time.monotonic() + timeout
    while not release.exists():
        if time.monotonic() >= deadline:
            return
        time.sleep(0.05)
