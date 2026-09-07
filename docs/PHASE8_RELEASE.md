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
| checkpoint/ledger 对账 | `wqb_agent.audit.audit_state` | 终态 checkpoint 必须有对应 `simulation_settled` ledger 事实；ledger 缺失报告 `ledger_missing`，记录不一致报告 `checkpoint_ledger_mismatch` |
| 只读烟测 | `python main.py --smoke-readonly --config config.example.json` | 仅读取 datasets/datafields；不执行 Simulation、提交或状态写入 |
| 生产入口 | 根目录 `AGENTS.md` 约束与 `main.py` | 生产仍只能走 `--suggest` → canonical proposals → `--run-proposals` |
| 提交安全 | `wqb_agent.submission`、架构静态测试 | 只生成 `MANUAL_REQUIRED` 候选；代码不自动提交 Alpha |
| 网络依赖隔离 | `test_doctor_and_audit_are_network_free` | 诊断与审计在 HTTP Session 被禁止时仍可执行 |
| 离线 CLI | `python main.py --doctor --offline`、`python main.py --audit-state --offline` | `--offline` 只允许用于只读诊断/审计，并在入口拒绝与生产或 smoke 混用 |
| 安装与 CI | `pyproject.toml`、`.github/workflows/ci.yml` | 使用包安装、编译、单元测试、离线诊断/审计；CI 不执行烟测 |
| 性能边界 | `TrialLedger.summarize_cached`、只读长跑探针 | 已提供可重建摘要缓存；未发现经证实的热点前不做猜测性优化 |
| 配置类型 | `wqb_agent.config.ResearchAllocation` | 角色分配与搜索预算、工厂硬上限分层表达，解析仍只发生一次 |

## Release Definition of Done 对照

| 问题 | 直接证据 | 结论 |
|---|---|---|
| 1. 外部 write 有哪些？ | `wqb_agent/client.py`、`wqb_agent/simulator.py`、架构测试 | 仅 Simulation 提交链；Alpha submission 不在生产代码中 |
| 2. 如何避免重复 Simulation POST？ | checkpoint、`SUBMIT_UNKNOWN`、submission fingerprint、`tests/test_architecture.py` | 已有 exactly-once 恢复边界；未知提交先对账，不自动重 POST |
| 3. 当前未决 `SUBMIT_UNKNOWN`？ | `python main.py --doctor --offline --state-dir .wqb_state` | 当前快照为 17 个 |
| 4. SearchPolicy 能否重启恢复？ | `Agent._load_state`、`SearchSnapshot.from_sources`、重启回归测试 | 从 trajectory、ledger、checkpoint 重建；缺失 ledger 时保持未知/降级 |
| 5. STABLE Alpha 的 robustness evidence？ | `ValidationPlan`、`ValidationReport`、`ResearchEvidenceBundle` | 只有验证报告 PASS 才进入 STABLE 语义，不以单次指标替代 |
| 6. incremental evidence 来自哪个 pool snapshot？ | `AlphaPoolSnapshot.snapshot_id`、结算 ledger 引用 | 结算时记录 snapshot id、pool size 与摘要证据 |
| 7. unavailable 为什么 unavailable？ | `extract_behavior_series`、doctor capability | 非 `LIVE_VERIFIED` PnL/return 一律 `UNAVAILABLE/INCONCLUSIVE` |
| 8. pool Alpha 为什么 eligible？ | `submission_eligibility` 的 reasons、`incremental_gate` | 按平台检查、健康、相关性、验证、年度证据和策略逐项判定 |
| 9. 所有 state artifact schema？ | `wqb_agent/schema.py` registry、doctor schema report | 新写入有版本；历史真实 artifact 仍会如实显示 LEGACY |
| 10. 老 schema 如何读取？ | `migrate_artifact` 及 migration tests | 内存迁移、确定性、幂等，不回写旧文件 |
| 11. CI 是否依赖真实 BRAIN？ | CI 三层命令、fixture/network-free tests | 不依赖；smoke 不进入 CI |
| 12. 新环境能否一条命令安装测试？ | `pyproject.toml`、`pip install .`、CI | 已验证 Python >=3.11 安装与测试链 |
| 13. 已知统计近似？ | README Known Limitations、研究政策 | PBO 与有效独立试验数标记为 proxy/approximate |
| 14. 哪些 capability 是 LIVE_VERIFIED？ | protocol truth、doctor、fixture tests | 只有真实验证响应才标 LIVE_VERIFIED；当前 PnL 为 UNAVAILABLE |
| 15. 删除 derived cache 能否重建？ | append-only trajectory/ledger、`summarize_cached` | 摘要缓存可删除重建；当前缺失的历史 TrialLedger 不能被猜测补造 |

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
