# 文档索引

`docs/` 根目录只保留当前运行需要的规则与参考；当前结论、轮次和候选状态以 `.wqb_state/` 为准。

| 文档 | 用途 |
|---|---|
| `EXPLORATION_ROADMAP.md` | 长期研究空间、选择规则与关闭条件 |
| `OPERATORS_CHEATSHEET.md` | 算子签名与类型审计依据 |
| `SIMULATION_SETTINGS.md` | 可调设置与单变量纪律 |
| `STATE_LAYOUT.md` | 状态文件分类、读取顺序与恢复边界 |
| `DSH_TOOL_DISCIPLINE.md` | 本环境工具调用约束 |
| `FILE_ORGANIZATION_AND_NAMING.md` | 文件职责与归档规则 |

`docs/archive/` 当前为空；后续仅在用户明确要求保留审计材料时使用，且不能替代 BRAIN API 或 `.wqb_state/` 当前状态。

根目录 [README.md](../README.md) 提供安装与两阶段入口；[AGENTS.md](../AGENTS.md) 是唯一执行契约。
