from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class PostState(str, Enum):
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AdapterCapabilities:
    publish: bool = True
    schedule: bool = False
    status: bool = False
    analytics: bool = False


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    multiplier: float = 2.0
    max_delay_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 6:
            raise ValueError("max_attempts must be between 1 and 6")
        if self.initial_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry delays cannot be negative")
        if self.multiplier < 1:
            raise ValueError("multiplier must be at least 1")


@dataclass(frozen=True)
class PostRequest:
    account_id: str
    text: str
    media_paths: tuple[str, ...] = ()
    scheduled_for: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if not self.account_id.strip():
            raise ValueError("account_id is required")
        if not self.text.strip() and not self.media_paths:
            raise ValueError("text or media is required")
        if self.scheduled_for is not None and self.scheduled_for.tzinfo is None:
            raise ValueError("scheduled_for must include timezone information")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class PostResult:
    account_id: str
    platform: str
    state: PostState
    post_id: str | None = None
    url: str | None = None
    scheduled_for: datetime | None = None
    published_at: datetime | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", MappingProxyType(dict(self.raw)))


@dataclass(frozen=True)
class AnalyticsSnapshot:
    account_id: str
    platform: str
    post_id: str
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    impressions: int | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    watch_time_seconds: float | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", MappingProxyType(dict(self.raw)))
