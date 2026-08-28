# Datasets 提取策略 V3 报告 (最优配置)

## 策略概述

**策略名称**: datasets--策略v3--Gazetteer验证 (强语境正则+白名单+黑名单)

**最优配置**: 步骤1+2+3（扩展关键词 + 缩写+引用 + keyword_supplement）

**核心思想**: 通过Gazetteer白名单验证候选数据集，避免误报模型名和通用词，确保输出质量。

**Pipeline**:
1. **Stage 0**: strip_references - 移除参考文献
2. **Stage 1**: Section选段 - 数据集专用关键词 + keyword_supplement
3. **Stage 2**: 强语境正则提取 - 不解析表格，多种模式+缩写+引用
4. **Stage 3**: Gazetteer验证 - 基于批量提取结果的白名单（paper_count >= 2）
5. **Stage 4**: 黑名单过滤 - 过滤已知模型名

---

## 消融实验结果

| 配置 | Recall | Precision | F1 | 推荐 |
|------|--------|-----------|----|------|
| Baseline | 1.23% | 20.00% | 2.33% | - |
| + 扩展关键词 | 3.70% | 33.33% | 6.67% | ✅ |
| + 缩写+引用 | 6.17% | 29.41% | 10.20% | ✅ |
| + keyword_supplement | 7.41% | 26.09% | 11.54% | ✅ |
| + 放宽Gazetteer | 8.64% | 17.95% | 11.67% | ❌ (Precision大幅下降) |

详细消融实验: [v3_ablation_report.md](v3_ablation_report.md)

---

## dev_10 测评结果 (最优配置)

### 指标对比

| 策略 | Recall | Precision | F1 | Gold数据集 | 提取数据集 | 匹配数 | 漏抽数 | 多抽数 | 平均耗时(ms) |
|------|--------|-----------|----|-----------|-----------|-------|-------|-------|-----------|
| v1 (Section+Table) | 9.88% | 66.67% | 17.20% | 81 | 12 | 8 | 73 | 4 | 0.0 |
| v2 (关键词全文) | 29.63% | 7.59% | 12.09% | 81 | 316 | 24 | 57 | 286 | 0.0 |
| **v3 (Gazetteer最优)** | **7.41%** | **26.09%** | **11.54%** | 81 | 23 | 6 | 75 | 17 | 98.5 |

### 性能统计

- 平均总耗时: 98.52 ms
- P95 总耗时: 133.38 ms
- 平均candidate_extract: 32.03 ms
- 平均gazetteer_match: 54.39 ms

### Strip References 方法分布

- none: 3 篇

---

## 分析

### 优势
1. **Precision较高** (26.09%) - 仅次于v1 (66.67%)，远高于v2 (7.59%)
2. **避免表格误报** - 不解析他人工作的实验表格
3. **可追溯** - 每个数据集都来自Gazetteer，有明确的paper_count支撑
4. **完全无模型名误报** - 黑名单+Gazetteer双重保护

### 劣势
1. **Recall低于v1/v2** (7.41% vs 9.88% vs 29.63%)
2. **F1仍低于v1** (11.54% vs 17.20%)
3. **耗时较高** (98.5ms vs 0ms) - 预处理+Gazetteer匹配需要额外时间
4. **Gazetteer覆盖不足** (42.5%的gold数据集不在gazetteer中) - 这是硬上限

### 改进效果（相对Baseline）

| 指标 | Baseline | 最优 | 提升 |
|------|----------|------|------|
| Recall | 1.23% | 7.41% | +6.18pp (502%) |
| Precision | 20.00% | 26.09% | +6.09pp (30%) |
| F1 | 2.33% | 11.54% | +9.21pp (395%) |

---

## 漏抽/多抽案例

### 漏抽示例 (共75个)
- `IJB-A`, `IJB-B` - IJB系列数据集，gazetteer只有IJB-C
- `MegaFace` - 不在gazetteer中
- `VGGFace2`, `VGGFace` - 不在gazetteer中
- `CASIA-WebFace` - 不在gazetteer中（但CASIA-FASD在）

### 多抽示例 (共17个)
- 未命中gazetteer但强语境提取的候选被过滤

---

## 已知限制

1. **Gazetteer覆盖** - 基于2217篇论文，42.5% gold数据集未覆盖
2. **Survey论文** - 强语境模式主要针对实验论文
3. **无Fallback** - 第一版只输出Gazetteer命中项
4. **耗时** - 预处理和Gazetteer匹配需要额外时间

---

## 结论

**是否建议作为当前最佳策略**: **否**

**理由**:
1. v3最优F1 (11.54%) 仍低于 v1 (17.20%)
2. Recall (7.41%) 低于 v1 (9.88%) 和 v2 (29.63%)
3. 虽Precision高，但整体性能不及v1

**建议使用场景**:
- 作为v1/v2输出的**验证过滤器**（保留Gazetteer命中的高质量结果）
- 用于**数据分析**（统计常见数据集分布）
- 未来作为**多策略融合**的组成部分（v1提取 + v3验证）

**未来改进方向**:
1. 扩大Gazetteer覆盖（增加bulk论文数量）
2. 添加Fallback机制（非Gazetteer命中但强语境 → low confidence）
3. 与v1/v2融合

---

## 运行方式

```bash
# 测试v3最优配置
python -m experiments.rule_extraction.datasets.test_runner --strategy v3

# 对比所有策略
python -m experiments.rule_extraction.datasets.test_runner --compare-all
```

---

## 交付清单

- [x] `shared/dataset_preprocess.py` - 预处理模块（扩展关键词 + keyword_supplement）
- [x] `scripts/build_gazetteer.py` - Gazetteer构建脚本
- [x] `data/gazetteer.json` - 1253个数据集条目
- [x] `strategies/v3_gazetteer.py` - V3策略（启用缩写+引用）
- [x] `strategies/v3_ablation_report.md` - 消融实验报告
- [x] `strategies/v3_report.md` - V3报告（本文件）
- [x] `test_runner.py` - 增强版测试运行器（支持timing + trace）
- [x] `results/v3_on_dev10.json` - 测试结果
- [x] `analysis/comparison.md` - 对比报告