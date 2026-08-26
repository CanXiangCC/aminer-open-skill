---
name: aminer-pdf-ocr
version: 3.0.0
author: AMiner
contact: report@aminer.cn
description: >
  [激活条件] 用户提供 PDF 并要求 OCR、转 Markdown 或抽取论文实验信息时使用。
  [功能] 调用 AMiner MinerU 开放平台异步接口，上传、轮询、下载 ZIP 并安全落盘；随后由 Agent 按 references/experiment_prompt.md 从 result.md 抽取实验 JSON。
  [路由规则] 引文真实性核验使用 pdf-citation-verifier；论文检索使用 aminer-academic-search / aminer-free-academic。
metadata:
  {"openclaw": {"emoji": "📄", "requires": {"bins": ["python3"], "env": ["OPEN_PLATFORM_TOKEN"]}, "primaryEnv": "OPEN_PLATFORM_TOKEN"}}
---

# PDF OCR + 实验信息抽取

脚本会先校验 PDF，再调用 AMiner MinerU 开放平台：上传任务、处理队列拥塞、轮询状态、下载临时 ZIP、提取 Markdown 和图片。OCR 成功后，Agent 读取完整 `result.md`，严格按照 `references/experiment_prompt.md` 写出 `experiments.json`。

## 执行前检查

1. 确认 `OPEN_PLATFORM_TOKEN` 已设置，绝不打印其值。
2. 安装 `requests` 和 `pypdf`。
3. 输入必须是本地 PDF 或 HTTP(S) URL。开放平台只接受未加密、1–30 页且不超过 10 MiB 的真实 PDF。

## 执行

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ocr.py" --input "/abs/path/to/paper.pdf"
```

可用参数：`--output-dir`、`--request-timeout`、`--poll-timeout`、`--max-upload-attempts`、`--no-save-images`、`--output`。旧的 `MINERU_BASE_URL`、backend、页码范围、公式和表格参数不适用于开放平台。

## 接口约束

- 上传和轮询必须使用同一个 token。
- 上传 `code: 202` 只代表入队；复用任务可能是 `code: 200`，必须使用返回的 `job_id`。
- 不能只看 `success`、HTTP 状态或 `code`；必须看 `data.status` 和 `data.is_finish`。
- `preparing`、`queued`、`running` 继续轮询；`success` 下载 ZIP；`failed`、`timeout`、`queue_timeout`、`expired`、`unknown` 停止。
- `data.queue_full` 按 `retry_after_seconds` 有限退避。
- 临时下载 URL 直连且不携带 Authorization，也不写入 `response.json`。
- ZIP 按 `.md` 和 `_middle.json` 后缀查找，不依赖 `document/` 目录名。

## 实验抽取

除非用户明确要求 OCR-only，否则读取完整 `result.md`，按 `references/experiment_prompt.md` 写入一个 JSON 对象到 `experiments.json`，并在回复中展示相同的完整 JSON。不得增加 `justification` 字段，不得编造实验、数据集、指标或分数。OCR 失败时只报告错误，不生成虚假抽取结果。

## 真实示例

默认本地样例为 `data/pdf/applsci-14-11736.pdf`（不入库，需自行放置）。真实测试只有在同时设置 `RUN_MINERU_LIVE=1` 和 `OPEN_PLATFORM_TOKEN` 时才启用，默认跳过。
