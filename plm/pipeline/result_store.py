from __future__ import annotations

import base64
import json
import re
import time
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


_JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_RETRYABLE_STATUS = {409, 429, 500, 502, 503, 504}
_PUBLIC_ERROR_KEYS = ("stage", "type", "code", "message")
_SECRET_TEXT = re.compile(
    r"(?i)(bearer\s+\S+|(?:access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|"
    r"authorization|cookie|password|private[_ -]?key)\s*[:=]\s*\S+)"
)


def validate_job_id(job_id: str) -> str:
    if not _JOB_ID.fullmatch(job_id):
        raise ValueError(
            "job_id must be 1-64 characters using letters, numbers, '.', '_' or '-'"
        )
    return job_id


def result_path(job_id: str) -> str:
    return f"pipeline-results/{validate_job_id(job_id)}.json"


def processing_result(job_id: str) -> dict[str, Any]:
    job_id = validate_job_id(job_id)
    return {
        "schema_version": 1,
        "job_id": job_id,
        "render_id": job_id,
        "status": "processing",
        "video_id": None,
        "youtube_status": None,
        "youtube_url": None,
        "failed_stage": None,
        "error": None,
    }


def public_result(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return only the fields that are safe and useful to the n8n fetcher."""
    job_id = validate_job_id(str(payload.get("job_id", "")))
    status = payload.get("status")
    if status not in {"processing", "succeeded", "failed"}:
        raise ValueError("status must be processing, succeeded or failed")

    raw_error = payload.get("error")
    error = None
    if isinstance(raw_error, Mapping):
        error = {}
        for key in _PUBLIC_ERROR_KEYS:
            if key not in raw_error or raw_error[key] is None:
                continue
            value = str(raw_error[key])[:1000]
            error[key] = _SECRET_TEXT.sub("[REDACTED]", value)

    return {
        "schema_version": 1,
        "job_id": job_id,
        "render_id": job_id,
        "status": status,
        "video_id": payload.get("video_id"),
        "youtube_status": payload.get("youtube_status"),
        "youtube_url": payload.get("youtube_url"),
        "failed_stage": payload.get("failed_stage"),
        "error": error,
    }


class GitHubResultStore:
    """Small GitHub Contents API client for deterministic pipeline result files."""

    def __init__(
        self,
        *,
        repository: str,
        token: str,
        branch: str = "plm-results",
        opener: Callable[..., Any] = urlopen,
        sleep: Callable[[float], None] = time.sleep,
        attempts: int = 3,
    ) -> None:
        if not repository or "/" not in repository:
            raise ValueError("repository must use owner/name format")
        if not token:
            raise ValueError("GitHub token is required")
        self.repository = repository
        self.token = token
        self.branch = branch
        self.opener = opener
        self.sleep = sleep
        self.attempts = attempts

    def publish(self, job_id: str, payload: Mapping[str, Any]) -> None:
        path = result_path(job_id)
        body = public_result(payload)
        for attempt in range(self.attempts):
            try:
                sha = self._current_sha(path)
                self._put(path, body, sha)
                return
            except HTTPError as exc:
                if exc.code not in _RETRYABLE_STATUS or attempt + 1 == self.attempts:
                    raise RuntimeError(
                        f"GitHub result publish failed with HTTP {exc.code}"
                    ) from exc
            except URLError as exc:
                if attempt + 1 == self.attempts:
                    raise RuntimeError("GitHub result publish failed due to network error") from exc
            self.sleep(2**attempt)
        raise RuntimeError("GitHub result publish failed")

    def _request(self, path: str, *, method: str = "GET", data: bytes | None = None):
        url = (
            f"https://api.github.com/repos/{self.repository}/contents/"
            f"{quote(path, safe='/')}"
        )
        if method == "GET":
            url += f"?ref={quote(self.branch, safe='')}"
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "plm-pipeline-result-fetcher",
            },
        )
        return self.opener(request, timeout=20)

    def _current_sha(self, path: str) -> str | None:
        try:
            with self._request(path) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data.get("sha")
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def _put(self, path: str, payload: Mapping[str, Any], sha: str | None) -> None:
        content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        request_body: dict[str, Any] = {
            "message": f"Update pipeline result for {payload['job_id']}",
            "content": base64.b64encode(content).decode("ascii"),
            "branch": self.branch,
        }
        if sha:
            request_body["sha"] = sha
        encoded = json.dumps(request_body).encode("utf-8")
        with self._request(path, method="PUT", data=encoded) as response:
            response.read()
