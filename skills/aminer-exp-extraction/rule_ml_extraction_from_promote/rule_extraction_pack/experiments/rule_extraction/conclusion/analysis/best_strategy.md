# Conclusion字段 - 最佳策略

## 最终选择
**conclusion--策略v5--三层分层（2026-07-01修复版）**

## 选择理由
1. **成功率**: 90.0% (9/10)
2. **质量远高于v1**: 9/10篇提取到真正总结（v1提取回顾内容）
3. **智能提取**:
   - 总结信号优先（overall/in summary等）
   - 跳过Limitations/Future Work子标题
   - 无信号时取section后半部分

## v5 vs v1质量对比

| Paper ID | v1提取 | v5提取 | Gold | 评价 |
|----------|--------|--------|------|------|
| 627c6cfe5aee126c0f83214c | "In this paper, we make a survey..." | "There are still several crucial challenges..." | ✅ | v5是总结 |
| 62fdae3890e50fcafdd6387b | "In this paper, we analyze..." | "We integrate...outperforms..." | ✅ | v5是总结 |
| 661ddba813fb2c6cf6b5d7e6 | "Home robots intend..." | "identifies over 90%..." | ✅ | v5是结果 |
| 53e9a3fbb7602d9702d13e26 | "We present a novel..." | "Our work has revealed that the fusion..." | ✅ | v5非常接近Gold |

## 失败案例分析

唯一失败的论文: `5b1643ba8fbcbf6e5a9bc884`
- **类型**: Survey论文
- **原因**: 无独立Conclusion section，结论分散
- **对策**: 这类论文需要特殊处理，或接受规则提取失败

## 实现要点

```python
from experiments.rule_extraction.conclusion.strategies.v5_layered import ConclusionRuleV5

# 使用方法
result = ConclusionRuleV5.extract(paper_md, max_sentences=3)
```

### Layer 1: 增强标题匹配（主要逻辑）
```python
# 1. 查找Conclusion section
# 2. 查找总结信号句（overall, in summary, finally等）
#    - 找到: 提取 前1句 + 信号句 + 后1句
#    - 未找到: 跳过Limitations/Future Work，取后N句
```

### Layer 2/3: Fallback
- Layer 2: Discussion section + 自指验证
- Layer 3: 后50%文章 + 关键词验证

## 集成建议

当集成到主代码库时:
1. 优先使用v5规则提取
2. 规则失败时，记录fallback原因
3. 让LLM作为补充手段

## 测试命令

```bash
# 测试v5
python -m experiments.rule_extraction.conclusion.test_runner --strategy v5

# 对比所有策略
python -m experiments.rule_extraction.conclusion.test_runner --compare-all
```

## 相关文件

- 实现代码: `experiments/rule_extraction/conclusion/strategies/v5_layered.py`
- 测试结果: `experiments/rule_extraction/conclusion/results/v5_on_dev10.json`
- 对比报告: `experiments/rule_extraction/conclusion/analysis/comparison.md`