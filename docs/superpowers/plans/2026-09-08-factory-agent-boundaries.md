# 工厂批量题案与 Agent 优化边界实施计划

> 目标：把工厂固定为每批 100 个题案，把 Agent 收敛为优化/模板改进角色，按美国东部本地日只保留内存缓存，并只以 checkpoint 作为运行恢复边界。

## 任务 1：建立失败测试与日缓存边界

**文件：** `tests/test_daily_cache.py`、`wqb_agent/daily_cache.py`

- 写纽约时区边界、日期切桶、跨日清理和内存-only 行为测试。
- 写缓存只接受可序列化的轻量 list/dict，且没有文件写 API 的测试。
- 先运行目标测试确认失败。
- 实现注入 clock 的 `DailyResearchCache`，提供 simulations/submitted-alphas/color-results 三类缓存和只读快照。

## 任务 2：明确工厂与 Agent 角色并固定 100 题案

**文件：** `wqb_agent/alpha_factory.py`、`wqb_agent/factory_runner.py`、`wqb_agent/agent.py`、`wqb_agent/proposal_contract.py`、相关测试

- 为工厂增加固定批量目标、来源字段和返回 `list[dict]` 的批量入口。
- 把优化生成移到 Agent-facing 方法；工厂只消费优化结果并负责批量填充/排序。
- 添加整批 100 个唯一且预检通过的 gate，失败时不调用执行入口。
- 删除/禁用普通 Agent 路径对工厂批量生成的隐式兜底。

## 任务 3：加强抗过拟合与颜色检测

**文件：** `wqb_agent/research_guard.py`、`wqb_agent/proposal_contract.py`、`wqb_agent/alpha_colors.py`、相关测试

- 增加结构骨架比较和参数/方向-only 拒绝规则。
- 保证新经济机制、单变量 robustness 和证据字段能通过。
- 颜色默认只读，报告证据冲突/ownership conflict/缺证据，不落盘颜色结果。

## 任务 4：把结果持久化收敛到 checkpoint

**文件：** `wqb_agent/agent.py`、`wqb_agent/runtime_components.py`、`wqb_agent/checkpoints.py`、`wqb_agent/context.py`、配置和文档

- Agent 运行时使用内存 trajectory/ledger 适配层，仅 checkpoint 可落盘。
- `_write_sims_results`、提交候选和颜色 evidence 改写入日缓存或直接报告，不写本地结果文件。
- 不再生成 `round_N.json`；完成 checkpoint 仅保存最小恢复索引，未完成 checkpoint 保留远程恢复字段。
- 更新状态布局和命令帮助，明确历史结果不在本地留存。

## 任务 5：分层验证与收尾审查

- 运行新增目标测试、现有全量单元测试、`compileall`、`ruff`。
- 用临时状态目录验证文件白名单、100 题案 gate、checkpoint 恢复和颜色只读行为。
- 使用代码审查技能检查安全边界和是否存在第二条 Simulation 路径。
- 最后再次确认没有生成 `.wqb_state` 外的缓存/构建物，未提交、未推送。
