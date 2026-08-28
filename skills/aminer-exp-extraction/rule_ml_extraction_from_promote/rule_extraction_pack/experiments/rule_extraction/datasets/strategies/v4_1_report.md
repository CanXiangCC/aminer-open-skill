# v4.1 收紧说明

相对 v4 的变更：

| 项 | v4 | v4.1 |
|----|----|------|
| camel_case | Layer A 启用 | **禁用** |
| abbrev_ref | 全文匹配 `[A-Z]{2,} [digits]` | **需 ±45/35 字符内出现 dataset/benchmark/eval 语境** |
| 表格解析范围 | 全部 Layer A section | **仅标题含 dataset/datasets/training data 等** |
| Layer B 关键词补充 | body hits ≥ 3 | **≥ 4** |
| 黑名单 | v3 模型名 | **+ BLEU/TER/NMT/ArcFace 等** |
| 表格行过滤 | v1 默认 | **跳过 method/metric 表头行** |

运行：

```bash
python experiments/rule_extraction/datasets/test_runner.py --strategy v4_1 --run-id 20260703_v4_1_tight
```

与 v4 baseline 对比：`runs/20260703_v4_baseline/` vs 新 run 的 `analysis/comparison.md`（若 `--compare-all` 含 v4_1）。
