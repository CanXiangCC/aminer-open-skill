"""
论文ID提取规则 - Paper ID Extraction Rule

从论文元数据或文件路径中提取论文ID
Extract paper ID from paper metadata or file path

主要策略 Main Strategies:
1. 从元数据中直接提取 - Extract directly from metadata
2. 从文件路径中解析 - Parse from file path
3. 从markdown内容中查找 - Search in markdown content
"""

import re
import os
from typing import Dict, Any, Optional


class PaperIDRule:
    """论文ID提取规则 - Paper ID Extraction Rule"""

    # 常见的论文ID模式 - Common paper ID patterns
    ID_PATTERNS = [
        r"paper[_-]?id[:\s]*([a-f0-9]+)",  # paper_id: 5b1643ba8fbcbf6e5a9bc884
        r"id[:\s]*([a-f0-9]{24})",          # id: 5b1643ba8fbcbf6e5a9bc884
        r"_id[:\s]*([a-f0-9]{24})",         # _id: 5b1643ba8fbcbf6e5a9bc884
    ]

    @staticmethod
    def extract(paper_md: str = None,
                paper_metadata: Dict[str, Any] = None,
                file_path: str = None) -> Optional[str]:
        """
        从论文中提取论文ID
        Extract paper ID from paper

        伪代码 Pseudocode:
        1. 优先从paper_metadata中提取paper_id字段
           Prioritize extracting paper_id field from paper_metadata
        2. 如果没有，尝试从markdown内容中匹配ID模式
           If not found, try matching ID patterns in markdown content
        3. 如果还没有，从文件路径中解析ID
           If still not found, parse ID from file path
        4. 返回找到的ID，未找到则返回None
           Return found ID, None if not found

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text
            paper_metadata: 论文元数据 - Paper metadata
            file_path: 论文文件路径 - Paper file path

        返回 Returns:
            Optional[str]: 论文ID - Paper ID
        """
        # 策略1：从元数据中提取 - Strategy 1: Extract from metadata
        if paper_metadata:
            paper_id = PaperIDRule._extract_from_metadata(paper_metadata)
            if paper_id:
                return paper_id

        # 策略2：从markdown内容中提取 - Strategy 2: Extract from markdown content
        if paper_md:
            paper_id = PaperIDRule._extract_from_md(paper_md)
            if paper_id:
                return paper_id

        # 策略3：从文件路径中提取 - Strategy 3: Extract from file path
        if file_path:
            paper_id = PaperIDRule._extract_from_path(file_path)
            if paper_id:
                return paper_id

        return None

    @staticmethod
    def _extract_from_metadata(metadata: Dict[str, Any]) -> Optional[str]:
        """
        从元数据中提取论文ID
        Extract paper ID from metadata

        伪代码 Pseudocode:
        1. 检查常见的元数据字段名
           Check common metadata field names
        2. 返回找到的有效ID
           Return found valid ID
        """
        # 伪代码实现 - Pseudocode implementation
        # common_keys = ["paper_id", "id", "_id", "paperId"]
        # for key in common_keys:
        #     if key in metadata:
        #         paper_id = metadata[key]
        #         if PaperIDRule._validate_id(paper_id):
        #             return paper_id
        return None

    @staticmethod
    def _extract_from_md(paper_md: str) -> Optional[str]:
        """
        从markdown内容中提取论文ID
        Extract paper ID from markdown content

        伪代码 Pseudocode:
        1. 遍历所有预定义的ID模式
           Iterate through all predefined ID patterns
        2. 对每个模式进行正则匹配
           Perform regex matching for each pattern
        3. 验证匹配到的ID格式
           Validate matched ID format
        4. 返回第一个有效的ID
           Return first valid ID
        """
        # 伪代码实现 - Pseudocode implementation
        # for pattern in PaperIDRule.ID_PATTERNS:
        #     matches = re.findall(pattern, paper_md, re.IGNORECASE)
        #     if matches:
        #         for match in matches:
        #             if PaperIDRule._validate_id(match):
        #                 return match
        return None

    @staticmethod
    def _extract_from_path(file_path: str) -> Optional[str]:
        """
        从文件路径中提取论文ID
        Extract paper ID from file path

        伪代码 Pseudocode:
        1. 从文件名中查找符合ID格式的部分
           Find ID-formatted part from filename
        2. 验证ID格式
           Validate ID format
        3. 返回提取的ID
           Return extracted ID
        """
        # 伪代码实现 - Pseudocode implementation
        # filename = os.path.basename(file_path)
        # name_without_ext = os.path.splitext(filename)[0]
        # id_pattern = r"([a-f0-9]{24})"
        # match = re.search(id_pattern, name_without_ext)
        # if match:
        #     paper_id = match.group(1)
        #     if PaperIDRule._validate_id(paper_id):
        #         return paper_id
        return None

    @staticmethod
    def _validate_id(paper_id: str) -> bool:
        """
        验证论文ID格式
        Validate paper ID format

        伪代码 Pseudocode:
        1. 检查是否为24位十六进制字符串
           Check if it's 24-character hex string
        2. 检查是否包含非法字符
           Check for illegal characters
        3. 返回验证结果
           Return validation result
        """
        # 伪代码实现 - Pseudocode implementation
        # if not paper_id or not isinstance(paper_id, str):
        #     return False
        # return len(paper_id) == 24 and all(c in '0123456789abcdef' for c in paper_id.lower())
        return bool(paper_id)  # 简化版本 - Simplified version