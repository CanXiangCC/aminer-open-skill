---
description: Paper Source Trace 论文来源追踪与引用意图分析
argument-hint: [file: <pdf-or-text-path> output: <output-dir> mode: current|example|all|hybrid template: yes|no aminer: on|off | 自然语言]
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# /paper-source-trace - Paper Source Trace

User invoked the Paper Source Trace skill with the following arguments:

```
$ARGUMENTS
```

## Your Task

Read and follow `${CLAUDE_PLUGIN_ROOT}/SKILL.md`. This command is an orchestration entrypoint, not a standalone parser or renderer. Use the existing Paper Source Trace workflow to produce:

- `analysis.md`
- `json/graph/citation_graph.json`
- `citation_map.svg` when static SVG generation is possible
- `citation_map.html` when graph data is available
- `citation_map_example.svg` only when `mode: all`
- `citation_map_spec.md` when SVG cannot be generated

## 1. Startup Confirmation

Before parsing the paper, reading the input file, checking `AMINER_API_KEY`, calling AMiner, or generating SVG, ask the user to confirm both settings:

- SVG generation mode: `current`, `example`, `all`, or `hybrid`
- AMiner enrichment: `on` or `off`

If `$ARGUMENTS` already contains `mode` and/or `aminer`, restate those provisional choices and ask the user to confirm the final pair before proceeding. Stop after asking until the user answers.

## 2. Parse Arguments

Accept structured fields and natural language in the same invocation.

Structured fields:

| Field | Values | Meaning |
| --- | --- | --- |
| `file` | PDF path, text path, or citation-context file path | Primary input |
| `output` | directory path | Artifact output directory |
| `mode` | `current`, `example`, `all`, `hybrid` | Visual mode |
| `template` | `yes`, `no` | Whether to use `references/analysis_template.md` |
| `aminer` | `on`, `off` | Whether AMiner enrichment is explicitly requested |

Natural language is valid. Extract the user's intent without discarding the original wording, especially language preference, output requirements, AMiner opt-in, template requests, and visual mode.

## 3. Input Guard

If `$ARGUMENTS` and the current conversation do not provide any PDF path, text path, pasted paper text, citation contexts, reference list, or usable paper evidence, ask the user to provide an input file or paper text. Do not fabricate `analysis.md`, `json/graph/citation_graph.json`, SVG/HTML content, citations, references, claims, or source traces.

If a file path is provided, read it when the host allows file access. If the file is unavailable, report the missing path and ask for a valid file or pasted text.

## 4. AMiner Opt-In Rule

Default: `aminer: off`.

Check `AMINER_API_KEY` only when one of the following is true:

- `aminer: on`
- the user explicitly says `AMiner 增强`, `用 AMiner 补全`, `查 AMiner 引用链`, `补全 paper_id`, `enhance with AMiner`, or equivalent wording

When AMiner is requested:

1. Check only whether `AMINER_API_KEY` exists. Never print the token.
2. If missing, skip AMiner enrichment, continue local analysis when local evidence exists, and record the skipped reason.
3. Use AMiner only for metadata, paper IDs, URLs, candidate reference matching, and external citation relationships.
4. Do not use AMiner as the sole evidence for citation intent or `source_traces[]`.
5. Include an AMiner cost summary when any AMiner call is planned or made.

## 5. Output Rules

Unless the user specifies `output`, use:

```
outputs/paper-source-trace/<safe-paper-stem>/
```

Use this output layout:

```text
analysis.md
citation_map.svg
citation_map.html
citation_map_example.svg        # only when mode is all
citation_map_spec.md            # only when SVG generation has caveats or fails
json/graph/citation_graph.json
json/aminer/*.json              # only when AMiner raw results are saved
json/extraction/*.json          # only when structured intermediates are saved
```

Keep output language rules from `SKILL.md`:

- `analysis.md`, SVG labels, evidence explanations, and final prose follow the user's primary language.
- `json/graph/citation_graph.json` keys, intent labels, relation types, and source roles stay English.

## 6. Execution Checklist

1. Ask the startup confirmation question and wait for the user's answer.
2. Resolve input evidence and output directory.
3. Read `${CLAUDE_PLUGIN_ROOT}/SKILL.md`.
4. Read referenced files only as needed:
   - `${CLAUDE_PLUGIN_ROOT}/references/schema.md`
   - `${CLAUDE_PLUGIN_ROOT}/references/evidence_protocol.md`
   - `${CLAUDE_PLUGIN_ROOT}/references/analysis_template.md` only for explicit template mode
   - `${CLAUDE_PLUGIN_ROOT}/references/visual.md` before writing SVG
5. Extract citation contexts and classify intents using the 12 allowed labels.
6. Build claim-centered source traces when the user asks for tracing or the supplied evidence clearly supports it.
7. Write `json/graph/citation_graph.json` before SVG and HTML artifacts.
8. Write `analysis.md`, SVG artifacts, and `citation_map.html` when graph data is available.
9. Validate that every citation has `intent`, `evidence`, `confidence`, and either `reference_id` or `unmatched_reference: true`.
10. Validate that every source step links to `citation_id` and `reference_id` when available.
11. Give the user a concise completion summary with output paths and any skipped AMiner/SVG/HTML caveats.
