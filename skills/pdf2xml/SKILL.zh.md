---
name: aminer-pdf2xml
version: 1.0.0
author: AMiner
contact: report@aminer.cn
description: >
  [触发] 当用户提供本地论文 PDF 路径，并要求转换、解析或提取为 XML / TEI 时使用，例如“把这个 PDF 转成 XML”“将论文解析成 TEI”“对这个 PDF 跑 GROBID”。
  [能力] 将 PDF 上传到 GROBID 兼容的 AMiner API 服务，请求全文 TEI XML 和常用坐标标注，校验响应后写入本地文件。
  [路由] 不要用于参考文献幻觉核验、引用事实核查、论文检索、学者查询或综述文献收集；这些任务应分别使用 pdf-citation-verifier、aminer-academic-search、aminer-free-academic 或 aminer-deep-search。本技能只做 PDF 到 TEI XML 的结构化转换。
metadata:
  {
    "openclaw":
      {
        "emoji": "📄",
        "requires": {
          "bins": ["python3"],
          "env": []
        }
      }
  }
---

# PDF 转 XML

通过 GROBID 兼容 API 服务把论文 PDF 转换为 TEI XML。可用自然语言或 `/pdf2xml` 触发。

## 这个技能做什么

GROBID 会解析学术 PDF，并返回 TEI XML，包含元数据、摘要、正文章节、图表、公式、引用和参考文献。本技能是一个轻量 API 客户端：

- 将 PDF POST 到 `{GROBID_BASE_URL}/api/processFulltextDocument`。
- 默认请求 `persName`、`figure`、`ref`、`formula`、`biblStruct` 的 TEI 坐标。
- 校验响应非空，且不包含 bad input 标记。
- 把返回的 TEI XML 写到 PDF 旁边，或写到用户指定路径。

脚本默认使用与旧版 `parse_pdf_origin.py` 一致的 AMiner/GROBID API 服务 `http://36.103.177.237:8088`。如需切换到其他兼容服务，设置 `GROBID_BASE_URL` 或传 `--base-url`。不要在面向用户的输出中打印环境变量的值。

## 文件清单

- `SKILL.md` / `SKILL.zh.md` - 英文 / 中文技能定义。
- `commands/pdf2xml.md` - slash command 入口。
- `scripts/pdf_to_xml.py` - API 客户端：检查服务、上传 PDF、写 TEI XML。
- `requirements.txt` - Python 依赖。
- `README_DEPLOYMENT.md` - 运行说明和手工验证步骤。

## Pre-flight

转换前依次执行下列检查。必需检查失败时立即停止，并把错误报告给用户。

**1. 可选 API 地址覆盖**

```bash
[ -z "${GROBID_BASE_URL+x}" ] && echo "GROBID_BASE_URL missing; using default AMiner/GROBID API" || echo "GROBID_BASE_URL exists"
```

`GROBID_BASE_URL` 是可选项。不要打印它的具体值。

**2. Python 依赖**

```bash
python3 - <<'PY'
import importlib.util
missing = [name for name in ("requests",) if importlib.util.find_spec(name) is None]
print("Missing: " + ", ".join(missing) if missing else "Python dependencies exist")
PY
```

缺失时提示：`pip install -r "${CLAUDE_PLUGIN_ROOT}/requirements.txt"`。

**3. API 服务可达性**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" --check
```

如果使用单次传入的 API 地址，而不是 `GROBID_BASE_URL`：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --base-url "<GROBID_API_BASE_URL>" \
  --check
```

如果检查失败，立即停止。告诉用户 API 服务当前不可达，可以稍后重试，或设置 `GROBID_BASE_URL` 指向另一个正在运行的 GROBID 兼容端点。

**4. PDF 输入**

用户必须提供存在的本地 `.pdf` 文件路径。如果用户只描述论文但没有给文件路径，需要追问本地 PDF 路径。不要自行编造或下载 PDF。

## 执行示例

基础转换。在 PDF 旁边写出 `<pdf-stem>.xml`：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --pdf "/abs/path/to/paper.pdf"
```

写到指定路径或目录：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --pdf "/abs/path/to/paper.pdf" \
  --output "/abs/path/to/out/paper.xml"

python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --pdf "/abs/path/to/paper.pdf" \
  --output-dir "outputs/pdf2xml"
```

单次命令指向某个 API 服务：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --base-url "<GROBID_API_BASE_URL>" \
  --pdf "/abs/path/to/paper.pdf"
```

当下游只需要更小 XML 时，关闭坐标标注：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --pdf "/abs/path/to/paper.pdf" \
  --no-coordinates
```

当配置的服务支持外部元数据查询时，可启用 GROBID consolidation：

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_to_xml.py" \
  --pdf "/abs/path/to/paper.pdf" \
  --consolidate-header 1 \
  --consolidate-citations 1
```

## 参数

| Flag | 默认 | 说明 |
| --- | --- | --- |
| `--pdf` | 必填，除非使用 `--check` | 本地 `.pdf` 文件路径。 |
| `--output` | 无 | 指定输出 `.xml` 路径，覆盖 `--output-dir`。 |
| `--output-dir` | 无 | 输出 `.xml` 的目录，文件名由 PDF 推导。 |
| `--base-url` | `$GROBID_BASE_URL` 或 `http://36.103.177.237:8088` | GROBID 兼容 API 基础地址。 |
| `--request-timeout` | 300 | 单请求超时，单位秒。 |
| `--consolidate-header` | 无 | GROBID `consolidateHeader`，可取 `0`、`1`、`2`。 |
| `--consolidate-citations` | 无 | GROBID `consolidateCitations`，可取 `0`、`1`、`2`。 |
| `--no-coordinates` | 关闭 | 不请求 TEI 坐标。 |
| `--check` | 关闭 | 探测 `/api/isalive` 后退出。 |

## 环境变量

| 变量 | 必需 | 用途 |
| --- | --- | --- |
| `GROBID_BASE_URL` | 否 | 覆盖默认 AMiner/GROBID API 基础地址。 |

## 运行约束

- 转换前必须先检查 Python 依赖和 API 可达性。
- 默认流程不要求用户启动本地 Docker；默认路径是 API 调用。
- 成功时 stdout 只输出 XML 路径；人类可读状态走 stderr。技能应把写出的路径报告给用户。
- 绝不伪造 XML 输出。脚本非零退出时，原样汇报分类错误码：`pdf_not_found`、`not_a_pdf`、`empty_response`、`bad_input_data`、`http_<code>`、`request_timeout` 或 `request_failed`。
- `bad_input_data` 表示 API 服务无法解析 PDF，常见原因是文件损坏、扫描版无文本层，或不是真正的 PDF。
- 大 PDF 可能较慢。遇到合理的长耗时转换时，提高 `--request-timeout`，不要直接当成卡死。

## 输出展示

脚本返回后，告诉用户：

- 写出的 `.xml` 路径。
- 格式是 GROBID 兼容 API 产出的 TEI XML。
- 失败时，stderr 中的确切错误码和最可能原因。
