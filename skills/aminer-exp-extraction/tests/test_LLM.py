"""LLM 服务连通性测试（LLM + SciBERT）。

服务地址完全来自环境变量（本包不内置任何端点）：
  - LLM_CHAT_URL    OpenAI 兼容 chat completions 端点
  - BERT_SERVER_URL  SciBERT 服务 base URL（/health、/filter、/filter/batch）
两个变量都设置时本文件的 5 个用例才会运行（会真实调用服务）；未设置时整文件自动
skip（tests/ 其他文件不依赖服务，离线可跑）。

跑法：
  .venv/bin/python tests/test_LLM.py               # 脚本方式，逐项打印
  .venv/bin/python -m pytest tests/test_LLM.py -v  # pytest 方式
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROD_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROD_ROOT))

# 服务地址只从环境变量读取；未设置则整文件跳过（不发起任何请求）
LLM_CHAT_URL = os.environ.get("LLM_CHAT_URL", "")
BERT_SERVER_URL = os.environ.get("BERT_SERVER_URL", "")

if not LLM_CHAT_URL or not BERT_SERVER_URL:
    pytest.skip(
        "service env vars not set (LLM_CHAT_URL / BERT_SERVER_URL) — "
        "set them to run live-service tests",
        allow_module_level=True,
    )

import requests  # noqa: E402

from pipeline.benchmark.config import LLM_MODEL  # noqa: E402

LLM_TIMEOUT = 60
BERT_TIMEOUT = 30

# 标准的两句实验性/非实验性文本（与生产 BERT filter 语义对齐）
EXP_SENTENCE = "We achieve 95% accuracy on ImageNet."
NONEXP_SENTENCE = "This paper is organized as follows."


def test_qwen_chat_completion() -> None:
    """LLM chat（生产 payload 形态：显式 model 字段 + 关 thinking）。"""
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": "用一句话介绍 SciBERT"}],
        "max_tokens": 100,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    resp = requests.post(LLM_CHAT_URL, json=payload, timeout=LLM_TIMEOUT)
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text[:200]}"
    data = resp.json()
    content = data["choices"][0]["message"]["content"].strip()
    assert content, "empty reply content"
    usage = data.get("usage", {})
    assert usage.get("prompt_tokens") and usage.get("completion_tokens"), usage
    print(f"\n[LLM] model={data.get('model')} reply: {content[:80]}")
    print(f"[LLM] usage: prompt={usage.get('prompt_tokens')} "
          f"completion={usage.get('completion_tokens')}")


def test_scibert_health() -> None:
    """SciBERT /health（集群 nginx 入口 /bert 前缀路由）。"""
    resp = requests.get(f"{BERT_SERVER_URL}/health", timeout=BERT_TIMEOUT)
    assert resp.status_code == 200, f"HTTP {resp.status_code}"
    data = resp.json()
    assert data.get("status") == "ok", data
    assert "SciBERT" in data.get("model", ""), data
    print(f"\n[SciBERT] health: {data}")


def test_scibert_filter() -> None:
    """SciBERT /filter 单篇过滤：实验句保留、组织句剔除。"""
    payload = {
        "sentences": [EXP_SENTENCE, NONEXP_SENTENCE],
        "threshold": 0.6,
    }
    resp = requests.post(f"{BERT_SERVER_URL}/filter", json=payload, timeout=BERT_TIMEOUT)
    assert resp.status_code == 200, f"HTTP {resp.status_code}"
    data = resp.json()
    assert data["total"] == 2, data
    assert EXP_SENTENCE in data["kept"], data
    assert NONEXP_SENTENCE not in data["kept"], data
    # confidences 与 kept 对齐（生产端 select_llm_sentences 成对消费），不含被剔除句
    assert len(data["confidences"]) == data["kept_count"], data
    print(f"\n[SciBERT] /filter kept {data['kept_count']}/{data['total']} "
          f"({data['inference_time_ms']} ms)")


def test_scibert_filter_batch_contract() -> None:
    """/filter/batch 多论文：响应字段与 bert_batch_client 依赖的契约对齐。"""
    payload = {
        "papers": [
            {"paper_id": "paper-001", "sentences": [EXP_SENTENCE, "Hello world."]},
            {"paper_id": "paper-002", "sentences": ["The experiment shows 3x speedup over the baseline."]},
        ],
        "threshold": 0.6,
        "batch_size": 32,
    }
    resp = requests.post(f"{BERT_SERVER_URL}/filter/batch", json=payload, timeout=BERT_TIMEOUT)
    assert resp.status_code == 200, f"HTTP {resp.status_code}"
    data = resp.json()
    assert data["paper_count"] == 2, data
    assert data["total_sentences"] == 3, data
    by_id = {p["paper_id"]: p for p in data["papers"]}
    for pid, n_sentences in (("paper-001", 2), ("paper-002", 1)):
        p = by_id[pid]
        assert p["total"] == n_sentences, p
        assert p["kept_count"] == len(p["kept"]) == len(p["indices"]) == len(p["confidences"]), p
        assert all(0 <= i < n_sentences for i in p["indices"]), p
    assert by_id["paper-001"]["kept"] == [EXP_SENTENCE], by_id["paper-001"]
    print(f"\n[SciBERT] /filter/batch papers={data['paper_count']} "
          f"kept={data['total_kept']}/{data['total_sentences']} "
          f"({data['inference_time_ms']} ms)")


def test_filter_papers_batch_client_default_url() -> None:
    """项目生产客户端 filter_papers_batch：默认 URL（无 env 时即集群入口）端到端可用。"""
    from pipeline.production.adapters.bert_batch_client import filter_papers_batch

    papers = [{"paper_id": "paper-001", "sentences": [EXP_SENTENCE, NONEXP_SENTENCE]}]
    data = filter_papers_batch(papers, threshold=0.6, batch_size=32)  # url 默认取 config
    assert data["paper_count"] == 1, data
    p = data["papers"][0]
    assert p["kept"] == [EXP_SENTENCE] and p["indices"] == [0], p
    assert "client_elapsed_sec" in data, data
    print(f"\n[client] filter_papers_batch -> kept {p['kept_count']}/{p['total']} "
          f"(server {data['inference_time_ms']} ms, client {data['client_elapsed_sec']} s)")


if __name__ == "__main__":
    tests = [
        test_qwen_chat_completion,
        test_scibert_health,
        test_scibert_filter,
        test_scibert_filter_batch_contract,
        test_filter_papers_batch_client_default_url,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:  # noqa: BLE001 — 脚本方式逐项汇报
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
