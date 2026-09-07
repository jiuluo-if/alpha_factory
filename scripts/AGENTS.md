# `scripts/` 局部规则

脚本只能是只读诊断、派生视图重建、对账辅助或明确设有保护的归档工具，不得形成第二套研究 API 或 Simulation 提交路径。

- 使用公开的 client、evidence 和 metrics 接口，不调用私有 session。
- 对账只轮询已知 progress URL，未知写结果绝不重 POST。
- 报告、cache 和 export 都是派生物，不是事实源；大型 JSONL 必须流式、有界读取。
- 归档必须先 dry-run，检查锁与 checkpoint，并在 `--apply` 前获得用户确认。
- 代码变更运行根目录测试和 compile 命令；不得手改 live `.wqb_state`。
