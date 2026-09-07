# Phase 8 发布验收记录

本文件是 Phase 8 的本地发布证据索引，不是 BRAIN 实时状态源。证据快照：2026-09-08；所有状态字段均以当前代码和命令输出为准。

## 验收矩阵

| 验收项 | 当前证据 | 状态与边界 |
|---|---|---|
| 配置解析与预算 | `wqb_agent.config.parse_config`、`tests/test_phase8_release.py` | 已覆盖；搜索与验证预算不得超过工厂上限 |
| 增量价值策略 | `wqb_agent.incremental_policy`、`wqb_agent.incremental_value` | 已覆盖 `advisory`、`required_when_available`、`required` 三种模式；无实证 PnL 时只记 `UNAVAILABLE` |
| 行为序列与 as-of 池 | `wqb_agent.behavior`、`wqb_agent.alpha_pool` | 只接受 `LIVE_VERIFIED` 行为证据；缺少进入时间的历史候选不进入历史池 |
| 结算与奖励证据 | `wqb_agent.agent`、`wqb_agent.search_outcome`、`wqb_agent.trial_ledger` | 最终证据优先于临时/旧奖励；语义相同的结算幂等 |
| 持久化 schema | `wqb_agent.schema` 及各写入器 | 新写入带版本与来源；读取侧兼容旧格式，不回写真实状态 |
| 状态诊断 | `python main.py --doctor --config config.example.json --state-dir .wqb_state` | 只读、无网络；会如实报告未完成 checkpoint、`SUBMIT_UNKNOWN`、ledger 缺失和能力未知 |
| 状态审计 | `python main.py --audit-state --config config.example.json --state-dir tests/fixtures` | 只读；检查生命周期、重复结算、孤儿验证、预算占用和提交池引用 |
| checkpoint/ledger 对账 | `wqb_agent.audit.audit_state` | 终态 checkpoint 必须有对应 `simulation_settled` ledger 事实，否则报告 `checkpoint_ledger_mismatch` |
| 只读烟测 | `python main.py --smoke-readonly --config config.example.json` | 仅读取 datasets/datafields；不执行 Simulation、提交或状态写入 |
| 生产入口 | 根目录 `AGENTS.md` 约束与 `main.py` | 生产仍只能走 `--suggest` → canonical proposals → `--run-proposals` |
| 提交安全 | `wqb_agent.submission`、架构静态测试 | 只生成 `MANUAL_REQUIRED` 候选；代码不自动提交 Alpha |
| 网络依赖隔离 | `test_doctor_and_audit_are_network_free` | 诊断与审计在 HTTP Session 被禁止时仍可执行 |
| 离线 CLI | `python main.py --doctor --offline`、`python main.py --audit-state --offline` | `--offline` 只允许用于只读诊断/审计，并在入口拒绝与生产或 smoke 混用 |
| 安装与 CI | `pyproject.toml`、`.github/workflows/ci.yml` | 使用包安装、编译、单元测试、离线诊断/审计；CI 不执行烟测 |
| 性能边界 | `TrialLedger.summarize_cached`、只读长跑探针 | 已提供可重建摘要缓存；未发现经证实的热点前不做猜测性优化 |
| 配置类型 | `wqb_agent.config.ResearchAllocation` | 角色分配与搜索预算、工厂硬上限分层表达，解析仍只发生一次 |

## 当前真实状态说明

真实 `.wqb_state` 只做过只读检查，不能把诊断中的未知或未完成状态写成发布成功：当前快照仍报告 1 个未完成/未决 checkpoint、17 个 `SUBMIT_UNKNOWN`，且 PnL 与增量能力为 `UNAVAILABLE`。这些是需要后续对账的研究运行状态，不通过本次代码发布自动清理。

## 发布复核命令

```powershell
python -m unittest discover -s tests -q
python -m compileall -q wqb_agent scripts tests
python -m pip install . --no-deps
python main.py --doctor --config config.example.json --state-dir .wqb_state
python main.py --audit-state --config config.example.json --state-dir tests/fixtures
git diff --check
```

命令中的真实状态检查必须保持只读；不得用它们绕过 checkpoint、生产锁、对账或人工提交边界。
