---
name: aminer-exp-extraction
version: 1.0.0
author: AMiner
contact: report@aminer.cn
description: >
  [激活条件] 用户要求操作论文抽取流水线时使用：启动/重启批量抽取 run（快照或
  watch 模式）、从 CSV 增补论文、查看 run 进度/错误、补数/回填错误篇（"补数"、
  "回填"、"backfill"）、压缩已结束 run 释放磁盘、或跑测试套件。
  [适用场景] 自包含 skill 包：内置完整运行时（pipeline、scripts、configs、
  规则/ML 包、tests），并给出六类操作的标准规程——run-extraction、
  ingest-csv、monitor-run、backfill-errors、compact-run、run-tests——每类含
  预检清单、精确命令、退出码语义与护栏。
  [路由规则] 一次请求只做一类操作：启动/重启 run → §run-extraction；向运行中
  的 watch run 喂新论文 → §ingest-csv；"run 跑得怎么样了" → §monitor-run
  （只读，永远是安全的第一步）；重跑已结束 run 的错误篇 → §backfill-errors；
  释放已结束 run 的磁盘 → §compact-run；验证仓库全绿 → §run-tests。不可混用：
  先补数后压缩；任何状态变更决策前先 monitor；补数/实验 run 永不进官方
  export/merge。
metadata:
  {
    "openclaw":
      {
        "emoji": "🦞",
        "requires":
          {
            "anyBins": ["uv", "python3"],
            "env": []
          },
        "install":
          [
            {
              "id": "uv",
              "kind": "uv",
              "bins": ["uv"],
              "label": "Install uv (Python package manager)"
            }
          ]
      }
  }
---

# aminer-exp-extraction — 论文抽取流水线操作 skill

生产级 LLM 论文抽取流水线的自包含 skill 包。本 SKILL.md 所在目录（"skill
根"，下文以 `{baseDir}` 引用）内置完整运行时：`pipeline/`、`preprocess/`、
`scripts/`（14 个入口/工具 CLI）、`configs/`、冻结的规则/ML 包、`tests/`、
`requirements.txt`。运行时不依赖 `{baseDir}` 之外的任何东西；服务端点来自
`configs/default.yaml` 或环境变量（绝不内置）。

