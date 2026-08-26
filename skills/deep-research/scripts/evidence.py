#!/usr/bin/env python3
"""Evidence ledger for aminer-deep-research. No network access.

The ledger is the single source of truth for what the report may cite, and for
the shape the report takes. Round 0 registers the scout probes that were
actually run; the numbered outline is induced from what they returned; every
source and claim hangs off a script-assigned section id; and `check` fails the
run when a claim has no source or a top-level section has no evidence.

    python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" init --topic "..."
    python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" probe --axis keyword --via paper_search_pro --query "..."
    python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" outline set --json '[{"title":"...","from_probes":["p1"],
        "children":[{"title":"..."},{"title":"...","kind":"disagreement"}]}]'
    python3 "${CLAUDE_SKILL_DIR}/scripts/aminer_open.py" --api paper_qa_search_pro --params '{...}' \
        | python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" add --aminer --section 1.1 --probe p1
    python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" claim --text "..." --supports 1 3 --section 1.1
    python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" gaps
    python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" check
    python3 "${CLAUDE_SKILL_DIR}/scripts/evidence.py" render
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any


# The ledger path is the host's choice, never the skill's. Resolve in order:
# --state <path>, then the $DR_LEDGER env var; neither set is an error. The
# skill owns no directory — it does not know "knowledge/", ".zscience/", or
# any location. Persistence and scratch are the host's job; the ledger is the
# skill's output (and an optional input), not a file the skill owns. Never
# write the ledger under ${CLAUDE_SKILL_DIR} (the skill tree is read-only).
DEFAULT_STATE = os.environ.get("DR_LEDGER")  # None unless the host sets it
STATE_VERSION = 2

KINDS = ("paper", "scholar", "patent", "venue", "org", "project", "web")
CLAIM_TYPES = ("observed", "interpretation")
SECTION_KINDS = ("topic", "disagreement")
# Chart types the A template path can render. A figure whose chart_type is not
# here must carry a B script (code_path); the template path refuses it.
FIGURE_TYPES = ("bar", "hbar", "line", "pie", "heatmap", "timeline")
# Quantitative chart shapes — they carry real numbers a report verifies. The
# structural `timeline` runs on dated events and is the fallback when the web
# returned no numbers. A Genre B report ships at least one quantitative figure;
# `figures_industry_quantitative_expected` warns when it ships none.
QUANTITATIVE_TYPES = ("bar", "hbar", "line", "pie", "heatmap")
FIGURE_BUDGET_PER_REPORT = 6
FIGURE_BUDGET_PER_SECTION = 2
PROBE_AXES = ("topic", "question", "keyword", "title", "abstract", "author", "org", "venue", "time", "web", "patent", "other")

# Stop and hand over partial results rather than spending past this on one task.
HARD_LIMIT_CNY = 20.0

# A probe whose hits are mostly already in the ledger asked the same question
# twice. Rewording is not a second search; change the retrieval axis instead.
LOW_YIELD_MIN_RETURNED = 5
LOW_YIELD_RATIO = 3

# A different failure from low yield: the probe returned plenty of *new* work
# that turned out to be off-object, so triage threw most of it away. A run that
# only measured duplication scored an 80%-discarded probe as healthy, and the
# subfield it was meant to cover ended up with no evidence at all.
DRIFT_MIN_RETURNED = 5
DRIFT_RATIO = 0.5

# Numbers are where a citation goes wrong invisibly: the claim reads well, the
# figure came from a different source than the one cited. Single- and two-digit
# values are too common to check, so only decimals and 3-plus-digit integers are
# compared against the stored text of the sources a claim leans on.
NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)?")
DIGIT_RUN_PATTERN = re.compile(r"(?<=\d)[\s,](?=\d)")
# "400 万" is 4 million in the source it came from: a myriad unit means the
# figure was rescaled on its way into the prose, so a literal match can never
# succeed and flagging it is pure noise.
MYRIAD_UNITS = "万亿兆"

# Kinds absent from this map have no public AMiner page; they stay link-free.
URL_TEMPLATES = {
    "paper": "https://www.aminer.cn/pub/{id}",
    "scholar": "https://www.aminer.cn/profile/{id}",
    "patent": "https://www.aminer.cn/patent/{id}",
    "venue": "https://www.aminer.cn/open/journal/detail/{id}",
}

TITLE_KEYS = ("title", "title_zh", "name", "name_zh", "titles")
ID_KEYS = ("paper_id", "id", "patent_id", "person_id", "venue_id", "org_id")


class LedgerError(ValueError):
    """User-facing ledger error."""


# --------------------------------------------------------------------------- state


def _empty_state() -> dict[str, Any]:
    return {
        "version": STATE_VERSION,
        "topic": "",
        "genre": "academic",
        "probes": [],
        "outline": [],
        "sources": [],
        "claims": [],
        "figures": [],
        "datums": [],
        "spend": {},
    }


def _upgrade_v1(state: dict[str, Any]) -> dict[str, Any]:
    """Lift a v1 ledger (flat angles) onto the v2 outline so a run in progress
    does not lose sources that were already paid for."""
    angles = [a for a in (state.pop("angles", None) or []) if isinstance(a, str)]
    section_of = {angle: str(i) for i, angle in enumerate(angles, start=1)}
    state["outline"] = [
        {
            "id": str(i),
            "title": angle,
            "from_probes": [],
            "children": [{
                "id": f"{i}.1",
                "title": "Disagreement and counter-evidence",
                "kind": "disagreement",
                "from_probes": [],
            }],
        }
        for i, angle in enumerate(angles, start=1)
    ]
    for source in state.get("sources", []):
        source["sections"] = [section_of[a] for a in source.pop("angles", None) or [] if a in section_of]
        source.setdefault("probes", [])
    for claim in state.get("claims", []):
        claim["section"] = section_of.get(claim.pop("angle", "") or "", "")
    state.setdefault("probes", [])
    state.setdefault("spend", {})
    state["migrated_from"] = {"version": 1, "angles": angles}
    state["unscouted"] = True
    state["version"] = STATE_VERSION
    return state


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LedgerError(f"State file {path} is not valid JSON: {exc.msg}") from None
    if not isinstance(state, dict):
        raise LedgerError(f"State file {path} must contain a JSON object")
    version = state.get("version", 1)
    if isinstance(version, int) and version > STATE_VERSION:
        raise LedgerError(
            f"State file {path} is version {version}; this script understands {STATE_VERSION}"
        )
    if version < STATE_VERSION or "angles" in state:
        state = _upgrade_v1(state)
    base = _empty_state()
    base.update(state)
    return base


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- probes


def _probe_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {probe["id"]: probe for probe in state["probes"]}


def _add_probe(state: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    query = args.query.strip()
    if not query:
        raise LedgerError("A probe needs a non-empty --query")
    probe = {
        "id": f"p{len(state['probes']) + 1}",
        "axis": args.axis,
        "query": query,
        "via": args.via.strip(),
        "returned": 0,
        "new": 0,
        "dup": 0,
    }
    if args.note:
        probe["note"] = args.note.strip()
    state["probes"].append(probe)
    return probe


# --------------------------------------------------------------------------- outline


def _assign_outline(nodes: Any, probe_ids: set[str], require_probes: bool) -> list[dict[str, Any]]:
    """Build the outline from a titles-only tree. Ids are ours, not the caller's,
    so the model cannot cite a section that the report skeleton will not print."""
    if not isinstance(nodes, list) or not nodes:
        raise LedgerError("Outline needs a non-empty JSON array of top-level sections")
    outline: list[dict[str, Any]] = []
    for i, node in enumerate(nodes, start=1):
        if not isinstance(node, dict):
            raise LedgerError("Each outline section must be a JSON object with a title")
        title = str(node.get("title") or "").strip()
        if not title:
            raise LedgerError(f"Outline section {i} needs a title")
        from_probes = [str(p) for p in (node.get("from_probes") or [])]
        unknown = [p for p in from_probes if p not in probe_ids]
        if unknown:
            raise LedgerError(f"Section {i} cites unknown probe(s): {', '.join(unknown)}")
        if require_probes and not from_probes:
            raise LedgerError(
                f"Section {i} '{title}' needs from_probes — run the Round 0 scout and record it "
                f"with `evidence.py probe` first, or pass --allow-unscouted and disclose it in the report"
            )
        children: list[dict[str, Any]] = []
        seen: set[str] = set()
        for j, kid in enumerate(node.get("children") or [], start=1):
            if not isinstance(kid, dict):
                raise LedgerError(f"Subsections of section {i} must be JSON objects")
            kid_title = str(kid.get("title") or "").strip()
            if not kid_title:
                raise LedgerError(f"Subsection {i}.{j} needs a title")
            if kid_title.lower() in seen:
                raise LedgerError(f"Duplicate subsection title '{kid_title}' under section {i}")
            seen.add(kid_title.lower())
            kind = str(kid.get("kind") or "topic")
            if kind not in SECTION_KINDS:
                raise LedgerError(f"Subsection kind must be one of: {', '.join(SECTION_KINDS)}")
            if kid.get("children"):
                raise LedgerError(f"Outline depth is 2; subsection {i}.{j} cannot have children")
            kid_probes = [str(p) for p in (kid.get("from_probes") or [])]
            unknown = [p for p in kid_probes if p not in probe_ids]
            if unknown:
                raise LedgerError(f"Subsection {i}.{j} cites unknown probe(s): {', '.join(unknown)}")
            children.append({
                "id": f"{i}.{j}",
                "title": kid_title,
                "kind": kind,
                "from_probes": kid_probes,
            })
        if not any(kid["kind"] == "disagreement" for kid in children):
            raise LedgerError(
                f"Section {i} '{title}' needs one subsection with \"kind\":\"disagreement\" — "
                f"the counter-evidence subsection every top-level section carries"
            )
        outline.append({"id": str(i), "title": title, "from_probes": from_probes, "children": children})
    return outline


def _section_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for top in state["outline"]:
        index[top["id"]] = top
        for kid in top["children"]:
            index[kid["id"]] = kid
    return index


def _require_sections(state: dict[str, Any], ids: list[str]) -> list[str]:
    index = _section_index(state)
    if not index:
        raise LedgerError("No outline yet — run the Round 0 scout, then `evidence.py outline set`")
    unknown = [i for i in ids if i not in index]
    if unknown:
        raise LedgerError(
            f"Unknown section id(s): {', '.join(unknown)}. Valid ids: {', '.join(index)}"
        )
    return list(dict.fromkeys(ids))


def _find_top(state: dict[str, Any], section_id: str) -> dict[str, Any]:
    for top in state["outline"]:
        if top["id"] == section_id:
            return top
    raise LedgerError(
        f"Unknown top-level section '{section_id}'. "
        f"Valid ids: {', '.join(t['id'] for t in state['outline']) or 'none'}"
    )


def _next_sub_id(top: dict[str, Any]) -> str:
    used = [int(kid["id"].split(".")[1]) for kid in top["children"]]
    return f"{top['id']}.{max(used, default=0) + 1}"


# --------------------------------------------------------------------------- sources


def _normalize_url(url: str) -> str:
    text = url.strip().lower()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    if text.startswith("www."):
        text = text[4:]
    return text.rstrip("/")


def _source_key(kind: str, ident: str, url: str) -> str:
    if ident:
        return f"{kind}:{ident.strip()}"
    if url:
        return f"url:{_normalize_url(url)}"
    raise LedgerError("A source needs an id or a url")


def _coerce_source(
    raw: Any,
    default_via: str,
    default_sections: list[str],
    default_probe: str | None,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise LedgerError("Each source must be a JSON object")
    kind = str(raw.get("kind") or "paper").strip()
    if kind not in KINDS:
        raise LedgerError(f"Unsupported source kind '{kind}'; use one of: {', '.join(KINDS)}")
    ident = str(raw.get("id") or "").strip()
    title = str(raw.get("title") or "").strip()
    url = str(raw.get("url") or "").strip()
    if not url and ident and kind in URL_TEMPLATES:
        url = URL_TEMPLATES[kind].format(id=ident)
    if not title:
        raise LedgerError("Each source needs a title")
    if not url and not ident:
        raise LedgerError(f"Source '{title}' needs a url or an id")
    own = [str(s) for s in (raw.get("sections") or [])]
    probe = str(raw.get("probe") or default_probe or "").strip()
    source = {
        "key": _source_key(kind, ident, url),
        "kind": kind,
        "id": ident,
        "title": title,
        "url": url,
        "via": str(raw.get("via") or default_via or "").strip(),
        "sections": list(dict.fromkeys(own or default_sections)),
        "probes": [probe] if probe else [],
        "depth": str(raw.get("depth") or "search"),
    }
    for optional in ("year", "venue", "authors", "assignee", "note", "abstract", "abstract_slice", "keywords"):
        if raw.get(optional) not in (None, "", []):
            source[optional] = raw[optional]
    return source


def _add_sources(
    state: dict[str, Any],
    items: list[Any],
    via: str,
    sections: list[str],
    probe: str | None,
) -> dict[str, Any]:
    known = {item["key"]: item for item in state["sources"]}
    added: list[int] = []
    duplicates: list[int] = []
    for raw in items:
        candidate = _coerce_source(raw, via, sections, probe)
        existing = known.get(candidate["key"])
        if existing:
            for field in ("sections", "probes"):
                for tag in candidate[field]:
                    if tag not in existing[field]:
                        existing[field].append(tag)
            if DEPTH_RANK.get(candidate.get("depth", "search"), 0) > DEPTH_RANK.get(existing.get("depth", "search"), 0):
                existing["depth"] = candidate["depth"]
            # A `paper_detail` hit on a source already found by search arrives here
            # as a duplicate. Its abstract is the thing that was paid for, so
            # merge the richer text in rather than discarding it. `note` is the
            # only content a web source has, so it merges the same way.
            for field in ("authors", "assignee", "abstract", "abstract_slice", "keywords", "year", "venue", "note"):
                incoming = candidate.get(field)
                if not incoming:
                    continue
                current = existing.get(field)
                if not current or len(str(incoming)) > len(str(current)):
                    existing[field] = incoming
            # Retrieving it again on purpose overrides an earlier triage call.
            if existing.pop("dropped", None) is not None:
                existing.pop("drop_reason", None)
            duplicates.append(existing["n"])
            continue
        candidate["n"] = len(state["sources"]) + 1
        state["sources"].append(candidate)
        known[candidate["key"]] = candidate
        added.append(candidate["n"])
    return {"added": added, "duplicates": duplicates, "total": len(state["sources"])}


def _drop_sources(state: dict[str, Any], numbers: list[int], reason: str) -> dict[str, Any]:
    """Retire scout noise without disturbing citation numbers.

    A broad probe buys relevance and noise in the same call. Dropped sources
    keep their slot — renumbering would silently repoint every citation — but
    leave the reference list and every coverage count.
    """
    by_number = {source["n"]: source for source in state["sources"]}
    unknown = [n for n in numbers if n not in by_number]
    if unknown:
        raise LedgerError(f"Unknown source number(s): {', '.join(str(n) for n in unknown)}")
    cited: dict[int, list[str]] = {}
    for claim in state["claims"]:
        for n in claim.get("supports", []):
            cited.setdefault(n, []).append(claim["id"])
    blocked = [n for n in numbers if n in cited]
    if blocked:
        detail = "; ".join(f"{n} supports {', '.join(cited[n])}" for n in blocked)
        raise LedgerError(f"Cannot drop a source a claim relies on: {detail}")
    dropped: list[int] = []
    for n in dict.fromkeys(numbers):
        source = by_number[n]
        if source.get("dropped"):
            continue
        source["dropped"] = True
        if reason:
            source["drop_reason"] = reason
        dropped.append(n)
    return {"dropped": dropped, "remaining": len(_live_sources(state))}


def _live_sources(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [source for source in state["sources"] if not source.get("dropped")]


def _untag_sources(state: dict[str, Any], numbers: list[int], section: str) -> dict[str, Any]:
    """Remove a section tag that a bulk `add --section` applied too broadly."""
    by_number = {source["n"]: source for source in state["sources"]}
    unknown = [n for n in numbers if n not in by_number]
    if unknown:
        raise LedgerError(f"Unknown source number(s): {', '.join(str(n) for n in unknown)}")
    _require_sections(state, [section])
    changed: list[int] = []
    for n in dict.fromkeys(numbers):
        source = by_number[n]
        if section in source.get("sections", []):
            source["sections"].remove(section)
            changed.append(n)
    return {"untagged": changed, "section": section}


def _retract_claims(state: dict[str, Any], ids: list[str], reason: str) -> dict[str, Any]:
    """Withdraw a mis-recorded claim. The id stays reserved so nothing renumbers.

    A wrong citation is the one error `check` cannot see, so correcting it has to
    be cheap: retract, then record the claim again.
    """
    by_id = {claim["id"]: claim for claim in state["claims"]}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise LedgerError(
            f"Unknown claim id(s): {', '.join(unknown)}. "
            f"Valid ids: {', '.join(by_id) or 'none'}"
        )
    retracted: list[str] = []
    for cid in dict.fromkeys(ids):
        claim = by_id[cid]
        if claim.get("retracted"):
            continue
        claim["retracted"] = True
        if reason:
            claim["retract_reason"] = reason
        retracted.append(cid)
    return {"retracted": retracted, "remaining": len(_live_claims(state))}


def _live_claims(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [claim for claim in state["claims"] if not claim.get("retracted")]


# --------------------------------------------------------------------------- spend


def _record_spend(state: dict[str, Any], api: str, unit_cny: float, calls: int = 1) -> None:
    if calls <= 0 or unit_cny < 0:
        return
    entry = state["spend"].setdefault(api, {"calls": 0, "unit_cny": unit_cny, "subtotal": 0.0})
    entry["calls"] += calls
    entry["unit_cny"] = unit_cny
    entry["subtotal"] = round(entry["calls"] * unit_cny, 4)


def _spend_from_aminer(state: dict[str, Any], payload: Any) -> None:
    """A paid call is a paid call whether or not its hits were worth keeping."""
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return
    for result in results:
        if not isinstance(result, dict) or result.get("dry_run"):
            continue
        api = str(result.get("api") or "").strip()
        cost = result.get("unit_cost_cny")
        if api and isinstance(cost, (int, float)) and cost > 0:
            _record_spend(state, api, float(cost))


def _spend_total(state: dict[str, Any]) -> float:
    return round(sum(entry["subtotal"] for entry in state["spend"].values()), 4)


def _paid_calls_without_hits(payload: Any, kind_override: str | None) -> list[dict[str, Any]]:
    """Paid calls that returned nothing usable.

    A query the API does not understand still answers 200 and still bills. Left
    unreported it reads as 'this angle has no literature' when it actually means
    'that query shape was wrong' — so surface it at the moment it happens.
    """
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return []
    empty: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict) or not result.get("ok") or result.get("dry_run"):
            continue
        cost = result.get("unit_cost_cny")
        if not isinstance(cost, (int, float)) or cost <= 0:
            continue
        if not extract_from_aminer({"results": [result]}, kind_override):
            data = result.get("data")
            empty.append({
                "api": str(result.get("api") or ""),
                "cost_cny": float(cost),
                "msg": str(data.get("msg") or "") if isinstance(data, dict) else "",
            })
    return empty


# --------------------------------------------------------------------------- aminer extraction


def _str_from_value(value: Any) -> str:
    """First usable string out of an AMiner field. `paper_*` returns plain
    strings; `patent_detail` wraps `title` / `abstract` as {"en": [...],
    "zh": [...]} — without descending into that dict the record has no title,
    fails entity detection, and the paid call lands as a no-hit."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, list) and value and isinstance(value[0], str) and value[0].strip():
        return value[0].strip()
    if isinstance(value, dict):
        for sub in (value.get("zh"), value.get("en"), value.get("name"), value.get("raw")):
            got = _str_from_value(sub)
            if got:
                return got
    return ""


