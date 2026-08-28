"""
Evidence extraction evaluation: benchmark (gold recall) + product quality metrics.

Product success criteria (engineering): low noise, high relevance, traceable, human acceptable.
Gold recall metrics remain for regression only.
"""

from __future__ import annotations

import re
from typing import Any

from experiments.rule_extraction.evidence.strategies._mswr_common import (
    is_noise_sentence,
    split_all_sentences,
)
from src.evaluation.semantic import SemanticScorer, jaccard_similarity, normalize_text

DEFAULT_K = 5
JACCARD_MATCH_THRESHOLD = 0.5
SEMANTIC_THRESHOLD = 0.85
RELEVANCE_HIT_THRESHOLD = 0.25

# Product-track automated gates (dev_10); human_acceptable is manual.
PRODUCT_THRESHOLDS = {
    "noise_rate_max": 0.15,
    "relevance_mean_min": 0.20,
    "traceable_rate_min": 0.95,
}

_PRODUCT_NOISE_PATTERNS = [
    re.compile(r"<table", re.I),
    re.compile(r"</tr>", re.I),
    re.compile(r"<td\b", re.I),
    re.compile(r"^\s*TABLE\s+[IVXLC\d]+", re.I),
    re.compile(r"^\s*(Figure|Fig\.)\s+\d", re.I),
    re.compile(r"^\s*Index Terms", re.I),
    re.compile(r"^\[\d+\]\s"),
    re.compile(r"^\s*http[s]?://", re.I),
    re.compile(r"\bhttps?://\S+", re.I),
    re.compile(r"^\s*In\s+(WACV|CVPR|ICCV|NeurIPS|Proc\.|Proceedings)", re.I),
    re.compile(r"pages\s+\d+\s*[–\-]\s*\d+", re.I),
    re.compile(r"\bet al\.\s*,", re.I),
    re.compile(r"^\s*\|\s*Method\s*\|", re.I),
    re.compile(r"\$\s*\d+\s+\.\s*$"),
    # v4.1: Spaced-digit OCR
    re.compile(r"(?:\d|\$|\.)\s+\d\s+\."),
    # v4.1: Image caption patterns
    re.compile(r"^A (?:sampling|sample|set|collection) of (?:images|figures|visuals)", re.I),
    re.compile(r"!\[.*\]\(.*(?:images|img|figures?|figs?)/", re.I),
]

MULTI_EXPERIMENT_PAPER_IDS_DEV_20 = [
    "628304515aee126c0f6f0e05",
    "659e2146939a5f4082894306",
    "661ddba813fb2c6cf6b5d7e6",
    "6632f3d201d2a3fbfc5b36bb",
    "66bac1ca01d2a3fbfcd435ac",
]

BUCKET_NAMES = ("single_experiment", "multi_experiment", "survey", "cross_lingual_query")


def is_noise_pred_sentence(sentence: str) -> bool:
    """Product metric: bib/HTML/table/citation/URL fragments unsuitable as evidence."""
    if not sentence or not sentence.strip():
        return True
    stripped = sentence.strip()
    if is_noise_sentence(stripped):
        return True
    for pat in _PRODUCT_NOISE_PATTERNS:
        if pat.search(stripped):
            return True
    return False


def _query_texts_from_experiment(experiment: dict) -> list[str]:
    texts: list[str] = []
    for kr in experiment.get("key_results") or []:
        if kr and str(kr).strip():
            texts.append(str(kr).strip())
    for sent in split_all_sentences(experiment.get("method") or "")[:2]:
        if sent.strip():
            texts.append(sent.strip())
    return texts


def relevance_score_for_sentence(sentence: str, query_texts: list[str]) -> float:
    if not sentence or not query_texts:
        return 0.0
    return max(jaccard_similarity(sentence, q) for q in query_texts)


