# v4.3.1 Union (语境过滤 + 表格行过滤 + Gazetteer硬过滤收紧，不扩充)

相对 v4.2（原始 gazetteer）的三项收紧：

| 改动 | 说明 |
|------|------|
| Channel B 语境过滤 | abbrev_ref / camel_case 需邻近 `dataset/benchmark/eval` 语境 |
| Channel B 表格行过滤 | 跳过含 `method/acc/miou/map` 的表头行 |
| Gazetteer 硬过滤收紧 | canonical 长度 ≥ 4；弱语义黑名单（other/lbp/fasd/npu/gabor/deepface/aid/sun/ar）；overlap ≥ 0.7；只允许 candidate ⊂ canonical 单向子串 |

**不扩充 gazetteer**：使用原始 1253 条 gazetteer。

## 运行

```bash
python experiments/rule_extraction/datasets/test_runner.py --strategy v4_3_1 --run-id 20260703_v4_3_1_eval
```
