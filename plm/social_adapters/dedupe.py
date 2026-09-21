from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from enum import Enum

from .models import PostRequest


class DeliveryState(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class DeliveryRecord:
    state: DeliveryState
    post_id: str | None = None


def request_fingerprint(request: PostRequest) -> str:
    if request.idempotency_key:
        return request.idempotency_key
    payload = {
        "account_id": request.account_id,
        "text": request.text,
        "media_paths": request.media_paths,
        "scheduled_for": request.scheduled_for.isoformat()
        if request.scheduled_for
        else None,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class InMemoryIdempotencyStore:
    """Thread-safe reference store; production may replace it with a durable store."""

    def __init__(self) -> None:
        self._records: dict[str, DeliveryRecord] = {}
        self._lock = threading.Lock()

    def claim(self, key: str) -> bool:
        with self._lock:
            existing = self._records.get(key)
            if existing and existing.state in {
                DeliveryState.PENDING,
                DeliveryState.SUCCEEDED,
            }:
                return False
            self._records[key] = DeliveryRecord(DeliveryState.PENDING)
            return True

    def mark_succeeded(self, key: str, post_id: str | None) -> None:
        with self._lock:
            self._records[key] = DeliveryRecord(DeliveryState.SUCCEEDED, post_id)

    def mark_failed(self, key: str) -> None:
        with self._lock:
            self._records[key] = DeliveryRecord(DeliveryState.FAILED)

    def get(self, key: str) -> DeliveryRecord | None:
        with self._lock:
            return self._records.get(key)
