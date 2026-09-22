import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.build_command_center import cell, render


class CommandCenterTests(unittest.TestCase):
    def test_latest_result_and_safe_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "yt-1-1790060279952.json").write_text(
                json.dumps(
                    {
                        "job_id": "yt-1-1790060279952",
                        "status": "succeeded",
                        "video_id": "aYSDmTcQUF0",
                        "youtube_url": "https://www.youtube.com/watch?v=aYSDmTcQUF0",
                        "failed_stage": None,
                        "error": None,
                    }
                ),
                encoding="utf-8",
            )
            page = render(root, datetime(2026, 9, 22, tzinfo=timezone.utc))
            self.assertIn("yt-1-1790060279952", page)
            self.assertIn("[動画](https://www.youtube.com/watch?v=aYSDmTcQUF0)", page)
            self.assertIn("succeeded", page)

    def test_malformed_file_and_untrusted_error_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "yt-2-1790060279952.json").write_text("{broken", encoding="utf-8")
            (root / "yt-3-1790060279952.json").write_text(
                json.dumps(
                    {
                        "job_id": "yt-3-1790060279952",
                        "status": "failed",
                        "video_id": "aYSDmTcQUF0",
                        "youtube_url": "https://evil.example/",
                        "failed_stage": "render",
                        "error": "<script>bad|row</script>\nnext",
                    }
                ),
                encoding="utf-8",
            )
            page = render(root, datetime(2026, 9, 22, tzinfo=timezone.utc))
            self.assertNotIn("yt-2-1790060279952", page)
            self.assertNotIn("evil.example", page)
            self.assertIn("&lt;script&gt;bad&#124;row&lt;/script&gt; next", page)
            self.assertEqual(cell(None), "—")
            self.assertEqual(cell("[click](https://evil.example)"),
                             "\\[click\\]\\(https://evil.example\\)")


if __name__ == "__main__":
    unittest.main()
