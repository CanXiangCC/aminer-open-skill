"""
Evidence field v2 — MSWR with hard filter, two-stage rerank, dynamic k, query quotas.
"""

from __future__ import annotations

import re
import time
from typing import Any

from experiments.rule_extraction.evidence.strategies import _mswr_common as common
from src.evaluation.semantic import SemanticScorer, jaccard_similarity

HARD_NOISE_PATTERNS = [
    re.compile(r"<table", re.I),
    re.compile(r"</table>", re.I),
    re.compile(r"</tr>", re.I),
    re.compile(r"<td", re.I),
    re.compile(r"^\s*TABLE\s+[IVXLC\d]+", re.I),
    re.compile(r"^\s*(Figure|Fig\.)\s+\d", re.I),
    re.compile(r"^\s*Index Terms", re.I),
    re.compile(r"^\[\d+\]\s"),
    re.compile(r"\bet al\.\s*,", re.I),
    re.compile(r"\b(In|Proc\.|Proceedings of|CVPR|ICCV|NeurIPS|WACV)\b.*\d{4}", re.I),
    re.compile(r"^\s*http[s]?://", re.I),
    re.compile(r"^\s*\|\s*Method\s*\|", re.I),
]

QUERY_QUOTAS = {"result": 3, "method": 2, "anchor": 1}


def compute_k(experiment: dict, *, fixed_k: int | None = None) -> int:
    if fixed_k is not None:
        return fixed_k
    n_kr = len(experiment.get("key_results") or [])
    return min(8, max(3, n_kr + 1))


class EvidenceRuleV2:
    STRATEGY_ID = "evidence--策略v2--field_backtrace_mswr_rerank"
    RERANK_POOL = 20

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
        sections = common.parse_sections(md_text)
        candidates, filter_trace = cls._build_candidate_pool(md_text)
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
                filter_trace=filter_trace,
            )
            out["evidence"] = evidence
            out["evidence_trace"] = trace
            results.append(out)

        total_ms = round((time.perf_counter() - t0) * 1000, 2)
        for r in results:
            r["evidence_trace"]["paper_extract_ms"] = total_ms
        return results

    @classmethod
    def _is_hard_noise(cls, sent: str) -> bool:
        stripped = sent.strip()
        for pat in HARD_NOISE_PATTERNS:
            if pat.search(stripped):
                return True
        return False

    @classmethod
    def _numeric_anchor(cls, query: str, sentence: str) -> float:
        if cls._is_hard_noise(sentence) or "<table" in sentence.lower():
            return 0.0
        return common.numeric_anchor(query, sentence)

    @classmethod
    def _build_candidate_pool(cls, md_text: str) -> tuple[list[str], dict[str, Any]]:
        sentences = common.split_all_sentences(md_text)
        pool: list[str] = []
        seen: set[str] = set()
        hard_dropped: list[str] = []
        noise_count = 0

        for sent in sentences:
            if common.is_noise_sentence(sent) or cls._is_hard_noise(sent):
                noise_count += 1
                if cls._is_hard_noise(sent) and len(hard_dropped) < 5:
                    hard_dropped.append(sent[:120])
                continue
            from src.evaluation.semantic import normalize_text
            key = normalize_text(sent)
            if key and key not in seen:
                seen.add(key)
                pool.append(sent)

        trace = {
            "raw_sentence_count": len(sentences),
            "filtered_candidate_count": len(pool),
            "noise_dropped": noise_count,
            "hard_noise_dropped": hard_dropped,
        }
        return pool, trace

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
        filter_trace: dict[str, Any],
    ) -> tuple[list[str], dict[str, Any]]:
        t0 = time.perf_counter()
        queries = common.build_queries(experiment)
        dropped_non_verbatim = 0

        query_bests: list[dict[str, Any]] = []
        for q in queries:
            scored: list[dict[str, Any]] = []
            for sent in candidates:
                sc = common.cheap_score(
                    sent, q, md_text, experiment, sections, single_exp,
                    numeric_fn=cls._numeric_anchor,
                )
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

        for cand in query_bests:
            if len(selected) >= k_dynamic:
                break
            qtype = cand["query_type"]
            if quota_used.get(qtype, 0) >= QUERY_QUOTAS.get(qtype, 1):
                continue
            sent = cand["sentence"]
            if any(jaccard_similarity(sent, prev) > 0.85 for prev in selected_texts):
                continue
            if not common.is_verbatim(sent, md_text):
                dropped_non_verbatim += 1
                continue
            selected.append({
                "sentence": sent,
                "score": cand["final_score"],
                "cheap_score": cand["cheap_score"],
                "emb_sim": cand["emb_sim"],
                "final_score": cand["final_score"],
                "query_type": qtype,
                "query_preview": cand["query_preview"],
                "scope": cand["scope"],
                "jaccard": cand["jaccard"],
                "numeric_anchor": cand["numeric_anchor"],
                "substring_boost": cand["substring_boost"],
                "rerank_pool_size": cand["rerank_pool_size"],
                "verbatim_ok": True,
            })
            selected_texts.append(sent)
            quota_used[qtype] = quota_used.get(qtype, 0) + 1

        extract_ms = round((time.perf_counter() - t0) * 1000, 2)
        trace = {
            "strategy": cls.STRATEGY_ID,
            "input_mode": input_mode,
            "query_count": len(queries),
            "candidate_count": len(candidates),
            "filtered_candidate_count": filter_trace.get("filtered_candidate_count"),
            "hard_noise_dropped": filter_trace.get("hard_noise_dropped"),
            "k_dynamic": k_dynamic,
            "fixed_k": fixed_k,
            "use_embedding": use_embedding,
            "quota_used": quota_used,
            "selected": selected,
            "dropped_non_verbatim": dropped_non_verbatim,
            "extract_ms": extract_ms,
        }
        return [s["sentence"] for s in selected], trace
