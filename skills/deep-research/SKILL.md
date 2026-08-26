---
name: deep-research
version: 1.0.0
author: AMiner
contact: report@aminer.cn
description: >
  Produce a cited, hierarchically numbered research report from AMiner Open Platform data plus the host's native web tools — and, in the same run, an Evidence Ledger: the self-describing, versioned JSON (sources, claims, figures, probes) behind the report — reusable as-is by anything downstream.
  Activate for literature reviews, research landscapes, entity investigations, trend comparisons, industry / market surveys, or any request that needs a sourced report rather than a lookup.
  You (the host model) drive a fixed research loop — scout the question, induce the outline from what came back, retrieve per section, record every source in an evidence ledger, find the gap, iterate — no claim reaches the report without a ledger source.
  AMiner routing and prices live in scripts/aminer_open.py; web evidence comes from the host's own WebSearch and WebFetch. Free-first; estimated AMiner cost of CNY 10+ needs explicit confirmation, CNY 20 hard stop. No extra LLM service is called.
  Route elsewhere for: a single lookup (use aminer-free-academic), a survey bibliography of hundreds of papers without a report (use aminer-deep-search), or personalized recommendations (use aminer-daily-paper).
metadata:
  {
    "openclaw":
      {
        "requires": {
          "bins": ["python3"],
          "env": ["AMINER_API_KEY"]
        },
        "primaryEnv": "AMINER_API_KEY"
      }
  }
---

# Deep Research

You are the researcher, not a wrapper around a search box. Scout the question first, let the report's structure follow from what retrieval actually returned, keep every source in a ledger, and write a report where each claim points back to something you retrieved.

## Language Routing

- Use `SKILL.zh.md` when the user mainly writes in Chinese or explicitly requests Chinese output.
- Use this `SKILL.md` for all other requests.
- Keep code, commands, ledger field names, and API names in English in either workflow; only the prose switches language.

## Deep Research produces two artifacts (v6 §1.2/§7.6)

Deep Research is **not** just an end feature (a report for humans). One DR run
produces two artifacts off the same flow — a cited report, and an **Evidence
Ledger**: the structured JSON the engine itself used to gate every claim
(sources, claims, figures, datums, probes, outline, spend). The ledger is
self-describing and reusable; what any downstream system does with it is that
system's business, not the skill's. The skill does not know or name a consumer:

```text
Deep Research Engine (scripts/evidence.py + scripts/aminer_open.py)
   ↓ one run
   ├── Evidence Ledger      (scripts/evidence.py state JSON — self-describing, reusable)
   └── Report + appendices  (evidence.py render --final / --appendix)

self-check, no external consumer: evidence.py check · evaluation/evaluate.py
```

The ledger is the engine's own state — it is **not hand-written**, it falls out
of the research loop (§7.6). It is a self-describing, versioned JSON: anyone
downstream (a context store, a RAG index, a review pipeline, or nothing at all)
may read it as-is. The skill produces it and stops — it does not export, convert,
or adapt it to any other system's schema; that specialization is the external
system's job, not the skill's.

### Submodules (v6 §7.13)

- `scripts/evidence.py` — **engine + evidence-ledger + report-renderer**: the
  research loop, the machine-consumable ledger state (`{version, topic, probes,
  outline, sources, claims, figures, datums, spend}`), `analyze()` self-check, and `render`.
- `scripts/aminer_open.py` — AMiner Open Platform retrieval (stdlib urllib, 26
  endpoints, price catalog, cost document). DR's own spend-tracking path (§7.14).
- `scripts/chartrender.py` — renders one registered figure to a PNG. Host-called
  (a sibling to `aminer_open.py`, never spawned by `evidence.py`, which stays a
  pure offline ledger): deterministic matplotlib templates (`bar` / `hbar` / `line`
  / `pie` / `heatmap`) or a host-written B script run in a best-effort sandbox (no
  network, locked cwd, 30 s timeout, forbidden-token scan, data on stdin); a B
  failure falls back to the matching template. The figure's numbers still come from
  the ledger, so `check`'s data↔source gate holds either way.
- `evaluation/evaluate.py` — quality report from `analyze()` (§7.13 5th submodule,
  §7.15 internal validation).
- `samples/patchtst_v3_ledger.json` — v3-schema sample ledger (PatchTST).
- `references/research-loop.md` — the actual procedure (read it at task start).

## Scope

