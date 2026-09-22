import unittest
from datetime import datetime, timedelta, timezone

from plm.improvement.collector import collect_one
from plm.improvement.core import CATEGORIES, due_slots, guidance, snapshot, valid_result, validate_ai


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


if __name__ == "__main__":
    unittest.main()
