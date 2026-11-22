import unittest

from plm.tiktok import build_tiktok_result, tiktok_result_path


class TikTokOfflineResultTests(unittest.TestCase):
    def test_pending_result_has_stable_separate_path(self):
        result = build_tiktok_result(
            job_id="tt-001", status="waiting_for_consent", privacy="SELF_ONLY",
            created_at="2026-09-30T12:00:00+09:00",
        )
        self.assertEqual(tiktok_result_path(result["job_id"]), "tiktok-results/tt-001.json")
        self.assertIsNone(result["publish_id"])
        self.assertIsNone(result["post_id"])

    def test_processing_requires_persisted_publish_id(self):
        with self.assertRaises(ValueError):
            build_tiktok_result(job_id="tt-001", status="processing", privacy="SELF_ONLY",
                                created_at="2026-09-30T12:00:00Z")

    def test_public_result_rejects_secret_bearing_freeform_values(self):
        with self.assertRaises(ValueError):
            build_tiktok_result(job_id="tt-001", status="failed", privacy="SELF_ONLY",
                                created_at="2026-09-30T12:00:00Z",
                                completed_at="2026-09-30T12:01:00Z", failed_stage="status",
                                error_code="Bearer secret")
        with self.assertRaises(ValueError):
            tiktok_result_path("../pipeline-results/other")

    def test_terminal_record_can_lack_post_id(self):
        result = build_tiktok_result(
            job_id="tt-002", status="succeeded", privacy="SELF_ONLY",
            publish_id="v_pub_123", created_at="2026-09-30T12:00:00Z",
            completed_at="2026-09-30T12:01:00Z",
        )
        self.assertIsNone(result["post_id"])


if __name__ == "__main__":
    unittest.main()
