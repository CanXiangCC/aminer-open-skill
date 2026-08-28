# 规则提取实验框架 - Rule Extraction Experiment Framework

用于独立评估各个字段规则提取效果的通用框架
Universal framework for independently evaluating rule extraction effectiveness of various fields

## 📁 目录结构 - Directory Structure

```
rule_extraction_experiment/
├── common/                    # 公共评估工具 - Common evaluation tools
│   ├── __init__.py           # 模块初始化 - Module initialization
│   ├── evaluator.py          # 通用评估框架 - Universal evaluation framework
│   ├── field_comparator.py   # 字段对比工具 - Field comparison tools
│   ├── metrics.py            # 评估指标计算 - Evaluation metrics calculation
│   └── report_generator.py   # 报告生成器 - Report generator
│
├── configs/                   # 实验配置 - Experiment configurations
│   ├── sample_size.json      # sample_size字段配置 - sample_size field configuration
│   ├── domain.json           # domain字段配置 - domain field configuration
│   └── experiment_type.json  # experiment_type字段配置 - experiment_type field configuration
│
├── results/                   # 实验结果 - Experiment results
│   ├── sample_size/          # sample_size评估结果 - sample_size evaluation results
│   ├── domain/               # domain评估结果 - domain evaluation results
│   └── experiment_type/      # experiment_type评估结果 - experiment_type evaluation results
│
└── runners/                   # 实验运行器 - Experiment runners
    ├── sample_size_runner.py # sample_size字段实验运行器 - sample_size field experiment runner
    ├── domain_runner.py      # domain字段实验运行器 - domain field experiment runner
    └── experiment_type_runner.py # experiment_type字段实验运行器 - experiment_type field experiment runner
```

## 🎯 核心功能 - Core Features

### 1. 通用评估框架 - Universal Evaluation Framework
- 支持任意字段的规则提取效果评估
  Support rule extraction evaluation for any field
- 自动加载gold标准数据
  Automatically load gold standard data
- 动态加载规则类
  Dynamically load rule classes
- 完整的对比和指标计算
  Complete comparison and metrics calculation

### 2. 多类型字段支持 - Multi-type Field Support
- **字符串类型** - String type: 模糊匹配、精确匹配
- **数值类型** - Numeric type: 容差匹配、误差计算
- **列表类型** - List type: 顺序匹配、重合度计算
- **字典类型** - Dictionary type: 键值对比、部分匹配
- **布尔类型** - Boolean type: 精确匹配
- **空值类型** - Null type: 缺失处理

### 3. 丰富的评估指标 - Rich Evaluation Metrics
- **基础指标** - Basic metrics: accuracy, coverage, extraction_rate
- **分类指标** - Classification metrics: precision, recall, f1_score
- **高级指标** - Advanced metrics: similarity distribution, classification report
- **时间成本** - Time cost: extraction time, speedup ratio
- **成本对比** - Cost comparison: token cost, API cost

### 4. 自动化报告生成 - Automated Report Generation
- Markdown格式的详细报告
  Detailed reports in Markdown format
- 表格化的对比结果
  Tabular comparison results
- 错误案例分析
  Error case analysis
- 结论和建议
  Conclusions and recommendations

## 🚀 快速开始 - Quick Start

### 1. 运行单个字段实验 - Run Single Field Experiment

```bash
# 运行sample_size字段实验
# Run sample_size field experiment
python rule_extraction_experiment/runners/sample_size_runner.py

# 运行domain字段实验
# Run domain field experiment
python rule_extraction_experiment/runners/domain_runner.py

# 运行experiment_type字段实验
# Run experiment_type field experiment
python rule_extraction_experiment/runners/experiment_type_runner.py
```

### 2. 自定义配置运行 - Run with Custom Configuration

```bash
# 使用自定义配置文件
# Use custom configuration file
python rule_extraction_experiment/runners/sample_size_runner.py --config path/to/custom_config.json
```

### 3. 批量运行 - Batch Run

