"""Static architecture guards for the production module boundaries."""

import ast
import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_ROOT = os.path.join(ROOT, "wqb_agent")


def _direct_imports(module_name):
    path = os.path.join(PACKAGE_ROOT, module_name + ".py")
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), filename=path)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = "." * node.level + (node.module or "")
                imports.add(base)
            elif node.module:
                imports.add(node.module)
    return imports


class TestArchitectureBoundaries(unittest.TestCase):
    DOMAIN_MODULES = (
        "alpha_factory",
        "candidate",
        "discovery",
        "diversity",
        "evidence",
        "failures",
        "memory",
        "metrics",
        "mutations",
        "proposal_contract",
        "reflection",
        "research_guard",
        "search_policy",
        "search_snapshot",
        "simulator",
        "state",
        "submission",
        "validation",
    )

    def test_domain_modules_do_not_reverse_import_agent(self):
        for module_name in self.DOMAIN_MODULES:
            imports = _direct_imports(module_name)
            self.assertNotIn(
                ".agent", imports,
                f"{module_name}.py 反向依赖 Agent，会形成编排器循环依赖",
            )
            self.assertNotIn(
                "wqb_agent.agent", imports,
                f"{module_name}.py 反向依赖 Agent，会形成编排器循环依赖",
            )

    def test_pure_modules_do_not_import_transport_or_persistence(self):
        banned = {
            ".client", "wqb_agent.client", ".state", "wqb_agent.state",
            "requests", "subprocess",
        }
        for module_name in (
            "alpha_factory", "expression", "metrics", "mutations",
            "proposal_contract", "research_guard", "factory_runner",
        ):
            imports = _direct_imports(module_name)
            overlap = sorted(imports & banned)
            self.assertEqual(
                overlap, [],
                f"{module_name}.py 不应直接依赖网络/持久化模块: {overlap}",
            )

    def test_validation_does_not_create_a_second_simulation_path(self):
        imports = _direct_imports("validation")
        self.assertNotIn(
            ".simulator", imports,
            "validation.py 只能生成扰动任务，真实执行必须回到 Agent 的生产边界",
        )
        self.assertNotIn(
            "wqb_agent.simulator", imports,
            "validation.py 不应直接依赖 Simulator",
        )

    def test_validation_uses_pure_mutations_instead_of_candidate_orchestrator(self):
        imports = _direct_imports("validation")
        self.assertNotIn(
            ".candidate", imports,
            "validation.py 应依赖纯 mutations 层，不应加载候选编排器",
        )
        self.assertIn(".mutations", imports)

    def test_maintenance_scripts_use_pure_metric_boundary(self):
        for name in ("check_health.py", "reconcile_pending.py", "validate_integrity.py"):
            path = os.path.join(ROOT, "scripts", name)
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            self.assertNotIn(
                "wqb_agent.simulator", source,
                f"{name} 不应通过 Simulator 获取纯指标/健康函数，避免审计脚本耦合生产调度器",
            )
            if name in {"check_health.py", "reconcile_pending.py"}:
                self.assertIn("wqb_agent.metrics", source)

    def test_only_transport_modules_can_submit_simulations(self):
        allowed = {"client.py", "simulator.py", "agent.py"}
        for filename in os.listdir(PACKAGE_ROOT):
            if not filename.endswith(".py") or filename in allowed:
                continue
            with open(os.path.join(PACKAGE_ROOT, filename), encoding="utf-8") as handle:
                source = handle.read()
            self.assertNotIn("submit_simulation(", source,
                             f"{filename} 创建了第二条 Simulation POST 路径")

    def test_no_production_alpha_submission_endpoint(self):
        for filename in os.listdir(PACKAGE_ROOT):
            if not filename.endswith(".py") or filename == "client.py":
                continue
            with open(os.path.join(PACKAGE_ROOT, filename), encoding="utf-8") as handle:
                source = handle.read().lower()
            self.assertNotIn('"/submit"', source,
                             f"{filename} 不得包含自动 Alpha submission endpoint")


if __name__ == "__main__":
    unittest.main()
