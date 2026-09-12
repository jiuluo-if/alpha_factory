# Testing

## Principles

测试验证当前可观察行为和安全不变量。日常维护优先快速、可定位的增量反馈；CI 是完整仓库回归和覆盖率的 authoritative gate。

## Local Fast Lane

审查 diff 后，识别直接受影响的 behavior，运行 1–5 个相关 test method/class 和一个最近邻 regression；对 changed Python files 运行 `py_compile` 和 Ruff。只有 typed frontier 被改动时才运行对应 mypy。普通本地修改默认不跑 whole suite。

## Progressive Expansion

失败或涉及多个 owner、shared helper、proposal/schema、state merge semantics 或 safety contract 时，依次扩大到 nearby subsystem，再到相关 module/contract suite。改动 safety contract 必须有对应行为测试；这仍不是默认 whole-repository regression。

## CI Full Gate

GitHub CI 使用 Python 3.11，执行 whole-tree syntax、typed frontier mypy、full Ruff、offline doctor、offline state audit、privacy，以及 coverage 驱动的完整测试。完整测试只执行一次：

```powershell
coverage erase
coverage run --branch -m unittest discover -s tests
coverage report
```

coverage execution 同时承担 full tests 和 branch coverage；coverage 只统计 `wqb_agent`，阈值由 `pyproject.toml` 的 `fail_under` 控制。

## Typed Frontier

typed frontier 是配置、运行时装配、凭据、Suggestion/Alpha Feed/Optimizer/Alpha Color 的九个模块。未触碰这些文件时，`MYPY = NOT_REQUIRED`；不扩大 mypy strict scope。

## Coverage

覆盖率用于 CI authoritative gate，不应在本地为普通文档或小范围维护重复运行全量测试。安全关键 production 模块不得通过 omit 排除。

## Slow / Benchmark Tests

pytest、pytest-xdist 和 benchmark 工具可用于开发或性能实验。pytest targeted selection（如 `pytest path/to/test.py::TestClass::test_method`、`pytest -k ...`）允许用于局部验证；whole-suite pytest 不属于默认本地流程。testmon 未作为本轮依赖采用。

## Adding Tests

新增测试应覆盖当前 behavior/contract，并放在最近的职责边界；优先复用既有 helper，避免恢复历史单体测试文件或引入第二套 runner 契约。

## Commands

```powershell
# Local fast lane (replace placeholders with actual tests/files)
python -m unittest tests.test_<affected>.<TestClass>.<test_method>
python -m py_compile <changed-python-files>
python -m ruff check <changed-python-files>

# CI full lane
python -m compileall -q wqb_agent scripts tests
python -m mypy wqb_agent/config.py wqb_agent/runtime_policy.py wqb_agent/runtime_components.py wqb_agent/runtime_composition.py wqb_agent/credentials.py wqb_agent/suggestion_workflow.py wqb_agent/alpha_feed_workflow.py wqb_agent/optimizer_workflow.py wqb_agent/alpha_color_workflow.py
python -m ruff check .
coverage erase
coverage run --branch -m unittest discover -s tests
coverage report
python main.py --state-dir tests/fixtures state doctor
python main.py --state-dir tests/fixtures state audit
python scripts/check_repo_privacy.py
```