```bash
# 批量运行所有配置
# Run all configurations in batch
python rule_extraction_experiment/runners/sample_size_runner.py --batch
```

## 📊 配置文件说明 - Configuration File Description

### 配置文件结构 - Configuration File Structure

```json
{
  "experiment_id": "rule_extraction_sample_size_v1",    // 实验ID - Experiment ID
  "field_name": "sample_size",                         // 字段名称 - Field name
  "field_type": "int",                                 // 字段类型 - Field type
  "description": "实验描述",                            // 实验描述 - Experiment description

  "test_set": "dev_10",                                // 测试集 - Test set
  "gold_set": "full_text_glm5_2",                      // Gold标准集 - Gold standard set

  "rule_module": "src.rule_extraction.rules.sample_size", // 规则模块 - Rule module
  "rule_class": "SampleSizeRule",                       // 规则类 - Rule class
  "rule_params": {                                      // 规则参数 - Rule parameters
    "section_filter": true,
    "min_confidence": 0.8,
    "max_candidates": 5
  },

  "data_paths": {
    "gold_data_dir": "data/gold",                       // Gold数据目录 - Gold data directory
    "fixtures_dir": "data/fixtures",                    // Fixtures目录 - Fixtures directory
    "output_dir": "rule_extraction_experiment/results"  // 输出目录 - Output directory
  },

  "metrics": [                                          // 评估指标 - Evaluation metrics
    "accuracy",
    "coverage",
    "extraction_rate",
    "precision",
    "recall",
    "f1_score",
    "statistics"
  ],

  "comparison_settings": {                             // 对比设置 - Comparison settings
    "tolerance": 0,
    "include_partial_matches": false,
    "similarity_threshold": 0.9
  }
}
```

## 📝 新增字段实验 - Add New Field Experiment

### 1. 创建规则类 - Create Rule Class

在 `src/rule_extraction/rules/` 目录下创建新的规则类：
Create a new rule class in `src/rule_extraction/rules/` directory:

```python
# src/rule_extraction/rules/new_field.py
class NewFieldRule:
    @staticmethod
    def extract(paper_md: str, **kwargs):
        # 实现提取逻辑 - Implement extraction logic
        pass
```

### 2. 创建配置文件 - Create Configuration File

在 `rule_extraction_experiment/configs/` 目录下创建配置：
Create configuration in `rule_extraction_experiment/configs/` directory:

```bash
cp rule_extraction_experiment/configs/sample_size.json \
   rule_extraction_experiment/configs/new_field.json
```

修改配置文件中的字段信息：
Modify field information in configuration file:
- `field_name`: 新字段名 - New field name
- `field_type`: 新字段类型 - New field type
- `rule_module`: 规则模块路径 - Rule module path
- `rule_class`: 规则类名 - Rule class name

### 3. 创建运行器 - Create Runner

在 `rule_extraction_experiment/runners/` 目录下创建运行器：
Create runner in `rule_extraction_experiment/runners/` directory:

```bash
cp rule_extraction_experiment/runners/sample_size_runner.py \
   rule_extraction_experiment/runners/new_field_runner.py
```

修改运行器中的配置路径：
Modify configuration path in runner:
- 默认配置文件路径 - Default configuration file path
- 函数名称和描述 - Function name and description

### 4. 运行实验 - Run Experiment

```bash
python rule_extraction_experiment/runners/new_field_runner.py
```

## 📈 结果分析 - Result Analysis

### 实验输出文件 - Experiment Output Files

每个实验会在 `rule_extraction_experiment/results/{field_name}/` 目录下生成以下文件：
Each experiment generates the following files in `rule_extraction_experiment/results/{field_name}/` directory:

1. **comparison_results.json** - 详细的对比结果
   Detailed comparison results
2. **metrics.json** - 评估指标
   Evaluation metrics
3. **config.json** - 实验配置
   Experiment configuration
4. **report.md** - Markdown格式的评估报告
   Evaluation report in Markdown format
5. **classification_report.json** - 分类报告（仅适用于分类字段）
   Classification report (only for classification fields)

