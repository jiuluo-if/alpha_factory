# 工厂批量题案与 Agent 优化边界设计

## 背景

最近运行暴露出三个结构性问题：题案生成量受 Agent 的普通批次上限限制；模拟结果、提交候选和轮次摘要被持久化为事实源；候选容易退化为窗口、权重或符号的参数微调。目标是让 Alpha 工厂负责每轮固定的大批量题案，Agent 只提供有经济机制依据的优化题案和模板改进，并把本地状态收敛为检查点。

## 约束与不变量

1. 工厂批次目标固定为 100 个候选。候选必须是唯一、通过生产预检并满足角色/族群/预算约束；不足 100 个时整批阻断，不部分 POST、不用重复候选填充。
2. Agent-facing 生成接口只产生优化候选或模板改进候选；其候选必须引用已完成且有证据的父题案，声明一个经济机制变化和一个可证伪问题。基础批量题案由工厂模板层生成。
3. 所有候选都要经过现有 `Agent.run_proposals()` 唯一安全执行入口。`SUBMIT_UNKNOWN`、已知 progress URL、checkpoint exactly-once 语义保持不变。
4. 模拟结果和已提交 Alpha 的运行数据按 `America/New_York` 的本地日作为内存缓存键。跨美国本地日自动丢弃前一日缓存；不写入 `sims_results.json`、`submission_pool.json`、Alpha 结果侧车、trajectory、trial ledger 或轮次摘要。
5. 磁盘只保留恢复所需 checkpoint。checkpoint 保存未完成任务的远程身份、状态和最小恢复元数据；完成后的指标、结果列表、提交池和颜色证据不在本地留存。
6. 不再生成/依赖无意义的 `round_N.json` 和 `round_N` 作为历史事实。内部兼容参数可以暂存，但持久化标识使用 checkpoint identity；不会用轮次编号推导新研究结论。
7. 每次产生的题案对外返回 `list[dict]`；顶层工厂 payload 的 `proposals` 必须始终是 list。
8. Alpha 颜色分组默认只读检测，不自动提交 Alpha、不覆盖非本项目颜色。沿用 PURPLE > GREEN > RED > BLUE > YELLOW 的证据优先级，并输出冲突/缺证据原因；颜色结果只进入当日内存缓存或未完成 checkpoint 的最小恢复字段。

## 设计

### 角色边界

`AlphaFactory.generate_factory_batch()` 负责从已核验字段和模板目录生成 100 个基础候选，按模板族、字段族和结构指纹去重，并在交给 Agent 前执行抗过拟合检查。`Agent.generate_optimized_proposals()` 只读取已完成信号，最多生成有限数量的一变量优化或模板改进候选，不能凭空从一个字段批量扫描窗口/权重/符号。工厂可以把优化候选纳入 100 个候选的排序集合，但候选来源与角色必须保留在记录中。

### 日缓存

新增无副作用的日缓存对象，注入 clock 后以纽约本地日期分桶。缓存只存当前进程中的轻量结果引用/摘要，不提供文件写入 API；日期变化时先清空旧桶再创建新桶。Agent 的原有结果输出函数改为写入此对象并打印缓存日期，不再写结果文件。恢复流程只从 checkpoint 读取远程状态，不从已过期的结果缓存恢复。

### 检查点

保留一个明确的 checkpoint 存储边界。未完成 checkpoint 仍可原样恢复；完成 checkpoint 只保留最小状态索引，不包含完整模拟指标或 Alpha 提交结果。旧格式读取时 fail-closed，旧 `round_N.json` 只作为待清理的遗留文件，不被新流程重新生成。

### 抗过拟合

在 proposal contract 中增加通用的结构比较：去除字段标识后比较 operator/window/weight/sign skeleton；只改方向、单独改数值窗口、单独改权重或同模板参数扫描，若没有新的经济机制和预注册 robustness 目的则拒绝。保留现有固定多腿规则和 loop guard，避免以新接口绕过旧约束。

### 颜色机制

保留既有证据分类逻辑，增加无结果、证据冲突和非项目托管颜色的检测输出。颜色检测只读调用 BRAIN `get_alpha`；只有显式的颜色同步命令才允许对项目拥有的颜色执行 PATCH，并且必须 readback 校验。同步结果不写 `alpha_color_evidence.json`。

## 验收标准

- 纽约时区跨 UTC 日界线时缓存仍属于同一纽约日，跨纽约本地日后旧结果不可见。
- 普通 Agent 生成接口不会生成工厂 100 题案；工厂接口返回长度恰为 100 的 `list[dict]`，任何不足或重复都阻断执行。
- 参数/方向/窗口扫描在没有新机制时被拒绝，机制不同且信息增益可审计时可继续。
- 运行一批后状态目录只出现 checkpoint（以及既有明确的运行控制锁，如有），不出现模拟结果、提交池、trajectory、ledger、轮次摘要或颜色证据文件。
- 未完成 checkpoint 可 exactly-once 恢复；未知 POST 仍不会重发。
- 颜色检测覆盖五类颜色、缺证据和 ownership conflict，且不调用 Alpha submit。
