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


class RenderQualityTests(unittest.TestCase):
    def test_keyword_palette_is_stable_and_missing_audio_asset_falls_back(self):
        import ffmpeg_builder
        first = ffmpeg_builder.PALETTES[
            int.from_bytes(__import__('hashlib').sha256(b'study').digest()[:2], 'big') % len(ffmpeg_builder.PALETTES)
        ]
        self.assertEqual(len(first), 3)
        self.assertIsNone(ffmpeg_builder._asset_path({'asset': '../unlicensed.mp3'}))
        self.assertIsNone(ffmpeg_builder._asset_path({'asset': 'missing.mp3'}))

    def test_caption_emphasis_escapes_untrusted_ass_text(self):
        import ffmpeg_builder
        text = ffmpeg_builder._caption_text({'text': '勉強{\\bad}を続ける', 'emphasis_words': ['勉強']})
        self.assertIn('\\c&H6ACBFF&', text)
        self.assertIn(r'\{\\bad\}', text)

    @unittest.skipUnless(__import__('shutil').which('ffmpeg') and __import__('shutil').which('ffprobe'), 'FFmpeg unavailable')
    def test_real_render_and_quality_gate(self):
        import subprocess
        import ffmpeg_builder
        import quality_gate
        with tempfile.TemporaryDirectory() as directory:
            previous = os.getcwd()
            os.chdir(directory)
            try:
                subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                                'sine=frequency=440:duration=2', 'audio.wav'], check=True)
                payload = {'scenes': [
                    {'start': 0, 'end': 1, 'visual_keyword': 'study', 'caption': '一つ目'},
                    {'start': 1, 'end': 2, 'visual_keyword': 'rain', 'caption': '二つ目'}],
                    'bgm': {'asset': 'missing.mp3'}, 'output': {'width': 1080, 'height': 1920, 'fps': 30}}
                ffmpeg_builder.build_video(payload, 'audio.wav', 'short.mp4')
                report = quality_gate.validate_video('short.mp4')
                self.assertEqual((report['width'], report['height'], report['fps']), (1080, 1920, 30))
                self.assertTrue(report['subtitles'])
                self.assertGreater(report['max_sample_luma'], 25)
                self.assertGreater(report['mean_audio_db'], -38)
                os.remove('captions.ass')
                with self.assertRaisesRegex(ValueError, 'subtitles missing'):
                    quality_gate.validate_video('short.mp4')
            finally:
                os.chdir(previous)
