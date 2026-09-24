"""Dispatch one job's 1h collector after GitHub's environment wait timer.

Only the successful, local YouTube Pipeline workflow can supply a job ID.
This job does not access YouTube or store credentials for the delayed period.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from plm.improvement.core import JOB_ID

WORKFLOW_PATH = ".github/workflows/youtube-pipeline.yml"
TITLE = re.compile(r"^Pipeline (yt-[0-9]+-[0-9]{13})$")
MIN_DELAY = timedelta(minutes=65)
MAX_DELAY = timedelta(hours=3)


def selected_job(event: dict[str, Any]) -> str | None:
    run = event.get("workflow_run") or {}
    repo = event.get("repository") or {}
    if (
        run.get("path") != WORKFLOW_PATH
        or run.get("conclusion") != "success"
        or run.get("head_branch") != "main"
        or run.get("event") != "workflow_dispatch"
        or (run.get("head_repository") or {}).get("full_name") != repo.get("full_name")
    ):
        return None
    title = run.get("display_title")
    match = TITLE.fullmatch(title) if isinstance(title, str) else None
    return match.group(1) if match and JOB_ID.fullmatch(match.group(1)) else None


def dispatch(event: dict[str, Any], token: str, opener=urllib.request.urlopen,
             *, now: datetime | None = None) -> bool:
    job_id = selected_job(event)
    if job_id is None:
        return False
    # GitHub silently creates an undefined environment with NO wait timer.
    # Refuse to dispatch if the required 70-minute timer has not actually elapsed.
    now = now or datetime.now(timezone.utc)
    finished = event["workflow_run"].get("updated_at")
    try:
        finished_at = datetime.fromisoformat(finished.replace("Z", "+00:00"))
        if finished_at.tzinfo is None:
            raise ValueError("timezone required")
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("missing pipeline completion timestamp") from exc
    elapsed = now - finished_at
    if elapsed < MIN_DELAY or elapsed > MAX_DELAY:
        raise RuntimeError("delayed metrics timer missing or outside 1h window")
    repository = event["repository"]["full_name"]
    owner, name = repository.split("/", 1)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", owner) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
        raise ValueError("invalid repository")
    url = f"https://api.github.com/repos/{owner}/{name}/actions/workflows/youtube-improvement.yml/dispatches"
    request = urllib.request.Request(
        url,
        data=json.dumps({"ref": "main", "inputs": {"job_id": job_id, "slot": "1h"}}).encode(),
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    with opener(request, timeout=20) as response:
        if response.status != 204:
            raise RuntimeError("metrics dispatch did not succeed")
    return True


def main() -> None:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    if dispatch(event, os.environ["GITHUB_TOKEN"]):
        print("Dispatched one targeted 1h metrics collection")
    else:
        print("Skipped nonmatching pipeline event")


if __name__ == "__main__":
    main()
