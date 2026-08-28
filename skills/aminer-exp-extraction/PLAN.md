# PLAN.md — aminer-open-skill 子项目规划与自验记录

> 本文档是 aminer-open-skill 子项目的完整规划（Phase 1），末尾"自验记录"章节在 Phase 2 搭建完成后追加。
> 标准依据：仓库根 `CONTRIBUTING.zh.md`（冲突时以它为准）。所有产物仅位于 `aminer-open-skill/` 内，仓库其余部分零改动。

---

## 1. 背景与目标

本仓库（exp-extraction-project）是生产级 LLM 论文抽取管线，CLI 操作面已经过实证（含由 CLI 智能体自治执行补数规程的端到端验收，见 `docs/BACKFILL_TOOLING_ACCEPTANCE_20260821.md`）。

目标：把操作能力重构为符合 aminer-open-skill 标准的 skill 包，供 openclaw 等客户端通过 `openclaw skills install` 安装使用。skill 全部是对仓库现有 `scripts/*.py` 的**操作规程包装**，不新增任何管线代码。

**不新增 Python 脚本的理由**：六个 skill 的功能（起 run / 增补 CSV / 监控 / 补数 / 压缩 / 测试）均由仓库既有脚本承载；监控派生统计用 `.venv/bin/python` 内联命令即可。因此无需 requirements.txt、无需 `_utils.py`，CONTRIBUTING §四（Python 代码规范）以"零新增 Python"方式满足。

## 2. skill 清单与取舍理由

按运行频率与已实证程度排序，共 6 个：

| # | skill | 职责 | 取舍理由 |
|---|-------|------|----------|
| 1 | aminer-run-extraction | 起生产 run（含 watch 动态增补模式、停止语义、退出码判读） | 最高频操作面；停止语义（SIGINT/SIGTERM/SIGKILL/同 run-id 重启）是运维关键知识 |
| 2 | aminer-ingest-csv | 动态增补 CSV（五类分类、幂等性、原子发布） | watch 模式的配套入口；与 run-extraction 构成动态增补闭环 |
| 3 | aminer-monitor-run | 运行监控与质量门核对（六层日志面派生） | 只读、零风险，是其他所有 skill 的"眼睛"；已实证的 CLI-leg 验收即以此为基础 |
| 4 | aminer-backfill-errors | 错误补数全规程（dry-run→apply→run→并集 durable 验证→汇报） | 从 `.agents/skills/backfill-errors/SKILL.md` 迁移并参数化；唯一已有成熟规程的候选 |
| 5 | aminer-compact-run | 手动 compaction（dry-run 先行、exit 2 语义、freed 统计） | 磁盘回收刚需；与 backfill 同为"改 run 状态"操作，路由边界必须写清 |
| 6 | aminer-run-tests | 全量/定向 pytest 与结果判读 | 341 基线核对是"零影响"验收的标准动作 |

**明确不设的 skill 及理由**：
- **官方 merge/export（merge_flat_experiments.py）**：ops 政策规定补数/实验 run 绝不进入官方 export/merge；官方交付是谨慎的手动步骤，做成 skill 会降低误用门槛、放大风险。相关边界写进各 skill 的路由规则与运行约束。
- **kill/restart 注入类工具**（如 phase3_kill_restart.py）：属验收测试驱动，非日常操作面。

**backfill 与 compact 的路由边界**（两者都改 run 状态，须互写边界）：
- 要提高 durable 率、修复错误篇 → aminer-backfill-errors；
- run 已完结、要回收磁盘空间 → aminer-compact-run；
- run 仍在进行中 → 两者都不该动手，先 aminer-monitor-run；
- 同一 run 上先补数后压缩（compaction 会改变 run 目录形态，`ledger_ok` 只出现在已压缩 run 中，顺序影响补数核对口径）。

## 3. 目录树

```
aminer-open-skill/
├── PLAN.md                                  # 本文档
├── README.md                                # 包介绍（英）
├── README.zh.md                             # 包介绍（中，与英文同步）
├── .claude-plugin/
│   └── marketplace.json                     # 6 个 skill 的 plugins 注册
└── skills/
    ├── run-extraction/
    │   ├── SKILL.md                         # 英文 skill 定义
    │   ├── SKILL.zh.md                      # 中文版（同步）
    │   ├── commands/run-extraction.md       # /run-extraction 四段式
    │   └── .claude-plugin/plugin.json       # 最小插件清单（见 §5）
    ├── ingest-csv/          （同构四件套）
    ├── monitor-run/
    ├── backfill-errors/
    ├── compact-run/
    └── run-tests/
```

