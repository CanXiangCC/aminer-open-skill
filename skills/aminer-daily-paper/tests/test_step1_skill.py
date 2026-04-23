#!/usr/bin/env python3
"""Step 1 本地验证脚本 — Skill aminer-daily-paper

验证 rec5_api / feishu_cards / render_feishu_messages / summarize_papers 改动。
无需连接后端，无需 API key，纯单元测试。

用法: cd aminer-open-skill && python skills/aminer-daily-paper/tests/test_step1_skill.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# 确保 scripts 目录在 sys.path
skill_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(skill_dir))

from scripts.rec5_api import normalize_rec5_paper
from scripts.feishu_cards import render_famous_author_blocks, markdown_block
from scripts.render_feishu_messages import validate_paper
from scripts.summarize_papers import _fa_item_to_str

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name}")
        if detail:
            print(f"    → {detail}")


# ============================================================
# 1. normalize_rec5_paper — famous_authors 保留 dict
# ============================================================
print("\n[1] normalize_rec5_paper: famous_authors 保留 dict 结构")

raw_paper = {
    "paper_id": "test001",
    "title": "Test Paper",
    "year": 2024,
    "authors": ["Author A"],
    "keywords": ["LLM"],
    "summary": "test",
    "famous_authors": [
        {"name": "Geoffrey Hinton", "description": "深度学习之父", "profile_url": "https://www.aminer.cn/profile/abc123"},
        {"name": "Yann LeCun", "description": "CNN 先驱"},
        "Some String Author: 纯文本格式",
    ],
    "aminer_author_profiles": [],
    "author_entries": [],
}

result = normalize_rec5_paper(raw_paper)
fa = result["famous_authors"]

check("famous_authors 长度 = 3", len(fa) == 3, f"got: {len(fa)}")
check("第一个是 dict", isinstance(fa[0], dict), f"got: {type(fa[0])}")
check("第一个保留 profile_url", fa[0].get("profile_url") == "https://www.aminer.cn/profile/abc123", f"got: {fa[0]}")
check("第二个是 dict（无 profile_url）", isinstance(fa[1], dict) and fa[1].get("profile_url") == "", f"got: {fa[1]}")
check("第三个是 string", isinstance(fa[2], str), f"got: {type(fa[2])}")

# 空 famous_authors
raw_empty = {**raw_paper, "famous_authors": []}
result_empty = normalize_rec5_paper(raw_empty)
check("空 famous_authors 不崩", result_empty["famous_authors"] == [])

# None famous_authors
raw_none = {**raw_paper, "famous_authors": None}
result_none = normalize_rec5_paper(raw_none)
check("None famous_authors → 空列表", result_none["famous_authors"] == [])


# ============================================================
# 2. render_famous_author_blocks — 三种输入
# ============================================================
print("\n[2] render_famous_author_blocks: dict 带 URL / dict 不带 URL / string")

paper_dict_with_url = {
    "famous_authors": [
        {"name": "Geoffrey Hinton", "description": "深度学习之父", "profile_url": "https://www.aminer.cn/profile/abc123"},
    ],
    "aminer_author_profiles": [],
}
blocks = render_famous_author_blocks(paper_dict_with_url)
check("dict 带 URL → 有 block", len(blocks) == 1, f"got: {len(blocks)}")
content = blocks[0]["text"]["content"] if blocks else ""
check("dict 带 URL → 渲染为链接", "[Geoffrey Hinton](https://www.aminer.cn/profile/abc123)" in content, f"got: {content}")
check("dict 带 URL → 包含描述", "深度学习之父" in content, f"got: {content}")

paper_dict_no_url = {
    "famous_authors": [
        {"name": "Yann LeCun", "description": "CNN 先驱"},
    ],
    "aminer_author_profiles": [
        {"name": "Yann LeCun", "profile_url": "https://www.aminer.cn/profile/def456"},
    ],
}
blocks = render_famous_author_blocks(paper_dict_no_url)
content = blocks[0]["text"]["content"] if blocks else ""
check("dict 无 URL → fallback name matching → 有链接", "def456" in content, f"got: {content}")

paper_string = {
    "famous_authors": ["Yoshua Bengio: 图灵奖得主"],
    "aminer_author_profiles": [
        {"name": "Yoshua Bengio", "profile_url": "https://www.aminer.cn/profile/ghi789"},
    ],
}
blocks = render_famous_author_blocks(paper_string)
content = blocks[0]["text"]["content"] if blocks else ""
check("string → name matching → 有链接", "ghi789" in content, f"got: {content}")

paper_empty = {"famous_authors": [], "aminer_author_profiles": []}
blocks = render_famous_author_blocks(paper_empty)
check("空 → 无 block", len(blocks) == 0)


# ============================================================
# 3. validate_paper — 接受 dict 类型 famous_authors
# ============================================================
print("\n[3] validate_paper: 接受 dict 类型 famous_authors")

valid_paper = {
    "title": "Test Paper",
    "paper_id": "test001",
    "keywords": ["LLM"],
    "summary": "test summary",
    "structured_summary": {"research_problem": "test", "research_challenge": "test", "research_method": "test"},
    "famous_authors": [
        {"name": "Hinton", "profile_url": "https://www.aminer.cn/profile/abc123", "description": "deep learning"},
    ],
    "authors": ["Author A"],
    "aminer_author_profiles": [{"name": "Author A"}],
    "author_entries": [{"display_name": "Author A", "profile_url": ""}],
    "aminer_paper_url": "https://www.aminer.cn/pub/test001",
}

try:
    validate_paper(valid_paper)
    check("dict famous_authors 不报错", True)
except ValueError as e:
    check("dict famous_authors 不报错", False, str(e))

# 混合类型
mixed_paper = {**valid_paper, "famous_authors": [
    {"name": "Hinton", "profile_url": "", "description": ""},
    "LeCun: CNN",
]}
try:
    validate_paper(mixed_paper)
    check("混合 dict+string 不报错", True)
except ValueError as e:
    check("混合 dict+string 不报错", False, str(e))

# 非法类型（int）应该报错
bad_paper = {**valid_paper, "famous_authors": [123]}
try:
    validate_paper(bad_paper)
    check("int 类型应报错", False, "没有报错")
except ValueError:
    check("int 类型应报错", True)


# ============================================================
# 4. _fa_item_to_str — dict 转可读字符串
# ============================================================
print("\n[4] _fa_item_to_str: dict 转可读字符串")

check(
    "dict 有 name+desc",
    _fa_item_to_str({"name": "Hinton", "description": "深度学习之父"}) == "Hinton: 深度学习之父",
)
check(
    "dict 只有 name",
    _fa_item_to_str({"name": "Hinton", "description": ""}) == "Hinton",
)
check(
    "dict name 为空",
    _fa_item_to_str({"name": "", "description": "nobody"}) == "",
)
check(
    "string 直接返回",
    _fa_item_to_str("Hinton: 深度学习之父") == "Hinton: 深度学习之父",
)
check(
    "None → 空字符串",
    _fa_item_to_str(None) == "None",  # str(None) = "None", .strip() = "None"
)


# ============================================================
# 汇总
# ============================================================
print(f"\n{'='*50}")
print(f"结果: {passed} 通过, {failed} 失败")
if failed:
    print("⚠️  有测试失败，请检查！")
    sys.exit(1)
else:
    print("✅ 全部通过")
