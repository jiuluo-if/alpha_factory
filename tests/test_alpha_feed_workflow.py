"""Alpha Feed 只读同步工作流的行为与安全边界测试。"""

import ast
import datetime as dt
import os
import shutil
import tempfile
import unittest
from unittest import mock

from wqb_agent.agent import Agent
from wqb_agent.alpha_feed_cache import WeeklyAlphaFeedCache
from wqb_agent.alpha_feed_workflow import (
    AlphaFeedWorkflow,
    remote_local_date,
)
from wqb_agent.daily_cache import DailyResearchCache
from wqb_agent.client import WQBQueryTooBroadError


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_ROOT = os.path.join(ROOT, "wqb_agent")


def _timestamp(value):
    return value.replace(tzinfo=dt.timezone.utc).timestamp()


class FeedReader:
    def __init__(self, rows_by_status=None):
        self.rows_by_status = rows_by_status or {"SUBMITTED": [], "UNSUBMITTED": []}
        self.calls = []
        self.write_calls = []

    def get_all_user_alphas(self, **kwargs):
        self.calls.append(dict(kwargs))
        return [dict(row) if isinstance(row, dict) else row
                for row in self.rows_by_status.get(kwargs["status"], [])]

    def submit_simulation(self, *args, **kwargs):
        self.write_calls.append(("simulation", args, kwargs))
        raise AssertionError("Alpha Feed workflow 不得提交 Simulation")

    def patch_alpha(self, *args, **kwargs):
        self.write_calls.append(("patch", args, kwargs))
        raise AssertionError("Alpha Feed workflow 不得 PATCH Alpha")


class TestAlphaFeedWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="wqb_feed_workflow_")
        self.now = _timestamp(dt.datetime(2026, 9, 9, 12, 0))
        self.clock = lambda: self.now
        self.daily = DailyResearchCache(clock=self.clock)
        self.weekly = WeeklyAlphaFeedCache(
            os.path.join(self.tmp, "weekly.json"),
            clock=self.clock,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def workflow(self, reader, *, now=None):
        return AlphaFeedWorkflow(
            alpha_reader=reader.get_all_user_alphas,
            daily_cache=self.daily,
            weekly_cache=self.weekly,
            now=now or self.clock,
        )

    def test_normal_refresh_keeps_query_split_result_schema_and_cache_fields(self):
        reader = FeedReader({
            "SUBMITTED": [
                {
                    "id": "submitted-1",
                    "status": "SUBMITTED",
                    "dateSubmitted": "2026-09-08T20:00:00-04:00",
                },
                {
                    "id": "submitted-1",
                    "status": "SUBMITTED-duplicate",
                    "dateSubmitted": "2026-09-09T20:00:00-04:00",
                },
            ],
            "UNSUBMITTED": [
                {
                    "id": "today-1",
                    "status": "UNSUBMITTED",
                    "dateCreated": "2026-09-09T08:00:00-04:00",
                },
                {
                    "id": "old-1",
                    "status": "UNSUBMITTED",
                    "dateCreated": "2026-09-03T08:00:00-04:00",
                },
            ],
        })
        workflow = self.workflow(reader, now=lambda: 1234.5)

        result = workflow.refresh(limit=20)

        self.assertEqual(result["local_date"], "2026-09-09")
        self.assertEqual(result["week_start"], "2026-09-03")
        self.assertEqual(result["refreshed_at"], 1234.5)
        self.assertEqual(result["submitted_count"], 1)
        self.assertEqual(result["today_simulated_count"], 1)
        self.assertEqual(result["weekly_simulated_count"], 2)
        self.assertEqual(result["simulation_count"], 2)
        self.assertEqual(result["source"], "/users/self/alphas")
        self.assertEqual(
            reader.calls,
            [
                {
                    "status": "SUBMITTED",
                    "limit": 20,
                    "max_results": 1000,
                    "date_submitted_after": "2026-09-02T23:59:59-04:00",
                    "date_submitted_before": "2026-09-10T00:00:00-04:00",
                },
                {
                    "status": "UNSUBMITTED",
                    "limit": 20,
                    "max_results": 1000,
                    "date_created_after": "2026-09-02T23:59:59-04:00",
                    "date_created_before": "2026-09-10T00:00:00-04:00",
                },
            ],
        )
        payload = self.weekly.load()
        self.assertEqual(payload["days"]["2026-09-09"]["simulations"][0]["alpha_id"], "today-1")
        self.assertEqual(payload["days"]["2026-09-03"]["simulations"][0]["alpha_id"], "old-1")
        self.assertEqual(payload["timezone"], "America/New_York")

    def test_refresh_updates_daily_before_weekly_and_preserves_identity(self):
        reader = FeedReader({
            "SUBMITTED": [{
                "id": "submitted-1",
                "status": "SUBMITTED",
                "dateSubmitted": "2026-09-09T08:00:00-04:00",
            }],
            "UNSUBMITTED": [{
                "id": "today-1",
                "status": "UNSUBMITTED",
                "dateCreated": "2026-09-09T08:00:00-04:00",
            }],
        })
        workflow = self.workflow(reader)
        self.assertIs(workflow.daily_cache, self.daily)
        self.assertIs(workflow.weekly_cache, self.weekly)

        with mock.patch.object(self.daily, "put_submitted_alphas", wraps=self.daily.put_submitted_alphas) as submitted, \
             mock.patch.object(self.daily, "put_simulations", wraps=self.daily.put_simulations) as simulations, \
             mock.patch.object(self.weekly, "refresh", wraps=self.weekly.refresh) as refresh:
            workflow.refresh()

        self.assertEqual(submitted.call_count, 1)
        self.assertEqual(simulations.call_count, 1)
        self.assertEqual(refresh.call_count, 1)
        self.assertEqual(self.daily.submitted_alphas()[0]["alpha_id"], "submitted-1")
        self.assertEqual(self.daily.simulations()[0]["alpha_id"], "today-1")

    def test_local_date_keeps_new_york_utc_naive_z_and_dst_semantics(self):
        self.assertEqual(remote_local_date("2026-09-09T03:59:59Z"), "2026-09-08")
        self.assertEqual(remote_local_date("2026-09-09T04:00:00Z"), "2026-09-09")
        self.assertEqual(remote_local_date("2026-09-09T03:59:59"), "2026-09-08")
        self.assertEqual(remote_local_date("2026-09-09T04:00:00+00:00"), "2026-09-09")
        self.assertEqual(remote_local_date("2026-11-02T04:59:59Z"), "2026-11-01")
        self.assertEqual(remote_local_date("2026-11-02T05:00:00Z"), "2026-11-02")
        self.assertIsNone(remote_local_date("not-a-date"))
        self.assertIsNone(remote_local_date(None))

    def test_window_is_seven_natural_new_york_days(self):
        reader = FeedReader({
            "SUBMITTED": [],
            "UNSUBMITTED": [
                {"id": "in-first-day", "dateCreated": "2026-09-03T08:00:00-04:00"},
                {"id": "outside", "dateCreated": "2026-09-02T23:59:59-04:00"},
            ],
        })
        self.workflow(reader).refresh()
        payload = self.weekly.load()
        self.assertIn("2026-09-03", payload["days"])
        self.assertNotIn("2026-09-02", payload["days"])

    def test_bad_rows_and_duplicate_ids_are_fail_soft_with_first_occurrence(self):
        reader = FeedReader({
            "SUBMITTED": [
                "not-a-row",
                {"status": "SUBMITTED", "dateSubmitted": "2026-09-09T08:00:00-04:00"},
                {"id": "submitted-invalid", "dateSubmitted": "not-a-date"},
                {"id": "submitted-1", "dateSubmitted": "2026-09-09T08:00:00-04:00"},
                {"id": "submitted-1", "dateSubmitted": "2026-09-09T08:00:00-04:00"},
            ],
            "UNSUBMITTED": [
                {"id": "sim-1", "dateCreated": "not-a-date"},
                {"id": "sim-1", "dateCreated": "2026-09-09T08:00:00-04:00"},
                {"id": "sim-2", "dateCreated": "2026-09-02T08:00:00-04:00"},
            ],
        })
        workflow = self.workflow(reader)

        result = workflow.refresh()

        self.assertEqual(result["submitted_count"], 1)
        self.assertEqual(result["today_simulated_count"], 0)
        self.assertEqual(result["weekly_simulated_count"], 0)
        self.assertEqual(self.daily.submitted_alphas()[0]["local_date"], "2026-09-09")
        self.assertEqual(self.daily.simulations(), [])
        payload = self.weekly.load()
        self.assertEqual(
            payload["days"]["2026-09-09"]["submitted_alphas"][0]["alpha_id"],
            "submitted-1",
        )
        self.assertEqual(payload["days"]["2026-09-09"]["simulations"], [])

    def test_query_too_broad_keeps_midpoint_overlap_and_depth_limit(self):
        class SplittingReader(FeedReader):
            def __init__(self):
                super().__init__({"SUBMITTED": [], "UNSUBMITTED": []})
                self.broad = {"SUBMITTED": True, "UNSUBMITTED": True}

            def get_all_user_alphas(self, **kwargs):
                self.calls.append(dict(kwargs))
                status = kwargs["status"]
                if self.broad[status]:
                    self.broad[status] = False
                    raise WQBQueryTooBroadError("too broad")
                if status == "SUBMITTED":
                    return [{"id": "submitted-1", "dateSubmitted": "2026-09-09T08:00:00-04:00"}]
                return [{"id": "sim-1", "dateCreated": "2026-09-09T08:00:00-04:00"}]

        reader = SplittingReader()
        self.workflow(reader).refresh()

        self.assertEqual(len(reader.calls), 6)
        self.assertTrue(all(call["max_results"] == 1000 for call in reader.calls))
        for status in ("SUBMITTED", "UNSUBMITTED"):
            calls = [call for call in reader.calls if call["status"] == status]
            initial = calls[0]
            left = calls[1]
            right = calls[2]
            if status == "SUBMITTED":
                start_key = "date_submitted_after"
                end_key = "date_submitted_before"
            else:
                start_key = "date_created_after"
                end_key = "date_created_before"
            left_end = dt.datetime.fromisoformat(left[end_key])
            right_start = dt.datetime.fromisoformat(right[start_key])
            self.assertEqual(left_end - right_start, dt.timedelta(seconds=2))
            self.assertEqual(initial[start_key], "2026-09-02T23:59:59-04:00")

        class AlwaysBroad(FeedReader):
            def __init__(self):
                super().__init__()

            def get_all_user_alphas(self, **kwargs):
                self.calls.append(dict(kwargs))
                raise WQBQueryTooBroadError("always broad")

        broad = AlwaysBroad()
        with self.assertRaises(WQBQueryTooBroadError):
            self.workflow(broad).refresh()
        self.assertEqual(len(broad.calls), 13)

    def test_facade_delegates_to_the_same_workflow_without_writes(self):
        reader = FeedReader({"SUBMITTED": [], "UNSUBMITTED": []})
        workflow = self.workflow(reader, now=lambda: 1234.5)
        agent = Agent.__new__(Agent)
        agent.alpha_feed_workflow = workflow

        result = agent.refresh_remote_alpha_feed(limit=7)

        self.assertEqual(result["refreshed_at"], 1234.5)
        self.assertEqual(reader.calls[0]["limit"], 7)
        self.assertEqual(reader.write_calls, [])

    def test_direct_workflow_and_agent_facade_have_equivalent_results(self):
        rows = {
            "SUBMITTED": [{
                "id": "submitted-1",
                "status": "SUBMITTED",
                "dateSubmitted": "2026-09-09T08:00:00-04:00",
            }],
            "UNSUBMITTED": [{
                "id": "sim-1",
                "status": "UNSUBMITTED",
                "dateCreated": "2026-09-09T08:00:00-04:00",
            }],
        }
        direct_reader = FeedReader(rows)
        facade_reader = FeedReader(rows)
        direct = self.workflow(direct_reader, now=lambda: 1234.5)

        facade_daily = DailyResearchCache(clock=self.clock)
        facade_weekly = WeeklyAlphaFeedCache(
            os.path.join(self.tmp, "facade-weekly.json"),
            clock=self.clock,
        )
        facade_workflow = AlphaFeedWorkflow(
            alpha_reader=facade_reader.get_all_user_alphas,
            daily_cache=facade_daily,
            weekly_cache=facade_weekly,
            now=lambda: 1234.5,
        )
        agent = Agent.__new__(Agent)
        agent.alpha_feed_workflow = facade_workflow

        direct_result = direct.refresh()
        facade_result = agent.refresh_remote_alpha_feed()
        direct_result.pop("cache_path")
        facade_result.pop("cache_path")

        self.assertEqual(direct_result, facade_result)
        self.assertEqual(self.daily.snapshot(), facade_daily.snapshot())
        self.assertEqual(self.weekly.load()["days"], facade_weekly.load()["days"])


class TestAlphaFeedWorkflowArchitecture(unittest.TestCase):
    def test_workflow_has_only_read_only_one_way_dependencies(self):
        path = os.path.join(PACKAGE_ROOT, "alpha_feed_workflow.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
            tree = ast.parse(source, filename=path)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add("." * node.level + (node.module or ""))
        for forbidden in (
            ".agent", "wqb_agent.agent", ".simulator", "wqb_agent.simulator",
            ".proposal_execution", "wqb_agent.proposal_execution",
            ".suggestion_workflow", "wqb_agent.suggestion_workflow",
            ".factory_runner", "wqb_agent.factory_runner", "main", "cli",
        ):
            self.assertNotIn(forbidden, imports)
        self.assertIn(".client", imports)
        for forbidden in (
            "submit_simulation(", "patch_alpha(", "submit_alpha(",
            "update_alpha(", "requests.post", "requests.patch",
            "WQBClient", "self.client",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("depth >= 12", source)
        self.assertIn("timedelta(minutes=1)", source)


if __name__ == "__main__":
    unittest.main()
