# Evidence Field — Roadmap

## M0 — Scaffold & Gold

- [x] Directory layout, DESIGN/README
- [x] `build_gold_sets.py` → per_experiment gold + substring audit
- [x] `load_gold_experiments_stripped()` for assignment consumers

## M1 — v1 MSWR

- [x] `EvidenceRuleV1` strategy with full trace
- [x] `evidence_evaluator.py` greedy match + aggregation
- [x] `test_runner.py` with runs/{run_id}/ monitoring
- [x] Unit tests + dev_10 run (benchmark: semantic_recall@5=19.4%, traceable=100%)

## M1.5 — v2/v3 MSWR + Eval Enhancement (2026-07-06)

- [x] Dual-track gold metrics (verbatim subset, normalized recall)
- [x] Bucket reporting (single/multi/survey/cross_lingual)
- [x] `EvidenceRuleV2` / `EvidenceRuleV3`
- [x] `--compare-v1` delta in manifest
- [x] **Product success criteria** (低噪声 + 高相关 + 可溯源 + 人工可接受)

**Note**: Gold recall ~19% is expected under benchmark track; product gates are the engineering pass/fail standard.

## M2 — v4 sentence clean + Product gates（2026-07-07）✅

- [x] wf8 R1–R4 `sentence_clean.py` + `EvidenceRuleV4`
- [x] Product track evaluator（noise / relevance / traceable）
- [x] dev_10 run `20260707_evidence_v4_dev10` — **product_pass YES**, noise 4.92%
- [x] v4.1 洗句补丁实验 — **未采纳**（指标低于 v4）
- [x] **实验最优方案拍板：v4** — 见 [DECISION.md](DECISION.md)

## M2b — Section union & embedding（future）

- [ ] `input_mode=section_union` using section selector output
- [ ] Embedding rerank ablation（dev_10 默认 Jaccard 已够用）
- [ ] dev_20 泛化 + 人工 spot-check

## M3 — Integration（future）

- [ ] Promote **v4** to `src/rule_extraction/` if dev_20 + human_acceptable OK
- [ ] Wire into datasets assignment blob co-occurrence pipeline
- [ ] 生产主管线：`merger.py` 仍 LLM evidence，集成前不改 `LLM_FIELDS`
