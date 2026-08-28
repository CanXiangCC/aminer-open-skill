"""复制数据文件"""
import shutil
from pathlib import Path

# 路径
corpus_dir = Path("D:/Zhipu_Intern/experiment_points_extraction/bulk_extraction/corpus/md")
outputs_dir = Path("D:/Zhipu_Intern/experiment_points_extraction/bulk_extraction/outputs/per_paper")

# 目标路径
corpus_target = Path("D:/Zhipu_Intern/experiment_points_extraction/ml_classification/data/raw/corpus")
outputs_target = Path("D:/Zhipu_Intern/experiment_points_extraction/ml_classification/data/raw/outputs")

# 创建目录
corpus_target.mkdir(parents=True, exist_ok=True)
outputs_target.mkdir(parents=True, exist_ok=True)

# 复制md文件
md_files = list(corpus_dir.glob("*.md"))[:100]
for md_file in md_files:
    shutil.copy2(md_file, corpus_target / md_file.name)

print(f"Copied {len(md_files)} md files")

# 复制json文件
json_files = list(outputs_dir.glob("*.json"))[:50]
for json_file in json_files:
    shutil.copy2(json_file, outputs_target / json_file.name)

print(f"Copied {len(json_files)} json files")
print("Data copying complete!")