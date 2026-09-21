import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RENDER_WORKER = Path(__file__).parents[1] / "render-worker"
sys.path.insert(0, str(RENDER_WORKER))
import render as render_module  # noqa: E402


class RenderResultTests(unittest.TestCase):
    def _environment(self):
        return {
            "INPUT_TITLE": "Pipeline test",
            "INPUT_NARRATION": "テスト音声です",
            "INPUT_SPEAKER": "1",
            "INPUT_OUTPUT_JSON": '{"width":1080,"height":1920}',
        }

    def test_success_records_render_and_quality_gate(self):
        report = {"ok": True, "width": 1080, "height": 1920}
        with tempfile.TemporaryDirectory() as directory:
            previous = os.getcwd()
            os.chdir(directory)
            try:
                with (
                    patch.dict(os.environ, self._environment(), clear=True),
                    patch.object(render_module, "generate_voice", return_value="audio.wav"),
                    patch.object(render_module, "build_video", return_value="short.mp4"),
                    patch.object(render_module, "validate_video", return_value=report),
                ):
                    render_module.main()
                result = json.loads(Path("render-result.json").read_text())
            finally:
                os.chdir(previous)
        self.assertTrue(result["ok"])
        self.assertEqual(result["stages"]["render"], "succeeded")
        self.assertEqual(result["stages"]["quality_gate"], "succeeded")

    def test_quality_gate_failure_records_exact_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = os.getcwd()
            os.chdir(directory)
            try:
                with (
                    patch.dict(os.environ, self._environment(), clear=True),
                    patch.object(render_module, "generate_voice", return_value="audio.wav"),
                    patch.object(render_module, "build_video", return_value="short.mp4"),
                    patch.object(
                        render_module,
                        "validate_video",
                        side_effect=ValueError("video file is too small"),
                    ),
                ):
                    with patch("sys.stderr"):
                        with self.assertRaises(ValueError):
                            render_module.main()
                result = json.loads(Path("render-result.json").read_text())
            finally:
                os.chdir(previous)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["stage"], "quality_gate")
        self.assertEqual(result["stages"]["quality_gate"], "failed")


if __name__ == "__main__":
    unittest.main()
