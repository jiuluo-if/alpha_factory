# 结构化 CLI 子命令设计

## 目标

将 `main.py` 的顶层 boolean flags 收敛为标准库 `argparse` 的结构化子命令，并让新语法与有限 legacy 语法最终进入同一个 canonical command representation 和同一套运行时 dispatch。

## Canonical grammar

```text
python main.py [--config PATH] [--state-dir PATH] suggest
python main.py [--config PATH] [--state-dir PATH] run-proposals [PATH] [--force-new-round]
python main.py [--config PATH] [--state-dir PATH] factory run [--hours HOURS]
python main.py [--config PATH] [--state-dir PATH] factory stop
python main.py [--config PATH] [--state-dir PATH] factory status
python main.py [--config PATH] [--state-dir PATH] state doctor [--offline]
python main.py [--config PATH] [--state-dir PATH] state audit [--offline]
python main.py [--config PATH] [--state-dir PATH] state preflight [--offline]
python main.py [--config PATH] [--state-dir PATH] context [--compact] [--json] [--task TASK] [--offline]
python main.py [--config PATH] [--state-dir PATH] smoke
python main.py [--config PATH] [--state-dir PATH] alpha sync-colors [--dry-run]
python main.py [--config PATH] [--state-dir PATH] alpha sync-feed
python main.py [--config PATH] [--state-dir PATH] recovery skip-stale ROUND SIMULATION_ID
python main.py [--config PATH] [--state-dir PATH] recovery skip-submit-unknown ROUND PROPOSAL_ID
python main.py [--config PATH] [--state-dir PATH] recovery finalize-round ROUND
```

`--config` 和 `--state-dir` 的 canonical 位置是 command 前。`--offline` 仅作为只读 legacy 兼容 no-op 保留在本地诊断/context parser 中；新命令的这些动作本身已经是只读语义。

## Canonical representation

`wqb_agent.cli.CLICommand` 使用 `domain`、`action` 加 typed command-specific fields 表示命令。`parse_cli()` 先检测并转换 legacy flag form，再由 canonical parser 解析；运行时不区分 new/legacy 两条业务路径。

## Legacy compatibility

以下旧形式在有限兼容窗口继续支持：`--suggest`、`--run-proposals [PATH]`、`--factory-run --factory-hours HOURS`、`--factory-stop`、`--factory-status`、`--doctor --offline`、`--audit-state --offline`、`--takeover-preflight --offline`、`--agent-context` 及其 context options、`--smoke-readonly`、`--sync-alpha-colors --dry-run`、`--sync-alpha-feed`、三个 recovery flags。legacy adapter 只在 stderr 输出弃用提示；stdout 的 JSON contract 不被污染。非法旧组合仍以 argparse 退出码 2 拒绝。

## 不变量

- 不修改 `Agent`、`Client`、`Simulator`、`factory_runner`、checkpoint、state schema、quota、research policy 或 typed config boundary。
- doctor/audit/preflight/context/factory stop/status 在 client import/构造前结束。
- suggest 不获取 Simulation owner lock；run-proposals、factory run、sync-colors 和 recovery 保留当前 lock scope。
- Simulation POST、`SUBMIT_UNKNOWN` exactly-once、known progress URL recovery 和 retry 逻辑不变。
- audit/preflight semantic block 返回 2；配置、用户输入和 runtime failure（包括 smoke 的凭据/网络不可用）返回 1；正常完成返回 0。Smoke 仍保留 `status=UNAVAILABLE` JSON contract。