def evaluate_experiment_product(
    experiment: dict,
    pred_evidence: list[str],
    md_text: str,
) -> dict[str, Any]:
    """Product-track metrics for one experiment (no gold required)."""
    pred = [str(p).strip() for p in (pred_evidence or []) if p]
    queries = _query_texts_from_experiment(experiment)

    noise_count = sum(1 for p in pred if is_noise_pred_sentence(p))
    traceable_count = sum(1 for p in pred if is_verbatim_in_md(p, md_text))
    rel_scores = [relevance_score_for_sentence(p, queries) for p in pred]

    noise_rate = noise_count / len(pred) if pred else 0.0
    traceable_rate = traceable_count / len(pred) if pred else 1.0
    relevance_mean = sum(rel_scores) / len(rel_scores) if rel_scores else 0.0
    relevance_hit_rate = (
        sum(1 for s in rel_scores if s >= RELEVANCE_HIT_THRESHOLD) / len(rel_scores)
        if rel_scores
        else 0.0
    )

    gates = check_product_gates({
        "noise_rate": noise_rate,
        "relevance_mean": relevance_mean,
        "traceable_rate": traceable_rate,
    })

    return {
        "pred_count": len(pred),
        "noise_count": noise_count,
        "noise_rate": noise_rate,
        "traceable_count": traceable_count,
        "traceable_rate": traceable_rate,
        "relevance_mean": relevance_mean,
        "relevance_min": min(rel_scores) if rel_scores else 0.0,
        "relevance_hit_rate": relevance_hit_rate,
        "product_pass": gates["pass"],
        "product_gates": gates,
    }


def check_product_gates(metrics: dict[str, float]) -> dict[str, Any]:
    """Automated product gates; human_acceptable is documented separately."""
    checks = {
        "low_noise": metrics.get("noise_rate", 1.0) <= PRODUCT_THRESHOLDS["noise_rate_max"],
        "high_relevance": metrics.get("relevance_mean", 0.0) >= PRODUCT_THRESHOLDS["relevance_mean_min"],
        "traceable": metrics.get("traceable_rate", 0.0) >= PRODUCT_THRESHOLDS["traceable_rate_min"],
    }
    return {
        "pass": all(checks.values()),
        "checks": checks,
        "thresholds": dict(PRODUCT_THRESHOLDS),
        "human_acceptable": None,
    }


def is_verbatim_in_md(sentence: str, md_text: str) -> bool:
    if not sentence or not md_text:
        return False
    if sentence.strip() in md_text:
        return True
    norm_s = normalize_text(sentence)
    norm_md = normalize_text(md_text)
    return bool(norm_s and norm_s in norm_md)


def _is_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def paper_is_cross_lingual(experiments: list[dict]) -> bool:
    for exp in experiments:
        for kr in exp.get("key_results") or []:
            if kr and _is_cjk(str(kr)):
                return True
    return False


def classify_paper_buckets(
    paper_id: str,
    gold_experiments: list[dict],
) -> set[str]:
    """Return bucket tags for a paper."""
    buckets: set[str] = set()
    if len(gold_experiments) == 1:
        buckets.add("single_experiment")
    if len(gold_experiments) >= 2:
        buckets.add("multi_experiment")
    if any((exp.get("experiment_type") or "") == "survey" for exp in gold_experiments):
        buckets.add("survey")
    if paper_is_cross_lingual(gold_experiments):
        buckets.add("cross_lingual_query")
    return buckets


def _fuzzy_match(a: str, b: str) -> bool:
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if shorter in longer and len(shorter) / len(longer) >= 0.5:
        return True
    return False


def _match_fn(a: str, b: str) -> bool:
    if normalize_text(a) == normalize_text(b):
        return True
    if _fuzzy_match(a, b):
        return True
    if jaccard_similarity(a, b) >= JACCARD_MATCH_THRESHOLD:
        return True
    return False


def _semantic_match(a: str, b: str, scorer: SemanticScorer | None) -> bool:
    if _match_fn(a, b):
        return True
    if scorer and scorer.similarity(a, b) >= SEMANTIC_THRESHOLD:
        return True
    return False


