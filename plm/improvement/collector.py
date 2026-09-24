"""Collect owner-authorized snapshots, independent of the upload pipeline."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Mapping

from .core import CATEGORIES, due_slots, guidance, snapshot, valid_result, validate_ai

ANALYTICS_METRICS = (
    "views,likes,comments,averageViewDuration,averageViewPercentage,"
    "subscribersGained,subscribersLost"
)


def analytics_query(api: Any, video_id: str, completed_at: datetime, now: datetime) -> Mapping[str, Any]:
    """Reuse the adapter's authenticated request and error classification."""
    query = urllib.parse.urlencode({
        "ids": "channel==MINE",
        "startDate": completed_at.date().isoformat(),
        "endDate": now.date().isoformat(),
        "metrics": ANALYTICS_METRICS,
        "filters": f"video=={video_id}",
    })
    return api._request_json(f"{api.ANALYTICS_API}?{query}")


def ai_guidance(api_key: str, base: Mapping[str, Any], metrics: Mapping[str, Any]) -> dict[str, Any] | None:
    """Optional Gemini JSON review. Send aggregates only, never credentials or video text."""
    if not api_key:
        return None
    prompt = (
        "日本語でYouTube Shortsの編集仮説をJSONで出力。数値がnullなら推測しない。"
        "元動画の台詞や表現はコピーせず、一般化した改善だけを書く。"
        "analysisは250字以内。improvement_actionsは次の7キーを持ち各180字以内: "
        + ", ".join(CATEGORIES)
        + ". ベースライン仮説: "
        + json.dumps(base, ensure_ascii=False)
        + "。匿名化した観測値: "
        + json.dumps(metrics, ensure_ascii=False)
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }).encode()
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent",
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = json.load(response)
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        return validate_ai(json.loads(text))
    except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, TypeError, ValueError):
        return None


def collect_one(
    result: Mapping[str, Any], state: dict[str, Any], completed_at: datetime,
    now: datetime, api: Any, *, gemini_key: str = "", ai=ai_guidance,
    target_slot: str | None = None,
) -> dict[str, Any]:
    if not valid_result(result):
        raise ValueError("invalid successful pipeline result")
    if state and (state.get("job_id"), state.get("video_id")) != (result["job_id"], result["video_id"]):
        raise ValueError("existing state belongs to another job/video")
    state = dict(state) or {
        "schema_version": 1, "job_id": result["job_id"],
        "video_id": result["video_id"], "youtube_url": result["youtube_url"],
        "completed_at": completed_at.astimezone(timezone.utc).isoformat(),
    }
    if target_slot not in (None, "1h"):
        raise ValueError("unsupported target slot")
    for slot, action in due_slots(completed_at, now, state):
        if target_slot is not None and slot != target_slot:
            continue
        if action == "missed":
            state[slot] = {"status": "missed", "reason": "schedule_arrived_too_late"}
            continue
        if action == "failed":
            state[slot] = {"status": "failed", "attempts": 3, "error": "retry_exhausted"}
            continue
        attempts = int((state.get(slot) or {}).get("attempts", 0)) + 1
        try:
            video = api.get_video(result["video_id"])
            if video.get("id") != result["video_id"]:
                raise ValueError("video_id_mismatch")
            try:
                extra = analytics_query(api, result["video_id"], completed_at, now)
                availability = "available" if extra.get("rows") else "not_yet_available"
            except Exception:
                extra, availability = None, "unavailable_or_not_authorized"
            state[slot] = {
                "status": "collected", "attempts": attempts,
                "metrics": snapshot(video, extra, now),
                "analytics_status": availability,
            }
        except Exception as exc:
            retryable = exc.__class__.__name__ == "TransientAdapterError"
            status = "retry_pending" if retryable and attempts < 3 else "failed"
            code = getattr(exc, "code", "youtube_metric_error")
            state[slot] = {
                "status": status, "attempts": attempts,
                "error": str(code)[:80] if re.fullmatch(r"[a-zA-Z0-9_-]+", str(code)) else "youtube_metric_error",
            }
    if (state.get("24h") or {}).get("status") == "collected":
        base = guidance(state.get("1h"), state["24h"])
        if not state.get("analysis"):
            state["analysis"] = base["analysis"]
            state["improvement_actions"] = base["improvement_actions"]
            state["analysis_method"] = "rules"
            state["analysis_evidence"] = base["evidence"]
        if gemini_key and state["analysis_method"] == "rules" and state.get("ai_attempts", 0) < 3:
            reviewed = ai(gemini_key, base, state["24h"]["metrics"])
            state["ai_attempts"] = state.get("ai_attempts", 0) + 1
            if reviewed:
                state["analysis"] = reviewed["analysis"]
                state["improvement_actions"] = reviewed["improvement_actions"]
                state["analysis_method"] = "gemini"
    return state
