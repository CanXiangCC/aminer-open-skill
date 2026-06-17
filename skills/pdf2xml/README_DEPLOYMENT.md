# PDF to XML Skill 运行与验证指南

## 一、交付清单

`pdf2xml` skill 集成在仓库的 `skills/pdf2xml/` 下：

```text
skills/pdf2xml/
├── SKILL.md
├── SKILL.zh.md
├── commands/
│   └── pdf2xml.md
├── scripts/
│   └── pdf_to_xml.py
├── README_DEPLOYMENT.md
└── requirements.txt
```

核心脚本 `scripts/pdf_to_xml.py` 会调用 GROBID 兼容 API：

```text
POST {GROBID_BASE_URL}/api/processFulltextDocument
```

默认 API 基址为：

```text
http://36.103.177.237:8088
```

如果要切换到自建服务，设置 `GROBID_BASE_URL` 或在单次命令中传 `--base-url`。

## 二、安装依赖

```bash
cd /path/to/aminer-open-skill
pip install -r skills/pdf2xml/requirements.txt
```

依赖检查：

```bash
python3 - <<'PY'
import importlib.util
missing = [name for name in ("requests",) if importlib.util.find_spec(name) is None]
print("Missing: " + ", ".join(missing) if missing else "Python dependencies exist")
PY
```

## 三、验证 API 可达

默认验证 AMiner/GROBID API：

```bash
python3 skills/pdf2xml/scripts/pdf_to_xml.py --check
```

单次命令传入 API 地址：

```bash
python3 skills/pdf2xml/scripts/pdf_to_xml.py \
  --base-url "<GROBID_API_BASE_URL>" \
  --check
```

预期 stderr 类似：

```text
GROBID API service is alive
```

不要在日志或用户输出里打印 `GROBID_BASE_URL` 的具体值。

## 四、转换 PDF

基础转换：

```bash
python3 skills/pdf2xml/scripts/pdf_to_xml.py \
  --pdf /abs/path/to/paper.pdf
```

写到指定目录：

```bash
python3 skills/pdf2xml/scripts/pdf_to_xml.py \
  --pdf /abs/path/to/paper.pdf \
  --output-dir outputs/pdf2xml
```

写到指定文件：

```bash
python3 skills/pdf2xml/scripts/pdf_to_xml.py \
  --pdf /abs/path/to/paper.pdf \
  --output /abs/path/to/paper.xml
```

默认会请求以下 TEI 坐标：

- `persName`
- `figure`
- `ref`
- `formula`
- `biblStruct`

如果下游只需要更小 XML，可以关闭坐标请求：

```bash
python3 skills/pdf2xml/scripts/pdf_to_xml.py \
  --pdf /abs/path/to/paper.pdf \
  --no-coordinates
```

## 五、参数说明

| Flag | 默认 | 说明 |
| --- | --- | --- |
| `--pdf` | 必填，除非 `--check` | 输入 PDF 路径 |
| `--output` | 无 | 输出 XML 路径，覆盖 `--output-dir` |
| `--output-dir` | 无 | 输出目录，文件名自动由 PDF 推导 |
| `--base-url` | `$GROBID_BASE_URL` 或 `http://36.103.177.237:8088` | GROBID 兼容 API 基址 |
| `--request-timeout` | 300 | 请求超时，单位秒 |
| `--consolidate-header` | 无 | GROBID `consolidateHeader`，可取 `0`、`1`、`2` |
| `--consolidate-citations` | 无 | GROBID `consolidateCitations`，可取 `0`、`1`、`2` |
| `--no-coordinates` | 关闭 | 不请求 TEI 坐标 |
| `--check` | 关闭 | 只探测 API 存活性 |

## 六、Claude Code / Codex / OpenClaw 使用

Slash command：

```text
/pdf2xml pdf: /abs/path/to/paper.pdf
```

自然语言：

```text
把 /abs/path/to/paper.pdf 转成 XML
```

执行流程：

- 检查 `GROBID_BASE_URL` 是否存在，但不打印具体值。
- 检查 Python 依赖。
- 调用 `--check` 验证 API 可达。
- 上传 PDF 并写出 `.xml`。
- 向用户报告 XML 路径。

## 七、常见错误

### `cannot reach GROBID`

API 服务不可达、网络不通或地址配置错误。稍后重试，或设置 `GROBID_BASE_URL` 指向另一个可用服务。

### `pdf_not_found` / `not_a_pdf`

PDF 路径不存在，或文件后缀不是 `.pdf`。检查路径拼写并尽量使用绝对路径。

### `bad_input_data`

API 无法解析该 PDF。常见原因包括文件损坏、扫描版无文本层，或文件并不是真正的 PDF。

### `request_timeout after 300s`

PDF 较大或服务处理较慢。可以提高超时：

```bash
python3 skills/pdf2xml/scripts/pdf_to_xml.py \
  --pdf /abs/path/to/large.pdf \
  --request-timeout 600
```

### `http_429` / `http_503`

服务限流、过载或临时不可用。稍后重试，或切换到自建兼容服务。

## 八、可选：自建 GROBID 兼容服务

默认流程不需要用户本地启动 GROBID。如果需要内网部署或隔离环境，可以自建 GROBID 服务，并通过 `GROBID_BASE_URL` 指向它。

常规 Docker 启动示例：

```bash
docker run --rm -p 8070:8070 -d --name grobid grobid/grobid:0.8.2-full
```

自建服务只需要暴露 GROBID 兼容的 HTTP API；skill 侧通过 `GROBID_BASE_URL` 或 `--base-url` 指向该服务。

## 九、输出格式

成功时：

- stdout：单独输出 XML 路径，方便脚本管道处理。
- stderr：输出 `OK: wrote <path>`。

失败时：

- stderr：输出 `ERROR: <code>`。
- 不生成伪造 XML。

生成结果是 TEI XML，通常包含：

- `<teiHeader>`：标题、作者、机构、摘要等元数据。
- `<text><body>`：正文结构。
- bibliography/reference 结构：参考文献和引用信息。
