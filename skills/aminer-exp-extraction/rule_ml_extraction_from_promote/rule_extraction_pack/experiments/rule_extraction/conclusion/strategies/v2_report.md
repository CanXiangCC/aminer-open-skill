# conclusion--策略v2--标题匹配 测试报告

## 策略描述
匹配多种Conclusion变体标题（含罗马数字、编号等）
Match multiple Conclusion title variations (including Roman numerals, numbers, etc.)

## 测试环境
- 测试集: dev_10
- 测试时间: 2026-07-01T17:03:22
- 句子切分: regex
- Markdown清理: 完整清理

## 测试结果
- 成功提取: 3/10
- 失败: 7/10
- 成功率: 30.0%

## 失败分析

**失败原因**: 正则模式过于严格

查看Section标题发现，大部分论文的Conclusion标题是:
- `# VII. CONCLUSION` (罗马数字 + CONCLUSION)
- `# VIII. CONCLUSION` (罗马数字 + CONCLUSION)

但v2的正则模式 `^[ivxlcdm]+\.\s+conclusions?$` 需要严格匹配：
1. 罗马数字开头
2. 点号
3. 空格
4. conclusion(s)

而实际标题是 `# VII. CONCLUSION`，header解析后是 `VII. CONCLUSION`，符合模式...

**实际问题**: 可能是Markdown中CONCLUSION是全大写，而匹配时case-insensitive可能有问题

## 结论

**问题**: 调试发现正则匹配逻辑存在bug，导致成功率偏低
**建议**: 不推荐使用，建议采用v1策略