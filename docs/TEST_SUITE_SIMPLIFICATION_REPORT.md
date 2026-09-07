# 测试套件简化报告

## 目标

让测试文件对应稳定边界，保留生产安全不变量和可观察行为，删除只验证历史报告、迁移脚本或已移除实现的重复测试。

## 变更

| 项目 | 处理 |
|---|---|
| `tests/test_agent.py` | 删除 1,938 行单体文件，按职责拆为 discovery、simulator、evaluation、flow、proposal safety、state、submission 7 个文件 |
| `tests/test_optimizations.py` | 删除 2,552 行历史优化/报告/派生脚本测试；对应脚本已不属于当前运行时入口 |
| `test_phase*.py`、`test_phase8_smoke.py` | 改为 `test_evaluation.py`、`test_recovery.py`、`test_search_calibration.py`、`test_incremental_value.py`、`test_runtime_safety.py`、`test_smoke.py` |
| facade 覆盖 | `test_research_api.py` 覆盖轻量 `ExperimentSpec`、字段发现、受保护执行、状态查询、历史查询、已知 URL 对账和算子参考 |
| 架构覆盖 | `test_architecture.py` 改为检查当前保留的维护脚本和唯一 Simulation 写入边界 |

## 结果

- 旧两份单体测试共 267 个测试方法；当前套件共 326 个测试，通过拆分、补充 facade 和修正当前边界后的全量回归。
- 最大测试文件约 917 行，已不存在 `test_agent.py` 或 `test_optimizations.py`。
- 保留的核心不变量包括：唯一受保护 Simulation 路径、checkpoint 恢复、`SUBMIT_UNKNOWN` 对账、proposal fail-closed、事实来源优先级、指标/健康/相关性未知状态和禁止 Alpha 自动提交。

## 验证证据

```text
python -m unittest discover -s tests   -> Ran 326 tests ... OK
python -m compileall -q wqb_agent scripts tests -> OK
git diff --cached --check -> OK
Markdown relative links -> BROKEN_MARKDOWN_LINKS=[]
```

本报告不记录 `.wqb_state/` 的实时实验结果；该目录仍是 live research state，必须按现有恢复和对账规则处理。
