import unittest

from wqb_agent.expression import ExpressionAnalysis, analyze_expression


class TestExpressionAnalysis(unittest.TestCase):
    def test_analysis_is_deterministic_and_extracts_only_known_fields(self):
        result = analyze_expression(
            "rank(ts_delta(returns_5d, 5)) + rank(close)",
            known_fields=("returns", "returns_5d", "close"),
        )

        self.assertIsInstance(result, ExpressionAnalysis)
        self.assertEqual(result.canonical, "rank(ts_delta(returns_5d,5))+rank(close)")
        self.assertEqual(result.operators, ("rank", "ts_delta"))
        self.assertEqual(result.fields, ("close", "returns_5d"))
        self.assertIn("returns_5d", result.identifiers)
        self.assertNotIn("returns", result.fields)

    def test_analysis_handles_empty_and_non_string_input(self):
        result = analyze_expression(None, known_fields=("close",))

        self.assertEqual(result.original, "")
        self.assertEqual(result.canonical, "")
        self.assertEqual(result.operators, ())
        self.assertEqual(result.identifiers, ())
        self.assertEqual(result.fields, ())

    def test_known_field_matching_is_case_insensitive_but_preserves_declared_id(self):
        result = analyze_expression(
            "Rank(CLOSE) + rank(close_5d)",
            known_fields=("close", "close_5d"),
        )

        self.assertEqual(result.fields, ("close", "close_5d"))


if __name__ == "__main__":
    unittest.main()