def _greedy_match(
    gold_sents: list[str],
    pred_sents: list[str],
    match_fn,
) -> tuple[list[dict[str, Any]], set[int], set[int]]:
    pairs: list[dict[str, Any]] = []
    used_pred: set[int] = set()
    matched_gold: set[int] = set()

    for gi, g in enumerate(gold_sents):
        best_pi = -1
        best_score = 0.0
        for pi, p in enumerate(pred_sents):
            if pi in used_pred:
                continue
            if match_fn(g, p):
                score = jaccard_similarity(g, p)
                if score > best_score:
                    best_score = score
                    best_pi = pi
        if best_pi >= 0:
            pairs.append({
                "gold": gold_sents[gi],
                "pred": pred_sents[best_pi],
                "score": round(best_score, 4),
            })
            used_pred.add(best_pi)
            matched_gold.add(gi)

    return pairs, matched_gold, used_pred


def _prf(tp: float, gold_count: int, pred_count: int) -> dict[str, float]:
    precision = tp / pred_count if pred_count else 0.0
    recall = tp / gold_count if gold_count else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def evaluate_experiment_evidence(
    gold_evidence: list[str],
    pred_evidence: list[str],
    md_text: str,
    *,
    experiment: dict | None = None,
    k: int | None = DEFAULT_K,
    semantic_scorer: SemanticScorer | None = None,
) -> dict[str, Any]:
    """Evaluate one experiment's evidence list."""
    gold = [str(g).strip() for g in (gold_evidence or []) if g]
    raw_pred = [str(p).strip() for p in (pred_evidence or []) if p]
    if k is None:
        pred = raw_pred
    else:
        pred = raw_pred[:k]

    k_used = len(pred)

    gold_v = [g for g in gold if is_verbatim_in_md(g, md_text)]
    gold_non_v = len(gold) - len(gold_v)

    verbatim_ok = sum(1 for p in pred if is_verbatim_in_md(p, md_text))
    verbatim_rate = verbatim_ok / len(pred) if pred else 1.0

    pairs, _, _ = _greedy_match(gold, pred, _match_fn)
    tp = float(len(pairs))
    prf = _prf(tp, len(gold), len(pred))

    sem_pairs, _, _ = _greedy_match(
        gold,
        pred,
        lambda g, p: _semantic_match(g, p, semantic_scorer),
    )
    sem_tp = float(len(sem_pairs))
    sem_prf = _prf(sem_tp, len(gold), len(pred))

    # Verbatim gold subset
    v_pairs, _, _ = _greedy_match(gold_v, pred, _match_fn)
    v_tp = float(len(v_pairs))
    v_prf = _prf(v_tp, len(gold_v), len(pred))

    v_sem_pairs, _, _ = _greedy_match(
        gold_v,
        pred,
        lambda g, p: _semantic_match(g, p, semantic_scorer),
    )
    v_sem_tp = float(len(v_sem_pairs))
    v_sem_prf = _prf(v_sem_tp, len(gold_v), len(pred))

    recall_ceiling_at_k = min(k_used, len(gold)) / len(gold) if gold else 0.0
    semantic_recall_normalized = (
        sem_prf["recall"] / recall_ceiling_at_k if recall_ceiling_at_k > 0 else 0.0
    )

    result: dict[str, Any] = {
        "gold_count": len(gold),
        "pred_count": len(pred),
        "k_used": k_used,
        "gold_verbatim_count": len(gold_v),
        "gold_non_verbatim_count": gold_non_v,
        "verbatim_rate": verbatim_rate,
        "traceable_rate": verbatim_rate,
        "verbatim_ok": verbatim_ok,
        "recall_at_k": prf["recall"],
        "precision_at_k": prf["precision"],
        "micro_f1_at_k": prf["f1"],
        "semantic_recall_at_k": sem_prf["recall"],
        "semantic_recall_at_k_all_gold": sem_prf["recall"],
        "semantic_precision_at_k": sem_prf["precision"],
        "semantic_f1_at_k": sem_prf["f1"],
        "recall_at_k_verbatim_gold": v_prf["recall"],
        "precision_at_k_verbatim_gold": v_prf["precision"],
        "micro_f1_at_k_verbatim_gold": v_prf["f1"],
        "semantic_recall_at_k_verbatim_gold": v_sem_prf["recall"],
        "semantic_precision_at_k_verbatim_gold": v_sem_prf["precision"],
        "semantic_f1_at_k_verbatim_gold": v_sem_prf["f1"],
        "recall_ceiling_at_k": recall_ceiling_at_k,
        "semantic_recall_normalized": semantic_recall_normalized,
        "match_pairs": pairs,
        "semantic_match_pairs": sem_pairs,
        "verbatim_gold_match_pairs": v_pairs,
        "verbatim_gold_semantic_match_pairs": v_sem_pairs,
    }
    if experiment is not None:
        product = evaluate_experiment_product(experiment, raw_pred, md_text)
        result.update(product)
    return result


