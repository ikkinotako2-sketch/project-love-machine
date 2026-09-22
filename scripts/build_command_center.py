"""Build a public, read-only job overview from sanitized Pipeline Result files."""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


JOB_NAME = re.compile(r"^yt-[0-9]+-([0-9]{13})\.json$")
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
STATUSES = {"processing", "succeeded", "failed"}
MAX_ROWS = 200
JST = ZoneInfo("Asia/Tokyo")


def cell(value: object, *, limit: int = 160) -> str:
    """Escape untrusted JSON for a GitHub-flavored Markdown table cell."""
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    plain = str(value).replace("\r", " ").replace("\n", " ")[:limit]
    escaped = html.escape(plain, quote=True)
    for mark in ("\\", "[", "]", "(", ")", "`"):
        escaped = escaped.replace(mark, "\\" + mark)
    return escaped.replace("|", "&#124;") or "—"


def records(result_dir: Path) -> list[tuple[int, dict[str, object]]]:
    candidates = []
    for path in result_dir.glob("yt-*.json"):
        match = JOB_NAME.fullmatch(path.name)
        if match:
            candidates.append((int(match.group(1)), path))
    candidates.sort(reverse=True)
    valid = []
    for timestamp, path in candidates:
        if len(valid) >= MAX_ROWS:
            break
        try:
            if path.stat().st_size > 64_000:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            if payload.get("job_id") != path.stem or payload.get("status") not in STATUSES:
                continue
            datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        except (OSError, UnicodeError, ValueError, OverflowError, json.JSONDecodeError):
            continue
        valid.append((timestamp, payload))
    return valid


def render(result_dir: Path, now: datetime) -> str:
    rows = records(result_dir)
    lines = [
        "# PLM Command Center — YouTube V2",
        "",
        "Pipeline Result Fetcher の公開済み結果を表示します。YouTube の動画は private が既定です。",
        "この一覧にはTokenやOAuth情報を含めません。表示時刻は job_id の生成時刻です。",
        "",
        f"最終更新: {now.astimezone(JST):%Y-%m-%d %H:%M JST} / 表示: 最新 {len(rows)} 件（最大 {MAX_ROWS} 件）",
        "",
        "| 実行日時 (JST) | job_id | status | video_id | youtube_url | failed_stage | error |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for timestamp, data in rows:
        time = datetime.fromtimestamp(timestamp / 1000, tz=JST).strftime("%Y-%m-%d %H:%M:%S")
        job = str(data["job_id"])
        video_id = data.get("video_id")
        url = data.get("youtube_url")
        safe_url = (
            f"https://www.youtube.com/watch?v={video_id}"
            if isinstance(video_id, str)
            and VIDEO_ID.fullmatch(video_id)
            and url == f"https://www.youtube.com/watch?v={video_id}"
            else None
        )
        link = f"[動画]({safe_url})" if safe_url else "—"
        lines.append(
            "| "
            + " | ".join(
                [
                    time,
                    f"[`{job}`](https://github.com/ikkinotako2-sketch/project-love-machine/blob/plm-results/pipeline-results/{job}.json)",
                    cell(data.get("status")),
                    cell(video_id),
                    link,
                    cell(data.get("failed_stage")),
                    cell(data.get("error")),
                ]
            )
            + " |"
        )
    if not rows:
        lines.append("| — | — | 結果なし | — | — | — | — |")
    lines += [
        "",
        "更新はGitHub Actionsの毎時スケジュールです。直ちに反映したい場合は",
        "`Update PLM Command Center` を手動実行します。スケジュールは遅延する場合があります。",
        "元の結果JSONが正本です。この一覧は閲覧用で、投稿処理やn8nの実行回数を増やしません。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_dir", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(render(args.result_dir, datetime.now(timezone.utc)), encoding="utf-8")


if __name__ == "__main__":
    main()
