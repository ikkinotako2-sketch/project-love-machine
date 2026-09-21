from __future__ import annotations

from typing import Any, Mapping


def _safe_result(value: Any, fallback_stage: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {
        "ok": False,
        "error": {
            "stage": fallback_stage,
            "type": "MissingResult",
            "message": "stage result JSON was not produced",
        },
    }


def build_pipeline_result(
    *,
    job_id: str,
    render_job_status: str,
    youtube_job_status: str,
    render_result: Any,
    youtube_result: Any,
) -> dict[str, Any]:
    """Build the stable JSON returned to n8n for success or partial failure."""
    render = _safe_result(render_result, "render_cloud")
    youtube = _safe_result(youtube_result, "youtube_adapter")

    failed_stage = None
    error = None
    if render_job_status != "success" or not render.get("ok"):
        error = render.get("error") or {
            "stage": "render_cloud",
            "type": "WorkflowFailure",
            "message": f"render job ended with {render_job_status}",
        }
        failed_stage = error.get("stage", "render_cloud")
    elif youtube_job_status != "success" or not youtube.get("ok"):
        error = youtube.get("error") or {
            "stage": "youtube_adapter",
            "type": "WorkflowFailure",
            "message": f"YouTube job ended with {youtube_job_status}",
        }
        failed_stage = error.get("stage", "youtube_adapter")

    if error is not None:
        error = dict(error)
        error.setdefault("stage", failed_stage)

    youtube_data = youtube.get("result") if isinstance(youtube.get("result"), dict) else {}
    return {
        "schema_version": 1,
        "job_id": job_id,
        "render_id": job_id,
        "status": "succeeded" if failed_stage is None else "failed",
        "failed_stage": failed_stage,
        "video_id": youtube_data.get("post_id"),
        "youtube_status": youtube_data.get("state"),
        "error": error,
        "stages": {
            "render_cloud": {
                "job_status": render_job_status,
                "result": render,
            },
            "youtube_adapter": {
                "job_status": youtube_job_status,
                "result": youtube,
            },
        },
    }
