#!/usr/bin/env python3
"""TODO-V07-13 parity gate: BERT-stage input parity across runs (fixed corpus).

Why not byte-diff final predictions: the LLM server is not run-to-run
deterministic (continuous-batching float reduction order), so predictions of
two SAME-config runs already differ in wording (verified 2026-08-21 on
phase7abc c-r3 vs b3-r1: 158/158 common papers differ). Prediction bytes are
therefore informational only.

The actual parity risk of bs32->bs64 / dual-lane is the BERT stage flipping
kept-sentences at the threshold edge. The LLM prompt is a deterministic
function of the kept-sentence set (frozen template + fixed paper text), and
per-paper ``prompt_chars`` is recorded in run monitors BEFORE the LLM call.
Same prompt_chars <=> same kept-set (a flip adds/removes a whole sentence).
Validated: two same-config champion rounds match 161/161 papers exactly.

Gate: every paper present in BOTH runs must have equal prompt_chars.
Papers present in only one run (per-run error variance, 0-3 unknown-class
errors) are reported but do not fail the gate.
Also prints (non-gating) prediction structural stats from flat exports:
experiment-count agreement and byte-equality rates on common papers.

Exit 0 = parity OK; exit 2 = prompt_chars mismatches; exit 1 = missing artifacts.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
RUNS = PROJ / "pipeline_output" / "production" / "runs"
EXPORTS = PROJ / "pipeline_output" / "production" / "exports"
EXTRACTOR = "llm.wf4_dev20_v2_wash_datasets"


def load_prompt_chars(run_id: str) -> dict[str, int]:
    """paper_id -> prompt_chars from per-paper monitors; missing -> -1.

    TODO-V07-11: compacted windows keep their monitors as
    ``compaction/window_*/monitors.jsonl`` (one original monitor per line);
    both layouts are read, on-disk per-paper files taking no precedence
    over window copies (a paper exists in exactly one of them).
    """
    out: dict[str, int] = {}
    mon_files = glob.glob(str(RUNS / run_id / "job_batch_*" / "monitors" / "*_monitor.json"))
    mon_files += glob.glob(str(RUNS / run_id / "compaction" / "window_*" / "monitors.jsonl"))
    if not mon_files:
        raise FileNotFoundError(f"no monitors under {RUNS / run_id}")

    def _absorb(d: dict) -> None:
        pid = d.get("paper_id")
        if not pid:
            return
        for e in d.get("extractors") or []:
            if e.get("extractor_id") == EXTRACTOR:
                md = e.get("metadata") or {}
                out[pid] = int(md.get("prompt_chars") or -1)

    for mon in mon_files:
        if mon.endswith(".jsonl"):
            for line in Path(mon).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    _absorb(json.loads(line))
        else:
            _absorb(json.loads(Path(mon).read_text(encoding="utf-8")))
    return out


def load_experiment_counts(run_id: str) -> dict[str, int] | None:
    """paper_id -> experiment count from flat export; None if export absent."""
    path = EXPORTS / f"ai2000_{run_id}_flat_merged.json"
    if not path.exists():
        return None
    rows = json.loads(path.read_text(encoding="utf-8"))
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        counts[r["paper_id"]] += 1
    return dict(counts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_a")
    ap.add_argument("run_b")
    ap.add_argument("--show", type=int, default=5, help="max mismatches to print")
    args = ap.parse_args()

    try:
        a = load_prompt_chars(args.run_a)
        b = load_prompt_chars(args.run_b)
    except FileNotFoundError as e:
        print(f"PARITY-ERROR missing artifacts: {e}", file=sys.stderr)
        return 1

    common = sorted(set(a) & set(b))
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    mism = [(p, a[p], b[p]) for p in common if a[p] != b[p]]

    print(f"parity {args.run_a} vs {args.run_b}: "
          f"common_papers={len(common)} only_a={len(only_a)} only_b={len(only_b)} "
          f"prompt_chars_mismatch={len(mism)}")
    if only_a:
        print(f"  papers only in A (error variance, informational; first 5): {only_a[:5]}")
    if only_b:
        print(f"  papers only in B (error variance, informational; first 5): {only_b[:5]}")
    for pid, x, y in mism[: args.show]:
        print(f"  MISMATCH {pid}: prompt_chars {x} vs {y} (delta {y - x})")

    ca, cb = load_experiment_counts(args.run_a), load_experiment_counts(args.run_b)
    if ca is not None and cb is not None:
        cexp = sorted(set(ca) & set(cb))
        same = sum(1 for p in cexp if ca[p] == cb[p])
        print(f"  [info] experiment-count agreement on exported papers: "
              f"{same}/{len(cexp)} (LLM variance expected; not gating)")

    if len(common) == 0:
        print("PARITY-FAIL no common papers")
        return 2
    if mism:
        print("PARITY-FAIL (BERT-stage input drift: kept-sentence set changed)")
        return 2
    print("PARITY-OK (per-paper prompt_chars identical => BERT kept-sets identical)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
