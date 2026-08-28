# Assignment 设计文档

## 当前最优方案

**`v2_type_aware`**（详见 [v2_report.md](v2_report.md)）为当前最优 assignment 策略：

- dev_20 Gold1 fuzzy F1 **37.45%**（v1: 36.10%）
- multi-experiment 子集 fuzzy F1 **39.34%**（v1: 33.80%）
- field_study_empty_rate **100%**（v1: 0%）

默认流水线：`v4.3 extract` → **`v2_type_aware` assign** → Gold1 per-experiment 评估。

## 目标

给定 paper 级 dataset 列表（来自 `strategies/v4_3`）与 experiment 元数据列表
（来自 Gold1，`datasets` 字段已剥），把 dataset 分配到各 experiment，使其与
Gold1 真值在 `(paper_id, experiment_index)` 粒度上对齐。

## 输入 / 输出 schema

### 输入

```python
paper_datasets: list[dict]            # v4.3 输出，每项至少 {name, aliases?, ...}
experiments: list[dict]               # Gold1 实验，datasets 已剥；保留：
                                      #   experiment_name, method, key_results,
                                      #   evidence, experiment_type, experiment_subject
md_text: str                          # 完整论文 markdown
paper_id: str                         # trace 标签
```

### 输出

```python
list[dict]  # 与 experiments 同序
# 每项 = 原 experiment 字段（深拷贝） +:
#   "datasets": list[dict]            # 分配结果
#   "assignment_trace": {
#       "strategy": "v1_cooccurrence",
#       "rule_hits": [...],            # 每条命中：{dataset, rule, exp_index, evidence}
#       "fallback_used": "primary|broadcast|none",
#       "broadcast_triggered": bool,
#       "assign_ms": float,
#   }
```

## 规则优先级（v1_cooccurrence）

按顺序尝试，命中即停止对该 dataset 的处理：

1. **共现匹配（主规则）** — blob 优先于 window
   - 对每个 `paper_dataset.name` + 其 `aliases`，用 `normalize_fuzzy` + gazetteer alias 归一化后扫描两类信号：
     - a) **blob 命中（强信号）**：dataset 名出现在 experiment 的 `method` / `key_results` / `evidence` 拼接文本里（fuzzy 子串 + alias 等价）。
     - b) **md 窗口命中（弱信号）**：dataset 在 `md_text` 中提及位置 ±400 字符窗口内出现某 experiment 的 `experiment_name` 关键词（去停用词后的显著 token）。
   - **决策**：若 blob 命中非空，**仅**分配到 blob 命中的 experiment（blob 是「该 experiment 确实用了该 dataset」的强证据，可抑制短 md 窗口跨 section 串入）；否则用 md 窗口命中。
   - 一个 dataset 可命中多个 experiment（共现不互斥，由 experiment_type 约束兜底）。

2. **experiment_type 约束（过滤层）**
   - `comparison` / `benchmark`：可接收未匹配项（主实验兜底）
   - `ablation` / `disentanglement`：**仅**保留共现命中的 dataset，不接受兜底
   - `field_study` / real-world 类（`experiment_type` 含 `field`/`real_world`，或 `experiment_subject` 含 `real-world`/`in-the-wild`/`real world`）：默认 `datasets=[]`，仅当共现明确提到才分配

3. **主实验兜底**
   - 未分配的 dataset → 第一个 `comparison`/`benchmark` 类 experiment；
   - 若无，则分给 experiment_name 含 `evaluation`/`benchmark`/`comparison`/`main`/`overall` 的 `other` 类条目；
   - **`other` 类（无 fallback 关键词）、`ablation`、`field_study` 均不作为兜底目标**——否则未匹配 dataset 会被灌进任意 experiment，使 broadcast 永不触发。

4. **最后兜底 broadcast**
   - 仅当 (a) 仍有 dataset 未分配 且 (b) 无 field_study experiment 时
   - 把所有 paper_datasets 复制到每个 experiment
   - trace 标 `broadcast_triggered=True`

