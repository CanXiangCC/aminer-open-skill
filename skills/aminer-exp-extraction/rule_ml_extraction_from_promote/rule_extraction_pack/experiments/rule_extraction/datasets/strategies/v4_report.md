# datasets--策略v4--分层混合提取

## 概述

v4 在 v1-v3 基础上采用 **高召回提取 + Gazetteer 软标注**：

- **Layer A**：dataset 语义 section（含子树）→ 宽松文本 + abbrev+citation + scoped 表格
- **Layer B**：Experiments/Results section → 强语境正则
- **Gazetteer**：仅标注 confidence，**不过滤**输出
- **黑名单**：过滤已知模型名

## 与 v1-v3 差异

| | v1 | v2 | v3 | v4 |
|--|----|----|----|-----|
| 范围 | dataset section | 全文 | section+supplement | Layer A/B |
| 表格 | 是 | 否 | 否 | Layer A only |
| Gazetteer | 否 | 否 | 硬过滤 | 软 confidence |
| trace | 无 | 无 | 有 | 完整分层 trace |

## Confidence 规则（初版）

| 条件 | confidence |
|------|------------|
| Gazetteer canonical/alias 精确命中 | high |
| Layer A 直白句式 / 表格 | medium |
| Layer B 强语境 / abbrev+citation | medium |
| 仅 Gazetteer 子串 / 仅宽松模式 | low |

## 已知限制

- Layer A 宽松模式在非 survey 论文上仍可能误报
- Gold2 仍含 LLM 全文级 datasets，与规则目标未完全对齐
- 自建 dataset（Description corpus 等）无 gazetteer 条目

## 运行

```bash
python -m experiments.rule_extraction.datasets.test_runner --strategy v4 --gold-set paper_union
```
