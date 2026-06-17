---
description: Convert a paper PDF to TEI XML using a GROBID-compatible API service
argument-hint: [pdf: <pdf-path> output: <xml-path> output-dir: <dir> base-url: <url> no-coordinates: true consolidate-header: 0|1|2 consolidate-citations: 0|1|2]
allowed-tools: Read, Bash, Glob, Grep
---

# /pdf2xml - PDF to XML

User invoked the PDF to XML skill with the following arguments:

```text
$ARGUMENTS
```

## Language Routing / 语言路由

- If `$ARGUMENTS` or the conversation is mainly Chinese, follow **中文命令流程** and read `${CLAUDE_PLUGIN_ROOT}/SKILL.zh.md`.
- Otherwise follow **English Command Flow** and read `${CLAUDE_PLUGIN_ROOT}/SKILL.md`.
- Parameter names remain English: `pdf`, `output`, `output-dir`, `base-url`, `no-coordinates`, `consolidate-header`, `consolidate-citations`.

## English Command Flow

### 1. Pre-flight

Run the checks below in order. A failed required check stops the flow. Do not run conversion until the checks pass.

1. Check the optional API endpoint override without printing its value:

   ```bash
   [ -z "${GROBID_BASE_URL+x}" ] && echo "GROBID_BASE_URL missing; using default AMiner/GROBID API" || echo "GROBID_BASE_URL exists"
   ```

2. Check Python dependency:

   ```bash
   python3 - <<'PY'
   import importlib.util
   missing = [name for name in ("requests",) if importlib.util.find_spec(name) is None]
   print("Missing: " + ", ".join(missing) if missing else "Python dependencies exist")
   PY
   ```

   If missing, instruct: `pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`.

3. Check the API service is alive:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" --check
   ```

   If the user supplied `base-url`, run the check with:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
     --base-url "<GROBID_API_BASE_URL>" \
     --check
   ```

   If unreachable, tell the user the API service is unavailable and they can retry later or set `GROBID_BASE_URL` to another running GROBID-compatible endpoint. Stop here.

4. Confirm the user supplied an existing local `.pdf` path. If not, ask. Never invent or download a PDF.

### 2. Parse `$ARGUMENTS`

| Field | Values | Default | Meaning |
| --- | --- | --- | --- |
| `pdf` | local PDF path | required | Local file to convert |
| `output` | path | none | Explicit output `.xml` path |
| `output-dir` | path | none | Directory for the `.xml` output |
| `base-url` | URL | `$GROBID_BASE_URL` or built-in AMiner/GROBID API | API base URL |
| `no-coordinates` | `true` / `false` | `false` | Disable TEI coordinate request |
| `consolidate-header` | `0` / `1` / `2` | none | GROBID `consolidateHeader` |
| `consolidate-citations` | `0` / `1` / `2` | none | GROBID `consolidateCitations` |

If `pdf` is missing or the path does not exist, stop and ask the user for a local PDF path.

### 3. Run

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --pdf "<pdf-path>"
```

Add flags only for values the user explicitly provided:

- `--output <path>` when `output` is set.
- `--output-dir <dir>` when `output-dir` is set.
- `--base-url <url>` when `base-url` is set.
- `--no-coordinates` when `no-coordinates` is `true`.
- `--consolidate-header N` and `--consolidate-citations N` when set.

### 4. Present the Result

On success, stdout is the written `.xml` path and stderr carries `OK: wrote <path>`. Tell the user the output path and that it is TEI XML from a GROBID-compatible API service.

On failure, the script exits non-zero with `ERROR: <code>` on stderr. Surface the code verbatim (`pdf_not_found`, `not_a_pdf`, `empty_response`, `bad_input_data`, `http_<code>`, `request_timeout`, `request_failed`) and the likely cause. Never fabricate XML.

## 中文命令流程

### 1. Pre-flight

依次执行下列检查。必需检查失败时立即停止，不要运行转换。

1. 检查可选 API 地址覆盖，但不要打印具体值：

   ```bash
   [ -z "${GROBID_BASE_URL+x}" ] && echo "GROBID_BASE_URL missing; using default AMiner/GROBID API" || echo "GROBID_BASE_URL exists"
   ```

2. 检查 Python 依赖：

   ```bash
   python3 - <<'PY'
   import importlib.util
   missing = [name for name in ("requests",) if importlib.util.find_spec(name) is None]
   print("Missing: " + ", ".join(missing) if missing else "Python dependencies exist")
   PY
   ```

   缺失则提示：`pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`。

3. 检查 API 服务是否存活：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" --check
   ```

   如果用户传了 `base-url`，检查命令应改为：

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
     --base-url "<GROBID_API_BASE_URL>" \
     --check
   ```

   不可达则告诉用户 API 服务当前不可用，可以稍后重试，或设置 `GROBID_BASE_URL` 指向另一个正在运行的 GROBID 兼容端点。然后停止。

4. 确认用户提供了存在的本地 `.pdf` 路径。没有就主动追问。不要自行编造或下载 PDF。

### 2. 解析 `$ARGUMENTS`

| 字段 | 取值 | 默认 | 含义 |
| --- | --- | --- | --- |
| `pdf` | 本地 PDF 路径 | 必填 | 要转换的本地文件 |
| `output` | 路径 | 无 | 指定输出 `.xml` 路径 |
| `output-dir` | 路径 | 无 | 输出 `.xml` 的目录 |
| `base-url` | URL | `$GROBID_BASE_URL` 或内置 AMiner/GROBID API | API 基础地址 |
| `no-coordinates` | `true` / `false` | `false` | 关闭 TEI 坐标请求 |
| `consolidate-header` | `0` / `1` / `2` | 无 | GROBID `consolidateHeader` |
| `consolidate-citations` | `0` / `1` / `2` | 无 | GROBID `consolidateCitations` |

如果 `pdf` 缺失或路径不存在，停下并向用户索要本地 PDF 路径。

### 3. 运行

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --pdf "<pdf-path>"
```

仅当用户显式提供时才加这些 flag：

- 给了 `output` -> `--output <path>`。
- 给了 `output-dir` -> `--output-dir <dir>`。
- 给了 `base-url` -> `--base-url <url>`。
- `no-coordinates` 为 `true` -> `--no-coordinates`。
- 给了 `consolidate-header` / `consolidate-citations` -> 对应 flag。

### 4. 展示结果

成功时 stdout 是写出的 `.xml` 路径，stderr 是 `OK: wrote <path>`。告诉用户输出路径，以及这是 GROBID 兼容 API 产出的 TEI XML。

失败时脚本以非零码退出，stderr 为 `ERROR: <code>`。原样汇报错误码（`pdf_not_found`、`not_a_pdf`、`empty_response`、`bad_input_data`、`http_<code>`、`request_timeout`、`request_failed`）和可能原因。禁止伪造 XML。