## 4. 每个 skill 的输入 / 输出 / 行为边界

frontmatter 统一约定：`name: aminer-<skill-name>`、`version: 1.0.0`、`author: AMiner`、`contact: report@aminer.cn`、description 三段结构（[激活条件]→[适用场景]→[路由规则]）。`metadata.openclaw.requires`：`bins: ["python3"]`、`env: []`；**不设 primaryEnv**——理由：端点与模型名全部从 `configs/default.yaml` 读取（可选环境变量 BERT_SERVER_URL / LLM_CHAT_URL / LLM_MODEL 仅是覆盖项），没有"真正必须"的环境变量，按 CONTRIBUTING"只填真正必须的"原则留空。

### 4.1 aminer-run-extraction
- **输入**：manifest 目录、session run id、config 路径（默认 `configs/default.yaml`）、可选 watch 模式参数。
- **输出**：`pipeline_output/production/runs/<run-id>/` 下的 run 产物 + `pipeline_output/production/logs/bulk-<ts>/` 下的日志；终端退出码。
- **命令**：`.venv/bin/python scripts/run_bulk.py --manifest-dir <目录> --run-id <id> --config configs/default.yaml`；watch 增补：追加 `--watch-manifest --poll-interval 5 --watch-idle-timeout 600`。
- **行为边界**：起 run 前建议 `scripts/pipeline_cli.py check-services` 探活；真实抽取将调用内网 BERT/LLM 服务（文档中显式标注）；停止语义（SIGINT/SIGTERM 优雅停→exit 130，跳过 md 清理与 compaction；SIGKILL 安全；同 run-id 重启跳过 ok 篇重试 error 篇）；退出码 0/2/3/130；`--job-batches` 与 `--start-from` 互斥、`--watch-manifest` 与 `--job-batches` 互斥。单段式生产（无 resume stage）。

### 4.2 aminer-ingest-csv
- **输入**：CSV 文件、manifest 目录、参与去重的 run id（可重复）、可选 `--include-retry` / `--size 50` / `--source-name`。
- **输出**：目标 manifest 目录下新增的 `job_batch_*.json`（原子发布，编号单调递增）；分类统计报告。
- **命令**：`.venv/bin/python scripts/pipeline_cli.py ingest --csv <文件> --manifest-dir <目录> --run-id <id>`。
- **行为边界**：五类分类 invalid>conflict>duplicate>retry>new；幂等（重复 ingest 按论文 id 与既有 run 的 prediction 去重）；**只写 manifest 不触发抽取**（由 watch 模式的 runner 在批次边界拾取）；影响面 = 目标 manifest 目录新增文件，不触碰其他路径。

### 4.3 aminer-monitor-run
- **输入**：session run id（可选 job_batch id）。
- **输出**：进度、错误分类计数、速率、退出码/质量门判读（只读，零写）。
- **数据源（六层日志面，真实路径）**：
  1. `pipeline_output/production/logs/bulk-<ts>/bulk.log` — append-only、pid 标记、双时区，`PROCESS END ... exit=N` 收尾；
  2. 同目录 `session.pid*.json`（启动配置 dump）与 `job_batch_*.pid*.summary.json`（papers_total/ok/error/skipped、rates、error_classes）；
  3. `runs/<run-id>/<job_batch>/progress.jsonl` — 每篇 `ts/status/error/llm_elapsed_sec`；
  4. `runs/<run-id>/ledger.jsonl` — 每篇终态 + `prediction_sha256` + `workflow_version`（仅较新 run 有）；
  5. `runs/<run-id>/<jb>/monitors/<paper_id>_monitor.json`、`staged_pipeline_monitor.json`、`bert_batch_monitor.json`；
  6. `runs/<run-id>/<jb>/predictions/<paper_id>.json` 的 error 字段（backfill 分类的数据源）。
