"""
扩展数据集脚本 - Expand Dataset Script

从bulk_extraction目录复制更多数据到ml_classification目录
Copy more data from bulk_extraction to ml_classification

主要功能 Main Functions:
- 复制更多的MD文件
- 复制更多的JSON标注文件
- 确保MD和JSON文件匹配
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

    # 目标样本数
    target_samples = 1000

    # 获取所有JSON文件对应的paper_id
    json_files = list(outputs_dir.glob("*.json"))
    paper_ids = [f.stem for f in json_files]
    print(f"找到 {len(paper_ids)} 个标注文件")

    # 选择前target_samples个
    selected_ids = paper_ids[:target_samples]
    print(f"选择 {len(selected_ids)} 个样本")

    # 复制JSON文件
    print(f"\n复制JSON文件到 {outputs_target}...")
    for paper_id in selected_ids:
        json_file = outputs_dir / f"{paper_id}.json"
        if json_file.exists():
            shutil.copy2(json_file, outputs_target / f"{paper_id}.json")

    print(f"已复制 {len(selected_ids)} 个JSON文件")

    # 复制对应的MD文件
    print(f"\n复制MD文件到 {corpus_target}...")
    copied_count = 0
    for paper_id in selected_ids:
        md_file = corpus_dir / f"{paper_id}.md"
        if md_file.exists():
            shutil.copy2(md_file, corpus_target / f"{paper_id}.md")
            copied_count += 1

    print(f"已复制 {copied_count} 个MD文件")

    print("\n数据扩展完成！")
    print(f"JSON文件: {len(list(outputs_target.glob('*.json')))}")
    print(f"MD文件: {len(list(corpus_target.glob('*.md')))}")

if __name__ == "__main__":
    main()