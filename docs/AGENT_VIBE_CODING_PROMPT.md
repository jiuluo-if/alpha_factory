# Alpha Factory Agent Vibe Coding Prompt

你接管的是 `F:\\codex\\wqb_alpha_factory`。这是研究仪器，不是让 Agent 自由改写状态的脚本。请在真实 BRAIN 响应、现有测试和检查点约束下完成工作；先读根目录与 `wqb_agent/AGENTS.md`，再读 `research_api.py`、当前目标模块和相关测试。

## 目标

连续运行多轮 Alpha 研究：Agent 只负责提出可证伪的新经济机制、优化方向和解释；Alpha Factory 负责把已核验字段扩展成每轮恰好 100 个可执行题案。每个题案必须是可添加到 `proposals` 的 `list[dict]` 成员，整批先完整预检，通过后才进入 `Agent.run_proposals()`。

## 不可违反的边界

1. Simulation 结果、Alpha 证据、颜色判定、trajectory、trial ledger、experience、context 和 submission pool 只能存在于当前进程内的按 `America/New_York` 本地日分桶缓存；远端 Alpha 的轻量 ID/状态/时间戳例外写入 `.alpha_feed_cache/weekly.json`，按当前工作日前推 7 个自然日保留并定期清理，禁止写结果侧车。
2. 允许持久化的只有当前提案/发现输入、运行锁、单个工厂会话控制面和用于恢复远程任务的最小检查点。检查点只保留 proposal identity、表达式/设置指纹、状态、已知 progress URL、错误与恢复元数据；不得写 metrics、checks、Alpha payload 或结果副本。
3. `SUBMIT_UNKNOWN` 不得重发；已知 progress URL 只能只读轮询/对账。未完成检查点优先恢复，禁止静默开新轮。
4. Alpha 提交始终由用户手工完成。颜色分组只读真实 Alpha 证据，不触发提交。
5. 不把 `-signal`、`reverse(signal)`、窗口/权重/符号扫描或固定多腿参数堆叠伪装成新 Alpha。数值-only 变化只能明确标成 `ROBUSTNESS`，并引用已完成 parent 与验证计划。

6. 字段发现必须在配置的数据集池上做可复现的分层抽样；至少覆盖 `min_datasets`
   个真实数据集，不能先把第一个数据集填满再把剩余数据集当作回退。每轮输入
   暴露 `dataset_selection`：seed、pool、ordered_pool、selected_counts、拒绝原因。

## 字段查重的正确实现

本地不再保存历史 Simulation/Alpha，因此不要从 trajectory、结果文件或旧 submission pool 推断字段是否重复。字段使用量必须来自平台 `/data-fields` 响应的 `alphaCount`（内部可标准化为 `alpha_count`）：

- 命中本地 `fields_cache.json` 或字段目录时，仍对本轮研究数据集做只读平台刷新；平台当前值覆盖本地旧值。
- `alphaCount=0` 是有效值；缺失、非法、非有限或刷新失败必须是 `UNKNOWN/UNAVAILABLE`，严格生产配置下排除，不得当作 0。
- 字段查重键必须是 `(dataset_id, field_id)`；不同数据集允许出现同名字段，禁止用裸 `field_id` 的后写值覆盖前一个数据集。
- 将字段的 `platform_dedupe`、来源、快照时间和排除原因写入当前 discovery/proposal 输入，不能写入模拟结果历史。
- 执行提案前再做一次平台字段使用量核验，避免 agents 产生 proposals 后计数已经变化。
- 不要凭空增加未登记的 Alpha 列表接口；当前字段查重只依赖已登记的 `/data-fields` 平台响应。

## 多字段模板与字段目录

- 字段目录按 `America/New_York` 本地日固化，manifest 与每个数据集字段文件只保存
  字段元数据、查询 scope、抓取时间、哈希和平台 `alphaCount` 状态；禁止写入结果。
- 模板可以使用 `{data_field}` 作为主字段别名，也可以使用 `{p}`、`{s}`、`{t}` 等
  槽位。`{data_field}` 不是字面字段名；`low`、`high`、`close`、`volume` 等只
  是语义示例，必须由当前平台字段真实替换。
- 双字段/三字段候选必须携带 `field_refs=[{"dataset":..., "id":...}]`，并让
  `fields`、`template_slots`、`field_understanding`、`field_analysis` 和
  `field_hypothesis_basis` 与实际槽位一致。相同裸 field id 跨 dataset 时必须
  用 field_refs 消歧，不能后写覆盖前写。
- 需要多字段时优先选不同 dataset 的类型兼容字段；没有真实跨 dataset 证据时，
  不得在批次统计中宣称跨 dataset。工厂批次必须记录模板数、双/多字段数、主数据集
  分布和跨数据集组合数。

## 每轮工作流

```text
读检查点/当前平台状态
  -> 选择研究空间与真实字段
  -> 刷新 alphaCount 并做字段类型/语义校验
  -> Agent 产生少量有证据的优化题案
  -> Factory 组合经济模板，补齐到 list[dict] 恰好 100 个
  -> 整批 schema / 字段 / 算子 / 类型 / 去重 / 经济机制 / 预算预检
  -> 通过后仅调用 Agent.run_proposals()
  -> 只在当日内存中评价 metrics/checks/颜色
  -> 失败、UNKNOWN、颜色和平台响应写入工程问题记录，不伪造 PASS
  -> 只保留最小检查点并进入下一轮
```

## 研究质量要求

每个 BASELINE/CHILD/ROBUSTNESS 都要说明 `economic_mechanism`、方向、方向变换、预期持有期、单一实验问题、失败条件、字段逐字语义、算子证据和 `self_correlation_impact`。缺证据保持 UNKNOWN。高换手、低子宇宙稳定性、异常 Sharpe、SELF_CORRELATION 待定或平台对账缺失都不能升级为成功。

颜色只是证据状态：GREEN/PURPLE/BLUE/YELLOW/RED 必须由真实健康、质量、年度稳定性、自相关和增量证据决定；证据不足不得着色为成功色，也不得把颜色当成 Alpha 提交授权。

## 排错和交付

- 先记录现象、复现、边界输入、数据流和最近改动，再写失败测试；禁止猜测式反复修补。
- 真实运行中记录：轮次检查点状态、`DONE/FAILED/PENDING/RUNNING/SUBMIT_UNKNOWN`、预算、平台刷新状态、字段排除数、整批阻断原因、颜色证据缺口和未验证项。
- 不删除未完成检查点、不手改 `.wqb_state`，不提交或推送 Git。
- 修改后运行：

```powershell
python -m unittest discover -s tests
python -m compileall -q wqb_agent scripts tests
python -m ruff check .
```

最终输出必须包含：实际证据、根因、改动文件、测试结果、仍在运行或未验证的状态，以及下一位 Agent 可直接执行的最小动作。禁止把本地缓存命中、模拟提交成功或 Alpha 颜色推断写成平台事实。
