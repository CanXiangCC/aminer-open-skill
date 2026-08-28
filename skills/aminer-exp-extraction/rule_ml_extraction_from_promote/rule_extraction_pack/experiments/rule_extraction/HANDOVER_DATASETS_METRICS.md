# 规则提取交接文档 - Datasets / Sample_Size / Metrics

## 项目背景

实验信息提取系统，从Markdown论文中提取结构化实验数据。已完成的规则提取：
- ✓ **conclusion**: v1策略, 90%成功率
- ✓ **limitations**: vK策略, 44.4%覆盖率, 见 [`limitations/analysis/best_strategy_vK.md`](limitations/analysis/best_strategy_vK.md)

---

## 待开发字段

| 字段 | 类型 | 描述 | 优先级 |
|------|------|------|--------|
| **datasets** | array | 数据集名称、类型、样本大小等 | 高 |
| **sample_size** | number | 整体样本数量 | 中 |
| ~~**metrics**~~ | array | 评估指标名称 | **已由 LLM 提取（2026-07-06 决策，见 [`metrics/DECISION.md`](metrics/DECISION.md)）** |

> **Metrics（2026-07-06）**：不推进 rule extraction；与 `key_results` 等同批 LLM 输出，token 小收益大。M1 gazetteer 实验仅作存档。

---

## 数据结构定义

### Datasets (schemas/experiment_v1.schema.json)

```json
{
  "name": string,              // 数据集名称
  "aliases": array,            // 别名（用于实体解析）
  "dataset_type": enum,        // text/image/video/audio/multimodal/tabular/timeseries/sensor/medical/biological/chemical/material/simulation/industrial/other
  "description": string,       // 数据集描述
  "sample_size": number|null,  // 样本数量
  "is_public": boolean|null,   // 是否公开
  "is_self_collected": boolean|null,  // 是否自建
  "urls": array,               // 访问URL
  "github_urls": array,        // GitHub URL
  "doi_list": array,           // DOI
  "cstr_list": array           // CSTR
}
```

### Sample Size

```json
"sample_size": number  // 整体样本数量，可为null
```

### Metrics

```json
"metrics": array<string>  // 评估指标名称列表
```

---

## 实验框架参考

### 目录结构

```
experiments/rule_extraction/
├── shared/                    # 共享工具
│   ├── utils.py              # 句子切分、Markdown清理
│   └── ...
├── limitations/              # Limitations实验（已完成）
│   ├── strategies/
│   │   └── vK_enhanced_filter.py  # vK策略
│   ├── results/
│   │   └── vK_on_dev10.json
│   ├── analysis/
│   │   └── best_strategy_vK.md
│   └── test_runner.py
└── conclusion/               # Conclusion实验（已完成）
    └── ...
```

### 测试流程模板

参考 `limitations/test_runner.py`:

```python
# 1. 加载Gold数据
gold_data = load_gold_data("dev_10")  # 9篇论文有数据

# 2. 加载manifest
manifest = load_manifest("dev_10")

# 3. 运行策略测试
for item in manifest:
    paper_id = item["paper_id"]
    gold = gold_data.get(paper_id)
    md_text = load_paper_md(item["md_path"])
    result = Strategy.extract(md_text)

# 4. 保存结果
save_result(results, strategy_id)

# 5. 生成对比报告
generate_report(all_results)
```

---

## 共享工具 (shared/utils.py)

```python
# 提取section内容
extract_section_by_keywords(md_text, keywords)

# 句子切分
extract_first_n_sentences(text, n, method="regex")  # 推荐regex

# Markdown清理
clean_markdown_text(text)  # 移除LaTeX、脚注、引用、链接、表格、代码块
```

---

## Gold数据位置

```
data/gold/dev_10/full_text_glm5_2/
├── 5b1643ba8fbcbf6e5a9bc884.json
├── 627c6cfe5aee126c0f83214c.json
└── ... (共10篇)
```

每个文件包含完整experiment对象，查看datasets/metrics/sample_size字段。

---

## 关键原则

1. **独立开发**: 所有代码在 `experiments/rule_extraction/` 目录，不修改主代码库
2. **Demo-driven**: 先写单个模块测试，输出到 `output/debug/{module}/`
3. **完整记录**: 每个策略都有详细报告和结果JSON
4. **结果驱动**: 以测试数据选择最佳策略
5. **保护现有实验**: `limitations/` 和 `conclusion/` 完全不动

---

## 运行命令

```bash
cd d:\Zhipu_Intern\experiment_points_extraction

# 运行单个策略
python experiments/rule_extraction/你的模块/test_runner.py --strategy v1

# 对比所有策略
python experiments/rule_extraction/你的模块/test_runner.py --compare-all
```

---

## 代码结构模板

```python
"""
数据集提取策略 - v1
Strategy: Datasets Extraction v1
"""

import re
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import extract_first_n_sentences, clean_markdown_text


class DatasetsRuleV1:
    """数据集提取规则 - Datasets Extraction Rule - V1"""

    # Section标题关键词
    DATASET_SECTION_KEYWORDS = [
        "dataset",
        "datasets",
        "data",
        "experimental setup",
        "materials",
    ]

    @staticmethod
    def extract(paper_md: str) -> Optional[List[Dict[str, Any]]]:
        """提取数据集"""
        # 1. 查找Datasets section
        # 2. 提取数据集名称、类型、样本大小
        # 3. 返回格式化的数据集列表
        pass


if __name__ == "__main__":
    # 测试
    test_md = """
# Datasets
We use ImageNet-1k with 1.28M images for training.
    """
    result = DatasetsRuleV1.extract(test_md)
    print(f"Extracted datasets: {result}")
```

---

## 输出格式

### test_runner.py 输出

```json
{
  "strategy_id": "v1",
  "strategy_name": "datasets--策略v1--section提取",
  "test_time": "2026-07-02T12:00:00",
  "batch": "dev_10",
  "papers": [
    {
      "paper_id": "xxx",
      "gold": [...],  // 从gold文件中读取
      "rule": [...],  // 策略提取结果
      "success": true  // 非null即为success
    }
  ],
  "summary": {
    "total": 9,
    "success": 7,
    "fail": 2,
    "success_rate": 0.777
  }
}
```

### analysis/comparison.md 输出

```markdown
# Datasets字段策略对比分析

## 策略概览
| 策略 | 成功率 | 成功数 | 失败数 |
|------|--------|--------|--------|
| datasets--策略v1--section提取 | 77.8% | 7 | 2 |

## 详细结果
...
```

---

## 下一步

1. 分析Gold数据中的datasets/metrics/sample_size字段模式
2. 设计初步策略（Section提取 → 关键词匹配 → 正则表达式）
3. 实现第一个策略（v1）
4. 运行测试，分析结果
5. 迭代改进（v2, v3...）
6. 选择最佳策略，记录到 `analysis/best_strategy_字段.md`

---

## 联系方式

如有问题，查看：
- 已完成的limitations实验: `experiments/rule_extraction/limitations/`
- 共享工具: `experiments/rule_extraction/shared/utils.py`
- Schema定义: `schemas/experiment_v1.schema.json`