### 单 experiment 论文（短路）

若 `len(experiments) == 1`：直接把 `paper_datasets` 赋给该 experiment，
trace 标 `fallback_used="single_experiment"`，跳过全部规则链。这保证单
experiment 论文的 assignment 结果等于 paper 级列表（与 Gold1 对齐前提是
Gold1 该论文也只有一个 experiment）。

## fallback 决策表

| 场景 | 行为 |
|------|------|
| 单 experiment | 短路赋全部 |
| 多 experiment，全部命中 | 无兜底 |
| 多 experiment，部分未命中 + 有 comparison | 主实验兜底 |
| 多 experiment，部分未命中 + 无 comparison 但有名称匹配 | 名称兜底 |
| 多 experiment，部分未命中 + 无任何兜底候选 + 无 field_study | broadcast |
| 多 experiment，部分未命中 + 有 field_study experiment | 未命中项丢弃（不 broadcast） |

## 已知失败模式（v1 限制，dev_20 实测）

1. **共义词歧义**：dataset 名同时出现在多个 experiment 的窗口里 → 可能错分。
   v1 不做冲突仲裁，靠 experiment_type 约束后过滤。
2. **experiment_name 太短 / 太泛**：如 "Main Results"，关键词命中过宽。
   v1 用停用词 + 显著 token（len≥4 且非 `experiment`/`results`/`evaluation`）过滤。
3. **md 提及位置模糊**：dataset 名在 md 里多次出现，v1 取**所有**提及位置的窗口并集，
   可能引入噪声。v2 可改为就近 section 匹配。
4. **field_study 默认空集未生效**（实测 `659e2146`/`661ddba8`）：blob 命中（dataset 名出现在 field_study experiment 文本）绕过了 field_study 屏蔽，导致 real-world experiment 仍被分到 4 个 dataset，`field_study_empty_rate=0%`。v2 需强屏蔽。
5. **ablation 子实验 0 命中**（实测 `66bac1ca` 3 个 ablation）：ablation 文本常不含 dataset 名，规则「仅分共现到的 dataset」导致全空，但 gold 期望子集。v2 需 ablation 继承主 comparison 子集。
6. **`other` 类无共现 → broadcast**（实测 `628304515`）：`other` experiment 缺 `experiment_type` 信号且文本 blob 不含 dataset 名时退化为 broadcast，把无关 dataset 灌进所有 experiment。v2 section 就近可缓解。
7. **无 gold experiment 元数据**：若 experiment 缺 `method`/`key_results`/`evidence`，共现匹配退化为仅 md 窗口匹配。

## v2 预留方向

- **assign_v2_score**：对共现命中打分（窗口距离 + 字段权重），解决歧义。
- **LLM-assisted assignment**：把 paper_datasets + experiment_name 列表喂 LLM 做语义分配。
- **ML experiment_type**：`ml_classification` 桥接，替换关键词 `experiment_class` 判定。

---

## 规则优先级（v2_type_aware）

v2 在 v1 基础上增加 **field_study 强屏蔽**、**ablation 三级继承**、**section 路由**，
并将 Pass A / Pass B 拆为两阶段。

### 执行顺序（整篇 paper）

| Step | 动作 |
|------|------|
| 0 | 预计算 `exp_meta` + `sections`（`dataset_preprocess._parse_sections` + header span） |
| 1 | **field_study 强屏蔽**：`datasets=[]`，`rule=field_study_forced_empty`，跳过后续一切 |
| 2 | 单 experiment 短路（field_study 单实验论文仍返回空） |
| 3 | **Pass A**（仅 `comparison` / `other`）：blob + section window 共现 → 主兜底 → broadcast |
| 4 | **Pass B**（仅 `ablation`）：三级策略（见下） |