- **行为边界**：只读；退出码判读表（0/2=error_rate>15%/3=parse_error_rate>10% 或 zero_datasets_rate>25%/130）；注明已知诊断边界——LLM 原始响应默认不落盘（parse_error 只留解析器诊断串），不要承诺能拿到原始响应。

### 4.4 aminer-backfill-errors
- **输入**：session run id（可重复）、可选 `--include-md-fetch`（默认排除死链）。
- **输出**：dry-run 报告（零写）→ `manifests/backfill/<run-id>-<YYYYMMDD-HHMMSS>/job_batch_backfill_000.json`（gitignored）→ 独立补数 run `<orig>-bf<YYYYMMDD>` → 补数报告。
- **命令链**：`scripts/backfill_errors.py --run-id <id>`（dry-run 默认）→ 核对清单全过后 `--apply` → `--run`（以独立 session id 子进程补跑，真实调用内网服务）→ 并集 durable 验证 → 汇报模板。
- **行为边界（从既有规程逐字保留的护栏）**：补数 run id 是独立 session，绝不进入官方 export/merge；默认 dry-run，`--apply/--run` 前必须完成核对清单；md_fetch 死链默认不补；不改任何语义参数；产物只在 gitignored 目录；补数 run 收尾时删除 `pipeline_output/production/exports/` 下按 run id 命名的自动 merge 产物以保持 exports/ 纯净（删除前列明影响面）。

### 4.5 aminer-compact-run
- **输入**：session run id（可重复）、可选 `--runs-dir`（对副本离线操作）。
- **输出**：dry-run 报告（零写）→ 压缩后的 run 目录 + freed 统计；退出码 0（完成或无事可做）/ 2（校验失败，原件保留）。
- **命令**：`.venv/bin/python scripts/compact_run.py --session-run-id <id> --dry-run` 先行，人工确认后再去掉 `--dry-run`。
- **行为边界**：破坏性操作，必须 dry-run 先行；只对已完结 run 操作；与 backfill 的顺序关系见 §2 路由边界。

### 4.6 aminer-run-tests
- **输入**：可选 pytest `-k` 表达式或测试文件路径。
- **输出**：测试结果与判读（只读）。
- **命令**：`.venv/bin/python -m pytest tests/ -q`（全量基线）；定向如 `-k backfill`。
- **行为边界**：绝不修改测试文件来"让测试通过"；失败时如实报告并指向对应模块维护者；不触碰任何服务。

## 5. .claude-plugin/marketplace.json 设计

- CONTRIBUTING 只要求"在 plugins 数组中补充新条目"，未给出 schema。本设计采用 Claude Code plugin marketplace 惯例格式（openclaw 对 Claude 兼容包可自动识别）：顶层 `name` / `owner` / `plugins[]`，每个条目 `name` / `source`（仓库内相对路径 `./skills/<skill-name>`）/ `description` / `version` / `author`。
- 每个 skill 目录附**最小 `.claude-plugin/plugin.json`**（name/version/description/author），使 plugins 条目指向的目录成为合法的 Claude 兼容插件包。此文件是 CONTRIBUTING 目录结构之外的**兼容性补充**（CONTRIBUTING 允许 skill 目录含"脚本、参考文档等"附加文件），不与任何规范冲突。
- **安装路径双保险**：(a) openclaw 官方文档明确"Git 与本地安装要求源根有 SKILL.md"——每个 `skills/<name>/` 根都有 SKILL.md，可直接 `openclaw skills install ./aminer-open-skill/skills/<name>`；(b) marketplace.json 满足 CONTRIBUTING 注册要求并兼容 Claude Code 市场。
- **已知风险**：marketplace.json 的 schema 未经 openclaw 实机验证（本任务红线禁止真实安装验收），最终以用户 `openclaw skills install` 手动验收为准；若格式被拒，只需调整 marketplace.json 单个文件，skill 本体不受影响。

## 6. 迁移映射（现有规程 → 新 skill）

