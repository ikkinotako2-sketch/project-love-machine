"""Offline SQLite reference for ClaimStore; no TikTok client or posting flow.

Each instance owns one connection. Use only with a local, persistent database
file; this module is a contract demonstrator, not a production deployment.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from .claim import (
    _ADVANCE, _CLAIMANT, _FINGERPRINT, _SENSITIVE, _safe_publish_id,
    ClaimConflict, ClaimKey, ClaimOutcome, ClaimRecord, InvalidClaimTransition,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tiktok_claims (
    platform TEXT NOT NULL CHECK (platform = 'tiktok'),
    account_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    content_fingerprint TEXT NOT NULL CHECK (length(content_fingerprint) = 64),
    claimant TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'claimed', 'initializing', 'initialized', 'transferring', 'processing',
        'succeeded', 'failed', 'unknown', 'reconciliation_required')),
    version INTEGER NOT NULL CHECK (version > 0),
    last_operation TEXT NOT NULL,
    publish_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (platform, account_id, job_id)
);
CREATE TRIGGER IF NOT EXISTS tiktok_publish_id_immutable
BEFORE UPDATE OF publish_id ON tiktok_claims
WHEN OLD.publish_id IS NOT NULL AND NEW.publish_id IS NOT OLD.publish_id
BEGIN SELECT RAISE(ABORT, 'publish_id is immutable'); END;
"""
_KEY = "platform = ? AND account_id = ? AND job_id = ?"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _validate_key(key: ClaimKey) -> None:
    if not isinstance(key, ClaimKey):
        raise ValueError("invalid claim key")
    ClaimKey(key.account_id, key.job_id, key.platform)


def _identity(key: ClaimKey) -> tuple[str, str, str]:
    return key.platform, key.account_id, key.job_id


def _record(row: sqlite3.Row) -> ClaimRecord:
    return ClaimRecord(
        ClaimKey(row["account_id"], row["job_id"], row["platform"]),
        row["content_fingerprint"], row["claimant"], row["state"],
        row["version"], row["last_operation"], row["publish_id"],
    )


class SQLiteClaimStore:
    """File-backed reference store; never grants posting or ownership takeover."""

    def __init__(self, database: str | Path, *, timeout: float = 5.0) -> None:
        path = Path(database)
        if (str(path) == ":memory:" or not path.is_absolute() or not path.parent.is_dir()
                or not isinstance(timeout, (int, float)) or not 0 < timeout <= 60):
            raise ValueError("use an absolute path in an existing directory")
        self._connection = sqlite3.connect(str(path), timeout=timeout, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        try:
            self._connection.execute(f"PRAGMA busy_timeout = {int(timeout * 1000)}")
            # This reference expects the default rollback journal. Do not
            # silently change a pre-existing database's journal mode.
            if self._connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                raise ValueError("SQLite reference requires DELETE journal mode")
            self._connection.execute("PRAGMA synchronous = FULL")
            self._connection.executescript(_SCHEMA)
        except BaseException:
            self._connection.close()
            raise

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> SQLiteClaimStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @contextmanager
    def _write(self) -> Iterator[None]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self._connection.execute("COMMIT")
        except BaseException:
            self._connection.execute("ROLLBACK")
            raise

    def _get(self, key: ClaimKey) -> ClaimRecord | None:
        row = self._connection.execute(
            f"SELECT * FROM tiktok_claims WHERE {_KEY}", _identity(key),
        ).fetchone()
        return _record(row) if row is not None else None

    def get(self, key: ClaimKey) -> ClaimRecord | None:
        _validate_key(key)
        return self._get(key)

    def claim(self, key: ClaimKey, fingerprint: str, claimant_id: str) -> ClaimOutcome:
        _validate_key(key)
        if not isinstance(fingerprint, str) or not _FINGERPRINT.fullmatch(fingerprint):
            raise ValueError("invalid content fingerprint")
        if (not isinstance(claimant_id, str) or not _CLAIMANT.fullmatch(claimant_id)
                or _SENSITIVE.search(claimant_id)):
            raise ValueError("invalid claimant_id")
        with self._write():
            timestamp = _now()
            cursor = self._connection.execute(
                """INSERT INTO tiktok_claims
                   (platform, account_id, job_id, content_fingerprint, claimant,
                    state, version, last_operation, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'claimed', 1, 'claim', ?, ?)
                   ON CONFLICT(platform, account_id, job_id) DO NOTHING""",
                (*_identity(key), fingerprint, claimant_id, timestamp, timestamp),
            )
            record = self._get(key)
            assert record is not None
            if record.fingerprint != fingerprint:
                raise ClaimConflict("same identity has a different content fingerprint")
            if record.claimant_id != claimant_id:
                raise ClaimConflict("identity is already claimed by a different worker")
            return ClaimOutcome(record, cursor.rowcount == 1)

    def _mutate(self, key: ClaimKey, claimant_id: str, version: int,
                transform: Callable[[ClaimRecord], ClaimRecord]) -> ClaimRecord:
        _validate_key(key)
        with self._write():
            current = self._get(key)
            if (current is None or current.claimant_id != claimant_id
                    or current.version != version):
                raise InvalidClaimTransition("missing claim, wrong claimant, or stale version")
            updated = transform(current)
            cursor = self._connection.execute(
                f"""UPDATE tiktok_claims SET state = ?, version = ?,
                    last_operation = ?, publish_id = ?, updated_at = ?
                    WHERE {_KEY} AND claimant = ? AND version = ?""",
                (updated.state, updated.version, updated.last_operation,
                 updated.publish_id, _now(), *_identity(key), claimant_id, version),
            )
            if cursor.rowcount != 1:
                raise InvalidClaimTransition("compare-and-swap failed")
            return updated

    def begin_initialize(self, key: ClaimKey, claimant_id: str, version: int) -> ClaimRecord:
        def update(current: ClaimRecord) -> ClaimRecord:
            if current.state != "claimed" or current.last_operation != "claim" or current.publish_id is not None:
                raise InvalidClaimTransition("initialize attempt already started")
            return replace(current, state="initializing", last_operation="begin_initialize", version=version + 1)
        return self._mutate(key, claimant_id, version, update)

    def persist_publish_id(self, key: ClaimKey, claimant_id: str, version: int,
                           publish_id: str) -> ClaimRecord:
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

    def advance(self, key: ClaimKey, claimant_id: str, version: int,
                next_state: str) -> ClaimRecord:
        def update(current: ClaimRecord) -> ClaimRecord:
            if next_state not in _ADVANCE.get(current.state, ()) or not current.publish_id:
                raise InvalidClaimTransition("invalid transition or missing publish_id")
            return replace(current, state=next_state,
                           last_operation=f"advance:{next_state}", version=version + 1)
        return self._mutate(key, claimant_id, version, update)
