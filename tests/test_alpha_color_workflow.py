import ast
import inspect
import os
from pathlib import Path
import unittest
from types import SimpleNamespace

from wqb_agent.alpha_color_workflow import AlphaColorWorkflow
from wqb_agent.alpha_colors import classify_alpha_color, sync_alpha_colors


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ColorTransport:
    def __init__(self, color=None, patch_result=None):
        self.color = color
        self.patch_result = patch_result
        self.get_calls = []
        self.patch_calls = []

    def get_alpha(self, alpha_id):
        self.get_calls.append(alpha_id)
        return {"id": alpha_id, "color": self.color}

    def set_alpha_color(self, alpha_id, color, *, verify=True):
        self.patch_calls.append((alpha_id, color, verify))
        if self.patch_result is not None:
            return self.patch_result
        self.color = color
        return {"id": alpha_id, "color": color}


def _candidate(alpha_id="a1"):
    return SimpleNamespace(alpha_id=alpha_id, status="DONE")


class TestAlphaColorWorkflow(unittest.TestCase):
    def workflow(self, transport, classifier=lambda _item: "GREEN"):
        return AlphaColorWorkflow(
            get_alpha=transport.get_alpha,
            set_alpha_color=transport.set_alpha_color,
            classifier=classifier,
        )

    def test_no_candidates_does_not_read_or_write(self):
        transport = ColorTransport()

        changes = self.workflow(transport).sync([])

        self.assertEqual(changes, [])
        self.assertEqual(transport.get_calls, [])
        self.assertEqual(transport.patch_calls, [])

    def test_same_color_is_noop(self):
        transport = ColorTransport(color="GREEN")

        changes = self.workflow(transport).sync([_candidate()])

        self.assertEqual(len(transport.get_calls), 1)
        self.assertEqual(transport.patch_calls, [])
        self.assertEqual(changes[0]["action"], "NOOP")
        self.assertEqual(changes[0]["old_color"], "GREEN")
        self.assertEqual(changes[0]["new_color"], "GREEN")
        self.assertEqual(
            set(changes[0]),
            {
                "alpha_id", "old_color", "new_color", "classification",
                "evidence", "action",
            },
        )
        self.assertEqual(
            set(changes[0]["evidence"]),
            {
                "classification", "research_classification",
                "self_correlation", "self_correlation_value",
                "submission_eligible", "incremental_decision",
            },
        )

    def test_dry_run_reads_but_never_patches(self):
        transport = ColorTransport(color=None)

        changes = self.workflow(transport).sync([_candidate()], dry_run=True)

        self.assertEqual(len(transport.get_calls), 1)
        self.assertEqual(transport.patch_calls, [])
        self.assertEqual(changes[0]["action"], "DRY_RUN_PATCH")
        self.assertEqual(changes[0]["new_color"], "GREEN")

    def test_existing_color_without_ownership_is_fail_closed(self):
        transport = ColorTransport(color="YELLOW")

        changes = self.workflow(transport).sync([_candidate()])

        self.assertEqual(len(transport.get_calls), 1)
        self.assertEqual(transport.patch_calls, [])
        self.assertEqual(changes[0]["action"], "OWNERSHIP_CONFLICT")
        self.assertEqual(changes[0]["new_color"], "YELLOW")

    def test_authorized_change_uses_verified_color_operation(self):
        transport = ColorTransport(color=None)

        changes = self.workflow(transport).sync([_candidate()])

        self.assertEqual(transport.patch_calls, [("a1", "GREEN", True)])
        self.assertEqual(changes[0]["action"], "PATCHED")
        self.assertEqual(changes[0]["new_color"], "GREEN")

    def test_readback_mismatch_fails_closed(self):
        transport = ColorTransport(
            color=None,
            patch_result={"id": "a1", "color": "YELLOW"},
        )

        with self.assertRaises(ValueError):
            self.workflow(transport).sync([_candidate()])
        self.assertEqual(transport.patch_calls, [("a1", "GREEN", True)])

    def test_missing_readback_fails_closed(self):
        transport = ColorTransport(color=None)
        transport.set_alpha_color = lambda *_args, **_kwargs: None

        with self.assertRaises(ValueError):
            self.workflow(transport).sync([_candidate()])

    def test_duplicate_alpha_id_is_read_once(self):
        transport = ColorTransport(color="GREEN")

        changes = self.workflow(transport).sync([_candidate(), _candidate()])

        self.assertEqual(len(transport.get_calls), 1)
        self.assertEqual(len(changes), 1)

    def test_missing_alpha_id_is_skipped(self):
        transport = ColorTransport(color=None)

        changes = self.workflow(transport).sync([_candidate(None)])

        self.assertEqual(changes, [])
        self.assertEqual(transport.get_calls, [])

    def test_no_classification_does_not_clear_unowned_remote_color(self):
        transport = ColorTransport(color="GREEN")

        changes = self.workflow(transport, classifier=lambda _item: None).sync(
            [_candidate()]
        )

        self.assertEqual(changes, [])
        self.assertEqual(transport.get_calls, [])
        self.assertEqual(transport.patch_calls, [])

    def test_legacy_wrapper_delegates_to_same_behavior(self):
        transport = ColorTransport(color=None)
        from tests.test_alpha_colors import _experiment

        changes = sync_alpha_colors(
            [_experiment(quality="PROMISING", self_result=True)],
            transport,
            "ignored",
        )

        self.assertEqual(transport.patch_calls, [("alpha-1", "YELLOW", True)])
        self.assertEqual(changes[0]["action"], "PATCHED")


class TestAlphaColorWorkflowBoundaries(unittest.TestCase):
    def test_workflow_is_not_client_or_agent_constructed(self):
        signature = inspect.signature(AlphaColorWorkflow)
        self.assertNotIn("client", signature.parameters)
        self.assertNotIn("agent", signature.parameters)

    def test_alpha_colors_has_no_remote_or_agent_import(self):
        source = Path(ROOT, "wqb_agent", "alpha_colors.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("requests", imports)
        self.assertNotIn("client", imports)
        self.assertNotIn("simulator", imports)
        self.assertNotIn("agent", imports)

    def test_workflow_has_only_color_operation_write_symbols(self):
        path = os.path.join(ROOT, "wqb_agent", "alpha_color_workflow.py")
        source = Path(path).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("client", imports)
        self.assertNotIn("agent", imports)
        self.assertNotIn("simulator", imports)
        self.assertNotIn("proposal_execution", imports)
        self.assertNotIn("requests.post", source)
        self.assertNotIn("requests.patch", source)
        self.assertNotIn("submit_simulation", source)
        self.assertNotIn("submit_alpha", source)
        self.assertNotIn("ProposalExecutionWorkflow", source)

    def test_main_does_not_duplicate_color_policy(self):
        source = Path(ROOT, "main.py").read_text(encoding="utf-8")
        self.assertNotIn("classify_alpha_color", source)
        self.assertNotIn("has_research_signal", source)


if __name__ == "__main__":
    unittest.main()
