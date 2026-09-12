# 文档导航

先读根目录 [`AGENTS.md`](../AGENTS.md)、[`ARCHITECTURE_AGENT.md`](ARCHITECTURE_AGENT.md) 和 [`wqb_agent/research_api.py`](../wqb_agent/research_api.py)。不要默认递归阅读全部文档。

| 要回答的问题 | 阅读 |
|---|---|
| Agent 如何理解项目和事实层级？ | [`ARCHITECTURE_AGENT.md`](ARCHITECTURE_AGENT.md) |
| BRAIN API、Retry-After、能力状态和未知结果如何处理？ | [`BRAIN_PROTOCOL.md`](BRAIN_PROTOCOL.md) |
| 如何设计可反证实验、记录 trial 并解释证据？ | [`RESEARCH_POLICY.md`](RESEARCH_POLICY.md) |
| 当前测试规则、增量验证和 CI 质量门是什么？ | [`TESTING.md`](TESTING.md) |
| 公共和本地文件如何划分？ | [`PRIVACY.md`](PRIVACY.md) |
| 算子、字段类型和设置有哪些平台参考？ | [`reference/OPERATORS_CHEATSHEET.md`](reference/OPERATORS_CHEATSHEET.md)、[`reference/SIMULATION_SETTINGS.md`](reference/SIMULATION_SETTINGS.md)（REFERENCE） |
| 如何恢复或审计本地研究状态？ | [`STATE_LAYOUT.md`](STATE_LAYOUT.md)（按需） |

## 参考文档

`reference/OPERATORS_CHEATSHEET.md` 可能被运行时读取和校验 hash，因此即使不属于默认阅读路径也要保留。`reference/SIMULATION_SETTINGS.md` 是平台设置参考。其他研究路线、文件命名和工具纪律文档只有在当前任务需要时阅读。

历史 phase、计划、报告和 round summary 不属于当前 policy；Git history 承担历史存档职责。
