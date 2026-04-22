# aminer-daily-paper 私有服务端到端测试报告

**日期**: 2026-04-22  
**后端**: `http://datacenter-service-py.private.aminer.cn/search/paper/AminerRecommendPapers`  
**链路**: 用户输入 → 模型意图识别(英文输出) → handle_trigger.py → run_pipeline.py → rec5_api(私有服务) → 渲染输出  
**结果**: 4/6 通过，2 个待修复

---

## 总览

| # | 用户输入 | 模型提取 | 推荐路径 | 耗时 | 论文数 | 状态 |
|---|---------|---------|---------|------|-------|------|
| A | 我是唐杰，清华大学的 | scholar: Jie Tang, org: Tsinghua University | scholar_path | ~10s | 10 | ✓ |
| B | 推荐 Jiawei Han 方向的论文 | scholar: Jiawei Han, org: University of Illinois at Urbana-Champaign | — | — | 0 | ✗ 后端 org 拼写不一致 |
| C | /aminer-dp | (无参数, token 识别) | recommend_v3 | ~6s | 10 | ✓ |
| D | 推荐 Fei-Fei Li 方向的论文 | scholar: Fei-Fei Li (无 org) | — | — | 0 | ✗ 重名无 org，意图识别应追问 |
| E | 推荐一些大模型智能体的论文 | topics: large language model, agent | topic_path | ~8s | 10 | ✓ |
| F | 推荐李飞飞方向的计算机视觉论文 | scholar: Fei-Fei Li, org: Stanford, topics: computer vision | scholar_path | ~11s | 10 | ✓ |

---

## 请求链路

```
用户输入
  │
  ├─ 无参数 ("/aminer-dp")
  │    └─ AMINER_API_KEY → 私有服务 recommend_v3 → 个性化推荐
  │
  ├─ topics ("推荐RAG论文")
  │    └─ 模型提取英文 topics → local_rec5 (ES → ranking → rerank) → topic_path 推荐
  │
  ├─ scholar + org ("我是唐杰，清华大学")
  │    └─ 模型提取英文 name/org → person search(公网) → uid
  │       ├─ uid 有论文 → scholar profile → local_rec5 → scholar_path 推荐
  │       └─ uid 无论文 → 降级: interests + topics 继续 (待部署)
  │
  ├─ scholar + org + topics ("李飞飞+CV")
  │    └─ scholar 信号 + topic 信号融合 → local_rec5 → scholar_path 推荐
  │
  └─ 异常处理
       ├─ scholar 重名无 org → 模型追问 org
       ├─ org 缩写 → 模型展开为全称
       ├─ 中文名 → 模型转为英文
       └─ uid 无论文且无其他信号 → 降级到 interests/topics (待部署)
```

---

## 逐示例详情

### A: 中文名 → 英文 (✓)

- **用户输入**: `我是唐杰，清华大学的，帮我推荐论文`
- **模型提取**: scholar: Jie Tang, org: Tsinghua University
- **后端 API**: `{"author_name": "Jie Tang", "author_org": "Tsinghua University", "size": 10}`
- **结果**: scholar_path, 10 篇论文, source=local_rec5

### B: org 缩写展开 (✗)

- **用户输入**: `推荐 Jiawei Han 方向的论文`
- **模型提取**: scholar: Jiawei Han, org: University of Illinois at Urbana-Champaign
- **后端 API**: `{"author_name": "Jiawei Han", "author_org": "University of Illinois at Urbana-Champaign", "size": 10}`
- **错误**: 后端 400 — "未找到姓名为 Jiawei Han 且机构匹配 University of Illinois at Urbana-Champaign 的 AMiner 学者"
- **原因**: person search 返回的 org 是 `University of Illinois at Urbanan`（拼写/格式差异），后端 `_org_matches` 子串匹配不上 `Urbana-Champaign`
- **需要修复**: 后端 `_org_matches` 需要更灵活的匹配（模糊/归一化）

### C: 无参数个性化 (✓)

