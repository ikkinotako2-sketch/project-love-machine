from __future__ import annotations

import http.client
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, Protocol

from plm.social_adapters.errors import PermanentAdapterError, TransientAdapterError

from .quota import QuotaBudget


TRANSIENT_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})


class YouTubeApi(Protocol):
    def upload_video(
        self,
        video_path: str,
        metadata: Mapping[str, Any],
        *,
        notify_subscribers: bool,
    ) -> Mapping[str, Any]: ...

    def get_video(self, video_id: str) -> Mapping[str, Any]: ...

    def get_analytics(
        self, video_id: str, *, start_date: str, end_date: str
    ) -> Mapping[str, Any]: ...


def _error_reason(payload: Any) -> str | None:
    try:
        errors = payload["error"]["errors"]
        if errors and isinstance(errors[0].get("reason"), str):
            return errors[0]["reason"]
    except (KeyError, IndexError, TypeError):
        return None
    return None


def classify_api_error(status: int, payload: Any) -> Exception:
    reason = _error_reason(payload)
    code = f"youtube_{reason or 'http_' + str(status)}"
    message = f"YouTube API request failed: HTTP {status}"
    if reason:
        message += f" ({reason})"
    if status in TRANSIENT_HTTP_STATUSES:
        return TransientAdapterError(message, code=code)
    return PermanentAdapterError(message, code=code)


