"""Offline SQLite ClaimStore contract tests; no external API or credentials."""

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from plm.tiktok.claim import (
    ClaimConflict, ClaimKey, ClaimStore, InvalidClaimTransition, recovery_decision,
)
from plm.tiktok.sqlite_claim import SQLiteClaimStore


KEY = ClaimKey("tiktok_game_001", "tt-sqlite-001")
FINGERPRINT = "a" * 64
WORKER = "worker-001"
PUBLISH_ID = "v_pub_file~001"


class SQLiteClaimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "claims.sqlite3"
        self.store = SQLiteClaimStore(self.database)
        self.addCleanup(self.store.close)

    def reopen(self):
        self.store.close()
        self.store = SQLiteClaimStore(self.database)
        self.addCleanup(self.store.close)
        return self.store.get(KEY)

    def claim(self):
        return self.store.claim(KEY, FINGERPRINT, WORKER).record

    def initialized(self):
        record = self.claim()
        attempt = self.store.begin_initialize(KEY, WORKER, record.version)
        return self.store.persist_publish_id(KEY, WORKER, attempt.version, PUBLISH_ID)

    def test_matches_claim_store_protocol_and_first_idempotent_claim(self):
        contract: ClaimStore = self.store
        first = contract.claim(KEY, FINGERPRINT, WORKER)
        again = contract.claim(KEY, FINGERPRINT, WORKER)
        self.assertTrue(first.created)
        self.assertFalse(again.created)
        self.assertEqual(first.record, again.record)

    def test_db_primary_key_and_publish_id_immutability_trigger(self):
        self.claim()
        with sqlite3.connect(self.database) as other:
            with self.assertRaises(sqlite3.IntegrityError):
                other.execute("""INSERT INTO tiktok_claims
                    (platform, account_id, job_id, content_fingerprint, claimant,
                     state, version, last_operation, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'claimed', 1, 'claim', 'now', 'now')""",
                    (*("tiktok", KEY.account_id, KEY.job_id), "b" * 64, "worker-002"))
        self.initialized()
        with sqlite3.connect(self.database) as other:
            with self.assertRaises(sqlite3.IntegrityError):
                other.execute("UPDATE tiktok_claims SET publish_id = 'changed' WHERE job_id = ?", (KEY.job_id,))
        self.assertEqual(self.store.get(KEY).publish_id, PUBLISH_ID)

    def test_competing_claimant_and_fingerprint_never_replace(self):
        first = self.claim()
        with SQLiteClaimStore(self.database) as other:
            with self.assertRaises(ClaimConflict):
                other.claim(KEY, FINGERPRINT, "worker-002")
            with self.assertRaises(ClaimConflict):
                other.claim(KEY, "b" * 64, WORKER)
            self.assertEqual(other.get(KEY), first)

    def test_concurrent_independent_connections_have_one_owner(self):
        barrier = threading.Barrier(8)
        winners, conflicts, unexpected = [], [], []

        def contender(index):
            try:
                with SQLiteClaimStore(self.database) as store:
                    barrier.wait(timeout=5)
                    try:
                        result = store.claim(KEY, FINGERPRINT, f"worker-{index:03}")
                        winners.append(result)
                    except ClaimConflict:
                        conflicts.append(index)
            except Exception as exc:
                unexpected.append(exc)

        threads = [threading.Thread(target=contender, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(unexpected, [])
        self.assertEqual((len(winners), len(conflicts)), (1, 7))
        self.assertTrue(winners[0].created)
        self.assertEqual(self.store.get(KEY), winners[0].record)

    def test_stale_version_cross_connection_cas_and_invalid_transition(self):
        before = self.claim()
        with SQLiteClaimStore(self.database) as other:
            advanced = other.begin_initialize(KEY, WORKER, before.version)
            with self.assertRaises(InvalidClaimTransition):
                self.store.begin_initialize(KEY, WORKER, before.version)
            self.assertEqual(self.store.get(KEY).version, before.version + 1)
            with self.assertRaises(InvalidClaimTransition):
                other.advance(KEY, WORKER, advanced.version, "processing")

    def test_claim_survives_reopen_and_same_owner_recovers(self):
        before = self.claim()
        after = self.reopen()
        self.assertEqual(after, before)
        self.assertEqual(recovery_decision(after), "begin_initialize_candidate")
        self.assertFalse(self.store.claim(KEY, FINGERPRINT, WORKER).created)

    def test_initializing_survives_reopen_and_blocks_second_attempt(self):
        claim = self.claim()
        attempt = self.store.begin_initialize(KEY, WORKER, claim.version)
        after = self.reopen()
        self.assertEqual(after, attempt)
        self.assertEqual(recovery_decision(after), "manual_reconciliation")
        with self.assertRaises(InvalidClaimTransition):
            self.store.begin_initialize(KEY, WORKER, after.version)

    def test_publish_id_survives_reopen_and_cannot_be_overwritten(self):
        before = self.initialized()
        after = self.reopen()
        self.assertEqual(after, before)
        self.assertEqual(recovery_decision(after), "reconcile_status")
        with self.assertRaises(InvalidClaimTransition):
            self.store.persist_publish_id(KEY, WORKER, after.version, "another-id")
        with self.assertRaises(InvalidClaimTransition):
            self.store.begin_initialize(KEY, WORKER, after.version)

    def test_transfer_and_processing_survive_reopen_without_reinitialize(self):
        record = self.initialized()
        for state in ("transferring", "processing"):
            record = self.store.advance(KEY, WORKER, record.version, state)
            after = self.reopen()
            self.assertEqual(after, record)
            self.assertEqual(recovery_decision(after), "reconcile_status")
            with self.assertRaises(InvalidClaimTransition):
                self.store.begin_initialize(KEY, WORKER, after.version)

    def test_ambiguous_reconciliation_survives_reopen(self):
        claim = self.claim()
        attempt = self.store.begin_initialize(KEY, WORKER, claim.version)
        held = self.store.mark_ambiguous(KEY, WORKER, attempt.version)
        after = self.reopen()
        self.assertEqual(after, held)
        self.assertIsNone(after.publish_id)
        self.assertEqual(recovery_decision(after), "manual_reconciliation")
        with self.assertRaises(InvalidClaimTransition):
            self.store.begin_initialize(KEY, WORKER, after.version)

    def test_unknown_survives_reopen_and_never_reinitialize(self):
        record = self.initialized()
        unknown = self.store.advance(KEY, WORKER, record.version, "unknown")
        after = self.reopen()
        self.assertEqual(after, unknown)
        self.assertEqual(recovery_decision(after), "reconcile_status")
        with self.assertRaises(InvalidClaimTransition):
            self.store.begin_initialize(KEY, WORKER, after.version)

    def test_succeeded_is_terminal_after_reopen(self):
        record = self.initialized()
        processing = self.store.advance(KEY, WORKER, record.version, "processing")
        done = self.store.advance(KEY, WORKER, processing.version, "succeeded")
        self.assertEqual(self.reopen(), done)
        self.assertEqual(recovery_decision(done), "no_op")
        with self.assertRaises(InvalidClaimTransition):
            self.store.advance(KEY, WORKER, done.version, "processing")

    def test_schema_contains_only_allowlisted_fields_and_timestamp(self):
        self.claim()
        with sqlite3.connect(self.database) as other:
            columns = {row[1] for row in other.execute("PRAGMA table_info(tiktok_claims)")}
            row = other.execute("SELECT created_at, updated_at FROM tiktok_claims").fetchone()
        self.assertEqual(columns, {
            "platform", "account_id", "job_id", "content_fingerprint", "claimant",
            "state", "version", "last_operation", "publish_id", "created_at", "updated_at",
        })
        self.assertTrue(row[0] and row[1])
        self.assertNotIn("token", " ".join(columns))

    def test_invalid_identifier_and_path_traversal_rejected(self):
        for account, job in (("tiktok_secret_001", "tt-sqlite-001"),
                             ("tiktok_game_001", "../outside"),
                             ("tiktok_game_001", "access_token-001")):
            with self.subTest(account=account, job=job), self.assertRaises(ValueError):
                self.store.claim(ClaimKey(account, job), FINGERPRINT, WORKER)
        with self.assertRaises(ValueError):
            self.store.claim(KEY, FINGERPRINT, "Bearer-secret")
        with self.assertRaises(ValueError):
            self.store.claim(KEY, "secret" * 10 + "abcd", WORKER)
        self.assertIsNone(self.store.get(KEY))


if __name__ == "__main__":
    unittest.main()
