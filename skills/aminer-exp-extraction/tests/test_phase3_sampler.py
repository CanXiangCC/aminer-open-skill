"""Tests for phase3_longrun_monitor /proc sampling (TODO: sampler hardening).

Locks down the process-tree RSS aggregation so the past mis-sampling bugs
cannot recur:
- VmRSS/PPid/Threads must come from /proc/<pid>/status key-value lines only
  (never /proc/<pid>/stat field indexes, which shift when comm contains
  spaces or parens);
- tree sums must include exactly the root plus its descendants;
- unreadable/partial status files must be skipped, not crash;
- a missing root must report gone (None).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
SCRIPT = PROJ / "scripts" / "phase3_longrun_monitor.py"

spec = importlib.util.spec_from_file_location("phase3_longrun_monitor", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


STATUS_TMPL = """Name:\t{name}
State:\tS (sleeping)
PPid:\t{ppid}
Threads:\t{threads}
VmPeak:\t 1000 kB
VmSize:\t 1000 kB
VmRSS:\t{rss} kB
"""


def _mkproc(root: Path, pid: int, ppid: int, rss_kb: int, threads: int = 1,
            name: str | None = None) -> None:
    d = root / str(pid)
    d.mkdir(parents=True, exist_ok=True)
    # comm with spaces+parens: the trap that broke /proc/stat parsing
    (d / "status").write_text(
        STATUS_TMPL.format(name=name or f"weird (name) {pid}", ppid=ppid,
                           rss=rss_kb, threads=threads),
        encoding="utf-8",
    )


def _fake_proc(tmp_path: Path) -> Path:
    """root(100) -> a(101) -> b(102); unrelated(999); broken(103 under root)."""
    root = tmp_path / "proc"
    _mkproc(root, 100, 1, rss_kb=1000, threads=3)
    _mkproc(root, 101, 100, rss_kb=2000, threads=2)
    _mkproc(root, 102, 101, rss_kb=4000, threads=1)
    _mkproc(root, 999, 1, rss_kb=99999, threads=9)  # unrelated: must be excluded
    broken = root / "103"  # descendant of root but unreadable status
    broken.mkdir()
    return root


class TestProcTreeStats:
    def test_sums_only_root_subtree(self, tmp_path):
        root = _fake_proc(tmp_path)
        st = mod._proc_tree_stats(100, proc_root=root)
        assert st == {"rss_kb": 1000 + 2000 + 4000, "threads": 3 + 2 + 1, "pids": 3}

    def test_subtree_from_mid_node(self, tmp_path):
        root = _fake_proc(tmp_path)
        st = mod._proc_tree_stats(101, proc_root=root)
        assert st["rss_kb"] == 2000 + 4000
        assert st["pids"] == 2

    def test_root_gone_returns_none(self, tmp_path):
        root = _fake_proc(tmp_path)
        assert mod._proc_tree_stats(424242, proc_root=root) is None
        assert mod._proc_tree_stats(424242, proc_root=tmp_path / "nope") is None

    def test_broken_status_skipped_not_crash(self, tmp_path):
        root = _fake_proc(tmp_path)
        # 103 has an empty status file; it must be excluded from sums silently
        st = mod._proc_tree_stats(100, proc_root=root)
        assert st["pids"] == 3
        assert st["rss_kb"] == 7000

    def test_missing_vmrss_excluded(self, tmp_path):
        root = tmp_path / "proc"
        _mkproc(root, 100, 1, rss_kb=500)
        d = root / "101"
        d.mkdir()
        (d / "status").write_text("Name:\tx\nPPid:\t100\nThreads:\t1\n", encoding="utf-8")
        st = mod._proc_tree_stats(100, proc_root=root)
        assert st["rss_kb"] == 500
        assert st["pids"] == 1

    def test_non_pid_dirs_ignored(self, tmp_path):
        root = _fake_proc(tmp_path)
        (root / "cpuinfo").write_text("x", encoding="utf-8")
        (root / "self").mkdir()
        st = mod._proc_tree_stats(100, proc_root=root)
        assert st["pids"] == 3

    def test_single_proc_stats_unchanged_shape(self, tmp_path):
        root = _fake_proc(tmp_path)
        st = mod._proc_stats(100, proc_root=root)
        assert st == {"rss_kb": 1000, "threads": 3}


class TestLiveProc:
    """Sanity anchors against the real /proc of trivial processes."""

    def test_sleep_tree_is_small(self):
        p = subprocess.Popen(["sleep", "5"])
        try:
            time.sleep(0.3)
            st = mod._proc_tree_stats(p.pid)
            assert st is not None
            assert st["pids"] == 1
            # a bare sleep is a few MB; GB-scale values mean a parsing bug
            assert st["rss_kb"] < 50_000, st
        finally:
            p.kill()
            p.wait()

    def test_tree_includes_children(self):
        py = subprocess.Popen(
            [sys.executable, "-c",
             "import subprocess,sys,time;"
             "subprocess.Popen([sys.executable,'-c','import time;time.sleep(5)']);"
             "time.sleep(5)"]
        )
        try:
            time.sleep(1.0)
            st = mod._proc_tree_stats(py.pid)
            assert st is not None
            assert st["pids"] >= 2
            single = mod._proc_stats(py.pid)
            assert st["rss_kb"] > single["rss_kb"]
            # two python processes: tens of MB, never GB
            assert st["rss_kb"] < 500_000, st
        finally:
            py.kill()
            py.wait()

    def test_tree_matches_manual_status_sum(self):
        py = subprocess.Popen(
            [sys.executable, "-c",
             "import subprocess,sys,time;"
             "subprocess.Popen([sys.executable,'-c','import time;time.sleep(5)']);"
             "time.sleep(5)"]
        )
        try:
            time.sleep(1.0)
            st = mod._proc_tree_stats(py.pid)
            manual = 0
            for pid_dir in Path("/proc").iterdir():
                if not pid_dir.name.isdigit():
                    continue
                status = (pid_dir / "status").read_text(encoding="utf-8")
                fields = {}
                for line in status.splitlines():
                    if line.startswith(("VmRSS:", "PPid:")):
                        k, v = line.split(":", 1)
                        fields[k] = int(v.split()[0])
                if int(pid_dir.name) == py.pid or fields.get("PPid") == py.pid:
                    manual += fields.get("VmRSS", 0)
            assert st["rss_kb"] == manual
        finally:
            py.kill()
            py.wait()
