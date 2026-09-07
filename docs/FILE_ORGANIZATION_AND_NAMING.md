# 本地文件整理与命名规范

> 适用范围：`F:\codex\newwqb`。本规范管理项目代码、文档、脚本和归档材料的物理位置与名称；不改变研究状态语义。

## 目录职责

| 路径 | 只存放 | 规则 |
|---|---|---|
| 根目录 | 入口、配置模板、依赖说明 | 只保留 `main.py`、`README.md`、`AGENTS.md`、`config*.json`、`requirements.txt` 等稳定入口 |
| `wqb_agent/` | 生产 Python 模块 | 一个职责一个 `snake_case.py`；禁止临时脚本混入 |
| `scripts/` | 当前仍有用途的辅助脚本 | 使用动作命名，如 `generate_report.py`、`check_health.py`；一次性脚本放归档 |
| `tests/` | 回归测试 | 文件名为 `test_<subject>.py`，测试必须对应生产模块或关键门控 |
| `prompts/` | Agent 提示词 | 使用小写 `snake_case.md` |
| `docs/` | 长期有效规范、路线图、报告和索引 | 主题文档使用大写 `UPPER_SNAKE_CASE.md`；入口为 `docs/README.md` |
| `docs/archive/rounds/` | 历史 round 快照 | 固定 `round_<十进制轮次>.json`，不改历史编号 |
| `docs/archive/run_logs/` | 历史日志 | `run_r<轮次>[_<用途>].log`；观察日志可用 `watch_rounds.log/.err` |
| `docs/archive/scratch/YYYYMMDD/` | 一次性脚本、临时输出、字段快照 | 日期作为目录，不再新建根目录 `_tmp_*` |
| `docs/archive/working_docs/YYYYMMDD/` | 阶段性临时文档 | 仅保留审计有价值的材料 |
| `docs/archive/state_backups/YYYYMMDD/` | 状态备份 | 只读留档；当前运行只认 `.wqb_state/` |
| `docs/archive/{proposals,reports,recovery,configs}/` | 对应类别的历史材料 | 归档根目录不得放散落文件 |
| `.wqb_state/` | 当前运行状态 | 受 `AGENTS.md` 保护，禁止手工移动、重命名或整理 |

## 命名规则

1. Python 使用小写 `snake_case.py`；测试使用 `test_` 前缀。
2. 长期文档使用大写主题名，例如 `SIMULATION_SETTINGS.md`；轮次或纪元标签放在末尾，例如 `CAMPAIGN_SUMMARY_RB162-RB179.md`。
3. JSON/日志/快照名称使用稳定对象加日期或轮次：`<kind>_r<round>_<YYYYMMDD>.<ext>`；日期统一 `YYYYMMDD`，轮次统一十进制内部编号。
4. 临时文件不得以无语义的 `_tmp`、`new`、`final2`、`copy` 作为唯一名称；必须说明用途，且优先放入 `scratch/YYYYMMDD/`。
5. 不为“最新”创建 `latest`、`newest` 等会漂移的文件名；当前状态通过固定路径或程序生成。
6. 文件名只使用 ASCII 字母、数字、下划线、短横线和点；避免空格、中文、括号和多重后缀。
7. 历史材料原则上不改名；确需迁移时保留内容、更新引用，并在本文件记录映射。

## 整理流程

1. 先用 `rg` 搜索文件名、路径和入口引用，再确定目标路径。
2. 先分类，再移动；不在一次操作中同时改变内容和语义。
3. 移动后全局搜索旧路径，更新 `README`、索引和仍有效的文档引用。
4. 对代码路径运行相关测试；对纯归档移动做文件存在性和引用核对。
5. 禁止整理 `.wqb_state/`、运行锁、checkpoint、trajectory、simulation 缓存或任何仍可能被生产入口读取的文件。
6. 删除前先归档；除非用户明确要求，不删除历史证据或恢复材料。

## 2026-08-26 迁移记录

| 原位置/名称 | 新位置/名称 |
|---|---|
| `archive/scratch_20260818/` | `archive/scratch/20260818/` |
| `archive/tmp_root_20260826/` | `archive/scratch/20260826/` |
| `archive/state_backup_20260818/`、`state_backup_20260819/` | `archive/state_backups/20260818/`、`20260819/` |
| `archive/tmp_docs_20260819/` | `archive/working_docs/20260819/` |
| 归档根目录散落的提案、报告、配置、恢复输出 | 分别移入 `proposals/`、`reports/`、`configs/`、`recovery/` |
| `_tmp_pending_recovery_20260818.json` | `recovery/pending_recovery_r171_20260818.json` |
| `config.research.json` | `configs/config_research_legacy.json` |
| `r340_summary.md` | `reports/research_summary_r340.md` |

历史 `rounds/`、`run_logs/` 和 `historical_docs/` 保持原位，以免破坏既有审计引用。
