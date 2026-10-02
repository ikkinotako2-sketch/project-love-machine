"""Offline TikTok media and posting-metadata preflight; never posts or authenticates.

Passing means only that supplied local evidence passes these static checks. It
does not establish that a creator actually consented or that TikTok approved
the app. Evidence must be collected by a separate compliant user interface.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Mapping

from .result import tiktok_result_path


MAX_BYTES = 4_000_000_000  # Conservative interpretation of the documented 4 GB.
MAX_SECONDS = 600  # Creator-info may lower this limit.
PRIVACY = frozenset({"SELF_ONLY", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "PUBLIC_TO_EVERYONE"})
REASONS = frozenset({
    "media_missing", "media_probe_failed", "container_unsupported", "codec_unsupported",
    "resolution_unsupported", "fps_unsupported", "duration_unsupported", "file_oversized",
    "caption_too_long", "caption_invalid", "privacy_unsupported", "privacy_unavailable",
    "ai_disclosure_missing", "commercial_disclosure_missing", "interaction_invalid",
    "interaction_unavailable", "commercial_privacy_conflict", "creator_info_missing",
    "creator_info_stale", "creator_info_invalid", "preview_missing", "caption_editability_missing",
    "privacy_selection_missing", "disclosure_ui_missing", "consent_missing",
})
_CONTAINERS = {".mp4": "mov,mp4,m4a,3gp,3g2,mj2", ".mov": "mov,mp4,m4a,3gp,3g2,mj2", ".webm": "matroska,webm"}
_CODECS = frozenset({"h264", "hevc", "vp8", "vp9"})
_CONSENT_REF = re.compile(r"[A-Za-z0-9._:-]{8,128}\Z")


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def probe_media(path: str | Path, *, run: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    """Inspect an actual local file with ffprobe; no shell or network access."""
    file = Path(path)
    if not file.is_file():
        raise ValueError("media_missing")
    try:
        completed = run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(file)],
            capture_output=True, text=True, timeout=30, check=True,
        )
        data = json.loads(completed.stdout)
        video = next(stream for stream in data["streams"] if stream.get("codec_type") == "video")
        fmt = data["format"]
        rate = video.get("avg_frame_rate") or "0/0"
        if rate == "0/0":
            rate = video.get("r_frame_rate")
        fps = float(Fraction(rate))
        duration = float(fmt.get("duration") or video["duration"])
        return {
            "extension": file.suffix.lower(),
            "format_name": fmt["format_name"],
            "major_brand": (fmt.get("tags") or {}).get("major_brand", ""),
            "codec": video["codec_name"],
            "width": int(video["width"]), "height": int(video["height"]),
            "fps": fps, "duration": duration, "size": file.stat().st_size,
        }
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, StopIteration, ZeroDivisionError, TypeError) as exc:
        raise ValueError("media_probe_failed") from exc


def validate_media(info: Mapping[str, Any], creator_max_seconds: int | None) -> set[str]:
    reasons: set[str] = set()
    ext = info.get("extension")
    fmt = str(info.get("format_name", ""))
    brand = str(info.get("major_brand", "")).lower()
    if ext not in _CONTAINERS or _CONTAINERS[ext] not in fmt or (ext == ".mov" and brand != "qt  ") or (ext == ".mp4" and brand == "qt  "):
        reasons.add("container_unsupported")
    if not isinstance(info.get("codec"), str) or info["codec"] not in _CODECS:
        reasons.add("codec_unsupported")
    if not all(isinstance(info.get(k), int) and 360 <= info[k] <= 4096 for k in ("width", "height")):
        reasons.add("resolution_unsupported")
    fps = info.get("fps")
    if not isinstance(fps, (int, float)) or not 23 <= fps <= 60:
        reasons.add("fps_unsupported")
    duration = info.get("duration")
    if not isinstance(duration, (int, float)) or not 0 < duration <= min(MAX_SECONDS, creator_max_seconds or MAX_SECONDS):
        reasons.add("duration_unsupported")
    size = info.get("size")
    if not isinstance(size, int) or size <= 0 or size > MAX_BYTES:
        reasons.add("file_oversized")
    return reasons


def validate_metadata(metadata: Mapping[str, Any], creator: Mapping[str, Any]) -> set[str]:
    reasons: set[str] = set()
    caption = metadata.get("title")
    if not isinstance(caption, str):
        reasons.add("caption_invalid")
    elif len(caption.encode("utf-16-le")) // 2 > 2200:
        reasons.add("caption_too_long")
    privacy = metadata.get("privacy_level")
    if not isinstance(privacy, str) or privacy not in PRIVACY:
        reasons.add("privacy_unsupported")
    elif not isinstance(creator.get("privacy_level_options"), list) or privacy not in creator["privacy_level_options"]:
        reasons.add("privacy_unavailable")
    if type(metadata.get("is_aigc")) is not bool:
        reasons.add("ai_disclosure_missing")
    if any(type(metadata.get(k)) is not bool for k in ("brand_content_toggle", "brand_organic_toggle")):
        reasons.add("commercial_disclosure_missing")
    if metadata.get("brand_content_toggle") is True and privacy == "SELF_ONLY":
        reasons.add("commercial_privacy_conflict")
    for option, restriction in (("disable_comment", "comment_disabled"), ("disable_duet", "duet_disabled"), ("disable_stitch", "stitch_disabled")):
        if type(metadata.get(option)) is not bool:
            reasons.add("interaction_invalid")
        elif creator.get(restriction) is True and metadata[option] is False:
            reasons.add("interaction_unavailable")
    return reasons


def validate_creator_and_consent(creator: Mapping[str, Any], evidence: Mapping[str, Any], now: datetime) -> set[str]:
    """Check supplied evidence; this cannot authenticate the human action."""
    reasons: set[str] = set()
    if not creator:
        reasons.add("creator_info_missing")
    options = creator.get("privacy_level_options")
    duration = creator.get("max_video_post_duration_sec")
    if (not isinstance(options, list) or not options or any(not isinstance(x, str) or x not in PRIVACY for x in options)
            or type(duration) is not int or duration <= 0
            or any(type(creator.get(k)) is not bool for k in ("comment_disabled", "duet_disabled", "stitch_disabled"))):
        reasons.add("creator_info_invalid")
    fetched = _time(creator.get("fetched_at"))
    if fetched is None or not now - timedelta(minutes=15) <= fetched <= now:
        reasons.add("creator_info_stale")
    if evidence.get("preview_rendered") is not True:
        reasons.add("preview_missing")
    if evidence.get("caption_editable") is not True:
        reasons.add("caption_editability_missing")
    if evidence.get("privacy_selected_by_creator") is not True:
        reasons.add("privacy_selection_missing")
    if evidence.get("disclosures_presented") is not True:
        reasons.add("disclosure_ui_missing")
    ref = evidence.get("consent_record_id")
    consent_time = _time(evidence.get("consented_at"))
    if (not isinstance(ref, str) or not _CONSENT_REF.fullmatch(ref)
            or consent_time is None or not fetched or not fetched <= consent_time <= now):
        reasons.add("consent_missing")
    return reasons


def preflight_result(job_id: str, reasons: set[str], now: datetime) -> dict[str, Any]:
    tiktok_result_path(job_id)  # Shares the existing job ID restriction.
    if reasons - REASONS or now.tzinfo is None:
        raise ValueError("invalid preflight result")
    return {
        "schema_version": 1, "job_id": job_id, "platform": "tiktok",
        "status": "fail" if reasons else "pass",
        "failure_reasons": sorted(reasons), "checked_at": now.isoformat(),
    }


def preflight_path(job_id: str) -> str:
    tiktok_result_path(job_id)
    return f"tiktok-preflight/{job_id}.json"


def check_preflight(
    *, job_id: str, media_path: str | Path, metadata: Mapping[str, Any],
    creator_info: Mapping[str, Any], evidence: Mapping[str, Any],
    now: datetime | None = None, probe: Callable[[str | Path], Mapping[str, Any]] = probe_media,
) -> dict[str, Any]:
    """Fail closed on missing evidence. No API requests or posting side effects."""
    tiktok_result_path(job_id)
    now = now or datetime.now(timezone.utc)
    reasons = validate_creator_and_consent(creator_info, evidence, now)
    reasons.update(validate_metadata(metadata, creator_info))
    try:
        info = probe(media_path)
    except ValueError as exc:
        reasons.add(str(exc) if str(exc) in {"media_missing", "media_probe_failed"} else "media_probe_failed")
    else:
        duration = creator_info.get("max_video_post_duration_sec")
        reasons.update(validate_media(info, duration if type(duration) is int and duration > 0 else None))
    return preflight_result(job_id, reasons, now)
