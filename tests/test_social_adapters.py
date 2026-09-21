import unittest
from datetime import datetime, timezone

from plm.account_manager import AccountConfig, AccountManager
from plm.social_adapters import (
    AdapterCapabilities,
    AdapterRegistry,
    AnalyticsSnapshot,
    PermanentAdapterError,
    PostRequest,
    PostResult,
    PostState,
    RetryPolicy,
    SocialAdapter,
    SocialHub,
    TransientAdapterError,
)


class FakeAdapter(SocialAdapter):
    platform = "youtube"
    capabilities = AdapterCapabilities(
        publish=True, schedule=True, status=True, analytics=True
    )

    def __init__(self, failures_before_success=0):
        self.failures_before_success = failures_before_success
        self.calls = 0

    def publish(self, account, request):
        self.calls += 1
        if self.calls <= self.failures_before_success:
            raise TransientAdapterError("temporary", code="temporary")
        return PostResult(
            account_id=account.account_id,
            platform=self.platform,
            state=PostState.PUBLISHED,
            post_id="post-123",
        )

    def schedule(self, account, request):
        self.calls += 1
        return PostResult(
            account_id=account.account_id,
            platform=self.platform,
            state=PostState.SCHEDULED,
            post_id="scheduled-123",
            scheduled_for=request.scheduled_for,
        )

    def get_post_status(self, account, post_id):
        return PostResult(
            account_id=account.account_id,
            platform=self.platform,
            state=PostState.PUBLISHED,
            post_id=post_id,
        )

    def get_analytics(self, account, post_id):
        return AnalyticsSnapshot(
            account_id=account.account_id,
            platform=self.platform,
            post_id=post_id,
            views=10,
        )


def enabled_account():
    return AccountConfig.from_dict(
        {
            "account_id": "youtube_game_001",
            "platform": "youtube",
            "display_name": "Test",
            "credential_ref": "n8n://youtube_game_001",
            "enabled": True,
        }
    )


def make_hub(adapter, *, attempts=3):
    registry = AdapterRegistry()
    registry.register(adapter)
    return SocialHub(
        AccountManager([enabled_account()]),
        registry,
        retry_policy=RetryPolicy(
            max_attempts=attempts,
            initial_delay_seconds=0,
            max_delay_seconds=0,
        ),
        sleep=lambda _seconds: None,
    )


class SocialHubTests(unittest.TestCase):
    def test_publish_returns_platform_post_id(self):
        result = make_hub(FakeAdapter()).deliver(
            PostRequest(account_id="youtube_game_001", text="unique post")
        )
        self.assertEqual(result.state, PostState.PUBLISHED)
        self.assertEqual(result.post_id, "post-123")

    def test_duplicate_successful_delivery_is_blocked(self):
        hub = make_hub(FakeAdapter())
        request = PostRequest(
            account_id="youtube_game_001",
            text="same post",
            idempotency_key="job-001",
        )
        hub.deliver(request)
        with self.assertRaisesRegex(PermanentAdapterError, "duplicate"):
            hub.deliver(request)

    def test_transient_error_is_retried_with_bound(self):
        adapter = FakeAdapter(failures_before_success=2)
        result = make_hub(adapter, attempts=3).deliver(
            PostRequest(account_id="youtube_game_001", text="retry post")
        )
        self.assertEqual(result.post_id, "post-123")
        self.assertEqual(adapter.calls, 3)

    def test_transient_error_stops_at_attempt_limit(self):
        adapter = FakeAdapter(failures_before_success=5)
        with self.assertRaises(TransientAdapterError):
            make_hub(adapter, attempts=2).deliver(
                PostRequest(account_id="youtube_game_001", text="failing post")
            )
        self.assertEqual(adapter.calls, 2)

    def test_scheduled_delivery_uses_schedule_operation(self):
        adapter = FakeAdapter()
        scheduled_for = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        result = make_hub(adapter).deliver(
            PostRequest(
                account_id="youtube_game_001",
                text="scheduled post",
                scheduled_for=scheduled_for,
            )
        )
        self.assertEqual(result.state, PostState.SCHEDULED)
        self.assertEqual(result.scheduled_for, scheduled_for)

    def test_status_and_analytics_use_common_hub_interface(self):
        hub = make_hub(FakeAdapter())
        status = hub.get_post_status("youtube_game_001", "post-123")
        analytics = hub.get_analytics("youtube_game_001", "post-123")
        self.assertEqual(status.state, PostState.PUBLISHED)
        self.assertEqual(analytics.views, 10)


if __name__ == "__main__":
    unittest.main()
