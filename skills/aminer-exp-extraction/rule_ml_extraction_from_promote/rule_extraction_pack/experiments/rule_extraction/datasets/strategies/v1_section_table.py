"""
datasets--策略v1--Section+Table提取

策略描述: 查找 Dataset 相关 section，提取数据集名称，包括表格中的列表
Strategy: Find Dataset-related sections, extract dataset names including from tables

Layer 1 - Section结构化提取
Layer 1 - Section-based structured extraction
"""

import re
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from experiments.rule_extraction.shared.utils import clean_markdown_text


class DatasetRuleV1:
    """数据集提取规则 - Dataset Extraction Rule - V1 (Section + Table)"""

    # Dataset 相关的 section 标题关键词
    SECTION_KEYWORDS = [
        "dataset", "datasets", "database", "databases", "data", "data collection", "data sources",
        "experiment", "experiments", "experimental setup", "experiment setup",
        "training data", "evaluation data", "benchmark", "implementation details",
        "evaluation protocol", "evaluation protocols",
    ]

    # 常见数据集类型
    DATASET_TYPES = [
        "text", "image", "audio", "video", "tabular", "multimodal",
        "sensor", "simulation", "3d", "point cloud", "other"
    ]

    @staticmethod
    def extract(paper_md: str, paper_id: str = "") -> Optional[List[Dict[str, Any]]]:
        """
        从 Markdown 提取数据集
        Extract datasets from markdown paper

        策略 Strategy:
        1. 查找 Dataset 相关的 section
        2. 提取该 section 内容
        3. 解析表格中的数据集列表
        4. 解析文本中的数据集提及
        5. 合并去重

        Args:
            paper_md: 论文markdown文本 - Paper markdown text
            paper_id: 论文ID（本策略不使用，保持接口一致） - Paper ID (not used, for interface consistency)

        Returns:
            Optional[List[Dict]]]: 提取的datasets数组，未找到返回None - Extracted datasets array, None if not found
        """
        # 1. 查找 Dataset section - Find Dataset section
        HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(HEADER_RE.finditer(paper_md))

        if not matches:
            return None

        # 收集所有相关 section 的内容 - Collect content from all relevant sections
        all_section_content = []

        for i, match in enumerate(matches):
            title = match.group(2).strip().lower()

            # 检查是否匹配关键词 - Check if matches any keyword
            if any(keyword in title for keyword in DatasetRuleV1.SECTION_KEYWORDS):
                # 提取 section 内容 - Extract section content
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(paper_md)
                content = paper_md[start:end].strip()
                all_section_content.append(content)

        if not all_section_content:
            return None

        # 2. 从内容中提取数据集 - Extract datasets from content
        datasets = {}  # normalized_name -> (original_name, details)

        for content in all_section_content:
            # 2.1 从表格中提取 - Extract from tables
            table_datasets = DatasetRuleV1._extract_from_tables(content)
            for name in table_datasets:
                normalized = DatasetRuleV1._normalize_name(name)
                if normalized not in datasets:
                    datasets[normalized] = (name, {})

            # 2.2 从文本中提取 - Extract from text
            text_datasets = DatasetRuleV1._extract_from_text(content)
            for name, details in text_datasets.items():
                normalized = DatasetRuleV1._normalize_name(name)
                # 合并详情 - Merge details
                existing = datasets.get(normalized)
                if existing:
                    existing_name, existing_details = existing
                    # 优先保留更长的名称 - Prefer longer name
                    if len(name) > len(existing_name):
                        datasets[normalized] = (name, {**existing_details, **details})
                    else:
                        datasets[normalized] = (existing_name, {**details, **existing_details})
                else:
                    datasets[normalized] = (name, details)

        # 3. 构建结果 - Build result
        result = []
        for normalized, (name, details) in sorted(datasets.items()):
            ds: Dict[str, Any] = {
                "name": name,
                "aliases": [],
                "dataset_type": details.get("type", "other"),
                "description": details.get("description", ""),
                "sample_size": details.get("sample_size"),
                "is_public": None,
                "is_self_collected": None,
                "urls": [],
                "github_urls": [],
                "doi_list": [],
                "cstr_list": []
            }
            result.append(ds)

        return result if result else None

    @staticmethod
    def _normalize_name(name: str) -> str:
        """
        标准化数据集名称（用于去重）
        Normalize dataset name for deduplication
        """
        # 转小写，移除空格和标点
        normalized = name.lower().replace(" ", "").replace("-", "").replace("_", "")
        # 移除后缀 "dataset", "corpus", "benchmark" - Remove common suffixes
        normalized = re.sub(r"(dataset|corpus|benchmark|set|collection)$", "", normalized)
        return normalized

    @staticmethod
    def _clean_dataset_name(name: str) -> str:
        """
        清理数据集名称
        Clean dataset name by removing extra content
        """
        if not name:
            return ""

        # 移除 [citation] 标记 - Remove [citation]
        cleaned = re.sub(r"\s*\[\d+\]", "", name).strip()

        # 移除括号中的额外信息 (但保留全称) - Remove extra info in parens
        cleaned = re.sub(r"\s*\(base set\)", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*\(novel set\)", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*\(clean\)", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*\(VI-[A-Z0-9]+\)", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*\(Challenge \d+\)", "", cleaned, flags=re.IGNORECASE)

        # 移除行末逗号 - Remove trailing comma
        cleaned = cleaned.rstrip(",").strip()

        return cleaned

    @staticmethod
    def _extract_from_tables(content: str) -> List[str]:
        """
        从 Markdown 表格中提取数据集名称
        Extract dataset names from Markdown tables

        识别表格模式:
        | Dataset | Description | Size |
        |---------|-------------|------|
        | ImageNet | ... | 1M    |
        """
        datasets = []

        # 1. Markdown 表格正则 - Markdown table regex
        TABLE_RE = re.compile(
            r"\|.*?\|[\r\n]+\|[-:|\s]+\|[\r\n]+((?:\|.*?\|[\r\n]+)+)",
            re.MULTILINE
        )

        for table_match in TABLE_RE.finditer(content):
            table_body = table_match.group(1)
            rows = table_body.strip().split("\n")

            # 假设第一列是数据集名称 - Assume first column is dataset names
            for row in rows:
                row = row.strip()
                if not row or not row.startswith("|"):
                    continue

                # 跳过分隔行 - Skip separator rows
                if "---" in row:
                    continue

                # 提取单元格 - Extract cells
                cells = [cell.strip() for cell in row.split("|")[1:-1]]

                if not cells:
                    continue

                # 假设第一个单元格是数据集名称 - Assume first cell is dataset name
                potential_name = cells[0]
                if DatasetRuleV1._is_valid_dataset_name(potential_name):
                    datasets.append(potential_name)
                else:
                    # 尝试清理 - Try to clean
                    cleaned = clean_markdown_text(potential_name)
                    if DatasetRuleV1._is_valid_dataset_name(cleaned):
                        datasets.append(cleaned)

        # 2. HTML 表格正则 - HTML table regex
        # 查找所有 <table> 元素 - Find all <table> elements
        HTML_TABLE_RE = re.compile(r"<table>.*?</table>", re.IGNORECASE | re.DOTALL)

        for table_match in HTML_TABLE_RE.finditer(content):
            table_text = table_match.group(0)
            # 分割行 - Split by </tr>
            rows = table_text.split("</tr>")

            # 找包含 "Datasets" 的行 - Find rows containing "Datasets"
            datasets_rows = []
            for row in rows:
                if "datasets</td>" in row.lower():
                    # 检查是否是数据行（包含数据集名称）而不是表头
                    # 表头通常包含 "Publish", "#", "Key" 等词
                    is_header = any(kw in row.lower() for kw in ["publish", "#", "key", "metric", "photo", "subject"])
                    if not is_header or " [90]" in row or " [69]" in row:  # 包含引用标注的是数据行
                        datasets_rows.append(row)

            # 从数据行提取数据集 - Extract datasets from data rows
            for row in datasets_rows:
                # 提取单元格 - Extract cells
                cell_contents = re.findall(r"<td>([^<]+)</td>", row, re.IGNORECASE)
                for cell in cell_contents[1:]:  # 跳过第一个 "Datasets"
                    # 处理单元格中的多个数据集 - Handle multiple datasets in a cell
                    # 格式可能是: "MS-Celeb-1M LFW [90]" 或 "MegaFace [105], [145] IJB-A [110]"
                    # 先移除引用 - Remove citations first
                    cleaned = re.sub(r"\s*\[\d+(?:,\s*\d+)*\]", "", cell).strip()
                    # 按空格分割 - Split by space
                    parts = re.split(r"\s+", cleaned)
                    for part in parts:
                        if part:
                            cleaned_part = DatasetRuleV1._clean_dataset_name(part)
                            if cleaned_part and DatasetRuleV1._is_valid_dataset_name(cleaned_part):
                                datasets.append(cleaned_part)

        return datasets

    @staticmethod
    def _is_table_header(text: str) -> bool:
        """
        判断是否是表格头
        Check if text is a table header
        """
        text_lower = text.lower().strip()
        header_indicators = ["#", "feature", "metric", "publish time", "photo", "subject", "key"]
        return any(indicator in text_lower for indicator in header_indicators) or text_lower.startswith("#")

    @staticmethod
    def _extract_from_text(content: str) -> Dict[str, Dict[str, Any]]:
        """
        从文本中提取数据集名称和详情
        Extract dataset names and details from text

        识别模式:
        - "We use the [Dataset Name] dataset"
        - "The [Dataset Name] dataset consists of X samples"
        - "[Dataset Name] is a large-scale dataset"
        """
        result = {}
        cleaned_content = clean_markdown_text(content)

        # 数据集名称模式 - Dataset name patterns
        # 1. "[Name] [is/are] a [adjectives?] [type?] dataset" - 如 "Cityscapes is a dataset for..."
        # 修改为更灵活的匹配: 允许通用的中间词 (generic, object, etc.)
        PATTERN_1 = re.compile(
            r"([A-Z][A-Za-z0-9\-\s]+?)\s+(?:is|are)\s+(?:a|an|the)?\s*[A-Za-z\- ]*\s+(?:dataset|corpus|benchmark)",
            re.IGNORECASE
        )

        # 2. "We use/evaluate/train on the [Name] dataset"
        PATTERN_2 = re.compile(
            r"(?:use|evaluate|train|test)\s+(?:on|with|using)?\s*(?:the\s+)?([A-Z][A-Za-z0-9\-\s]+?)(?:\s+(?:dataset|corpus|benchmark)|,|$)",
            re.IGNORECASE
        )

        # 3. "Dataset. We use [Name] and [Name]" - section 开头
        PATTERN_3 = re.compile(
            r"dataset\.?\s*we\s+(?:use|verify|evaluate)\s+(?:the\s+)?([A-Z][A-Za-z0-9\-\s]+?)(?:,|\s+and|\.$)",
            re.IGNORECASE
        )

        for pattern in [PATTERN_1, PATTERN_2, PATTERN_3]:
            for match in pattern.finditer(cleaned_content):
                name = match.group(1).strip()

                # 处理 "A and B" 的情况 - Handle "A and B" cases
                if " and " in name:
                    parts = [p.strip() for p in name.split(" and ")]
                else:
                    parts = [name]

                for part in parts:
                    if DatasetRuleV1._is_valid_dataset_name(part):
                        # 尝试提取详情 - Try to extract details
                        details = DatasetRuleV1._extract_details(cleaned_content, part)
                        result[part] = details

        return result

    @staticmethod
    def _extract_details(text: str, name: str) -> Dict[str, Any]:
        """
        提取数据集详情（类型、样本大小、描述）
        Extract dataset details (type, sample_size, description)
        """
        details = {
            "type": "other",
            "description": "",
            "sample_size": None
        }

        # 查找包含数据集名称的句子 - Find sentences containing dataset name
        sentences = re.split(r"[.!?]", text)
        relevant_sentences = []
        for sent in sentences:
            if name.lower() in sent.lower():
                relevant_sentences.append(sent.strip())

        description = " ".join(relevant_sentences[:2])  # 取前两句 - Take first 2 sentences
        details["description"] = description

        # 提取样本大小 - Extract sample size
        SAMPLE_SIZE_PATTERNS = [
            r"(\d+(?:,\d+)*(?:\.\d+)?)\s+(?:samples|images|videos|examples|instances|documents|entries)",
            r"(?:contains|consists of|has)\s+(\d+(?:,\d+)*(?:\.\d+)?)\s+",
            r"(\d+K|\d+M|\d+G)\s+(?:samples|images)",
        ]

        for pattern in SAMPLE_SIZE_PATTERNS:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                size_str = match.group(1)
                details["sample_size"] = DatasetRuleV1._parse_sample_size(size_str)
                break

        # 推断类型 - Infer type
        type_keywords = {
            "text": ["text", "document", "corpus", "caption", "translation"],
            "image": ["image", "picture", "photo", "visual", "face", "object"],
            "video": ["video", "clip", "frame"],
            "audio": ["audio", "sound", "speech", "music"],
            "sensor": ["lidar", "sensor", "rgbd", "point cloud"],
            "simulation": ["simulation", "simulator", "virtual"],
            "3d": ["3d", "3-d", "three-dimensional", "mesh"],
            "multimodal": ["multimodal", "multi-modal", "audiovisual"]
        }

        description_lower = description.lower()
        for dtype, keywords in type_keywords.items():
            if any(kw in description_lower for kw in keywords):
                details["type"] = dtype
                break

        return details

    @staticmethod
    def _parse_sample_size(size_str: str) -> Optional[int]:
        """
        解析样本大小字符串
        Parse sample size string (e.g., "1,234,567", "10K", "100M")
        """
        size_str = size_str.strip().upper()

        if "K" in size_str:
            return int(float(size_str.replace("K", "")) * 1000)
        elif "M" in size_str:
            return int(float(size_str.replace("M", "")) * 1000000)
        elif "G" in size_str:
            return int(float(size_str.replace("G", "")) * 1000000000)
        else:
            return int(size_str.replace(",", ""))

    @staticmethod
    def _is_valid_dataset_name(name: str) -> bool:
        """
        验证是否是有效的数据集名称
        Validate if it's a valid dataset name

        过滤规则:
        - 不能是纯数字或数字+单位 (如 1.4M, 330K)
        - 不能包含常见停用词 (the, of, to, and, etc.)
        - 长度至少 2 个字符
        - 必须以字母开头
        """
        if not name or len(name) < 2:
            return False

        name_lower = name.lower()

        # 过滤包含停用词的名称 - Filter names containing stop words
        stop_words = {
            "the", "a", "an", "this", "that", "these", "those",
            "our", "we", "our", "proposed", "method", "approach",
            "experiment", "result", "evaluation", "benchmark",
            "dataset", "corpus", "set", "collection", "benchmark",
            "data", "training", "test", "validation",
            "which", "where", "when", "how", "why",
            "and", "or", "but", "with", "from", "to", "of", "for", "in", "on", "at", "by",
            "prerequisite", "utilization", "distribution", "effective", "deep",
            "image", "video", "audio", "text", "table", "row", "column"
        }

        # 检查名称是否包含任何停用词 - Check if name contains any stop word
        for word in stop_words:
            if f" {word} " in f" {name_lower} ":
                return False

        # 过滤纯数字或数字+单位 (如 14M, 330K, 1234567)
        name_clean = re.sub(r"[^A-Za-z0-9]", "", name)
        SAMPLE_SIZE_RE = re.compile(r"^[\d,]+\.?\d*[KMGT]?B?$")
        if SAMPLE_SIZE_RE.match(name_clean):
            return False

        # 不能是纯数字 - Cannot be purely numeric
        if name.isdigit():
            return False

        # 必须包含至少一个字母 - Must contain at least one letter
        if not any(c.isalpha() for c in name):
            return False

        # 首字母大写或全部大写 - First letter capitalized or all caps
        if name[0].islower():
            return False

        # 至少包含2个字母 - Must contain at least 2 letters
        letter_count = sum(1 for c in name if c.isalpha())
        if letter_count < 2:
            return False

        # 不能以常见词开头 - Cannot start with common words
        start_words = {"a", "an", "the", "our", "this", "that"}
        if name_lower.split()[0] in start_words:
            return False

        return True


if __name__ == "__main__":
    # 测试 - Test
    test_md = """
# Introduction
This is the introduction.

# Datasets
We evaluate our method on several benchmark datasets.

| Dataset | Type | Size |
|---------|------|------|
| ImageNet | Image | 1.4M |
| COCO | Image | 330K |
| PASCAL VOC | Image | 20K |

The ImageNet dataset is a large-scale visual recognition dataset.
PASCAL VOC is a standard object detection benchmark.

# References
[1] Some paper.
    """

    result = DatasetRuleV1.extract(test_md)
    print(f"Extracted {len(result) if result else 0} datasets:")
    if result:
        for ds in result:
            print(f"  - {ds['name']} ({ds['dataset_type']})")