# aminer-open-skill

[![版本](https://img.shields.io/badge/version-1.8.1-0969da)](.claude-plugin/marketplace.json)
[![可用 Skill](https://img.shields.io/badge/available_skills-7-2da44e)](#选择-skill)
[![许可证](https://img.shields.io/badge/license-MIT-6f42c1)](LICENSE)

[English](README.md) | 中文

面向 Claude Code、Codex、OpenClaw 等 AI 助手的 AMiner Skill 集，用于查找论文、构建阅读清单、追踪论文来源和核查引用。

> 根据任务选择范围最匹配的 Skill。能用免费检索解决时先从免费检索开始，仅在必要时使用深度或计费功能。

- [🧰 选择 Skill](#选择-skill)
- [🚀 快速开始](#快速开始)
- [💬 使用场景](#使用场景)
- [ℹ️ 注意事项](#注意事项)
- [📚 参考资料](#参考资料)

## 选择 Skill

通常可以按照“发现与收集文献 -> 分析与追踪论文 -> 核验引用”的流程选择 Skill，也可以直接从当前需要完成的任务开始。

### 🔎 发现与收集文献

| Skill | 适合完成的任务 | Token 要求 | 使用说明 |
| --- | --- | --- | --- |
| `aminer-free-academic` | 使用 AMiner 免费接口查找和初筛论文、学者、机构、期刊或专利 | 接口免费，但仍需 Token | [SKILL.md](skills/aminer-free-academic/SKILL.md) |
| `aminer-academic-search` | 对论文、学者、机构、期刊和专利进行完整检索或深度分析 | 必须配置；部分 API 计费 | [SKILL.md](skills/aminer-academic-search/SKILL.md) |
| `aminer-daily-paper` | 根据主题、学者、作者或 AMiner 账号获取个性化论文推荐 | 必须配置 | [SKILL.md](skills/aminer-daily-paper/SKILL.md) |
| `aminer-deep-search` | 通过多轮检索、去重和引用扩展构建大规模综述文献集 | 必须配置 | [SKILL.zh.md](skills/aminer-deep-search/SKILL.zh.md) |

### 🧭 分析与追踪论文

| Skill | 适合完成的任务 | Token 要求 | 使用说明 |
| --- | --- | --- | --- |
| `paper-source-trace` | 将论文关键论点追踪到引用上下文和来源，并生成证据报告与引用图 | 可选；仅在使用 AMiner 增强时需要 | [SKILL.zh.md](skills/paper-source-trace/SKILL.zh.md) / [使用说明](skills/paper-source-trace/README_zh.md) |

### ✅ 核验引用

| Skill | 适合完成的任务 | Token 要求 | 使用说明 |
| --- | --- | --- | --- |
| `pdf-citation-verifier` | 核验论文 PDF 所列参考文献是否真实存在 | 必须配置 | [SKILL.zh.md](skills/pdf-citation-verifier/SKILL.zh.md) |
| `citation-faithfulness` | 核查正文引用是否准确表达了被引来源的原意 | 不需要 AMiner Token，但需要联网 | [SKILL.zh.md](skills/citation-faithfulness/SKILL.zh.md) |

## 快速开始

### 1. 📦 添加需要的 Skill

克隆原作者仓库：

```bash
git clone https://github.com/CanXiangCC/aminer-open-skill.git
cd aminer-open-skill
```

通过 AI 助手常用的 Skill 或插件安装方式，添加所需的 `skills/<skill-name>/` 目录。如果 AI 助手支持 Claude 插件，可以通过 [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) 查看可安装条目。

### 2. 🔑 按需配置 Token

在 [AMiner 控制台](https://open.aminer.cn/open/board?tab=control)生成 Token，然后在 AI 助手使用的环境中配置 `AMINER_API_KEY`：

```bash
export AMINER_API_KEY="<YOUR_TOKEN>"
```

Claude Code、Codex 等本地对话式会话可以使用仓库提供的快速配置工具：

```text
Windows：       tools\setup-aminer-token.cmd
PowerShell：    .\tools\setup-aminer-token.ps1
macOS/Linux：   ./tools/setup-aminer-token.sh
```

OpenClaw 需要使用自己的环境配置：

```bash
openclaw config set env.vars.AMINER_API_KEY "<YOUR_TOKEN>"
```

独立 CLI、CI 和定时任务也需要在各自运行环境中配置 Token。并非所有 Skill 都需要 Token，配置前请先查看上方表格。

### 3. 💬 直接描述任务

用自然语言说明学术任务，并提供需要的论文、主题、学者或输出偏好：

```text
查找近期关于多模态智能体的论文，并总结主要研究方向。
```

如果 Skill 提供 slash command，也可以直接调用：

```text
/aminer-deep-search topic: "多模态智能体" target-size: 200
```

## 使用场景

安装对应 Skill 后，可以直接使用下面的请求：

| 目标 | 示例请求 | Skill |
| --- | --- | --- |
| 快速查找论文 | “查找 10 篇近期关于长上下文语言模型的论文，返回标题、年份、期刊或会议、引用量和链接。” | `aminer-free-academic` |
| 调研学者或研究方向 | “整理 Andrew Ng 的研究画像，包括研究兴趣、代表论文、主要合作者和近期工作。” | `aminer-academic-search` |
| 获取聚焦阅读清单 | “推荐 8 篇关于工具调用型多模态智能体的论文，优先选择近期且高引用的工作。” | `aminer-daily-paper` |
| 为综述收集文献 | “收集 200 篇检索增强生成方向的候选论文，从高质量种子论文继续扩展，去重后导出文献清单。” | `aminer-deep-search` |
| 追踪论文来源 | “分析这篇 PDF，将每个关键论点追踪到引用上下文和来源，解释引用意图，并生成 Markdown、JSON、SVG 和 HTML 产物。” | `paper-source-trace` |
| 识别虚假参考文献 | “核验这篇论文 PDF 中的所有参考文献，标出不存在、可疑或需要人工复核的条目。” | `pdf-citation-verifier` |
| 核查引用忠实性 | “逐条检查这篇论文的正文引用，获取被引来源，并判断上下文中的论断是否得到原文支持。” | `citation-faithfulness` |

## 注意事项

- 不要打印、记录或提交 `AMINER_API_KEY`。
- AMiner 免费接口仍需 Token。建议先用 `aminer-free-academic`，仅在必要时调用计费 API。
- 部分任务会产生 API 费用。执行大规模检索或高成本调用前，应先查看预估成本。
- `tools/` 下的配置工具只面向本地对话式环境。OpenClaw、CLI、CI 和定时任务需要单独配置。
- 如果需要直接集成 API，而不是使用 Skill，请参考下方 AMiner 开放平台文档。

## 参考资料

- [AMiner 控制台](https://open.aminer.cn/open/board?tab=control)
- [AMiner 开放平台文档](https://open.aminer.cn/open/docs)
- [Claude 插件清单](.claude-plugin/marketplace.json)
- [MIT License](LICENSE)
