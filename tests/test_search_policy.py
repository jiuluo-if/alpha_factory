import unittest

from wqb_agent.search_policy import (
    BudgetAllocator,
    SearchPolicy,
    empirical_pool_summary,
    incremental_novelty,
    pareto_front,
    structural_fingerprint,
)


class TestStructuralAndEmpiricalDiversity(unittest.TestCase):
    def test_structural_fingerprint_anonymizes_fields_and_windows(self):
        left = structural_fingerprint("rank(ts_mean(close, 20))", ["close"])
        right = structural_fingerprint("rank(ts_mean(volume, 60))", ["volume"])
        self.assertEqual(left, right)

    def test_behaviorally_same_signals_are_redundant(self):
        pool = [{"expression": "rank(close)", "fields_used": ["close"], "returns": [1, 2, 3, 4]}]
        candidate = {"expression": "zscore(price)", "fields_used": ["price"], "returns": [1, 2, 3, 4]}
        summary = empirical_pool_summary(candidate, pool)
        self.assertEqual(summary["status"], "AVAILABLE")
        self.assertAlmostEqual(summary["max_corr"], 1.0)
        self.assertEqual(incremental_novelty(candidate, pool)["empirical"]["incremental_value"], 0.0)

    def test_missing_pnl_is_explicitly_unavailable(self):
        summary = empirical_pool_summary({"expression": "rank(close)"}, [])
        self.assertEqual(summary["status"], "UNAVAILABLE")
        self.assertIsNone(summary["max_corr"])

    def test_pareto_front_keeps_quality_novelty_tradeoff(self):
        records = [
            {"id": "quality", "sharpe": 2, "fitness": .8, "turnover": .2, "margin": .5, "drawdown": .2, "novelty": .2},
            {"id": "novel", "sharpe": 1, "fitness": .5, "turnover": .3, "margin": .4, "drawdown": .3, "novelty": .95},
            {"id": "dominated", "sharpe": .5, "fitness": .2, "turnover": .5, "margin": .2, "drawdown": .5, "novelty": .1},
        ]
        ids = {row["id"] for row in pareto_front(records)}
        self.assertEqual(ids, {"quality", "novel"})


class TestBudgetAllocator(unittest.TestCase):
    def test_pending_arm_is_not_bombarded(self):
        allocator = BudgetAllocator(total_budget=10, max_pending_per_arm=1)
        proposal = {"datasets": ["pv1"], "template_family": "momentum"}
        self.assertTrue(allocator.reserve(proposal))
        self.assertFalse(allocator.reserve(proposal))
        allocator.mark_pending(proposal)
        self.assertFalse(allocator.reserve(proposal))
        allocator.complete(proposal, reward=.4)
        self.assertTrue(allocator.reserve(proposal))

    def test_search_policy_records_novelty_and_allocator_arm(self):
        policy = SearchPolicy({"enabled": True, "max_simulations": 10})
        proposal = {"expression": "rank(close)", "fields": ["close"], "datasets": ["pv1"], "template_family": "trend"}
        policy.annotate(proposal, [])
        self.assertIn("search_evidence", proposal)
        self.assertEqual(policy.allocator.arm_key(proposal), "pv1::trend")
        self.assertTrue(policy.accept(proposal))

    def test_synthetic_selection_reduces_duplicates_under_same_budget(self):
        candidates = [
            {"expression": "rank(field_%d)" % i, "fields": ["field_%d" % i], "template_family": "rank", "datasets": ["pv1"]}
            for i in range(6)
        ] + [
            {"expression": "ts_mean(rank(signal_%d), 5)" % i, "fields": ["signal_%d" % i], "template_family": "smooth", "datasets": ["fundamental6"]}
            for i in range(3)
        ]
        old = candidates[:4]
        old_syntax = len({structural_fingerprint(row["expression"], row["fields"]) for row in old})
        policy = SearchPolicy({"enabled": True, "max_pending_per_arm": 10, "max_simulations": 20})
        chosen, pool = [], []
        for _ in range(4):
            for row in candidates:
                policy.annotate(row, pool)
            row = max(candidates, key=policy.priority)
            candidates.remove(row)
            chosen.append(row)
            pool.append(row)
            policy.accept(row)
        new_syntax = len({structural_fingerprint(row["expression"], row["fields"]) for row in chosen})
        self.assertGreater(new_syntax, old_syntax)


if __name__ == "__main__":
    unittest.main()
