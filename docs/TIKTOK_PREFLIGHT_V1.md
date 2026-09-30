# TikTok Preflight v1 (offline only)

This branch adds local validation, not a TikTok adapter or a posting workflow.
No Action calls these functions. `pass` means only that the supplied file and
evidence satisfy static checks; it does **not** authorize posting or prove the
creator truly consented. The eligibility blocker in `TIKTOK_ADAPTER_V1_DESIGN.md`
remains in force.

## Inputs and boundary

`check_preflight(job_id, media_path, metadata, creator_info, evidence)` accepts:

- A local render output such as `short.mp4`. `probe_media` reads the actual file
  with `ffprobe` (no shell) and checks its byte size from the filesystem.
  FFmpeg/ffprobe is already installed by `render-short.yml`, and the renderer's
  quality gate already uses ffprobe. The validator also accepts an injected
  probe for offline unit tests.
- Direct Post metadata: `title` caption, `privacy_level`, explicit Boolean
  `is_aigc`, both commercial disclosure flags and the three interaction flags.
  No privacy default is applied. Caption length is counted as UTF-16 code
  units, up to 2200. `SELF_ONLY` branded third-party content is rejected.
- A separately obtained, recent creator-info snapshot: the current
  `privacy_level_options`, `max_video_post_duration_sec`, disabled interaction
  flags, and `fetched_at`. The 15-minute freshness limit is a conservative PLM
  policy, not a TikTok guarantee. A future app must call creator_info/query
  when rendering its posting page and use the latest response.
- Evidence supplied by a separate creator-facing UI: `preview_rendered`,
  `caption_editable`, `privacy_selected_by_creator`, `disclosures_presented`,
  `consent_record_id`, and `consented_at`. No constructor fills these fields,
  generates consent, selects privacy, or calls an API. A plain offline record
  cannot authenticate a human action; a future reviewed UI must bind evidence
  to the actual creator, content fingerprint and displayed settings.

The media validator checks MP4/MOV/WebM container evidence, H.264/H.265/VP8/VP9,
360–4096 px in each dimension, 23–60 fps, positive duration no longer than
10 minutes or the creator-specific maximum, and at most 4,000,000,000 bytes
(a conservative 4 GB interpretation). A valid media file is not necessarily
eligible to be posted: TikTok may impose further checks.

## Output

The result contract is `tiktok-preflight/<job_id>.json` with only
`schema_version`, `job_id`, `platform`, `status` (`pass`/`fail`), sorted
allowlisted `failure_reasons`, and `checked_at`. It excludes video paths,
metadata text, creator identifiers, consent references, tokens, upload URLs,
and raw API responses. The function returns a dict; it does not write files.
It is separate from `tiktok-results/<job_id>.json` in PR #15.

## State machine and deduplication

`validate_transition` accepts a bounded path from `waiting_for_consent` through
`initialized`, `transferring`, and `processing` to terminal states. `unknown`
may only be reconciled to `processing`, `succeeded`, or `failed`; it can never
return to `initialized`. This is an offline guard, not durable state storage.

GitHub Actions concurrency serializes runs in a group but is not a durable,
atomic claim for `(account_id, job_id)`. The existing SocialHub store is only
in-memory. A future implementation needs a transactional store that survives
runner restarts, persists a claim and `publish_id`, and blocks automatic replay
if init's outcome is unknown. This remains a blocker before posting code.

## References checked 2026-09-30

- https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide
- https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post
- https://developers.tiktok.com/docs/en/content-posting-api-reference-query-creator-info
- https://developers.tiktok.com/docs/en/content-sharing-guidelines
