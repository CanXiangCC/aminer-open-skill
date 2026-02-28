# aminer-open-skill

把 AMiner 的学术数据能力，变成“开箱即用”的查询与分析 Skill。  
你只需要提供一个研究问题（查学者 / 查论文 / 查机构 / 查期刊 / 查专利），它就会自动走对应 API 工作流并输出结构化结果。

## 一句话了解这个 Skill

`aminer-data-search` 适合做学术信息检索和轻量分析。底层整合了 28 个 API，并封装成 6 类常用工作流，减少手动拼接口和字段对齐的成本。

## 能解决哪些问题

- 查某位学者：简介、研究方向、论文、专利、项目
- 查某篇/某类论文：详情、引用关系、关键词扩展
- 查某个机构：学者规模、论文产出、专利分布
- 查某个期刊：指定年份论文与主题追踪
- 用自然语言问学术问题：如“Transformer 最新进展”
- 查某个技术方向专利：并串联学者/机构专利关系

## 3 分钟上手

### 1) 准备 Token（必需）

在 AMiner 控制台生成 Token：  
https://open.aminer.cn/open/board?tab=control

### 2) 配置环境变量（推荐）

```bash
export AMINER_API_KEY="<YOUR_TOKEN>"
```

### 3) 运行示例

```bash
# 查学者画像
python skills/aminer-data-search/scripts/aminer_client.py \
  --action scholar_profile --name "Andrew Ng"

# 按标题深挖论文（含引用链）
python skills/aminer-data-search/scripts/aminer_client.py \
  --action paper_deep_dive --title "Attention is all you need"

# 分析机构研究力
python skills/aminer-data-search/scripts/aminer_client.py \
  --action org_analysis --org "清华大学"

# 自然语言问答式搜论文
python skills/aminer-data-search/scripts/aminer_client.py \
  --action paper_qa --query "transformer 架构最新进展"
```

## 常见使用方式

- **按任务走工作流**：适合“给我完整结果”的需求（如 scholar_profile、paper_deep_dive）
- **按接口精细调用**：适合“只调一个 API”的需求（`--action raw` + `--api` + `--params`）
- **按成本控制策略**：先免费/低价接口定位目标，再调用高价详情接口

## 目录说明

- `skills/aminer-data-search/SKILL.md`：完整能力说明、工作流设计、调用约束
- `skills/aminer-data-search/scripts/aminer_client.py`：Python 客户端与命令行入口
- `skills/aminer-data-search/references/api-catalog.md`：28 个 API 参数与路径速查
- `skills/aminer-data-search/evals/evals.json`：评测用例与测试样例

## 注意事项

- 没有 Token 时不要继续调用 API（可用 `AMINER_API_KEY` 或 `--token`）
- 客户端已内置超时重试与部分降级策略，能提升请求稳定性
- 部分 API 为计费接口，建议先确认场景再放大调用规模

## 参考资料

- AMiner 开放平台文档：https://open.aminer.cn/open/doc
- Skill 详细文档：`skills/aminer-data-search/SKILL.md`