class YouTubeRestApi:
    DATA_API = "https://www.googleapis.com/youtube/v3/videos"
    UPLOAD_API = "https://www.googleapis.com/upload/youtube/v3/videos"
    ANALYTICS_API = "https://youtubeanalytics.googleapis.com/v2/reports"

    def __init__(
        self,
        token_provider,
        *,
        quota: QuotaBudget | None = None,
        upload_resume_attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 1 <= upload_resume_attempts <= 6:
            raise ValueError("upload_resume_attempts must be between 1 and 6")
        self.token_provider = token_provider
        self.quota = quota or QuotaBudget()
        self.upload_resume_attempts = upload_resume_attempts
        self._sleep = sleep

    def upload_video(
        self,
        video_path: str,
        metadata: Mapping[str, Any],
        *,
        notify_subscribers: bool,
    ) -> Mapping[str, Any]:
        self.quota.consume_upload()
        size = os.path.getsize(video_path)
        mime_type = mimetypes.guess_type(video_path)[0] or "application/octet-stream"
        query = urllib.parse.urlencode(
            {
                "uploadType": "resumable",
                "part": "snippet,status",
                "notifySubscribers": str(notify_subscribers).lower(),
            }
        )
        request = urllib.request.Request(
            f"{self.UPLOAD_API}?{query}",
            data=json.dumps(metadata).encode("utf-8"),
            headers={
                **self._auth_headers(),
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(size),
                "X-Upload-Content-Type": mime_type,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                upload_url = response.headers.get("Location")
        except urllib.error.HTTPError as exc:
            raise self._from_http_error(exc) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TransientAdapterError(
                "failed to start resumable YouTube upload",
                code="youtube_upload_session_connection",
            ) from exc
        if not upload_url:
            raise PermanentAdapterError(
                "YouTube did not return a resumable upload URL",
                code="youtube_upload_location_missing",
            )
        return self._complete_resumable_upload(upload_url, video_path, mime_type)

    def get_video(self, video_id: str) -> Mapping[str, Any]:
        self.quota.consume_data_units(1)
        query = urllib.parse.urlencode(
            {"part": "status,processingDetails,statistics,snippet", "id": video_id}
        )
        payload = self._request_json(f"{self.DATA_API}?{query}")
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list) or not items:
            raise PermanentAdapterError(
                f"YouTube video was not found: {video_id}",
                code="youtube_video_not_found",
            )
        return items[0]

    def get_analytics(
        self, video_id: str, *, start_date: str, end_date: str
    ) -> Mapping[str, Any]:
        query = urllib.parse.urlencode(
            {
                "ids": "channel==MINE",
                "startDate": start_date,
                "endDate": end_date,
                "metrics": "views,likes,comments,shares,estimatedMinutesWatched",
                "filters": f"video=={video_id}",
            }
        )
        return self._request_json(f"{self.ANALYTICS_API}?{query}")

    def _complete_resumable_upload(
        self, upload_url: str, video_path: str, mime_type: str
    ) -> Mapping[str, Any]:
        total = os.path.getsize(video_path)
        offset = 0
        delay = 1.0
        for attempt in range(1, self.upload_resume_attempts + 1):
            try:
                status, headers, body = self._stream_file(
                    upload_url, video_path, mime_type, offset, total
                )
            except (OSError, TimeoutError, http.client.HTTPException):
                recovered = self._recover_upload(upload_url, total)
                if isinstance(recovered, Mapping):
                    return recovered
                offset, headers = recovered
                status, body = 308, b""

            if status in {200, 201}:
                return self._decode_json(body)
            if status == 308:
                offset = self._next_offset(headers.get("Range"))
            elif status in TRANSIENT_HTTP_STATUSES:
                recovered = self._recover_upload(upload_url, total)
                if isinstance(recovered, Mapping):
                    return recovered
                offset, headers = recovered
            else:
                payload = self._decode_json(body, default={})
                raise classify_api_error(status, payload)

            if attempt < self.upload_resume_attempts:
                retry_after = headers.get("Retry-After")
                self._sleep(float(retry_after) if retry_after else delay)
                delay = min(delay * 2, 30)

        raise PermanentAdapterError(
            "resumable upload outcome is unknown; automatic restart blocked to prevent a duplicate",
            code="youtube_upload_outcome_unknown",
        )

    def _recover_upload(
        self, upload_url: str, total: int
    ) -> Mapping[str, Any] | tuple[int, Mapping[str, str]]:
        """Confirm the same session before resuming; never start a second video."""
        delay = 1.0
        for attempt in range(1, self.upload_resume_attempts + 1):
            try:
                status, headers, body = self._query_upload_status(upload_url, total)
            except (OSError, TimeoutError, http.client.HTTPException):
                status, headers, body = 503, {}, b""
            if status in {200, 201}:
                return self._decode_json(body)
            if status == 308:
                return self._next_offset(headers.get("Range")), headers
            if status not in TRANSIENT_HTTP_STATUSES:
                raise classify_api_error(
                    status, self._decode_json(body, default={})
                )
            if attempt < self.upload_resume_attempts:
                retry_after = headers.get("Retry-After")
                self._sleep(float(retry_after) if retry_after else delay)
                delay = min(delay * 2, 30)
        raise PermanentAdapterError(
            "resumable upload outcome is unknown; automatic restart blocked to prevent a duplicate",
            code="youtube_upload_outcome_unknown",
        )

    def _stream_file(
        self,
        upload_url: str,
        video_path: str,
        mime_type: str,
        offset: int,
        total: int,
    ) -> tuple[int, Mapping[str, str], bytes]:
        parsed = urllib.parse.urlsplit(upload_url)
        connection_class = (
            http.client.HTTPSConnection
            if parsed.scheme == "https"
            else http.client.HTTPConnection
        )
        connection = connection_class(parsed.netloc, timeout=120)
        path = urllib.parse.urlunsplit(("", "", parsed.path, parsed.query, ""))
        remaining = total - offset
        connection.putrequest("PUT", path)
        connection.putheader("Authorization", f"Bearer {self.token_provider.get_access_token()}")
        connection.putheader("Content-Type", mime_type)
        connection.putheader("Content-Length", str(remaining))
        if offset:
            connection.putheader("Content-Range", f"bytes {offset}-{total - 1}/{total}")
        connection.endheaders()
        with open(video_path, "rb") as video:
            video.seek(offset)
            while True:
                chunk = video.read(1024 * 1024)
                if not chunk:
                    break
                connection.send(chunk)
        response = connection.getresponse()
        body = response.read()
        headers = {key: value for key, value in response.getheaders()}
        status = response.status
        connection.close()
        return status, headers, body

    def _query_upload_status(
        self, upload_url: str, total: int
    ) -> tuple[int, Mapping[str, str], bytes]:
        parsed = urllib.parse.urlsplit(upload_url)
        connection = http.client.HTTPSConnection(parsed.netloc, timeout=30)
        path = urllib.parse.urlunsplit(("", "", parsed.path, parsed.query, ""))
        connection.putrequest("PUT", path)
        connection.putheader("Authorization", f"Bearer {self.token_provider.get_access_token()}")
        connection.putheader("Content-Length", "0")
        connection.putheader("Content-Range", f"bytes */{total}")
        connection.endheaders()
        response = connection.getresponse()
        body = response.read()
        headers = {key: value for key, value in response.getheaders()}
        status = response.status
        connection.close()
        return status, headers, body

    def _request_json(self, url: str) -> Mapping[str, Any]:
        request = urllib.request.Request(url, headers=self._auth_headers(), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return self._decode_json(response.read())
        except urllib.error.HTTPError as exc:
            raise self._from_http_error(exc) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TransientAdapterError(
                "temporary YouTube API connection failure",
                code="youtube_connection_error",
            ) from exc

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token_provider.get_access_token()}"}

    @staticmethod
    def _decode_json(body: bytes, *, default=None):
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            if default is not None:
                return default
            raise PermanentAdapterError(
                "YouTube API returned invalid JSON",
                code="youtube_invalid_response",
            )

    @staticmethod
    def _next_offset(range_header: str | None) -> int:
        if not range_header:
            return 0
        match = re.fullmatch(r"bytes=\d+-(\d+)", range_header)
        if not match:
            raise PermanentAdapterError(
                "YouTube upload returned an invalid Range header",
                code="youtube_invalid_upload_range",
            )
        return int(match.group(1)) + 1

    @staticmethod
    def _from_http_error(exc: urllib.error.HTTPError) -> Exception:
        body = exc.read()
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        return classify_api_error(exc.code, payload)
