---
name: aminer-exp-extraction-endpoints
description: aminer-exp-extraction skill 模型服务现状 — 全部走 BigModel glm-5.3（用户 2026-08-28 决定），线上 AMiner 网关 extraction 接口仍未部署完
metadata:
  type: project
---

aminer-open-skill 仓库的 `skills/aminer-exp-extraction`（单脚本 `extract_experiments.py`）自 2026-08-28 起**所有模型服务统一走智谱 BigModel 公共 API** `https://open.bigmodel.cn/api/paas/v4/chat/completions`（model `glm-5.3`，`Authorization: Bearer $BIGMODEL_API_KEY`，`stream:false`，OpenAI messages 格式）：

- **句子过滤（Stage-A）**：默认 `--filter glm` —— `pipeline/production/adapters/glm_sentence_filter.py`，一次 chat 调用给编号句子打实验相关性分，客户端按 score≥0.6（冻结阈值）、原顺序、cap 60 截取；SciBERT `/filter/batch` 降级为可选覆盖（`--filter bert` + `BERT_SERVER_URL`，需 `AMINER_API_KEY`）。
- **抽取（Stage-B）**：`OpenAIChatLLMClient`（`pipeline/benchmark/stages/openai_chat_llm_client.py`，唯一 LLM 实现；`SingleLLMClient` 是它的薄子类），wf1/wf4/wf8 全部经它走 BigModel。temperature 0.05 / max_tokens 2048 冻结。旧的 `LLM_VENDOR=aminer_extraction`（chat_template_kwargs + AMiner 鉴权）与本地 Ollama 后端已删除。

**Why:** 用户 2026-08-28 明确要求"模型服务都改为基于 open.bigmodel.cn curl"且"BERT 服务也用 GLM 的"；且线上网关 `datacenter.aminer.cn/gateway/open_platform` extraction 接口未部署完（LLM 40301、BERT `code=200 msg='no data'`，2026-08-28 实测仍如此）。内网 `http://datacenter-service-py.private.aminer.cn/extraction` 的 BERT `/filter/batch` 当天实测可用（可作 bert 覆盖模式的 BERT_SERVER_URL）。

**How to apply:**
- 运行前置：只需 `BIGMODEL_API_KEY`（`OPENAI_API_KEY` 兜底）；CLI 缺 key 时会早期报错退出。
- md 输入：`--md` / `--md-dir` / `--csv`（paper_id,md_url，下载到 `--md-cache`）。
- 5390877920f70186a0d2cadd 的 md_url（用户提供）：`https://aminer-platform-public.oss-cn-beijing.aliyuncs.com/chat_with_paper/pdfImage/minerU/2026/6/30/6a43dafa2e7165df44101909/6a43dafa2e7165df44101909.md`（真实论文为 Sturtevant/Felner/Helmert "Value Compression of Pattern Databases"；AMiner 记录的标题/作者/年份元数据是错误合并的）。
- e2e 状态：2026-08-28 真实跑通（paper 5390877920f70186a0d2cadd，ok exp=2，60/87 句，212.7s）。要点：glm-5.3 太慢被用户取消后，默认模型改为 **glm-5.3-flash**（探测 3.1s vs 5.2 的 8.4s）；glm-5.3/5.3-flash/5.2 均为"始终思考"模型（`thinking.type=disabled` 会 400，提示用 low/high/max，注意参数是 `{"level": ...}` 不是 `{"type": ...}`），client 默认发 `thinking={"level":"low"}`（env `LLM_THINKING_LEVEL` 可调，`off` 省略）；BigModel 的 `max_tokens` 含 reasoning_tokens，故 filter 预算 16384、抽取经 `num_predict_override=8192`。
- 注意：本机默认 `python3` 是 3.8.16，`wf8_core.py:34` 的 `list[str]` 需 3.9+，用 `/usr/local/bin/python3.11` 跑。