| 现有资产（只读参考，未改动） | 去向 |
|---|---|
| `.agents/skills/backfill-errors/SKILL.md` 全规程（§0–§6） | aminer-backfill-errors：步骤、核对清单、汇报模板、六条护栏逐字迁移，并参数化为 `$ARGUMENTS` 驱动的 slash command |
| `docs/PIPELINE_HANDOFF.md` 的 run/停止/重启操作面 | aminer-run-extraction（停止语义、退出码、watch 模式） |
| `docs/PIPELINE_HANDOFF.md` 的日志/监控面 | aminer-monitor-run（六层日志面路径与字段） |
| ops 政策（单段式生产、补数不进官方 export、exports/ 纯净） | 各 skill 的运行约束 + 路由规则 |
| `docs/BACKFILL_TOOLING_ACCEPTANCE_20260821.md` 的 openclaw 验收经验（如 `--apply` 双执行摩擦、WARN 文案） | aminer-backfill-errors 的命令表述规避已知摩擦点（明确单次执行、逐步确认） |
| 质量门阈值（error_rate 15% / parse_error_rate 10% / zero_datasets_rate 25%）与 341 测试基线 | aminer-monitor-run 与 aminer-run-tests 的判读口径 |

## 7. 地面真相差异清单（任务书 vs 仓库实际，一律以仓库实际为准）

1. **workflow 版本**：任务书称 0.7.1；实际 `pipeline/production/config.py:45` 为 `WF4_WORKFLOW_VERSION = "0.8.0"`（2026-08-21 v0.8 里程碑合入，prediction 语义自 0.7.1 不变）。skill 文本不硬编码版本号，需要时引导从 `ledger.jsonl` 的 `workflow_version` 字段读取。
2. **backfill 输出目录**：任务书写 `manifests/backfill/<run>_<ts>/`；实际代码（backfill_errors.py）为连字符连接 `manifests/backfill/<run-id>-<YYYYMMDD-HHMMSS>/`。按实际写。
3. **session.pid*.json / job_batch summary 位置**：任务书将它们与 progress/ledger 并列在 run 目录；实际位于 `pipeline_output/production/logs/bulk-<ts>/` 下。run 目录内是 progress.jsonl、ledger.jsonl（较新 run）、job_batch 子目录。监控 skill 按真实路径写。
4. **exports/ 路径**：实际为 `pipeline_output/production/exports/`（非仓库根 exports/）。
5. **ledger.jsonl 覆盖范围**：仅较新 run（rolling/ledger 合入后）存在，旧 run 无；监控 skill 注明此差异。
6. **测试基线**：文档口径 341 passed；Phase 2 自验以实际执行结果记录。

## 8. 自验步骤（Phase 2 末尾逐条执行并记录于 §9）

1. `git status --short` — 除 `aminer-open-skill/` 与工作区既有未跟踪文件（CONTRIBUTING.zh.md、docs/PLAN_AGENT_PROMPT_SKILL_REPO_20260821.md）外，零新增/零修改。
2. `.venv/bin/python -m pytest tests/ -q` — 全绿且数量与基线一致（证明 skill 目录对仓库零影响）。
3. CONTRIBUTING.zh.md §五自查清单逐条核对（文件完整性 / SKILL.md 内容 / 代码质量（无新增 Python）/ 密钥安全），结果列表记录。
4. 每个 skill 的执行示例逐条纸面推演：命令引用的脚本路径存在、旗标与 `--help` 输出一致、dry-run 默认成立、无硬编码端点/模型名/密钥。
5. `python -m json.tool` 校验 marketplace.json 与全部 plugin.json。

## 9. 自验记录（2026-08-22，全部通过）

### 9.1 git status --short
```
?? CONTRIBUTING.zh.md
?? aminer-open-skill/
?? docs/PLAN_AGENT_PROMPT_SKILL_REPO_20260821.md
```
仅 `aminer-open-skill/` 新增 + 工作区既有两条未跟踪文件；跟踪文件零修改。✅

### 9.2 测试基线
```
$ .venv/bin/python -m pytest tests/ -q
341 passed in 12.49s
```
341 passed，与文档口径基线一致——skill 目录对仓库零影响。✅

### 9.3 CONTRIBUTING.zh.md §五自查清单（对 6 个 skill 逐条）

**文件完整性**
- [x] 6 个 SKILL.md 均存在，frontmatter 完整（name=aminer-<name> / version=1.0.0 / description 三段 / metadata.openclaw）
- [x] 6 个 commands/<skill-name>.md 均创建（四段式：Pre-flight / Parse $ARGUMENTS / Run / Present the result）
- [x] .claude-plugin/marketplace.json 已注册全部 6 个 skill（plugins 数组）
- [x] README.md 与 README.zh.md 均已更新（skill 列表 + 目录说明 + 安装方法）

