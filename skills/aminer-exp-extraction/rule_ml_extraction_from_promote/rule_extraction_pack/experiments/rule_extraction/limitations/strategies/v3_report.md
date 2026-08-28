# limitations--策略v3--全文模糊匹配 测试报告

## 策略描述
全文搜索，返回最相关段落
Full text search, return most relevant paragraph

## 测试环境
- 测试集: dev_10 (9篇论文有limitations数据)
- 测试时间: 2026-07-01T17:11:13
- 句子切分: regex
- Markdown清理: 完整清理

## 测试结果
- 成功提取: 9/9 (100%)
- 失败: 0/9

## 质量评估

### 严重问题：内容相关性低

**示例1** - 论文 `5b1643ba8fbcbf6e5a9bc884`:
- **Gold标准**: "由于隐私问题，公开可用的训练数据库大多从名人的照片中收集，与日常生活中捕获的图像相去甚远。"
- **规则提取**: "Fg-net aging database. http://www.fgnet.rsunit.com."
- **评估**: 完全不相关 - extracted URL not the paper's limitations

**示例2** - 论文 `627c6cfe5aee126c0f83214c`:
- **Gold标准**: "Current datasets and evaluation metrics are not sufficient to achieve diverse and detailed captioning..."
- **规则提取**: "1) We make a comparison between AAC and similar or related tasks in Section II..."
- **评估**: 提取了section介绍，非limitation

### 问题分析

1. **关键词过于宽泛**: "limitation"这个关键词在学术论文中出现频率很高
2. **缺乏上下文过滤**: 不区分论文自己的limitations vs 描述其他方法的limitations
3. **Section无关**: 没有排除"Introduction", "Related Work"等非结论性section

## 结论

**不推荐**: 虽然覆盖率100%，但内容质量太低，无法使用

**问题根源**: 模糊匹配对长文本（如survey论文）失效，提取到不相关内容