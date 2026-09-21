from __future__ import annotations

from abc import ABC, abstractmethod

from plm.account_manager import AccountConfig

from .errors import UnsupportedOperationError
from .models import AdapterCapabilities, AnalyticsSnapshot, PostRequest, PostResult


class SocialAdapter(ABC):
    """Contract implemented by every platform-specific PLM adapter."""

    platform: str
    capabilities: AdapterCapabilities

    @abstractmethod
    def publish(self, account: AccountConfig, request: PostRequest) -> PostResult:
        """Publish immediately and return the platform post ID when available."""

    def schedule(self, account: AccountConfig, request: PostRequest) -> PostResult:
        raise UnsupportedOperationError(
            f"{self.platform} scheduling is not implemented or verified",
            code="schedule_unsupported",
        )

    def get_post_status(self, account: AccountConfig, post_id: str) -> PostResult:
        raise UnsupportedOperationError(
            f"{self.platform} status lookup is not implemented or verified",
            code="status_unsupported",
        )

    def get_analytics(
        self, account: AccountConfig, post_id: str
    ) -> AnalyticsSnapshot:
        raise UnsupportedOperationError(
            f"{self.platform} analytics is not implemented or verified",
            code="analytics_unsupported",
        )
