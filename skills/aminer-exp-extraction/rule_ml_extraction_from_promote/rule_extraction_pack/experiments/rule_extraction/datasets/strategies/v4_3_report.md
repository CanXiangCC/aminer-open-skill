# v4.3 Union Ensemble (语境收紧 + Gazetteer扩充) — 当前最优

> **当前最优方案** (dev_10, fuzzy F1 = 56.14%)
> v4.4 (20K 自动重建 gazetteer) 未能超越本方案，详见 [v4_4_report.md](v4_4_report.md)。

相对 v4.2 的两项改动：

| 改动 | 说明 |
|------|------|
| Channel B 语境过滤 | abbrev_ref / camel_case 需邻近 `dataset/benchmark/eval` 语境；表格行过滤 method/metric 表头 |
| Gazetteer 扩充 | 补 ~25 条 face recognition 子领域（IJB-A/B、VGGFace/2、UMDFaces、WebCaricature、YTF、FERET、CelebFaces+、RFW、CPLFW/CALFW/SLLFW/DELFW/DFW/ELFW、FAM、AR Face、AsianCeleb、BU-3DFE、CASIA-HFB、NIR-VIS 2.0、MS1M） |

## 运行

```bash
python experiments/rule_extraction/datasets/test_runner.py --strategy v4_3 --run-id 20260703_v4_3_eval
```

对比 v4.1 / v4.2 / v4.3：

```bash
python experiments/rule_extraction/datasets/test_runner.py --strategy v4_1 --run-id 20260703_v4_3_eval --eval-modes fuzzy
python experiments/rule_extraction/datasets/test_runner.py --strategy v4_2 --run-id 20260703_v4_3_eval --eval-modes fuzzy
python experiments/rule_extraction/datasets/test_runner.py --strategy v4_3 --run-id 20260703_v4_3_eval --eval-modes fuzzy
python experiments/rule_extraction/datasets/analysis/generate_comparison.py --run-dir experiments/rule_extraction/datasets/runs/20260703_v4_3_eval
```

## trace 字段

- `branch_a`: v4.1 输出统计
- `branch_b`: loose 候选（语境过滤后）→ gazetteer → blacklist
- `merge`: `v4_1_only` / `gazetteer_only` / `both`
- `tightening`: 标记本版收紧项
