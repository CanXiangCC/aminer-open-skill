# aminer-exp-extraction

自包含的生产级 LLM 论文抽取管线 **OpenClaw skill**。本目录是
[aminer-exp-skill](../../README.zh.md) 技能集中的一个 skill：根部
`SKILL.md`（OpenClaw 标准格式），目录内打包了完整的 **vendored 运行时**
（管线代码、脚本、配置、规则/ML 包、测试）——单独克隆或安装即可完整使用，
运行期不依赖上游项目。

服务端点与模型名**不内置**：通过 config 或环境变量带入你自己的 BERT/LLM
服务。

## 安装（OpenClaw）

一条命令——安装本 skill 目录（即本 README 所在、根部有 SKILL.md 的目录）：

```bash
# 克隆 aminer-exp-skill 仓库后：
openclaw skills install ./skills/aminer-exp-extraction
```

安装会拷贝整个目录（含运行时），skill 在 workspace 里自包含。此后 run 产物
落在安装副本内的 `pipeline_output/production/` 下——适合轻量操作；长期重度
生产 run 建议单独 `git clone` 仓库使用。

## Quick Start（快速上手，从克隆开始）

准备只有两步：装 uv + 填端点——不需要创建或维护任何 venv；所有命令经
`uv run` 自动解析 Python 3.12 与依赖（首次使用后走缓存）。

```bash
git clone <aminer-exp-skill 仓库> && cd aminer-exp-skill/skills/aminer-exp-extraction
# 未装 uv 先装（用户级，无需 sudo）：curl -LsSf https://astral.sh/uv/install.sh | sh

# 配置服务端点——二选一：编辑 configs/default.yaml：
#   bert_server_url / llm_api_url / llm_model
# 或导出环境变量（优先于 yaml）：
#   BERT_SERVER_URL / LLM_CHAT_URL / LLM_MODEL

uv run --with-requirements requirements.txt --python 3.12 python scripts/pipeline_cli.py check-services   # 探活两个服务
# 从 CSV 准备 manifest：
uv run --with-requirements requirements.txt --python 3.12 python scripts/pipeline_cli.py ingest --csv <论文列表.csv> \
    --manifest-dir manifests/myset --run-id my-run-1
# 起抽取 run（将调用你的 BERT/LLM 服务）：
uv run --with-requirements requirements.txt --python 3.12 python scripts/run_bulk.py --manifest-dir manifests/myset \
    --run-id my-run-1 --config configs/default.yaml
```

可选自检：`uv run --with-requirements requirements.txt --with-requirements requirements-dev.txt --python 3.12 -m pytest tests/ -q` → 开箱即 **336 passed +
1 skipped**（`tests/test_LLM.py` 的真实服务用例在 `LLM_CHAT_URL` /
`BERT_SERVER_URL` 未设置时自动跳过；设置后且服务可达时基线为 341 passed）。

## 操作一览（完整规程见 SKILL.md）

| 用户意图 | SKILL.md 章节 | 脚本 |
|---|---|---|
| 起跑 / 重启批量 run（快照或 watch 模式） | §1 run-extraction | `scripts/run_bulk.py` |
| 从 CSV 向 manifest 目录增补论文 | §2 ingest-csv | `scripts/pipeline_cli.py ingest` |
| 只读运行监控（进度、错误、退出码） | §3 monitor-run | 日志面读取 |
| 重跑错误篇、提升 durable 率 | §4 backfill-errors | `scripts/backfill_errors.py` |
| 回收已完结 run 的磁盘空间 | §5 compact-run | `scripts/compact_run.py` |
| 核对仓库是否全绿 | §6 run-tests | pytest |

路由速查：起跑/重启 run → §1；给 run 补论文 → §2；"run 跑得怎么样了？" →
§3（只读，永远安全）；错误篇需要重跑 → §4（绝不进官方 export）；run 已完结、
要回收磁盘 → §5（破坏性；必须先 dry-run）；核对全绿 → §6。

## 目录结构

```
├── SKILL.md / SKILL.zh.md      # skill 定义（英/中）——OpenClaw 入口
├── pipeline/                   # vendored 运行时：production/benchmark/evaluation 包
├── preprocess/                 # vendored 运行时：预处理阶段
├── scripts/                    # 14 个入口/工具脚本（run_bulk、pipeline_cli、backfill…）
├── configs/default.yaml        # 管线配置（端点待填）
├── rule_ml_extraction_from_promote/   # 冻结的规则/ML 抽取包（含模型）
├── reference_detector.py       # preprocess 使用的参考文献剥离器
├── dataset_evidence/           # 证据打分（测试依赖）
├── tests/                      # 341 用例测试套件（自举；除 test_LLM.py 外离线可跑）
├── pipeline_output/            # 运行时输出（gitignored；跟踪一个 fixture run）
├── manifests/                  # 你的 job_batch manifest（gitignored；用 ingest 生成）
├── requirements.txt / requirements-dev.txt
├── VENDOR_MANIFEST.json        # vendoring 溯源 + 脱敏记录
└── CONTRIBUTING.zh.md          # 本仓库的 skill 标准
```

## vendored 运行时

运行时复制自上游 `exp-extraction-project`（commit 记录在
`VENDOR_MANIFEST.json`）并做了发布脱敏：全部内网端点与模型路径已移除——取值只能
来自 `configs/default.yaml` 或 `BERT_SERVER_URL` / `LLM_CHAT_URL` /
`LLM_MODEL` 环境变量。prediction 语义与上游 0.7.1 起保持不变（workflow 版本
0.8.0）。完整的 vendoring 与脱敏记录见 `PLAN.md`。

## 安全护栏（对所有操作生效）

- **语义参数冻结**：绝不引导修改 LLM prompt/model/temperature、`bert_threshold`、schema/normalize/merge/commit 配置。
- 补数/实验 run **绝不进入官方 export/merge**。
- 破坏性操作（`--apply`、`--run`、compaction、删文件）必须先 dry-run 或明确列出影响面。
- 绝不打印密钥值；绝不硬编码内网端点与模型名。
- 调用真实 BERT/LLM 服务的步骤一律显式标注"将调用服务，确认后执行"。

## 贡献

skill 标准见 `CONTRIBUTING.zh.md`（SKILL.md 规范、Python 规范、PR 自查清单）。