def evaluate_paper_evidence(
    gold_experiments: list[dict],
    pred_experiments: list[dict],
    md_text: str,
    *,
    k: int | None = DEFAULT_K,
    semantic_scorer: SemanticScorer | None = None,
) -> dict[str, Any]:
    """Evaluate all experiments in one paper (aligned by index)."""
    exp_evals: list[dict[str, Any]] = []
    n = min(len(gold_experiments), len(pred_experiments))
    for i in range(n):
        gold_ev = gold_experiments[i].get("evidence") or []
        pred_ev = pred_experiments[i].get("evidence") or []
        ev = evaluate_experiment_evidence(
            gold_ev,
            pred_ev,
            md_text,
            experiment=gold_experiments[i],
            k=k,
            semantic_scorer=semantic_scorer,
        )
        ev["experiment_name"] = gold_experiments[i].get("experiment_name") or f"exp_{i}"
        exp_evals.append(ev)
    return {"experiments": exp_evals}


def _empty_aggregate() -> dict[str, Any]:
    return {
        "experiment_count": 0,
        "gold_count": 0,
        "gold_verbatim_count": 0,
        "gold_non_verbatim_count": 0,
        "pred_count": 0,
        "verbatim_rate": 0.0,
        "traceable_rate": 0.0,
        "noise_rate": 0.0,
        "relevance_mean": 0.0,
        "relevance_hit_rate": 0.0,
        "recall_at_k": 0.0,
        "precision_at_k": 0.0,
        "micro_f1_at_k": 0.0,
        "semantic_recall_at_k": 0.0,
        "semantic_recall_at_k_all_gold": 0.0,
        "semantic_recall_at_k_verbatim_gold": 0.0,
        "recall_at_k_verbatim_gold": 0.0,
        "semantic_recall_normalized": 0.0,
        "product_pass": False,
    }


