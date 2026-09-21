import base64
import io
import json
import unittest
from pathlib import Path
from urllib.error import HTTPError

from plm.pipeline.result_store import (
    GitHubResultStore,
    processing_result,
    public_result,
    result_path,
    validate_job_id,
)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class ResultFetcherTests(unittest.TestCase):
    def test_processing_result_has_stable_fetcher_shape(self):
        result = processing_result("job-001")
        self.assertEqual(result["status"], "processing")
        self.assertEqual(result["job_id"], result["render_id"])
        for key in (
            "video_id", "youtube_status", "youtube_url", "failed_stage", "error"
        ):
            self.assertIsNone(result[key])

    def test_public_result_keeps_only_allowlisted_fields(self):
        result = public_result(
            {
                "job_id": "job-002",
                "status": "failed",
                "video_id": None,
                "youtube_status": None,
                "youtube_url": None,
                "failed_stage": "youtube_adapter",
                "error": {
                    "stage": "youtube_adapter",
                    "type": "UploadError",
                    "code": "temporary",
                    "message": "upload failed; Bearer hidden-token",
                    "access_token": "must-not-leak",
                },
                "stages": {"oauth": {"client_secret": "must-not-leak"}},
            }
        )
        encoded = json.dumps(result)
        self.assertNotIn("must-not-leak", encoded)
        self.assertNotIn("hidden-token", encoded)
        self.assertNotIn("stages", result)
        self.assertEqual(result["error"]["code"], "temporary")

    def test_job_id_cannot_escape_result_directory(self):
        for invalid in ("../secret", "space here", "", "x" * 65):
            with self.assertRaises(ValueError):
                validate_job_id(invalid)
        self.assertEqual(result_path("safe_job-3"), "pipeline-results/safe_job-3.json")

    def test_store_creates_json_in_results_branch(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            if request.method == "GET":
                raise HTTPError(request.full_url, 404, "not found", {}, io.BytesIO())
            return _Response({"content": {"sha": "new-sha"}})

        store = GitHubResultStore(
            repository="owner/repo",
            token="test-token",
            opener=opener,
            sleep=lambda _delay: None,
        )
        store.publish("job-004", processing_result("job-004"))

        put_request = requests[-1][0]
        body = json.loads(put_request.data.decode("utf-8"))
        stored = json.loads(base64.b64decode(body["content"]).decode("utf-8"))
        self.assertEqual(body["branch"], "plm-results")
        self.assertNotIn("sha", body)
        self.assertEqual(stored["status"], "processing")
        self.assertEqual(put_request.get_header("Authorization"), "Bearer test-token")

    def test_store_updates_existing_result(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            if request.method == "GET":
                return _Response({"sha": "old-sha"})
            return _Response({"content": {"sha": "new-sha"}})

        store = GitHubResultStore(
            repository="owner/repo", token="test-token", opener=opener
        )
        store.publish(
            "job-005",
            {
                "job_id": "job-005",
                "status": "succeeded",
                "video_id": "video-123",
                "youtube_status": "private",
                "youtube_url": "https://www.youtube.com/watch?v=video-123",
                "failed_stage": None,
                "error": None,
            },
        )
        body = json.loads(requests[-1][0].data.decode("utf-8"))
        self.assertEqual(body["sha"], "old-sha")

    def test_pipeline_publishes_processing_and_final_results(self):
        workflow = (
            Path(__file__).parents[1] / ".github/workflows/youtube-pipeline.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("Publish processing result", workflow)
        self.assertIn("needs: initialize", workflow)
        self.assertIn("Publish fetchable pipeline result", workflow)
        self.assertIn("PLM_RESULT_SOURCE: pipeline-result.json", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("name: pipeline-result-${{ inputs.job_id }}", workflow)


if __name__ == "__main__":
    unittest.main()
