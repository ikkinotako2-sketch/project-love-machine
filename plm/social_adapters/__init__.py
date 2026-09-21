"""Platform-independent posting interface and orchestration."""

from .base import SocialAdapter
from .dedupe import InMemoryIdempotencyStore
from .errors import (
    AdapterError,
    PermanentAdapterError,
    TransientAdapterError,
    UnsupportedOperationError,
)
from .hub import SocialHub
from .models import (
    AdapterCapabilities,
    AnalyticsSnapshot,
    PostRequest,
    PostResult,
    PostState,
    RetryPolicy,
)
from .registry import AdapterRegistry

__all__ = [
    "AdapterCapabilities",
    "AdapterError",
    "AdapterRegistry",
    "AnalyticsSnapshot",
    "InMemoryIdempotencyStore",
    "PermanentAdapterError",
    "PostRequest",
    "PostResult",
    "PostState",
    "RetryPolicy",
    "SocialAdapter",
    "SocialHub",
    "TransientAdapterError",
    "UnsupportedOperationError",
]
