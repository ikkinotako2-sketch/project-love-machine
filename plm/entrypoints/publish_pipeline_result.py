from __future__ import annotations

import json
import os
from pathlib import Path

from plm.pipeline.result_store import GitHubResultStore, processing_result


def _load_payload(job_id: str, source: str | None):
    if not source:
        return processing_result(job_id)
    path = Path(source)
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    job_id = os.environ["PLM_JOB_ID"]
    payload = _load_payload(job_id, os.environ.get("PLM_RESULT_SOURCE"))
    store = GitHubResultStore(
        repository=os.environ["GITHUB_REPOSITORY"],
        token=os.environ["GITHUB_TOKEN"],
        branch=os.environ.get("PLM_RESULTS_BRANCH", "plm-results"),
    )
    store.publish(job_id, payload)
    print(f"Published sanitized pipeline result for {job_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
