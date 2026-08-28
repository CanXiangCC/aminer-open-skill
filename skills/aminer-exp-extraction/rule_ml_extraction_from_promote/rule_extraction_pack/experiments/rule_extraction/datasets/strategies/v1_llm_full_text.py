"""
datasets--策略v1--LLM全文本抽取

策略描述: 直接从 bulk_extraction/outputs/per_paper/ 读取已抽取的 datasets 字段
Strategy: Read datasets field directly from bulk_extraction/outputs/per_paper/

Layer 1 - 最高覆盖率策略
Layer 1 - Highest coverage strategy
"""

import json
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))


class DatasetRuleV1:
    """数据集提取规则 - Dataset Extraction Rule - V1 (LLM Full Text)"""

    # bulk_extraction 输出目录
    BULK_OUTPUT_DIR = project_root / "bulk_extraction" / "outputs" / "per_paper"

    @staticmethod
    def extract(paper_md: str, paper_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        从 bulk_extraction 提取数据集
        Extract datasets from bulk_extraction

        策略 Strategy:
        1. 根据 paper_id 读取 bulk_extraction/outputs/per_paper/{paper_id}.json
        2. 提取所有 experiment 的 datasets 字段
        3. 合并去重（按 name）
        4. 返回 datasets 数组

        Args:
            paper_md: 论文markdown文本（本策略不使用，保持接口一致） - Paper markdown (not used, for interface consistency)
            paper_id: 论文ID - Paper ID

        Returns:
            Optional[List[Dict]]]: 提取的datasets数组，未找到返回None - Extracted datasets array, None if not found
        """
        # 读取 bulk_extraction 输出 - Read bulk_extraction output
        bulk_file = DatasetRuleV1.BULK_OUTPUT_DIR / f"{paper_id}.json"

        if not bulk_file.exists():
            return None

        try:
            with open(bulk_file, 'r', encoding='utf-8') as f:
                bulk_data = json.load(f)

            # 确保是数组 - Ensure it's an array
            if not isinstance(bulk_data, list):
                bulk_data = [bulk_data]

            # 收集所有 datasets - Collect all datasets
            all_datasets = []
            seen_names = set()

            for exp in bulk_data:
                datasets = exp.get("datasets")
                if not datasets or not isinstance(datasets, list):
                    continue

                for ds in datasets:
                    ds_name = ds.get("name")
                    if not ds_name:
                        continue

                    # 去重 - Deduplicate by name
                    if ds_name in seen_names:
                        continue
                    seen_names.add(ds_name)
                    all_datasets.append(ds)

            return all_datasets if all_datasets else None

        except Exception as e:
            print(f"Error reading {bulk_file}: {e}")
            return None


if __name__ == "__main__":
    # 测试 - Test
    print("Testing DatasetRuleV1...")
    print(f"Bulk output dir: {DatasetRuleV1.BULK_OUTPUT_DIR}")

    # 检查目录是否存在 - Check if directory exists
    if DatasetRuleV1.BULK_OUTPUT_DIR.exists():
        files = list(DatasetRuleV1.BULK_OUTPUT_DIR.glob("*.json"))
        print(f"Found {len(files)} bulk extraction files")

        if files:
            # 测试第一个文件 - Test first file
            test_paper_id = files[0].stem
            print(f"\nTesting with paper: {test_paper_id}")
            result = DatasetRuleV1.extract("", test_paper_id)

            if result:
                print(f"Found {len(result)} datasets:")
                for ds in result:
                    print(f"  - {ds.get('name')} ({ds.get('dataset_type', 'unknown')})")
            else:
                print("No datasets found")
    else:
        print("Bulk output directory not found!")