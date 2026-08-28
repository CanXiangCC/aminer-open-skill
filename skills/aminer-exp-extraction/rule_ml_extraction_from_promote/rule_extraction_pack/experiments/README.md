# Experiments

## Section-Union Multi3 LLM Benchmark

对比 **section_union + glm-4.5-AirX** 策略下：

- **Baseline**：3 篇论文各 1 次 LLM 调用（串行）
- **Multi**：3 篇 section-union 正文合并为 1 次 LLM 调用

测量纯 LLM API 耗时与 input/output tokens 差异。不含预处理/路由时间，不做 evaluation 打分。

### 前置

- `.env` 中配置 `ZHIPUAI_API_KEY`
- 项目根目录激活 venv：`.\venv\Scripts\Activate.ps1`

### 运行

```powershell
cd d:\Zhipu_Intern\experiment_points_extraction

# 仅收集 section-union body（不调 API）
python experiments/section_union_multi3_bench/run_benchmark.py --batch dev_10 --skip-llm

# 指定 3 篇 smoke test
python experiments/section_union_multi3_bench/run_benchmark.py `
  --batch dev_10 `
  --paper-id 53e9a3fbb7602d9702d13e26 `
  --paper-id 5b1643ba8fbcbf6e5a9bc884 `
  --paper-id 627c6cfe5aee126c0f83214c

# 自动从 manifest 选前 3 篇 section_union 成功者
python experiments/section_union_multi3_bench/run_benchmark.py --batch dev_10

# dev_20 全量对比（6 组×3 篇 + 1 组×2 篇 = 7 次 LLM）
python experiments/section_union_multi3_bench/run_benchmark.py `
  --batch dev_20 `
  --full-batch `
  --output-dir experiments/section_union_multi3_bench/output/dev_20
```

### 输出

`experiments/section_union_multi3_bench/output/`：

| 路径 | 含义 |
|------|------|
| `bodies/{paper_id}.json` | section-union `body_text` 缓存 |
| `skipped.json` | fallback 或非 section_union 篇目 |
| `baseline_single/` | 3 次单篇 raw + parsed |
| `multi3/` | 1 次三文档 raw + 按 paper 拆分 parsed |
| `report.json` / `report.md` | 对比指标 |

### 指标说明

| 指标 | 含义 |
|------|------|
| `baseline_total_llm_ms` | 3 次单篇 LLM 墙钟耗时之和 |
| `multi_llm_ms` | 1 次三文档 LLM 墙钟耗时 |
| `llm_time_saved_pct` | `(baseline - multi) / baseline × 100%` |
| `input_token_saved_pct` | 同上，基于 API usage 的 input tokens |
| `parse_ok_baseline` / `parse_ok_multi` | JSON 解析 + schema normalize 成功篇数 |

### 限制

- 仅 `path_taken == section_union` 的论文参与对比；full_text fallback 记入 `skipped.json`
- Multi 模式使用专用 prompt：`src/llm/chunk_baseline_multi3.txt`（不修改 `chunk_baseline.txt`）
- 不修改正式 `orchestrator` / strategy runner 行为
- 预处理时间两边相同，**不计入**节省比例

### 测试

```bash
pytest tests/experiments/test_section_union_multi3_bench.py -q
```

***

## Rule Extraction Experiments

在独立的实验目录中，通过多方案对比测试，为每个字段找到最佳规则提取策略。

### 实验结构

```
experiments/rule_extraction/
├── shared/                           # 共享工具
│   ├── sentence_splitters/           # 句子切分方案对比
│   ├── markdown_cleaners/            # Markdown清理工具
│   └── utils.py                      # 共享函数
│
├── conclusion/                       # conclusion字段实验
│   ├── strategies/                   # 各策略实现
│   ├── results/                      # 测试结果
│   └── analysis/                     # 结果分析
│
└── limitations/                      # limitations字段实验
    └── (同上结构)
```

### 已完成实验

#### Conclusion字段
- **最佳策略**: `conclusion--策略v1--section提取`
- **成功率**: 90.0% (9/10)
- **测试时间**: 2026-07-01

#### Limitations字段
- **最佳策略**: `limitations--策略K--vH增强过滤`
- **成功率**: 44.4% (4/9)
- **准确率**: ~50% (2篇完全准确)
- **测试时间**: 2026-07-02
- **详情**: 见 [`limitations/analysis/best_strategy_vK.md`](limitations/analysis/best_strategy_vK.md)

#### Metrics字段
- **决策（2026-07-06）**: **LLM 直接提取**，不采用 rule extraction
- **理由**: metrics 输出 token 小、收益高；M1 规则基线 fuzzy F1 ~28%，precision 不足
- **生产**: `src/llm/*_baseline.txt` + `merger.py` `LLM_FIELDS`
- **M1 实验存档**: [`rule_extraction/metrics/DECISION.md`](rule_extraction/metrics/DECISION.md)

#### Evidence字段
- **实验最优（2026-07-07）**: **`evidence--策略v4--clean_mswr_rerank_dynamic`** — wf8 R1–R4 洗句 + v3 MSWR
- **dev_10**: product_pass YES；noise 4.92%；relevance 40.98%；traceable 100%
- **参考 run**: `rule_extraction/evidence/runs/20260707_evidence_v4_dev10/`
- **决策记录**: [`rule_extraction/evidence/DECISION.md`](rule_extraction/evidence/DECISION.md)
- **生产**: `merger.py` 仍 LLM 输出 evidence；v4 **未接入** orchestrator
- **运行**: `python -m experiments.rule_extraction.evidence.test_runner --strategy v4 --batch dev_10`

### 共享工具基准测试

#### 句子切分
- **推荐方案**: `regex` (正则切分器)
- **准确率**: 100% (测试用例)
- **零依赖**: 不需要NLTK

### 运行命令

```bash
# 测试Conclusion所有策略
cd d:\Zhipu_Intern\experiment_points_extraction
python experiments/rule_extraction/conclusion/test_runner.py --compare-all

# 测试Limitations所有策略
python experiments/rule_extraction/limitations/test_runner.py --compare-all

# 查看测试结果
cat experiments/rule_extraction/conclusion/analysis/comparison.md
cat experiments/rule_extraction/limitations/analysis/comparison.md
```

### 重要原则

1. **独立开发**: 所有代码在 `experiments/rule_extraction/` 目录，不修改主代码库
2. **保护现有实验**: `experiments/section_union_multi3_bench/` 完全不动
3. **完整记录**: 每个测试都有详细报告，clear后可恢复理解
4. **策略命名**: 统一格式 `field--策略[编号]--[描述]`
5. **结果驱动**: 以测试数据选择最佳策略，不以主观判断
6. **阶段性集成**: 所有字段开发完成后再考虑集成到主代码库