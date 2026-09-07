# WQB Alpha 研究 Agent

面向 WorldQuant BRAIN 的状态驱动 Alpha 工厂。单轮保持严格预算和证据闭环，
也支持最长一整天的 AI 接管运行；唯一目标是用真实 Simulation 获得健康、稳定、
低相关的候选，不把字段猜测、单次高分或文档快照当作平台事实。

## 生产入口

每次研究先读 [AGENTS.md](AGENTS.md)，再按两阶段流程执行：

```powershell
python main.py --suggest
# 审阅 .wqb_state/suggestions.json、context.md、experience.json
python main.py --run-proposals
```

`--suggest` 只做研究空间、数据集和真实字段 discovery，不消耗 Simulation。`--run-proposals` 是唯一允许提交 Simulation 的入口；它执行字段、类型、算子、谱系、去重、预算与 checkpoint 预检。

长时运行使用：

```powershell
python main.py --factory-run
# 运行中查看状态或请求在安全边界停止（均不需要 BRAIN 凭据）
python main.py --factory-status
python main.py --factory-stop
```

工厂默认最多运行 86400 秒、最多预留 240 个 Simulation，恢复未完成 checkpoint 优先；它仍通过同一个
`Agent.run_proposals()` 提交，不旁路生产状态机；结束时只输出一份紧凑会话摘要。`factory_session.json`、
`suggestions.json` 和 `proposals.json` 都是固定 canonical 文件，逻辑内容不变
时不会重复写入。工厂内部调用默认静默，避免把每个轮次的诊断输出变成长时重复报告；需要排障时可直接使用
`--factory-status` 和现有 checkpoint/trajectory 证据。

## Alpha 模板工厂

`wqb_agent/alpha_factory.py` 提供初步的 template-first 候选工厂：先选择可审计的表达式骨架，再用 discovery 字段填充 `p`/`s`/`g` 槽位。工厂只生成候选，不访问 BRAIN、不写 `.wqb_state`、不提交 Simulation；候选会携带 `template_id`、`template_family`、结构指纹、槽位和阶段路径，随后仍必须经过 `proposals.json` 的完整生产预检。

同一批同一 `template_family` 最多保留 2 个候选；若工厂在预算预留后、checkpoint 写入前退出，会优先恢复同一 session 的 canonical proposals，无法证明提交状态时停在 `RECONCILE_REQUIRED`。

AI 可在 hypothesis 中显式指定 `template_ids`、`template_family` 或 `template_ref` 进入模板模式；未指定时保留旧候选生成兼容路径。`wqb_agent/research_guard.py` 会对已完成且有分数的历史实验做只读结构审计：同一谱系同一变更类别连续无实质增益时，阻断该类别并提示切换变量；`UNKNOWN`、超时和基础设施失败不会被当作研究结论。

## 安全边界

- BRAIN API 是字段、Simulation、指标、checks 与 Alpha 状态的唯一实时事实源。
- `.wqb_state/` 是本地运行状态；不要手改、移动或删除其中的 checkpoint、trajectory、lock 与缓存。
- 预算、并发与质量门只从 `config.json` 读取。
- 可调设置仅为 `universe`、`truncation`、`decay`，且一次只能改变一个。
- `SUBMIT_UNKNOWN` 只能只读对账，绝不自动重复 POST；Alpha 提交始终由用户在 BRAIN 手工完成。

## 安装与配置

```powershell
pip install -r requirements.txt
```

复制 `config.example.json` 为本地 `config.json` 后配置。凭据可来自 `WQB_USERNAME` / `WQB_PASSWORD` 环境变量、`~/.brain_credentials.txt` 或根目录 `.env`；不要提交凭据。

## Proposal 要点

proposal 必须使用 discovery 已证实的字段，并记录：`fields`、`datasets`、`field_understanding`、`field_analysis`、`field_source`、`field_hypothesis_basis`、`operator_mapping`、`operator_evidence`、`experiment_question`、`expected_failure_modes`、`tuning_risk`、`experiment_stage` 与 `research_role`。

`BASELINE` 是最小机制；`CHILD` 和 `ROBUSTNESS` 必须指向已完成 parent，且只能有一个 `change_type`。VECTOR 字段须先经可核验的 `vec_avg` 或 `vec_sum` 聚合，才可进入后续算子。

每个 DONE 结果必须结合 Sharpe、Fitness、Turnover、Returns、Drawdown、Margin、全部 checks、健康数据与 SELF_CORRELATION 判读。`PROMISING` 不等于可提交；只有稳定、健康且相关性通过的候选才可进入人工审核池。

## 状态与文档

| 位置 | 用途 |
|---|---|
| `.wqb_state/context.md` | 当前压缩决策视图，研究前先读 |
| `.wqb_state/experience.json` | 经验、avoid、next 与谱系记忆 |
| `.wqb_state/trajectory.jsonl` | append-only 实验证据 |
| `.wqb_state/round_*.checkpoint.json` | exactly-once 提交与恢复依据 |
| [docs/EXPLORATION_ROADMAP.md](docs/EXPLORATION_ROADMAP.md) | 长期研究空间与选择规则 |
| [docs/OPERATORS_CHEATSHEET.md](docs/OPERATORS_CHEATSHEET.md) | 算子签名与类型依据 |
| [docs/SIMULATION_SETTINGS.md](docs/SIMULATION_SETTINGS.md) | 设置白名单与纪律 |
| [docs/STATE_LAYOUT.md](docs/STATE_LAYOUT.md) | 状态读取、仲裁与归档边界 |
| [docs/README.md](docs/README.md) | 文档索引与历史归档说明 |

验证改动：

```powershell
python -m unittest discover -s tests
```
