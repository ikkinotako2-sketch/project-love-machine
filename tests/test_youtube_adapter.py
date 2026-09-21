import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from plm.account_manager import AccountConfig, AccountManager
from plm.social_adapters import (
    AdapterRegistry,
    PermanentAdapterError,
    PostRequest,
    PostState,
    RetryPolicy,
    SocialHub,
    TransientAdapterError,
)
from plm.social_adapters.youtube import (
    QuotaBudget,
    YouTubeAdapter,
    YouTubeRestApi,
    classify_api_error,
)


class MockYouTubeApi:
    def __init__(self, *, failures=0):
        self.failures = failures
        self.upload_calls = 0
        self.last_metadata = None
        self.last_dates = None

    def upload_video(self, video_path, metadata, *, notify_subscribers):
        self.upload_calls += 1
        if self.upload_calls <= self.failures:
            raise TransientAdapterError("temporary", code="youtube_http_503")
        self.last_metadata = metadata
        return {
            "id": "video-123",
            "status": metadata["status"] | {"uploadStatus": "uploaded"},
            "snippet": {"publishedAt": "2026-09-21T01:00:00Z"},
        }

    def get_video(self, video_id):
        return {
            "id": video_id,
            "status": {"uploadStatus": "processed", "privacyStatus": "public"},
            "statistics": {"viewCount": "10"},
        }

    def get_analytics(self, video_id, *, start_date, end_date):
        self.last_dates = (start_date, end_date)
        return {
            "columnHeaders": [
                {"name": "views"},
                {"name": "likes"},
                {"name": "comments"},
                {"name": "shares"},
                {"name": "estimatedMinutesWatched"},
            ],
            "rows": [[100, 8, 3, 2, 12.5]],
        }


def youtube_account():
    return AccountConfig.from_dict(
        {
            "account_id": "youtube_game_001",
            "platform": "youtube",
            "display_name": "YouTube Game",
            "credential_ref": "env://PLM_YOUTUBE_OAUTH_JSON",
            "enabled": True,
            "adapter_config": {"analytics_days": 28},
        }
    )


def request_for(path, *, scheduled_for=None, key="job-001"):
    return PostRequest(
        account_id="youtube_game_001",
        text="description",
        media_paths=(str(path),),
        scheduled_for=scheduled_for,
        idempotency_key=key,
        metadata={
            "title": "Test Short",
            "description": "description",
            "tags": ["game", "shorts"],
            "made_for_kids": False,
            "contains_synthetic_media": True,
            "notify_subscribers": False,
        },
    )


def make_hub(api, *, now=None, attempts=3):
    registry = AdapterRegistry()
    registry.register(
        YouTubeAdapter(
            api,
            now=now or (lambda: datetime(2026, 9, 21, tzinfo=timezone.utc)),
            today=lambda: date(2026, 9, 21),
        )
    )
    return SocialHub(
        AccountManager([youtube_account()]),
        registry,
        retry_policy=RetryPolicy(
            max_attempts=attempts,
            initial_delay_seconds=0,
            max_delay_seconds=0,
        ),
        sleep=lambda _seconds: None,
    )


class YouTubeAdapterTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        handle.write(b"test-video")
        handle.close()
        self.video_path = Path(handle.name)

    def tearDown(self):
        self.video_path.unlink(missing_ok=True)

    def test_upload_returns_video_id_and_safe_defaults(self):
        api = MockYouTubeApi()
        result = make_hub(api).deliver(request_for(self.video_path))
        self.assertEqual(result.post_id, "video-123")
        self.assertEqual(result.state, PostState.QUEUED)
        self.assertEqual(api.last_metadata["status"]["privacyStatus"], "private")
        self.assertTrue(api.last_metadata["status"]["containsSyntheticMedia"])

    def test_scheduled_upload_is_private_with_future_publish_at(self):
        api = MockYouTubeApi()
        scheduled = datetime(2026, 9, 22, 12, 30, tzinfo=timezone.utc)
        result = make_hub(api).deliver(
            request_for(self.video_path, scheduled_for=scheduled)
        )
        self.assertEqual(result.state, PostState.SCHEDULED)
        self.assertEqual(api.last_metadata["status"]["privacyStatus"], "private")
        self.assertEqual(api.last_metadata["status"]["publishAt"], "2026-09-22T12:30:00Z")

    def test_past_schedule_is_permanent_and_not_uploaded(self):
        api = MockYouTubeApi()
        past = datetime(2026, 9, 20, tzinfo=timezone.utc)
        with self.assertRaises(PermanentAdapterError):
            make_hub(api).deliver(
                request_for(self.video_path, scheduled_for=past)
            )
        self.assertEqual(api.upload_calls, 0)

    def test_transient_error_only_is_retried(self):
        api = MockYouTubeApi(failures=1)
        result = make_hub(api, attempts=2).deliver(request_for(self.video_path))
        self.assertEqual(result.post_id, "video-123")
        self.assertEqual(api.upload_calls, 2)

    def test_duplicate_idempotency_key_is_blocked(self):
        api = MockYouTubeApi()
        hub = make_hub(api)
        request = request_for(self.video_path)
        hub.deliver(request)
        with self.assertRaisesRegex(PermanentAdapterError, "duplicate"):
            hub.deliver(request)
        self.assertEqual(api.upload_calls, 1)

    def test_status_maps_processed_public_to_published(self):
        result = make_hub(MockYouTubeApi()).get_post_status(
            "youtube_game_001", "video-123"
        )
        self.assertEqual(result.state, PostState.PUBLISHED)
        self.assertEqual(result.post_id, "video-123")

    def test_analytics_maps_metrics_and_watch_time(self):
        api = MockYouTubeApi()
        result = make_hub(api).get_analytics("youtube_game_001", "video-123")
        self.assertEqual(result.views, 100)
        self.assertEqual(result.likes, 8)
        self.assertEqual(result.watch_time_seconds, 750.0)
        self.assertEqual(api.last_dates, ("2026-08-24", "2026-09-20"))

    def test_audience_and_synthetic_flags_are_required(self):
        request = request_for(self.video_path)
        metadata = dict(request.metadata)
        metadata.pop("made_for_kids")
        unsafe = PostRequest(
            account_id=request.account_id,
            text=request.text,
            media_paths=request.media_paths,
            idempotency_key="job-002",
            metadata=metadata,
        )
        with self.assertRaisesRegex(PermanentAdapterError, "made_for_kids"):
            make_hub(MockYouTubeApi()).deliver(unsafe)

    def test_http_error_classification(self):
        transient = classify_api_error(503, {"error": {}})
        quota = classify_api_error(
            403, {"error": {"errors": [{"reason": "quotaExceeded"}]}}
        )
        invalid = classify_api_error(400, {"error": {}})
        self.assertIsInstance(transient, TransientAdapterError)
        self.assertIsInstance(quota, PermanentAdapterError)
        self.assertIsInstance(invalid, PermanentAdapterError)

    def test_quota_guard_stops_before_an_extra_upload(self):
        budget = QuotaBudget(upload_limit=1)
        budget.consume_upload()
        with self.assertRaisesRegex(PermanentAdapterError, "quota guard"):
            budget.consume_upload()

    def test_resumable_upload_checks_same_session_before_resuming(self):
        class TokenProvider:
            def get_access_token(self):
                return "test-token"

        api = YouTubeRestApi(
            TokenProvider(), upload_resume_attempts=2, sleep=lambda _seconds: None
        )
        offsets = []

        def stream(_url, _path, _mime, offset, _total):
            offsets.append(offset)
            if len(offsets) == 1:
                raise OSError("connection lost")
            return 201, {}, b'{"id":"video-123"}'

        api._stream_file = stream
        api._query_upload_status = lambda _url, _total: (
            308,
            {"Range": "bytes=0-4"},
            b"",
        )
        result = api._complete_resumable_upload(
            "https://upload.example/session", str(self.video_path), "video/mp4"
        )
        self.assertEqual(result["id"], "video-123")
        self.assertEqual(offsets, [0, 5])


if __name__ == "__main__":
    unittest.main()
