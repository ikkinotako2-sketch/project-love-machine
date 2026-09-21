from __future__ import annotations

import time
from typing import Callable

from plm.account_manager import AccountManager

from .dedupe import InMemoryIdempotencyStore, request_fingerprint
from .errors import (
    PermanentAdapterError,
    TransientAdapterError,
    UnsupportedOperationError,
)
from .models import AnalyticsSnapshot, PostRequest, PostResult, RetryPolicy
from .registry import AdapterRegistry


class SocialHub:
    """Common execution engine: account config + adapter + delivery safeguards."""

    def __init__(
        self,
        accounts: AccountManager,
        adapters: AdapterRegistry,
        *,
        idempotency_store: InMemoryIdempotencyStore | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.accounts = accounts
        self.adapters = adapters
        self.idempotency_store = idempotency_store or InMemoryIdempotencyStore()
        self.retry_policy = retry_policy or RetryPolicy()
        self._sleep = sleep

    def deliver(self, request: PostRequest) -> PostResult:
        account = self.accounts.get(request.account_id)
        if not account.enabled:
            raise PermanentAdapterError(
                f"account is disabled: {account.account_id}",
                code="account_disabled",
            )
        adapter = self.adapters.get(account.platform)
        if adapter.platform != account.platform:
            raise PermanentAdapterError(
                "adapter platform does not match account platform",
                code="platform_mismatch",
            )

        key = request_fingerprint(request)
        if not self.idempotency_store.claim(key):
            raise PermanentAdapterError(
                "duplicate delivery blocked by idempotency key",
                code="duplicate_blocked",
            )

        try:
            result = self._deliver_with_retry(adapter, account, request)
        except Exception:
            self.idempotency_store.mark_failed(key)
            raise
        self.idempotency_store.mark_succeeded(key, result.post_id)
        return result

    def get_post_status(self, account_id: str, post_id: str) -> PostResult:
        account, adapter = self._resolve(account_id)
        if not adapter.capabilities.status:
            raise UnsupportedOperationError(
                f"status lookup is not available for {adapter.platform}",
                code="status_unsupported",
            )
        return adapter.get_post_status(account, post_id)

    def get_analytics(self, account_id: str, post_id: str) -> AnalyticsSnapshot:
        account, adapter = self._resolve(account_id)
        if not adapter.capabilities.analytics:
            raise UnsupportedOperationError(
                f"analytics is not available for {adapter.platform}",
                code="analytics_unsupported",
            )
        return adapter.get_analytics(account, post_id)

    def _resolve(self, account_id: str):
        account = self.accounts.get(account_id)
        adapter = self.adapters.get(account.platform)
        if adapter.platform != account.platform:
            raise PermanentAdapterError(
                "adapter platform does not match account platform",
                code="platform_mismatch",
            )
        return account, adapter

    def _deliver_with_retry(self, adapter, account, request) -> PostResult:
        delay = self.retry_policy.initial_delay_seconds
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            try:
                if request.scheduled_for is not None:
                    if not adapter.capabilities.schedule:
                        raise UnsupportedOperationError(
                            f"scheduling is not available for {adapter.platform}",
                            code="schedule_unsupported",
                        )
                    return adapter.schedule(account, request)
                if not adapter.capabilities.publish:
                    raise PermanentAdapterError(
                        f"publishing is not available for {adapter.platform}",
                        code="publish_unsupported",
                    )
                return adapter.publish(account, request)
            except TransientAdapterError:
                if attempt >= self.retry_policy.max_attempts:
                    raise
                self._sleep(min(delay, self.retry_policy.max_delay_seconds))
                delay *= self.retry_policy.multiplier
        raise RuntimeError("unreachable retry state")
