import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import main as main_entry
from wqb_agent.checkpoints import CheckpointStore
from wqb_agent.preflight import build_agent_context, render_agent_context, run_takeover_preflight
from wqb_agent.state import Trajectory


def _preflight(*, status="READY", blocking=None, latest_round=12,
               submit_unknown=0):
    return {
        "status": status,
        "network_write": False,
        "state_dir": ".wqb_state",
        "blocking": list(blocking or []),
        "doctor": {"submit_unknown_count": submit_unknown},
        "state": {"ok": status == "READY", "errors": list(blocking or [])},
        "unfinished_checkpoints": [
            item for item in (blocking or []) if item.endswith(".checkpoint.json")
        ],
        "trajectory": {"records": 42, "latest_round": latest_round},
        "current_best": {"alpha_id": "a1"},
        "evidence_cache_entries": 3,
        "proposal_round": latest_round,
        "proposal_count": 0,
    }


class TestAgentContext(unittest.TestCase):
    def test_takeover_preflight_scans_checkpoints_once_per_command(self):
        with __import__("tempfile").TemporaryDirectory() as state_dir:
            original_scan = CheckpointStore.scan
            original_iter_rows = Trajectory.iter_rows
            original_listdir = __import__("os").listdir
            with patch.object(
                CheckpointStore, "scan", autospec=True,
                side_effect=original_scan,
            ) as scan, patch.object(
                Trajectory, "iter_rows", autospec=True,
                side_effect=lambda self: original_iter_rows(self),
            ) as iter_rows, patch(
                "wqb_agent.workspace_snapshot.os.listdir", wraps=original_listdir,
            ) as listdir:
                result = run_takeover_preflight({
                    "simulation": {}, "agent": {"state_dir": state_dir},
                })
        self.assertEqual(result["status"], "READY")
        self.assertEqual(scan.call_count, 1)
        self.assertEqual(iter_rows.call_count, 1)
        self.assertEqual(listdir.call_count, 1)

    def test_context_reuses_authoritative_preflight_and_blocks_next_action(self):
        with patch(
            "wqb_agent.preflight.run_takeover_preflight",
            return_value=_preflight(
                status="BLOCKED",
                blocking=["round_12.checkpoint.json", "checkpoint_ledger_mismatch"],
                submit_unknown=4,
            ),
        ) as preflight:
            context = build_agent_context({"simulation": {}, "agent": {}}, task="general")

        preflight.assert_called_once()
        self.assertEqual(context["workspace_status"], "BLOCKED")
        self.assertEqual(context["unfinished_checkpoints"], ["round_12.checkpoint.json"])
        self.assertEqual(context["submit_unknown"], 4)
        self.assertEqual(context["latest_round"], 12)
        self.assertIn("只读对账", context["next_safe_action"])
        self.assertFalse(context["network_write"])

    def test_compact_text_has_required_sections_and_bounded_route(self):
        context = build_agent_context(
            {"simulation": {}, "agent": {}}, task="state-recovery",
            preflight=_preflight(),
        )
        rendered = render_agent_context(context, compact=True)
        for heading in (
            "PROJECT", "SAFETY INVARIANTS", "WORKSPACE STATUS",
            "UNFINISHED CHECKPOINTS", "SUBMIT_UNKNOWN", "LATEST ROUND",
            "NEXT SAFE ACTION", "TASK → FILES", "TASK → TESTS",
            "VALIDATION COMMANDS",
        ):
            self.assertIn(heading, rendered)
        self.assertLessEqual(len(context["task"]["files"]), 3)
        self.assertLessEqual(len(context["task"]["tests"]), 2)
        self.assertLessEqual(len(context["task"]["docs"]), 1)

    def test_json_mode_is_machine_readable_and_read_only(self):
        context = build_agent_context(
            {"simulation": {}, "agent": {}}, task="config",
            preflight=_preflight(),
        )
        rendered = render_agent_context(context, json_mode=True)
        payload = json.loads(rendered)
        self.assertEqual(payload["workspace_status"], "SAFE")
        self.assertFalse(payload["network_write"])
        self.assertEqual(payload["task"]["name"], "config")
        self.assertIn("wqb_agent/config.py", payload["task"]["files"])

    def test_snapshot_keeps_bom_encoded_json_compatible(self):
        with __import__("tempfile").TemporaryDirectory() as state_dir:
            with open(
                __import__("os").path.join(state_dir, "proposals.json"),
                "w", encoding="utf-8-sig",
            ) as handle:
                json.dump({"round_no": 7, "proposals": [{"id": "p1"}]}, handle)
            result = run_takeover_preflight({
                "simulation": {}, "agent": {"state_dir": state_dir},
            })
        self.assertEqual(result["proposal_round"], 7)
        self.assertEqual(result["proposal_count"], 1)

    def test_context_routes_new_architecture_tasks_to_current_files(self):
        expected = {
            "runtime-composition": [
                "wqb_agent/runtime_components.py",
                "wqb_agent/config.py",
                "wqb_agent/agent.py",
            ],
            "workspace-diagnostics": [
                "wqb_agent/workspace_snapshot.py",
                "wqb_agent/preflight.py",
                "wqb_agent/doctor.py",
            ],
            "checkpoint-recovery": [
                "wqb_agent/checkpoints.py",
                "wqb_agent/agent.py",
                "wqb_agent/workspace_snapshot.py",
            ],
        }
        for task_name, files in expected.items():
            context = build_agent_context(
                {"simulation": {}, "agent": {}}, task=task_name,
                preflight=_preflight(),
            )
            self.assertEqual(context["task"]["name"], task_name)
            self.assertEqual(context["task"]["files"], files)
            self.assertLessEqual(len(context["task"]["files"]), 3)
            self.assertLessEqual(len(context["task"]["tests"]), 2)
            self.assertLessEqual(len(context["task"]["docs"]), 1)

    def test_unknown_task_uses_low_noise_default_route(self):
        context = build_agent_context(
            {"simulation": {}, "agent": {}}, task="unrecognized",
            preflight=_preflight(),
        )
        self.assertEqual(context["task"]["name"], "general")
        self.assertIn("wqb_agent/research_api.py", context["task"]["files"])

    def test_cli_json_context_is_read_only_and_machine_readable(self):
        with patch(
            "sys.argv",
            ["main.py", "--agent-context", "--compact", "--json",
             "--config", "missing-config.json", "--state-dir", ".wqb_state"],
        ), redirect_stdout(io.StringIO()) as output:
            main_entry.main()
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["network_write"])
        self.assertIn(payload["workspace_status"], {"SAFE", "REVIEW", "BLOCKED"})
        self.assertIn("validation_commands", payload)


if __name__ == "__main__":
    unittest.main()
