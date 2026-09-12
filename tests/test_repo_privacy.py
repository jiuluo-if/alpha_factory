"""Privacy regression for the public tree.

The repository keeps raw research exports local-only; this test proves the
guard detects the classes it claims to detect and that the tracked tree is free
of them right now. Synthetic samples are built by concatenation so the test file
itself never contains a literal private path.
"""

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_guard():
    spec = importlib.util.spec_from_file_location(
        "check_repo_privacy", ROOT / "scripts" / "check_repo_privacy.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_repo_privacy"] = module
    spec.loader.exec_module(module)
    return module


GUARD = _load_guard()


class TestRepositoryPrivacyGuard(unittest.TestCase):
    def test_tracked_tree_has_no_private_research_data(self):
        files = GUARD.tracked_files(ROOT)
        findings, skipped = GUARD.scan(ROOT, files)
        self.assertEqual(skipped, [])
        self.assertEqual(
            [item.as_dict() for item in findings],
            [],
            "tracked files must not expose machine paths or private research artifacts",
        )

    def test_windows_drive_path_is_detected(self):
        text = "root = " + "C" + ":" + "\\" + "Users" + "\\" + "researcher" + "\\" + "state"
        codes = {item.code for item in GUARD._scan_text("sample.py", text)}
        self.assertIn("ABSOLUTE_LOCAL_PATH", codes)

    def test_private_attachment_path_is_detected(self):
        text = "spec=" + "attachments" + "/" + "7e3fc2fc-7fdc-41c6-a100-61d212d98f8c" + "/goal.md"
        codes = {item.code for item in GUARD._scan_text("sample.md", text)}
        self.assertIn("PRIVATE_ATTACHMENT_PATH", codes)

    def test_alpha_identifier_is_detected(self):
        text = "alpha_id=" + "alpha-" + "1234567890"
        codes = {item.code for item in GUARD._scan_text("sample.json", text)}
        self.assertIn("ALPHA_IDENTIFIER", codes)

    def test_submission_identifier_is_detected(self):
        text = "proposal_id=" + "p-" + "52b9c26b61b4e283"
        codes = {item.code for item in GUARD._scan_text("sample.json", text)}
        self.assertIn("SUBMISSION_IDENTIFIER", codes)

    def test_remote_simulation_url_is_detected(self):
        text = (
            "url=https://api.worldquantbrain.com/simulations/"
            + "9f2a4c6b8d0e1234"
        )
        codes = {item.code for item in GUARD._scan_text("sample.py", text)}
        self.assertIn("SIMULATION_PROGRESS_URL", codes)

    def test_raw_audit_artifact_path_is_detected(self):
        findings, _ = GUARD.scan(ROOT, ["docs/research_quality_audit_x/audit.json"])
        codes = {item.code for item in findings}
        self.assertIn("RAW_AUDIT_ARTIFACT", codes)

    def test_weak_credential_literal_is_not_flagged(self):
        text = "password=" + '"' + "explicit-password" + '"'
        codes = {item.code for item in GUARD._scan_text("sample.py", text)}
        self.assertNotIn("HARDCODED_CREDENTIAL", codes)

    def test_plain_architecture_reference_is_not_flagged(self):
        text = "state_dir = '" + ".wqb_state" + "'  # relative, project-owned"
        codes = {item.code for item in GUARD._scan_text("sample.py", text)}
        self.assertEqual(codes, set())


if __name__ == "__main__":
    unittest.main()
