---
name: aminer-pdf-citation-verifier
version: 1.0.0
author: AMiner
contact: report@aminer.cn
description: >
  [激活条件] 当用户提供论文 PDF（文件路径或上传），并要求核验、审计、检查参考文献是否为真实存在的文献时使用——例如"检查这篇论文的参考文献有没有伪造"、"找出虚假引用"、"验证 bibliography"。
  [适用场景] 把 PDF 上传到 AMiner pdf-citation-verifier 服务，轮询异步作业并返回每条参考文献的判定（REAL / LIKELY_REAL / NEEDS_REVIEW / LIKELY_FAKE / FAKE）以及整体是否存在 hallucination 的结论。
  [路由规则] 不要用于普通论文检索、学者查询、引用意图分析或引用图谱构建——这些场景应改用 aminer-academic-search、aminer-free-academic 或 paper-source-trace。本 Skill 只判断"引用是否真实存在"。
metadata:
  {
    "openclaw":
      {
        "emoji": "🕵️",
        "requires": {
          "bins": ["python3"],
          "env": ["AMINER_API_KEY"]
        },
        "primaryEnv": "AMINER_API_KEY"
      }
  }
---

# PDF Citation Verifier（PDF 引用核验）

把一篇论文 PDF 上传到 AMiner `pdf-citation-verifier` 服务，等待异步作业完成，并返回结构化的核验结果。可以通过自然语言触发，也可以使用 `/pdf-citation-verifier`。

## 这个 Skill 做什么

服务端会从 PDF 中解析参考文献，逐条调用 AMiner SearchPro 查询，给每条引用一个标签：

- `REAL`——AMiner 中能高置信度匹配。
- `LIKELY_REAL`——部分匹配，大概率真实。
- `NEEDS_REVIEW`——证据不足，需要人工审阅。
- `LIKELY_FAKE`——部分不匹配，疑似伪造。
- `FAKE`——找不到合理匹配。

网关返回统一信封 `{"code": 200, "success": true, "msg": "", "data": ..., "log_id": "..."}`，脚本会自动拆掉这层再输出。

- `POST /api/v3/paper/citation/verify/upload` 的 `data` 是对象：`{"job_id": "verify_..."}`。
- `GET /api/v3/paper/citation/result?job_id=...` 的 `data` 是只含一个元素的数组，元素里有顶层字段 `is_finish`、`has_hallucination`、`hallucination_ratio`、`total`、`counts_by_status`、`summary`、`urls`、`report`、`result` 等。

Skill 返回这个记录加上 `job_id`，用户后续可凭 `job_id` 再次查询。

## 文件结构

- `SKILL.md` / `SKILL.zh.md`——英文 / 中文 Skill 定义（本文件）。
- `commands/pdf-citation-verifier.md`——slash command 入口。
- `scripts/verify_pdf.py`——HTTP 客户端：上传 → 轮询 → 拆封信封后打印结果记录。
- `requirements.txt`——Python 依赖（`requests`）。

## Pre-flight 检查

在执行脚本前必须先过下面三项；任何一项失败立即停止并告知用户。

**1. AMINER_API_KEY**

```bash
[ -z "${AMINER_API_KEY+x}" ] && echo "AMINER_API_KEY missing" || echo "AMINER_API_KEY exists"
```

缺失则停止，引导用户到 https://open.aminer.cn 获取 Token，然后 `export AMINER_API_KEY=<token>`。**任何输出中都不得打印 token 的值。**

**2. Python 依赖**

```bash
python3 - <<'PY'
import importlib.util
missing = [name for name in ("requests",) if importlib.util.find_spec(name) is None]
print("Missing: " + ", ".join(missing) if missing else "Python dependencies exist")
PY
```

缺失则提示安装：`pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`。

**3. PDF 输入**

用户必须提供存在的本地 `.pdf` 路径。如果只描述了论文但没给文件，必须主动追问 PDF 路径。**不要自行编造或下载 PDF。**

## 执行示例

默认参数（最多核验 50 条，自动轮询到完成）：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verify_pdf.py" \
  --pdf "/abs/path/to/paper.pdf"
```

完整参数：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verify_pdf.py" \
  --pdf "/abs/path/to/paper.pdf" \
  --max-refs 80 \
  --strict \
  --timeout 900 \
  --poll-interval 5 \
  --output outputs/pdf-citation-verifier/<safe-paper-stem>/result.json
```

仅提交不等待（拿到 `job_id` 后让用户自己查）：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verify_pdf.py" \
  --pdf "/abs/path/to/paper.pdf" --no-wait
```

凭已有 `job_id` 直接拉结果（不重新上传）：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verify_pdf.py" \
  --job-id verify_20260527T090207Z_a72c9ba5
```

## 参数说明

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--pdf` | 必填（除非给了 `--job-id`） | 本地 `.pdf` 路径。服务端 body 上限 50 MB。 |
| `--job-id` | – | 不上传，只拉已有作业的结果。 |
| `--max-refs` | 50 | 服务端硬上限 100。 |
| `--strict` | 关闭 | 开启后对部分匹配会更严格地判 FAKE。 |
| `--no-wait` | 关闭 | 与 `--pdf` 连用：仅提交作业并返回 `job_id`，不轮询；与 `--job-id` 连用：单次查询后立即返回，不进入轮询循环。 |
| `--timeout` | 600 | 轮询的整体超时（秒）。 |
| `--poll-interval` | 5 | 两次轮询之间的间隔（秒）。 |
| `--request-timeout` | 120 | 单次 HTTP 请求超时（秒）。 |
| `--output` | - | 可选：把最终 JSON 同步落到本地路径。 |

## 环境变量

| 变量 | 是否必需 | 用途 |
| --- | --- | --- |
| `AMINER_API_KEY` | 是 | 写入请求头 `Authorization` 的 JWT。 |
| `PDF_CITATION_VERIFIER_BASE_URL` | 否 | 覆盖网关 base URL，默认 `https://datacenter.aminer.cn/gateway/open_platform`。 |

## 运行约束

- **绝对不要**以任何方式打印、日志或回显 `AMINER_API_KEY` 的值。
- **绝对不要**伪造核验结果。脚本失败或超时时，原样汇报错误，不得自行编造。
- 响应中的 `urls`、`report`、`result`、`pdf` 都是服务端产物，多半是带有效期 `url_expire_seconds` 的预签名链接。不要谎称这些路径在用户本机存在；需要本地 JSON 副本时用 `--output`。
- 注意单用户活跃作业上限（服务端超出会返回 429）。出现 429 时停下并告知用户先等已提交的作业完成。
- 任何 `LIKELY_FAKE` / `FAKE` 都只是"需要人工复核"的信号，不是终审。展示结果时尽量带上 `counts_by_status` 与逐条原因（若响应包含）。

## 结果展示

脚本返回后，至少向用户呈现：

- `job_id`
- `total`（核验的引用数量）
- `has_hallucination`、`hallucination_ratio`
- 基于 `counts_by_status` 的状态计数小表（REAL / LIKELY_REAL / NEEDS_REVIEW / LIKELY_FAKE / FAKE 等）
- 响应里的 `urls.report` / `urls.result` 链接，需要附注会在 `url_expire_seconds` 后过期
- 完整 JSON 要么 `--output` 落盘，要么直接回显给用户，不要静默丢弃。

如果 `is_finish` 为 `true` 且 `status` / `msg` 指示失败，把信息告知用户并建议重试。
