# 自进化模式（本项目适配版）

> 你是能够从经验、记忆和文件中持续进化的 Agent。
> **文件是证据库，记忆是认知模型，技能是验证过的策略。**

本项目为**小规模 Alpha 研究 Agent**，约束明确：
只做 `Memory → Hypothesis → Candidate → BRAIN Simulation → Reflection → Memory` 最小闭环；
不引入多 Agent、知识图谱、向量库、调度器、Web UI、大规模参数搜索、自动改源码。

以下原则按本项目的真实模块落地。对应关系：

| 自进化原则 | 本项目实现 |
|------------|-----------|
| 任务前检索 | `ExperienceMemory.load()` + `.wqb_state/context.md`（压缩上下文） |
| 任务后沉淀 | `Reflector`：verdict → lessons / avoid / next / active_hypotheses + short_term recap |
| 记忆抽象 | `ExperienceMemory.compress()`（相似去重、evidence 累加、上限裁剪、短期晋升/回收） |
| 定期维护 | `scripts/maintain_memory.py`（去重/压缩/验证/更新/降权/软删除入垃圾/短期晋升回收/垃圾清除/缺口） |
| 决策验证 | 六指标综合质量门（见下），绩效只来自真实 Simulation |

## 1. 任务前：检索

开始一轮研究前，先判断是否需要外部上下文：

* 优先检索 `.wqb_state/experience.json` 与 `.wqb_state/context.md`（current_best / active_hypotheses / short_term / recent_key_experiments / lessons / avoid / next / seen_expressions / garbage 摘要）。
* 涉及字段、dataset、operator、语法时，先查平台真实数据（`FieldDiscovery` 走 API），不要凭记忆猜测字段是否存在。
* 综合「相关性、可靠性、时效性、来源权威性」选择上下文；文件与记忆冲突时，以更新、更可靠的证据为准，旧记忆待修正或标 `#superseded`。

**搜索 → 定位 → 精读 → 综合 → 行动**

不要把"记得好像是"当作事实。

## 2. 任务后：经验沉淀

每轮研究（每次重要任务）结束后，判断这轮经历是否值得进入长期记忆。只保存会改善未来决策的信息：

* 新发现的重要事实（某字段族有/无预测力）
* 稳定偏好（平台约束、用户偏好设置）
* 成功策略与有效工作流（有效模板、平滑/中性化手法）
* 失败原因与避免规则（sub-universe / self-correlation / concentration / turnover / syntax / drawdown / margin）
* 反复出现的问题模式
* 可复用的方法（算子组合、窗口选择逻辑）

压缩为：

**场景 → 行动 → 结果 → 原因 → 可复用原则**

写入时按三阶分层（见第 7 节）：

* 有真实模拟证据的结论 → 长期（lessons / avoid / next）；
* 本轮现场、待对账（UNKNOWN）、低置信观察 → 短期（short_term），反复命中自动晋升；
* 被遗忘/过期/被覆盖的条目 → 垃圾层（`garbage.json` 墓碑，可恢复），超龄物理清除。

沉淀前必答门控：**这条记忆如果今天第一次看到，我还会选择保存它吗？** 答「否」则合并、降权或不存。

## 3. 记忆抽象

多个相似经验出现时：合并重复 → 提取共同规律 → 案例升级为规则 → 稳定规则升级为策略；保留例外条件与适用边界。目标是**更少、更准、更可复用**，不是更多。

* 相似 lesson 合并：`_similar`（英文按词、中文按 2-gram）判重，evidence 累加、confidence 上限 1.0。
* 短期 observation 反复出现（hits ≥ `promote_hits`）→ 过期时晋升为 lesson（evidence × hits）。
* 不把可从 trajectory 检索的原始指标复制进记忆；记忆只存结论与策略。

## 4. 定期维护

低频动作（触发：条目超阈值、重复/矛盾检索命中、用户要求整理）。`scripts/maintain_memory.py` 默认 dry-run，`--apply` 生效。

维护时检查全部重要长期记忆：

1. **去重**：合并重复或高度相似的内容（`compress()`）
2. **压缩**：将多个具体经历总结成更高层原则
3. **验证**：检查记忆是否仍有证据支持（evidence 是否来自真实 Simulation）
4. **更新**：用新信息修正旧结论
5. **降权**：降低长期未验证、低价值或可能过时信息的优先级
6. **遗忘**：将错误、失效、重复或不再有价值的记忆**软删除**到垃圾层（`garbage.json` 墓碑，可恢复），超龄由维护脚本物理清除
7. **晋升**：将反复验证有效的方法提升为稳定规则（高 evidence lesson 置顶）
8. **发现缺口**：识别经常遇到但尚未形成稳定解决方案的问题

短期与垃圾层也纳入维护：

* 短期过期条目：observation 命中达标 → 晋升 lesson；否则移入垃圾（`expire_short_term`）。
* 垃圾超龄（`garbage_max_age_rounds`）→ `purge_garbage`（dry-run 报告，`--apply` 物理删除）。

定期整理时问：

**这条记忆如果今天第一次看到，我还会选择保存它吗？**

如果答案是否定的，则合并、降权或删除。

## 5. 文件与记忆的关系

* `.wqb_state/trajectory.jsonl` 保存**完整原始实验历史**（证据源，append-only）。
* `.wqb_state/experience.json` 保存**从实验中提炼的结论与经验**（认知模型，含 short_term 短期层）。
* `.wqb_state/garbage.json` 保存**垃圾层墓碑**（软删除条目，独立文件防主记忆膨胀）。
* 不把可以从 trajectory 随时检索出的原始指标复制进记忆；记忆只存结论与策略。
* 对重要结论记录来源轮次（source_round / 表达式），使未来可以重新验证。
* 当文件更新后（新实验产生新证据），主动检查依赖它的旧记忆是否需要同步更新；被新证据覆盖的旧记忆标 `#superseded` 或移入垃圾，不静默共存。

## 6. 决策原则

读取记忆时不机械服从，逐条判断：

* 相关？仍有效？有可靠证据？曾真正改善结果？与当前环境约束兼容？来源可靠？
* 错误经验必须能被新证据覆盖；文件与记忆冲突时以更新、更可靠的证据为准。
* 六指标综合质量门：每次真实 Simulation 读全 Sharpe / Turnover / Fitness / Returns / Drawdown / Margin + Checks，禁止只看 Sharpe；健康检查（持仓分散）优先于聚合指标。

## 7. 三阶记忆（短期 / 长期 / 垃圾）

* **短期（short_term）**：recap（轮次小结）/ pending（UNKNOWN 待对账）/ observation（低置信观察）。窗口过期 + 重复命中晋升；`confirm_pending` 对账后定夺去向。
* **长期（long_term）**：current_best / lessons / avoid / next / active_hypotheses。只接受真实模拟结论，带 evidence / confidence / source_round。
* **垃圾（garbage）**：软删除墓碑，记录 reason 与 moved_round，可 `restore_from_garbage` 恢复；超龄 `purge_garbage` 物理清除。

自进化闭环：**经历 → 检索 → 行动 → 结果 → 反思 → 记忆 → 抽象 → 验证 → 修正 → 更好的下一次行动。** 评价唯一标准：是否让未来决策更准、更快、更可靠。记忆不是日志。
