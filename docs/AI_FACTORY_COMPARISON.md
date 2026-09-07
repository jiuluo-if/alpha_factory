# AI 工厂对照与落地边界

本工程的工厂设计对照了 `F:\codex\ai\ai-worker-skill\ai-worker-skill` 下的本地
`wqb-batch-runner`、`wqb-memory-writer`、`wqb-zero-order-field-factory`、
`wqb-robustness-audit` 与顶层 `SKILL.md`。这些文件是方法参考，不是 newwqb
的运行时依赖，也不替代本工程的 `AGENTS.md`。

| 外部方法 | 本工程采用 | 本工程保留的边界 |
|---|---|---|
| session_state、batch fingerprint、预算预留 | `factory_session.json`、固定 `proposals.json`、既有 proposal fingerprint、已见表达式排除和配置化的18/100轮上限 | 不复制 exact-4/multi-simulation 提交链；所有真实 POST 仍走 `Agent.run_proposals()` |
| skeleton/template diversity | `AlphaFactory` 的模板目录、family、stage path、slot 与结构指纹，并限制同族最多 2 个 | 不用模板绕过真实字段 discovery、类型门控、SELF_CORRELATION 或健康检查 |
| memory-writer 的 session 幂等与聚合 | `ExperienceMemory` 的压缩表达式集合、短期/长期/垃圾三层和幂等写入 | trajectory 仍是唯一原始证据；UNKNOWN、INFRA 不进入长期 lesson |
| field factory 的 slot/evidence 追踪 | `assemble_proposals()` 为每个真实字段生成可审计 BASELINE，并逐字保留 description | 不从字段名推断语义，不把模板 rationale 冒充经济事实 |
| robustness / anti-overfit | `ResearchLoopGuard`、lineage、single change_type 与结果后的 validation | 不进行 Field × Operator × Window 穷举，不把一次高分直接提升为 current_best |

提案契约也已从 `agent.py` 提取到 `wqb_agent/proposal_contract.py`。这对应外部方法中“批次先校验、再派发”的边界，但只共享纯校验逻辑；它不读取状态、不调用 BRAIN，因此不会形成第二条生产执行链。

## 文件不膨胀策略

- 工厂控制面只有 `.wqb_state/factory_session.json`；不存在每轮 session 文件、日志副本或临时 proposals 副本。单次 session 同时受时长和 `agent.factory.max_simulations` 预算约束。
- 若进程在预算预留后、checkpoint 写入前退出，只恢复同一 `factory_session_id` 的 canonical `proposals.json`；若执行异常但没有 checkpoint 证据，则停在 `RECONCILE_REQUIRED`，不猜测 POST 是否成功。
- `--factory-stop` 只写入该 canonical session 的 `stop_requested`，`--factory-status` 只读；二者不创建额外控制文件，也不需要 BRAIN 凭据。
- `artifacts.py` 对 JSON/text 做原子、内容比较和唯一临时文件写入；只有逻辑状态变化才替换文件。
- 小型 `stale_skip` / `round_finalization` 审计采用稳定身份幂等追加；`trajectory.jsonl` 仍只由 `Trajectory` API 追加并强制 flush/fsync。
- `experience.json` 中表达式去重集合用压缩字段保存，运行时恢复成精确集合；重要结论仍只保存有限 lesson、avoid、next 与 lineage。
- lineage 只作为最近决策索引并有上限（默认 256 条）；完整实验历史不复制到 memory，仍从 trajectory 回溯。
- 每轮自动生成的临时 hypothesis id（如 `h-next-r…`、`h-iter-r…`、旧纪元 `h-rb…`/`rb…-hypothesis`）在加载和保存时过滤，不把可重建的轮次标识累积成长期记忆。
- `round_*.json` 与已完成 checkpoint 只可由 `scripts/archive_completed_rounds.py` 先 dry-run 后归档；未完成 checkpoint、trajectory 和运行锁不整理。
