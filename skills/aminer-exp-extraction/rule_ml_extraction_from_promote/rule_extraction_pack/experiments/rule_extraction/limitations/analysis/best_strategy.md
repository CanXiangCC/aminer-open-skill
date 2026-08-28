# Limitations字段 - 最佳策略

## 当前状态

**无法确定唯一最佳策略**

## 策略对比

| 策略 | 成功率 | 质量 | 推荐 |
|------|--------|------|------|
| v1 - section提取 | 22.2% | 高 | ⚠️ 条件推荐 |
| v2 - conclusion内搜索 | 22.2% | 高 | ⚠️ 条件推荐 |
| v3 - 全文模糊匹配 | 100% | 极低 | ❌ 不推荐 |
| v4 - 多源融合 | 100% | 极低 | ❌ 不推荐 |

## 详细分析

### v1/v2: 高质量低覆盖率

**成功案例** - 论文 `63b63fca90e50fcafd8f4461`:
- **规则提取**: "There is a domain gap between the manually degraded low-quality dataset and the dataset based on the surveillance scenes, resulting in CQIL not being able to take full advantage of encoders trained on low-quality data in real surveillance scenes."
- **Gold标准**: "There is a domain gap between the manually degraded low-quality dataset and the dataset based on the surveillance scenes, resulting in CQIL not being able to take full advantage of encoders trained on low-quality data in real surveillance scenes."
- **评估**: 完美匹配！

**失败原因**: 大多数论文没有独立的"Limitations" section

### v3/v4: 高覆盖率极低质量

**问题**:
1. 提取到其他方法的limitations（在survey论文中）
2. 提取到section介绍文字
3. 无法区分"本文的limitations"和"其他方法的limitations"

**示例失败**:
```
Paper: 5b1643ba8fbcbf6e5a9bc884 (survey)
Gold: "由于隐私问题，公开可用的训练数据库大多从名人的照片中收集..."
Rule: "Fg-net aging database. http://www.fgnet.rsunit.com."
```

## 建议方案

### 方案A: 条件式使用v1/v2

**适用场景**: 有独立Limitations section的论文
- 先尝试v1 (section提取)
- v1失败时尝试v2 (conclusion内搜索)
- 两者都失败时返回None

**优点**: 高质量，可信任
**缺点**: 覆盖率低（~22%）

### 方案B: 改进版模糊匹配

**改进方向**:
1. 排除"Introduction", "Related Work", "Background"等section
2. 只在"Discussion", "Conclusion"等section内搜索
3. 优先匹配包含"our", "proposed", "this work"等自指关键词
4. 使用语义相似度而非简单关键词匹配

**优点**: 可能提高质量和覆盖率
**缺点**: 实现复杂，需要更多测试

### 方案C: 混合策略

**逻辑**:
1. v1/v2优先（高质量）
2. 失败时使用改进版v3
3. 最终由LLM验证和补充

## 最终选择

**推荐**: `方案A - 条件式使用v1/v2`

**理由**:
1. 可信度高：提取内容与Gold完全一致
2. 实现简单：复用现有代码
3. 可扩展：后续可添加更复杂的fallback

**使用方式**:
```python
# 优先v1
result = LimitationsRuleV1.extract(paper_md)
if not result:
    # v1失败，尝试v2
    result = LimitationsRuleV2.extract(paper_md)
# 两者都失败，返回None，让LLM处理
```

## 后续工作

1. 实现"改进版模糊匹配"作为v5
2. 对比v5与v1/v2的质量和覆盖率
3. 考虑与Conclusion提取类似，对survey论文做特殊处理

## 适用范围

- ✅ 有独立Limitations section的论文
- ✅ Limitations集成在Conclusion中的论文
- ❌ Survey论文（limitations分散在多处）
- ❌ Limitations表述不明确的论文