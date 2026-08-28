# Limitations字段实验 - Limitations Field Experiments

## 最佳策略 (已采纳)

**vK - vH增强过滤** (2026-07-02)

- **覆盖率**: 44.4% (4/9)
- **准确率**: ~50% (2篇完全准确)
- **详情**: [`analysis/best_strategy_vK.md`](analysis/best_strategy_vK.md)

## 策略演进

| 代际 | 策略 | 覆盖率 | 准确率 | 状态 |
|------|------|--------|--------|------|
| v1 | Section提取 | 22.2% | 高 | ✓ 高质量低覆盖 |
| v2 | Conclusion内搜索 | 22.2% | 高 | ✓ 高质量低覆盖 |
| v3 | 全文模糊匹配 | 100% | 极低 | ✗ 不推荐 |
| v4 | 多源融合 | 100% | 低 | ✗ 继承v3问题 |
| v5 | 三层分层 | 88.9% | 中 | 基础分层框架 |
| vH | 增强引用删除 | 100% | ~15% | ✗ 大量误匹配 |
| vK | **增强过滤** | **44.4%** | **~50%** | **✓ 当前最佳** |

## vK核心改进

### 过滤规则
- Section标题过滤（大写LIMITATION）
- Future Work过滤
- 方法介绍过滤
- 对比工作过滤
- 积极内容过滤
- 消极词验证
- 自指验证（however/but/although/despite）

## 运行命令
```bash
cd d:\Zhipu_Intern\experiment_points_extraction
python experiments/rule_extraction/limitations/test_runner.py --strategy vK
```