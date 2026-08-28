"""
Evidence field v3 — v1 MSWR + two-stage rerank + dynamic k + query quotas + v1 fill pass.

No v2 hard filter. Candidate pool and cheap scoring identical to v1.
"""

from __future__ import annotations

import difflib
import re
import time
from typing import Any

from experiments.rule_extraction.shared.dataset_preprocess import _parse_sections
from src.evaluation.semantic import SemanticScorer, jaccard_similarity, normalize_text

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "with",
    "by", "from", "at", "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those", "we", "our", "their", "its", "as",
    "using", "based", "via", "over", "under", "between", "among",
})

_NOISE_PATTERNS = [
    re.compile(r"^\s*future\s+work\b", re.I),
    re.compile(r"^\s*in\s+future\s+work\b", re.I),
    re.compile(r"^\[\d+\]\s*$"),
    re.compile(r"^[\[\(]?\d+[\]\)]?\s+et\s+al", re.I),
]

_NUMERIC_RE = re.compile(r"\d+\.?\d*")

QUERY_QUOTAS = {"result": 3, "method": 2, "anchor": 1}


def compute_k(experiment: dict, *, fixed_k: int | None = None) -> int:
    if fixed_k is not None:
        return fixed_k
    n_kr = len(experiment.get("key_results") or [])
    return min(8, max(3, n_kr + 1))