- Use for: literature reviews, research landscapes, scholar / institution / venue / patent investigations, trend and comparison questions, industry / market surveys, anything needing citations.
- Route elsewhere for: a single lookup (`aminer-free-academic`), a survey bibliography of hundreds of papers (`aminer-deep-search`), personalized recommendations (`aminer-daily-paper`).

## Pre-flight

1. Answer in the user's language unless they ask otherwise.
2. Ask at most two questions, and only when different answers would change the research scope. Otherwise state your assumptions and start.
3. The AMiner key is in the shell environment as `AMINER_API_KEY` — the host exports
   it (e.g. `export AMINER_API_KEY=…` or a sourced `.env`) before invoking the skill,
   and `aminer_open.py` reads it from there and nowhere else. If the key is
   missing or invalid the script returns an auth error — then stop and point the
   user to the [AMiner Console](https://open.aminer.cn/open/board?tab=control).
   Never request, print, log, or save the token.

## Tools

| Need | Tool |
| --- | --- |
| Papers, scholars, institutions, venues, patents | `scripts/aminer_open.py` — allowlisted AMiner endpoints with prices |
| Anything the web knows and AMiner does not: project pages, docs, standards, leaderboards, releases, news | the host's native `WebSearch` and `WebFetch` |
| Probes, outline, sources, claims, datums (captured data points), coverage gaps, citation numbering, spend | `scripts/evidence.py` — offline ledger |
| A registered figure rendered to a PNG — charts that visualize ledger-verified numbers, or a structural timeline of dated events | `scripts/chartrender.py` — matplotlib templates (`bar` / `hbar` / `line` / `pie` / `heatmap` / `timeline`) or a sandboxed B script; record the result back with `evidence.py figure mark-rendered` |

Rules:

- Every AMiner request goes through `scripts/aminer_open.py`. Never hand-roll a request, substitute another search API, or call an endpoint outside `references/api-reference.md`.
- Web evidence uses the host's own tools; do not bundle or shell out to a scraper. Prefer `WebFetch` on the actual page over trusting a search snippet. If native web tools are unavailable, continue AMiner-only and say so in the report.
- Nothing enters the report unless it is in the ledger, and no section exists that `evidence.py render` did not print.

Read `references/api-reference.md` before choosing AMiner calls. It marks `paper_qa_search_pro` as the default topic search, explains why `query_type: "auto"` is the default and when to drop to `topic`, lists the fields that steer a drifting query, and marks which endpoints are free.

## Method

Follow `references/research-loop.md`. It is the actual procedure — read it at the start of the task, not after you have already spent money.

Shape of it:

- **Round 0 — scout, then induce.** Frame the question, `evidence.py init` (pass `--genre industry` for an industry / market survey — the genre is set at `init` and drives the figures-expected `check`), run 3–4 `paper_qa_search_pro` probes in `query_type: "auto"` (~¥2.80) — separated by object and structured filter, not by rewording — triage with free `paper_info`, buy `paper_detail` for the keepers, then induce 2–4 numbered top-level sections from what came back, each with 2–4 subsections, exactly one of which is the `disagreement` subsection. Do not invent section titles before retrieval.
- **Each round** — retrieve per section (AMiner + web) → pipe results in untagged with `--probe <id>`, then tag only the keepers with `--section <id>` and `drop` the noise → read (free `paper_info` triage before paid `paper_detail`) → `evidence.py gaps` → decide whether to continue.
- **Wrap-up** — `evidence.py check` must exit 0, then `evidence.py render --final` gives the ledger view (numbering, claims per section, stable ledger source numbers) — **write the report as a draft in prose from the ledger's claims, citing sources as `[@n]` placeholders, never pasting `render --final` into the body** (no `c1` ids, no `_来源：` lines, no `_（分歧）_` tags, no raw `冲突：` bullets), ending with a references heading that holds one `{{references}}` line. `render --renumber --draft <path> --out <path>` then swaps the placeholders for dense ascending citation numbers, fills the references slot with a cited-only bibliography, and writes a citation-map sidecar next to the delivered report — an `[@n]` naming an unknown or dropped source is a hard error. Finally `render --appendix --out auto --citation-map <sidecar>` writes the appendix tables (D carries the report↔ledger number map) and returns the one line the report quotes. If the report has figures, the `figure add` → `chartrender.py` → `figure mark-rendered` chain must have run first — `render --final` emits a `_[FIGURE fN] …_` placeholder per registered figure, which you replace with the image embed when assembling the draft. For an industry report, figures and a player-comparison table are expected, not optional.

Quick start:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" init --topic "RAG evaluation"
# industry / market survey:
# python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" init --topic "中国大模型行业调研" --genre industry

python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" probe --axis topic --via paper_qa_search_pro \
  --query "retrieval augmented generation evaluation"
python3 "${CLAUDE_SKILL_DIR}/scripts/aminer_open.py" --api paper_qa_search_pro \
  --params '{"query":"retrieval augmented generation evaluation","query_type":"auto","year_from":2023,"sort":"balanced"}' \
  | python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" add --aminer --probe p1
python3 "${CLAUDE_SKILL_DIR}/scripts/aminer_open.py" --api paper_info --params '{"ids":["<id>","<id>"]}' \
  | python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" add --aminer
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" drop --source 7 9 --reason "off topic"
python3 "${CLAUDE_SKILL_DIR}/scripts/aminer_open.py" --api paper_detail --params '{"id":"<id>"}' \
  | python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" add --aminer

python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" outline set --json '[
  {"title":"Evaluation methods","from_probes":["p1"],"children":[
    {"title":"LLM-judge metrics"},
    {"title":"Disagreement: judge validity","kind":"disagreement"}]}]'

