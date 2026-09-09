# Alpha Color 远端写工作流设计

## 背景

颜色分类是已有 Experiment 证据的派生视图；远端 Alpha `color` 是显式维护动作。当前两者和 CLI 编排混在 `alpha_colors.py`，导致纯领域模块拥有远端写路径。

## 方案

新增 `AlphaColorWorkflow` 作为独立 CLI control/write workflow。它只接收窄 operation-shaped hooks：远端 `get_alpha`、远端 `set_alpha_color`，以及分类函数；核心 `sync(experiments, *, dry_run=False)` 不知道 `state_dir`、trajectory、Agent 或四个 AgentWorkflows。

`alpha_colors.py` 只保留颜色常量、证据 predicate/classifier、轻量 evidence summary 和 `load_color_candidates`。颜色同步统一由 `AlphaColorWorkflow.sync()` 负责，旧的转发入口已移除；CLI 直接构造 workflow 并委托，不保留第二个实现。

`main.py` 继续拥有 CLI 控制面：取得 `sync-alpha-colors` 单实例锁、lazy 构造 `WQBClient`、加载候选、调用 workflow、输出既有 JSON schema、处理异常和 exit code。workflow 的唯一远端写 hook 是 `set_alpha_color(alpha_id, desired, verify=True)`。

## Ownership 与安全语义

当前没有持久 ownership source；`PROJECT_COLOR_OWNER`/`color_managed_by` 仅存在于旧循环的进程内检查，且当前代码没有写入 ownership evidence。因此不引入 sidecar，也不假装具有跨进程 ownership。若远端已有非空颜色且目标不同，无法证明项目拥有它，则返回 `OWNERSHIP_CONFLICT`、不 PATCH。目标与旧颜色相同则 `NOOP`。目标为 `None` 时，无 ownership 证据直接跳过；若未来显式传入可证明的项目 ownership，才允许清除，但本阶段不制造该证据。

## 验证契约

- 分类 characterization：PURPLE/GREEN/RED/BLUE/YELLOW/None、优先级和 `has_research_signal` 保持。
- workflow：no candidate 0/0；same 1/0；dry-run change 1/0；conflict 1/0；authorized change 1/1；readback mismatch 1/1 then fail。
- 架构 guard：`alpha_colors.py` 不依赖 client/Agent/Simulator；workflow 不依赖 Agent/Simulator/proposal execution 且无 raw requests write；main 不复制分类规则。
- 不运行 live `alpha sync-colors`。
