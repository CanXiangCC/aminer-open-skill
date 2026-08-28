"""
领域提取规则 - Domain Extraction Rule

从论文中提取研究领域
Extract research domain from papers

主要策略 Main Strategies:
1. 检查论文标题、摘要、关键词中的领域信息
   Check domain information in title, abstract, keywords
2. 匹配预定义的领域列表和关键词
   Match against predefined domain list and keywords
3. 使用领域关键词的权重和频率进行判断
   Use weights and frequency of domain keywords for judgment
"""

import re
from typing import Optional, Dict, List, Tuple


class DomainRule:
    """领域提取规则 - Domain Extraction Rule"""

    # 预定义的研究领域及其关键词
    # Predefined research domains and their keywords
    DOMAINS = {
        "computer_science": {
            "keywords": [
                "computer", "software", "algorithm", "machine learning", "deep learning",
                "neural network", "artificial intelligence", "AI", "data mining",
                "programming", "database", "system", "computing", "code", "LLM",
                "large language model", "natural language processing", "NLP",
                "computer vision", "cloud computing", "distributed system"
            ],
            "weight": 1.0,
            "aliases": ["cs", "computing"]
        },
        "medicine": {
            "keywords": [
                "medical", "clinical", "patient", "treatment", "disease", "health",
                "pharmaceutical", "drug", "therapy", "medicine", "healthcare",
                "diagnosis", "biomedical", "hospital", "physician"
            ],
            "weight": 1.0,
            "aliases": ["health", "medical"]
        },
        "biology": {
            "keywords": [
                "biology", "gene", "protein", "cell", "molecular", "organism",
                "evolution", "ecology", "bioinformatics", "genome", "DNA", "RNA"
            ],
            "weight": 1.0,
            "aliases": ["life science", "bio"]
        },
        "physics": {
            "keywords": [
                "physics", "quantum", "particle", "atom", "energy", "force",
                "matter", "relativity", "mechanics", "thermodynamics", "optics"
            ],
            "weight": 1.0,
            "aliases": ["physical"]
        },
        "chemistry": {
            "keywords": [
                "chemistry", "chemical", "reaction", "molecule", "compound",
                "catalyst", "synthesis", "organic", "inorganic"
            ],
            "weight": 1.0,
            "aliases": ["chem"]
        },
        "economics": {
            "keywords": [
                "economics", "economic", "market", "finance", "investment",
                "trade", "business", "financial", "econometrics", "monetary"
            ],
            "weight": 1.0,
            "aliases": ["econ", "business"]
        },
        "social_science": {
            "keywords": [
                "social", "sociology", "psychology", "anthropology", "political",
                "society", "human", "behavior", "cultural", "community"
            ],
            "weight": 1.0,
            "aliases": ["social", "humanities"]
        },
        "engineering": {
            "keywords": [
                "engineering", "mechanical", "electrical", "civil", "industrial",
                "manufacturing", "design", "prototype", "construction"
            ],
            "weight": 1.0,
            "aliases": ["eng", "tech"]
        }
    }

    @staticmethod
    def extract(paper_md: str,
                use_title_weight: bool = True,
                min_score: float = 0.1) -> Optional[str]:
        """
        从论文中提取研究领域
        Extract research domain from paper

        伪代码 Pseudocode:
        1. 提取论文的标题、摘要等高权重部分
           Extract high-weight parts like title, abstract
        2. 对每个领域进行关键词匹配和频率统计
           Perform keyword matching and frequency counting for each domain
        3. 如果启用标题权重，对标题中的关键词给予更高权重
           If title weight enabled, give higher weight to keywords in title
        4. 计算每个领域的得分
           Calculate score for each domain
        5. 选择得分最高且超过最小得分的领域
           Choose domain with highest score above minimum
        6. 返回研究领域，未找到则返回None
           Return research domain, None if not found

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text
            use_title_weight: 是否对标题中的关键词加权
                              Whether to weight keywords in title
            min_score: 最小得分阈值 - Minimum score threshold

        返回 Returns:
            Optional[str]: 研究领域 - Research domain
        """
        # 伪代码实现 - Pseudocode implementation
        # 1. 提取高权重内容 - Extract high-weight content
        # title = DomainRule._extract_title(paper_md)
        # abstract = DomainRule._extract_abstract(paper_md)
        # keywords = DomainRule._extract_keywords(paper_md)

        # 2. 对每个领域计算得分 - Calculate score for each domain
        # domain_scores = {}
        # for domain_name, domain_info in DomainRule.DOMAINS.items():
        #     score = DomainRule._calculate_domain_score(
        #         paper_md, domain_info["keywords"],
        #         title=title if use_title_weight else None,
        #         abstract=abstract,
        #         keywords=keywords
        #     )
        #     domain_scores[domain_name] = score * domain_info["weight"]

        # 3. 选择最佳领域 - Select best domain
        # if domain_scores:
        #     best_domain = max(domain_scores.items(), key=lambda x: x[1])
        #     if best_domain[1] >= min_score:
        #         return best_domain[0]

        return "computer_science"  # 默认值 - Default value

    @staticmethod
    def _extract_title(paper_md: str) -> Optional[str]:
        """
        从论文中提取标题
        Extract title from paper

        伪代码 Pseudocode:
        1. 查找第一个一级markdown header (# Title)
           Find first level-1 markdown header (# Title)
        2. 返回标题文本
           Return title text
        """
        # 伪代码实现 - Pseudocode implementation
        # match = re.search(r"^#\s+(.+)$", paper_md, re.MULTILINE)
        # return match.group(1) if match else None
        return None

    @staticmethod
    def _extract_abstract(paper_md: str) -> Optional[str]:
        """
        从论文中提取摘要
        Extract abstract from paper

        伪代码 Pseudocode:
        1. 查找Abstract section
           Find Abstract section
        2. 提取该section的内容
           Extract content of that section
        3. 返回摘要文本
           Return abstract text
        """
        # 伪代码实现 - Pseudocode implementation
        # abstract_match = re.search(
        #     r"#+\s*abstract\s*\n(.*?)(?=#+|\Z)",
        #     paper_md,
        #     re.IGNORECASE | re.DOTALL
        # )
        # return abstract_match.group(1) if abstract_match else None
        return None

    @staticmethod
    def _extract_keywords(paper_md: str) -> List[str]:
        """
        从论文中提取关键词
        Extract keywords from paper

        伪代码 Pseudocode:
        1. 查找Keywords section
           Find Keywords section
        2. 解析关键词列表
           Parse keyword list
        3. 返回关键词列表
           Return keyword list
        """
        # 伪代码实现 - Pseudocode implementation
        # keywords_match = re.search(
        #     r"#+\s*keywords?\s*\n(.*?)(?=#+|\Z)",
        #     paper_md,
        #     re.IGNORECASE | re.DOTALL
        # )
        # if keywords_match:
        #     keywords_text = keywords_match.group(1)
        #     keywords = [k.strip() for k in re.split(r"[,;\n]", keywords_text)]
        #     return [k for k in keywords if k]
        # return []
        return []

    @staticmethod
    def _calculate_domain_score(text: str,
                                 domain_keywords: List[str],
                                 title: Optional[str] = None,
                                 abstract: Optional[str] = None,
                                 keywords: List[str] = None) -> float:
        """
        计算领域得分
        Calculate domain score

        伪代码 Pseudocode:
        1. 统计领域关键词在全文中的出现频率
           Count frequency of domain keywords in full text
        2. 如果提供了标题，对标题中的关键词给予3倍权重
           If title provided, give 3x weight to keywords in title
        3. 如果提供了摘要，对摘要中的关键词给予2倍权重
           If abstract provided, give 2x weight to keywords in abstract
        4. 如果提供了关键词列表，直接匹配的给予5倍权重
           If keyword list provided, give 5x weight to direct matches
        5. 归一化得分（除以文本长度）
           Normalize score (divide by text length)
        6. 返回最终得分
           Return final score
        """
        # 伪代码实现 - Pseudocode implementation
        # total_score = 0.0
        # text_lower = text.lower()

        # for keyword in domain_keywords:
        #     keyword_lower = keyword.lower()

        #     # 全文匹配 - Full text matching
        #     main_count = text_lower.count(keyword_lower)
        #     total_score += main_count

        #     # 标题匹配（3倍权重） - Title matching (3x weight)
        #     if title:
        #         title_count = title.lower().count(keyword_lower)
        #         total_score += title_count * 3

        #     # 摘要匹配（2倍权重） - Abstract matching (2x weight)
        #     if abstract:
        #         abstract_count = abstract.lower().count(keyword_lower)
        #         total_score += abstract_count * 2

        #     # 关键词列表匹配（5倍权重） - Keyword list matching (5x weight)
        #     if keywords:
        #         for kw in keywords:
        #             if keyword_lower in kw.lower():
        #                 total_score += 5

        # # 归一化 - Normalize
        # normalized_score = total_score / (len(text) + 1)  # 避免除以零 - Avoid division by zero
        # return normalized_score
        return 0.0

    @staticmethod
    def extract_all_domains(paper_md: str, top_n: int = 3) -> List[Tuple[str, float]]:
        """
        提取所有可能的领域及其得分
        Extract all possible domains with their scores

        伪代码 Pseudocode:
        1. 对每个领域计算得分
           Calculate score for each domain
        2. 按得分降序排序
           Sort by score in descending order
        3. 返回前N个领域
           Return top N domains

        参数 Parameters:
            paper_md: 论文markdown文本 - Paper markdown text
            top_n: 返回前几个领域 - Return top N domains

        返回 Returns:
            List[Tuple[str, float]]: 领域得分列表，格式为[(领域, 得分), ...]
                                     Domain score list, format [(domain, score), ...]
        """
        # 伪代码实现 - Pseudocode implementation
        # domain_scores = {}
        # for domain_name, domain_info in DomainRule.DOMAINS.items():
        #     score = DomainRule._calculate_domain_score(
        #         paper_md, domain_info["keywords"]
        #     )
        #     domain_scores[domain_name] = score * domain_info["weight"]

        # # 排序并返回前N个 - Sort and return top N
        # sorted_domains = sorted(
        #     domain_scores.items(),
        #     key=lambda x: x[1],
        #     reverse=True
        # )
        # return sorted_domains[:top_n]
        return []