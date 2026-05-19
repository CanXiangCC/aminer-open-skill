# Paper Source Trace

`paper-source-trace` turns one academic paper into claim-centered source-tracing and citation-intent analysis artifacts. It is the unified successor to the earlier English and Chinese source-tracing variants.

## Quick Start

Use natural language:

```text
请分析这篇论文 PDF, 生成中文 analysis.md、json/graph/citation_graph.json、citation_map.svg 和 citation_map.html。
```

Use the slash command:

```text
/paper-source-trace file: papers/demo.pdf output: outputs/paper-source-trace/demo mode: all template: no aminer: off
```

AMiner is optional. Keep `aminer: off` for local analysis. Use `aminer: on` only when you explicitly want AMiner to supplement paper IDs, URLs, metadata, or citation relationships.

## Use Cases

Use this skill when a user provides a paper PDF, extracted paper text, citation contexts, or references and asks for:

- citation intent extraction;
- claim-to-source tracing for key paper claims and contributions;
- entity and relation extraction;
- paper contribution mapping;
- `json/graph/citation_graph.json`;
- SVG and HTML citation maps;
- optional AMiner metadata or citation-relation enrichment.

## Standard Outputs

| Output | Description |
| --- | --- |
| `analysis.md` | Report in the user's primary language, covering citation intent groups, claim-to-source traces, graph interpretation, and uncertainty |
| `json/graph/citation_graph.json` | Stable machine-readable graph with English keys, allowed intent labels, and optional `source_traces[]` |
| `citation_map.svg` | Static citation map when SVG generation is possible |
| `citation_map.html` | Single-file interactive graph when graph data is available |
| `citation_map_example.svg` | Extra example-mode SVG only when visual mode is `all` |
| `citation_map_spec.md` | Fallback notes when SVG cannot be generated |

## AMiner Enrichment

AMiner is optional. Local citation analysis does not require an AMiner token or `AMINER_API_KEY`.

AMiner enrichment is used only when explicitly requested with phrases such as `AMiner 增强`, `用 AMiner 补全`, `查 AMiner 引用链`, or `enhance with AMiner`.

When enabled, the recommended API chain is:

1. `paper_search` or `paper_search_pro` to locate the target paper.
2. `paper_detail` to enrich target metadata.
3. `paper_relation` to retrieve AMiner cited papers.
4. `paper_info` to batch-enrich cited paper basics.

AMiner data can enrich IDs, URLs, candidate references, and external cited-paper metadata. It must not replace local citation contexts or justify citation-intent labels by itself.
It also must not prove a claim-to-source trace without local evidence from the target paper.

## Token Setup

On Windows, run the repository helper when AMiner enrichment is needed:

```powershell
.\tools\setup-aminer-token.cmd
```

Check token status without printing the token:

```powershell
.\tools\setup-aminer-token.ps1 -Status
```

Clear the user-level token:

```powershell
.\tools\setup-aminer-token.ps1 -Clear
```

If your host uses OpenClaw-style configuration, you can also configure the variable outside this skill:

```bash
openclaw config set env.vars.AMINER_API_KEY "<YOUR_TOKEN>"
```

Do not commit real tokens, screenshots containing tokens, or logs that print tokens.

## Parameters

| Parameter | Values | Default | Description |
| --- | --- | --- | --- |
| `file` | PDF or text path | none | Input paper, extracted text, citation contexts, or reference list |
| `output` | output directory | `outputs/paper-source-trace/<safe-paper-stem>/` | Output root; JSON artifacts go under `json/graph/`, `json/aminer/`, and `json/extraction/` |
| `mode` | `current`, `example`, `all`, `hybrid` | confirm before generation | Controls static SVG mode and HTML behavior |
| `template` | `yes`, `no` | `no` | Use the fixed `analysis.md` template only when explicitly requested |
| `aminer` | `on`, `off` | `off` | Check `AMINER_API_KEY` only when AMiner enrichment is explicitly enabled |

## Self Check

Run the local doctor-style check from the repository root:

```powershell
.\tools\check-paper-source-trace.ps1
```

The check validates the skill directory, slash-command entry, marketplace entry, schema example, evals, README links, old slug cleanup, and token status without printing the token.

## Language Policy

- `analysis.md`, SVG labels, evidence explanations, and final prose follow the user's primary language.
- `json/graph/citation_graph.json` keys, intent labels, relation types, and schema fields remain English.
- The canonical graph is saved under `json/graph/citation_graph.json`.

## References

- `references/schema.md`: canonical `citation_graph.json` schema saved as `json/graph/citation_graph.json`.
- `references/evidence_protocol.md`: evidence and uncertainty policy.
- `references/prompts.md`: extraction and review prompts.
- `references/visual.md`: SVG and HTML graph layout rules.
- `references/analysis_template.md`: fixed report template for explicit template requests.
