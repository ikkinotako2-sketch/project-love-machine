"""Allowlisted, offline result records for a possible TikTok pipeline.

This module has no API client, credentials, workflow dispatch, or network I/O.
It must not be mistaken for a posting integration.
"""

from __future__ import annotations

import re
from datetime import datetime


_JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9._:~-]{1,128}\Z")
_STATES = frozenset({"waiting_for_consent", "initialized", "transferring", "processing", "succeeded", "failed", "unknown"})
_STAGES = frozenset({"creator_info", "consent", "initialize", "transfer", "status", "policy", "render"})
_PRIVACY = frozenset({"SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE"})


def tiktok_result_path(job_id: str) -> str:
    if not isinstance(job_id, str) or not _JOB_ID.fullmatch(job_id):
        raise ValueError("invalid job_id")
    return f"tiktok-results/{job_id}.json"


def _identifier(value: str | None, field: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not _SAFE_IDENTIFIER.fullmatch(value)):
        raise ValueError(f"invalid {field}")
    return value


def _timestamp(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"invalid {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid {field}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} requires timezone")
    return value


def build_tiktok_result(
    *,
    job_id: str,
    status: str,
    privacy: str,
    created_at: str,
    completed_at: str | None = None,
    publish_id: str | None = None,
    post_id: str | None = None,
    failed_stage: str | None = None,
    error_code: str | None = None,
) -> dict[str, object]:
    """Build a public result without accepting raw responses or freeform errors.

    A status of ``unknown`` must be reconciled using a persisted publish_id;
    never initialize a second post merely because the first attempt timed out.
    """
    tiktok_result_path(job_id)
    if status not in _STATES or privacy not in _PRIVACY:
        raise ValueError("invalid status or privacy")
    if failed_stage is not None and failed_stage not in _STAGES:
        raise ValueError("invalid failed_stage")
    if status == "failed" and failed_stage is None:
        raise ValueError("failed_stage is required for failure")
    if status != "failed" and (failed_stage is not None or error_code is not None):
        raise ValueError("error fields require failed status")
    if status in {"initialized", "transferring", "processing", "succeeded"} and not publish_id:
        raise ValueError("publish_id required after initialization")
    if status in {"succeeded", "failed"} and completed_at is None:
        raise ValueError("terminal result requires completed_at")
    return {
        "schema_version": 1,
        "job_id": job_id,
        "platform": "tiktok",
        "status": status,
        "publish_id": _identifier(publish_id, "publish_id"),
        "post_id": _identifier(post_id, "post_id"),
        "privacy": privacy,
        "created_at": _timestamp(created_at, "created_at"),
        "completed_at": _timestamp(completed_at, "completed_at"),
        "failed_stage": failed_stage,
        "error": {"code": _identifier(error_code, "error_code")} if error_code else None,
    }
