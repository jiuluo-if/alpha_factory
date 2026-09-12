# Alpha templates

`wqb_agent.alpha_templates` 是模板模型、内置 catalog、resource loader、registry 和 numeric audit 的唯一 owner。`alpha_factory.py` 只消费 registry；`candidate.py` 的 from-scratch 生成也复用同一套模板 binding path。

## 新增模板

1. 编辑 `wqb_agent/alpha_templates/catalog/builtin.toml`，新增一个 `[[templates]]`。
2. 声明唯一 `id`、`version`、`kind`（`baseline` 或 `economic`）、`family`、`expression` 和 `required_slots`。
3. 声明显式 `economic_mechanism`、`direction`、`direction_transform`、`expected_horizon`、`falsification` 与 `self_correlation_impact`。
4. 把模板加入适用的 `selection_groups`；group membership 属于 catalog metadata，不在 Python 中维护 template ID 集合。
5. 只有表达式中真正允许研究轮换的 numeric literal 才声明 `numeric_slots`，并提供 `allowed_values`。安全常量和算子必需常量保持固定，不声明为 slot。

## 修改与验证

loader 通过 `importlib.resources` 读取 TOML，兼容 source checkout、editable install 和 wheel。它会拒绝重复 ID、缺字段、非法 kind/slot/group/direction、重复 slot name、slot token/occurrence 不存在、缺 allowed values 和未分类 numeric literal；不会静默跳过、自动修复或回退默认模板。

模板 fingerprint 只描述 structural identity（family、expression、required slots、stage path），不包含 rationale、日期或文档叙事。平台 operator 语法仍由 [`reference/OPERATORS_CHEATSHEET.md`](reference/OPERATORS_CHEATSHEET.md) 维护。

```powershell
python -m unittest tests.test_alpha_template_catalog
python -m unittest tests.test_candidate_builder tests.test_factory_boundaries
python -m py_compile wqb_agent/alpha_templates/model.py wqb_agent/alpha_templates/loader.py wqb_agent/alpha_templates/registry.py wqb_agent/alpha_factory.py wqb_agent/candidate.py
python -m ruff check wqb_agent/alpha_templates wqb_agent/alpha_factory.py wqb_agent/candidate.py
```
