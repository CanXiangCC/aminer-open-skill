# aminer-open-skill

[![Version](https://img.shields.io/badge/version-1.9.0-0969da)](.claude-plugin/marketplace.json)
[![Available Skills](https://img.shields.io/badge/available_skills-7-2da44e)](#choose-a-skill)
[![License](https://img.shields.io/badge/license-MIT-6f42c1)](LICENSE)

English | [中文](README.zh.md)

An AMiner Skill collection for finding papers, building reading lists, tracing sources, and checking citations in Claude Code, Codex, OpenClaw, and similar AI assistants.

- [🧰 Choose a Skill](#choose-a-skill)
- [🚀 Quick Start](#quick-start)
- [💬 Use Cases](#use-cases)
- [ℹ️ Notes](#notes)
- [📚 References](#references)

## Choose a Skill

A typical workflow moves from finding literature, to understanding a paper's sources, to verifying its citations. Start with the category that matches your current task.

### 🔎 Find and collect literature

| Skill | Use it when you want to | Token | Guide |
| --- | --- | --- | --- |
| `aminer-free-academic` | Find and screen papers, scholars, institutions, venues, or patents with free AMiner APIs | A token is still required; listed APIs are free | [SKILL.md](skills/aminer-free-academic/SKILL.md) |
| `aminer-academic-search` | Run full academic searches, deeper analysis, or explicit structured experiment retrieval across papers, scholars, institutions, venues, and patents | Required; some APIs are billed; experiment pricing is TBD | [SKILL.md](skills/aminer-academic-search/SKILL.md) |
| `aminer-daily-paper` | Get personalized paper recommendations from topics, scholars, authors, or an AMiner account | Required | [SKILL.md](skills/aminer-daily-paper/SKILL.md) |
| `aminer-deep-search` | Build a large survey bibliography through multi-round search, deduplication, and citation expansion | Required | [SKILL.md](skills/aminer-deep-search/SKILL.md) |

### 🧭 Analyze and trace a paper

| Skill | Use it when you want to | Token | Guide |
| --- | --- | --- | --- |
| `paper-source-trace` | Trace a paper's key claims to its citation contexts and sources, then generate evidence reports and citation maps | Optional; only needed for AMiner enrichment | [SKILL.md](skills/paper-source-trace/SKILL.md) / [Usage guide](skills/paper-source-trace/README.md) |

### ✅ Verify citations

| Skill | Use it when you want to | Token | Guide |
| --- | --- | --- | --- |
| `pdf-citation-verifier` | Check whether the references listed in a paper PDF actually exist | Required | [SKILL.md](skills/pdf-citation-verifier/SKILL.md) |
| `citation-faithfulness` | Check whether in-text citations accurately represent what the cited sources say | No AMiner token required; web access is required | [SKILL.md](skills/citation-faithfulness/SKILL.md) |

## Quick Start

### 1. 📦 Add the Skill you need

Clone the repository:

```bash
git clone https://github.com/CanXiangCC/aminer-open-skill.git
cd aminer-open-skill
```

Add the selected `skills/<skill-name>/` directory to your AI assistant using its normal Skill or plugin installation method. If your assistant supports Claude plugins, use [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) as the plugin list.

### 2. 🔑 Configure the token when required

Generate a token in the [AMiner Console](https://open.aminer.cn/open/board?tab=control), then set `AMINER_API_KEY` in the environment used by your assistant:

```bash
export AMINER_API_KEY="<YOUR_TOKEN>"
```

For local Claude Code, Codex, and similar conversational sessions, the repository provides quick setup tools:

```text
Windows:       tools\setup-aminer-token.cmd
PowerShell:    .\tools\setup-aminer-token.ps1
macOS/Linux:   ./tools/setup-aminer-token.sh
```

OpenClaw uses its own environment configuration:

```bash
openclaw config set env.vars.AMINER_API_KEY "<YOUR_TOKEN>"
```

Standalone CLI commands, CI jobs, and scheduled tasks must set the token where the command runs. Check the table above first because not every Skill requires a token.

### 3. 💬 Ask naturally

Describe the academic task and provide any required paper, topic, scholar, or output preferences:

```text
Find recent papers on multimodal agents and summarize the main research directions.
```

Skills that provide slash commands can also be invoked directly:

```text
/aminer-deep-search topic: "multimodal agents" target-size: 200
```

## Use Cases

The following prompts can be used directly after the corresponding Skill is installed:

| Goal | Example request | Skill |
| --- | --- | --- |
| Find papers quickly | "Find 10 recent papers on long-context language models. Return the title, year, venue, citation count, and URL." | `aminer-free-academic` |
| Investigate a scholar or research topic | "Build a research profile for Andrew Ng, including interests, representative papers, collaborators, and recent work." | `aminer-academic-search` |
| Retrieve structured experiments | "Return the original Experiment JSON for this paper, filtered by method and dataset name." | `aminer-academic-search` |
| Get a focused reading list | "Recommend 8 papers on tool-using multimodal agents, prioritizing recent and highly cited work." | `aminer-daily-paper` |
| Collect literature for a survey | "Collect 200 candidate papers on retrieval-augmented generation, expand from strong seed papers, remove duplicates, and export the bibliography." | `aminer-deep-search` |
| Trace a paper's sources | "Analyze this PDF. Trace each key claim to its citation context and source, explain the citation intent, and generate the Markdown, JSON, SVG, and HTML outputs." | `paper-source-trace` |
| Detect fabricated references | "Check every reference in this paper PDF and flag entries that are missing, suspicious, or need manual review." | `pdf-citation-verifier` |
| Check citation faithfulness | "For each in-text citation in this paper, retrieve the cited source and determine whether the surrounding claim is supported by the original text." | `citation-faithfulness` |

## Notes

- Never print, log, or commit `AMINER_API_KEY`.
- Free AMiner APIs still require a token. Start with `aminer-free-academic` before using paid APIs.
- Some tasks may incur API charges. Review the estimated cost before approving large searches or expensive calls.
- The setup tools under `tools/` configure local chat sessions only. Set the token separately for OpenClaw, CLI, CI, and scheduled jobs.
- For direct API integration rather than Skill usage, see the AMiner Open Platform documentation below.

## References

- [AMiner Console](https://open.aminer.cn/open/board?tab=control)
- [AMiner Open Platform Documentation](https://open.aminer.cn/open/docs)
- [Claude plugin list](.claude-plugin/marketplace.json)
- [MIT License](LICENSE)