def aggregate_experiment_evals(
    exp_evals: list[dict[str, Any]],
) -> dict[str, Any]:
    """Micro-aggregate across experiments."""
    if not exp_evals:
        return _empty_aggregate()

    total_gold = sum(e["gold_count"] for e in exp_evals)
    total_gold_v = sum(e.get("gold_verbatim_count", 0) for e in exp_evals)
    total_gold_nv = sum(e.get("gold_non_verbatim_count", 0) for e in exp_evals)
    total_pred = sum(e["pred_count"] for e in exp_evals)
    total_matched = sum(len(e.get("match_pairs") or []) for e in exp_evals)
    total_sem_matched = sum(len(e.get("semantic_match_pairs") or []) for e in exp_evals)
    total_v_matched = sum(len(e.get("verbatim_gold_match_pairs") or []) for e in exp_evals)
    total_v_sem_matched = sum(len(e.get("verbatim_gold_semantic_match_pairs") or []) for e in exp_evals)
    total_verbatim = sum(e.get("verbatim_ok", 0) for e in exp_evals)

    prf = _prf(float(total_matched), total_gold, total_pred)
    sem_prf = _prf(float(total_sem_matched), total_gold, total_pred)
    v_prf = _prf(float(total_v_matched), total_gold_v, total_pred)
    v_sem_prf = _prf(float(total_v_sem_matched), total_gold_v, total_pred)

    # Weighted mean of per-experiment normalized recall
    norm_weighted = 0.0
    norm_denom = 0
    for e in exp_evals:
        gc = e.get("gold_count", 0)
        if gc > 0:
            norm_weighted += e.get("semantic_recall_normalized", 0) * gc
            norm_denom += gc
    semantic_recall_normalized = norm_weighted / norm_denom if norm_denom else 0.0

    total_noise = sum(e.get("noise_count", 0) for e in exp_evals)
    rel_weighted = 0.0
    rel_denom = 0
    hit_weighted = 0.0
    for e in exp_evals:
        pc = e.get("pred_count", 0)
        if pc > 0:
            rel_weighted += e.get("relevance_mean", 0.0) * pc
            hit_weighted += e.get("relevance_hit_rate", 0.0) * pc
            rel_denom += pc
    noise_rate = total_noise / total_pred if total_pred else 0.0
    traceable_rate = total_verbatim / total_pred if total_pred else 1.0
    relevance_mean = rel_weighted / rel_denom if rel_denom else 0.0
    relevance_hit_rate = hit_weighted / rel_denom if rel_denom else 0.0
    product_gates = check_product_gates({
        "noise_rate": noise_rate,
        "relevance_mean": relevance_mean,
        "traceable_rate": traceable_rate,
    })

    return {
        "experiment_count": len(exp_evals),
        "gold_count": total_gold,
        "gold_verbatim_count": total_gold_v,
        "gold_non_verbatim_count": total_gold_nv,
        "pred_count": total_pred,
        "verbatim_rate": traceable_rate,
        "traceable_rate": traceable_rate,
        "noise_rate": noise_rate,
        "noise_count": total_noise,
        "relevance_mean": relevance_mean,
        "relevance_hit_rate": relevance_hit_rate,
        "recall_at_k": prf["recall"],
        "precision_at_k": prf["precision"],
        "micro_f1_at_k": prf["f1"],
        "semantic_recall_at_k": sem_prf["recall"],
        "semantic_recall_at_k_all_gold": sem_prf["recall"],
        "semantic_precision_at_k": sem_prf["precision"],
        "semantic_f1_at_k": sem_prf["f1"],
        "recall_at_k_verbatim_gold": v_prf["recall"],
        "semantic_recall_at_k_verbatim_gold": v_sem_prf["recall"],
        "semantic_precision_at_k_verbatim_gold": v_sem_prf["precision"],
        "semantic_f1_at_k_verbatim_gold": v_sem_prf["f1"],
        "semantic_recall_normalized": semantic_recall_normalized,
        "product_pass": product_gates["pass"],
        "product_gates": product_gates,
    }


def aggregate_paper_evals(
    paper_evals: list[dict[str, Any]],
    *,
    multi_paper_ids: set[str] | None = None,
    gold_by_paper: dict[str, list[dict]] | None = None,
) -> dict[str, Any]:
    """Aggregate across papers; optional multi-experiment subset and buckets."""
    all_exp: list[dict[str, Any]] = []
    multi_exp: list[dict[str, Any]] = []
    bucket_exps: dict[str, list[dict[str, Any]]] = {b: [] for b in BUCKET_NAMES}

    for pe in paper_evals:
        paper_id = pe.get("paper_id", "")
        exps = pe.get("experiments") or []
        for exp_ev in exps:
            all_exp.append(exp_ev)
            if multi_paper_ids and paper_id in multi_paper_ids:
                multi_exp.append(exp_ev)

        if gold_by_paper and paper_id in gold_by_paper:
            tags = classify_paper_buckets(paper_id, gold_by_paper[paper_id])
            for tag in tags:
                bucket_exps[tag].extend(exps)

    overall = aggregate_experiment_evals(all_exp)
    result: dict[str, Any] = {"overall": overall}
    if multi_paper_ids is not None:
        result["multi_experiment"] = aggregate_experiment_evals(multi_exp)
        result["multi_experiment_paper_ids"] = sorted(multi_paper_ids)

    if gold_by_paper is not None:
        result["buckets"] = {
            name: aggregate_experiment_evals(bucket_exps[name])
            for name in BUCKET_NAMES
        }
    return result
