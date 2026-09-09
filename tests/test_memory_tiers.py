"""Three-tier memory tests: short_term / long_term / garbage.

Covers promotion of repeated observations, soft-delete tombstones with
restore, garbage purge, backward compatibility with old experience.json,
and the context digest.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wqb_agent.context import _safe_text, write_context  # noqa: E402
from wqb_agent.memory import ExperienceMemory  # noqa: E402
from wqb_agent.reflection import Reflector  # noqa: E402
from wqb_agent.state import Experiment  # noqa: E402


class TmpStateMixin:
    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="wqb_mem_")

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestShortTerm(TmpStateMixin, unittest.TestCase):
    def test_add_and_recent_orders_by_update(self):
        m = ExperienceMemory(state_dir=self._tmp)
        m.add_short_term("recap", "round 1 recap", 1)
        e2 = m.add_short_term("recap", "round 2 recap", 2)
        recent = m.recent_short_term(1)
        self.assertEqual(recent[0]["id"], e2["id"])
        self.assertEqual(len(m.short_term), 2)

    def test_similar_merge_bumps_hits(self):
        m = ExperienceMemory(state_dir=self._tmp)
        e1 = m.add_short_term(
            "observation", "anl4 netincome 主腿在 r84 后持续有效", 80
        )
        e2 = m.add_short_term(
            "observation", "anl4 netincome 主腿在 r84 后持续有效", 85
        )
        self.assertEqual(e1["id"], e2["id"])
        self.assertEqual(e1["hits"], 2)
        self.assertEqual(len(m.short_term), 1)

    def test_invalid_kind_rejected(self):
        m = ExperienceMemory(state_dir=self._tmp)
        with self.assertRaises(ValueError):
            m.add_short_term("nope", "text", 1)


class TestNextQueue(TmpStateMixin, unittest.TestCase):
    def test_stale_next_idea_cannot_reopen_old_research(self):
        m = ExperienceMemory(state_dir=self._tmp, next_max_age_rounds=20)
        m.add_next("old fundamental retry", 9, 100, 100,
                   fields=["cashflow_op"], datasets=["fundamental6"])
        m.add_next("fresh independent test", 4, 125, 125,
                   fields=["new_field"], datasets=["pv13"])
        self.assertEqual(m.next_with_fields(130)["idea"], "fresh independent test")
        self.assertIsNone(m.next_with_fields(150))


class TestPromotion(TmpStateMixin, unittest.TestCase):
    def test_independent_lineages_promote_observation_to_lesson(self):
        m = ExperienceMemory(state_dir=self._tmp, short_term_window=3,
                             promote_hits=2)
        m.updated_round = 100
        m.add_short_term(
            "observation", "flag 事件腿低权混入有效", 95,
            detail={"lineage": "h-a"},
        )
        m.add_short_term(
            "observation", "flag 事件腿低权混入有效", 96,
            detail={"lineage": "h-b"},
        )  # hits=2, independent lineages
        promoted, trashed = m.expire_short_term(now_round=100)
        self.assertEqual(len(promoted), 1)
        self.assertEqual(len(trashed), 0)
        self.assertEqual(len(m.lessons), 1)
        self.assertEqual(m.lessons[0]["evidence"], 2)  # evidence 1 * min(hits,3)=2

    def test_same_lineage_repetition_never_promotes(self):
        m = ExperienceMemory(state_dir=self._tmp, short_term_window=3,
                             promote_hits=2)
        m.updated_round = 100
        m.add_short_term("observation", "same lineage observation", 95,
                         detail={"lineage": "h-a"})
        m.add_short_term("observation", "same lineage observation", 96,
                         detail={"lineage": "h-a"})
        promoted, trashed = m.expire_short_term(now_round=100)
        self.assertEqual(promoted, [])
        self.assertEqual(len(trashed), 1)

    def test_recap_expires_to_garbage_not_lesson(self):
        m = ExperienceMemory(state_dir=self._tmp, short_term_window=2)
        m.updated_round = 10
        m.add_short_term("recap", "round 8 recap text", 8)
        promoted, trashed = m.expire_short_term(now_round=10)
        self.assertEqual(promoted, [])
        self.assertEqual(len(trashed), 1)
        self.assertEqual(len(m.lessons), 0)
        self.assertEqual(m.garbage_stats()["total"], 1)
        self.assertEqual(m.garbage[0]["reason"], "expired")

    def test_low_hits_observation_not_promoted(self):
        m = ExperienceMemory(state_dir=self._tmp, short_term_window=1,
                             promote_hits=2)
        m.add_short_term("observation", "single weak observation", 5)
        promoted, trashed = m.expire_short_term(now_round=6)
        self.assertEqual(promoted, [])
        self.assertEqual(len(trashed), 1)


class TestGarbage(TmpStateMixin, unittest.TestCase):
    def test_move_restore_roundtrip(self):
        m = ExperienceMemory(state_dir=self._tmp)
        lesson = m.add_lesson("a lesson to tombstone", 1, evidence=5)
        m.move_to_garbage("lesson", lesson, reason="superseded",
                          note="replaced by newer evidence", round_no=9)
        self.assertEqual(len(m.lessons), 1)  # still referenced in long term
        # soft-delete means: remove from long term after moving
        m.lessons = [item for item in m.lessons if item["id"] != lesson["id"]]
        self.assertEqual(len(m.lessons), 0)
        self.assertEqual(m.garbage_stats()["total"], 1)
        restored = m.restore_from_garbage(m.garbage[0]["id"])
        self.assertIsNotNone(restored)
        self.assertEqual(restored["id"], lesson["id"])
        self.assertEqual(len(m.lessons), 1)

    def test_purge_dry_run_vs_apply(self):
        m = ExperienceMemory(state_dir=self._tmp, garbage_max_age_rounds=10)
        m.updated_round = 50
        lesson = {"id": "x1", "claim": "old", "evidence": 1}
        m.move_to_garbage("lesson", lesson, reason="stale", round_no=30)
        candidates = m.purge_garbage(now_round=50, dry_run=True)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(m.garbage_stats()["total"], 1)  # dry-run: untouched
        m.purge_garbage(now_round=50, dry_run=False)
        self.assertEqual(m.garbage_stats()["total"], 0)

    def test_save_load_roundtrip(self):
        m = ExperienceMemory(state_dir=self._tmp)
        m.add_short_term("observation", "persist me", 1)
        m.add_lesson("persistent lesson", 2, evidence=4)
        m.add_short_term("recap", "round recap", 2)
        m.save()
        m2 = ExperienceMemory(state_dir=self._tmp).load()
        self.assertEqual(len(m2.short_term), 2)
        self.assertEqual(len(m2.lessons), 1)
        self.assertTrue(os.path.exists(os.path.join(self._tmp, "garbage.json")))


class TestBackwardCompat(TmpStateMixin, unittest.TestCase):
    def test_old_experience_json_without_new_fields(self):
        old = {
            "current_best": None,
            "lessons": [{"id": "a", "claim": "old lesson", "evidence": 3}],
            "avoid": [],
            "next": [],
            "active_hypotheses": [],
            "seen_expressions": ["rank(x)"],
            "used_hypotheses": [],
            "best_exhausted": False,
            "updated_round": 7,
        }
        with open(os.path.join(self._tmp, "experience.json"), "w",
                  encoding="utf-8") as f:
            json.dump(old, f)
        m = ExperienceMemory(state_dir=self._tmp).load()
        self.assertEqual(len(m.lessons), 1)
        self.assertEqual(m.short_term, [])
        self.assertEqual(m.garbage, [])
        self.assertEqual(m.updated_round, 7)
        # old file must round-trip through save() without errors
        m.save()
        m3 = ExperienceMemory(state_dir=self._tmp).load()
        self.assertEqual(len(m3.lessons), 1)

    def test_corrupt_experience_json_degrades_not_crashes(self):
        """2026-08-19 修复回归：experience.json 损坏时备份 + 降级启动，
        绝不崩溃（trajectory.jsonl 仍是完整证据源）。"""
        path = os.path.join(self._tmp, "experience.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{ not valid json !!!")
        m = ExperienceMemory(state_dir=self._tmp).load()
        self.assertEqual(m.lessons, [])
        self.assertEqual(m.updated_round, 0)
        # 损坏文件被稳定备份，原文件可被 save() 重建；重复启动不制造
        # 新的时间戳备份。
        m.save()
        self.assertTrue(os.path.exists(path))
        self.assertTrue(os.path.exists(path + ".corrupt"))
        backups = [p for p in os.listdir(self._tmp) if ".corrupt" in p]
        self.assertEqual(backups, ["experience.json.corrupt"])
        m2 = ExperienceMemory(state_dir=self._tmp).load()
        self.assertEqual(len(m2.lessons), 0)

    def test_wrong_shaped_memory_collections_fail_closed(self):
        with open(os.path.join(self._tmp, "experience.json"), "w",
                  encoding="utf-8") as f:
            json.dump({
                "lessons": "not-a-list",
                "avoid": ["bad", {"direction": "keep"}],
                "short_term": {"bad": True},
                "used_hypotheses": "chars-are-not-ids",
            }, f)
        with open(os.path.join(self._tmp, "garbage.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"not": "a-list"}, f)
        memory = ExperienceMemory(state_dir=self._tmp).load()
        self.assertEqual(memory.lessons, [])
        self.assertEqual(memory.avoid, [{"direction": "keep"}])
        self.assertEqual(memory.short_term, [])
        self.assertEqual(memory.used_hypotheses, set())
        self.assertEqual(memory.garbage, [])


class TestContextDigest(TmpStateMixin, unittest.TestCase):
    def test_context_contains_short_term_and_garbage(self):
        m = ExperienceMemory(state_dir=self._tmp)
        m.updated_round = 3
        m.add_short_term("recap", "round 3 recap", 3)
        lesson = m.add_lesson("lesson to be trashed", 1, evidence=1)
        m.move_to_garbage("lesson", lesson, reason="low_value", round_no=3)
        ctx = m.context()
        self.assertIn("short_term", ctx)
        self.assertEqual(len(ctx["short_term"]), 1)
        digest = ctx["garbage_digest"]
        self.assertEqual(digest["stats"]["total"], 1)
        self.assertEqual(digest["recent"][0]["reason"], "low_value")

    def test_write_context_includes_sections(self):
        m = ExperienceMemory(state_dir=self._tmp)
        m.updated_round = 4
        m.add_short_term("recap", "round 4 recap with news window 16", 4)
        m.add_lesson("stable lesson for context", 2, evidence=6)
        path = write_context(self._tmp, m, [])
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("## short_term", text)
        self.assertIn("## garbage", text)
        self.assertIn("round 4 recap", text)

    def test_write_context_honors_bounded_experiment_digest(self):
        m = ExperienceMemory(state_dir=self._tmp)
        experiments = []
        for index, fitness in enumerate((0.1, 0.9, 0.3), start=1):
            exp = Experiment(index, "h", f"rank(field{index})", {}, [f"field{index}"])
            exp.status = "DONE"
            exp.metrics = {"fitness": fitness, "sharpe": fitness}
            experiments.append(exp)
        path = write_context(self._tmp, m, experiments, context_experiments=1)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("rank(field2)", text)
        self.assertNotIn("rank(field1)", text)
        self.assertNotIn("rank(field3)", text)

    def test_context_digest_sorts_legacy_string_metrics(self):
        m = ExperienceMemory(state_dir=self._tmp)
        low = Experiment(1, "h", "rank(low)", {}, ["low"])
        low.status = "DONE"
        low.metrics = {"fitness": "0.2", "sharpe": "0.2"}
        high = Experiment(2, "h", "rank(high)", {}, ["high"])
        high.status = "DONE"
        high.metrics = {"fitness": "1.5", "sharpe": "1.5"}
        path = write_context(self._tmp, m, [low, high], context_experiments=1)
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("rank(high)", text)
        self.assertNotIn("rank(low)", text)

    def test_context_text_formatter_handles_corrupt_optional_values(self):
        self.assertEqual(_safe_text(None, 10), "")
        self.assertEqual(_safe_text(12345, 3), "123")


class TestConfirmPending(TmpStateMixin, unittest.TestCase):
    def test_pending_success_becomes_lesson(self):
        m = ExperienceMemory(state_dir=self._tmp)
        p = m.add_short_term("pending", "UNKNOWN expr needs reconciliation", 5)
        m.confirm_pending(p["id"], "success", 5,
                          detail="reconciled: real alpha sharpe=1.2")
        self.assertEqual(len(m.lessons), 1)
        self.assertEqual(len(m.short_term), 0)

    def test_pending_failed_becomes_avoid_and_lesson(self):
        m = ExperienceMemory(state_dir=self._tmp)
        p = m.add_short_term("pending", "UNKNOWN expr reconciliation", 5)
        m.confirm_pending(p["id"], "failed", 5,
                          detail="reconciled: syntax error, never submitted")
        self.assertEqual(len(m.avoid), 1)
        self.assertEqual(len(m.lessons), 1)

    def test_pending_neutral_goes_to_garbage(self):
        m = ExperienceMemory(state_dir=self._tmp)
        p = m.add_short_term("pending", "UNKNOWN expr reconciliation", 5)
        m.confirm_pending(p["id"], "neutral", 5)
        self.assertEqual(len(m.short_term), 0)
        self.assertEqual(m.garbage_stats()["total"], 1)


class TestReflectIntegration(TmpStateMixin, unittest.TestCase):
    def test_reflect_writes_recap_and_pending(self):
        m = ExperienceMemory(state_dir=self._tmp)
        reflector = Reflector(m)
        e = Experiment(1, "h-1", "rank(close)", {}, ["close"])
        e.status = "UNKNOWN"
        e.error = "ConnectionError: proxy down"
        reflector.reflect(1, {"id": "h-1", "tags": ["price"],
                              "direction": "long", "_round": 1}, [e])
        kinds = {s["kind"] for s in m.short_term}
        self.assertIn("recap", kinds)
        self.assertIn("pending", kinds)
        self.assertEqual(len(m.lessons), 0)  # UNKNOWN never writes lessons
        self.assertEqual(len(m.avoid), 0)


if __name__ == "__main__":
    unittest.main()
