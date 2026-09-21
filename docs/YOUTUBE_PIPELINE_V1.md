# PLM YouTube Pipeline v1

## Purpose

One n8n `workflow_dispatch` starts the complete cloud path:

```
PLM Render Request
  -> PLM Render Cloud
  -> PLM Quality Gate
  -> PLM YouTube Adapter
  -> pipeline-result-<job_id>
```

The pipeline is `.github/workflows/youtube-pipeline.yml`. It calls the existing
`render-short.yml` and `youtube-adapter.yml` as reusable workflows; rendering and
upload logic are not copied into the pipeline.

## Tracking and generated identifiers

- n8n creates one unique `job_id`.
- The pipeline uses the same value as `render_id` and YouTube idempotency key.
- Render artifact name is generated as `rendered-short-<job_id>`.
- The GitHub Actions run ID is passed internally to the Adapter.
- Final result artifact is generated as `pipeline-result-<job_id>`.

n8n never supplies a Render Run ID or artifact name. It can locate the final artifact
by its deterministic name, without a human reading the Actions screen.

## n8n dispatch inputs

Send these values to GitHub's workflow dispatch endpoint. JSON fields such as scenes
remain JSON-encoded strings because GitHub workflow inputs are scalar values.

```json
{
  "ref": "main",
  "inputs": {
    "job_id": "yt-20260922-0001",
    "account_id": "youtube_game_001",
    "oauth_secret_name": "PLM_YOUTUBE_GAME_001",
    "title": "動画タイトル",
    "hook": "冒頭フック",
    "narration": "ナレーション本文",
    "speaker": "1",
    "scenes_json": "[]",
    "captions_json": "[]",
    "bgm_json": "{}",
    "output_json": "{\"format\":\"mp4\",\"width\":1080,\"height\":1920,\"fps\":30}",
    "description": "説明文",
    "tags": "game,shorts",
    "privacy_status": "private",
    "scheduled_for": "",
    "made_for_kids": "false",
    "contains_synthetic_media": "true",
    "notify_subscribers": "false"
  }
}
```

Use a new `job_id` for new content. Reusing a completed upload's ID is blocked by the
YouTube Adapter's cross-run claim and Social Hub idempotency checks.

## Result JSON

The YouTube reusable workflow writes `youtube-result.json` to the existing
`youtube-result-<run_id>` artifact. The final job downloads and parses that file
directly. It does not pass the JSON through a reusable-workflow output, so GitHub's
secret redaction remains intact.

The final artifact always uses one stable schema. On success it contains `video_id`,
`youtube_status`, and `youtube_url`. On failure, `failed_stage` identifies `render_request`, `voice`,
`render`, `quality_gate`, `render_cloud_setup`, `youtube_adapter`, or
`youtube_adapter_setup`. Nested stage results retain the normalized error code and
message without credentials.

The pipeline defaults to private, never passes OAuth values as inputs, and only selects
a GitHub Secret whose name begins with `PLM_YOUTUBE_`.
