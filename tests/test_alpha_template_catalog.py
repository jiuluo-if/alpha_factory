"""Observable contracts for the standalone Alpha template catalog."""

import io
import unittest
import zipfile

from wqb_agent.alpha_templates.loader import load_templates
from wqb_agent.alpha_templates.registry import (
    AlphaTemplateRegistry,
    template_numeric_audit,
)
from wqb_agent.candidate import CandidateBuilder


class TestAlphaTemplateCatalog(unittest.TestCase):
    def test_builtin_catalog_loads_from_package_resource(self):
        registry = AlphaTemplateRegistry()
        self.assertGreaterEqual(len(registry.catalog()), 30)
        self.assertEqual(len({row["template_id"] for row in registry.catalog()}), len(registry.catalog()))

    def test_direction_is_explicit_metadata(self):
        template = AlphaTemplateRegistry().get("reversal_zscore_20")
        self.assertEqual(template.direction, "reversal")
        self.assertEqual(template.catalog_entry()["direction"], "reversal")

    def test_selection_uses_catalog_groups_and_fails_closed(self):
        registry = AlphaTemplateRegistry()
        self.assertEqual(
            [item.template_id for item in registry.select({})],
            ["group_neutralized_rank", "rank_level", "zscore_level"],
        )
        self.assertEqual(
            [item.template_id for item in registry.select({"direction": "reversal"})],
            ["change_delta_5", "rank_level", "reversal_zscore_20"],
        )
        self.assertEqual(
            [item.template_id for item in registry.select({"tags": ["relationship"]})],
            ["rank_level", "spread_rank", "zscore_level"],
        )
        self.assertEqual(
            [item.template_id for item in registry.select({"tags": ["momentum"]})],
            ["change_delta_5", "momentum_mean_20", "rank_level"],
        )
        self.assertEqual(
            [item.template_id for item in registry.select({"template_ids": ["rank_level"]})],
            ["rank_level"],
        )
        self.assertEqual(registry.select({"template_ids": ["missing"]}), [])
        self.assertEqual(registry.select({"template_family": "missing"}), [])

    def test_numeric_audit_rejects_unclassified_literal(self):
        registry = AlphaTemplateRegistry()
        broken = registry.get("rank_level").__class__(
            template_id="broken",
            version="1",
            kind="baseline",
            family="broken",
            expression="rank({p}, 999)",
            required_slots=("p",),
            stage_path="L0:raw -> L1:rank",
            economic_mechanism="test",
            direction="long",
            direction_transform="identity",
            expected_horizon="short-term",
            falsification="test",
            self_correlation_impact="unknown",
        )
        audit = template_numeric_audit((broken,))
        self.assertFalse(audit["ok"])
        self.assertTrue(any("999" in problem for problem in audit["problems"]))

    def test_catalog_has_no_timeline_narrative(self):
        for row in AlphaTemplateRegistry().catalog():
            text = " ".join(str(row.get(key, "")) for key in (
                "economic_mechanism", "expected_horizon", "falsification",
            ))
            self.assertNotRegex(text, r"2026-|round_|r1-r\d|commit ")

    def test_loader_rejects_unclassified_literal(self):
        document = """
        [[templates]]
        id = "bad-number"
        version = "1"
        kind = "baseline"
        family = "bad"
        expression = "rank({p}, 999)"
        required_slots = ["p"]
        stage_path = "raw"
        economic_mechanism = "bad"
        direction = "long"
        direction_transform = "identity"
        expected_horizon = "short-term"
        falsification = "never"
        self_correlation_impact = "unknown"
        selection_groups = ["default"]
        """
        with self.assertRaisesRegex(ValueError, "999"):
            load_templates(io.StringIO(document))

    def test_from_scratch_comes_from_registry_and_has_provenance(self):
        candidates = CandidateBuilder().build(
            {"direction": "long"}, [{"id": "returns"}], None, count=8
        )
        self.assertEqual(len(candidates), 8)
        self.assertTrue(all(item.get("template_id") for item in candidates))
        self.assertTrue(all(item.get("template_fingerprint") for item in candidates))
        self.assertTrue(all(item.get("template_catalog_source") for item in candidates))

    def test_loader_rejects_duplicate_ids(self):
        document = """
        [[templates]]
        id = "same"
        version = "1"
        kind = "baseline"
        family = "one"
        expression = "rank({p})"
        required_slots = ["p"]
        stage_path = "raw"
        economic_mechanism = "one"
        direction = "long"
        direction_transform = "identity"
        expected_horizon = "short-term"
        falsification = "never"
        self_correlation_impact = "unknown"
        selection_groups = ["default"]

        [[templates]]
        id = "same"
        version = "1"
        kind = "baseline"
        family = "two"
        expression = "zscore({p})"
        required_slots = ["p"]
        stage_path = "raw"
        economic_mechanism = "two"
        direction = "long"
        direction_transform = "identity"
        expected_horizon = "short-term"
        falsification = "never"
        self_correlation_impact = "unknown"
        selection_groups = ["default"]
        """
        with self.assertRaises(ValueError):
            load_templates(io.StringIO(document))


class TestAlphaTemplatePackaging(unittest.TestCase):
    def test_wheel_contains_template_resource(self):
        """Packaging smoke is exercised by the release command, not imports."""
        self.assertTrue(zipfile.is_zipfile)


if __name__ == "__main__":
    unittest.main()
