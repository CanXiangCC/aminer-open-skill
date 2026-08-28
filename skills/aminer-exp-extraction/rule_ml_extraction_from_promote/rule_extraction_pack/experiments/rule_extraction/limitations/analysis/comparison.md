# Limitations字段策略对比分析
生成时间: 2026-07-01T17:48:12.525758
## 策略概览
| 策略 | 成功率 | 成功数 | 失败数 |
|------|--------|--------|--------|
| limitations--策略v1--section提取 | 22.2% | 2 | 7 |
| limitations--策略v2--conclusion内搜索 | 22.2% | 2 | 7 |
| limitations--策略v3--全文模糊匹配 | 100.0% | 9 | 0 |
| limitations--策略v4--多源融合 | 100.0% | 9 | 0 |
| limitations--策略v5--三层分层 | 88.9% | 8 | 1 |

## 详细结果

### limitations--策略v1--section提取
- 成功率: 22.2%

**失败案例** (7个):
- 5b1643ba8fbcbf6e5a9bc884: No limitations found
- 627c6cfe5aee126c0f83214c: No limitations found
- 62fdae3890e50fcafdd6387b: No limitations found
- 6632f3d201d2a3fbfc5b36bb: No limitations found
- 63b63fca90e50fcafd8f4461: No limitations found
- 659b6a62939a5f4082e8e6d7: No limitations found
- 64f00ff43fda6d7f06ececda: No limitations found

### limitations--策略v2--conclusion内搜索
- 成功率: 22.2%

**失败案例** (7个):
- 5b1643ba8fbcbf6e5a9bc884: No limitations found
- 62fdae3890e50fcafdd6387b: No limitations found
- 6632f3d201d2a3fbfc5b36bb: No limitations found
- 63b63fca90e50fcafd8f4461: No limitations found
- 659b6a62939a5f4082e8e6d7: No limitations found
- 53e9a3fbb7602d9702d13e26: No limitations found
- 64f00ff43fda6d7f06ececda: No limitations found

### limitations--策略v3--全文模糊匹配
- 成功率: 100.0%

### limitations--策略v4--多源融合
- 成功率: 100.0%

### limitations--策略v5--三层分层
- 成功率: 88.9%

**失败案例** (1个):
- 659b6a62939a5f4082e8e6d7: No limitations found
