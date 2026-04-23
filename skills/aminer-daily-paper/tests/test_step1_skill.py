#!/usr/bin/env python3
"""Local checks for aminer-daily-paper: rec5 normalization and summarize_papers helpers.

Usage: python skills/aminer-daily-paper/tests/test_step1_skill.py
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

skill_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(skill_dir))

# Keep this local check runnable even when PyYAML is unavailable.
if "yaml" not in sys.modules:
    sys.modules["yaml"] = types.SimpleNamespace(
        safe_load=lambda *_args, **_kwargs: {},
        safe_dump=lambda *_args, **_kwargs: "",
    )

from scripts.handle_trigger import _normalize_interface_payload, parse_trigger_text
from scripts.rec5_api import normalize_rec5_paper
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

raw_empty = {**raw_paper, "famous_authors": []}
result_empty = normalize_rec5_paper(raw_empty)
check("空 famous_authors 不崩", result_empty["famous_authors"] == [])

raw_none = {**raw_paper, "famous_authors": None}
result_none = normalize_rec5_paper(raw_none)
check("None famous_authors → 空列表", result_none["famous_authors"] == [])

print("\n[2] _fa_item_to_str: dict 转可读字符串")
check("dict 有 name+desc", _fa_item_to_str({"name": "Hinton", "description": "深度学习之父"}) == "Hinton: 深度学习之父")
check("dict 只有 name", _fa_item_to_str({"name": "Hinton", "description": ""}) == "Hinton")
check("dict name 为空", _fa_item_to_str({"name": "", "description": "nobody"}) == "")
check("string 直接返回", _fa_item_to_str("Hinton: 深度学习之父") == "Hinton: 深度学习之父")
check("None", _fa_item_to_str(None) == "None")

print("\n[3] handle_trigger: 输入归一化与兜底 topic")
invalid_parsed = parse_trigger_text("/aminer-dp aminer_author_id: 123456 topics: 多模态")
try:
    _normalize_interface_payload(invalid_parsed, base_dir=skill_dir)
    check("非法 aminer_author_id 抛错", False, "expected ValueError(invalid_aminer_author_id)")
except ValueError as exc:
    check("非法 aminer_author_id 抛错", str(exc) == "invalid_aminer_author_id", f"got: {exc}")

free_text_parsed = parse_trigger_text("/aminer-dp 推荐多模态和tool-use相关论文")
free_text_norm = _normalize_interface_payload(free_text_parsed, base_dir=skill_dir)
check("free_text 可推导 topics", len(free_text_norm["topics"]) >= 1, f"got: {free_text_norm['topics']}")
check("free_text topics 包含多模态", any("多模态" in t for t in free_text_norm["topics"]), f"got: {free_text_norm['topics']}")

explicit_parsed = parse_trigger_text("/aminer-dp topics: 环境保护, 生态保护")
explicit_parsed["free_text"] = "多模态和tool-use"
explicit_norm = _normalize_interface_payload(explicit_parsed, base_dir=skill_dir)
check("显式 topics 优先于 free_text 兜底", explicit_norm["topics"] == ["环境保护", "生态保护"], f"got: {explicit_norm['topics']}")

print(f"\n{'='*50}")
print(f"结果: {passed} 通过, {failed} 失败")
if failed:
    print("⚠️  有测试失败，请检查！")
    sys.exit(1)
print("✅ 全部通过")
