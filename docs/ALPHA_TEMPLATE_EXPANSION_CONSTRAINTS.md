# Alpha template expansion constraints

本文件是 Alpha 模板更新与拓展的强制预读协议。任何 Agent 在新增、修改、迁移、审查或扩展 `wqb_agent/alpha_templates` 中的模板、schema、catalog、operator coverage、horizon 或 settings 规则前，必须先阅读：

1. 根目录 `AGENTS.md`；
2. `wqb_agent/AGENTS.md`；
3. `wqb_agent/alpha_templates/AGENTS.md`；
4. 本文件；
5. `wqb_agent/research_api.py`、直接依赖模块和相关测试。

若无法完成上述阅读，Agent 必须停止模板变更并报告 `TEMPLATE_CONSTRAINTS_NOT_READ`。完成阅读后，Agent 必须在工作记录中确认本协议，并在变更说明中给出对应验证证据。

## 不可放宽的边界

- tracked catalog 只能包含明确标注的 `TOY/SYNTHETIC/NON-RESEARCH` 示例；真实模板、字段 ID、固定配对、表达式、经验先验、ExperienceMemory、trajectory 和研究证据只能存在本地私有目录。
- 私有 catalog 只能按显式绝对路径、`WQB_ALPHA_TEMPLATE_CATALOG`、用户 home 私有默认路径解析；缺失必须 fail-closed，禁止搜索 cwd/父目录或回退 public catalog。
- Probe 必须有经济机制、字段关系、方向理由、预期 horizon、falsification、self-correlation 影响、novelty、4–6 个算子出现次数和 2–4 个经济字段；Control 才允许 1–3 个算子和单字段。
- horizon 只能来自 `5/22/66/120/255`；多窗口必须是相邻有序 profile，禁止笛卡尔积。每个实验只能选择一个 horizon/profile 和一个 settings arm；arm 每次只改变一个主要变量。
- 算子覆盖是审计目标，不是堆叠复杂度的理由。只有算子 arity 已验证、经济效应明确且与机制关系相符时，才可扩展覆盖。
- Alpha Factory 生成研究探针，不生成可直接提交的 Alpha；promotion 必须逐级进行，失败试验必须继续由现有 TrialLedger 和 ExperienceMemory 记账。

## 变更前检查

Agent 必须确认：私有数据未进入 tracked files、文档、测试、prompt、日志或报告；没有新增第二套 state/proposal/ledger/ExperienceMemory/Simulation 路径；schema/validation/loader/registry 的行为测试已覆盖；没有真实 Simulation、Alpha submission 或 quota 消耗。
