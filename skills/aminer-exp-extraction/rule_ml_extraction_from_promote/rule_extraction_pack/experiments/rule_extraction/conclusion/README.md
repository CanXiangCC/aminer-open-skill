# Conclusion字段实验 - Conclusion Field Experiments

## 实验时间
2026-07-01 (v5修复)

## 测试集
dev_10 (10篇论文)

## 策略对比

| 策略 | 描述 | 成功率 | 质量 | 推荐度 |
|------|------|--------|------|--------|
| v1 | 直接提取Conclusion section前N句 | 90.0% | ❌ 提取回顾内容 | ⭐ |
| v2 | 匹配多种Conclusion变体标题 | 30.0% | - | ⭐ |
| v3 | Section + 关键词双重验证 | 30.0% | - | ⭐ |
| v5 | 总结信号优先+子标题跳过 | 90.0% | ✅ 提取真正总结 | ⭐⭐⭐⭐⭐ |

## 最佳策略

**conclusion--策略v5--三层分层（已修复）**

### 成功率
- 成功提取: 9/10
- 失败: 1/10 (survey论文，无独立Conclusion section)

### v5改进（2026-07-01）
**问题**: v1提取Conclusion section的**前N句**，但真正的总结往往在section后半部分或以总结信号开头。

**解决方案**:
1. Layer 1: 总结信号优先（overall/in summary等），提取"前1句+信号句+后1句"
2. 无信号时: 跳过Limitations/Future Work子标题，取之前内容的后N句
3. Layer 2/3: 作为fallback（针对无Conclusion section的论文）

### v5 vs v1质量对比
| Paper ID | v1提取 | v5提取 | 评价 |
|----------|--------|--------|------|
| 627c6cfe5aee126c0f83214c | "In this paper, we make a survey..." | "There are still several crucial challenges..." | ✅ v5是总结 |
| 62fdae3890e50fcafdd6387b | "In this paper, we analyze..." | "We integrate this supervision...outperforms..." | ✅ v5是总结 |
| 661ddba813fb2c6cf6b5d7e6 | "Home robots intend to make..." | "identifies over 90% of anomalous..." | ✅ v5是结果 |
| 53e9a3fbb7602d9702d13e26 | "We present a novel..." | "Our work has revealed that the fusion..." | ✅ v5非常接近Gold |

**差异**: 9/10篇v5提取到真正总结，v1提取到回顾内容。

### 失败案例分析
唯一失败的论文: `5b1643ba8fbcbf6e5a9bc884`
- 类型: Survey论文
- 原因: 无独立Conclusion section，结论分散

## 测试结果详情

- **策略报告**: `strategies/v1_report.md`
- **对比分析**: `analysis/comparison.md`
- **最佳策略**: `analysis/best_strategy.md`

## 运行命令
```bash
cd d:\Zhipu_Intern\experiment_points_extraction
python experiments/rule_extraction/conclusion/test_runner.py --compare-all
```