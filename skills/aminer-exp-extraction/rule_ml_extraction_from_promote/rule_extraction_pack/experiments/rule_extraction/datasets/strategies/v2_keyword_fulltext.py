"""
datasets--策略v2--关键词全文匹配

策略描述: 全文搜索数据集关键词模式，优先保证召回
Strategy: Full-text keyword matching for datasets, prioritize recall

Layer 1 - 高召回策略 - High Recall Strategy
"""

import re
import sys
from pathlib import Path
from typing import Optional, List, Dict

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


class DatasetRuleV2:
    """数据集提取规则 - Dataset Extraction Rule - V2 (Keyword Full Text)"""

    @staticmethod
    def extract(paper_md: str, paper_id: str = "") -> Optional[List[Dict]]:
        """
        从全文提取数据集
        Extract datasets from full text

        策略 Strategy:
        1. 匹配缩写 + 引用: LFW [90], IJB-A [110]
        2. 匹配引用 + 缩写: [90] LFW, [110] IJB-A
        3. 匹配多引用: MegaFace [105], [145]
        4. 匹配大写单词序列: VGGFace2, CASIAWebFace
        5. 合并去重

        Args:
            paper_md: 论文markdown文本 - Paper markdown text
            paper_id: 论文ID（本策略不使用，保持接口一致） - Paper ID (not used, for interface consistency)

        Returns:
            Optional[List[Dict]]: 提取的datasets数组，未找到返回None - Extracted datasets array, None if not found
        """
        # 不清理引用格式，保留 [数字] - Don't clean citations, keep [number]
        # 只移除LaTeX和代码块 - Only remove LaTeX and code blocks
        md_for_search = paper_md
        md_for_search = re.sub(r'\$\$.*?\$', '[MATH]', md_for_search, flags=re.DOTALL)
        md_for_search = re.sub(r'\$[^$]+?\$', '[MATH]', md_for_search)
        md_for_search = re.sub(r'```.*?```', '', md_for_search, flags=re.DOTALL)
        md_for_search = re.sub(r'`[^`]+`', '', md_for_search)

        # 按句子处理，避免跨句误匹配 - Process by sentence
        sentences = re.split(r'[.!?]', md_for_search)

        dataset_candidates = set()

        for sentence in sentences:
            # 模式 1: 缩写 + 引用 - Acronym + citation
            # LFW [90], IJB-A [110], MegaFace [105]
            matches = re.finditer(
                r'\b([A-Z]{2,6}(?:-[A-Z0-9]+)?)\s*(?:,\s*)?\[\d+(?:,\s*\d+)*\]',
                sentence
            )
            for m in matches:
                name = m.group(1)
                if DatasetRuleV2._is_valid_dataset_name(name):
                    dataset_candidates.add(name)

            # 模式 2: 引用 + 缩写 - Citation + acronym
            # [90] LFW, [110] IJB-A, [105], [145] MegaFace
            matches = re.finditer(
                r'\[\d+(?:,\s*\d+)*\]\s*([A-Z]{2,6}(?:-[A-Z0-9]+)?)\b',
                sentence
            )
            for m in matches:
                name = m.group(1)
                if DatasetRuleV2._is_valid_dataset_name(name):
                    dataset_candidates.add(name)

            # 模式 3: 数据集 and 数据集 - Dataset and Dataset
            # LFW and MegaFace, MegaFace and IJB-A
            matches = re.finditer(
                r'\b([A-Z]{2,6}(?:-[A-Z0-9]+)?)\s+and\s+([A-Z]{2,6}(?:-[A-Z0-9]+)?)\b',
                sentence,
                re.IGNORECASE
            )
            for m in matches:
                for i in [1, 2]:
                    name = m.group(i)
                    if DatasetRuleV2._is_valid_dataset_name(name):
                        dataset_candidates.add(name)

            # 模式 4: "the [Dataset] dataset"
            # the LFW dataset, the MegaFace dataset
            matches = re.finditer(
                r'(?:the|a|an)\s+([A-Z][A-Za-z0-9\-]+?)\s+dataset\b',
                sentence,
                re.IGNORECASE
            )
            for m in matches:
                name = m.group(1).strip()
                if DatasetRuleV2._is_valid_dataset_name(name):
                    dataset_candidates.add(name)

            # 模式 5: 常见多词名称 (2个以上大写字母开头)
            # VGGFace2, CASIAWebFace, UMDFacesVideos, ImageNet21K
            # 匹配: 大写+小写+大写... 的模式
            matches = re.finditer(
                r'\b([A-Z][A-Za-z0-9]+(?:[A-Z][a-z0-9]+)+)\b',
                sentence
            )
            for m in matches:
                name = m.group(1)
                if len(name) >= 4 and DatasetRuleV2._is_valid_dataset_name(name):
                    # 检查是否包含足够的大写字母
                    if sum(1 for c in name if c.isupper()) >= 2:
                        dataset_candidates.add(name)

        # 构建结果 - Build result
        result = []
        for name in sorted(dataset_candidates):
            ds = {
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
            result.append(ds)

        return result if result else None

    @staticmethod
    def _is_valid_dataset_name(name: str) -> bool:
        """
        验证是否是有效的数据集名称（基于实际gold数据集模式）
        Validate if it's a valid dataset name (based on gold dataset patterns)
        """
        if not name or len(name) < 2:
            return False

        name_upper = name.upper()
        name_lower = name.lower()

        # 必须至少2个字母 - Must have at least 2 letters
        letter_count = sum(1 for c in name if c.isalpha())
        if letter_count < 2:
            return False

        # 首字母大写 - First letter must be uppercase
        if not name[0].isupper():
            return False

        # ========== 模式匹配白名单 - Pattern whitelist ==========
        # 基于gold数据分析的命名模式
        patterns = [
            # 缩写: LFW, IJB-A, RFW, CFP, YTF, CALFW, MORPH, CACD, FG-NET
            r'^[A-Z]{2,6}$',
            # 缩写+连字符: IJB-A, MS-Celeb-1M, NIR-VIS 2.0
            r'^[A-Z]{2,6}(?:-[A-Z0-9\.]+)+$',
            # 全称+缩写: CASIA-WebFace, VGGFace2, ShapeNet-ViPC
            r'^[A-Z][A-Za-z0-9]+(?:[A-Z][a-z0-9]+)+$',
            # 包含特定常见前缀
            r'^(?:Image|Pascal|ShapeNet|VGG|CASIA|COCO|IJB|UMDFaces|CFP|CFPLFW|SLLFW|YTF|CALFW|MORPH|CACD|FG-NET|RFW|DFW|ELFW|DELFW|FAM|FERET|AR)',
            # Google, Facebook (已知私有数据集)
            r'^(?:Google|Facebook|CelebFaces\+)$',
        ]

        for pattern in patterns:
            if re.match(pattern, name):
                return True

        # ========== 黑名单 - Blacklist ==========
        # 模型/框架名称
        blacklist = {
            # 深度学习框架/模型
            'resnet', 'vgg', 'alexnet', 'googlenet', 'inception', 'mobilenet',
            'shufflenet', 'squeezenet', 'densenet', 'mobiface', 'efficientnet',
            'darknet', 'wide_resnet', 'pytorch', 'tensorflow', 'caffe', 'mxnet',
            'chainer', 'keras', 'torch', 'tf', 'pt',
            # 常见的模型组件
            'lstm', 'gru', 'rnn', 'cnn', 'gcn', 'transformer', 'bert',
            'llama', 'gpt', 'chatgpt', 'gemini', 'claude', 'gemma',
            # 通用词/领域词
            'llms', 'scenes', 'net', 'cnn', 'deep', 'super', 'ultra',
            'wordnet', 'imagenet', 'coco', 'voc', 'mnist', 'cifar',
            'cityscapes', 'pascal', 'shape', 'coco2017', 'vggface',
            # 不常见的短词（可能是误匹配）
            'id', 'llms', 'sc', 'tse', 'lb', 'lp', 'cnns', 'lbp', 'hog',
            # 版本号/数字标识（可能是误匹配）
            'v1', 'v2', 'v3', 'v4', 'v5', 'v6',
        }

        name_clean = re.sub(r'[-.]', '', name_lower)
        if name_clean in blacklist or name_clean.replace('net', '') in blacklist:
            return False

        # 必须包含至少2个大写字母（区分普通词）
        upper_count = sum(1 for c in name if c.isupper())
        lower_count = sum(1 for c in name if c.islower())
        if upper_count < 2 and lower_count < 2:
            return False

        # 纯数字或数字+后缀的（如 v1, v2）
        if re.match(r'^v\d+$', name):
            return False

        return True


if __name__ == "__main__":
    # 测试 - Test
    test_md = """
    We evaluate our method on LFW [90] and IJB-A [110]. The MegaFace [105], [145] benchmark
    provides large-scale evaluation. We also use VGGFace2 [22] for additional testing.

    The CASIA-WebFace dataset provides public training data. [90] reports state-of-the-art
    accuracy on LFW benchmark. We achieve better results than state-of-the-art.

    Table I shows comparison on UMDFaces [11] and YTF [220].
    """

    result = DatasetRuleV2.extract(test_md, "test")
    print(f"Extracted {len(result) if result else 0} datasets:")
    if result:
        for ds in result:
            print(f"  - {ds['name']}")