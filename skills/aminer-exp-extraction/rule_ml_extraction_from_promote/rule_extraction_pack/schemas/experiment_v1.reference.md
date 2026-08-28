# Experiment Extraction v1 — 字段参考

> 人类可读的字段说明文档。机器校验请使用同目录下的 [`experiment_v1.schema.json`](./experiment_v1.schema.json)。

## 概述

- **版本**：`experiment_v1`
- **粒度**：单个 experiment 对象；一篇论文可输出 **多个** experiment（JSON 数组）
- **示例数据**：[`data/examples/extractions_demo.batch.json`](../data/examples/extractions_demo.batch.json)
- **抽取原则**：只依据论文原文；无法确定时返回 `null`、`""` 或 `[]`；禁止编造

## 顶层对象

| 字段 | 类型 | 说明 |
|------|------|------|
| `_id` | `string \| null` | 实验唯一 ID（Mongo 主键）；抽取阶段通常为 `null` |
| `paper_id` | `string` | 关联论文 ID（如 AMiner ID、DOI Hash、内部论文 ID） |
| `experiment_name` | `string` | 实验名称，如 `"Human Preference Evaluation"`、`"Ablation Study"` |
| `research_problem` | `string` | 研究问题（Why）：当前研究试图解决的问题 |
| `research_goal` | `string` | 研究目标（Goal）：实验希望验证的内容 |
| `experiment_subject` | `string[]` | 实验对象（What）：如 `["GPT-4"]`、`["Human Participants"]` |
| `method` | `string` | 实验方法（How）：设计与实施过程 |
| `datasets` | `object[]` | 实验涉及的数据集列表，见下表 |
| `sample_size` | `number \| null` | 实验总体样本规模（与 `datasets[].sample_size` 不同，表示本实验实际使用量） |
| `metrics` | `string[]` | 评价指标，如 `Accuracy`、`F1`、`BLEU` |
| `key_results` | `string[]` | 核心实验结果，建议保留多条 |
| `conclusion` | `string` | 实验结论（Conclusion） |
| `limitations` | `string` | 实验局限性 |
| `evidence` | `string[]` | 支撑各字段的论文原文句子 |
| `domain` | `string` | 学科领域，见 [domain 枚举](#domain-枚举) |
| `experiment_type` | `string` | 实验类型，见 [experiment_type 枚举](#experiment_type-枚举) |
| `experiment_history` | `string[]` | 实验历史（预留，可为空数组） |
| `score` | `number` | 抽取置信度 `0~1`，见 [score 规则](#score-规则) |

## `datasets[]` 子对象

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | `string` | 数据集名称，如 `ImageNet`、`THU-MedBench` |
| `aliases` | `string[]` | 别名，用于后续实体归并，如 `["ImageNet-1K", "ILSVRC2012"]` |
| `dataset_type` | `string` | 数据集类型，见 [dataset_type 枚举](#dataset_type-枚举) |
| `description` | `string` | 简介：来源、内容、覆盖范围等 |
| `sample_size` | `number \| null` | 该数据集的样本总数 |
| `is_public` | `boolean \| null` | 是否可公开获取：`true` / `false` / `null`（无法判断） |
| `is_self_collected` | `boolean \| null` | 是否作者自行构建：`true` / `false` / `null` |
| `urls` | `string[]` | 访问地址（官网、HuggingFace、Kaggle、Zenodo 等） |
| `github_urls` | `string[]` | GitHub 仓库（数据集、代码或项目仓库） |
| `doi_list` | `string[]` | **数据集 DOI**（非论文 DOI），如 `10.5281/zenodo.123456` |
| `cstr_list` | `string[]` | 中国科技资源标识，如 `CSTR:16666.11.nbsdc.xxxxx` |

### 数据集识别规则

以下内容均可识别为数据集：

- Dataset / Database / Corpus / Benchmark / Collection
- Survey Data / Registry / Clinical Records
- Industrial Database / Self-collected Data

示例：`ImageNet`、`MIMIC-III`、`UK Biobank`、`Global Cement Production Sites Database`。

**注意**：不要简单把 source database 直接当作 dataset name；若作者基于多个来源构建数据库，优先识别作者最终构建的数据集。

## 枚举值

### domain 枚举

```
computer_science | medicine | biology | chemistry | physics | materials
engineering | economics | education | energy | environment | social_science | other
```

### experiment_type 枚举

```
benchmark | comparison | ablation | simulation | survey | human_study
field_study | lab_experiment | clinical_trial | case_study | empirical_study
data_analysis | other
```

### dataset_type 枚举

```
text | image | video | audio | multimodal | tabular | timeseries | sensor
medical | biological | chemical | material | simulation | industrial | other
```

## score 规则

| 区间 | 含义 |
|------|------|
| `0.9 ~ 1.0` | 文本明确说明 |
| `0.7 ~ 0.9` | 可直接推断 |
| `0.5 ~ 0.7` | 弱推断 |
| `< 0.5` | 证据不足 |

推荐解读：`> 0.8` 高可信；`0.5 ~ 0.8` 中可信；`< 0.5` 低可信。

## 最小结构示例

```json
{
  "_id": null,
  "paper_id": "6653e91a01d2a3fbfc780ace",
  "experiment_name": "SOAYBench Evaluation",
  "research_problem": "...",
  "research_goal": "...",
  "experiment_subject": ["Large Language Models"],
  "method": "Benchmark evaluation against baselines.",
  "datasets": [
    {
      "name": "SOAYBench",
      "aliases": [],
      "dataset_type": "text",
      "description": "...",
      "sample_size": 3960,
      "is_public": true,
      "is_self_collected": true,
      "urls": ["https://github.com/example/repo"],
      "github_urls": ["https://github.com/example/repo"],
      "doi_list": [],
      "cstr_list": []
    }
  ],
  "sample_size": 792,
  "metrics": ["EM", "F1"],
  "key_results": ["..."],
  "conclusion": "...",
  "limitations": "",
  "evidence": ["..."],
  "domain": "computer_science",
  "experiment_type": "benchmark",
  "experiment_history": [],
  "score": 0.95
}
```

## Pipeline 输出约定

LLM extractor 对单篇论文输出 **JSON 数组**，每个元素符合本 schema：

```json
[
  { "...experiment 1..." },
  { "...experiment 2..." }
]
```

校验时：对数组中每个元素分别用 `experiment_v1.schema.json` 校验。