### field_study 强屏蔽（v2 必须）

```text
若 experiment_class == field_study:
  datasets = []
  rule = "field_study_forced_empty"
  跳过共现 / 继承 / broadcast
```

与 v1 差异：v1 在 blob 命中时仍分配 dataset 给 field_study；v2 **无条件空集**。

### Pass A：comparison / other

- **blob 命中**：同 v1（method/key_results/evidence fuzzy 匹配）
- **section window**：dataset mention 所在 section 内出现 experiment_name token 才计命中；
  跨 section 的 ±400 字符窗口 **丢弃**（`md_section_window`）
- **主实验兜底 / broadcast**：ablation / field_study **不参与**

### Pass B：ablation 三级策略

对每个 `experiment_class == ablation`：

| Step | 条件 | 行为 | trace.rule |
|------|------|------|------------|
| 1 | blob 共现非空 | 只分共现到的 dataset（子集） | `ablation_blob_cooccurrence` |
| 2 | 无共现 + 配对 main 有 datasets | **深拷贝** `main.datasets`（已路由结果） | `ablation_inherit_main` |
| 3 | 无共现 + paper 内仅 1 个 comparison | 继承该 main.datasets | `ablation_inherit_single_mainline` |
| 4 | 以上均失败 | `datasets=[]` | `ablation_no_main_fallback_empty` |

**设计理由**：继承 `main_exp.datasets` 而非 `paper_datasets` 全量，是因为 main 已经过
共现 + 兜底路由，代表「该主线实际使用的 dataset 子集」；ablation 是对主线的组件消融，
应继承主线的 dataset 范围，而非 paper 级噪声并集。

**禁止**：
- ablation 接收 primary fallback 的未分配 paper dataset
- ablation 参与 broadcast
- ablation 直接读取 raw `paper_datasets` 全量

### main_exp 配对（`pairing.find_main_exp_for`）

供 ablation Step 2 使用；多 comparison 论文禁止默认 `experiments[0]`：

1. 候选仅限 `experiment_class == comparison`
2. 若恰好 1 个 comparison → 直接返回
3. 多 comparison：section 标题 token overlap（60%）+ experiment_name Jaccard（40%）打分
4. 最高分 ≤ 0 → 返回 None

### v1 vs v2 差异表

| 维度 | v1_cooccurrence | v2_type_aware |
|------|-----------------|---------------|
| field_study | blob 可绕过空集 | **强制 `[]`** |
| ablation | 仅 blob/window 共现 | 三级：blob → inherit main → single mainline → `[]` |
| window 匹配 | ±400 字符 | **同 section 内** token |
| broadcast 目标 | 全部 experiment | 仅 comparison/other |
| 默认策略 | 历史基线 | **当前最优** |

### v2 dev_20 实测改善

| 指标 | v1 | v2 | Δ |
|------|----|----|---|
| overall fuzzy F1 | 36.10% | 37.45% | +1.35 pp |
| multi-exp fuzzy F1 | 33.80% | 39.34% | +5.54 pp |
| field_study_empty_rate | 0% (0/2) | **100% (2/2)** | +100 pp |
| broadcast papers | 1 | 1 | — |

仍依赖 extract recall 上限：assign 无法补回 v4.3 未抽到的 dataset。

## 与评估的接口

`evaluator.evaluate_assignment(assigned_by_paper, gold_by_paper, multi_experiment_paper_ids)`
逐 `(paper_id, experiment_index)` 调 `shared.dataset_evaluator.evaluate_paper_datasets`
并聚合：

- overall P/R/F1（strict + fuzzy）
- multi_experiment 子集（dev_20 那 5 篇：`628304515`/`659e21469`/`661ddba81`/`6632f3d20`/`66bac1ca0`）
- broadcast 触发次数 / 触发论文数
- field_study experiment 空集命中率（assigned `datasets==[]` 且 gold 也 `==[]` 视为命中）
