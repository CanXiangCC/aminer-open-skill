# v4.4 — v4.3 策略 + gazetteer_20k（20K 论文自动重建）

## 定义

**v4.4 = v4.3 策略代码 + `gazetteer_20k.json`**

策略代码完全复用 v4.3（语境过滤 + 表格行过滤 + union 合并），通过 `--gazetteer-path`
切换 gazetteer 来源。差异只在 gazetteer 内容：

| gazetteer | 来源 | 条目数 | normalized_keys |
|-----------|------|--------|-----------------|
| 原始 | 早期批量提取 | 1,253 | 1,256 |
| 手动扩充 (v4.3 用) | 原始 + 25 条 face recognition | 1,277 | 1,280 |
| **gazetteer_20k (v4.4 用)** | 20K AI 论文 per_paper LLM 提取自动挖掘 | **7,442** | **7,840** |

## 动机

v4.3 的手动扩充 +25 face 数据集是针对 dev_10 survey 论文 (`5b1643ba`) 量身定制的，
存在过拟合 dev_10 的风险，难以泛化到 dev_20 或其它领域。v4.4 用 20K 论文语料自动
重建 gazetteer，目标是验证"自动大规模挖掘"能否替代"人工小规模精修"，并提供一个
不依赖 dev_10 人工知识的可推广基线。

## 运行方式

```bash
# v4.4 on dev_10
python experiments/rule_extraction/datasets/test_runner.py --strategy v4_3 \
  --batch dev_10 --run-id 20260703_gaz20k_v44_dev10_20k --eval-modes fuzzy \
  --gazetteer-path experiments/rule_extraction/datasets/data/gazetteer_20k.json

# v4.4 on dev_20 (Gold2 / paper_union)
python experiments/rule_extraction/datasets/test_runner.py --strategy v4_3 \
  --batch dev_20 --run-id 20260703_gaz20k_v44_dev20_20k --eval-modes fuzzy \
  --gazetteer-path experiments/rule_extraction/datasets/data/gazetteer_20k.json
```

`--gazetteer-path` 通过 `RULE_GAZETTEER_PATH` 环境变量同时作用于策略侧
(`v3_gazetteer._load_gazetteer`) 和评估侧 (`dataset_evaluator._load_gazetteer_aliases`)，
保证 alias 等价类与硬过滤用同一份 gazetteer。

## 评估结果

| batch | gold | R | P | F1 | survey F1 | non-survey F1 |
|-------|------|---|---|-----|-----------|---------------|
| dev_10 | Gold2 | 47.56% | 35.45% | **40.62%** | 45.33% | 37.61% |
| dev_20 | Gold2 | 56.41% | 19.30% | **28.76%** | 20.51% | 29.96% |
| dev_20 | Gold1 | 55.26% | 18.42% | **27.63%** | 20.51% | 28.68% |

## 与 v4.3 (手动扩充) 对比

| 设置 | v4.3 F1 | v4.4 F1 | Δ | 主要原因 |
|------|---------|---------|---|---------|
| dev_10 / Gold2 | **56.14%** | 40.62% | -15.52pp | precision 崩塌 53.93% → 35.45% |
| dev_20 / Gold2 | (未测) | 28.76% | — | precision 仅 19.30% |

### v4.4 退步根因

`gazetteer_20k.json` 条目数 7,442（vs 手动 1,277），`v3_gazetteer._match_gazetteer`
使用 **双向子串匹配**（`norm_key in candidate or candidate in norm_key`）：
- 条目越多 → 候选名被某个 gazetteer key 子串命中的概率大幅上升
- 大量低质量 loose 候选（如 `ASD`、`Tool`、`MMT`、`Net`）都能在 20K gazetteer
  中找到一条对应条目通过硬过滤
- 召回略升（更多真名被认出）但 precision 大幅下降，净 F1 显著退步

### 控制对照

- v4.1 用 manual 与 20k 两次跑结果完全一致 (F1=43.97%)，证明 v4.1 不依赖
  gazetteer，且 `--gazetteer-path` 切换确实生效（v4.3 切换后结果改变）。
- dev_20 Gold1 vs Gold2 差异很小 (27.63% vs 28.76%)，说明 union 去重对评估
  整体指标影响有限，但对多 experiment 论文（5 篇）的单篇指标会有差异。

## 结论

1. **v4.3 + 手动扩充仍为当前最优**（dev_10 F1=56.14%）。
2. 自动重建 gazetteer 单独替换不可行 — 20K 规模 + 子串匹配会导致 precision 崩塌。
3. 若要走自动挖掘路线，需配合以下任一改造（v4.5+ 方向）：
   - 收紧匹配：从双向子串改为精确 normalize 等价或长度门槛 + overlap 比例
   - 提高 `min_paper_count`（当前 =2）以过滤低频噪声条目
   - 对 gazetteer 条目做长度/语义黑名单过滤（类似 v4.3.1 的 `_match_gazetteer_tight`）

## 相关文件

- [`scripts/build_gazetteer_20k.py`](../scripts/build_gazetteer_20k.py) — 重建脚本
- [`data/gazetteer_20k.json`](../data/gazetteer_20k.json) — 7,442 条目
- [`data/gazetteer_20k_stats.json`](../data/gazetteer_20k_stats.json) — 统计
- [`runs/20260703_gazetteer_20k/summary_data.json`](../runs/20260703_gazetteer_20k/summary_data.json) — 完整指标
