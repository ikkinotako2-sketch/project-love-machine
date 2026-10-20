import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from plm.tiktok.preflight import (
    check_preflight, preflight_path, preflight_result, probe_media,
    validate_media, validate_metadata,
)
from plm.tiktok.state import validate_transition


NOW = datetime(2026, 9, 30, 4, 0, tzinfo=timezone.utc)


def media(**overrides):
    return {
        "extension": ".mp4", "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "major_brand": "isom", "codec": "h264", "width": 1080,
        "height": 1920, "fps": 30.0, "duration": 40.0, "size": 8_000_000,
        **overrides,
    }


def creator(**overrides):
    return {
        "privacy_level_options": ["SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS"],
        "max_video_post_duration_sec": 180,
        "comment_disabled": False, "duet_disabled": True, "stitch_disabled": False,
        "fetched_at": "2026-09-30T03:59:00Z", **overrides,
    }


def metadata(**overrides):
    return {
        "title": "Creator-edited caption", "privacy_level": "SELF_ONLY",
        "is_aigc": True, "brand_content_toggle": False,
        "brand_organic_toggle": False, "disable_comment": False,
        "disable_duet": True, "disable_stitch": False, **overrides,
    }


def evidence(**overrides):
    return {
        "preview_rendered": True, "caption_editable": True,
        "privacy_selected_by_creator": True, "disclosures_presented": True,
        "consent_record_id": "review-event-001",
        "consented_at": "2026-09-30T03:59:30Z", **overrides,
    }


class MediaTests(unittest.TestCase):
    def test_valid_media_metadata(self):
        self.assertEqual(validate_media(media(), 180), set())

    def test_invalid_codec_and_container(self):
        self.assertEqual(validate_media(media(extension=".avi", codec="mpeg4"), 180),
                         {"container_unsupported", "codec_unsupported"})

    def test_invalid_resolution_fps_duration_and_size(self):
        reasons = validate_media(media(width=320, fps=22, duration=181, size=4_000_000_001), 180)
        self.assertEqual(reasons, {"resolution_unsupported", "fps_unsupported",
                                   "duration_unsupported", "file_oversized"})

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
    def test_probe_reads_real_video_not_renderer_assumptions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "short.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "color=c=black:s=360x640:r=30:d=1", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", str(path)], check=True, timeout=30)
            info = probe_media(path)
            self.assertEqual((info["codec"], info["width"], info["height"]),
                             ("h264", 360, 640))
            self.assertEqual(info["size"], path.stat().st_size)
            self.assertEqual(validate_media(info, 180), set())


class MetadataTests(unittest.TestCase):
    def test_caption_utf16_limit(self):
        self.assertIn("caption_too_long", validate_metadata(metadata(title="🙂" * 1101), creator()))

    def test_unsupported_and_creator_unavailable_privacy(self):
        self.assertIn("privacy_unsupported", validate_metadata(metadata(privacy_level="public"), creator()))
        self.assertIn("privacy_unavailable", validate_metadata(metadata(privacy_level="PUBLIC_TO_EVERYONE"), creator()))

    def test_missing_ai_and_commercial_disclosures(self):
        reasons = validate_metadata(metadata(is_aigc=None, brand_organic_toggle=None), creator())
        self.assertIn("ai_disclosure_missing", reasons)
        self.assertIn("commercial_disclosure_missing", reasons)

    def test_interaction_restriction_and_private_branded_content(self):
        reasons = validate_metadata(metadata(disable_duet=False, brand_content_toggle=True), creator())
        self.assertEqual(reasons, {"interaction_unavailable", "commercial_privacy_conflict"})


class PreflightTests(unittest.TestCase):
    def test_evidence_supplied_offline_pass_has_no_raw_data(self):
        result = check_preflight(job_id="tt-001", media_path="short.mp4",
                                 metadata=metadata(), creator_info=creator(), evidence=evidence(),
                                 now=NOW, probe=lambda _: media())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["failure_reasons"], [])
        self.assertNotIn("Creator-edited caption", json.dumps(result))
        self.assertEqual(preflight_path("tt-001"), "tiktok-preflight/tt-001.json")

    def test_missing_consent_preview_and_stale_creator_info_fail_closed(self):
        result = check_preflight(job_id="tt-001", media_path="short.mp4", metadata=metadata(),
                                 creator_info=creator(fetched_at="2026-09-29T03:59:00Z"),
                                 evidence=evidence(consent_record_id=None, preview_rendered=False),
                                 now=NOW, probe=lambda _: media())
        self.assertTrue({"consent_missing", "preview_missing", "creator_info_stale"}
                        <= set(result["failure_reasons"]))

    def test_missing_file_fails_without_a_network_call(self):
        result = check_preflight(job_id="tt-001", media_path="does-not-exist.mp4",
                                 metadata=metadata(), creator_info=creator(), evidence=evidence(), now=NOW)
        self.assertIn("media_missing", result["failure_reasons"])

    def test_secret_bearing_reason_and_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            preflight_result("tt-001", {"Bearer secret"}, NOW)
        with self.assertRaises(ValueError):
            preflight_path("../other")

    def test_invalid_transition_and_unknown_reinitialization(self):
        for current, target in (("waiting_for_consent", "processing"),
                                ("unknown", "initialized"), ("succeeded", "initialized")):
            with self.subTest(current=current, target=target), self.assertRaises(ValueError):
                validate_transition(current, target)
        validate_transition("unknown", "processing")


if __name__ == "__main__":
    unittest.main()