- **用户输入**: `/aminer-dp`
- **后端 API**: `{"size": 10}` + Authorization header 带 AMINER_API_KEY
- **结果**: recommend_v3, 10 篇论文
- **验证**: 无 token 时返回 400 "Authorization / aminer_author_id / author_name / topics 至少提供一类"

### D: 重名无 org (✗ — 意图识别应拦住)

- **用户输入**: `推荐 Fei-Fei Li 方向的论文`
- **模型提取**: scholar: Fei-Fei Li (无 org)
- **错误**: 后端 400 — "学者 Fei-Fei Li 存在重名，请补充 user_org"
- **预期行为**: SKILL.md 规则要求模型在重名时追问 org，不应发送请求

### E: 中文 topics → 英文 (✓)

- **用户输入**: `推荐一些大模型智能体的论文`
- **模型提取**: topics: [large language model, agent], language_sort: zh
- **后端 API**: `{"topics": ["large language model", "agent"], "size": 10, "language_sort": "zh"}`
- **结果**: topic_path, 10 篇论文, source=local_rec5

### F: scholar + org + topics 混合 (✓)

- **用户输入**: `帮我推荐李飞飞方向的计算机视觉论文`
- **模型提取**: scholar: Fei-Fei Li, org: Stanford University, topics: [computer vision]
- **后端 API**: `{"author_name": "Fei-Fei Li", "author_org": "Stanford University", "topics": ["computer vision"], "size": 10}`
- **结果**: scholar_path, 10 篇论文, source=local_rec5

---

## 耗时统计 (skill pipeline 端到端)

| 指标 | 值 |
|------|-----|
| 平均 | ~9s |
| 最快 | 6.5s (无参数) |
| 最慢 | 11.4s (scholar_path) |
| 论文数 | 固定 10 篇 |

---

## 并发测试

| 并发数 | 请求类型 | 通过 | 失败 | wall time |
|--------|---------|------|------|-----------|
| 2 | 同构 | 2 | 0 | 9.5s |
| 5 | 同构 | 5 | 0 | 11.1s |
| 8 | 同构 | 8 | 0 | 10.3s |
| 10 | 同构 | 10 | 0 | 11.2s |
| 10 | 异构 | 10 | 0 | 14.4s |

---

## 本次改动 (vs 线上)

### 1. aminer-open-skill: SKILL.md

```diff
  Request Fields:
- | `aminer_author_id` | string | conditional | ... |
  | `author_name` | string | conditional | Scholar name. |
+ | `author_name` | string | conditional | Scholar name (English). |
  | `author_org` | string | optional | Scholar institution. |
+ | `author_org` | string | optional | Scholar institution (English full name). Required for disambiguation. |
  | `topics` | string[] | conditional | Research topics list. |
+ | `topics` | string[] | conditional | Research topics list (English). |

- At least one of `aminer_author_id`, `author_name`, or `topics` should be provided.
+ At least one of `author_name` or `topics` should be provided.

  Natural language input:
- 1. Extract `topics`, `author_name`, `author_org`, or `aminer_author_id` from the text.
+ 1. Extract `topics`, `author_name`, and/or `author_org` from the text. Apply:
+    - English only: all field values in English (唐杰 → Jie Tang, 清华大学 → Tsinghua University)
+    - Expand abbreviations: full official English names (UIUC → University of Illinois at Urbana-Champaign)
+    - Disambiguate scholars: must provide org for ambiguous names, ask user if missing
+    - Unknown English name: ask user to describe research direction
```

### 2. datacenter-service-py: profile.py

```diff
  if not collected:
-     raise ValueError(f"学者 {person_id} 缺少 authored papers，无法构建 scholar fallback profile")
+     return collected
```

效果: uid 无论文时不再抛异常，降级到 interests/topics 继续推荐。**需重新部署生效**。

---

## 待修复

| 问题 | 归属 | 说明 |
|------|------|------|
| org 子串匹配不灵活 | 后端 | `_org_matches` 无法匹配拼写/格式差异（如 `Urbanan` vs `Urbana-Champaign`） |
| 意图识别规则验证 | skill | SKILL.md 规则写了，需模型实际执行验证（重名追问、缩写展开等） |
| uid 无论文降级 | 后端 | 代码已改，需部署后验证 |
