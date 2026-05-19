# Fixed `analysis.md` Template

Use this only when the user explicitly requests a template, compliance format, standard format, or fixed structure.

Render all headings, prose, table labels, and uncertainty notes in the user's primary language. Keep JSON field names and intent labels unchanged when referenced.

Do not invent citations to fill a section. If no reliable evidence supports an intent or row, write `No reliable evidence found` or `未发现可靠证据`, matching the output language.

## Required Markdown Structure

```markdown
# Citation Intent Analysis: <paper_title>

## 1. Overall Conclusion

- Target paper:
- Citation structure judgment:
- Citation chains worth reading first:
- Main uncertainty:

## 2. Target Paper Core Content

| Item | Content |
| --- | --- |
| Research problem |  |
| Core method |  |
| Data / benchmark |  |
| Main result |  |
| Limitation |  |

## 3. Citation Intent Overview

| Intent label | Count | Representative references | Role in understanding the paper |
| --- | ---: | --- | --- |

## 4. Intent-Grouped Citation Analysis

### 4.x `<intent>`: <display label>

| Item | Content |
| --- | --- |
| Judgment basis |  |
| Key citations |  |
| Evidence anchors |  |
| Role in the paper's argument |  |
| Uncertainty |  |

Repeat only for intents with reliable evidence. Summarize absent expected intents briefly instead of fabricating citations.

## 5. Core Method Citation Chain

| Method component | Supporting reference | Borrowed idea | Role in this paper | Evidence and uncertainty |
| --- | --- | --- | --- | --- |

## 6. Dataset, Metric, and Baseline Citations

| Evaluation target | Dataset / metric / baseline | Supporting reference | Role in result interpretation | Evidence and uncertainty |
| --- | --- | --- | --- | --- |

## 7. Entity and Relation Graph Interpretation

- Main entities:
- Main relations:
- Recommended reading path through `citation_map.svg`:
- AMiner enrichment impact, if any:

## 8. Coverage, Noise, and Uncertainty

- Coverage:
- Missing or noisy evidence:
- Reference matching caveats:
- AMiner enrichment caveats:
- SVG generation status:

## 9. Output File Checklist

| File | Status | Notes |
| --- | --- | --- |
| `analysis.md` | Generated | Report in the user's primary language |
| `citation_graph.json` | Generated | Must parse as JSON |
| `citation_map.svg` | Generated / not generated | Static citation map |
| `citation_map_example.svg` | Generated / not used | Only for `all` mode |
| `citation_map_spec.md` | Optional / not used | Fallback if SVG generation fails |
```

## Quality Rules

- Keep the section order.
- Preserve all records in `citation_graph.json`; the Markdown report may summarize dense groups.
- Each intent group must explain how the group supports the target paper's problem, method, experiment, or limitation.
- AMiner-enriched metadata must be labeled as metadata, not as local citation evidence.
