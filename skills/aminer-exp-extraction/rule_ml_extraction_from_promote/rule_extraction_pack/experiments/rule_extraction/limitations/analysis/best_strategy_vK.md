# Limitations字段 - 最佳策略 vK

## 最终选择

**策略**: `vK - vH增强过滤`

**状态**: **已采纳为主要策略**

## 性能

- **覆盖率**: 44.4% (4/9)
- **准确提取率**: ~50% (2篇完全准确，1篇可能正确)
- **误匹配率**: ~25% (1篇survey对比工作误匹配)

## 策略描述

基于vH增强过滤，核心改进：

### 过滤规则
1. **Section标题过滤**: 排除大写"LIMITATION"标题
2. **Future Work过滤**: 排除"FUTURE RESEARCH DIRECTIONS"
3. **方法介绍过滤**: 排除"In addition, we propose"/"In our work, we focus"
4. **对比工作过滤**: 
   - "effective methods for"
   - "[A-Z][a-z]+\. proposed"
5. **积极内容过滤**: 排除"benefits from"/"achieves SOTA"
6. **背景介绍过滤**: 排除"Due to ... limitations,"
7. **消极词验证**: 必须包含"limitation"/"cannot"/"fails to"等消极词
8. **自指验证**: "however"/"but"/"although"/"despite"/"on the other hand"必须有"our"/"we"/"this work"

### 信号词优先级
```
however, but, although, despite, nevertheless, nonetheless,
on the other hand, limitation, limitations, shortcoming,
constraint, limited to, fails to
```

### 提取流程
```
1. 预处理: 删除References section + 混杂引用检测
2. Layer 1: Conclusion中找信号句（带严格过滤）
3. Layer 2: 全文后20%找信号句（带严格过滤）
4. Layer 3: 取消，直接返回None（宁可漏判不误判）
```

## 测试结果详情

| Paper | 提取质量 | 说明 |
|-------|----------|------|
| 62fdae3890e50fcafdd6387b | ✓ 完全准确 | 提取到"Limitation. Despite its robustness..." |
| 63b63fca90e50fcafd8f4461 | ✓ 完全准确 | 提取到"However, there is a domain gap..." |
| 627c6cfe5aee126c0f83214c | ? 可能正确 | "Datasets and evaluation metrics... Although..." |
| 5b1643ba8fbcbf6e5a9bc884 | ✗ 误匹配 | survey论文对比工作"DFM utilized..." |
| 其他5篇 | - | 未能提取 |

## 已知限制

1. **Survey论文**: 容易提取到对比工作的limitations而非本文的
2. **无自指表述**: 某些论文的limitations不使用"our"/"we"，可能被过滤
3. **非Conclusion表述**: limitations可能在Discussion/Experiments中，不在Conclusion末尾

## 后续改进方向

1. **Survey论文特殊处理**: 检测survey特征，调整过滤策略
2. **自指关键词扩展**: 增加"this approach"/"the proposed method"等
3. **多layer扩展**: 添加Discussion/Experiments section搜索
4. **语义相似度**: 替代关键词匹配，提高准确率

## 文件位置

- 策略实现: [`strategies/vK_enhanced_filter.py`](strategies/vK_enhanced_filter.py)
- 测试结果: [`results/vK_on_dev10.json`](results/vK_on_dev10.json)
- 测试运行: [`test_runner.py`](test_runner.py) --strategy vK

## 运行命令

```bash
cd d:\Zhipu_Intern\experiment_points_extraction
python experiments/rule_extraction/limitations/test_runner.py --strategy vK
```

## 实验时间

2026-07-02 (vK最终版本)