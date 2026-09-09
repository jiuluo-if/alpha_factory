# 渐进式工程质量门设计

## 目标

建立可持续、渐进式的工程质量底线：coverage 回归、typed frontier 类型回归和低风险 lint 回归都能真实阻断 CI，同时保持现有研究、认证、Simulation、恢复、credentials、Alpha Feed/Color 与研究政策语义不变。

## 设计决策

- Coverage 只统计 `wqb_agent` production package，开启 branch coverage，不通过 omit 低覆盖安全模块抬高数字。
- 以 2026-09-09 配置生效后的实测 production 基线为依据：statement `79.99%`、branch `68.31%`、branch-aware 综合 `76.74%`；`source=["wqb_agent"]` 会纳入未被测试导入的 `validation.py`，初始 `fail_under=76.0`。
- Mypy 采用单一工具，Python 3.11；第一阶段显式检查 9 个边界清晰模块，使用基础告警选项和 `follow_imports=skip`，不启用全仓 strict，不检查 tests 作为 typed target。
- Ruff 启用 import sorting 和已测得的低风险 UP 子规则；Bugbear 仅启用 `B007`、`B904`。跳过可能改变 Enum 表现或异常/zip 语义的规则。
- 类型与 lint 修复只做局部、可证明不改变 runtime 的修改；若发现真实 bug，必须先补行为回归测试再修复。
- CI 保持 Python 3.11 单矩阵，顺序为 install → compile → type → unit → Ruff → branch coverage → doctor → audit。

## Typed frontier

第一阶段检查：

`wqb_agent/config.py`、`wqb_agent/runtime_policy.py`、`wqb_agent/runtime_components.py`、`wqb_agent/runtime_composition.py`、`wqb_agent/credentials.py`、`wqb_agent/suggestion_workflow.py`、`wqb_agent/alpha_feed_workflow.py`、`wqb_agent/optimizer_workflow.py`、`wqb_agent/alpha_color_workflow.py`。

全局 mypy 保持非 strict，仅使用 `check_untyped_defs`、`no_implicit_optional`、`warn_unused_configs`、`warn_redundant_casts`、`warn_unused_ignores` 和 `follow_imports=skip`。`agent.py`、`client.py`、`simulator.py`、`proposal_execution.py` 不因本阶段质量门而大范围注解或重构。

## Ruff frontier

启用：`E4`、`E7`、`E9`、`F`、`I`、`UP009`、`UP012`、`UP017`、`UP031`、`UP035`、`UP037`、`B007`、`B904`。

暂不启用：`UP042`、`B025`、`B905`、`SIM`、`RUF`。原因是当前发现的规则涉及 `str/Enum` runtime 表现、不可达恢复分支、`zip` 长度语义或尚未完成安全成本评估。

## 验证与回归

本地和 CI 使用同一组核心命令：

```text
python -m compileall -q wqb_agent scripts tests
python -m mypy wqb_agent/config.py wqb_agent/runtime_policy.py wqb_agent/runtime_components.py wqb_agent/runtime_composition.py wqb_agent/credentials.py wqb_agent/suggestion_workflow.py wqb_agent/alpha_feed_workflow.py wqb_agent/optimizer_workflow.py wqb_agent/alpha_color_workflow.py
python -m unittest discover -s tests
python -m ruff check .
coverage erase
coverage run --branch -m unittest discover -s tests
coverage report
python main.py --state-dir tests/fixtures state doctor
python main.py --state-dir tests/fixtures state audit
python main.py context --compact --json
git diff --check
```

不执行 live BRAIN authentication、Simulation POST 或 Alpha submission；不修改 `.wqb_state/` 与 `.alpha_feed_cache/` 中真实研究状态。