class EvidenceRuleV3:
    STRATEGY_ID = "evidence--策略v3--field_backtrace_mswr_rerank_dynamic"
    RERANK_POOL = 20
    DEFAULT_K = 5

    @classmethod
    def extract_for_paper(
        cls,
        md_text: str,
        experiments: list[dict],
        *,
        k: int | None = None,
        input_mode: str = "full_text",
        fixed_k: int | None = None,
        use_embedding: bool = False,
    ) -> list[dict]:
        t0 = time.perf_counter()
        single_exp = len(experiments) == 1
        sections = _parse_sections(md_text)
        candidates = cls._build_candidate_pool(md_text)
        scorer = SemanticScorer(
            type="embedding" if use_embedding else "jaccard",
            device="cpu" if use_embedding else None,
        )

        results: list[dict] = []
        for exp in experiments:
            k_dynamic = compute_k(exp, fixed_k=fixed_k if fixed_k is not None else k)
            out = dict(exp)
            evidence, trace = cls._extract_one(
                md_text,
                exp,
                candidates,
                sections,
                k_dynamic=k_dynamic,
                input_mode=input_mode,
                single_exp=single_exp,
                scorer=scorer,
                use_embedding=use_embedding,
                fixed_k=fixed_k if fixed_k is not None else k,
            )
            out["evidence"] = evidence
            out["evidence_trace"] = trace
            results.append(out)

        total_ms = round((time.perf_counter() - t0) * 1000, 2)
        for r in results:
            r["evidence_trace"]["paper_extract_ms"] = total_ms
        return results

    @classmethod
    def _extract_one(
        cls,
        md_text: str,
        experiment: dict,
        candidates: list[str],
        sections: list[dict[str, Any]],
        *,
        k_dynamic: int,
        input_mode: str,
        single_exp: bool,
        scorer: SemanticScorer,
        use_embedding: bool,
        fixed_k: int | None,
    ) -> tuple[list[str], dict[str, Any]]:
        t0 = time.perf_counter()
        queries = cls._build_queries(experiment)
        dropped_non_verbatim = 0

        query_bests: list[dict[str, Any]] = []
        for q in queries:
            scored: list[dict[str, Any]] = []
            for sent in candidates:
                sc = cls._score_sentence(sent, q, md_text, experiment, sections, single_exp)
                scored.append({"sentence": sent, **sc})

            scored.sort(key=lambda x: x["total"], reverse=True)
            pool = scored[: cls.RERANK_POOL]
            if not pool:
                continue

            max_cheap = max(p["total"] for p in pool) or 1.0
            best: dict[str, Any] | None = None
            best_final = -1.0

            for item in pool:
                cheap_norm = item["total"] / max_cheap if max_cheap > 0 else 0.0
                emb_sim = scorer.similarity(q["text"], item["sentence"])
                final_score = 0.40 * cheap_norm + 0.60 * emb_sim
                if final_score > best_final:
                    best_final = final_score
                    best = {
                        "sentence": item["sentence"],
                        "cheap_score": round(item["total"], 4),
                        "cheap_score_normalized": round(cheap_norm, 4),
                        "emb_sim": round(emb_sim, 4),
                        "final_score": round(final_score, 4),
                        "scope": item["scope"],
                        "jaccard": round(item["jaccard"], 4),
                        "numeric_anchor": round(item["numeric_anchor"], 4),
                        "substring_boost": round(item["substring_boost"], 4),
                        "query_type": q["type"],
                        "query_preview": q["text"][:80],
                        "rerank_pool_size": len(pool),
                    }

            if best and best_final > 0:
                query_bests.append(best)

        query_bests.sort(key=lambda x: x["final_score"], reverse=True)

        quota_used: dict[str, int] = {"result": 0, "method": 0, "anchor": 0}
        selected: list[dict[str, Any]] = []
        selected_texts: list[str] = []

        def _append_selected(cand: dict[str, Any], *, from_fill: bool = False) -> bool:
            nonlocal dropped_non_verbatim
            sent = cand["sentence"]
            if any(jaccard_similarity(sent, prev) > 0.85 for prev in selected_texts):
                return False
            if not cls._is_verbatim(sent, md_text):
                dropped_non_verbatim += 1
                return False
            entry: dict[str, Any] = {
                "sentence": sent,
                "score": cand.get("final_score", cand.get("total", 0)),
                "query_type": cand["query_type"],
                "query_preview": cand["query_preview"],
                "scope": cand["scope"],
                "jaccard": cand["jaccard"],
                "numeric_anchor": cand["numeric_anchor"],
                "substring_boost": cand["substring_boost"],
                "verbatim_ok": True,
                "from_fill_pass": from_fill,
            }
            if "cheap_score" in cand:
                entry.update({
                    "cheap_score": cand["cheap_score"],
                    "cheap_score_normalized": cand.get("cheap_score_normalized"),
                    "emb_sim": cand.get("emb_sim"),
                    "final_score": cand.get("final_score"),
                    "rerank_pool_size": cand.get("rerank_pool_size"),
                })
            selected.append(entry)
            selected_texts.append(sent)
            return True

        for cand in query_bests:
            if len(selected) >= k_dynamic:
                break
            qtype = cand["query_type"]
            if quota_used.get(qtype, 0) >= QUERY_QUOTAS.get(qtype, 1):
                continue
            if _append_selected(cand):
                quota_used[qtype] = quota_used.get(qtype, 0) + 1

        if len(selected) < k_dynamic:
            all_scored: list[dict[str, Any]] = []
            for q in queries:
                for sent in candidates:
                    sc = cls._score_sentence(sent, q, md_text, experiment, sections, single_exp)
                    all_scored.append({
                        "sentence": sent,
                        **sc,
                        "query_type": q["type"],
                        "query_preview": q["text"][:80],
                    })
            all_scored.sort(key=lambda x: x["total"], reverse=True)
            seen_sents = {s["sentence"] for s in selected}
            for cand in all_scored:
                if len(selected) >= k_dynamic:
                    break
                if cand["sentence"] in seen_sents:
                    continue
                if _append_selected(cand, from_fill=True):
                    seen_sents.add(cand["sentence"])

        extract_ms = round((time.perf_counter() - t0) * 1000, 2)
        trace = {
            "strategy": cls.STRATEGY_ID,
            "input_mode": input_mode,
            "query_count": len(queries),
            "candidate_count": len(candidates),
            "k_dynamic": k_dynamic,
            "fixed_k": fixed_k,
            "use_embedding": use_embedding,
            "quota_used": quota_used,
            "selected": selected,
            "dropped_non_verbatim": dropped_non_verbatim,
            "extract_ms": extract_ms,
        }
        return [s["sentence"] for s in selected], trace

    @classmethod
    def _build_candidate_pool(cls, md_text: str) -> list[str]:
        sentences = cls._split_all_sentences(md_text)
        pool: list[str] = []
        seen: set[str] = set()
        for sent in sentences:
            if cls._is_noise_sentence(sent):
                continue
            key = normalize_text(sent)
            if key and key not in seen:
                seen.add(key)
                pool.append(sent)
        return pool

    @classmethod
    def _split_all_sentences(cls, text: str) -> list[str]:
        abbreviations = [
            r"Dr\.", r"Mr\.", r"Mrs\.", r"Ms\.", r"Prof\.",
            r"Ph\.D\.", r"Ph\.D", r"M\.D\.", r"B\.S\.",
            r"U\.S\.", r"U\.K\.", r"e\.g\.", r"i\.e\.",
            r"Fig\.", r"Sec\.", r"Eq\.", r"vs\.",
            r"et al\.", r"etc\.",
        ]
        protected = text
        for i, abbr in enumerate(abbreviations):
            protected = re.sub(abbr, f"@@ABBR{i}@@@@", protected, flags=re.IGNORECASE)
        sentences = re.split(r"(?<=[.!?])\s+", protected)
        sentences = [re.sub(r"@@ABBR\d+@@@@", ".", s) for s in sentences]
        return [s.strip() for s in sentences if s.strip()]

    @classmethod
    def _is_noise_sentence(cls, sent: str) -> bool:
        if len(sent) < 20 or len(sent) > 500:
            return True
        if sent.lstrip().startswith("#"):
            return True
        stripped = sent.strip()
        if stripped.startswith("|") and stripped.count("|") >= 2:
            return True
        pipe_ratio = stripped.count("|") / max(len(stripped), 1)
        if pipe_ratio > 0.3:
            return True
        for pat in _NOISE_PATTERNS:
            if pat.search(stripped):
                return True
        return False

    @classmethod
    def _build_queries(cls, experiment: dict) -> list[dict[str, Any]]:
        queries: list[dict[str, Any]] = []
        for kr in experiment.get("key_results") or []:
            if kr and str(kr).strip():
                queries.append({"text": str(kr).strip(), "weight": 1.0, "type": "result"})
        for sent in cls._split_method_sentences(experiment.get("method") or "")[:2]:
            queries.append({"text": sent, "weight": 0.7, "type": "method"})
        name_tokens = cls._significant_tokens(experiment.get("experiment_name") or "")
        if name_tokens:
            queries.append({"text": " ".join(name_tokens), "weight": 0.4, "type": "anchor"})
        return queries

    @classmethod
    def _split_method_sentences(cls, method: str) -> list[str]:
        return cls._split_all_sentences(method)

    @classmethod
    def _significant_tokens(cls, name: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z0-9]{4,}", name.lower())
        return [t for t in tokens if t not in _STOPWORDS]

    @classmethod
    def _score_sentence(
        cls,
        sentence: str,
        query: dict[str, Any],
        md_text: str,
        experiment: dict,
        sections: list[dict[str, Any]],
        single_exp: bool,
    ) -> dict[str, float]:
        q_text = query["text"]
        scope = cls._scope(sentence, md_text, experiment, sections, single_exp)
        jac = jaccard_similarity(q_text, sentence)
        num = cls._numeric_anchor(q_text, sentence)
        sub = cls._substring_boost(q_text, sentence)
        base = 0.55 * jac + 0.25 * num + 0.20 * sub
        total = scope * base * query["weight"]
        return {
            "total": total,
            "scope": scope,
            "jaccard": jac,
            "numeric_anchor": num,
            "substring_boost": sub,
        }

    @classmethod
    def _scope(
        cls,
        sentence: str,
        md_text: str,
        experiment: dict,
        sections: list[dict[str, Any]],
        single_exp: bool,
    ) -> float:
        if single_exp:
            return 1.0
        if not sections:
            return 0.3

        sent_pos = md_text.find(sentence)
        if sent_pos < 0:
            sent_pos = 0

        sent_section_idx = cls._section_for_pos(sections, sent_pos)
        if sent_section_idx is None:
            return 0.3

        sec = sections[sent_section_idx]
        section_text = (sec.get("title") or "") + " " + (sec.get("content") or "")
        section_lower = section_text.lower()

        name_tokens = cls._significant_tokens(experiment.get("experiment_name") or "")
        if name_tokens and any(t in section_lower for t in name_tokens):
            return 1.0

        method_sents = cls._split_method_sentences(experiment.get("method") or "")
        if method_sents:
            method_pos = md_text.find(method_sents[0][:40])
            if method_pos >= 0:
                method_sec_idx = cls._section_for_pos(sections, method_pos)
                if method_sec_idx == sent_section_idx:
                    return 0.6

        return 0.3

    @classmethod
    def _section_for_pos(cls, sections: list[dict[str, Any]], pos: int) -> int | None:
        for i, sec in enumerate(sections):
            if sec["start"] <= pos < sec["end"]:
                return i
        return None

    @classmethod
    def _numeric_anchor(cls, query: str, sentence: str) -> float:
        q_nums = _NUMERIC_RE.findall(query)
        if not q_nums:
            return 0.5
        s_text = sentence
        matched = sum(1 for n in q_nums if n in s_text)
        if matched == len(q_nums):
            return 1.0
        if matched > 0:
            return 0.5
        return 0.0

    @classmethod
    def _substring_boost(cls, query: str, sentence: str) -> float:
        tokens = [t for t in re.findall(r"[a-zA-Z0-9]{4,}", query.lower()) if t not in _STOPWORDS]
        if tokens:
            hit_ratio = sum(1 for t in tokens if t in sentence.lower()) / len(tokens)
            return hit_ratio
        return difflib.SequenceMatcher(None, query.lower(), sentence.lower()).ratio()

    @classmethod
    def _is_verbatim(cls, sentence: str, md_text: str) -> bool:
        if sentence.strip() in md_text:
            return True
        norm_s = normalize_text(sentence)
        norm_md = normalize_text(md_text)
        return bool(norm_s and norm_s in norm_md)
