"""
datasets--策略v3--Gazetteer验证

策略描述: 基于Gazetteer的强语境正则提取 + Layer-1白名单验证 + 黑名单过滤
Strategy: Gazetteer-based strong-context regex extraction + Layer-1 whitelist validation + blacklist filtering

Pipeline:
  Stage 0: strip_references
  Stage 1: Section选段（复用section_title_matches）
  Stage 2: 强语境正则提取（不含表格）
  Stage 3: Gazetteer验证（paper_count >= 2，最长匹配）
  Stage 4: 黑名单过滤
  Stage 5: Fallback（v3第一版不做）

v3特点:
- 不解析Markdown/HTML表格（表格常含他人工作的dataset）
- 不使用v2的驼峰全文规则（GoogLeNet等误报源）
- 只输出Gazetteer命中的数据集（第一版）
"""

import re
import time
import json
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any, Set

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.dataset_preprocess import preprocess_paper


class DatasetRuleV3:
    """数据集提取规则 - Dataset Extraction Rule - V3 (Gazetteer验证)"""

    # 模型黑名单（即使通过Gazetteer也要过滤）
    BLACKLIST = {
        "resnet", "vgg", "alexnet", "googlenet", "inception", "mobilenet",
        "yolo", "r-cnn", "fasterrcnn", "maskrcnn", "ssd", "retinanet",
        "lstm", "gru", "rnn", "transformer", "bert", "gpt", "roberta",
        "efficientnet", "densenet", "shufflenet", "squeezenet",
        "unet", "segnet", "vit", "swin", "deit", "mae", "beit",
        "clip", "sam", "stable diffusion", "midjourney",
        "adam", "sgd", "rmsprop", "optimizer", "attention",
        "batchnorm", "dropout", "relu", "sigmoid", "tanh",
        "conv", "pooling", "softmax", "crossentropy"
    }

    # 强语境正则模式
    STRONG_CONTEXT_PATTERNS = [
        # "We evaluate/train/test on X" / "evaluate on X and Y"
        r"(?:we|our)\s+(?:evaluate|train|test|validate|use|experiment|benchmark)(?:\s+(?:on|with|using)?\s+(?:the\s+)?)?([A-Z][A-Za-z0-9\-\s]+?)(?=\s+(?:dataset|corpus|benchmark)|,|\sand\s|\.|\n|$)",

        # "the/a/an X dataset|benchmark|corpus"
        r"(?:the|a|an)\s+([A-Z][A-Za-z0-9\-\s]+?)(?:\s+(?:dataset|corpus|benchmark))",

        # "X is/are a ... dataset|corpus|benchmark"
        r"([A-Z][A-Za-z0-9\-\s]+?)\s+is\s+(?:a|an)?\s*(?:large-scale|publicly available|widely used|commonly used|popular|standard)?\s*[A-Za-z\- ]*\s*(?:dataset|corpus|benchmark)",

        # "use [X] to evaluate"
        r"(?:use|using)\s+(?:the\s+)?([A-Z][A-Za-z0-9\-\s]+?)(?:\s+to\s+evaluate|to\s+train|for\s+evaluation|for\s+training)(?=\s|$|\.|,)",

        # "evaluate on [X] and [Y]"
        r"(?:evaluate|train|test)\s+(?:on|using)\s+(?:the\s+)?([A-Z][A-Za-z0-9\-\s]+?)(?=\s+and\s+|,|\s+(?:dataset|corpus|benchmark)|\.$|$)",

        # Survey/review style: "e.g., LFW, X, Y"
        r"e\.?\s*g\.?,?\s*([A-Z][A-Z0-9\-]+?)(?=,|\s+and\s+|\.)",

        # "such as LFW" / "including LFW"
        r"(?:such as|including|like|e\.g\.|for example|examples include)\s+([A-Z][A-Z0-9\-]+?)(?=,|\s+and\s+|\.)",

        # "LFW, X and Y" (when preceded by context words)
        r"(?:datasets?|databases?|benchmarks?|corpora|corpus)\s*(?:such as|including|like|:|,)\s*([A-Z][A-Z0-9\-]+?)(?=,|\s+and\s+|\.)",
    ]

    # 可选的缩写+引用模式（v3第一版默认禁用，可在v3_report里说明ablation计划）
    # 缩写+引用: LFW [90], IJB-A [110]
    ABBREV_REF_PATTERN = r"([A-Z]{2,}(?:-\d+[A-Z]?)?)\s*\[\d+\]"

    @staticmethod
    def extract(paper_md: str, paper_id: str = "", *, enable_abbrev_ref: bool = True) -> Optional[Dict[str, Any]]:
        """
        从 Markdown 提取数据集

        Returns:
            Optional[Dict]: 包含datasets和trace信息
        """
        start_time = time.perf_counter()

        trace: Dict[str, Any] = {
            "preprocess": {},
            "extraction": {},
            "timing_ms": {}
        }

        # Stage 0+1: 预处理（strip_references + section选段）
        selected_text, preprocess_trace = preprocess_paper(paper_md)
        trace["preprocess"] = preprocess_trace["preprocess"]
        trace["timing_ms"]["preprocess_total"] = preprocess_trace["timing_ms"].get("preprocess_total", 0)

        # Stage 2: 候选生成（强语境正则）
        candidate_start = time.perf_counter()
        candidates = DatasetRuleV3._extract_candidates(selected_text, enable_abbrev_ref)
        trace["extraction"]["candidates_raw"] = candidates
        trace["timing_ms"]["candidate_extract"] = round((time.perf_counter() - candidate_start) * 1000, 2)

        # Stage 3: Gazetteer验证
        gazetteer_start = time.perf_counter()
        gazetteer = DatasetRuleV3._load_gazetteer()
        gazetteer_matches = DatasetRuleV3._match_gazetteer(candidates, gazetteer)
        trace["extraction"]["after_gazetteer"] = gazetteer_matches
        trace["timing_ms"]["gazetteer_match"] = round((time.perf_counter() - gazetteer_start) * 1000, 2)

        # Stage 4: 黑名单过滤
        filter_start = time.perf_counter()
        filtered = DatasetRuleV3._filter_blacklist(gazetteer_matches)
        trace["extraction"]["after_blacklist"] = filtered
        trace["timing_ms"]["blacklist_filter"] = round((time.perf_counter() - filter_start) * 1000, 2)

        # 构建结果
        trace["timing_ms"]["strategy_total"] = round((time.perf_counter() - start_time) * 1000, 2)
        trace["extraction"]["matched_source"] = {
            "candidates_raw_count": len(candidates),
            "gazetteer_matched_count": len(gazetteer_matches),
            "after_blacklist_count": len(filtered)
        }

        datasets = [DatasetRuleV3._build_dataset_entry(name) for name in filtered]

        return {
            "datasets": datasets,
            "trace": trace,
        }

    @staticmethod
    def _extract_candidates(text: str, enable_abbrev_ref: bool) -> List[str]:
        """
        强语境正则提取候选数据集
        """
        candidates: Set[str] = set()

        # 应用所有模式
        for pattern in DatasetRuleV3.STRONG_CONTEXT_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                candidate = match.group(1).strip()
                if candidate and DatasetRuleV3._is_valid_candidate(candidate):
                    # 处理 "A and B" 拆分
                    for name in DatasetRuleV3._split_and(candidate):
                        if DatasetRuleV3._is_valid_candidate(name):
                            candidates.add(name)

        # 可选：缩写+引用模式
        if enable_abbrev_ref:
            for match in re.finditer(DatasetRuleV3.ABBREV_REF_PATTERN, text):
                candidate = match.group(1)
                if DatasetRuleV3._is_valid_candidate(candidate):
                    candidates.add(candidate)

        return sorted(list(candidates))

    @staticmethod
    def _split_and(text: str) -> List[str]:
        """
        拆分 "A and B" 格式
        """
        if " and " in text.lower():
            parts = [p.strip() for p in re.split(r"\s+and\s+", text, flags=re.IGNORECASE)]
            return parts
        return [text]

    @staticmethod
    def _is_valid_candidate(name: str) -> bool:
        """
        验证候选是否合理
        """
        if not name or len(name) < 2:
            return False

        name = name.strip()

        # 纯数字过滤
        if name.isdigit():
            return False

        # 过滤纯停用词
        stop_words = {"the", "a", "an", "our", "we", "this", "that", "these", "those"}
        if name.lower() in stop_words:
            return False

        # 过滤无意义的短词
        if len(name) <= 2:
            return False

        # 首字母应该是大写（允许全大写）
        if not (name[0].isupper()):
            return False

        # 必须至少包含2个字母
        letter_count = sum(1 for c in name if c.isalpha())
        if letter_count < 2:
            return False

        return True

    @staticmethod
    def _load_gazetteer() -> List[Dict[str, Any]]:
        """
        加载Gazetteer
        优先读取环境变量 RULE_GAZETTEER_PATH 指定的 gazetteer（用于 v4.4 等
        切换 gazetteer 来源的实验），否则回退到默认 gazetteer.json。
        """
        import os
        env_path = os.environ.get("RULE_GAZETTEER_PATH")
        if env_path:
            p = Path(env_path)
            if p.exists():
                with open(p, 'r', encoding='utf-8') as f:
                    return json.load(f)
        gazetteer_path = project_root / "experiments" / "rule_extraction" / "datasets" / "data" / "gazetteer.json"
        if gazetteer_path.exists():
            with open(gazetteer_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    @staticmethod
    def _normalize_name(name: str) -> str:
        """
        标准化名称用于匹配
        """
        if not name:
            return ""
        normalized = name.lower()
        normalized = re.sub(r"[\s\-_]+", "", normalized)
        normalized = re.sub(r"(dataset|corpus|benchmark|set|collection)$", "", normalized)
        return normalized

    @staticmethod
    def _match_gazetteer(candidates: List[str], gazetteer: List[Dict[str, Any]]) -> List[str]:
        """
        Gazetteer验证（最长匹配优先）

        要求：
        - 子串匹配的最小长度为 3
        - 候选长度和匹配长度的比例不能太小（避免 "ijba" 匹配到 "i"）
        """
        if not gazetteer:
            return []

        matched = []

        for candidate in candidates:
            candidate_norm = DatasetRuleV3._normalize_name(candidate)
            if not candidate_norm or len(candidate_norm) < 2:
                continue

            # 查找所有匹配
            matches = []
            for entry in gazetteer:
                canonical_name = entry["canonical_name"]
                canonical_norm = DatasetRuleV3._normalize_name(canonical_name)

                # 子串匹配（双向）- 要求最小长度 3 且比例合理
                if canonical_norm in candidate_norm:
                    overlap_len = len(canonical_norm)
                    # 最小长度 3，且 overlap 占候选长度的至少 50%
                    if overlap_len >= 3 and overlap_len / len(candidate_norm) >= 0.5:
                        matches.append((overlap_len, canonical_name))
                elif candidate_norm in canonical_norm:
                    overlap_len = len(candidate_norm)
                    # 最小长度 3，且 overlap 占canonical长度的至少 50%
                    if overlap_len >= 3 and overlap_len / len(canonical_norm) >= 0.5:
                        matches.append((overlap_len, canonical_name))

                # 检查aliases
                for alias in entry.get("aliases", []):
                    alias_norm = DatasetRuleV3._normalize_name(alias)
                    if alias_norm in candidate_norm:
                        overlap_len = len(alias_norm)
                        if overlap_len >= 3 and overlap_len / len(candidate_norm) >= 0.5:
                            matches.append((overlap_len, canonical_name))
                    elif candidate_norm in alias_norm:
                        overlap_len = len(candidate_norm)
                        if overlap_len >= 3 and overlap_len / len(alias_norm) >= 0.5:
                            matches.append((overlap_len, canonical_name))

            if matches:
                # 返回最长匹配的canonical name
                matches.sort(key=lambda x: x[0], reverse=True)
                if matches[0][1] not in matched:
                    matched.append(matches[0][1])

        return matched

    @staticmethod
    def _filter_blacklist(names: List[str]) -> List[str]:
        """
        黑名单过滤
        """
        filtered = []
        for name in names:
            name_norm = DatasetRuleV3._normalize_name(name)
            if not any(b in name_norm for b in DatasetRuleV3.BLACKLIST):
                filtered.append(name)
        return filtered

    @staticmethod
    def _build_dataset_entry(name: str) -> Dict[str, Any]:
        """
        构建数据集条目
        """
        return {
            "name": name,
            "aliases": [],
            "dataset_type": "other",
            "description": "",
            "sample_size": None,
            "is_public": None,
            "is_self_collected": None,
            "urls": [],
            "github_urls": [],
            "doi_list": [],
            "cstr_list": []
        }


if __name__ == "__main__":
    # 测试
    test_md = """
# Introduction
This is the introduction [1].

# Datasets
We evaluate our method on ImageNet and COCO datasets. The ImageNet dataset is a large-scale benchmark.

# Experiments
We use the MNIST and CIFAR-10 for training and testing.

# References
[1] Some paper.
    """

    result = DatasetRuleV3.extract(test_md, "test")
    print(f"Extracted {len(result['datasets']) if result else 0} datasets:")
    if result:
        for ds in result['datasets']:
            print(f"  - {ds['name']}")
        print(f"\nTrace: {json.dumps(result['trace'], indent=2)}")