python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" add --section 1.1 --json '[{"kind":"paper","id":"<id>","title":"..."}]'
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" claim --section 1.1 --supports 1 4 \
  --text "LLM-judge metrics dominate reported RAG evaluation since 2023"
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" gaps
```

## Invoking the scripts — and where the ledger lives

Invoke scripts via `${CLAUDE_SKILL_DIR}` so the script path does not depend on
cwd. The skill **owns no ledger location** — the path is the host's choice. When
nothing else has chosen, default the run's workspace to a per-run directory
`outputs/<topic-slug>-<YYYYMMDD-HHMM>/` under the current project (ledger at its
root, figures under `figures/`; one directory per run — runs never overwrite
each other), resolve it to an absolute path, and tell the user where the ledger
lives — a default the host applies, not one the engine assumes. Set
it once, `export DR_LEDGER=<workspace>/evidence-ledger.json`, and every
`evidence.py` / `evaluate.py` call reads it from `$DR_LEDGER` (or take `--state`
/ `--ledger` explicitly). The skill assumes no `knowledge/`, `.zscience/`, or
any directory — persistence and scratch are the host's job; the ledger is the
skill's output (and an optional input), not a file the skill owns. Never write
the ledger under `${CLAUDE_SKILL_DIR}` (the skill tree is read-only source).

The ledger *is* the skill's structured output — a self-describing, versioned
JSON. The skill produces it and stops: it does not export, convert, or adapt it
to any other system's schema. Anything that wants the research in another shape
(a context store, a RAG index, a brief) reads the ledger and does that itself,
outside the skill.

```bash
# the ledger view — the content reference to draft against (numbers are ledger n)
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" render --final
# the delivered report: [@n] placeholders become ascending [N], the references
# slot becomes a cited-only bibliography, and a citation-map sidecar is written
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" render --renumber \
  --draft <draft.md> --out <report.md>
# the appendices (retrieval log / cost / data & methods / citation map) next to the ledger
python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" render --appendix --out auto \
  --citation-map <report-citation-map.json>
