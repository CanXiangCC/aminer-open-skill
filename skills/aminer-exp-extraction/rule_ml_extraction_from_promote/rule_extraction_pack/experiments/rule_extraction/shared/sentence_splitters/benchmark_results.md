# 句子切分方案基准测试 - Sentence Splitter Benchmark

## 测试时间
2026-07-01

## 测试样本

| 样本 | 期望句子数 |
|------|-----------|
| 包含缩写 (Dr., Prof.) | 3 |
| 简单句 | 3 |
| 多个缩写 (U.S., Fig., Sec.) | 3 |

## 测试结果

### Regex Splitter
- **准确率**: 3/3 (100%)
- **所有测试通过**: ✓

### NLTK Splitter
- **状态**: 不可用（需要下载punkt_tab数据）
- **结论**: 不推荐（需要额外依赖）

## 最终选择

**推荐方案**: `regex` (正则切分器)

### 选择理由
1. **零依赖**: 不需要额外安装NLTK或下载数据
2. **准确率**: 在测试用例中达到100%
3. **轻量**: 代码简洁，易于维护
4. **边界处理**: 正确处理常见缩写（Dr., Prof., Ph.D., U.S., Fig., Sec.等）

### 实现要点
```python
from experiments.rule_extraction.shared.utils import extract_first_n_sentences

# 使用方法
sentences = extract_first_n_sentences(text, n=3, method='regex')
```

### 已处理的缩写列表
- Dr., Mr., Mrs., Ms., Prof.
- Ph.D., M.D., B.S.
- U.S., U.K., e.g., i.e.
- Fig., Sec., Eq., vs.
- et al., etc.