**SKILL.md 内容**
- [x] description 均含激活条件、适用场景、路由规则（中英双版一致）
- [x] 正文均有环境变量检查 bash（BERT_SERVER_URL/LLM_CHAT_URL/LLM_MODEL 存在性检查，绝不打印值）
- [x] 正文均有可直接运行的执行示例（默认参数、仓库根可复制执行）
- [x] 无硬编码 key、base_url 或模型名（grep 复核：无 URL/IP/密钥模式命中，唯一命中为 "Disk-space" 的 `sk-` 误报）

**代码质量**（本包零新增 Python，以"无"满足）
- [x] 无跨文件复制的工具函数（无 Python 文件）
- [x] `__all__` 不适用
- [x] 无只存不读参数（无 Python 文件）
- [x] 无新增依赖（不需要 requirements.txt）

**密钥安全**
- [x] 代码与脚本无密钥明文
- [x] SKILL.md 与 commands/ 无打印 key 值的指令（各文件均有"绝不打印值"约束）

### 9.4 执行示例纸面推演

| 示例 | 推演结果 |
|---|---|
| run_bulk.py：--manifest-dir/--run-id/--config/--watch-manifest/--poll-interval/--watch-idle-timeout/--job-batches/--start-from/--smoke/--force/--no-gate/--no-md-cache-cleanup | 全部与 --help 一致；互斥约束（--job-batches vs --start-from、--watch-manifest vs --job-batches）已写入文档 ✅ |
| pipeline_cli.py ingest：--csv/--manifest-dir/--run-id（可重复）/--include-retry/--size（默认 50）/--source-name | 与 --help 一致 ✅ |
| pipeline_cli.py check-services --config | 存在该子命令与旗标 ✅ |
| backfill_errors.py：--run-id/--apply/--run/--include-md-fetch/--new-run-id/--config/--runs-dir；默认 dry-run 零写 | 与 --help 及源码一致（默认 dry-run：不传 --apply/--run 即零写）✅ |
| compact_run.py：--session-run-id（可重复）/--dry-run/--runs-dir；exit 0/2 语义 | 与 --help 一致 ✅ |
| 示例引用的 4 个脚本路径 scripts/{run_bulk,pipeline_cli,backfill_errors,compact_run}.py | 均存在 ✅ |
| 监控示例引用的日志路径（logs/bulk-<ts>/bulk.log、summary.json、runs/<id>/<jb>/progress.jsonl、ledger.jsonl 字段） | 与实际 run 目录逐一核对一致 ✅ |

### 9.5 JSON 校验
```
OK: aminer-open-skill/.claude-plugin/marketplace.json
OK: aminer-open-skill/skills/{backfill-errors,compact-run,ingest-csv,monitor-run,run-extraction,run-tests}/.claude-plugin/plugin.json
```
7/7 通过。✅

### 9.6 遗留事项（留给用户验收）
- `openclaw skills install ./aminer-open-skill/skills/<name>` 逐个安装实测（本任务红线禁止真实安装验收）；marketplace.json schema 若被 openclaw 拒绝，仅需调整该单个文件。
- 涉及真实 BERT/LLM 内网服务的步骤（run / backfill --run）均已在文档中显式标注"确认后执行"，留待用户安装后手动测试。

---

# v2 重构：自包含独立仓库（2026-08-22）

## 10. 动机与决策

v1 按"skill 只做规程级包装、引用父仓库脚本"执行，导致 skill 包依赖
exp-extraction-project 才能运行。用户澄清真实目标：**aminer-open-skill/ 作为独立
仓库单独 push，别人拉下来就能用**。v2 据此重构，核心决策：

1. **运行时代码 vendor 进包根**，目录布局与上游镜像（`scripts/ pipeline/ configs/
   tests/ ...`）。依据：全库路径锚定均为 `__file__` 相对（`PROD_ROOT =
   parents[1]`、`PROJECT_ROOT = parents[2]`），镜像布局让入口脚本、测试、默认值
   零改动可用。
