# Evidence Protocol for Citation Intent Analysis

Use this protocol before writing `analysis.md` and before finalizing `json/graph/citation_graph.json`.

## Evidence Sources

Use only:

- supplied PDF text;
- extracted paper text;
- citation contexts;
- reference entries;
- user-provided notes;
- explicitly requested AMiner metadata or citation relationships.

Do not fill gaps with domain memory, plausible bibliography guesses, or AMiner-only citation links.

## Evidence Anchors

For each important citation, capture as many anchors as possible:

| Anchor | Meaning |
| --- | --- |
| `citation_context` | Local sentence or short paragraph where the citation appears |
| `section` | Target paper section or nearby heading |
| `target_claim` | Target-paper claim, method choice, dataset choice, or result interpretation supported by the citation |
| `cited_work_role` | Role of the cited work, such as problem origin, method component, dataset source, baseline, tool, theory, result evidence, or limitation |
| `intent_rationale` | Why this citation belongs to its selected intent label instead of a nearby label |
| `confidence_reason` | Why confidence is high, medium, or low |

## Claim-Centered Source Tracing

Use source tracing to answer: which cited sources support, motivate, supply, contrast, or limit a target-paper claim?

For each important target-paper claim or contribution:

1. Identify the claim from the target paper text, not from outside memory.
2. Link the claim to one or more local citation contexts.
3. Assign each cited source a `source_role`, such as `foundation`, `method-origin`, `method-adaptation`, `dataset-source`, `metric-source`, `baseline-comparison`, `evidence-support`, `contrast`, `limitation-source`, or `future-direction`.
4. Explain how the cited source supports the claim using visible evidence.
5. Record uncertainty when the claim is clear but the citation context is weak, noisy, or only indirectly connected.

Build `source_traces[]` only when at least one local citation context supports the trace. AMiner metadata can enrich IDs, URLs, and candidate matches, but cannot by itself prove a claim-to-source relationship.

## Citation Context Rules

- Prefer citation sentences and adjacent context over abstract-level summaries.
- If a citation appears only in a table, figure caption, or noisy PDF extraction, mark the noise in `notes`.
- If the cited title or reference entry cannot be matched reliably, use `unmatched_reference: true`.
- Do not copy long source passages into `analysis.md`; summarize evidence and keep short anchors.
- AMiner metadata can improve reference matching but cannot create local citation evidence.

## Intent Rationale Rules

Each important citation should answer:

1. What target-paper idea does this citation support?
2. What is the cited work's role in that idea?
3. Why is the chosen `intent` more appropriate than similar labels?
4. How strongly does the visible evidence support the judgment?

Examples:

- `core-method`: cited work directly supplies or motivates a main method component.
- `supporting-method`: cited work supports an auxiliary technique or implementation choice.
- `dataset`: cited work introduces or defines a dataset used in evaluation.
- `baseline`: cited work is used as a comparison system, not merely related work.
- `result-evidence`: cited work or external result helps interpret target-paper performance.

## Confidence Policy

| Level | Range | Use when |
| --- | ---: | --- |
| high | `0.80-1.00` | Citation sentence, reference match, and target claim are all clear |
| medium | `0.55-0.79` | Intent is likely but section context, reference match, or cited-work role is incomplete |
| low | `0.10-0.54` | Evidence is noisy, table-derived, ambiguous, or weakly connected |

Do not use high confidence when only the reference title or AMiner metadata is known but the local citation context is missing.

## No-Evidence Handling

If an expected intent, method chain, dataset link, or baseline link has no reliable evidence, write the equivalent of `No reliable evidence found` in the output language. In Chinese output, write `未发现可靠证据`.

If a target-paper claim has no reliable citation-backed source trace, write `No reliable source trace found` in the output language. In Chinese output, write `未发现可靠溯源证据`.

When generating `analysis.md`, explicitly distinguish:

- evidence-backed conclusions;
- plausible but uncertain interpretations;
- missing or noisy evidence;
- AMiner metadata enrichment that does not prove intent.
- claim-to-source traces supported by local citation contexts.

When generating `json/graph/citation_graph.json`, preserve uncertainty in `notes`, `intent_rationale`, `confidence_reason`, or `source_traces[].notes`.
