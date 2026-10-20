import threading
import unittest
from dataclasses import replace

from plm.tiktok.claim import (
    ClaimConflict, ClaimKey, InMemoryClaimStore, InvalidClaimTransition,
    recovery_decision,
)


KEY = ClaimKey("tiktok_game_001", "tt-001")
FINGERPRINT = "a" * 64
WORKER = "worker-001"


class TikTokClaimTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryClaimStore()

    def _claim(self):
        return self.store.claim(KEY, FINGERPRINT, WORKER).record

    def _initialized(self):
        record = self._claim()
        record = self.store.begin_initialize(KEY, WORKER, record.version)
        return self.store.persist_publish_id(KEY, WORKER, record.version, "v_pub_file~001")

    def test_crash_before_claim_does_not_initialize(self):
        self.assertEqual(recovery_decision(self.store.get(KEY)), "claim_candidate")

    def test_first_claim_and_safe_same_worker_reload(self):
        first = self.store.claim(KEY, FINGERPRINT, WORKER)
        second = self.store.claim(KEY, FINGERPRINT, WORKER)
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.record, second.record)
        self.assertEqual(recovery_decision(second.record), "begin_initialize_candidate")

    def test_different_worker_and_content_rejected(self):
        self._claim()
        with self.assertRaises(ClaimConflict):
            self.store.claim(KEY, FINGERPRINT, "worker-002")
        with self.assertRaises(ClaimConflict):
            self.store.claim(KEY, "b" * 64, WORKER)

    def test_concurrent_claim_has_one_winner(self):
        barrier = threading.Barrier(8)
        wins, conflicts = [], []

        def contender(index):
            barrier.wait()
            try:
                wins.append(self.store.claim(KEY, FINGERPRINT, f"worker-{index:03}").record)
            except ClaimConflict:
                conflicts.append(index)

        threads = [threading.Thread(target=contender, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual((len(wins), len(conflicts)), (1, 7))

    def test_claimed_crash_before_initialize_can_be_reloaded(self):
        record = self._claim()
        self.assertEqual(recovery_decision(self.store.get(KEY)), "begin_initialize_candidate")
        started = self.store.begin_initialize(KEY, WORKER, record.version)
        self.assertEqual(started.state, "initializing")
        self.assertEqual(recovery_decision(started), "manual_reconciliation")

    def test_publish_id_saved_once_and_crash_after_init_checks_status(self):
        record = self._initialized()
        self.assertEqual(record.publish_id, "v_pub_file~001")
        self.assertEqual(recovery_decision(self.store.get(KEY)), "reconcile_status")
        with self.assertRaises(InvalidClaimTransition):
            self.store.persist_publish_id(KEY, WORKER, record.version, "another-id")
        with self.assertRaises(InvalidClaimTransition):
            self.store.begin_initialize(KEY, WORKER, record.version)

    def test_ambiguous_response_blocks_all_automatic_reinitialize(self):
        started = self.store.begin_initialize(KEY, WORKER, self._claim().version)
        ambiguous = self.store.mark_ambiguous(KEY, WORKER, started.version)
        self.assertEqual(ambiguous.state, "reconciliation_required")
        self.assertEqual(recovery_decision(ambiguous), "manual_reconciliation")
        with self.assertRaises(InvalidClaimTransition):
            self.store.begin_initialize(KEY, WORKER, ambiguous.version)

    def test_crash_during_transfer_and_processing_never_reinitialize(self):
        record = self._initialized()
        for state in ("transferring", "processing"):
            record = self.store.advance(KEY, WORKER, record.version, state)
            self.assertEqual(recovery_decision(self.store.get(KEY)), "reconcile_status")
            with self.assertRaises(InvalidClaimTransition):
                self.store.begin_initialize(KEY, WORKER, record.version)

    def test_unknown_requires_reconciliation_only(self):
        record = self._initialized()
        unknown = self.store.advance(KEY, WORKER, record.version, "unknown")
        self.assertEqual(recovery_decision(unknown), "reconcile_status")
        with self.assertRaises(InvalidClaimTransition):
            self.store.begin_initialize(KEY, WORKER, unknown.version)

    def test_success_terminal_and_repeat_is_noop(self):
        record = self._initialized()
        record = self.store.advance(KEY, WORKER, record.version, "processing")
        done = self.store.advance(KEY, WORKER, record.version, "succeeded")
        self.assertEqual(recovery_decision(done), "no_op")
        self.assertFalse(self.store.claim(KEY, FINGERPRINT, WORKER).created)
        with self.assertRaises(InvalidClaimTransition):
            self.store.advance(KEY, WORKER, done.version, "processing")

    def test_stale_version_and_invalid_transition_rejected(self):
        record = self._initialized()
        with self.assertRaises(InvalidClaimTransition):
            self.store.advance(KEY, WORKER, record.version - 1, "processing")
        with self.assertRaises(InvalidClaimTransition):
            self.store.advance(KEY, WORKER, record.version, "initialized")
        self.assertEqual(recovery_decision(replace(record, publish_id=None)), "manual_reconciliation")

    def test_identifier_safety_and_no_secret_fields(self):
        for account, job in (("tiktok_game_001", "../escape"),
                             ("tiktok_secret_001", "tt-001"),
                             ("tiktok_game_001", "access_token-001")):
            with self.subTest(account=account, job=job), self.assertRaises(ValueError):
                ClaimKey(account, job)
        with self.assertRaises(ValueError):
            self.store.claim(KEY, "Bearer secret", WORKER)
        started = self.store.begin_initialize(KEY, WORKER, self._claim().version)
        with self.assertRaises(ValueError):
            self.store.persist_publish_id(KEY, WORKER, started.version, "access_token:fake")
        self.assertEqual(set(self.store.get(KEY).__dict__),
                         {"key", "fingerprint", "claimant_id", "state", "version", "last_operation", "publish_id"})


if __name__ == "__main__":
    unittest.main()