# the skill's own quality report on the ledger (§7.13)
python3 "${CLAUDE_SKILL_DIR}/evaluation/evaluate.py" --ledger "$DR_LEDGER"
```

## Cost control

- Free first: free discovery and disambiguation endpoints before anything paid; free `paper_info` before paid `paper_detail`.
- **Route by query shape.** `paper_qa_search_pro` at ¥0.70 is the default for topic and multi-filter search, and what Round 0 scout uses. Drop to `paper_search_pro` at ¥0.01 whenever the query is already a structured filter (author, org, venue, or a single controlled keyword with citation or year ordering).
- **Send the query in `query_type: "auto"` — query mode.** ~5 s vs ~0.4 s for non-LLM modes, well inside the 30 s timeout (no automatic retry on a paid endpoint), better recall. Drop to `topic` only for literal term matching, and pin the concept with `all_terms` when you do. Separate probes by object and filter, never by rewording.
- **Read what you cite.** Search results carry no abstract; a free `paper_info` slice is ~190 chars; `paper_detail` is ¥0.01 for the full abstract + keywords. `check` warns with `cited_sources_without_detail` when a claim leans on a paper you never read properly.
- **Check `warnings` and `total` on every result.** `aminer_open.py` hoists them out of the response; a warning means the query that ran is not the query you sent.
- Estimate the whole planned chain with `--dry-run` or `--batch` before paid calls. `add --aminer` accumulates actual spend into the ledger; a paid call whose hits you discarded still needs `evidence.py spend`.
- A full scholar profile is about ¥6.00. At ¥10.00 show the call plan and wait for confirmation, then pass `--confirm-high-cost`. At ¥20.00 accumulated, `check` blocks — stop and hand over partial results.

## Budgets

2–4 top-level sections · 2–4 subsections each, one being the disagreement subsection · 3–4 probes (~¥2.80) · 4 rounds · ≤2 paid `paper_qa_search_pro` calls and ≤3 web calls per round, ¥0.01 `paper_search_pro` unlimited · ≤8 candidates per top-level section · ≤50 paid detail calls per task · ≤5 `paper_relation` expansions · ≤6 figures per report (≤2 per section; optional for Genre A, ≥1 expected for Genre B; no cost — rendered locally by `chartrender.py`, `timeline` template runs on dated events when numeric data is thin) · ¥10.00 confirmation threshold · ¥20.00 hard stop. A typical run lands near ¥4–6, and searches are ~92% of it — ration searches, not abstracts.

## Failure handling

- **Empty search**: reformulate once on a *different axis* — a different topic phrase or structured filter, not a reworded synonym — then report the gap instead of a third attempt.
- **Ambiguous entity**: show the top candidates and ask the user to pick. Never buy details for every candidate.
- **API error**: report the public endpoint name and an actionable message; never surface headers or credentials.
- **Starving section**: merge it into a neighbour rather than buying searches for symmetry. A thin subsection gets written thin and labelled thin.
- **Thin evidence**: `check` fails, so narrow the claims and ship a clearly limited report. Never fill a gap from memory.
- **No web tools**: continue with AMiner and record the limitation in the report's Limitations section.

## Output

Write the final report per `references/report-format.md`. Two genres, picked from the task framing: an **academic review** (default — literature reviews, research landscapes, entity investigations) and an **industry report** (industry / market surveys: "行业调研", "市场格局", "竞争格局"). For either genre the report is **prose you write from the ledger's claims — not `render --final` pasted into the body.** `render --final` is the ledger view: take from one run the section / subsection numbering, the claim set per section in order, and the stable ledger source numbers; write each subsection as flowing prose carrying its `[@n]` citation placeholders, and use tables when comparing several entities. `render --renumber` turns the draft into the delivered report — ascending `[N]` numbers by first appearance, a cited-only bibliography, and a citation-map sidecar. Do not paste the ledger scaffold — claim ids (`c1`), source-pool lines (`_来源：`), the `_（分歧）_` / `_（解读）_` tags, or raw `冲突：` bullets — into the report; those are ledger internals. The appendices are **not** part of the report: `render --appendix --out auto` writes Appendix A (retrieval log), B (calls and cost) and C (data and methods) to a file next to the ledger, and you append to Appendix C the few method facts the ledger cannot know. Probe ids, retrieval axes, API names, prices and screening counts live in that file, never in the report. For an **industry report**, the skeleton is the consulting shape (executive summary / market size / player landscape with a comparison table / competitive dynamics / technology & patents / supply chain & compute / policy / outlook), retrieval is web-first (market data, funding, chips, policy) with AMiner as the tech / IP channel, and at least one figure (market share / player / timeline) plus a player-comparison table are expected, not optional. `render` emits its headings in the language of the ledger's topic; copy the reference heading and entries as printed rather than translating them.

## Rules

- **Nothing in the report that is not in the ledger.** No section exists that `render` did not print; no claim appears without ledger sources.
- **Two senses of "figure".** A lowercase *figure* (as in `claims_with_unsourced_numbers`) means a number quoted in a claim — it must appear in a cited source. A registered *Figure* (`figure add`, id `f1…`) means a chart rendered to a PNG — its `data` is checked by the same number-provenance rule (`figures_unsupported_numbers`). Both draw from ledger numbers; neither may show a number the ledger does not vouch for.
- **Adversarial verification is mandatory.** Every top-level section has a `disagreement` subsection; every key claim is checked against a source that could contradict it.
- **No fabricated citations.** Every citation must be a real entity returned by `aminer_open.py` or a page actually fetched via `WebFetch`.
- **File output for large results.** When search results exceed 20 items or raw API output exceeds 5000 characters, write intermediate results to a scratch path the host chooses (e.g. `$DR_WORKDIR/scratch/`) instead of keeping them in context. The skill assumes no `.zscience/` or other scratch directory. Stdout only short status: `"Found N results, saved to <path>"`.
