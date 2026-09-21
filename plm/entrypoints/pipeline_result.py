from __future__ import annotations

import json
import os
from pathlib import Path

from plm.pipeline import build_pipeline_result


def _json_env(name: str):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _json_file(path_value: str | None):
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def main() -> int:
    result = build_pipeline_result(
        job_id=os.environ["PLM_JOB_ID"],
        render_job_status=os.environ.get("PLM_RENDER_JOB_STATUS", "unknown"),
        youtube_job_status=os.environ.get("PLM_YOUTUBE_JOB_STATUS", "unknown"),
        render_result=_json_env("PLM_RENDER_RESULT_JSON"),
        youtube_result=_json_file(os.environ.get("PLM_YOUTUBE_RESULT_PATH")),
    )
    output = Path(os.environ.get("PLM_PIPELINE_RESULT_PATH", "pipeline-result.json"))
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