2. **按公网标准脱敏**（推送目标未定，就高不就低）：内网端点/模型路径全部移除，
   取值只能来自 config 或环境变量。**只改副本，父仓库零改动。**
3. **测试随包**：保住基线验证能力；唯一连服务的 `tests/test_LLM.py` 改为
   环境变量未设时模块级自动 skip。
4. v1 的 6 个 skill、marketplace.json、README 骨架全部保留，文档口径从
   "exp-extraction-project 仓库根"改为"本仓库根"并补首次安装引导。

## 11. vendor 清单（含 v2 执行中实测补充）

计划 9 个脚本，实际 **14 个**——跑 vendored 测试发现 5 个"独立脚本"被测试按
文件路径加载（build_ai2000_manifests / phase3_longrun_monitor / run_phase6_sweep /
collect_phase6_results / phase7_compare_predictions），一并补入。完整清单见
`VENDOR_MANIFEST.json`（copied_paths）。总计约 4.7MB、430+ 文件。

## 12. 脱敏清单（比计划多出 4 处，全树 grep 实测发现）

| # | 位置 | 处理 |
|---|---|---|
| 1 | `configs/default.yaml`（3 端点值 + 集群拓扑注释） | 值改空串 + 中性引导注释 |
| 2 | `pipeline/benchmark/config.py:24-30`（env 兜底默认 + 拓扑注释） | 默认改空串 + 注释重写 |
| 3 | `scripts/pipeline_cli.py`（DEFAULT_QWEN_CHAT_URL） | 改空串 |
| 4 | `pipeline/production/batch_bert_pipeline_wf4.py:1385`（api_url 三级兜底） | 兜底改空串 |
| 5 | `pipeline/production/runners/batch_run_wf4.py:657-659`（print 兜底） | 改空串 |
| 6 | `scripts/run_bulk.py:64`（NO_PROXY 含两个内网 IP）**（计划外）** | 收敛为 127.0.0.1,localhost |
| 7 | `pipeline/benchmark/stages/openai_chat_qwen_client.py:20`（docstring URL）**（计划外）** | 改中性表述 |
| 8 | `tests/test_phase3_fault_injection.py:348-375`（模拟错误串含 IP）**（计划外）** | 换中性主机名（分类只依赖子串顺序，语义不变，测试通过验证） |
| 9 | `pipeline/production/docs/STRATEGY_PROD_WF4_BERT_FLAT_50.md`（示例命令含 IP）**（计划外）** | 换占位符 |
| 10 | `tests/test_LLM.py` | 端点只读环境变量；未设时模块级 skip；docstring 中性化 |

全树按内网 IP（完整地址）与模型路径模式扫描，零残留。

## 13. 其他 v2 产物

- `.gitignore`（独立仓库版）：忽略 `.venv/ __pycache__/ .pytest_cache/`、
  `pipeline_output` 运行时输出（白名单保留 fixture run）、`manifests/**`（留
  .gitkeep）。其中显式写出的 `pipeline_output/production/{runs,logs,exports}/`
  行为满足 `test_runtime_artifact_paths_are_gitignored` 的断言。
- `manifests/.gitkeep`：manifest 由使用者 ingest 生成或自带，不随包附带内部数据。
- `VENDOR_MANIFEST.json`：上游 commit（49df0066bd48…）、复制清单、脱敏记录。
- `CONTRIBUTING.zh.md` 随包（父仓库中本就未跟踪，即为本包而写）。

## 14. v2 自验记录（2026-08-22，全部通过）

### 14.1 vendored 测试套件（包根执行，用父仓库 .venv 解释器）
```
$ cd aminer-open-skill && ../.venv/bin/python -m pytest tests/ -q
336 passed, 1 skipped in 10.84s
```
336 + 1（test_LLM 模块级 skip，盖住 5 个服务用例）= 与父仓库 341 基线同源；
设 `LLM_CHAT_URL`/`BERT_SERVER_URL` 且服务可达时应为 341 passed。**证明路径
锚定与测试可移植成立。**

### 14.2 运行时导入链（registry 自注册 → 规则包模型 → preprocess → reference_detector）
```
import chain OK; WF4_WORKFLOW_VERSION = 0.8.0
rule_pack OK / preprocess + reference_detector OK
```