下文所有命令都**在 skill 根下**、用 [uv](https://docs.astral.sh/uv/) 执行
（`uv run --with-requirements requirements.txt --python 3.12 python ...`）——
uv 首次使用时自动把 Python 3.12 与全部依赖解析进它自己的全局缓存；包内不创建、
也不维护任何 venv。命令中的路径均相对 `{baseDir}`。

## 操作路由

| 用户意图 | 章节 | 脚本 |
|---|---|---|
| 启动 / 重启生产 run（快照或 watch 模式） | [run-extraction](#1-run-extraction--起一个生产抽取-run) | `scripts/run_bulk.py` |
| 从 CSV 向 manifest 目录增补论文（喂 watch run） | [ingest-csv](#2-ingest-csv--从-csv-动态增补论文) | `scripts/pipeline_cli.py ingest` |
| "run 跑得怎么样了"——进度、错误、退出码 | [monitor-run](#3-monitor-run--只读-run-监控) | （仅读取日志面） |
| 重跑已结束 run 的错误篇、提升 durable 率 | [backfill-errors](#4-backfill-errors--补数回填错误篇) | `scripts/backfill_errors.py` |
| 释放已结束 run 的磁盘空间 | [compact-run](#5-compact-run--已结束-run-的手动压缩) | `scripts/compact_run.py` |
| 验证仓库仍然全绿 | [run-tests](#6-run-tests--跑流水线测试套件) | pytest |

跨章节顺序规则：**补数决策先于压缩**（压缩会改变 run 目录形态；`ledger_ok`
只在已压缩的 run 中出现）；对 run 做任何状态变更决策前**先 monitor**；绝不操作
仍在执行中的 run。

## 首次使用（新克隆 / 新安装）

只需要两件事：PATH 上有 [uv](https://docs.astral.sh/uv/)，以及服务端点。
不创建任何 venv——下文所有命令经 `uv run` 自动解析 Python 3.12 + 依赖
（首次调用会下载并缓存，约 30 秒；之后启动不到 1 秒）。

```bash
# 1. 未装 uv 先装（用户级，无需 sudo）：
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 填入你的服务端点——二选一：编辑 configs/default.yaml 的
#   bert_server_url / llm_api_url / llm_model
# 或导出环境变量（优先级高于 yaml）：
#   BERT_SERVER_URL / LLM_CHAT_URL / LLM_MODEL
```

端点探活（同时验证依赖解析）：

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/pipeline_cli.py check-services --config configs/default.yaml
```

## 通用预检（每类操作前）

1. 工作目录 = skill 根（`{baseDir}/scripts/run_bulk.py` 必须存在）；
   `uv --version` 必须成功（否则先完成首次使用）。
2. 检查可选环境变量覆盖——**只看是否设置，绝不打印值**：

```bash
for v in BERT_SERVER_URL LLM_CHAT_URL LLM_MODEL; do
  if [ -z "${!v+x}" ]; then
    echo "$v: 未设置（将使用 configs/default.yaml 中的值）"
  else
    echo "$v: 已设置（覆盖 configs/default.yaml）"
  fi
done
```

3. 会调用服务的操作（run-extraction、backfill 的 `--run`）必须先通过
   check-services 探活；monitor 与测试绝不调用服务。

## 1. run-extraction — 起一个生产抽取 run

通过 `scripts/run_bulk.py` 启动（或安全重启）一个生产批量抽取 session run。

### 默认值（用户未显式给出时）

- **manifest-dir**：用户口语化提到数据集（如"p500"）时，列
  `{baseDir}/manifests/` 并匹配目录名（如 `manifests/ai2000_p500single`）；
  无匹配或有多个匹配时先询问再继续。
- **CSV 输入（从零起跑）**：用户给了 CSV 路径且无匹配 manifest 时，先按 §2
  ingest 流程准备 manifest——目标为以 CSV 文件名主干命名的新 manifest 目录
  （如 `ai2000_test800.csv` → `manifests/ai2000_test800/`），核对 ingest 报告
  的 `new` 数量符合预期且 `invalid` / `conflict` 为零，再继续下面的起跑步骤。
  一条指令即可覆盖 CSV → ingest → run 全链路。
- **run-id**：`<manifest目录名>-<YYYYMMDD-HHMM>`（本地时间，起跑时取——如
  `ai2000_p500single-20260821-1530`）。先查
  `pipeline_output/production/runs/`：若该 id 已存在，按当前时间重新生成；
  仅当用户明确要求重启某 run 时才复用已有 id（同 id 重启跳过 ok 篇、重试
  error 篇）。
- **输出位置**（自动创建，无需配置）：预测/checkpoint/进度在
  `pipeline_output/production/runs/<run-id>/job_batch_*/`；进程日志在
  `pipeline_output/production/logs/bulk-<ts>/`；单 run 导出快照
  `pipeline_output/production/exports/<run-id>_*.json`；运行器状态
  `pipeline_output/production/bulk_state.json`。

有这些默认值，"跑 p500 抽取"这样的最小指令即可执行——起跑前把推导出的
manifest-dir 和 run-id 报给用户确认。

快照模式（处理完 manifest 目录后退出）：

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/run_bulk.py \
  --manifest-dir manifests/<source-dir> \
  --run-id <session-run-id> \
  --config configs/default.yaml
```

watch 模式（启动队列排空后，在批次边界重扫 manifest 目录、追加新的
`job_batch_*.json`；空闲 `--watch-idle-timeout` 秒后退出）：

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/run_bulk.py \
  --manifest-dir manifests/<source-dir> \
  --run-id <session-run-id> \
  --config configs/default.yaml \
  --watch-manifest --poll-interval 5 --watch-idle-timeout 600
```

**这些命令会调用真实 BERT/LLM 服务——执行前必须与用户确认。**

其余常用旗标（已对照 `--help` 核实）：`--job-batches 006`（可重复，显式批次
列表——与 `--start-from` 互斥，与 `--watch-manifest` 同用会被拒绝）、
`--smoke N`（只跑前 N 篇即退出）、`--force`、`--no-gate`、
`--no-md-cache-cleanup`。

停止语义与重启：

- **SIGINT / SIGTERM**（如 Ctrl-C）：优雅停止。当前 `pipeline_batch` 收尾、
  写 checkpoint，随后进程以退出码 **130** 退出；停止时跳过 md-cache 清理与
  compaction。
- **SIGKILL**（`kill -9`）：设计上安全——预测文件原子写入，被杀的 run 不会
  留下撕裂状态。
- **重启**：用**完全相同的命令 + 相同 `--run-id`** 重跑。已是 ok 的篇目跳过、
  error 篇目重试。生产是单段式（无 resume 阶段）——这个重启行为就是恢复机制。
- 唯一的子进程是边界处瞬态的 `merge_exports.py`。

退出码：**0** 正常完成；**2** 质量门（error_rate > 15%）；**3** 门暂停
（parse_error_rate > 10% 或 zero_datasets_rate > 25%；已写
`bulk_state.json` + `job_checkpoint.json`）；**130** 被 SIGINT/SIGTERM 优雅
停止。

约束：同时只允许一个生产 run；**语义参数冻结**（见护栏）；不得手工修改或删除
`pipeline_output/production/runs/` 下的任何东西——查看用 monitor-run，释放
空间用 compact-run。

## 2. ingest-csv — 从 CSV 动态增补论文

通过 `scripts/pipeline_cli.py ingest` 把 CSV 中的论文作为新
`job_batch_*.json` 追加进 manifest 目录。ingest **只写 manifest 文件**——
绝不触发抽取、绝不调用服务。watch 模式的 runner 会在批次边界拾取新批次。

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/pipeline_cli.py ingest \
  --csv <paper-list.csv> \
  --manifest-dir manifests/<source-dir> \
  --run-id <session-run-id>
```

把"仅有 error 预测"的行重新入队（默认只报告不入队），并指定批次大小：

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/pipeline_cli.py ingest \
  --csv <paper-list.csv> \
  --manifest-dir manifests/<source-dir> \
  --run-id <session-run-id> \
  --include-retry --size 500 --source-name <name>
```

旗标（已对照 `--help` 核实）：`--csv`（必填）、`--manifest-dir`（必填）、
`--run-id`（可重复——列出的每个 run 的预测都参与去重）、`--include-retry`、
`--size`（每个新 job_batch 的论文数，默认 500）、`--source-name`。

每行 CSV 按以下优先级五路分类：`invalid > conflict > duplicate > retry > new`。

- **invalid** —— 行格式错误（先修 CSV）；
- **conflict** —— 已知论文的元数据不一致；
- **duplicate** —— 论文在列出的 run 中已有 ok 预测；
- **retry** —— 论文仅有 error 预测（仅在 `--include-retry` 时重新入队）；
- **new** —— 进入新发布的 job_batch。

幂等与影响面：manifest 原子发布；目标目录的 `job_batch` 编号单调递增——重复
执行同一 ingest 不会重复入论文。影响面：**只有目标 `--manifest-dir` 新增
`job_batch_*.json` 文件**。不得发明或改写论文元数据；CSV 原样透传——
invalid/conflict 行是上游数据问题，如实报告。不得把 `--manifest-dir` 指向
`manifests/backfill/` 产物——补数 manifest 归 §backfill-errors 所有。

## 3. monitor-run — 只读 run 监控

从流水线的六层日志面推导 session run 的健康状态。本节一切操作**只读**——
monitor 绝不修改任何东西；若结论指向动作，如实报告并路由到对应章节。

Run 根：`pipeline_output/production/runs/<session-run-id>/`。日志 session：
`pipeline_output/production/logs/bulk-<ts>/`（每次进程启动的 append-only 日志
目录）。

| 层 | 路径 | 提供什么 |
|---|---|---|
| 1 | `logs/bulk-<ts>/bulk.log` | append-only、pid 标注、双时区（本地 +08:00 与 UTC）；以 `PROCESS START` / `PROCESS END pid=... exit=N` 分帧 |
| 2 | `logs/bulk-<ts>/session.pid*.json` | 启动配置快照（session id、pid、时区、启动时间） |
| 2 | `logs/bulk-<ts>/job_batch_*.pid*.summary.json` | 每批次 `papers_total / ok / error / skipped`、`rates`（error_rate、parse_error_rate、zero_datasets_rate）、`error_classes` 计数 |
| 3 | `runs/<run-id>/<job_batch>/progress.jsonl` | 每篇一行：`ts / status / error / llm_elapsed_sec`（含 run/批次/论文 id） |
| 4 | `runs/<run-id>/ledger.jsonl` | 每篇最终状态 + `prediction_sha256` + `workflow_version`（仅较新 run——老 run 无 ledger） |
| 5 | `runs/<run-id>/<job_batch>/monitors/<paper_id>_monitor.json`、`staged_pipeline_monitor.json`、`bert_batch_monitor.json` | 各阶段耗时、merge_conflicts |
| 6 | `runs/<run-id>/<job_batch>/predictions/<paper_id>.json` | 每篇的 `error` 字段——补数分类的数据源 |

示例读取（全部只读）——找日志 session 与最终退出码：

```bash
ls pipeline_output/production/logs/ | grep bulk | tail -n 5
grep -h "PROCESS END" pipeline_output/production/logs/bulk-<ts>/bulk.log
```

从 progress.jsonl 统计各批次状态与吞吐：

```bash
uv run --with-requirements requirements.txt --python 3.12 python - <<'PY'
import json, glob, collections
for f in sorted(glob.glob('pipeline_output/production/runs/<run-id>/job_batch_*/progress.jsonl')):
    c, llm = collections.Counter(), []
    for line in open(f):
        r = json.loads(line)
        c[r['status']] += 1
        if r.get('llm_elapsed_sec') is not None:
            llm.append(r['llm_elapsed_sec'])
    print(f, dict(c), 'llm_avg_sec=%.2f' % (sum(llm)/len(llm) if llm else 0))
PY
```

从 ledger 统计错误类分布（`workflow_version` 从 ledger 读取——不得硬编码）：

```bash
uv run --with-requirements requirements.txt --python 3.12 python - <<'PY'
import json, collections
c = collections.Counter()
for line in open('pipeline_output/production/runs/<run-id>/ledger.jsonl'):
    c[json.loads(line)['status']] += 1
print(dict(c))
PY
```

退出码解读：**0** 报告最终 ok/error/skipped 计数；**2** 列出错误类，若需提升
durable 率路由到 §backfill-errors；**3** 报告触发的是哪个门（checkpoint 已
写）；**130** 该 run 可用相同 run-id 重启。

诊断边界：**LLM 原始响应默认不落盘。** `parse_error` 篇只保留解析器的诊断
字符串——报告该字符串，不得承诺原始响应转储。

数字必须与日志面推导结果逐字一致——不估算、不编造。某层缺失（如老 run 没有
ledger.jsonl）就明说，退回用存在的层。

## 4. backfill-errors — 补数（回填错误篇）

对给定**已结束**的 session run：推导"错误集"（run 见过的篇目 − durable-ok），
按可重试类别生成补数 manifest，用**全新独立 session run id** 重跑，再验证
durable 率提升。绝不触碰官方 export/merge。run 仍在执行时**不得**补数——先
monitor。

额外预检：run 存在（`pipeline_output/production/runs/<session_run_id>/` 下有
`job_batch_*/`）；真实重跑前服务可达；`manifests/` 下的源 manifest 必须索引
该 run 论文的 `md_url`（dry-run `no-md_url` 警告数 = 0；非零说明语料 manifest
缺失——先修语料）。

### 4.1 dry-run（默认，零写）

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/backfill_errors.py --run-id <session_run_id>
```

审查清单——`--apply` 前**逐项**确认：
- [ ] universe 数与 run 规模一致（= run 见过的论文数）；
- [ ] 分类符合预期：`parse_error / llm_timeout / llm_http /
      bert / post_llm / missing_prediction / corrupt` 进入补数；
      `md_fetch` 默认排除（死链重试无意义，除非用户明确要求
      `--include-md-fetch`）；
- [ ] `ledger_ok`（若有）只出现在已压缩的 run；
- [ ] `WARN no md_url` 为 0；
- [ ] 预期 durable 率增益与错误集规模一致。

### 4.2 生成补数 manifest

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/backfill_errors.py --run-id <session_run_id> --apply
```

产物：`manifests/backfill/<run-id>-<YYYYMMDD-HHMMSS>/job_batch_backfill_000.json`
（原子写入，含 `backfill_meta.json` 溯源）。该目录被 gitignore、绝不提交。注意
run id 与时间戳之间是**连字符**拼接。

### 4.3 执行补数 run（新 session id——核心护栏）

**此步骤会真实调用 BERT/LLM 服务；耗时与错误集规模成正比。执行前必须与用户
确认。**

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/backfill_errors.py --run-id <session_run_id> --run \
    --config configs/default.yaml
# 等价于：run_bulk --manifest-dir <backfill-dir> --run-id <orig>-bf<YYYYMMDD>
```

- 新 run id 默认 `<orig>-bf<YYYYMMDD>`（仅当用户明确要求时才用 `--new-run-id`
  覆盖）。
- 同时只跑一个 run；合并多个 run 的补数前先问用户。

### 4.4 验证 durable 率

```bash
ls pipeline_output/production/runs/<orig>-bf<date>/job_batch_backfill_000/predictions/ | wc -l
uv run --with-requirements requirements.txt --python 3.12 python scripts/backfill_errors.py --run-id <session_run_id>   # 同口径错误集复查
```

通过标准（**并集口径**——独立 session 即护栏；原 run 的错误集本身不变）：
- 补数 run 的 ok 预测数 ≈ 补数论文数；
- 并集 durable =（原 run ok ∪ 补数 run ok）/ universe 达到预期值
  （如 5/10 → 10/10）。
- 清理提示：run 结束时 run_bulk 会为该 run 自动跑 `merge_exports`，产出
  `pipeline_output/production/exports/<bf-run-id>_job_batch_backfill_000.json`
  （以 run id 命名的独立文件——绝不进入任何官方交付 JSON）。补数/实验 run
  应在汇报前删除这一个文件以保持 `exports/` 干净。删除的影响面：仅那一个
  自动生成文件，别无其他——删除前向用户说明。

### 4.5 汇报模板

```
Backfill report: <orig> -> <orig>-bf<date>
- Error set: <counts per class> (md_fetch excluded N papers: dead links, upstream data fix needed)
- Durable rate: X/Y (a%) -> (X+B)/Y (b%) (actually recovered M/B)
- Remaining unrecovered: <paper_id + reason, one per line>
- Artifacts: manifests/backfill/<dir>/ (gitignored)
```

补数专属护栏（任一被违反即停止并解释）：
1. 补数 run id 是**独立 session**——绝不进入官方 export / merge_flat /
   merge_exports。
2. 本规程绝不调用官方 merge/export 脚本。
3. 默认 dry-run；审查清单完成前不得 `--apply` / `--run`；各步按序且只执行一次
   （dry-run → 审查 → apply → run → 验证 → 汇报）；未确认清单前不得把
   `--apply` 与 `--run` 批量连做。
4. md_fetch 死链默认不补（上游数据问题）；纳入需用户明确要求
   （`--include-md-fetch`）。
5. 补数/实验 run 产物只存在于被 gitignore 的目录（`runs/`、
   `manifests/backfill/`）。

## 5. compact-run — 已结束 run 的手动压缩

通过 `scripts/compact_run.py` 压缩已结束的 session run。**这是破坏性（释放
空间）操作：必须先 `--dry-run` 并向用户展示将要发生什么，确认后才真实执行。**

额外预检：
1. run 已**结束**（该 run 无存活 bulk 进程——查
   `pipeline_output/production/logs/bulk-<ts>/bulk.log` 以 `PROCESS END`
   结尾，或用 §monitor-run）。绝不压缩执行中的 run。
2. 若计划对该 run 补数，先做补数决策（§backfill-errors）：压缩改变 run 目录
   形态，且 `ledger_ok` 条目只在已压缩 run 中出现，会改变补数 dry-run 的审查
   基准。

第一步——dry-run（零写，强制先行）：

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/compact_run.py --session-run-id <session-run-id> --dry-run
```

第二步——真实压缩（用户确认 dry-run 报告之后）：

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/compact_run.py --session-run-id <session-run-id>
```

一次调用压缩多个 run（`--session-run-id` 可重复），或对拷贝的 runs 树离线
操作：

```bash
uv run --with-requirements requirements.txt --python 3.12 python scripts/compact_run.py \
  --session-run-id <run-a> --session-run-id <run-b> \
  --runs-dir <copied-runs-dir> --dry-run
```

旗标（已对照 `--help` 核实）：`--session-run-id`（必填、可重复）、`--dry-run`、
`--runs-dir`（覆盖 runs 根——对副本操作）。

退出码：**0** 已压缩（或 dry-run / 无事可做）；**2** 校验失败——**原件保留**，
无损失；报告并停止。

绝不用手工删除 `pipeline_output/production/runs/` 下文件的方式"绕开"本工具。

## 6. run-tests — 跑流水线测试套件

在 skill 根下跑 pytest 套件。对代码与测试严格只读；完全离线跑 fixtures（不调
BERT/LLM 服务）。新安装先用 `requirements-dev.txt`（含 pytest）。

```bash
uv run --with-requirements requirements.txt --with-requirements requirements-dev.txt --python 3.12 -m pytest tests/ -q                       # 全量
uv run --with-requirements requirements.txt --with-requirements requirements-dev.txt --python 3.12 -m pytest tests/ -q -k backfill           # 按关键字
uv run --with-requirements requirements.txt --with-requirements requirements-dev.txt --python 3.12 -m pytest tests/test_backfill_errors.py -q  # 按文件
```

结果解读：
- **全绿** = `0 failed`、无意外 skip。新克隆且未设服务环境变量的基线：
  **336 passed + 1 skipped**——未设 `LLM_CHAT_URL` / `BERT_SERVER_URL` 时
  `tests/test_LLM.py` 整模块自动跳过；设置且服务可达时为 **341 passed**。
  精确计数是随仓库增长的活动基线——与最近一次记录的全绿 run 对比，而非硬编码
  数字。
- **失败** = 逐字报告失败测试 id 与断言/输出摘录；把失败文件映射到其模块
  （如 `tests/test_backfill_errors.py` → `scripts/backfill_errors.py`）。
- 不得为让测试通过而修改测试、fixtures 或流水线代码；不得不报告首次失败就
  选择性重跑"追"一个侥幸通过。测试失败牵连流水线行为时，如实报告——不在本
  节尝试修复。

## 产物路径

所有 run 产物落在 `{baseDir}/pipeline_output/production/`（`runs/`、`logs/`、
`exports/`、`partials/`）与 `manifests/` 下——这些目录被 gitignore（仅一个
测试 fixture run 被跟踪）。当本 skill 经 `openclaw skills install` 安装后，
即位于安装副本内（如 `~/.openclaw/workspace/skills/aminer-exp-extraction/`）——
适合轻量操作（monitor、ingest、测试、小型 run）。长期重度生产 run 建议使用
skill 仓库的独立 `git clone`，让 run 产物不落在 agent workspace 里，并把操作
者指向那里。

## 护栏（适用于所有操作——任一被违反即停止并解释）

1. **语义参数冻结**：绝不修改配置中的 LLM prompt、模型、温度、
   `bert_threshold` 或任何 schema/normalize/merge/commit 设置。
2. 端点与模型名只来自 `configs/default.yaml` 或环境变量——绝不硬编码；绝不
   打印密钥值。
3. 补数与实验 run **绝不进入官方 export/merge**（官方交付的
   merge_flat_experiments / merge_exports）。
4. 破坏性动作（`--apply`、`--run`、压缩、删除文件）必须先 dry-run 或给出明确
   影响面说明。
5. 调用真实 BERT/LLM 服务的步骤都明确标注"会调用服务——确认后执行"。
6. 如实汇报——数字与日志面推导结果逐字一致；不估算、不编造。

## 文件地图

| 路径 | 职责 |
|---|---|
| `SKILL.md` / `SKILL.zh.md` | 本 skill 定义（英/中，保持同步） |
| `scripts/` | 14 个入口/工具 CLI（run_bulk、pipeline_cli、backfill_errors、compact_run、merge/collect 工具等） |
| `pipeline/`、`preprocess/`、`reference_detector.py`、`rule_ml_extraction_from_promote/` | 内置运行时（流水线阶段、预处理、冻结规则/ML 包） |
| `configs/default.yaml` | 流水线配置——在此填入服务端点 |
| `tests/` + `dataset_evidence/` | 离线测试套件（未设环境变量时活服务用例自动跳过） |
| `requirements.txt` / `requirements-dev.txt` | 运行时 / 开发依赖（全部公网 PyPI） |
| `README.md` / `README.zh.md` | 包概览与 Quick Start |
| `VENDOR_MANIFEST.json` / `PLAN.md` | vendor 溯源、脱敏记录、设计历史 |
