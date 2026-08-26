#!/usr/bin/env python3
"""Deep Research end-to-end smoke.

Two modes:

  --fixture (default, no key, no network)
      Loads samples/patchtst_v3_ledger.json and exercises the skill's own
      pipeline offline: the check gate returns a verdict, and render --final
      emits sections. The fixture is a schema/shape demo, not a gold-standard
      ledger, so check may legitimately flag it — what matters is the engine
      runs cleanly and emits a verdict, not that ok == True.

  --live  (needs AMINER_API_KEY, ~¥0.70)
      Runs the real engine on a question: init → probe → one live
      paper_qa_search_pro call → add the real results to the ledger → minimal
      outline + one claim → gaps → render. Proves REAL AMiner data flows
      through the whole skill pipeline. The scout/induce/iterate loop is
      model-driven and intentionally NOT reproduced here — this is a plumbing
      smoke, not a full research run.

The live mode is the credential-gated step: this script verifies the plumbing
in --fixture mode here and now; run --live with your AMINER_API_KEY to exercise
the real engine.

This smoke tests the skill's OWN pipeline (ledger → check → render) only. It
does not know about, and does not wire up, any external system that might
consume the ledger downstream — adapting the ledger to another system's schema
is that system's job, not the skill's.

Run:
    python smoke_dr.py --fixture
    AMINER_API_KEY=... python smoke_dr.py --live --question "patch tokenisation forecasting"
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
SCRIPTS = SKILL_DIR / "scripts"
EVIDENCE = SCRIPTS / "evidence.py"
AMINER = SCRIPTS / "aminer_open.py"


def _run(cmd: list[str], input_text: str | None = None) -> dict:
    """Run a python script subprocess, return parsed JSON stdout."""
    proc = subprocess.run(
        [sys.executable, *cmd],
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"command failed (exit {proc.returncode}): {' '.join(cmd)}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        # some subcommands print non-JSON status; return raw
        return {"_raw": proc.stdout.strip()}


def fixture_mode() -> int:
    """Exercise the skill's own pipeline offline on the sample ledger.

    check (the anti-fabrication gate) returns a structured verdict and
    render --final emits report sections. The fixture is a minimal shape demo,
    not a gold-standard ledger — check may legitimately flag it; we assert the
    engine *runs cleanly and emits a verdict*, not that ok == True.
    """
    ledger_path = SKILL_DIR / "samples" / "patchtst_v3_ledger.json"
    assert ledger_path.exists(), f"fixture missing: {ledger_path}"

    # check: emits {ok, blocking, warnings, totals, spend}. Exits 1 when ok is
    # False (blocking issues) but still prints the JSON verdict to stdout.
    proc = subprocess.run(
        [sys.executable, str(EVIDENCE), "--state", str(ledger_path), "check"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode in (0, 1), f"check crashed (exit {proc.returncode}): {proc.stderr}"
    check = json.loads(proc.stdout)
    assert "ok" in check and "blocking" in check, f"check verdict malformed: {check}"
    verdict = "PASS" if check["ok"] else "flagged (expected for the minimal fixture)"
    print(f"[fixture] check ran: {verdict}")

    # render --final: the report renderer runs on the fixture.
    render = subprocess.run(
        [sys.executable, str(EVIDENCE), "--state", str(ledger_path), "render", "--final"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert render.returncode == 0, f"render failed (exit {render.returncode}): {render.stderr}"
    sections = [ln for ln in render.stdout.splitlines() if ln.startswith("## ")]
    assert sections, "render produced no sections"
    print(f"[fixture] render --final OK ({len(sections)} sections)")

    print("\n[PASS] fixture smoke — skill pipeline (check→render) runs cleanly "
          "(no key needed).")
    return 0


def live_mode(question: str) -> int:
    if not os.environ.get("AMINER_API_KEY"):
        print("ERROR: --live needs AMINER_API_KEY in env. "
              "Aborting before any paid call.", file=sys.stderr)
        return 1

    work = Path(tempfile.mkdtemp(prefix="dr_live_"))
    # The skill owns no ledger location; the host (here, this smoke script)
    # picks one. evidence.py reads $DR_LEDGER, so set it once for every child.
    os.environ["DR_LEDGER"] = str(work / "evidence-ledger.json")
    print(f"[live] workspace: {work}")
    print(f"[live] ledger: {os.environ['DR_LEDGER']}")
    print(f"[live] question: {question}")
    print(f"[live] cost estimate: ~¥0.70 (1× paper_qa_search_pro; paper_info free)")

    a = lambda *args: _run([str(AMINER), *args])

    # 1. init + probe (run evidence.py with cwd=work so any relative scratch
    #    lands there; the ledger itself is at $DR_LEDGER).
    def e_in_work(args, inp=None):
        proc = subprocess.run([sys.executable, str(EVIDENCE), *args],
                              input=inp, capture_output=True, text=True,
                              encoding="utf-8", cwd=str(work))
        if proc.returncode != 0:
            sys.stderr.write(proc.stderr)
            raise SystemExit(f"evidence.py failed (exit {proc.returncode}): {args}")
        return json.loads(proc.stdout) if proc.stdout.strip() else {}

    e_in_work(["init", "--topic", question])
    e_in_work(["probe", "--axis", "topic", "--via", "paper_qa_search_pro", "--query", question])
    print("[live] init + probe p1 done")

    # 2. minimal outline FIRST (1 section + disagreement child) — `add --section`
    #    validates the section id against the outline, so the outline must exist
    #    before tagging. Scout/induce is model-driven; --allow-unscouted covers
    #    the smoke (we do not induce from results here).
    e_in_work(["outline", "set", "--allow-unscouted", "--json", json.dumps([
        {"title": "Overview", "from_probes": ["p1"], "children": [
            {"title": "Disagreement and open issues", "kind": "disagreement"}]}])])
    print("[live] outline set (1 section + disagreement)")

    # 3. one live paper_qa_search_pro call → pipe straight into the ledger,
    #    tagged to section 1, linked to probe p1.
    params = json.dumps({"query": question, "query_type": "auto", "sort": "balanced"})
    search_doc = a("--api", "paper_qa_search_pro", "--params", params)
    assert search_doc.get("ok"), f"search failed: {search_doc}"
    add_resp = e_in_work(["add", "--aminer", "--probe", "p1", "--section", "1"],
                         inp=json.dumps(search_doc))
    print(f"[live] added search results to ledger: {add_resp}")

    # 4. one claim grounded in the first source (source n=1). Read the ledger
    #    from $DR_LEDGER — that is where evidence.py actually persists it.
    state = json.loads(Path(os.environ["DR_LEDGER"]).read_text("utf-8"))
    first = next((s for s in state["sources"] if not s.get("dropped")), None)
    assert first, "no sources in ledger"
    claim_text = f"{first.get('title', 'This paper')} is relevant to: {question}."
    e_in_work(["claim", "--section", "1", "--supports", "1",
               "--text", claim_text, "--type", "interpretation"])
    print(f"[live] claim c1 grounded in source 1: {first.get('title','')[:50]}…")

    # 5. gaps (coverage is thin by design; check/gaps may flag — that's fine)
    gaps = e_in_work(["gaps"])
    print(f"[live] gaps: {len(gaps.get('unsupported_claims', []))} unsupported, "
          f"{len(gaps.get('sections_below_two_sources', []))} thin sections")

    # 6. render --final (proves the renderer works on real data)
    render = subprocess.run([sys.executable, str(EVIDENCE), "render", "--final"],
                            capture_output=True, text=True, encoding="utf-8", cwd=str(work))
    md = render.stdout
    assert "## " in md, "render produced no sections"
    print(f"[live] render --final OK ({len(md)} chars of markdown)")

    print("\n[PASS] live smoke — REAL AMiner data flowed through the skill pipeline "
          f"(init→probe→add→claim→render). Ledger saved: {os.environ['DR_LEDGER']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Deep Research end-to-end smoke.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fixture", action="store_true", help="no-key fixture mode (default)")
    mode.add_argument("--live", action="store_true", help="real AMiner run (needs AMINER_API_KEY, ~¥0.70)")
    parser.add_argument("--question", default="patch tokenisation long-horizon forecasting",
                        help="research question for --live")
    args = parser.parse_args()
    if args.live:
        return live_mode(args.question)
    return fixture_mode()


if __name__ == "__main__":
    sys.exit(main())
