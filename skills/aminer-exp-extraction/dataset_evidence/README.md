# Dataset Evidence Backfill

Post-hoc MSWR evidence extraction for existing bulk pipeline predictions.

## Purpose

Adds evidence fields to existing prediction JSON files without re-running the full extraction pipeline. This is used to backfill evidence for runs where the evidence pack was not vendored.

## Prerequisites

- Evidence pack must be vendored: `scripts/vendor_from_upstream.py`
- MD files must be cached in `pipeline_output/md_cache/`

## Usage

### Nested session (single job batch)

```bash
python -m dataset_evidence.score_bulk_evidence \
    --session-run-id prod-bulk-20260717 \
    --job-batch job_batch_000
```

### Nested session (all job batches)

```bash
python -m dataset_evidence.score_bulk_evidence \
    --session-run-id prod-bulk-20260717
```

### Legacy flat run

```bash
python -m dataset_evidence.score_bulk_evidence \
    --run-id prod-bulk-20260717-job000
```

### Dry run (no modifications)

```bash
python -m dataset_evidence.score_bulk_evidence \
    --session-run-id prod-bulk-20260717 \
    --job-batch job_batch_000 \
    --dry-run
```

### Force overwrite existing evidence

```bash
python -m dataset_evidence.score_bulk_evidence \
    --session-run-id prod-bulk-20260717 \
    --job-batch job_batch_000 \
    --force
```

## CLI Options

- `--run-id`: Legacy flat run ID (prod-bulk-YYYYMMDD-jobNNN) or nested session/job (prod-bulk-YYYYMMDD/job_batch_NNN). Can be repeated.
- `--session-run-id`: Session run ID (parent folder under runs/)
- `--job-batch`: Job batch subfolder (e.g. job_batch_000); omit to process all under session
- `--concurrency`: Thread pool for MD downloads and evidence scoring (default: 8)
- `--retries`: Download retry attempts (default: 3)
- `--dry-run`: Scan and compute without modifying files
- `--force`: Force overwrite existing non-empty evidence
- `--demo`: Run self-check demo

## Output

- Prediction files are updated in-place with `experiments[0]["evidence"]` only (atomic write via `.tmp` + `os.replace`)
- Papers with existing non-empty evidence are skipped unless `--force` is set
- Evidence report is written to `runs/{session}/{job_batch}/evidence_report.md`

Note: backfill does **not** modify `provenance` (predictions store provenance as a list, not a dict).

## Post-backfill

After backfill, re-run the merge script to generate the merged export with evidence:

```bash
python scripts/merge_flat_experiments.py --session-run-id prod-bulk-20260717
```

Output: `exports/ai2000_prod-bulk-20260717_flat_merged.json` (flat experiment array) with populated evidence fields.

## Difference vs dataset_confidence

| Aspect | dataset_confidence | dataset_evidence |
|--------|-------------------|------------------|
| Target | `experiments[].datasets[]` | `experiments[].evidence` |
| Context needed | MD text only | MD text + experiments_stripped (7 LLM fields) |
| Adapter import | `score_datasets_confidence()` | `get_evidence_v4().extract_for_paper()` |
| Metrics | Frequency, usage, identifier, completeness | MSWR evidence per experiment |

## Algorithm

1. Read prediction JSON
2. Build `experiments_stripped` from all experiments using `schema.LLM_FIELDS` (7 fields)
3. Get MD from `md_cache/{paper_id}.md` (download if needed)
4. Call `EvidenceRuleV4.extract_for_paper(raw_md, experiments_stripped, input_mode="full_text")`
5. Write `experiments[0]["evidence"]` back to prediction (atomic)