def _first_str(record: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        got = _str_from_value(record.get(key))
        if got:
            return got
    return ""


def _looks_like_entity(record: dict[str, Any]) -> bool:
    return bool(_first_str(record, ID_KEYS)) and bool(_first_str(record, TITLE_KEYS))


def _absorb_content(node: dict[str, Any], entry: dict[str, Any]) -> None:
    """Keep the text the call actually paid for.

    A `paper_detail` abstract costs money and a `paper_info` slice costs a free
    call; dropping either on the floor means the ledger cannot show what a claim
    rests on, cannot check a citation, and cannot survive a restart. Stored here,
    never printed by `render` or `gaps` — use `source show` to read one.
    """
    authors = node.get("authors")
    if isinstance(authors, list):
        names = [a["name"].strip() for a in authors
                 if isinstance(a, dict) and isinstance(a.get("name"), str) and a["name"].strip()]
        if not names:
            names = [a.strip() for a in authors if isinstance(a, str) and a.strip()]
        if names:
            entry["authors"] = names
    for key in ("abstract", "abstract_slice"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            entry[key] = value.strip()
        elif isinstance(value, dict):
            # patent_detail abstracts arrive as {"en": [...], "zh": [...]} with
            # NOVELTY / USE / ADVANTAGE sections as separate list items.
            for sub in (value.get("zh"), value.get("en")):
                if isinstance(sub, list):
                    text = " ".join(p.strip() for p in sub if isinstance(p, str) and p.strip())
                    if text:
                        entry[key] = text
                        break
    keywords = node.get("keywords")
    if isinstance(keywords, str) and keywords.strip():
        entry["keywords"] = keywords.strip()
    elif isinstance(keywords, list):
        words = [k.strip() for k in keywords if isinstance(k, str) and k.strip()]
        if words:
            entry["keywords"] = words
    # Patents carry the rights holder under `assignee` / `applicant` as a list of
    # {name, raw_address_info, sequence}; papers never have it. Mirroring the
    # authors extraction so a `patent_detail` hit persists the assignee a player
    # table and a per-assignee corpus chart both need.
    for key in ("assignee", "applicant"):
        holder = node.get(key)
        if isinstance(holder, list):
            names = [h["name"].strip() for h in holder
                     if isinstance(h, dict) and isinstance(h.get("name"), str) and h["name"].strip()]
            if names:
                entry["assignee"] = names
                break
        elif isinstance(holder, str) and holder.strip():
            entry["assignee"] = [holder.strip()]
            break


def _coerce_year(value: Any) -> int | None:
    """Normalise a year from whatever an AMiner node carries: a paper's `year`
    int, a patent_search `app_year` / `pub_year` string ("2024"), or a
    patent_detail epoch dict {"seconds": 1640908800}. Returns None when nothing
    parses — the source ships without a year rather than with a fabricated one."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 1000 <= value <= 2999 else None
    if isinstance(value, str):
        m = re.search(r"\b(1[0-9]{3}|20[0-9]{2}|2[1-9]\d{2})\b", value)
        return int(m.group(1)) if m else None
    if isinstance(value, dict):
        seconds = value.get("seconds")
        if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
            try:
                return time.gmtime(seconds).tm_year
            except (OverflowError, ValueError, OSError):
                return None
    return None


def _walk(node: Any, via: str, kind: str, found: list[dict[str, Any]], depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(node, list):
        for item in node:
            _walk(item, via, kind, found, depth + 1)
        return
    if not isinstance(node, dict):
        return
    if _looks_like_entity(node):
        entry: dict[str, Any] = {
            "kind": kind,
            "id": _first_str(node, ID_KEYS),
            "title": _first_str(node, TITLE_KEYS),
            "via": via,
            "depth": _depth_for_api(via),
        }
        year = _coerce_year(
            node.get("year") or node.get("app_year") or node.get("pub_year")
            or node.get("app_date") or node.get("pub_date")
        )
        if year is not None:
            entry["year"] = year
        venue = node.get("venue")
        if isinstance(venue, str) and venue.strip():
            entry["venue"] = venue.strip()
        elif isinstance(venue, dict):
            name = _first_str(venue, ("name", "name_zh", "raw"))
            if name:
                entry["venue"] = name
        elif isinstance(node.get("venue_name"), str) and node["venue_name"].strip():
            entry["venue"] = node["venue_name"].strip()
        _absorb_content(node, entry)
        found.append(entry)
        return
    for value in node.values():
        _walk(value, via, kind, found, depth + 1)


# How deeply a source has actually been read, named after where the data came
# from. A search result is a title; a `paper_info` slice is a truncated
# abstract; only `paper_detail` is the whole abstract and keywords. Claims must
# not rest on the first two.
DEPTHS = ("search", "slice", "detail")
DEPTH_RANK = {name: i for i, name in enumerate(DEPTHS)}
DEPTH_BY_API = {"paper_info": "slice", "paper_detail": "detail", "patent_detail": "detail"}


def _depth_for_api(api: str) -> str:
    return DEPTH_BY_API.get(api, "search")


KIND_BY_API = {
    "person_search": "scholar",
    "person_detail": "scholar",
    "person_figure": "scholar",
    "org_person_relation": "scholar",
    "person_project": "project",
    "org_search": "org",
    "org_detail": "org",
    "org_disambiguate": "org",
    "org_disambiguate_pro": "org",
    "venue_search": "venue",
    "venue_detail": "venue",
}


def _kind_for_api(api: str) -> str:
    """Entity kind the API returns. Pass --kind for anything not covered here."""
    if api in KIND_BY_API:
        return KIND_BY_API[api]
    if "patent" in api:
        return "patent"
    return "paper"


def extract_from_aminer(payload: Any, kind_override: str | None = None) -> list[dict[str, Any]]:
    """Pull entity records out of an aminer_open.py result document."""
    found: list[dict[str, Any]] = []
    results = payload.get("results") if isinstance(payload, dict) else None
    if isinstance(results, list):
        for result in results:
            if not isinstance(result, dict) or not result.get("ok"):
                continue
            api = str(result.get("api") or "")
            _walk(result.get("data"), api, kind_override or _kind_for_api(api), found)
    else:
        _walk(payload, "", kind_override or "paper", found)
    unique: dict[str, dict[str, Any]] = {}
    for item in found:
        unique.setdefault(f"{item['kind']}:{item['id']}", item)
    return list(unique.values())


# --------------------------------------------------------------------------- claims and analysis


def _add_claim(state: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    return _record_claim(
        state,
        text=args.text or "",
        section=args.section or "",
        supports=list(args.supports),
        claim_type=args.type,
        conflict=args.conflict or "",
        allow_unsupported=args.allow_unsupported,
    )


def _record_claim(
    state: dict[str, Any],
    text: str,
    section: str,
    supports: list[int],
    claim_type: str = "observed",
    conflict: str = "",
    allow_unsupported: bool = False,
) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise LedgerError("A claim needs non-empty --text")
    if claim_type not in CLAIM_TYPES:
        raise LedgerError(f"Unsupported claim type '{claim_type}'; use one of: {', '.join(CLAIM_TYPES)}")
    numbers = {source["n"] for source in state["sources"]}
    unknown = [n for n in supports if n not in numbers]
    if unknown:
        raise LedgerError(f"Unknown source number(s): {', '.join(str(n) for n in unknown)}")
    if not supports and not allow_unsupported:
        raise LedgerError("A claim needs at least one --supports source (use --allow-unsupported for an open question)")
    section = _require_sections(state, [section])[0]
    claim = {
        "id": f"c{len(state['claims']) + 1}",
        "text": text,
        "supports": sorted(set(supports)),
        "type": claim_type,
        "section": section,
    }
    if conflict:
        claim["conflict"] = conflict.strip()
    state["claims"].append(claim)
    return claim


def _add_claims_batch(state: dict[str, Any], payload: Any) -> dict[str, Any]:
    """Record many claims in one call.

    A section's worth of claims is the normal unit of work; one subprocess per
    claim pushed every caller into writing their own driver loop.
    """
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise LedgerError("Batch input must be a JSON array of claim objects")
    recorded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for position, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            failed.append({"position": position, "error": "not a JSON object"})
            continue
        try:
            recorded.append(_record_claim(
                state,
                text=str(item.get("text") or ""),
                section=str(item.get("section") or ""),
                supports=[int(n) for n in (item.get("supports") or [])],
                claim_type=str(item.get("type") or "observed"),
                conflict=str(item.get("conflict") or ""),
                allow_unsupported=bool(item.get("allow_unsupported")),
            ))
        except (LedgerError, TypeError, ValueError) as exc:
            failed.append({"position": position, "text": str(item.get("text") or "")[:80], "error": str(exc)})
    return {"claims": recorded, "failed": failed}


def _rollup(state: dict[str, Any]) -> tuple[dict[str, set[int]], dict[str, list[str]], dict[str, set[str]]]:
    """Sources and claims per section id, with children rolled into the parent.

    The model tags mostly at subsection level, so a parent gate that ignored
    children would block a section that is in fact well covered.
    """
    sources_by: dict[str, set[int]] = {}
    claims_by: dict[str, list[str]] = {}
    live = {source["n"] for source in state["sources"] if not source.get("dropped")}
    for top in state["outline"]:
        for sid in (top["id"], *(kid["id"] for kid in top["children"])):
            sources_by.setdefault(sid, set())
            claims_by.setdefault(sid, [])
    for source in state["sources"]:
        if source.get("dropped"):
            continue
        for sid in source.get("sections", []):
            if sid in sources_by:
                sources_by[sid].add(source["n"])
    for claim in state["claims"]:
        if claim.get("retracted"):
            continue
        sid = claim.get("section", "")
        if sid in claims_by:
            claims_by[sid].append(claim["id"])
            # A source a section's claim leans on covers that section, whether or
            # not it was also tagged there.
            for n in claim.get("supports", []):
                if n in live:
                    sources_by[sid].add(n)

    probes_by_top: dict[str, set[str]] = {}
    for top in state["outline"]:
        own_sources = set(sources_by[top["id"]])
        own_claims = list(claims_by[top["id"]])
        for kid in top["children"]:
            own_sources |= sources_by[kid["id"]]
            own_claims += claims_by[kid["id"]]
        sources_by[top["id"]] = own_sources
        claims_by[top["id"]] = own_claims
        probes_by_top[top["id"]] = {
            p for s in state["sources"] if s["n"] in own_sources for p in s.get("probes", [])
        }
    return sources_by, claims_by, probes_by_top


def analyze(state: dict[str, Any]) -> dict[str, Any]:
    sources = _live_sources(state)
    dropped = [s["n"] for s in state["sources"] if s.get("dropped")]
    claims = _live_claims(state)
    retracted = [c["id"] for c in state["claims"] if c.get("retracted")]
    cited: set[int] = set()
    for claim in claims:
        cited.update(claim.get("supports", []))

    sources_by, claims_by, probes_by_top = _rollup(state)
    tops = [top["id"] for top in state["outline"]]
    subs = [kid for top in state["outline"] for kid in top["children"]]
    spend_total = _spend_total(state)
    figures = _live_figures(state)
    fig_sections = _figures_by_section(state)
    known_sections = set(_section_index(state))

    return {
        "topic": state.get("topic", ""),
        "genre": state.get("genre", "academic"),
        "totals": {
            "sources": len(sources),
            "dropped_sources": len(dropped),
            "claims": len(claims),
            "retracted_claims": len(retracted),
            "sections": len(tops),
            "subsections": len(subs),
            "probes": len(state["probes"]),
            "cited_sources": len(cited),
            "figures": len(figures),
            "datums": len(_live_datums(state)),
        },
        "sections": [
            {
                "id": top["id"],
                "title": top["title"],
                "sources": len(sources_by[top["id"]]),
                "claims": len(claims_by[top["id"]]),
                "probes": sorted(probes_by_top[top["id"]]),
                "children": [
                    {
                        "id": kid["id"],
                        "title": kid["title"],
                        "kind": kid["kind"],
                        "sources": len(sources_by[kid["id"]]),
                        "claims": len(claims_by[kid["id"]]),
                    }
                    for kid in top["children"]
                ],
            }
            for top in state["outline"]
        ],
        # blocking
        "outline_missing": not state["outline"],
        "sections_below_two_sources": [t for t in tops if len(sources_by[t]) < 2],
        "unsupported_claims": [c["id"] for c in claims if not c.get("supports")],
        "spend_over_hard_limit": spend_total >= HARD_LIMIT_CNY,
        # warnings
        "subsections_below_two_sources": [k["id"] for k in subs if len(sources_by[k["id"]]) < 2],
        "sections_missing_disagreement": [
            top["id"] for top in state["outline"]
            if not any(kid["kind"] == "disagreement" for kid in top["children"])
        ],
        "sections_from_single_probe": [
            t for t in tops if len(sources_by[t]) >= 2 and len(probes_by_top[t]) == 1
        ],        "low_yield_probes": [
            {
                "probe": p["id"], "axis": p.get("axis", ""), "query": p.get("query", ""),
                "new": p.get("new", 0), "returned": p.get("returned", 0),
            }
            for p in state["probes"]
            if p.get("returned", 0) >= LOW_YIELD_MIN_RETURNED
            and p.get("new", 0) * LOW_YIELD_RATIO < p.get("returned", 0)
        ],
        "drifting_probes": _drifting_probes(state),
        "sections_without_claims": [t for t in tops if not claims_by[t]],
        "untagged_sources": [s["n"] for s in sources if not s.get("sections")],
        "sources_without_probe": [s["n"] for s in sources if not s.get("probes")],
        "cited_sources_without_detail": [
            s["n"] for s in sources
            if s["n"] in cited and s["kind"] != "web" and s.get("depth") != "detail"
        ],
        "single_source_claims": [c["id"] for c in claims if len(c.get("supports", [])) == 1],
        "claims_with_unsourced_numbers": _claims_with_unsourced_numbers(state),
        "figures_with_no_sources": [f["id"] for f in figures if not f.get("source_ids")],
        "figures_unsupported_numbers": _figures_with_unsourced_numbers(state),
        "figures_in_unrendered_section": [
            f["id"] for f in figures if f.get("section", "") not in known_sections
        ],
        "figures_without_render": [f["id"] for f in figures if not f.get("rendered")],
        "figures_over_budget": len(figures) > FIGURE_BUDGET_PER_REPORT,
        "figures_industry_expected": (
            state.get("genre") == "industry" and len(figures) == 0
        ),
        "figures_industry_quantitative_expected": (
            state.get("genre") == "industry"
            and not any(
                f.get("chart_type") in QUANTITATIVE_TYPES
                or (f.get("code_path") and f.get("chart_type") != "timeline")
                for f in figures
            )
        ),
        "figures_thin_data": _figures_thin_data(state),
        "sections_over_figure_budget": [
            sid for sid, fids in fig_sections.items() if len(fids) > FIGURE_BUDGET_PER_SECTION
        ],
        "figure_code_divergence": _figure_code_divergence(state),
        "unresolved_conflicts": [
            {"claim": c["id"], "conflict": c["conflict"]} for c in claims if c.get("conflict")
        ],
        "uncited_sources": [s["n"] for s in sources if s["n"] not in cited],
        "datums_without_source": [
            d["id"] for d in _live_datums(state)
            if d.get("source") not in {s["n"] for s in sources}
        ],
        "industry_web_sources_without_datums": (
            [s["n"] for s in sources if s["kind"] == "web"
             and s["n"] not in {d["source"] for d in _live_datums(state)}]
            if state.get("genre") == "industry" else []
        ),
        "web_sources": sum(1 for s in sources if s["kind"] == "web"),
        "aminer_sources": sum(1 for s in sources if s["kind"] != "web"),
        "spend": {
            "total_cny": spend_total,
            "hard_limit_cny": HARD_LIMIT_CNY,
            "by_api": state["spend"],
        },
        "unscouted": bool(state.get("unscouted")),
    }


def _source_text(source: dict[str, Any]) -> str:
    """Everything the ledger has actually read about one source, as one blob."""
    parts: list[str] = []
    for key in ("title", "abstract", "abstract_slice", "note", "venue"):
        value = source.get(key)
        if isinstance(value, str):
            parts.append(value)
    for key in ("keywords", "authors"):
        value = source.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(v) for v in value)
    year = source.get("year")
    if year:
        parts.append(str(year))
    return DIGIT_RUN_PATTERN.sub("", " ".join(parts))


def _checkable_numbers(text: str) -> list[str]:
    out: list[str] = []
    for match in NUMBER_PATTERN.finditer(text):
        normalised = match.group().replace(",", ".")
        digits = normalised.replace(".", "")
        if "." not in normalised and len(digits) < 3:
            continue  # one- and two-digit values are too common to mean anything
        if "." not in normalised and len(digits) == 4 and 1900 <= int(digits) <= 2099:
            continue  # a bare year is prose, not a reported figure
        if text[match.end():match.end() + 3].lstrip()[:1] in MYRIAD_UNITS:
            continue  # rescaled by a myriad unit, so a literal match can never succeed
        out.append(normalised)
    return list(dict.fromkeys(out))


def _claims_with_unsourced_numbers(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Figures in a claim that appear in none of the sources it cites.

    This is the one error `check` used to be blind to: the prose is fine, the
    citation points at the wrong source. A warning, not a gate — a figure the
    model converted into another unit or another language ("4 million" written as
    "400 万") lands here too, and that is still worth a second look.
    """
    by_number = {source["n"]: source for source in state["sources"]}
    findings: list[dict[str, Any]] = []
    for claim in _live_claims(state):
        supports = [by_number[n] for n in claim.get("supports", []) if n in by_number]
        haystacks = [_source_text(s) for s in supports]
        if not any(h.strip() for h in haystacks):
            continue  # nothing was ever read for these sources; other warnings cover that
        blob = DIGIT_RUN_PATTERN.sub("", " ".join(haystacks))
        missing = [n for n in _checkable_numbers(claim["text"]) if n not in blob]
        if missing:
            findings.append({
                "claim": claim["id"],
                "section": claim.get("section", ""),
                "supports": claim.get("supports", []),
                "numbers_not_in_any_cited_source": missing,
            })
    return findings


# --------------------------------------------------------------------------- figures


def _live_figures(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in state["figures"] if not f.get("dropped")]


def _figure_index(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {f["id"]: f for f in state["figures"] if f.get("id")}


def _record_figure(
    state: dict[str, Any],
    section: str,
    chart_type: str,
    title: str,
    data: Any,
    sources: list[int],
    claims: list[str],
    code_path: str,
    from_datums: bool = False,
    from_metadata: bool = False,
) -> dict[str, Any]:
    if not title.strip():
        raise LedgerError("A figure needs a non-empty --title")
    section = _require_sections(state, [section])[0]
    numbers = {source["n"] for source in state["sources"]}
    unknown = [n for n in sources if n not in numbers]
    if unknown:
        raise LedgerError(f"Unknown source number(s): {', '.join(str(n) for n in unknown)}")
    if not sources:
        raise LedgerError("A figure needs at least one --supports source (its data must be sourced)")
    claim_ids = {c["id"] for c in state["claims"]}
    bad_claims = [c for c in claims if c not in claim_ids]
    if bad_claims:
        raise LedgerError(f"Unknown claim id(s): {', '.join(bad_claims)}")
    if not code_path and chart_type not in FIGURE_TYPES:
        raise LedgerError(
            f"No template for chart_type '{chart_type}'. Supported: {', '.join(FIGURE_TYPES)}; "
            f"for other shapes supply --code <path> (a B script)."
        )
    figure = {
        "id": f"f{len(state['figures']) + 1}",
        "section": section,
        "chart_type": chart_type,
        "title": title.strip(),
        "data": data,
        "source_ids": sorted(set(sources)),
        "claim_ids": sorted(set(claims)),
        "rendered": False,
        "rendered_by": None,
        "from_datums": from_datums,
        "from_metadata": from_metadata,
    }
    if code_path:
        figure["code_path"] = code_path
    state["figures"].append(figure)
    return figure


def _mark_figure_rendered(state: dict[str, Any], fid: str, path: str, by: str) -> dict[str, Any]:
    by_id = _figure_index(state)
    figure = by_id.get(fid)
    if figure is None:
        raise LedgerError(f"Unknown figure id '{fid}'. Valid ids: {', '.join(by_id) or 'none'}")
    if by not in ("script", "template"):
        raise LedgerError("--by must be 'script' or 'template'")
    figure["render_path"] = path
    figure["rendered"] = True
    figure["rendered_by"] = by
    return figure


def _drop_figures(state: dict[str, Any], ids: list[str], reason: str) -> dict[str, Any]:
    by_id = _figure_index(state)
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise LedgerError(f"Unknown figure id(s): {', '.join(unknown)}. Valid: {', '.join(by_id) or 'none'}")
    dropped: list[str] = []
    for fid in dict.fromkeys(ids):
        figure = by_id[fid]
        if figure.get("dropped"):
            continue
        figure["dropped"] = True
        if reason:
            figure["drop_reason"] = reason
        dropped.append(fid)
    return {"dropped": dropped, "remaining": len(_live_figures(state))}


def _datum_numeric(value: Any) -> float | None:
    """A datum value as a float, resolving 万 / 亿 myriad suffixes. None if not
    numeric — a non-numeric datum belongs in a timeline, not a bar."""
    if value is None:
        return None
    s = str(value).strip()
    try:
        return float(s)
    except ValueError:
        pass
    for suffix, mult in (("万", 1e4), ("亿", 1e8)):
        if s.endswith(suffix):
            try:
                return float(s[: -len(suffix)]) * mult
            except ValueError:
                return None
    return None


def _live_datums(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [d for d in state.get("datums", []) if not d.get("dropped")]


def _public_datum(datum: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in datum.items() if k != "dropped"}


def _record_datum(
    state: dict[str, Any],
    source: int,
    metric: str,
    value: str,
    unit: str,
    year: str,
    entity: str,
) -> dict[str, Any]:
    if not metric.strip():
        raise LedgerError("A datum needs a non-empty --metric (what the number measures)")
    if not str(value).strip():
        raise LedgerError("A datum needs a non-empty --value")
    numbers = {s["n"] for s in state["sources"]}
    if source not in numbers:
        raise LedgerError(f"Unknown source number: {source}")
    datum = {
        "id": f"d{len(state.get('datums', [])) + 1}",
        "source": source,
        "metric": metric.strip(),
        "value": str(value).strip(),
        "unit": unit.strip(),
        "year": year.strip(),
        "entity": entity.strip(),
    }
    state.setdefault("datums", []).append(datum)
    return datum


def _drop_datums(state: dict[str, Any], ids: list[str], reason: str) -> dict[str, Any]:
    by_id = {d["id"]: d for d in state.get("datums", []) if d.get("id")}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise LedgerError(f"Unknown datum id(s): {', '.join(unknown)}. Valid: {', '.join(by_id) or 'none'}")
    dropped: list[str] = []
    for did in dict.fromkeys(ids):
        datum = by_id[did]
        if datum.get("dropped"):
            continue
        datum["dropped"] = True
        if reason:
            datum["drop_reason"] = reason
        dropped.append(did)
    return {"dropped": dropped, "remaining": len(_live_datums(state))}


def _assemble_figure_data(
    state: dict[str, Any], datum_ids: list[str], chart_type: str,
) -> tuple[Any, list[int]]:
    """Build a figure's --data and its source list from captured datums. Each
    datum already cites a source, so the assembled numbers are source-verified
    by construction — the figure is exempt from figures_with_unsourced_numbers."""
    by_id = {d["id"]: d for d in _live_datums(state)}
    unknown = [i for i in datum_ids if i not in by_id]
    if unknown:
        raise LedgerError(f"Unknown datum id(s): {', '.join(unknown)}. Valid: {', '.join(by_id) or 'none'}")
    datums = [by_id[i] for i in dict.fromkeys(datum_ids)]
    if chart_type in ("bar", "hbar", "pie"):
        out = []
        for d in datums:
            v = _datum_numeric(d.get("value"))
            if v is None:
                raise LedgerError(
                    f"datum {d['id']} value {d.get('value')!r} is not numeric; "
                    f"use --type timeline for non-numeric / dated data"
                )
            out.append({"label": d.get("entity") or d.get("metric", ""), "value": v})
        data: Any = out
    elif chart_type == "timeline":
        data = [
            {
                "date": d.get("year") or d.get("value", ""),
                "event": f"{d.get('entity') or d.get('metric', '')}: {d.get('value', '')}{d.get('unit', '')}",
                "group": d.get("metric", ""),
            }
            for d in datums
        ]
    elif chart_type == "line":
        series: dict[str, list[dict[str, Any]]] = {}
        for d in datums:
            v = _datum_numeric(d.get("value"))
            if v is None:
                raise LedgerError(
                    f"datum {d['id']} value {d.get('value')!r} is not numeric; "
                    f"use --type timeline for non-numeric / dated data"
                )
            series.setdefault(d.get("metric", ""), []).append({"x": d.get("year", ""), "y": v})
        data = [
            {"series": m, "points": sorted(pts, key=lambda p: str(p["x"]))}
            for m, pts in series.items()
        ]
    else:
        raise LedgerError(
            f"--from-datums assembles bar / hbar / pie / line / timeline, not '{chart_type}'; "
            f"for {chart_type} pass --data directly"
        )
    sources = sorted({d["source"] for d in datums})
    return data, sources


def _source_metadata_label(source: dict[str, Any], field: str) -> str | None:
    """One aggregation label for a source along a metadata field, or None when
    the source carries no value for it. `year` and `venue` are scalars; the
    patent rights-holder lives under `assignee` (a list of names) — its primary
    holder is the label, the way a player table would file it."""
    if field == "year":
        y = source.get("year")
        return str(y) if isinstance(y, int) else None
    if field == "venue":
        v = source.get("venue")
        return v.strip() if isinstance(v, str) and v.strip() else None
    if field == "assignee":
        holders = source.get("assignee")
        if isinstance(holders, list) and holders and isinstance(holders[0], str):
            return holders[0].strip() or None
        if isinstance(holders, str) and holders.strip():
            return holders.strip()
        return None
    if field == "kind":
        k = source.get("kind")
        return k.strip() if isinstance(k, str) and k.strip() else None
    return None


def _assemble_metadata_figure(
    state: dict[str, Any], source_nums: list[int], field: str, chart_type: str,
) -> tuple[Any, list[int]]:
    """Build a figure's --data by counting how the given sources fall along a
    metadata field — patents per application year, filings per assignee, papers
    per venue. The counts come from the ledger's own source records, so the
    numbers are source-verified by construction and the figure is exempt from
    `figures_with_unsourced_numbers` (the same exemption `--from-datums` gets)."""
    if field not in ("year", "venue", "assignee", "kind"):
        raise LedgerError(
            f"--from-source-metadata aggregates by year / venue / assignee / kind, not '{field}'"
        )
    by_number = {s["n"]: s for s in state["sources"]}
    counts: dict[str, int] = {}
    used: list[int] = []
    for n in dict.fromkeys(source_nums):
        source = by_number.get(n)
        if source is None:
            raise LedgerError(f"Unknown source number(s): {n}")
        label = _source_metadata_label(source, field)
        if not label:
            continue
        counts[label] = counts.get(label, 0) + 1
        used.append(n)
    if not counts:
        raise LedgerError(
            f"None of the given sources carry a '{field}' value to aggregate; "
            f"capture the field first (patents need a patent_detail call)"
        )
    if chart_type not in ("bar", "hbar", "pie"):
        raise LedgerError(
            f"--from-source-metadata assembles bar / hbar / pie, not '{chart_type}'; "
            f"for {chart_type} pass --data directly"
        )
    items = [{"label": label, "value": value} for label, value in counts.items()]
    if field == "year":
        items.sort(key=lambda it: it["label"])            # chronological left→right
    else:
        items.sort(key=lambda it: (-it["value"], it["label"]))  # count desc, then name
    data: Any = items
    sources = sorted(set(used))
    return data, sources


def _figure_data_text(figure: dict[str, Any]) -> str:
    """Serialise a figure's data to text so the number-provenance check can
    run over it with the same machinery it uses for claim prose."""
    return json.dumps(figure.get("data"), ensure_ascii=False)


def _figure_source_numbers(state: dict[str, Any], figure: dict[str, Any]) -> list[int]:
    """Every source number a figure's data leans on: its own source_ids plus
    the supports of the claims it visualises. Same haystack a claim uses."""
    by_id = {c["id"]: c for c in state["claims"]}
    nums = set(figure.get("source_ids", []))
    for cid in figure.get("claim_ids", []):
        claim = by_id.get(cid)
        if claim:
            nums.update(claim.get("supports", []))
    return sorted(nums)


def _figures_with_unsourced_numbers(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Figures whose data carries numbers that appear in none of their sources.

    The same check `claims_with_unsourced_numbers` runs over claim prose, now
    over a figure's serialised data — so a chart cannot smuggle in a number the
    ledger never sourced. A warning, not a gate, for the same reason as claims:
    a unit conversion or a myriad-unit rescale lands here too.
    """
    by_number = {source["n"]: source for source in state["sources"]}
    findings: list[dict[str, Any]] = []
    for figure in _live_figures(state):
        if figure.get("from_datums") or figure.get("from_metadata"):
            continue  # assembled from captured datums / ledger metadata; counts are source-verified by construction
        nums = _figure_source_numbers(state, figure)
        haystacks = [by_number[n] for n in nums if n in by_number]
        texts = [_source_text(s) for s in haystacks]
        if not any(t.strip() for t in texts):
            continue  # nothing was ever read for these sources; other warnings cover that
        blob = DIGIT_RUN_PATTERN.sub("", " ".join(texts))
        missing = [n for n in _checkable_numbers(_figure_data_text(figure)) if n not in blob]
        if missing:
            findings.append({
                "figure": figure["id"],
                "section": figure.get("section", ""),
                "source_ids": nums,
                "numbers_not_in_any_cited_source": missing,
            })
    return findings


def _figures_thin_data(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Figures whose data has too few points to plot meaningfully.

    `figures_with_unsourced_numbers` asks whether a figure's numbers are
    sourced; this asks whether there are enough of them to be a chart at all —
    a one-bar bar chart or a one-point line is a defect, not a figure. A
    structural figure (timeline) needs >=2 events. A custom B-script shape (no
    matching template type) is not structurally checked here; the provenance
    and divergence checks still apply to it.
    """
    findings: list[dict[str, Any]] = []
    for figure in _live_figures(state):
        ct = figure.get("chart_type", "")
        data = figure.get("data")
        thin = False
        if ct in ("bar", "hbar", "pie"):
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                # grouped bar: {series, items:[{label, values}]} — thin if <2 items
                thin = len(data["items"]) < 2
            else:
                thin = not isinstance(data, list) or len(data) < 2
        elif ct == "line":
            if isinstance(data, list):
                series_list = data
            elif isinstance(data, dict):
                series_list = [data]
            else:
                series_list = []
            pts = sum(len(s.get("points", [])) for s in series_list if isinstance(s, dict))
            thin = pts < 2
        elif ct == "heatmap":
            rows = len(data.get("rows", [])) if isinstance(data, dict) else 0
            cols = len(data.get("cols", [])) if isinstance(data, dict) else 0
            thin = rows < 2 or cols < 2
        elif ct == "timeline":
            thin = not isinstance(data, list) or len(data) < 2
        else:
            continue  # custom B-script shape: structure unknown, other checks apply
        if thin:
            findings.append({
                "figure": figure["id"],
                "section": figure.get("section", ""),
                "chart_type": ct,
                "minimum_points": 2,
            })
    return findings


def _figure_code_divergence(state: dict[str, Any]) -> list[dict[str, Any]]:
    """A B script that hardcodes a number the registered data does not carry.

    Heuristic and deliberately a warning, not a gate: it reads the script text
    and flags 3-plus-digit literals absent from the figure's data blob. A real
    divergence check would hook the script's plotting calls; this catches the
    obvious 'the script baked in a different figure' without running anything.
    Figures without a code_path are unaffected.
    """
    findings: list[dict[str, Any]] = []
    for figure in _live_figures(state):
        code_path = figure.get("code_path")
        if not code_path:
            continue
        path = Path(code_path)
        if not path.exists():
            continue
        data_blob = _figure_data_text(figure)
        script_text = path.read_text(encoding="utf-8")
        extra = [n for n in _checkable_numbers(script_text) if n not in data_blob]
        if extra:
            findings.append({
                "figure": figure["id"],
                "code_path": code_path,
                "numbers_in_script_not_in_data": extra,
            })
    return findings


def _figures_by_section(state: dict[str, Any]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for top in state["outline"]:
        for sid in (top["id"], *(kid["id"] for kid in top["children"])):
            grouped.setdefault(sid, [])
    for figure in _live_figures(state):
        sid = figure.get("section", "")
        if sid in grouped:
            grouped[sid].append(figure["id"])
    return grouped


def _probe_yield(state: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Per-probe kept/dropped counts, read off the sources themselves.

    Derived rather than counted at add time so it stays correct after `drop`,
    which is exactly when drift becomes visible.
    """
    tally: dict[str, dict[str, int]] = {p["id"]: {"kept": 0, "dropped": 0} for p in state["probes"]}
    for source in state["sources"]:
        bucket = "dropped" if source.get("dropped") else "kept"
        for pid in source.get("probes", []):
            if pid in tally:
                tally[pid][bucket] += 1
    return tally


def _drifting_probes(state: dict[str, Any]) -> list[dict[str, Any]]:
    tally = _probe_yield(state)
    out: list[dict[str, Any]] = []
    for probe in state["probes"]:
        counts = tally[probe["id"]]
        returned = counts["kept"] + counts["dropped"]
        if returned < DRIFT_MIN_RETURNED:
            continue
        rate = counts["dropped"] / returned
        if rate >= DRIFT_RATIO:
            out.append({
                "probe": probe["id"],
                "axis": probe.get("axis", ""),
                "query": probe.get("query", ""),
                "returned": returned,
                "kept": counts["kept"],
                "dropped": counts["dropped"],
                "drop_rate": round(rate, 2),
            })
    return out


# --------------------------------------------------------------- render labels

# The report follows the user's language, so the renderer has to as well: a
# Chinese report used to come back wearing an English skeleton (`## References`,
# `Drop rate`, `_(disagreement)_`) because every label here was a literal.
#
# What is *not* translated is as deliberate as what is. API names, probe ids and
# `axis` values are controlled vocabulary shared with the CLI and the API
# catalog; source titles and venues are real metadata. Translating any of them
# would break the link between the report and the thing it cites.
_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")

_LABELS_EN = {
    "sources_prefix": "Sources: ",
    "sources_none": "none",
    "disagreement": " _(disagreement)_",
    "interpretation": " _(interpretation)_",
    "conflict": "conflict: ",
    "unsupported": "[unsupported]",
    "no_outline": "_No outline: run the Round 0 scout, then `evidence.py outline set`._",
    "no_claims": "_No claims recorded — do not write this subsection._",
    "references": "## References",
    "no_sources": "_No sources recorded._",
    "unplaced": "## Unplaced claims",
    "unplaced_note": "section '{section}' no longer exists",
    "figure_placeholder": "_[FIGURE {id}] {title} — sources: {sources}_",
    "unplaced_figures": "## Unplaced figures",
    "appendix_a": "## Appendix A — Retrieval log",
    "appendix_a_head": (
        "| Probe | Axis | Tool | Query | Returned | Kept | Dropped | Drop rate | Reasons for dropping |"
    ),
    "no_probes": "_No probes registered._",
    "appendix_b": "## Appendix B — Calls and cost",
    "appendix_b_head": "| API | Calls | Unit price (CNY) | Subtotal (CNY) |",
    "total": "**Total**",
    "all_free": "_Every call in this run was free._",
    "cost_note": (
        "Free endpoints are not billed and therefore do not appear above. "
        "Hard stop for one task: CNY {limit:.2f}."
    ),
    "appendix_c": "## Appendix C — Data and methods",
    "appendix_c_head": "| Item | Value |",
    "c_searches": "Searches run (by axis)",
    "c_searches_fmt": "{n} ({axes})",
    "c_screened": "Records screened / retained / discarded",
    "c_depth": "Reading depth of retained sources",
    "c_kinds": "Academic sources / web sources",
    "c_claims": "Claims recorded (of which interpretation)",
    "c_claims_fmt": "{n} ({part})",
    "c_conflicts": "Claims carrying a recorded conflict",
    "c_coverage": "Top-level sections / subsections",
    "c_figures": "Figures recorded",
    "c_depth_names": {"detail": "full abstract", "slice": "abstract slice", "search": "title only"},
    "appendix_c_figures": "### Figures",
    "appendix_c_figures_head": "| Figure | Type | Sources | Rendered by |",
    "c_prose_todo": (
        "_Add below, in prose: inclusion and exclusion criteria, the retrieval time "
        "window and year filter, the language strategy, and the evidence level "
        "(abstract-level, not full text). The ledger cannot know these._"
    ),
    "pointer": (
        "Appendices are written to `{path}`: Appendix A records each search's axis, "
        "query, returned/kept/discarded counts and the reasons for discarding; "
        "Appendix B records calls and cost per endpoint; Appendix C records the "
        "screening counts, reading-depth distribution and coverage statistics."
    ),
    "appendix_d": "## Appendix D — Citation number map",
    "appendix_d_head": "| Report | Ledger | Title |",
    "appendix_d_note": (
        "_Report numbers are the ascending first-appearance numbers of the report "
        "delivered with this map (see its `*-citation-map.json` sidecar). `*` marks a "
        "retained source the report never cites; such sources appear in figure-source "
        "columns as `43*`, i.e. by ledger number._"
    ),
    "pointer_with_map": (
        "Appendices are written to `{path}`: Appendix A records each search's axis, "
        "query, returned/kept/discarded counts and the reasons for discarding; "
        "Appendix B records calls and cost per endpoint; Appendix C records the "
        "screening counts, reading-depth distribution and coverage statistics; "
        "Appendix D maps the report's citation numbers to ledger source numbers."
    ),
}

_LABELS_ZH = {
    "sources_prefix": "来源：",
    "sources_none": "无",
    "disagreement": " _（分歧）_",
    "interpretation": " _（解读）_",
    "conflict": "冲突：",
    "unsupported": "[无来源]",
    "no_outline": "_尚无大纲：先做第 0 轮扫描，再执行 `evidence.py outline set`。_",
    "no_claims": "_未记录任何论断——本子节不得写入报告。_",
    "references": "## 参考文献",
    "no_sources": "_未记录任何来源。_",
    "unplaced": "## 未归位论断",
    "unplaced_note": "章节 '{section}' 已不存在",
    "figure_placeholder": "_[FIGURE {id}] {title} — 来源：{sources}_",
    "unplaced_figures": "## 未归位图表",
    "appendix_a": "## 附录 A — 检索明细",
    "appendix_a_head": "| 探针 | 检索轴 | 工具 | 查询 | 返回 | 保留 | 丢弃 | 丢弃率 | 丢弃原因 |",
    "no_probes": "_未登记任何探针。_",
    "appendix_b": "## 附录 B — 调用与费用",
    "appendix_b_head": "| 接口 | 调用次数 | 单价（元） | 小计（元） |",
    "total": "**合计**",
    "all_free": "_本次运行的所有调用均为免费接口。_",
    "cost_note": "免费接口不计费，故不在上表中。单个任务的强制停止线：{limit:.2f} 元。",
    "appendix_c": "## 附录 C — 数据与方法",
    "appendix_c_head": "| 项目 | 数值 |",
    "c_searches": "检索次数（按检索轴）",
    "c_searches_fmt": "{n}（{axes}）",
    "c_screened": "筛查 / 保留 / 丢弃条数",
    "c_depth": "保留来源的读取深度",
    "c_kinds": "学术来源 / 网页来源",
    "c_claims": "论断条数（其中解读类）",
    "c_claims_fmt": "{n}（{part}）",
    "c_conflicts": "记录了冲突的论断",
    "c_coverage": "一级章节 / 子节",
    "c_figures": "已记录图表",
    "c_depth_names": {"detail": "完整摘要", "slice": "摘要片段", "search": "仅题目"},
    "appendix_c_figures": "### 图表",
    "appendix_c_figures_head": "| 图表 | 类型 | 来源 | 渲染方式 |",
    "c_prose_todo": (
        "_请在下方以散文补足台账无法知道的部分：纳入与排除标准、检索时间窗与年份过滤、"
        "语言策略，以及证据层级（摘要级而非全文级）。_"
    ),
    "pointer": (
        "附录已写入 `{path}`：附录 A 记录每次检索的检索轴、查询与返回／保留／丢弃条数"
        "及丢弃原因，附录 B 记录各接口的调用次数与费用小计，附录 C 记录筛查计数、"
        "证据读取深度分布与覆盖统计。"
    ),
    "appendix_d": "## 附录 D — 引用编号对照",
    "appendix_d_head": "| 报告编号 | 台账编号 | 标题 |",
    "appendix_d_note": (
        "_报告编号是随本映射交付的那份报告中按正文首现递增的编号（sidecar 为 "
        "`*-citation-map.json`）。`*` 标记报告未引用、仅台账留存的来源；这类来源在图表"
        "来源列中以 `43*` 形式按台账编号出现。_"
    ),
    "pointer_with_map": (
        "附录已写入 `{path}`：附录 A 记录每次检索的检索轴、查询与返回／保留／丢弃条数"
        "及丢弃原因，附录 B 记录各接口的调用次数与费用小计，附录 C 记录筛查计数、"
        "证据读取深度分布与覆盖统计，附录 D 给出报告引用号与台账编号的对照。"
    ),
}


def _labels(state: dict[str, Any], lang: str = "auto") -> dict[str, Any]:
    """Label table for the render. `auto` follows the ledger's topic.

    Auto-detection rather than a flag: the language of the report is already
    decided by the request, and a flag the model has to remember is a flag the
    model eventually forgets — which is exactly how the English skeleton got
    into a Chinese report.
    """
    if lang == "auto":
        lang = "zh" if _CJK.search(state.get("topic") or "") else "en"
    return _LABELS_ZH if lang == "zh" else _LABELS_EN


def _bibliography_line(source: dict[str, Any], number: int) -> str:
    """One reference in academic form: authors, title, venue, year, link.

    Tool provenance (`via paper_qa_search_pro`) is deliberately absent — it is
    retrieval bookkeeping, not bibliographic data, and belongs in the appendix.
    """
    bits: list[str] = []
    authors = source.get("authors")
    if isinstance(authors, list) and authors:
        shown = ", ".join(str(a) for a in authors[:3])
        bits.append(f"{shown}, et al." if len(authors) > 3 else f"{shown}.")
    elif isinstance(authors, str) and authors.strip():
        bits.append(f"{authors.strip()}.")
    bits.append(f"{source['title'].rstrip('.')}.")
    tail = [str(source[key]) for key in ("venue", "year") if source.get(key)]
    if tail:
        bits.append(", ".join(tail) + ".")
    if source.get("url"):
        bits.append(source["url"])
    return f"[{number}] " + " ".join(bits)


CITE_TOKEN = re.compile(r"\[@(\d+)\]")
REFERENCES_PLACEHOLDER = "{{references}}"


def _renumber_draft(state: dict[str, Any], draft: Path, out: Path, lang: str = "auto",
                    ledger: str = "") -> dict[str, Any]:
    """Assign the report's ascending citation numbers from the draft itself.

    Engine-side numbers (ledger n — stable, never renumbered, a dropped source
    keeps its slot) and reader-side numbers (first appearance in the delivered
    text) are strictly separated. The draft carries [@n] placeholders keyed to
    ledger numbers; this pass assigns dense ascending numbers by where each
    token first appears, substitutes them, fills the `{{references}}` slot with
    a cited-only bibliography, and writes the mapping to a sidecar the appendix
    consumes. A placeholder naming an unknown or dropped source is a hard error
    — a citation pointing at nothing must not reach the page.
    """
    text = draft.read_text(encoding="utf-8")
    live = {source["n"]: source for source in _live_sources(state)}
    dropped = {source["n"] for source in state["sources"] if source.get("dropped")}

    unknown = sorted({int(m.group(1)) for m in CITE_TOKEN.finditer(text)} - set(live))
    if unknown:
        dead = [n for n in unknown if n in dropped]
        missing = [n for n in unknown if n not in dropped]
        parts = []
        if missing:
            parts.append(
                "unknown source number(s) "
                + ", ".join(f"[@{n}]" for n in missing)
                + " — nothing in the ledger matches"
            )
        if dead:
            parts.append(
                "dropped source(s) "
                + ", ".join(f"[@{n}]" for n in dead)
                + " — a dropped source cannot be cited"
            )
        raise LedgerError("; ".join(parts) + ". Fix the draft; the ledger is not edited here.")

    order: list[int] = []
    seen: set[int] = set()
    for match in CITE_TOKEN.finditer(text):
        n = int(match.group(1))
        if n not in seen:
            seen.add(n)
            order.append(n)
    external = {n: i for i, n in enumerate(order, start=1)}

    replaced = CITE_TOKEN.sub(lambda m: f"[{external[int(m.group(1))]}]", text)
    if REFERENCES_PLACEHOLDER not in replaced:
        raise LedgerError(
            "Draft has no {{references}} placeholder under its references heading. "
            "`render --renumber` fills that slot with the cited-only bibliography; "
            "it never invents the section. Add the placeholder line and re-run."
        )
    entries = [_bibliography_line(live[n], external[n]) for n in order]
    replaced = replaced.replace(REFERENCES_PLACEHOLDER, "\n".join(entries))

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(replaced if replaced.endswith("\n") else replaced + "\n", encoding="utf-8")

    map_path = out.with_name(f"{out.stem}-citation-map.json")
    payload = {
        "version": 1,
        "ledger": ledger,
        "report": out.as_posix(),
        "cited": len(order),
        "external_to_ledger": {str(i): n for n, i in external.items()},
        "ledger_to_external": {str(n): i for n, i in external.items()},
    }
    map_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "out": out.as_posix(),
        "map_path": map_path.as_posix(),
        "cited": len(order),
        "entries": len(entries),
        "first_five": [f"[{external[n]}]={n}" for n in order[:5]],
    }


def _appendix_markdown(state: dict[str, Any], lang: str = "auto",
                       citation_map: dict[str, Any] | None = None) -> str:
    """Appendix A (retrieval), B (calls and cost), C (data and methods) and,
    when a citation map is supplied, D (report number -> ledger number).

    Everything the report's prose is not allowed to carry: probe ids, queries,
    yields, API names, prices, and the screening counts that used to sit in a
    "Data and methods" section in the body. With a map, source references the
    reader can chase (the figure-source column) switch to the report's external
    numbers; ledger numbers stay canonical everywhere the reader cannot see.
    """
    lab = _labels(state, lang)
    tally = _probe_yield(state)
    drop_reasons: dict[str, list[str]] = {}
    for source in state["sources"]:
        if not source.get("dropped"):
            continue
        for pid in source.get("probes", []):
            reason = source.get("drop_reason") or ""
            if reason and reason not in drop_reasons.setdefault(pid, []):
                drop_reasons[pid].append(reason)

    lines = [lab["appendix_a"], ""]
    if not state["probes"]:
        lines += [lab["no_probes"], ""]
    else:
        lines += [
            lab["appendix_a_head"],
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
        for probe in state["probes"]:
            counts = tally[probe["id"]]
            returned = counts["kept"] + counts["dropped"]
            rate = f"{counts['dropped'] / returned:.0%}" if returned else "—"
            reasons = "; ".join(drop_reasons.get(probe["id"], [])) or "—"
            lines.append(
                f"| {probe['id']} | {probe.get('axis', '')} | {probe.get('via', '') or '—'} "
                f"| {probe.get('query', '')} | {returned} | {counts['kept']} | {counts['dropped']} "
                f"| {rate} | {reasons} |"
            )
        lines.append("")

    lines += [lab["appendix_b"], ""]
    spend = state.get("spend") or {}
    if not spend:
        lines += [lab["all_free"], ""]
    else:
        lines += [lab["appendix_b_head"], "| --- | ---: | ---: | ---: |"]
        total = 0.0
        for api in sorted(spend):
            entry = spend[api]
            subtotal = float(entry.get("subtotal", 0.0))
            total += subtotal
            lines.append(f"| {api} | {entry.get('calls', 0)} | {entry.get('unit_cny', 0)} | {subtotal:.2f} |")
        lines += [f"| {lab['total']} | | | **{total:.2f}** |", ""]
        lines += [lab["cost_note"].format(limit=HARD_LIMIT_CNY), ""]

    lines += _appendix_c_lines(state, lab, citation_map)
    if citation_map:
        ext = {int(k): v for k, v in citation_map["ledger_to_external"].items()}
        lines += [lab["appendix_d"], "", lab["appendix_d_head"], "| --- | --- | --- |"]
        for source in _live_sources(state):
            n = source["n"]
            number = ext.get(n)
            report_col = f"[{number}]" if number is not None else "—"
            mark = "" if number is not None else "*"
            lines.append(f"| {report_col} | {n}{mark} | {source['title']} |")
        lines += ["", lab["appendix_d_note"], ""]
    return "\n".join(lines)


def _appendix_c_lines(state: dict[str, Any], lab: dict[str, Any],
                      citation_map: dict[str, Any] | None = None) -> list[str]:
    """Appendix C — the methods facts the ledger can actually vouch for.

    These used to be narrated from memory in a body section. Everything here is
    counted off the ledger instead; what the ledger cannot know (criteria, time
    window, language strategy) is left to prose, and said so.
    """
    live = _live_sources(state)
    claims = _live_claims(state)

    axes: dict[str, int] = {}
    for probe in state["probes"]:
        axis = probe.get("axis", "") or "—"
        axes[axis] = axes.get(axis, 0) + 1
    axis_text = ", ".join(f"{axis} {n}" for axis, n in sorted(axes.items())) or "—"

    depths: dict[str, int] = {}
    for source in live:
        depths[source.get("depth", "search")] = depths.get(source.get("depth", "search"), 0) + 1
    names = lab["c_depth_names"]
    depth_text = ", ".join(
        f"{names.get(d, d)} {depths[d]}" for d in ("detail", "slice", "search") if depths.get(d)
    ) or "—"

    web = sum(1 for s in live if s.get("kind") == "web")
    interpretations = sum(1 for c in claims if c.get("type") == "interpretation")
    conflicts = sum(1 for c in claims if c.get("conflict"))
    subs = sum(len(top["children"]) for top in state["outline"])

    rows = [
        (lab["c_searches"], lab["c_searches_fmt"].format(n=len(state["probes"]), axes=axis_text)),
        (lab["c_screened"], f"{len(state['sources'])} / {len(live)} / {len(state['sources']) - len(live)}"),
        (lab["c_depth"], depth_text),
        (lab["c_kinds"], f"{len(live) - web} / {web}"),
        (lab["c_claims"], lab["c_claims_fmt"].format(n=len(claims), part=interpretations)),
        (lab["c_conflicts"], str(conflicts)),
        (lab["c_coverage"], f"{len(state['outline'])} / {subs}"),
        (lab["c_figures"], str(len(_live_figures(state)))),
    ]
    lines = [lab["appendix_c"], "", lab["appendix_c_head"], "| --- | --- |"]
    lines += [f"| {item} | {value} |" for item, value in rows]
    figures = _live_figures(state)
    if figures:
        lines += ["", lab["appendix_c_figures"], "", lab["appendix_c_figures_head"], "| --- | --- | --- | --- |"]
        ext = citation_map["ledger_to_external"] if citation_map else None
        for f in figures:
            ftype = f.get("chart_type") or "—"
            nums = sorted(_figure_source_numbers(state, f))
            if ext:
                fsrc = ", ".join(f"[{ext[str(n)]}]" if str(n) in ext else f"{n}*"
                                 for n in nums) or "—"
            else:
                fsrc = ", ".join(str(n) for n in nums) or "—"
            fby = f.get("rendered_by") or "—"
            lines.append(f"| {f['id']} | {ftype} | {fsrc} | {fby} |")
    return lines + ["", lab["c_prose_todo"], ""]


def render_markdown(state: dict[str, Any], final: bool = False, lang: str = "auto") -> str:
    lab = _labels(state, lang)
    sources_by, claims_by, _ = _rollup(state)
    by_id = {claim["id"]: claim for claim in state["claims"]}
    index = _section_index(state)
    lines: list[str] = []

    live = _live_sources(state)
    # Citation numbers here are raw ledger numbers (stable across renders, never
    # renumbered — a drop keeps its slot). The ascending, reader-facing numbers
    # live only in the delivered report and are assigned by `render --renumber`
    # from the draft's [@n] placeholders; `--final` is the content reference the
    # host writes prose against, not the numbering source.
    fig_by_id = {f["id"]: f for f in state["figures"]}
    figures_by = _figures_by_section(state)

    def claim_bullet(claim_id: str) -> list[str]:
        claim = by_id[claim_id]
        refs = " ".join(f"[{n}]" for n in claim["supports"]) or lab["unsupported"]
        marker = "" if claim["type"] == "observed" else lab["interpretation"]
        out = [f"- **{claim['id']}**{marker} {claim['text']} {refs}"]
        if claim.get("conflict"):
            out.append(f"  - {lab['conflict']}{claim['conflict']}")
        return out

    def source_refs(section_id: str) -> str:
        return " ".join(f"[{n}]" for n in sorted(sources_by[section_id])) or lab["sources_none"]

    def fig_placeholder(fid: str) -> str:
        figure = fig_by_id.get(fid, {})
        refs = " ".join(
            f"[{n}]" for n in sorted(_figure_source_numbers(state, figure))
        ) or lab["sources_none"]
        return lab["figure_placeholder"].format(id=fid, title=figure.get("title", ""), sources=refs)

    if not state["outline"]:
        lines += [lab["no_outline"], ""]
    for top in state["outline"]:
        lines += [
            f"## {top['id']}. {top['title']}", "",
            f"_{lab['sources_prefix']}{source_refs(top['id'])}_", "",
        ]
        own = [cid for cid in claims_by[top["id"]] if by_id[cid].get("section") == top["id"]]
        if own:
            lines += [line for cid in own for line in claim_bullet(cid)]
        for fid in figures_by.get(top["id"], []):
            lines.append(fig_placeholder(fid))
        if own or figures_by.get(top["id"]):
            lines.append("")
        for kid in top["children"]:
            tag = lab["disagreement"] if kid["kind"] == "disagreement" else ""
            lines += [
                f"### {kid['id']} {kid['title']}{tag}", "",
                f"_{lab['sources_prefix']}{source_refs(kid['id'])}_", "",
            ]
            body = [line for cid in claims_by[kid["id"]] for line in claim_bullet(cid)]
            lines += body or [lab["no_claims"]]
            for fid in figures_by.get(kid["id"], []):
                lines.append(fig_placeholder(fid))
            lines.append("")

    lines += [lab["references"], ""]
    if not live:
        lines.append(lab["no_sources"])
    for source in live:
        if final:
            lines.append(_bibliography_line(source, source["n"]))
            continue
        bits = [f"[{source['n']}]"]
        title = source["title"]
        bits.append(f"[{title}]({source['url']})" if source["url"] else title)
        meta = [str(source[k]) for k in ("year", "venue") if source.get(k)]
        if source.get("via"):
            meta.append(f"via {source['via']}")
        if meta:
            bits.append("— " + ", ".join(meta))
        lines.append(" ".join(bits))

    orphans = [c for c in _live_claims(state) if c.get("section") not in index]
    if orphans:
        lines += ["", lab["unplaced"], ""] + [
            f"- **{c['id']}** {c['text']} "
            f"({lab['unplaced_note'].format(section=c.get('section', ''))})"
            for c in orphans
        ]
    orphan_figs = [f for f in _live_figures(state) if f.get("section") not in index]
    if orphan_figs:
        lines += ["", lab["unplaced_figures"], ""] + [
            f"- {f['id']} ({lab['unplaced_note'].format(section=f.get('section', ''))})"
            for f in orphan_figs
        ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- CLI


def _read_payload(args: argparse.Namespace) -> Any:
    raw = args.json if args.json else sys.stdin.read()
    if not raw.strip():
        raise LedgerError("No input: pipe JSON on stdin or pass --json")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LedgerError(f"Input is not valid JSON: {exc.msg}") from None


def _items_from_payload(payload: Any, args: argparse.Namespace) -> list[Any]:
    if args.aminer:
        return extract_from_aminer(payload, args.kind)
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise LedgerError("Input must be a JSON array of sources")
    if args.kind:
        for item in payload:
            if isinstance(item, dict):
                item.setdefault("kind", args.kind)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deep-research evidence ledger (offline)")
    parser.add_argument("--state", default=DEFAULT_STATE,
                        help="Ledger file — your workspace decides where; "
                             "defaults to $DR_LEDGER if set")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create or reset the ledger")
    init.add_argument("--topic", default="")
    init.add_argument("--genre", choices=["academic", "industry"], default="academic",
                      help="Report genre: academic (default) or industry (web-first, figures expected)")
    init.add_argument("--force", action="store_true", help="Overwrite an existing ledger")

    probe = sub.add_parser("probe", help="Register a Round 0 scout probe before running it")
    probe.add_argument("--query", required=True)
    probe.add_argument("--axis", required=True, choices=PROBE_AXES, help="Retrieval axis this probe uses")
    probe.add_argument("--via", default="", help="Tool or API the probe runs on")
    probe.add_argument("--note", default="")

    outline = sub.add_parser("outline", help="Create or revise the numbered outline")
    outline_sub = outline.add_subparsers(dest="outline_command", required=True)

    outline_set = outline_sub.add_parser("set", help="Induce the outline from the scout (stdin JSON, or --json)")
    outline_set.add_argument("--json", help="Inline JSON instead of stdin")
    outline_set.add_argument("--force", action="store_true", help="Replace an existing outline")
    outline_set.add_argument("--allow-unscouted", action="store_true",
                             help="Build the outline without probes; the report must disclose it")

    outline_add = outline_sub.add_parser("add-sub", help="Append a subsection to a top-level section")
    outline_add.add_argument("--parent", required=True)
    outline_add.add_argument("--title", required=True)
    outline_add.add_argument("--kind", choices=SECTION_KINDS, default="topic")

    outline_retitle = outline_sub.add_parser("retitle", help="Rename a section without changing its id")
    outline_retitle.add_argument("--section", required=True)
    outline_retitle.add_argument("--title", required=True)

    outline_sub.add_parser("show", help="Print the outline with per-section counts")

    add = sub.add_parser("add", help="Add sources (stdin JSON array, or --json)")
    add.add_argument("--json", help="Inline JSON instead of stdin")
    add.add_argument("--aminer", action="store_true", help="Input is aminer_open.py output; extract entity records")
    add.add_argument("--kind", choices=KINDS, help="Force the source kind")
    add.add_argument("--via", default="", help="How the source was obtained (api name, WebSearch, WebFetch)")
    add.add_argument("--section", action="append", default=[], help="Outline section id; repeatable")
    add.add_argument("--probe", default="", help="Probe id these hits came from")

    claim = sub.add_parser("claim", help="Record a claim and its supporting sources")
    claim.add_argument("--text")
    claim.add_argument("--section", help="Outline section id (see `outline show`)")
    claim.add_argument("--supports", nargs="*", type=int, default=[], help="Source numbers")
    claim.add_argument("--type", choices=CLAIM_TYPES, default="observed")
    claim.add_argument("--conflict", default="", help="Describe an unresolved disagreement between sources")
    claim.add_argument("--allow-unsupported", action="store_true", help="Record an open question with no source")
    claim.add_argument("--batch", action="store_true",
                       help="Read a JSON array of {section,text,supports,type?,conflict?} from --json or stdin")
    claim.add_argument("--json", help="Inline JSON for --batch instead of stdin")

    source = sub.add_parser("source", help="Inspect one source's stored text")
    source_sub = source.add_subparsers(dest="source_command", required=True)
    source_show = source_sub.add_parser("show", help="Print what the ledger read for a source")
    source_show.add_argument("--source", nargs="+", type=int, required=True, help="Source numbers")

    spend = sub.add_parser("spend", help="Record a paid call whose hits were not added")
    spend.add_argument("--api", required=True)
    spend.add_argument("--cny", required=True, type=float, help="Unit price of one call")
    spend.add_argument("--calls", type=int, default=1)

    drop = sub.add_parser("drop", help="Retire scout noise; the citation number stays reserved")
    drop.add_argument("--source", nargs="+", type=int, required=True, help="Source numbers to drop")
    drop.add_argument("--reason", default="")

    untag = sub.add_parser("untag", help="Remove one section tag from sources a bulk add over-tagged")
    untag.add_argument("--source", nargs="+", type=int, required=True)
    untag.add_argument("--section", required=True)

    retract = sub.add_parser("retract", help="Withdraw a mis-recorded claim; record the corrected one after")
    retract.add_argument("--claim", nargs="+", required=True)
    retract.add_argument("--reason", default="")

    figure = sub.add_parser("figure", help="Record a chart that visualizes ledger claims, then render it")
    figure_sub = figure.add_subparsers(dest="figure_command", required=True)

    figure_add = figure_sub.add_parser("add", help="Register a figure against a section's claims")
    figure_add.add_argument("--section", required=True, help="Outline section id (see `outline show`)")
    figure_add.add_argument("--type", choices=FIGURE_TYPES,
                            help="Template shape; required unless --code is given")
    figure_add.add_argument("--title", required=True)
    figure_add.add_argument("--data", help="JSON the chart plots (pass '-' to read stdin); required unless --from-datums")
    figure_add.add_argument("--sources", nargs="+", type=int,
                            help="Source numbers backing the figure's data; required unless --from-datums (which supplies them)")
    figure_add.add_argument("--claims", nargs="*", default=[], help="Claim ids the figure visualizes")
    figure_add.add_argument("--code", default="",
                            help="Path to a host-written B render script (custom shape; sandboxed by chartrender.py)")
    figure_add.add_argument("--from-datums", nargs="+", default=[],
                            help="Assemble --data (and --sources) from captured datum ids; bar/hbar/pie/line/timeline; "
                                 "numbers are source-verified by construction")
    figure_add.add_argument("--from-source-metadata", action="store_true",
                            help="Assemble --data by counting the given --sources along a metadata field "
                                 "(--field year/venue/assignee/kind); bar/hbar/pie; counts are source-verified by construction")
    figure_add.add_argument("--field", default="",
                            help="Metadata field to aggregate --from-source-metadata by: year, venue, assignee, kind")

    figure_mark = figure_sub.add_parser("mark-rendered", help="Record that chartrender.py produced the PNG")
    figure_mark.add_argument("--id", required=True)
    figure_mark.add_argument("--path", required=True, help="Rendered PNG path")
    figure_mark.add_argument("--by", choices=("script", "template"), required=True)

    figure_sub.add_parser("list", help="Print all figures with their render status")

    figure_drop = figure_sub.add_parser("drop", help="Retire mis-recorded figures")
    figure_drop.add_argument("--id", nargs="+", required=True)
    figure_drop.add_argument("--reason", default="")

    datum = sub.add_parser("datum", help="Record a number extracted from a source — the data point a figure plots")
    datum_sub = datum.add_subparsers(dest="datum_command", required=True)
    datum_add = datum_sub.add_parser("add", help="Capture one extracted number against a source")
    datum_add.add_argument("--source", type=int, required=True, help="Source number the number was read from")
    datum_add.add_argument("--metric", required=True, help="What the number measures (e.g. 市场规模, 融资额, 市场份额)")
    datum_add.add_argument("--value", required=True, help="The number (e.g. 410, 32.5, 1.2万)")
    datum_add.add_argument("--unit", default="", help="Unit (亿元, %, 亿美元)")
    datum_add.add_argument("--year", default="", help="Year or date the value applies to")
    datum_add.add_argument("--entity", default="", help="Entity the value is about (company, model, region)")
    datum_sub.add_parser("list", help="Print captured datums")
    datum_drop = datum_sub.add_parser("drop", help="Retire a mis-captured datum")
    datum_drop.add_argument("--id", nargs="+", required=True)
    datum_drop.add_argument("--reason", default="")

    sub.add_parser("gaps", help="Report coverage gaps before writing")
    sub.add_parser("stats", help="Print ledger totals")
    sub.add_parser("check", help="Exit non-zero when the ledger is not report-ready")
    render = sub.add_parser("render", help="Print the numbered outline, its claims, and the reference list")
    render.add_argument("--final", action="store_true",
                       help="Academic bibliography form; the content reference to write prose against "
                            "(numbers are stable ledger numbers)")
    render.add_argument("--appendix", action="store_true",
                       help="Print Appendix A (retrieval log), B (calls and cost) and C (data and methods) instead")
    render.add_argument("--renumber", action="store_true",
                       help="Assign the report's ascending citation numbers: read --draft (prose with "
                            "[@n] placeholders), substitute them, fill the {{references}} slot with a "
                            "cited-only bibliography, and write the delivered report plus a citation-map "
                            "sidecar to --out")
    render.add_argument("--draft", default="",
                       help="With --renumber: the draft markdown to read")
    render.add_argument("--citation-map", default="",
                       help="With --appendix: translate source references to the report's external "
                            "numbers and append Appendix D (the map)")
    render.add_argument("--lang", choices=("auto", "en", "zh"), default="auto",
                       help="Label language; auto follows the ledger topic")
    render.add_argument("--out", default="",
                       help="With --appendix: write the appendices to this file instead of stdout, "
                            "and return the path plus a one-line pointer to quote in the report "
                            "(pass 'auto' for <ledger stem>-appendix.md next to the ledger). "
                            "With --renumber: the delivered report path (required)")
    return parser


def _run_outline(state: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if args.outline_command == "set":
        if state["outline"] and not args.force:
            raise LedgerError(
                "An outline already exists; pass --force to replace it "
                "(sources keep their old section ids and may become unplaced)"
            )
        nodes = _read_payload(args)
        state["outline"] = _assign_outline(
            nodes, set(_probe_index(state)), require_probes=not args.allow_unscouted
        )
        if args.allow_unscouted:
            state["unscouted"] = True
        return {"ok": True, "outline": state["outline"], "unscouted": bool(state.get("unscouted"))}

    if args.outline_command == "add-sub":
        top = _find_top(state, args.parent)
        title = args.title.strip()
        if not title:
            raise LedgerError("A subsection needs a non-empty --title")
        kid = {"id": _next_sub_id(top), "title": title, "kind": args.kind, "from_probes": []}
        top["children"].append(kid)
        return {"ok": True, "section": kid}

    if args.outline_command == "retitle":
        index = _section_index(state)
        node = index.get(args.section)
        if node is None:
            raise LedgerError(
                f"Unknown section id '{args.section}'. Valid ids: {', '.join(index) or 'none'}"
            )
        title = args.title.strip()
        if not title:
            raise LedgerError("A section needs a non-empty --title")
        node["title"] = title
        return {"ok": True, "section": {"id": node["id"], "title": node["title"]}}

    return {"ok": True, "sections": analyze(state)["sections"]}


def _public_figure(figure: dict[str, Any]) -> dict[str, Any]:
    """Trim a figure for JSON output — drop the (possibly large) `data` blob
    and the `dropped` bookkeeping flag; everything the host needs to cite and
    re-render the figure stays."""
    return {
        key: figure[key] for key in (
            "id", "section", "chart_type", "title", "source_ids", "claim_ids",
            "rendered", "rendered_by", "render_path", "code_path", "from_datums",
            "from_metadata",
        ) if key in figure
    }


def _run_figure(state: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if args.figure_command == "add":
        from_datums = list(args.from_datums or [])
        from_metadata = bool(args.from_source_metadata)
        if from_datums and from_metadata:
            raise LedgerError("Use --from-datums or --from-source-metadata, not both")
        if from_datums:
            if not args.type:
                raise LedgerError("--from-datums requires --type (bar / hbar / pie / line / timeline)")
            data, sources = _assemble_figure_data(state, from_datums, args.type)
        elif from_metadata:
            if not args.type:
                raise LedgerError("--from-source-metadata requires --type (bar / hbar / pie)")
            if not args.field:
                raise LedgerError("--from-source-metadata requires --field (year / venue / assignee / kind)")
            if not args.sources:
                raise LedgerError("--from-source-metadata needs --sources to aggregate")
            data, sources = _assemble_metadata_figure(state, list(args.sources), args.field, args.type)
        else:
            if not args.data:
                raise LedgerError("A figure needs --data JSON, or --from-datums <ids>, or --from-source-metadata")
            raw = sys.stdin.read() if args.data == "-" else args.data
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise LedgerError(f"--data is not valid JSON: {exc.msg}") from None
            if not args.sources:
                raise LedgerError("A figure needs --sources, or --from-datums / --from-source-metadata to supply them")
            sources = list(args.sources)
        figure = _record_figure(
            state,
            section=args.section,
            chart_type=args.type or "",
            title=args.title,
            data=data,
            sources=sources,
            claims=list(args.claims),
            code_path=args.code or "",
            from_datums=bool(from_datums),
            from_metadata=from_metadata,
        )
        return {"ok": True, "figure": _public_figure(figure)}
    if args.figure_command == "mark-rendered":
        figure = _mark_figure_rendered(state, args.id, args.path, args.by)
        return {"ok": True, "figure": _public_figure(figure)}
    if args.figure_command == "drop":
        result = _drop_figures(state, list(args.id), args.reason.strip())
        return {"ok": True, **result}
    return {"ok": True, "figures": [_public_figure(f) for f in _live_figures(state)]}


def _run_datum(state: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if args.datum_command == "add":
        datum = _record_datum(
            state, args.source, args.metric, args.value, args.unit, args.year, args.entity,
        )
        return {"ok": True, "datum": _public_datum(datum)}
    if args.datum_command == "drop":
        result = _drop_datums(state, list(args.id), args.reason.strip())
        return {"ok": True, **result}
    return {"ok": True, "datums": [_public_datum(d) for d in _live_datums(state)]}


def run(args: argparse.Namespace) -> tuple[Any, int]:
    if not args.state:
        raise LedgerError(
            "No ledger path given. Set $DR_LEDGER (e.g. "
            "export DR_LEDGER=<workspace>/evidence-ledger.json) or pass "
            "--state <path>. The skill owns no default location."
        )
    path = Path(args.state)

    if args.command == "init":
        if path.exists() and not args.force:
            raise LedgerError(f"{path} already exists; pass --force to reset it")
        state = _empty_state()
        state["topic"] = args.topic
        state["genre"] = args.genre
        save_state(path, state)
        return {"ok": True, "state": str(path), "topic": state["topic"],
                "genre": state["genre"], "outline": []}, 0

    state = load_state(path)

    if args.command == "probe":
        probe = _add_probe(state, args)
        save_state(path, state)
        return {"ok": True, "probe": probe}, 0

    if args.command == "outline":
        payload = _run_outline(state, args)
        if args.outline_command != "show":
            save_state(path, state)
        return payload, 0

    if args.command == "add":
        payload = _read_payload(args)
        sections = _require_sections(state, args.section) if args.section else []
        probe = None
        if args.probe:
            probe = _probe_index(state).get(args.probe)
            if probe is None:
                raise LedgerError(
                    f"Unknown probe '{args.probe}'; register it with `evidence.py probe` first"
                )
        result = _add_sources(state, _items_from_payload(payload, args), args.via, sections, args.probe)
        wasted: list[dict[str, Any]] = []
        if args.aminer:
            _spend_from_aminer(state, payload)
            wasted = _paid_calls_without_hits(payload, args.kind)
        if probe is not None:
            probe["new"] += len(result["added"])
            probe["dup"] += len(result["duplicates"])
            probe["returned"] += len(result["added"]) + len(result["duplicates"])
        save_state(path, state)
        payload_out = {"ok": True, **result, "spend_total_cny": _spend_total(state)}
        if wasted:
            payload_out["paid_calls_without_hits"] = wasted
        return payload_out, 0

    if args.command == "claim":
        if args.batch:
            result = _add_claims_batch(state, _read_payload(args))
            save_state(path, state)
            return {"ok": not result["failed"], **result}, 0 if not result["failed"] else 1
        if not args.text or not args.section:
            raise LedgerError("A single claim needs --text and --section (or pass --batch)")
        claim = _add_claim(state, args)
        save_state(path, state)
        return {"ok": True, "claim": claim}, 0

    if args.command == "source":
        by_number = {source["n"]: source for source in state["sources"]}
        unknown = [n for n in args.source if n not in by_number]
        if unknown:
            raise LedgerError(f"Unknown source number(s): {', '.join(str(n) for n in unknown)}")
        shown = []
        for n in args.source:
            source = by_number[n]
            shown.append({
                key: source[key] for key in (
                    "n", "kind", "id", "title", "url", "year", "venue", "authors", "assignee",
                    "keywords", "abstract", "abstract_slice", "note", "depth", "sections",
                    "probes", "via", "dropped", "drop_reason",
                ) if key in source
            })
        return {"ok": True, "sources": shown}, 0

    if args.command == "spend":
        _record_spend(state, args.api, args.cny, args.calls)
        save_state(path, state)
        return {"ok": True, "spend": state["spend"], "total_cny": _spend_total(state)}, 0

    if args.command == "drop":
        result = _drop_sources(state, args.source, args.reason.strip())
        save_state(path, state)
        return {"ok": True, **result}, 0

    if args.command == "untag":
        result = _untag_sources(state, args.source, args.section)
        save_state(path, state)
        return {"ok": True, **result}, 0

    if args.command == "retract":
        result = _retract_claims(state, args.claim, args.reason.strip())
        save_state(path, state)
        return {"ok": True, **result}, 0

    if args.command == "figure":
        payload = _run_figure(state, args)
        if args.figure_command not in ("list",):
            save_state(path, state)
        return payload, 0

    if args.command == "datum":
        payload = _run_datum(state, args)
        if args.datum_command not in ("list",):
            save_state(path, state)
        return payload, 0

    if args.command == "stats":
        report = analyze(state)
        return {"ok": True, **report["totals"], "spend_total_cny": report["spend"]["total_cny"]}, 0

    if args.command == "gaps":
        return {"ok": True, **analyze(state)}, 0

    if args.command == "check":
        report = analyze(state)
        blocking = {
            "outline_missing": report["outline_missing"],
            "unsupported_claims": report["unsupported_claims"],
            "sections_below_two_sources": report["sections_below_two_sources"],
            "spend_over_hard_limit": report["spend_over_hard_limit"],
            "figures_with_no_sources": report["figures_with_no_sources"],
            "figures_in_unrendered_section": report["figures_in_unrendered_section"],
        }
        failed = (
            any(blocking.values())
            or report["totals"]["sources"] == 0
            or report["totals"]["claims"] == 0
        )
        return {
            "ok": not failed,
            "blocking": blocking,
            "warnings": {key: report[key] for key in (
                "subsections_below_two_sources",
                "sections_missing_disagreement",
                "sections_from_single_probe",
                "low_yield_probes",
                "drifting_probes",
                "sections_without_claims",
                "untagged_sources",
                "sources_without_probe",
                "cited_sources_without_detail",
                "single_source_claims",
                "claims_with_unsourced_numbers",
                "figures_unsupported_numbers",
                "figures_without_render",
                "figures_over_budget",
                "figures_industry_expected",
                "figures_industry_quantitative_expected",
                "figures_thin_data",
                "sections_over_figure_budget",
                "figure_code_divergence",
                "uncited_sources",
                "datums_without_source",
                "industry_web_sources_without_datums",
                "unresolved_conflicts",
            )},
            "totals": report["totals"],
            "spend": report["spend"],
        }, 1 if failed else 0

    if args.command == "render":
        if args.renumber:
            if args.final or args.appendix:
                raise LedgerError("--renumber cannot be combined with --final or --appendix")
            if not args.draft or not args.out:
                raise LedgerError("render --renumber needs --draft <path> and --out <path>")
            return _renumber_draft(state, Path(args.draft), Path(args.out), args.lang,
                                   ledger=path.as_posix()), 0
        if args.appendix:
            citation_map = None
            if args.citation_map:
                map_path = Path(args.citation_map)
                try:
                    citation_map = json.loads(map_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise LedgerError(f"Cannot read citation map {map_path}: {exc}") from None
                if not isinstance(citation_map.get("ledger_to_external"), dict):
                    raise LedgerError(
                        f"Citation map {map_path} carries no ledger_to_external table; "
                        "it is written by `render --renumber` next to the delivered report"
                    )
            markdown = _appendix_markdown(state, args.lang, citation_map)
            if not args.out:
                return markdown, 0
            # The appendices are bookkeeping, not reading matter: writing them
            # out keeps probe ids, endpoint names and CNY amounts off the page
            # the reader actually gets, and leaves one quotable line behind.
            out = path.with_name(f"{path.stem}-appendix.md") if args.out == "auto" else Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(markdown if markdown.endswith("\n") else markdown + "\n", encoding="utf-8")
            lab = _labels(state, args.lang)
            pointer_key = "pointer_with_map" if citation_map else "pointer"
            pointer = lab[pointer_key].format(path=out.as_posix())
            return {"ok": True, "path": out.as_posix(), "pointer": pointer}, 0
        return render_markdown(state, final=args.final, lang=args.lang), 0

    raise LedgerError(f"Unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        payload, code = run(parser.parse_args(argv))
    except LedgerError as exc:
        print(json.dumps({"ok": False, "error": "invalid_request", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    if isinstance(payload, str):
        print(payload, end="")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
