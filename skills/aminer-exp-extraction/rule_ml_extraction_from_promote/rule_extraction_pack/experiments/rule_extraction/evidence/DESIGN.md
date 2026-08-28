# Evidence Field — Design (v1)

## Semantics

- `evidence: string[]` — per-experiment **verbatim** sentences from the paper markdown (not summaries or paraphrases).
- Hybrid input: `experiment_name`, `method`, `key_results[]` from LLM/Gold upstream; **must not** use gold `datasets` or gold `evidence` as retrieval queries.

## v1 Algorithm — MSWR

1. **Candidate pool** — regex sentence-split full md; filter noise (length, tables, headers, citations).
2. **Query set** — weighted queries from key_results (1.0), method sentences (0.7), name tokens (0.4).
3. **Scope** — section-aware routing for multi-experiment papers; single-exp shortcut = 1.0.
4. **Score** — `scope × (0.55·Jaccard + 0.25·numeric_anchor + 0.20·substring_boost) × query_weight`.
5. **Greedy select k** — per-query argmax, dedupe Jaccard > 0.85, verbatim md substring required.
6. **Trace** — full scoring breakdown per selected sentence.

## Evaluation — Two Tracks

### Product track (success criteria)

Open engineering goal: produce **reasonable, traceable evidence** — not necessarily matching gold.

| Gate | Metric | dev_10 threshold | Meaning |
|------|--------|------------------|---------|
| 低噪声 | `noise_rate` | ≤ 15% | bib / URL / table HTML / Index Terms fragments |
| 高相关 | `relevance_mean` | ≥ 20% | mean max Jaccard(pred, key_results ∪ method) |
| 可溯源 | `traceable_rate` | ≥ 95% | pred sentences are md substrings |
| 人工可接受 | `human_acceptable` | manual | spot-check ~10 papers; not automated |

`pass` in `run_manifest.json` = all three automated gates pass. Gold recall does **not** gate pass.

### Benchmark track (regression only)

Gold exists for convenient evaluation; ~40% of gold evidence is non-verbatim paraphrase.

| Metric | Description |
|--------|-------------|
| `verbatim_rate` / `traceable_rate` | Fraction of pred sentences that are md substrings |
| `recall_at_k` / `precision_at_k` / `micro_f1_at_k` | Greedy 1:1 match at k=5 |
| `semantic_recall_at_k` | Match when Jaccard ≥ 0.5 or embedding ≥ 0.85 |
| `gold_substring_rate` | Gold audit: gold evidence in md (build time) |

Greedy match order: exact normalize → fuzzy substring (len ratio ≥ 0.5) → Jaccard ≥ 0.5.

Legacy benchmark thresholds (informational, non-gating): `semantic_recall_at_5` 45%, `verbatim_rate` 85%.

## v2 Directions

- `section_union` input mode
- Embedding rerank for paraphrase misses
- Stronger multi-experiment section routing
- Text cleaning (`compact_markdown`) for retrieval quality
