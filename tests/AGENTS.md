# `tests/` 局部规则

测试保护机制不变量和可观察行为。使用临时目录、fake client、固定时钟和最小 fixture；绝不连接真实 BRAIN 或消耗真实 Simulation 预算。

facade 测试应验证 `research_api.py` 组合现有 discovery、执行、证据和 reconciliation 路径，而不是复制它们。只保护历史架构形状的测试可以删除；核心安全不变量必须迁移并保留。

代码变更必须运行：

```powershell
python -m unittest discover -s tests
python -m compileall -q wqb_agent scripts tests
```
