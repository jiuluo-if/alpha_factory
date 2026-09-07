# `.wqb_state` 状态与记忆布局

> `.wqb_state` 是程序维护的运行状态目录。文件名是接口的一部分；本文件负责分类和阅读顺序，不授权手工移动、改名或重写状态文件。

## 分类总览

| 类别 | 固定路径/模式 | 内容与权威性 | 处理规则 |
|---|---|---|---|
| 记忆：决策视图 | `context.md` | 给下一轮读取的压缩视图；可由程序重建 | 先读；不手改 |
| 记忆：经验库 | `experience.json` | `current_best`、`active_hypotheses`、`short_term`、`lessons`、`avoid`、`next`、压缩编码的 `seen_expressions_blob` | 通过 `ExperienceMemory` 或维护脚本更新；表达式运行时解压用于精确去重 |
| 记忆：墓碑 | `garbage.json` | 被遗忘、过期或淘汰条目的可恢复记录 | 只软删除；不与经验库混写 |
| 原始证据 | `trajectory.jsonl` | append-only 实验事件，最完整的历史事实源 | 只追加；禁止排序、压缩或覆盖 |
| 执行恢复 | `round_*.checkpoint.json`、`run.lock`（POSIX 另有 OS guard） | 提交状态、progress URL、锁和崩溃恢复依据 | OS owner 存活或存在未完成 checkpoint 时禁止新轮和移动 |
| 当前工作项 | `suggestions.json`、`proposals.json` | 当前 discovery 证据包与待执行提案；长时工厂复用同一 inbox | 只由规定流程生成/审阅；逻辑内容不变不重写 |
| 工厂控制面 | `factory_session.json` | 单个长时 session 的 deadline、预算、最近动作和 `stop_requested` | 固定单文件；`--factory-status` 只读，`--factory-stop` 原子请求安全停止；不按轮次复制 session/log |
| 展示缓存 | `sims_results.json`、`reconcile_report.json`、`recovered_candidates.json` | 可重建的结果、对账和分析输出 | 不覆盖 checkpoint 或 trajectory |
| 发现与证据侧车 | `fields_cache.json`、`evidence_cache.json`、`platform_field_catalog_YYYYMMDD/` | 字段目录、平台证据缓存与字段快照 | 日期目录不可覆盖；优先最新完整 manifest |
| 平台审计快照 | `active_alphas_YYYYMMDD.json`、`new_active_details_YYYYMMDD.json` | ACTIVE Alpha 辅助 provenance | 只作审计背景；平台当前响应优先 |
| 隔离区 | `quarantine/` | 明确隔离的异常、备份或不可直接使用材料；例如 `quarantine/submission_pool_history/`、`quarantine/duplicate_round_summaries/` | 不得自动回流生产链 |
| 当前轮次摘要 | `.wqb_state/round_N.json` | 最近轮次摘要 | 根目录只保留最近 10 个；历史摘要归档到 `docs/archive/rounds/` |
| 历史轮次 | `docs/archive/rounds/round_N.json` | 已完成轮次摘要 | 保持十进制编号；由 `scripts/archive_completed_rounds.py` 归档 |
| 历史 checkpoint | `docs/archive/checkpoints/round_N.checkpoint.json` | 已完成 checkpoint 的审计副本 | 仅归档 `complete=true`；未完成任务必须留在 `.wqb_state/` |

## 记忆阅读顺序

1. `context.md`：快速了解当前结论、`avoid`、`next` 和未完成任务。
2. `experience.json`：核对短期经验、长期 lessons、候选谱系和已见表达式。
3. `garbage.json`：仅在判断某机制是否已淘汰、是否可恢复时查阅。
4. `trajectory.jsonl`：对关键结论做原始实验回溯；按关键词定位，不整读大文件。`trajectory_window` 仅保留内存近期窗口（默认 512），旧 parent 由 `Trajectory` 流式查找，完整原始证据仍只保存在该 JSONL 文件。
5. checkpoint 与 evidence cache：恢复任务或补齐平台后处理时查阅。

## 冲突仲裁与整理边界

- 未完成传输状态以 checkpoint 为准；已确认实验事实以 trajectory 为准；展示结果以可重建缓存为准。
- `context.md` 与 `experience.json` 是压缩决策视图，不得反向覆盖原始证据。
- `SELF_CORRELATION` 缺失、`PENDING` 或未完成时只能标记 `RECONCILE`，不得升级为 `PROMOTE`。
- 任何历史状态快照、`quarantine/` 内容和本地字段目录都不能冒充当前 BRAIN API 响应。
- 允许新增审计说明或外部报告；禁止手工移动/重命名 canonical 文件、删除运行锁、覆盖状态文件，或把备份直接放回生产路径。
- 需要归档的历史材料移至 `docs/archive/`，按 `docs/FILE_ORGANIZATION_AND_NAMING.md` 分类；不要在 `.wqb_state` 内复制一份“整理版”状态。
- 非 canonical 的状态备份可移入已有 `quarantine/<category>/` 子目录；保留原文件名和内容，并在本文件或审计记录中说明来源。
- 轮次归档使用 `python scripts/archive_completed_rounds.py` 先 dry-run，再经确认加 `--apply`；默认保留最近 10 个摘要。
