import json
import tempfile
import unittest
from pathlib import Path

from plm.entrypoints.pipeline_result import _json_file
from plm.pipeline import build_pipeline_result


class PipelineResultTests(unittest.TestCase):
    def test_pipeline_reuses_existing_workflows(self):
        workflow = (
            Path(__file__).parents[1]
            / ".github/workflows/youtube-pipeline.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("uses: ./.github/workflows/render-short.yml", workflow)
        self.assertIn("uses: ./.github/workflows/youtube-adapter.yml", workflow)
        self.assertNotIn("docker run", workflow)
        self.assertNotIn("youtube_job", workflow)
        self.assertIn("default: private", workflow)
        self.assertIn("Download YouTube Adapter result artifact", workflow)
        self.assertNotIn("needs.youtube.outputs.result_json", workflow)
        adapter_workflow = (
            Path(__file__).parents[1]
            / ".github/workflows/youtube-adapter.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("jobs.execute.outputs.result_json", adapter_workflow)

    def test_success_exposes_video_id_and_status(self):
        result = build_pipeline_result(
            job_id="job-001",
            render_job_status="success",
            youtube_job_status="success",
            render_result={
                "ok": True,
                "stages": {"render": "succeeded", "quality_gate": "succeeded"},
            },
            youtube_result={
                "ok": True,
                "result": {
                    "post_id": "video-123",
                    "state": "queued",
                    "url": "https://www.youtube.com/watch?v=video-123",
                },
            },
        )
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["job_id"], result["render_id"])
        self.assertEqual(result["video_id"], "video-123")
        self.assertEqual(result["youtube_status"], "queued")
        self.assertEqual(
            result["youtube_url"],
            "https://www.youtube.com/watch?v=video-123",
        )
        self.assertIsNone(result["failed_stage"])

    def test_youtube_result_artifact_is_loaded(self):
        payload = {
            "ok": True,
            "result": {
                "post_id": "video-123",
                "state": "queued",
                "url": "https://www.youtube.com/watch?v=video-123",
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "youtube-result.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(_json_file(str(path)), payload)

    def test_quality_gate_failure_is_preserved(self):
        result = build_pipeline_result(
            job_id="job-002",
            render_job_status="failure",
            youtube_job_status="skipped",
            render_result={
                "ok": False,
                "error": {
                    "stage": "quality_gate",
                    "type": "ValueError",
                    "message": "bad video",
                },
            },
            youtube_result=None,
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed_stage"], "quality_gate")
        self.assertIsNone(result["video_id"])

    def test_youtube_failure_is_normalized_to_adapter_stage(self):
        result = build_pipeline_result(
            job_id="job-003",
            render_job_status="success",
            youtube_job_status="failure",
            render_result={"ok": True},
            youtube_result={
                "ok": False,
                "error": {
                    "type": "PermanentAdapterError",
                    "code": "duplicate_blocked",
                    "message": "duplicate",
                },
            },
        )
        self.assertEqual(result["failed_stage"], "youtube_adapter")
        self.assertEqual(result["error"]["stage"], "youtube_adapter")
        self.assertEqual(result["error"]["code"], "duplicate_blocked")


if __name__ == "__main__":
    unittest.main()
