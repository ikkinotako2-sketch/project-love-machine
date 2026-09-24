import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json

from plm.improvement.collector import collect_one
from plm.improvement.core import CATEGORIES, due_slots, guidance, snapshot, valid_result, validate_ai
from scripts.collect_youtube_metrics import run
from scripts.dispatch_delayed_1h import dispatch, selected_job


NOW = datetime(2026, 9, 22, 16, 0, tzinfo=timezone.utc)
RESULT = {
    "job_id": "yt-1024-1790063329826", "status": "succeeded",
    "video_id": "rwbrvHllunw", "youtube_url": "https://www.youtube.com/watch?v=rwbrvHllunw",
}


class FakeApi:
    ANALYTICS_API = "https://example.invalid/analytics"

    def __init__(self):
        self.calls = 0

    def get_video(self, video_id):
        self.calls += 1
        return {"id": video_id, "statistics": {"viewCount": "18", "likeCount": "2", "commentCount": "0"}}

    def _request_json(self, url):
        return {"columnHeaders": [{"name": "averageViewDuration"}], "rows": [[12.5]]}


class MetricTests(unittest.TestCase):
    def test_targeted_dispatch_does_not_collect_24h_and_cron_still_does(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "pipeline-results" / f"{RESULT['job_id']}.json"
            path.parent.mkdir()
            path.write_text(json.dumps(RESULT), encoding="utf-8")
            api = FakeApi()
            completed = NOW - timedelta(hours=1, minutes=10)
            with (patch("scripts.collect_youtube_metrics.YouTubeRestApi", return_value=api),
                  patch("scripts.collect_youtube_metrics.completed_at", return_value=completed)):
                self.assertEqual(run(root, now=NOW, job_id=RESULT["job_id"], target_slot="1h"), (1, 1))
                target = root / "improvement-results" / path.name
                state = json.loads(target.read_text(encoding="utf-8"))
                self.assertEqual(state["1h"]["status"], "collected")
                self.assertNotIn("24h", state)
                self.assertEqual(run(root, now=NOW, job_id=RESULT["job_id"], target_slot="1h"), (0, 1))
                self.assertEqual(api.calls, 1)
                self.assertEqual(run(root, now=completed + timedelta(hours=24, minutes=10)), (2, 1))
                state = json.loads(target.read_text(encoding="utf-8"))
                self.assertEqual(state["24h"]["status"], "collected")
                self.assertEqual(api.calls, 2)
            with self.assertRaises(ValueError):
                run(root, job_id="../../bad", target_slot="1h")

    def test_deduped_one_and_24_hour_snapshots(self):
        api = FakeApi()
        completed = NOW - timedelta(hours=1, minutes=15)
        state = collect_one(RESULT, {}, completed, NOW, api)
        self.assertEqual(state["1h"]["metrics"]["views"], 18)
        self.assertEqual(state["1h"]["metrics"]["averageViewDuration"], 12.5)
        self.assertNotIn("24h", state)
        self.assertEqual(collect_one(RESULT, state, completed, NOW, api), state)
        self.assertEqual(api.calls, 1)
        later = completed + timedelta(hours=24, minutes=20)
        state = collect_one(RESULT, state, completed, later, api)
        self.assertEqual(api.calls, 2)
        self.assertEqual(set(state["improvement_actions"]), set(CATEGORIES))
        self.assertEqual(state["analysis_method"], "rules")
        self.assertEqual(state["24h"]["status"], "collected")

    def test_late_schedule_does_not_claim_historical_one_hour_observation(self):
        self.assertEqual(due_slots(NOW - timedelta(hours=25), NOW, {}), [("1h", "missed"), ("24h", "collect")])
        api = FakeApi()
        state = collect_one(RESULT, {}, NOW - timedelta(hours=25), NOW, api)
        self.assertEqual(state["1h"]["status"], "missed")
        self.assertEqual(api.calls, 1)

    def test_collection_window_boundaries(self):
        completed = NOW - timedelta(hours=3)
        self.assertEqual(due_slots(completed, NOW, {}), [("1h", "collect")])
        self.assertEqual(due_slots(completed, NOW + timedelta(seconds=1), {}), [("1h", "missed")])
        self.assertEqual(due_slots(NOW - timedelta(hours=24), NOW, {}), [("1h", "missed"), ("24h", "collect")])
        self.assertEqual(due_slots(NOW - timedelta(hours=36), NOW, {}), [("1h", "missed"), ("24h", "collect")])

    def test_analytics_permission_denied_preserves_data_api_counts(self):
        class NoAnalyticsApi(FakeApi):
            def _request_json(self, url):
                raise PermissionError("analytics scope missing")

        state = collect_one(RESULT, {}, NOW - timedelta(hours=1), NOW, NoAnalyticsApi())
        self.assertEqual(state["1h"]["status"], "collected")
        self.assertEqual(state["1h"]["analytics_status"], "unavailable_or_not_authorized")
        self.assertEqual(state["1h"]["metrics"]["views"], 18)
        self.assertIsNone(state["1h"]["metrics"]["averageViewDuration"])

    def test_failure_retries_are_bounded_and_do_not_touch_pipeline_result(self):
        class TransientAdapterError(Exception):
            code = "youtube_http_503"
        class BrokenApi(FakeApi):
            def get_video(self, video_id):
                raise TransientAdapterError("do not persist raw message")
        api = BrokenApi()
        original = dict(RESULT)
        state = {}
        completed = NOW - timedelta(hours=1)
        for attempt in range(1, 4):
            state = collect_one(RESULT, state, completed, NOW, api)
            self.assertEqual(state["1h"]["attempts"], attempt)
        self.assertEqual(state["1h"]["status"], "failed")
        self.assertEqual(RESULT, original)
        self.assertEqual(state["1h"]["error"], "youtube_http_503")

    def test_missing_analytics_are_null_and_ai_requires_seven_valid_categories(self):
        metrics = snapshot({"statistics": {"viewCount": "0"}}, {}, NOW)
        self.assertEqual(metrics["views"], 0)
        self.assertIsNone(metrics["averageViewPercentage"])
        self.assertFalse(metrics["analytics_available"])
        base = guidance(None, {"metrics": metrics})
        self.assertEqual(set(base["improvement_actions"]), set(CATEGORIES))
        self.assertIsNone(validate_ai({"analysis": "x", "improvement_actions": {"hook": "x"}}))
        self.assertTrue(valid_result(RESULT))
        self.assertFalse(valid_result({**RESULT, "youtube_url": "https://example.com"}))

    def test_ai_review_is_optional_bounded_and_can_upgrade_rules_without_refetch(self):
        api = FakeApi()
        completed = NOW - timedelta(hours=24, minutes=15)
        state = collect_one(RESULT, {}, completed, NOW, api)
        self.assertEqual(state["analysis_method"], "rules")
        calls = api.calls
        reviewed = {
            "method": "gemini", "analysis": "少量データの仮説を次回検証する。",
            "improvement_actions": {key: "短い実験を行う。" for key in CATEGORIES},
        }
        upgraded = collect_one(RESULT, state, completed, NOW, api, gemini_key="mock", ai=lambda *args: reviewed)
        self.assertEqual(upgraded["analysis_method"], "gemini")
        self.assertEqual(api.calls, calls)
        self.assertEqual(upgraded["ai_attempts"], 1)


class DelayedDispatchTests(unittest.TestCase):
    def event(self):
        return {
            "repository": {"full_name": "owner/project"},
            "workflow_run": {
                "path": ".github/workflows/youtube-pipeline.yml",
                "conclusion": "success", "head_branch": "main",
                "event": "workflow_dispatch", "display_title": f"Pipeline {RESULT['job_id']}",
                "updated_at": "2026-09-22T14:50:00Z",
                "head_repository": {"full_name": "owner/project"},
            },
        }

    def test_dispatch_only_valid_successful_local_pipeline(self):
        event = self.event()
        sent = []

        class Response:
            status = 204
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        def opener(request, timeout):
            sent.append((request.full_url, json.loads(request.data)))
            return Response()

        self.assertTrue(dispatch(event, "fake-token", opener, now=NOW))
        self.assertEqual(sent[0][1], {"ref": "main", "inputs": {"job_id": RESULT["job_id"], "slot": "1h"}})
        for key, value in (("conclusion", "failure"), ("head_branch", "feature"),
                           ("path", ".github/workflows/other.yml"),
                           ("display_title", "Pipeline yt-1194-1790206647599; echo unsafe")):
            invalid = json.loads(json.dumps(event))
            invalid["workflow_run"][key] = value
            self.assertIsNone(selected_job(invalid))
            self.assertFalse(dispatch(invalid, "fake-token", opener, now=NOW))
        fork = self.event()
        fork["workflow_run"]["head_repository"]["full_name"] = "elsewhere/project"
        self.assertFalse(dispatch(fork, "fake-token", opener, now=NOW))
        self.assertEqual(len(sent), 1)

    def test_unconfigured_environment_cannot_dispatch_early(self):
        event = self.event()
        with self.assertRaisesRegex(RuntimeError, "timer missing"):
            dispatch(event, "fake-token", now=NOW - timedelta(minutes=10))


if __name__ == "__main__":
    unittest.main()
