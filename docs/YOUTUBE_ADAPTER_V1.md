# PLM YouTube Adapter v1

Official specifications were checked on 2026-09-21. This implementation uses only the
Python standard library and adds no paid service.

## Verified API behavior

- `videos.insert` uploads a video, supports resumable media upload, returns a video
  resource/ID, and requires OAuth. Uploads from unverified API projects created after
  2020-07-28 are restricted to private until the project passes YouTube's audit.
- Scheduled publishing uses `status.publishAt`. It is valid only while
  `privacyStatus=private` and the video has never been published. PLM also rejects a
  past schedule instead of allowing YouTube to publish immediately.
- `videos.list(part=status,processingDetails,statistics,snippet)` supplies upload,
  processing, privacy, and basic statistics state.
- YouTube Analytics `reports.query` uses `ids=channel==MINE` and a `video==VIDEO_ID`
  filter. PLM requests views, likes, comments, shares, and estimated minutes watched.
- The documented default quota includes 100 `videos.insert` calls per day in its own
  upload bucket and 10,000 daily units for other Data API endpoints. `videos.list`
  costs one unit. PLM includes a process-local admission guard; Google Cloud remains
  authoritative.
- Resumable upload retries are limited to connection failures and HTTP
  500/502/503/504, with exponential backoff and `Retry-After` support. PLM also treats
  HTTP 429 as transient. Authentication, invalid input, policy, upload-limit, and
  quota-exceeded responses are permanent and are not retried.

Official references:

- https://developers.google.com/youtube/v3/docs/videos/insert
- https://developers.google.com/youtube/v3/docs/videos
- https://developers.google.com/youtube/v3/docs/videos/list
- https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol
- https://developers.google.com/youtube/v3/determine_quota_cost
- https://developers.google.com/youtube/v3/docs/errors
- https://developers.google.com/youtube/analytics/reference/reports/query
- https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps

## Runtime flow

```
PLM Render Cloud artifact
  -> n8n workflow_dispatch
  -> PLM YouTube Adapter GitHub Action
  -> SocialHub / AccountManager
  -> YouTubeAdapter
  -> YouTube Data API / YouTube Analytics API
```

`youtube-adapter.yml` downloads `short.mp4` from a selected PLM Render Cloud run. It
does not edit or invoke the existing render workflow. The same Adapter object handles
every validated `youtube_*_NNN` account.

## n8n entrypoint

n8n calls GitHub's workflow dispatch endpoint for
`.github/workflows/youtube-adapter.yml`. Supply the Render Cloud run ID and artifact
name, metadata, account ID, and a unique n8n job ID as `idempotency_key`.

The Action performs two duplicate checks:

1. SocialHub blocks a repeated key within the process.
2. A hashed, non-secret GitHub artifact claim blocks the same upload key across runs
   for 30 days. Concurrency serializes identical keys.

The normalized response is saved as `youtube-result-<run_id>` for n8n to retrieve.
Status and analytics operations use `video_id` and do not download a render artifact.

## Credential boundary

Create one GitHub repository secret per YouTube account. Its name must begin with
`PLM_YOUTUBE_`; its value is a JSON object containing `client_id`, `client_secret`, and
`refresh_token`. n8n passes only the secret's name. The value is injected into the
runner, refreshed through Google OAuth, never printed, and never committed.

OAuth consent and any Google/YouTube verification or guardian confirmation remain
manual. Service accounts are not used because YouTube supports them only for eligible
content owners.

## Safety defaults

- Immediate uploads default to `private`.
- Scheduled uploads are always created as `private` with future `publishAt`.
- Audience (`made_for_kids`) and synthetic-media disclosure must be explicit booleans.
- Subscriber notifications default to false.
- An uncertain resumable-upload outcome is not restarted automatically, preventing a
  second video from being created when the first result cannot be confirmed.
