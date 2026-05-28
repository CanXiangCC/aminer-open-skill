---
description: Verify whether the references in a paper PDF are real, using AMiner pdf-citation-verifier
argument-hint: [pdf: <pdf-path> | job-id: <verify_...> max-refs: <1-100> strict: yes|no no-wait: yes|no output: <json-path> | 自然语言]
allowed-tools: Read, Write, Bash, Glob
---

# /pdf-citation-verifier — PDF Citation Verifier

User invoked the PDF Citation Verifier skill with:

```text
$ARGUMENTS
```

## Language Routing / 语言路由

- If `$ARGUMENTS` or the conversation is mainly Chinese, follow **中文命令流程** and read `${CLAUDE_PLUGIN_ROOT}/SKILL.zh.md`.
- Otherwise follow **English Command Flow** and read `${CLAUDE_PLUGIN_ROOT}/SKILL.md`.
- Parameter names stay English: `pdf`, `job-id`, `max-refs`, `strict`, `no-wait`, `output`.
- JSON keys, status labels (`REAL` / `LIKELY_REAL` / `NEEDS_REVIEW` / `LIKELY_FAKE` / `FAKE`), and reason codes stay English.
- 如果 `$ARGUMENTS` 或对话主要是中文，使用 **中文命令流程**。
- 否则使用 **English Command Flow**。

## English Command Flow

### 1. Pre-flight

Run the checks below in order. **Any failed check stops the flow — do not run the script.**

1. Check `AMINER_API_KEY` is set:

   ```bash
   [ -z "${AMINER_API_KEY+x}" ] && echo "AMINER_API_KEY missing" || echo "AMINER_API_KEY exists"
   ```

   If missing, tell the user to get a token from https://open.aminer.cn and `export AMINER_API_KEY=<token>`. Never echo the token value.

2. Check Python dependency:

   ```bash
   python3 - <<'PY'
   import importlib.util
   missing = [name for name in ("requests",) if importlib.util.find_spec(name) is None]
   print("Missing: " + ", ".join(missing) if missing else "Python dependencies exist")
   PY
   ```

   If missing, instruct: `pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`.

3. Confirm the user supplied a local `.pdf` file path, or alternatively a `job-id` to fetch results for a previously submitted job. If neither, ask for one. **Never fabricate or download a PDF.**

### 2. Parse `$ARGUMENTS`

Accept structured fields and natural language together:

| Field | Values | Default | Meaning |
| --- | --- | --- | --- |
| `pdf` | absolute PDF path | required unless `job-id` is given | Local file to verify |
| `job-id` | `verify_YYYYMMDDTHHMMSSZ_<8hex>` | – | Fetch result for an existing job instead of uploading |
| `max-refs` | 1-100 | 50 | Max references to verify (upload only) |
| `strict` | yes / no | no | Stricter FAKE judgement (upload only) |
| `no-wait` | yes / no | no | With `pdf`: submit and return `job_id` without polling. With `job-id`: single fetch, no polling loop. |
| `timeout` | seconds | 600 | Overall polling timeout |
| `output` | path | – | Optional JSON output path |

If both `pdf` and `job-id` are missing, or the PDF path does not exist, stop and ask the user.

### 3. Run

Build the command from parsed args. For a fresh upload:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verify_pdf.py" \
  --pdf "<pdf-path>"
```

For fetching an existing job:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verify_pdf.py" \
  --job-id "<verify_...>"
```

Add flags only for values the user explicitly provided:

- `--max-refs N` when `max-refs` is set
- `--strict` when `strict: yes`
- `--no-wait` when `no-wait: yes`
- `--timeout N` when `timeout` is set
- `--output <path>` when `output` is set

### 4. Present the Result

Stdout is JSON (the unwrapped record from `data[0]`). Show the user:

- `job_id`
- `total`, `has_hallucination`, `hallucination_ratio`
- A short table built from `counts_by_status` (or top-level `REAL` / `LIKELY_REAL` / `NEEDS_REVIEW` / `LIKELY_FAKE` / `FAKE` counts)
- `urls.report` / `urls.result` if present, noting they may expire after `url_expire_seconds`
- The path written when `--output` was used

If the gateway returned a non-200 `code` or the script exited with an error, surface the error verbatim. Do not invent verdicts.

## 中文命令流程

### 1. Pre-flight

依次执行下列检查，**任何一项失败立即停止，不要运行脚本。**

1. 检查 `AMINER_API_KEY` 是否已设置：

   ```bash
   [ -z "${AMINER_API_KEY+x}" ] && echo "AMINER_API_KEY missing" || echo "AMINER_API_KEY exists"
   ```

   缺失则提示用户到 https://open.aminer.cn 申请 token，然后 `export AMINER_API_KEY=<token>`。**禁止回显 token 值。**

2. 检查 Python 依赖：

   ```bash
   python3 - <<'PY'
   import importlib.util
   missing = [name for name in ("requests",) if importlib.util.find_spec(name) is None]
   print("Missing: " + ", ".join(missing) if missing else "Python dependencies exist")
   PY
   ```

   缺失则提示：`pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`。

3. 确认用户给了存在的本地 `.pdf` 路径，或者给了一个 `job-id` 用于查询已提交作业。两者都没有就主动追问，**不要自行编造或下载 PDF。**

### 2. 解析 `$ARGUMENTS`

同时支持结构化字段和自然语言：

| 字段 | 取值 | 默认 | 含义 |
| --- | --- | --- | --- |
| `pdf` | PDF 绝对路径 | 没给 `job-id` 时必填 | 要核验的本地文件 |
| `job-id` | `verify_YYYYMMDDTHHMMSSZ_<8hex>` | – | 不重新上传，只查已提交作业 |
| `max-refs` | 1-100 | 50 | 最多核验多少条参考文献（仅上传时有效） |
| `strict` | yes / no | no | 是否启用更严格的 FAKE 判定（仅上传时有效） |
| `no-wait` | yes / no | no | 与 `pdf` 连用：仅提交不轮询；与 `job-id` 连用：单次查询不循环。 |
| `timeout` | 秒 | 600 | 轮询总超时 |
| `output` | 路径 | – | 可选的 JSON 落地路径 |

如果 `pdf` 和 `job-id` 都缺失，或者 PDF 路径不存在，停下并向用户追问。

### 3. 运行

按用户实际给的参数拼命令。新上传：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verify_pdf.py" \
  --pdf "<pdf-path>"
```

只查已有作业：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/verify_pdf.py" \
  --job-id "<verify_...>"
```

仅当用户显式提供时才加这些 flag：

- 给了 `max-refs` → `--max-refs N`
- `strict: yes` → `--strict`
- `no-wait: yes` → `--no-wait`
- 给了 `timeout` → `--timeout N`
- 给了 `output` → `--output <path>`

### 4. 展示结果

脚本的 stdout 是 JSON（已拆掉网关信封，即 `data[0]` 这个记录）。向用户展示：

- `job_id`
- `total`、`has_hallucination`、`hallucination_ratio`
- 基于 `counts_by_status`（或顶层 `REAL` / `LIKELY_REAL` / `NEEDS_REVIEW` / `LIKELY_FAKE` / `FAKE` 计数）的状态小表
- 响应里的 `urls.report` / `urls.result`，需要附注会在 `url_expire_seconds` 后过期
- 如果用了 `--output`，告诉用户落盘路径

如果网关 `code` 非 200，或者脚本以错误退出，**原样汇报错误**，禁止伪造核验结论。
