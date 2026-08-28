"""
Gazetteer构建脚本 - Gazetteer Builder

从批量提取结果构建数据集 gazetteer
Build dataset gazetteer from batch extraction results

输入: bulk_extraction/outputs/extractions.batch_paper_md_result_matched_20260612.json
输出: experiments/rule_extraction/datasets/data/gazetteer.json
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Any, Optional
from collections import defaultdict

# 添加项目根目录到路径
# 从 scripts/datasets/rule_extraction/experiments/ → 根目录
project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))


# 模型黑名单 - 这些是模型名，不是数据集
MODEL_BLACKLIST = {
    "resnet", "vgg", "alexnet", "googlenet", "inception", "mobilenet",
    "yolo", "r-cnn", "fasterrcnn", "maskrcnn", "ssd", "retinanet",
    "lstm", "gru", "rnn", "transformer", "bert", "gpt", "roberta",
    "efficientnet", "densenet", "shufflenet", "squeezenet",
    "unet", "segnet", "fpn", "pan", "fpn", "yolov3", "yolov4", "yolov5",
    "vit", "swin", "deit", "mae", "beit", "clip", "sam", "dall-e",
    "stable diffusion", "midjourney", "diffusion",
    "attention", "self-attention", "cross-attention",
    "cnn", "convnet", "mlp", "linear",
    "adam", "sgd", "rmsprop", "optimizer"
}


def normalize_name(name: str) -> str:
    """
    标准化数据集名称（用于合并）
    Normalize dataset name for merging
    """
    if not name:
        return ""

    # 转小写
    normalized = name.lower()

    # 移除空格、连字符、下划线
    normalized = re.sub(r"[\s\-_]+", "", normalized)

    # 移除后缀
    normalized = re.sub(r"(dataset|corpus|benchmark|set|collection|data)$", "", normalized)

    return normalized


def is_model_name(name: str) -> bool:
    """
    检查是否是模型名（黑名单过滤）
    Check if it's a model name (blacklist filtering)
    """
    name_lower = normalize_name(name)
    return any(model in name_lower for model in MODEL_BLACKLIST)


def build_gazetteer(
    bulk_json_path: Path,
    output_path: Path,
    min_paper_count: int = 2
) -> List[Dict[str, Any]]:
    """
    构建 gazetteer

    Args:
        bulk_json_path: 批量提取结果路径
        output_path: 输出路径
        min_paper_count: 最小论文数阈值

    Returns:
        Gazetteer entries
    """
    print(f"Loading bulk extraction from: {bulk_json_path}")

    with open(bulk_json_path, 'r', encoding='utf-8') as f:
        bulk_data = json.load(f)

    print(f"Loaded {len(bulk_data)} papers")

    # 收集所有数据集名称及其出现次数
    dataset_counts: Dict[str, Set[str]] = defaultdict(set)  # normalized_name -> set(paper_ids)
    name_mapping: Dict[str, List[str]] = defaultdict(list)  # normalized_name -> [original_names]

    for entry in bulk_data:
        paper_id = entry.get("paper_id", "")
        datasets = entry.get("datasets", [])

        for ds in datasets:
            if not isinstance(ds, dict):
                continue

            name = ds.get("name", "").strip()
            if not name or is_model_name(name):
                continue

            normalized = normalize_name(name)
            dataset_counts[normalized].add(paper_id)
            name_mapping[normalized].append(name)

            # 同时记录 aliases
            aliases = ds.get("aliases", [])
            for alias in aliases:
                if alias and alias.strip():
                    alias_normalized = normalize_name(alias.strip())
                    dataset_counts[alias_normalized].add(paper_id)
                    name_mapping[alias_normalized].append(alias.strip())

    # 构建 Gazetteer entries
    gazetteer = []

    for normalized, paper_ids in dataset_counts.items():
        paper_count = len(paper_ids)

        # 过滤低频项
        if paper_count < min_paper_count:
            continue

        # 获取所有别名
        all_names = name_mapping.get(normalized, [])
        canonical_name = max(all_names, key=len)  # 最长的作为 canonical name

        # 构建 normalized_keys（用于最长匹配）
        normalized_keys = set([normalized])
        for name in all_names:
            normalized_keys.add(normalize_name(name))

        entry = {
            "canonical_name": canonical_name,
            "aliases": list(set(all_names) - {canonical_name}),
            "normalized_keys": sorted(list(normalized_keys)),
            "paper_count": paper_count
        }
        gazetteer.append(entry)

    # 按 paper_count 降序排序
    gazetteer.sort(key=lambda x: x["paper_count"], reverse=True)

    print(f"Built gazetteer with {len(gazetteer)} entries (paper_count >= {min_paper_count})")

    # 写入文件
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(gazetteer, f, indent=2, ensure_ascii=False)

    print(f"Saved gazetteer to: {output_path}")

    return gazetteer


def load_gazetteer(gazetteer_path: Path) -> List[Dict[str, Any]]:
    """
    加载 gazetteer
    Load gazetteer
    """
    with open(gazetteer_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def match_gazetteer(
    candidate: str,
    gazetteer: List[Dict[str, Any]],
    case_sensitive: bool = False
) -> Optional[str]:
    """
    匹配候选数据集名到 gazetteer（最长匹配优先）
    Match candidate dataset name to gazetteer (longest match first)

    Returns:
        Canonical name if found, None otherwise
    """
    candidate_normalized = normalize_name(candidate)
    if not candidate_normalized:
        return None

    # 查找所有匹配的 entry
    matches = []
    for entry in gazetteer:
        for norm_key in entry.get("normalized_keys", []):
            # 支持子串匹配
            if norm_key in candidate_normalized or candidate_normalized in norm_key:
                matches.append((len(norm_key), entry["canonical_name"]))
                break

    if not matches:
        return None

    # 返回最长匹配
    matches.sort(key=lambda x: x[0], reverse=True)
    return matches[0][1]


def main():
    """
    主函数
    """
    bulk_json_path = project_root / "bulk_extraction" / "outputs" / "extractions.batch_paper_md_result_matched_20260612.json"
    output_path = Path(__file__).parent.parent / "data" / "gazetteer.json"

    if not bulk_json_path.exists():
        print(f"Error: bulk extraction file not found: {bulk_json_path}")
        return

    gazetteer = build_gazetteer(bulk_json_path, output_path, min_paper_count=2)

    # 打印统计信息
    print("\n=== Gazetteer Statistics ===")
    print(f"Total entries: {len(gazetteer)}")

    top_10 = gazetteer[:10]
    print(f"\nTop 10 datasets by paper_count:")
    for entry in top_10:
        print(f"  - {entry['canonical_name']}: {entry['paper_count']} papers")


if __name__ == "__main__":
    main()