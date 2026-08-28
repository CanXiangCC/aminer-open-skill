# v4.2 Union Ensemble

双通道合并策略：

| 通道 | 来源 | 作用 |
|------|------|------|
| A | v4.1（原样） | 高 precision，保留非 gazetteer / 自采集 dataset |
| B | v4 宽松候选 → v3 `_match_gazetteer` 硬过滤 | 补 survey / 标准 benchmark 召回 |

合并：按 `normalize_fuzzy` + gazetteer alias 等价类去重；冲突时**保留 v4.1 的 name 与 metadata**。

## 运行

```bash
python experiments/rule_extraction/datasets/test_runner.py --strategy v4_2 --run-id 20260703_v4_2_eval
```

与 v4.1 / v4 同 run 对比：

```bash
python experiments/rule_extraction/datasets/test_runner.py --strategy v4_1 --run-id 20260703_v4_2_eval --eval-modes fuzzy
python experiments/rule_extraction/datasets/test_runner.py --strategy v4 --run-id 20260703_v4_2_eval --eval-modes fuzzy
python experiments/rule_extraction/datasets/test_runner.py --strategy v4_2 --run-id 20260703_v4_2_eval --eval-modes fuzzy
python experiments/rule_extraction/datasets/analysis/generate_comparison.py --run-dir experiments/rule_extraction/datasets/runs/20260703_v4_2_eval
```

## trace 字段

- `branch_a`: v4.1 输出统计
- `branch_b`: loose 候选 → gazetteer → blacklist
- `merge`: `v4_1_only` / `gazetteer_only` / `both`
