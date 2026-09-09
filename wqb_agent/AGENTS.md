# `wqb_agent/` 局部规则

先读根 `AGENTS.md`、`docs/ARCHITECTURE_AGENT.md` 和 `research_api.py`。其他模块是 facade 所组合的现有运行时能力。

## 职责

- `client.py`、`discovery.py`、`simulator.py`、`state.py`、`proposal_contract.py` 是核心机制边界。
- `metrics.py`、`expression.py`、`artifacts.py`、`locking.py` 和 failure helpers 是共享安全/序列化原语。
- `search*`、`validation*`、`robustness.py`、`incremental_value.py`、`memory.py`、`submission.py` 是内部评估或 workspace 视图。
- `factory_runner.py` 是兼容/legacy control plane，不是默认 Agent mental model。

领域模块不得导入 `Agent` 或创建另一条执行/状态路径；BRAIN 事实留在 client/discovery 边界，纯评估函数不得产生网络写入。

## 不变量

- `Agent.run_proposals()` 仍是受保护的 Simulation 路径。
- POST 前持久化 identity/checkpoint；写结果含糊时只轮询或对账同一 job，绝不重复 POST。Simulation 结果与 Alpha 证据不落盘；远端 Alpha 仅以轻量 ID/状态/时间戳按滚动 7 日写入 `.alpha_feed_cache/weekly.json`。
- 保留 Retry-After、锁、预算、schema、expression dedup 和 `UNKNOWN` / `UNAVAILABLE`。
- 远端 Alpha 轻量元数据写入 `.alpha_feed_cache/weekly.json`：每 3 小时与提交 Alpha 同批刷新，按纽约本地日分桶，仅保留当前工作日前推 7 个自然日和 `11200（7*1600）` 条模拟元数据上限；每次刷新清理滚动窗口外和超时临时资源，并保留 `updated_at`/`expires_at`。不得写入指标、表达式、trajectory 或证据。
- Alpha submission 始终手工完成。

研究空间轮换、搜索分配和候选优先级属于 `RESEARCH_POLICY`，不是 BRAIN 机制。

## 验证

For code changes run:

```powershell
python -m unittest discover -s tests
python -m compileall -q wqb_agent scripts tests
```