### 报告解读 - Report Interpretation

#### 关键指标说明 - Key Metrics Description

- **accuracy**: 精确匹配率 - Exact match rate
- **coverage**: 覆盖率 - Coverage rate (1 - missing rate)
- **extraction_rate**: 提取成功率 - Extraction success rate
- **precision**: 精确率 - Precision (TP / (TP + FP))
- **recall**: 召回率 - Recall (TP / (TP + FN))
- **f1_score**: F1分数 - F1 score (harmonic mean of precision and recall)

#### 状态说明 - Status Description

- **✅ exact_match**: 精确匹配 - Exact match
- **⚠️ partial_match**: 部分匹配 - Partial match
- **❌ mismatch**: 不匹配 - Mismatch
- **⭕ missing**: 缺失 - Missing
- **🚨 error**: 错误 - Error

## 🛠️ 扩展和定制 - Extension and Customization

### 添加新的评估指标 - Add New Evaluation Metrics

在 `rule_extraction_experiment/common/metrics.py` 中添加新的计算方法：
Add new calculation method in `rule_extraction_experiment/common/metrics.py`:

```python
@staticmethod
def calculate_new_metric(comparison_results: Dict[str, Any]) -> Dict[str, Any]:
    # 实现新指标计算逻辑
    # Implement new metric calculation logic
    pass
```

### 自定义对比逻辑 - Custom Comparison Logic

在 `rule_extraction_experiment/common/field_comparator.py` 中扩展对比方法：
Extend comparison methods in `rule_extraction_experiment/common/field_comparator.py`:

```python
@staticmethod
def compare_custom_type(gold: Any, rule: Any) -> Dict[str, Any]:
    # 实现自定义对比逻辑
    # Implement custom comparison logic
    pass
```

### 自定义报告模板 - Custom Report Template

在 `rule_extraction_experiment/common/report_generator.py` 中修改报告生成方法：
Modify report generation methods in `rule_extraction_experiment/common/report_generator.py`:

```python
def generate_custom_report(self) -> str:
    # 实现自定义报告生成逻辑
    # Implement custom report generation logic
    pass
```

## 🔧 故障排除 - Troubleshooting

### 常见问题 - Common Issues

1. **规则类加载失败 - Rule class loading failed**
   - 检查 `rule_module` 路径是否正确
     Check if `rule_module` path is correct
   - 确保规则类在模块中正确导出
     Ensure rule class is properly exported in module

2. **Gold数据未找到 - Gold data not found**
   - 检查 `gold_data_dir` 和路径配置
     Check `gold_data_dir` and path configuration
   - 确保测试集和Gold集名称正确
     Ensure test set and gold set names are correct

3. **提取结果全为None - All extraction results are None**
   - 检查规则提取逻辑是否正确实现
     Check if rule extraction logic is correctly implemented
   - 验证规则参数配置
     Validate rule parameter configuration

## 📚 相关文档 - Related Documentation

- 项目主文档 - Project main documentation: `CLAUDE.md`
- 规则提取模块 - Rule extraction module: `src/rule_extraction/`
- Gold标准数据 - Gold standard data: `data/gold/`
- 实验数据 - Experiment data: `data/fixtures/`

## 🤝 贡献 - Contributing

如需添加新的字段评估功能或改进现有功能：
If you want to add new field evaluation functionality or improve existing functionality:

1. 创建新的规则类 - Create new rule class
2. 创建对应的配置文件 - Create corresponding configuration file
3. 创建对应的运行器 - Create corresponding runner
4. 测试并验证结果 - Test and validate results
5. 更新文档 - Update documentation

## 📝 版本历史 - Version History

- **v0.1.0** (2026-06-26) - 初始版本 - Initial version
  - 支持基础字段类型的评估 - Support basic field type evaluation
  - 实现通用评估框架 - Implement universal evaluation framework
  - 支持sample_size、domain、experiment_type字段 - Support sample_size, domain, experiment_type fields