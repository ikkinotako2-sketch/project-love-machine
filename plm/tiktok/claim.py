"""Offline durable-claim contract and in-memory model; no posting or API calls.

The in-memory implementation is for contract tests only. A production backend
must make claim and version-checked transitions atomic and durable across all
workers before any external initialize request can be sent.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, replace
from typing import Protocol

from plm.account_manager.models import _ACCOUNT_ID_RE

from .result import _identifier, tiktok_result_path


_FINGERPRINT = re.compile(r"[0-9a-f]{64}\Z")
_CLAIMANT = re.compile(r"[A-Za-z0-9._-]{8,64}\Z")
_SENSITIVE = re.compile(r"(?i)(bearer|access.?token|refresh.?token|secret|password|authorization|upload.?url)")
_ADVANCE = {
    "initialized": {"transferring", "processing", "unknown", "failed"},
    "transferring": {"processing", "unknown", "failed"},
    "processing": {"succeeded", "unknown", "failed"},
    "unknown": {"processing", "succeeded", "failed", "reconciliation_required"},
    "reconciliation_required": {"processing", "succeeded", "failed"},
}


class ClaimConflict(ValueError):
    """A different claimant or fingerprint already owns this identity."""


class InvalidClaimTransition(ValueError):
    """An unsafe or stale mutation was refused."""


@dataclass(frozen=True)
class ClaimKey:
    account_id: str
    job_id: str
    platform: str = "tiktok"

    def __post_init__(self) -> None:
        tiktok_result_path(self.job_id)  # Reuse existing path-safe job validation.
        match = _ACCOUNT_ID_RE.fullmatch(self.account_id) if isinstance(self.account_id, str) else None
        if (self.platform != "tiktok" or match is None or match.group("platform") != "tiktok"
                or _SENSITIVE.search(self.account_id) or _SENSITIVE.search(self.job_id)):
            raise ValueError("invalid TikTok account identity")


@dataclass(frozen=True)
class ClaimRecord:
    key: ClaimKey
    fingerprint: str
    claimant_id: str
    state: str
    version: int
    last_operation: str
    publish_id: str | None = None


@dataclass(frozen=True)
class ClaimOutcome:
    record: ClaimRecord
    created: bool


class ClaimStore(Protocol):
    """Backend must implement these as transactions with a unique ClaimKey.

    Durable writes, especially begin_initialize, must commit before external
    I/O. A version is checked on every mutation. A lost response must never
    turn an existing claim into permission to initialize again.
    """

    def claim(self, key: ClaimKey, fingerprint: str, claimant_id: str) -> ClaimOutcome: ...
    def get(self, key: ClaimKey) -> ClaimRecord | None: ...
    def begin_initialize(self, key: ClaimKey, claimant_id: str, version: int) -> ClaimRecord: ...
    def persist_publish_id(self, key: ClaimKey, claimant_id: str, version: int, publish_id: str) -> ClaimRecord: ...
    def mark_ambiguous(self, key: ClaimKey, claimant_id: str, version: int) -> ClaimRecord: ...
    def advance(self, key: ClaimKey, claimant_id: str, version: int, next_state: str) -> ClaimRecord: ...


def _safe_publish_id(publish_id: str) -> str:
    _identifier(publish_id, "publish_id")
    if not publish_id or _SENSITIVE.search(publish_id):
        raise ValueError("invalid publish_id")
    return publish_id


class InMemoryClaimStore:
    """Thread-safe mock. Do not use for live posting or cross-run recovery."""

    def __init__(self) -> None:
        self._records: dict[ClaimKey, ClaimRecord] = {}
        self._lock = threading.Lock()

    def claim(self, key: ClaimKey, fingerprint: str, claimant_id: str) -> ClaimOutcome:
        if not isinstance(key, ClaimKey) or not isinstance(fingerprint, str) or not _FINGERPRINT.fullmatch(fingerprint):
            raise ValueError("invalid claim key or content fingerprint")
        if not isinstance(claimant_id, str) or not _CLAIMANT.fullmatch(claimant_id) or _SENSITIVE.search(claimant_id):
            raise ValueError("invalid claimant_id")
        with self._lock:
            record = self._records.get(key)
            if record is not None:
                if record.fingerprint != fingerprint:
                    raise ClaimConflict("same identity has a different content fingerprint")
                if record.claimant_id != claimant_id:
                    raise ClaimConflict("identity is already claimed by a different worker")
                return ClaimOutcome(record, False)
            record = ClaimRecord(key, fingerprint, claimant_id, "claimed", 1, "claim")
            self._records[key] = record
            return ClaimOutcome(record, True)

    def get(self, key: ClaimKey) -> ClaimRecord | None:
        with self._lock:
            return self._records.get(key)

    def _mutate(self, key: ClaimKey, claimant_id: str, version: int, transform) -> ClaimRecord:
        with self._lock:
            current = self._records.get(key)
            if current is None or current.claimant_id != claimant_id or current.version != version:
                raise InvalidClaimTransition("missing claim, wrong claimant, or stale version")
            updated = transform(current)
            self._records[key] = updated
            return updated

    def begin_initialize(self, key: ClaimKey, claimant_id: str, version: int) -> ClaimRecord:
        def update(current: ClaimRecord) -> ClaimRecord:
            if current.state != "claimed" or current.last_operation != "claim" or current.publish_id is not None:
                raise InvalidClaimTransition("initialize attempt already started")
            return replace(current, state="initializing", last_operation="begin_initialize", version=version + 1)
        return self._mutate(key, claimant_id, version, update)

    def persist_publish_id(self, key: ClaimKey, claimant_id: str, version: int, publish_id: str) -> ClaimRecord:
        safe_id = _safe_publish_id(publish_id)

        def update(current: ClaimRecord) -> ClaimRecord:
            if current.state != "initializing" or current.publish_id is not None:
                raise InvalidClaimTransition("publish_id can only be saved once after initialize")
            return replace(current, state="initialized", publish_id=safe_id,
                           last_operation="persist_publish_id", version=version + 1)
        return self._mutate(key, claimant_id, version, update)

    def mark_ambiguous(self, key: ClaimKey, claimant_id: str, version: int) -> ClaimRecord:
        def update(current: ClaimRecord) -> ClaimRecord:
            if current.state != "initializing":
                raise InvalidClaimTransition("ambiguous init requires an in-flight attempt")
            return replace(current, state="reconciliation_required",
                           last_operation="ambiguous_initialize", version=version + 1)
        return self._mutate(key, claimant_id, version, update)

    def advance(self, key: ClaimKey, claimant_id: str, version: int, next_state: str) -> ClaimRecord:
        def update(current: ClaimRecord) -> ClaimRecord:
            if next_state not in _ADVANCE.get(current.state, ()) or not current.publish_id:
                raise InvalidClaimTransition("invalid transition or missing publish_id")
            return replace(current, state=next_state, last_operation=f"advance:{next_state}", version=version + 1)
        return self._mutate(key, claimant_id, version, update)


def recovery_decision(record: ClaimRecord | None) -> str:
    """Pure conservative next-action hint, never permission or a side effect.

    `begin_initialize_candidate` requires separate preflight, creator consent,
    policy eligibility, and a durable begin_initialize commit before any API I/O.
    """
    if record is None:
        return "claim_candidate"
    if record.state == "claimed" and record.last_operation == "claim" and record.publish_id is None:
        return "begin_initialize_candidate"
    if record.state in {"initialized", "transferring", "processing", "unknown"}:
        return "reconcile_status" if record.publish_id else "manual_reconciliation"
    if record.state in {"initializing", "reconciliation_required"}:
        return "manual_reconciliation"
    if record.state in {"succeeded", "failed"}:
        return "no_op"
    return "manual_reconciliation"
