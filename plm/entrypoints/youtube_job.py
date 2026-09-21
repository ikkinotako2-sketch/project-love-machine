from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from plm.account_manager import AccountConfig, AccountManager
from plm.social_adapters import AdapterRegistry, PostRequest, RetryPolicy, SocialHub
from plm.social_adapters.youtube import (
    EnvironmentOAuthTokenProvider,
    QuotaBudget,
    YouTubeAdapter,
    YouTubeRestApi,
)


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"required environment variable is missing: {name}")
    return value


def _boolean(name: str) -> bool:
    value = _required(name).lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


def _account() -> AccountConfig:
    account_id = _required("PLM_ACCOUNT_ID")
    analytics_days = int(os.environ.get("PLM_ANALYTICS_DAYS", "28"))
    return AccountConfig.from_dict(
        {
            "account_id": account_id,
            "platform": "youtube",
            "display_name": account_id,
            "credential_ref": "env://PLM_YOUTUBE_OAUTH_JSON",
            "enabled": True,
            "adapter_config": {"analytics_days": analytics_days},
        }
    )


def _hub(account: AccountConfig) -> SocialHub:
    quota = QuotaBudget(
        upload_limit=int(os.environ.get("PLM_YOUTUBE_UPLOAD_LIMIT", "100")),
        data_units=int(os.environ.get("PLM_YOUTUBE_DATA_UNITS", "10000")),
    )
    api = YouTubeRestApi(
        EnvironmentOAuthTokenProvider(),
        quota=quota,
        upload_resume_attempts=int(os.environ.get("PLM_UPLOAD_RESUME_ATTEMPTS", "3")),
    )
    registry = AdapterRegistry()
    registry.register(YouTubeAdapter(api))
    return SocialHub(
        AccountManager([account]),
        registry,
        retry_policy=RetryPolicy(
            max_attempts=int(os.environ.get("PLM_MAX_ATTEMPTS", "3")),
            initial_delay_seconds=1,
            multiplier=2,
            max_delay_seconds=30,
        ),
    )


def _result_payload(result) -> dict[str, Any]:
    payload = {
        "account_id": result.account_id,
        "platform": result.platform,
        "post_id": result.post_id,
    }
    if hasattr(result, "state"):
        payload.update(
            {
                "state": result.state.value,
                "url": result.url,
                "scheduled_for": result.scheduled_for.isoformat()
                if result.scheduled_for
                else None,
                "published_at": result.published_at.isoformat()
                if result.published_at
                else None,
            }
        )
    else:
        payload.update(
            {
                "captured_at": result.captured_at.isoformat(),
                "views": result.views,
                "likes": result.likes,
                "comments": result.comments,
                "shares": result.shares,
                "watch_time_seconds": result.watch_time_seconds,
            }
        )
    return payload


def run() -> dict[str, Any]:
    operation = _required("PLM_OPERATION")
    account = _account()
    hub = _hub(account)
    if operation == "upload":
        scheduled_text = os.environ.get("PLM_SCHEDULED_FOR", "").strip()
        scheduled_for = (
            datetime.fromisoformat(scheduled_text.replace("Z", "+00:00"))
            if scheduled_text
            else None
        )
        tags = [
            item.strip()
            for item in os.environ.get("PLM_TAGS", "").split(",")
            if item.strip()
        ]
        request = PostRequest(
            account_id=account.account_id,
            text=os.environ.get("PLM_DESCRIPTION", ""),
            media_paths=(_required("PLM_VIDEO_PATH"),),
            scheduled_for=scheduled_for,
            idempotency_key=_required("PLM_IDEMPOTENCY_KEY"),
            metadata={
                "title": _required("PLM_TITLE"),
                "description": os.environ.get("PLM_DESCRIPTION", ""),
                "tags": tags,
                "category_id": os.environ.get("PLM_CATEGORY_ID", "22"),
                "privacy_status": os.environ.get("PLM_PRIVACY_STATUS", "private"),
                "made_for_kids": _boolean("PLM_MADE_FOR_KIDS"),
                "contains_synthetic_media": _boolean(
                    "PLM_CONTAINS_SYNTHETIC_MEDIA"
                ),
                "notify_subscribers": _boolean("PLM_NOTIFY_SUBSCRIBERS"),
            },
        )
        return _result_payload(hub.deliver(request))
    video_id = _required("PLM_VIDEO_ID")
    if operation == "status":
        return _result_payload(hub.get_post_status(account.account_id, video_id))
    if operation == "analytics":
        return _result_payload(hub.get_analytics(account.account_id, video_id))
    raise ValueError("PLM_OPERATION must be upload, status, or analytics")


def main() -> int:
    output_path = Path(os.environ.get("PLM_RESULT_PATH", "youtube-result.json"))
    try:
        payload = {"ok": True, "result": run()}
        exit_code = 0
    except Exception as exc:
        payload = {
            "ok": False,
            "error": {
                "type": type(exc).__name__,
                "code": getattr(exc, "code", "entrypoint_error"),
                "message": str(exc),
            },
        }
        exit_code = 1
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
