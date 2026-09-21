from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from plm.account_manager import AccountConfig
from plm.social_adapters.base import SocialAdapter
from plm.social_adapters.errors import PermanentAdapterError
from plm.social_adapters.models import (
    AdapterCapabilities,
    AnalyticsSnapshot,
    PostRequest,
    PostResult,
    PostState,
)

from .api import YouTubeApi


class YouTubeAdapter(SocialAdapter):
    platform = "youtube"
    capabilities = AdapterCapabilities(
        publish=True, schedule=True, status=True, analytics=True
    )

    def __init__(
        self,
        api: YouTubeApi,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        today: Callable[[], date] = date.today,
    ) -> None:
        self.api = api
        self._now = now
        self._today = today

    def publish(self, account: AccountConfig, request: PostRequest) -> PostResult:
        metadata = self._build_metadata(request, scheduled=False)
        resource = self.api.upload_video(
            self._video_path(request),
            metadata,
            notify_subscribers=self._notify_subscribers(request),
        )
        return self._post_result(account, resource)

    def schedule(self, account: AccountConfig, request: PostRequest) -> PostResult:
        if request.scheduled_for is None:
            raise PermanentAdapterError(
                "scheduled_for is required", code="youtube_schedule_time_missing"
            )
        if request.scheduled_for <= self._now():
            raise PermanentAdapterError(
                "YouTube publishAt must be in the future",
                code="youtube_schedule_time_not_future",
            )
        metadata = self._build_metadata(request, scheduled=True)
        resource = self.api.upload_video(
            self._video_path(request),
            metadata,
            notify_subscribers=self._notify_subscribers(request),
        )
        return self._post_result(account, resource, request.scheduled_for)

    def get_post_status(self, account: AccountConfig, post_id: str) -> PostResult:
        return self._post_result(account, self.api.get_video(post_id))

    def get_analytics(
        self, account: AccountConfig, post_id: str
    ) -> AnalyticsSnapshot:
        days = int(account.adapter_config.get("analytics_days", 28))
        if not 1 <= days <= 365:
            raise PermanentAdapterError(
                "analytics_days must be between 1 and 365",
                code="youtube_analytics_days_invalid",
            )
        end = self._today() - timedelta(days=1)
        start = end - timedelta(days=days - 1)
        payload = self.api.get_analytics(
            post_id, start_date=start.isoformat(), end_date=end.isoformat()
        )
        values = self._analytics_values(payload)
        minutes = values.get("estimatedMinutesWatched")
        return AnalyticsSnapshot(
            account_id=account.account_id,
            platform=self.platform,
            post_id=post_id,
            views=self._optional_int(values.get("views")),
            likes=self._optional_int(values.get("likes")),
            comments=self._optional_int(values.get("comments")),
            shares=self._optional_int(values.get("shares")),
            watch_time_seconds=float(minutes) * 60 if minutes is not None else None,
            raw=payload,
        )

    def _build_metadata(
        self, request: PostRequest, *, scheduled: bool
    ) -> dict[str, Any]:
        title = request.metadata.get("title")
        if not isinstance(title, str) or not title.strip():
            raise PermanentAdapterError(
                "YouTube title is required in metadata.title",
                code="youtube_title_missing",
            )
        if len(title) > 100:
            raise PermanentAdapterError(
                "YouTube title exceeds 100 characters",
                code="youtube_title_too_long",
            )
        made_for_kids = request.metadata.get("made_for_kids")
        synthetic = request.metadata.get("contains_synthetic_media")
        if not isinstance(made_for_kids, bool):
            raise PermanentAdapterError(
                "metadata.made_for_kids must be explicitly true or false",
                code="youtube_audience_missing",
            )
        if not isinstance(synthetic, bool):
            raise PermanentAdapterError(
                "metadata.contains_synthetic_media must be explicitly true or false",
                code="youtube_synthetic_disclosure_missing",
            )
        tags = request.metadata.get("tags", [])
        if not isinstance(tags, (list, tuple)) or not all(
            isinstance(tag, str) and tag.strip() for tag in tags
        ):
            raise PermanentAdapterError(
                "metadata.tags must be a list of non-empty strings",
                code="youtube_tags_invalid",
            )
        privacy = str(request.metadata.get("privacy_status", "private"))
        if privacy not in {"private", "unlisted", "public"}:
            raise PermanentAdapterError(
                "privacy_status must be private, unlisted, or public",
                code="youtube_privacy_invalid",
            )
        status: dict[str, Any] = {
            "privacyStatus": "private" if scheduled else privacy,
            "selfDeclaredMadeForKids": made_for_kids,
            "containsSyntheticMedia": synthetic,
        }
        if scheduled:
            status["publishAt"] = self._rfc3339(request.scheduled_for)
        return {
            "snippet": {
                "title": title.strip(),
                "description": str(request.metadata.get("description", request.text)),
                "tags": [tag.strip() for tag in tags],
                "categoryId": str(request.metadata.get("category_id", "22")),
            },
            "status": status,
        }

    @staticmethod
    def _video_path(request: PostRequest) -> str:
        if len(request.media_paths) != 1:
            raise PermanentAdapterError(
                "YouTube upload requires exactly one video file",
                code="youtube_video_file_required",
            )
        path = Path(request.media_paths[0])
        if not path.is_file():
            raise PermanentAdapterError(
                f"video file does not exist: {path}",
                code="youtube_video_file_missing",
            )
        return str(path)

    @staticmethod
    def _notify_subscribers(request: PostRequest) -> bool:
        value = request.metadata.get("notify_subscribers", False)
        if not isinstance(value, bool):
            raise PermanentAdapterError(
                "notify_subscribers must be boolean",
                code="youtube_notify_invalid",
            )
        return value

    def _post_result(
        self,
        account: AccountConfig,
        resource: Mapping[str, Any],
        scheduled_for: datetime | None = None,
    ) -> PostResult:
        video_id = resource.get("id")
        if not isinstance(video_id, str) or not video_id:
            raise PermanentAdapterError(
                "YouTube response did not contain a video ID",
                code="youtube_video_id_missing",
            )
        status = resource.get("status") or {}
        state = self._state(status, scheduled_for)
        publish_at = status.get("publishAt")
        parsed_schedule = scheduled_for or self._parse_datetime(publish_at)
        return PostResult(
            account_id=account.account_id,
            platform=self.platform,
            state=state,
            post_id=video_id,
            url=f"https://www.youtube.com/watch?v={video_id}",
            scheduled_for=parsed_schedule,
            published_at=self._parse_datetime(
                (resource.get("snippet") or {}).get("publishedAt")
            ),
            raw=resource,
        )

    @staticmethod
    def _state(status: Mapping[str, Any], scheduled_for) -> PostState:
        upload_status = status.get("uploadStatus")
        if upload_status in {"failed", "rejected", "deleted"}:
            return PostState.FAILED
        if scheduled_for or status.get("publishAt"):
            return PostState.SCHEDULED
        if upload_status in {"uploaded"}:
            return PostState.QUEUED
        if upload_status == "processed" or status.get("privacyStatus") in {
            "public",
            "unlisted",
        }:
            return PostState.PUBLISHED
        return PostState.UNKNOWN

    @staticmethod
    def _analytics_values(payload: Mapping[str, Any]) -> dict[str, Any]:
        headers = payload.get("columnHeaders") or []
        rows = payload.get("rows") or []
        if not rows:
            return {}
        names = [header.get("name") for header in headers]
        return dict(zip(names, rows[0]))

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return int(value) if value is not None else None

    @staticmethod
    def _rfc3339(value: datetime | None) -> str:
        if value is None or value.tzinfo is None:
            raise PermanentAdapterError(
                "scheduled_for must include timezone information",
                code="youtube_schedule_timezone_missing",
            )
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
