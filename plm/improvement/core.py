"""Pure planning and normalization for YouTube improvement collection.

Snapshots are observations at collection time, never reconstructed historical
YouTube Analytics intervals. Missing analytics values stay null.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

JOB_ID = re.compile(r"^yt-[0-9]+-[0-9]{13}$")
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
SLOTS = {"1h": timedelta(hours=1), "24h": timedelta(hours=24)}
MAX_LATE = {"1h": timedelta(hours=3), "24h": timedelta(hours=36)}
CATEGORIES = (
    "hook", "duration", "caption_density", "scene_changes",
    "narration", "cta", "topic_selection",
)


def valid_result(result: Mapping[str, Any]) -> bool:
    return (
        result.get("status") == "succeeded"
        and isinstance(result.get("job_id"), str)
        and bool(JOB_ID.fullmatch(result["job_id"]))
        and isinstance(result.get("video_id"), str)
        and bool(VIDEO_ID.fullmatch(result["video_id"]))
        and result.get("youtube_url")
        == f"https://www.youtube.com/watch?v={result.get('video_id')}"
    )


def due_slots(completed_at: datetime, now: datetime, state: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Return (slot, action), where action is collect or missed."""
    if completed_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("timestamps must include timezone")
    due = []
    for slot, delay in SLOTS.items():
        previous = state.get(slot) or {}
        if previous.get("status") in {"collected", "missed", "failed"}:
            continue
        if previous.get("attempts", 0) >= 3:
            due.append((slot, "failed"))
        elif now >= completed_at + delay:
            due.append((slot, "missed" if now > completed_at + MAX_LATE[slot] else "collect"))
    return due


def snapshot(video: Mapping[str, Any], analytics: Mapping[str, Any] | None, now: datetime) -> dict[str, Any]:
    stats = video.get("statistics") or {}
    headers = (analytics or {}).get("columnHeaders") or []
    rows = (analytics or {}).get("rows") or []
    extra = dict(zip((column.get("name") for column in headers), rows[0])) if rows else {}
    def count(value: Any) -> int | None:
        try:
            result = int(value)
            return result if result >= 0 else None
        except (ValueError, TypeError):
            return None
    def number(value: Any) -> float | None:
        try:
            result = float(value)
            return result if result >= 0 and result < 1e9 else None
        except (ValueError, TypeError):
            return None
    return {
        "captured_at": now.astimezone(timezone.utc).isoformat(),
        "views": count(stats.get("viewCount")),
        "likes": count(stats.get("likeCount")),
        "comments": count(stats.get("commentCount")),
        "averageViewDuration": number(extra.get("averageViewDuration")),
        "averageViewPercentage": number(extra.get("averageViewPercentage")),
        "subscribersGained": count(extra.get("subscribersGained")),
        "subscribersLost": count(extra.get("subscribersLost")),
        "analytics_available": bool(rows),
        "source": "YouTube Data API videos.list; optional YouTube Analytics reports.query",
    }


def guidance(one_hour: Mapping[str, Any] | None, day: Mapping[str, Any]) -> dict[str, Any]:
    """Conservative, generalized hypotheses, without copying any video."""
    current = day.get("metrics") or {}
    earlier = (one_hour or {}).get("metrics") or {}
    views = current.get("views")
    enough = isinstance(views, int) and views >= 30
    percentage = current.get("averageViewPercentage")
    growing = isinstance(views, int) and isinstance(earlier.get("views"), int) and views > earlier["views"]
    actions = {
        "hook": "冒頭で視聴者への具体的な問いを1つ示す。次回は異なる表現を比較する。",
        "duration": "主題を1つに絞り、不要な間を削る。尺の変更は比較実験として扱う。",
        "caption_density": "字幕を短い意味単位に区切り、画面を読み切れる量にする。",
        "scene_changes": "話題の切れ目で画面を切り替え、変化の頻度を段階的に試す。",
        "narration": "短文と自然な間で要点を伝え、字幕との同期を確認する。",
        "cta": "最後に内容に沿った簡潔な問いを1つ置く。",
        "topic_selection": "元動画の表現を再利用せず、視聴者の課題を別の切り口で選ぶ。",
    }
    if enough and isinstance(percentage, (int, float)) and percentage < 45:
        actions["hook"] = "冒頭の説明を短くし、視聴者の疑問を先に提示する比較実験を行う。"
        actions["duration"] = "平均視聴率が低いため、次回は1つの要点に絞った短い尺を試す。"
    if enough and isinstance(current.get("comments"), int) and current["comments"] == 0:
        actions["cta"] = "内容に直接関係する答えやすい問いを最後に1つ置いて比較する。"
    return {
        "method": "rules",
        "analysis": (
            "24時間の観測値を基にした編集仮説。成長傾向あり。" if enough and growing
            else "データが少ないため、以下は検証用の編集仮説。効果は未確認。"
        ),
        "evidence": {"views_24h": views, "views_1h": earlier.get("views"), "sample_sufficient": enough},
        "improvement_actions": actions,
    }


def validate_ai(output: Any) -> dict[str, Any] | None:
    if not isinstance(output, dict) or not isinstance(output.get("analysis"), str):
        return None
    actions = output.get("improvement_actions")
    if not isinstance(actions, dict) or set(actions) != set(CATEGORIES):
        return None
    if any(not isinstance(actions[key], str) or not 1 <= len(actions[key]) <= 180 for key in CATEGORIES):
        return None
    if len(output["analysis"]) > 250:
        return None
    return {"method": "gemini", "analysis": output["analysis"], "improvement_actions": actions}
