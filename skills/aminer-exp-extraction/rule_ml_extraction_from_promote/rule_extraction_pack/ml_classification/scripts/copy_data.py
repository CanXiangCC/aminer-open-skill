"""
数据复制脚本 - Data Copy Script

从bulk_extraction目录复制所需数据到ml_classification目录
Copy required data from bulk_extraction to ml_classification directory
"""

import os
import shutil
from pathlib import Path

def main():
    # 项目路径
    project_root = Path("D:/Zhipu_Intern/experiment_points_extraction")
    corpus_dir = project_root / "bulk_extraction" / "corpus" / "md"
    outputs_dir = project_root / "bulk_extraction" / "outputs" / "per_paper"

    # 目标目录
    ml_classification_dir = project_root / "ml_classification" / "data" / "raw"
    corpus_target = ml_classification_dir / "corpus"
    outputs_target = ml_classification_dir / "outputs"

    # 创建目录
    corpus_target.mkdir(parents=True, exist_ok=True)
    outputs_target.mkdir(parents=True, exist_ok=True)

    # 复制前100个md文件
    print(f"从 {corpus_dir} 复制md文件...")
    md_files = list(corpus_dir.glob("*.md"))[:100]

    for md_file in md_files:
        shutil.copy2(md_file, corpus_target / md_file.name)

    print(f"✅ 已复制 {len(md_files)} 个md文件到 {corpus_target}")

    # 复制前50个JSON文件作为参考
    print(f"从 {outputs_dir} 处复制JSON文件...")
    json_files = list(outputs_dir.glob("*.json"))[:50]

    for json_file in json_files:
        shutil.copy2(json_file, outputs_target / json_file.name)

    print(f"✅ 已复制 {len(json_files)} 个JSON文件到 {outputs_target}")
    print("\n数据复制完成！")

if __name__ == "__main__":
    main()