### 14.3 入口脚本
`run_bulk / pipeline_cli / backfill_errors / compact_run / merge_flat_experiments`
五个入口 `--help` 全部正常（包根执行）。

### 14.4 配置与 JSON
脱敏后 `configs/default.yaml` 可正常解析（bert_server_url=''、llm_model=''）；
marketplace.json / 6 个 plugin.json / VENDOR_MANIFEST.json 共 8 个 JSON 全部
`json.tool` 校验通过。

### 14.5 脱敏扫描
对全包做内网 IP / 用户模型路径的 grep 扫描 → **零命中**（PLAN.md 自身的扫描
模式描述亦已泛化，不含任何前缀）。

### 14.6 父仓库零影响
`git status --short` 仅 `aminer-open-skill/` + 既有两条未跟踪文件；父仓库
`pytest tests/ -q` 复跑 341 passed（见 §15）。

### 14.7 v2 遗留事项
- `openclaw skills install ./skills/<name>` 安装实测仍留给用户。
- 全新机器端到端（建 venv → pip install → 填端点 → 起真实 run）未执行
  （红线禁止真实服务调用）；Quick Start 命令已按 `--help` 与 requirements.txt
  纸面核对。
- vendored 副本与上游的后续同步：可参考上游 `scripts/vendor_from_upstream.py`
  的做法手动更新 VENDOR_MANIFEST.json。


---

## 16. v3 重构：OpenClaw 标准单 skill 格式（2026-08-21）

### 16.1 动机
用户实测 `openclaw skills install ~/project/exp-extraction-project/aminer-open-skill`
报错 "archive is missing SKILL.md"。查证 openclaw 官方文档（docs.openclaw.ai/
clawhub/skill-format、/cli/skills、/tools/skills）确认：openclaw 的 skill 格式是
**单目录 + 根部 SKILL.md**，本地/git 安装均要求源根部有 SKILL.md；它**没有**
commands/ 斜杠命令目录概念（那是 Claude Code 插件约定），也不读
`.claude-plugin/marketplace.json`。v2 的 "6 个子 skill + marketplace.json" 结构
openclaw 无法整体安装；逐个安装 `./skills/<name>` 则只拷 4 个 skill 文件、不含
运行时，装出来引用路径全部悬空（实测证实）。

### 16.2 结构变更
- 新增根部 `SKILL.md` + `SKILL.zh.md`：单一 skill（name: aminer-open-skill），
  合并原 6 个 SKILL.md 的全部内容为 6 个操作章节（run-extraction / ingest-csv
  / monitor-run / backfill-errors / compact-run / run-tests），frontmatter 保持
  任务书标准（name/version/author/contact + 三段式 description + metadata.
  openclaw.requires），包内路径以 openclaw 官方的 `{baseDir}` 占位符引用；
  护栏措辞逐字保留。
- 删除 `skills/` 整目录（6×SKILL.md/SKILL.zh.md/commands/plugin.json）与根部
  `.claude-plugin/marketplace.json`。
- 运行时零改动：`scripts/`（14 个 CLI）本就在标准位置，全部路径
  `__file__` 锚定于 parents[1]，安装到任何目录都可用。
- README.md / README.zh.md 改为单 skill 口径（一条命令安装：本地路径或
  git URL）。
- VENDOR_MANIFEST.json notes 追加 v3 布局说明。

### 16.3 排序与产物路径说明
安装副本内的 run 产物落在 `~/.openclaw/workspace/skills/aminer-open-skill/
pipeline_output/production/`——SKILL.md 与 README 已写明：轻量操作用安装副本，
长期重度生产 run 用独立 clone。

### 16.4 v3 自验记录
- `openclaw skills install ./aminer-open-skill` 成功；安装副本含 SKILL.md +
  scripts/ + pipeline/ + configs/（全目录拷贝，仅新增 .openclaw/source-origin.json）。
- `openclaw skills list` / `skills check` 确认注册且依赖满足。
- 包根 pytest 复跑仍 336 passed + 1 skipped。
- 脱敏复扫（内网 IP / 模型路径模式）零命中。
- 已清理此前试装的坏 skill `aminer-run-extraction`（仅 4 文件、路径悬空）。

