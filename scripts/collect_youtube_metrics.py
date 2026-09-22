"""Hourly GitHub Actions entrypoint. Reads sanitized results, writes separate state."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from plm.improvement.collector import collect_one
from plm.improvement.core import JOB_ID, valid_result
from plm.social_adapters.youtube import EnvironmentOAuthTokenProvider, YouTubeRestApi


def completed_at(repo: Path, relative: str) -> datetime | None:
    proc = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%cI", "--", relative],
        capture_output=True, text=True, timeout=15, check=False,
    )
    if proc.returncode or not proc.stdout.strip():
        return None
    return datetime.fromisoformat(proc.stdout.strip())


def write_if_changed(path: Path, payload: dict) -> bool:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def run(results: Path, *, now: datetime | None = None) -> tuple[int, int]:
    now = now or datetime.now(timezone.utc)
    root = results / "pipeline-results"
    out = results / "improvement-results"
    api = YouTubeRestApi(EnvironmentOAuthTokenProvider())
    changed = 0
    states = []
    for path in sorted(root.glob("yt-*.json"), reverse=True)[:500]:
        if not JOB_ID.fullmatch(path.stem) or path.stat().st_size > 64_000:
            continue
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
            if not valid_result(result) or result["job_id"] != path.stem:
                continue
            started = completed_at(results, str(path.relative_to(results)))
            if started is None:
                continue
            target = out / path.name
            state = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
            updated = collect_one(result, state, started, now, api, gemini_key=os.environ.get("PLM_GEMINI_API_KEY", ""))
            changed += write_if_changed(target, updated)
            states.append(updated)
        except (ValueError, OSError, json.JSONDecodeError):
            continue  # Corrupt public files never stop the next job.
    eligible = [s for s in states if s.get("analysis") and (s.get("24h") or {}).get("status") == "collected"]
    if eligible:
        newest = max(eligible, key=lambda s: s["completed_at"])
        latest = {
            "schema_version": 1, "status": "ready", "source_job_id": newest["job_id"],
            "analysis": newest["analysis"],
            "improvement_actions": newest["improvement_actions"],
            "analysis_method": newest["analysis_method"],
        }
        changed += write_if_changed(out / "latest.json", latest)
    return changed, len(states)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_checkout", type=Path)
    args = parser.parse_args()
    changed, total = run(args.results_checkout)
    print(f"Improvement state files changed: {changed}; eligible jobs scanned: {total}")


if __name__ == "__main__":
    main()
