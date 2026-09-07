# Alpha Factory

Alpha Factory 是一个面向 AI Agents 的 WorldQuant BRAIN Alpha 研究工程：使用真实的 fields、operators 和 Simulation，Agent 负责研究判断，Python 负责执行、证据、恢复与安全。

## 核心研究循环

```text
观察 → 发现 → 假设 → 实验 → 评估 → 记录 → 迭代
```

最短阅读路径：`README.md` → `AGENTS.md` → `wqb_agent/research_api.py`；需要时再读 [`docs/ARCHITECTURE_AGENT.md`](docs/ARCHITECTURE_AGENT.md)。

## 快速开始

安装依赖并复制配置：

```powershell
pip install -r requirements.txt
Copy-Item config.example.json config.json
```

只读地发现平台字段：

```powershell
python main.py --suggest
```

Agent 评估并写好 `.wqb_state/proposals.json` 后，使用当前唯一受保护的 Simulation 路径：

```powershell
python main.py --run-proposals
```

也可以直接使用 `wqb_agent.research_api` 的 `inspect_state`、`discover_fields`、`run_experiment`、`get_experiment`、`compare_experiments`、`search_history` 和 `reconcile`。特殊诊断命令见 `docs/README.md`，不属于默认研究循环。

## 安全边界

- BRAIN live response 是 datasets、fields、operators、Simulation、metrics 和 checks 的实时事实源；cache、报告和 fixture 不是事实源。
- 字段和算子必须真实验证；设置、schema、去重和硬预算必须在执行前检查。
- 已知 progress URL 只允许只读轮询；远程写结果未知时保持 `SUBMIT_UNKNOWN`，禁止盲目重 POST。
- checkpoint 是恢复边界；缺失或模糊证据保持 `UNKNOWN` / `UNAVAILABLE`，不得伪装成 `PASS`。
- Alpha submission 始终由用户在 BRAIN 中手工完成。

## 项目结构

```text
wqb_agent/research_api.py  # Agent-facing facade
wqb_agent/                 # BRAIN、执行、状态和评估实现
main.py                    # 兼容 CLI 与安全入口
docs/                      # 当前协议、研究政策与少量参考
tests/                     # 核心安全不变量和可观察行为
```

## 文档入口

- [`AGENTS.md`](AGENTS.md)：coding/research agent 的最高优先级说明
- [`docs/ARCHITECTURE_AGENT.md`](docs/ARCHITECTURE_AGENT.md)：概念、事实层级和调用边界
- [`docs/BRAIN_PROTOCOL.md`](docs/BRAIN_PROTOCOL.md)：BRAIN 协议、Retry-After 和 capability
- [`docs/RESEARCH_POLICY.md`](docs/RESEARCH_POLICY.md)：假设、反证、稳健性和统计纪律

算子与设置参考文档若被运行时需要，会在 `docs/README.md` 中标为 `REFERENCE`，不作为默认 mental model。

## 测试

```powershell
python -m unittest discover -s tests
python -m compileall -q wqb_agent scripts tests
```