### 16.5 v3 遗留事项
- git 安装方式（`openclaw skills install git:<url>`）待独立仓库远程建好后实测。
- ClawHub 发布（clawhub skill publish）如需，另记；50MB 上限内（包 ~8.5MB）。

### 16.6 v3.1 依赖安装改为 uv 优先（2026-08-21）
用户指出寻常 openclaw skill 不应让使用者手工装 venv。核实官方文档：openclaw 的
`metadata.openclaw.install` 规范支持 brew/node/go/uv/download 五种安装器（偏好序
Homebrew → uv → node → go → download），Python 生态的正规路径是 uv。据此调整：
- frontmatter：`requires.anyBins: ["uv","python3"]` + `install: [{kind: "uv", bins:
  ["uv"]}]`（openclaw/macOS Skills UI 可自动装 uv）。
- 首次使用改为 uv 优先：`uv venv .venv --python 3.12` + `uv pip install`（uv 自管
  Python，绕开系统缺 python3.12-venv/ensurepip 的问题）；另给零安装替代
  `uv run --with-requirements requirements.txt --python 3.12 ...`；普通 venv 降为
  备选。
- 实测（WSL，uv 0.12.5）：`uv run --with-requirements` 首跑自动装配 Python 3.12 +
  全部依赖并跑通 5 入口 --help；缓存后启动 0.5s；`uv venv` 建的包内 .venv 跑全套
  测试 336 passed + 1 skipped。README 双语同步。

### 16.7 v3.2 移除 venv，全面改为标准 openclaw/uv 方式（2026-08-21）
应用户要求删除包内 `.venv`，与标准 openclaw skill 对齐：SKILL.md/README（英中）
中的全部命令改为 `uv run --with-requirements requirements.txt --python 3.12
python ...` 字面形式（pytest 用叠加 requirements-dev.txt 的变体，heredoc 同）；
首次使用只剩两步（装 uv + 填端点），不再有任何 venv 创建/维护说明。依赖解析
走 uv 全局缓存（首跑 ~30s 下载，之后启动 <1s），包内零环境残留。实测：无
.venv 状态下 pytest 336 passed + 1 skipped，heredoc 形式正常。

### 16.8 v3.3 run-id/输出默认值约定（2026-08-21）
SKILL.md §1 新增 Defaults 小节：用户不指定时——manifest-dir 按 `{baseDir}/
manifests/` 目录名模糊匹配（如"p500"→ai2000_p500single）；run-id 默认
`<manifest目录名>-<YYYYMMDD-HHMM>`（与已有 run 冲突则按当前时间重生成，仅用户
明确要求重启才复用）；输出位置固定（runs/logs/exports/bulk_state，自动创建）。
配合本机安装副本的就绪准备（端点值静默写入 + p500 manifest 拷入 + uv 探活
6/6 OK，均为运行时状态不入库），最小指令"跑 p500 抽取"即可执行。

---

## 17. v4 重构：多 skill 仓库 aminer-exp-skill（2026-08-22）

### 17.1 动机与结构
团队需要向同一仓库持续添加新 skill。结构调整：
- 仓库更名 `aminer-open-skill` → `aminer-exp-skill`（git 历史经 `git mv` 保留）。
- 原全部内容整体下移一层至 `skills/aminer-exp-extraction/`，作为技能集中的第一个
  skill（frontmatter name 同步改为 `aminer-exp-extraction`）。
- 仓库根新增正式 README.md/README.zh.md 与根 .gitignore（通用忽略；skill 各自带
  自己的运行时忽略规则）。
- 安装方式变为按 skill 粒度：`openclaw skills install ./skills/<name>`。

### 17.2 运行时零改动依据
全部脚本路径 `__file__` 锚定于 scripts/ 的上级（PROD_ROOT = parents[1]），整棵树
下移一层后锚点随迁，代码零改动；重排后测试套件复跑验证（见 17.3）。

### 17.3 v4 自验记录
- 重排后包内 pytest：336 passed + 1 skipped（git 仓库根上移不影响
  test_runtime_artifact_paths_are_gitignored 的 check-ignore 判定）。
- 5 个入口脚本 --help 正常。
- openclaw 卸载 aminer-open-skill、改装 `./skills/aminer-exp-extraction`，
  skills check 就绪。
