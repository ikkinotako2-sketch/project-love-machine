# PLM YouTube Improvement Engine v1

## Scope and timing

The independent `PLM YouTube Improvement Engine` Action runs hourly at minute 43
UTC. It scans up to 500 successful sanitized `plm-results/pipeline-results/yt-*.json`
files. The last commit time of each successful result file is the reference for
approximately 1-hour and 24-hour snapshots. GitHub schedule delays mean snapshots
are **not exact at the minute**. The state stores `captured_at` so they can be
interpreted honestly. If the schedule missed the 1h window (after 3h) or 24h
window (after 36h), it records `missed` rather than pretending a later snapshot
was historical data.

It never dispatches the posting Pipeline or invokes n8n. The existing Pipeline
result JSON remains unchanged and metrics errors cannot fail an uploaded video.
Each slot has at most three attempts across scheduled runs; only transient
YouTube errors retry. Missing permission and invalid video errors fail the slot.

## Authorized data

The collector reuses the YouTube Adapter OAuth refresh provider, authenticated
request transport and `videos.list` status method. It stores only cumulative
views, likes and comments from `statistics`, not video text or raw API payloads.
An optional `reports.query` request with `channel==MINE` and `video==<video_id>`
asks for `averageViewDuration`, `averageViewPercentage`, `subscribersGained`,
`subscribersLost`. These require the channel owner's YouTube Analytics scope and
can lag. Empty/unavailable values are `null`, never fabricated zero. For video
filters, subscriber values cover the video's watch page rather than all possible
subscription sources.

The current workflow selects the existing `PLM_YOUTUBE_GAME_001` OAuth secret
for the current `youtube_game_001` account. Additional accounts need an explicit
safe account-to-secret selector and result account ID before being enrolled;
do not copy the workflow for each account.

## Storage and improvement

The collector writes only `plm-results/improvement-results/<job_id>.json`.
It contains `job_id`, `video_id`, `youtube_url`, `completed_at`, the `1h` and
`24h` states, `analysis`, `analysis_method`, and seven `improvement_actions`
keys: `hook`, `duration`, `caption_density`, `scene_changes`, `narration`, `cta`,
`topic_selection`. All advice is a generalized edit hypothesis; it never
copies another video's content.

At 24h, a conservative rule-based baseline is always available. If the
repository secret `PLM_GEMINI_API_KEY` is set to a free-tier Gemini API key, a
Gemini review replaces the baseline. It receives only aggregate metrics and
short baseline hypotheses; its JSON is validated, and retries are capped at
three. Without the key, `analysis_method=rules` makes the limitation explicit.
No paid service is enabled by this workflow.

The most recent complete 24h guidance is copied to
`plm-results/improvement-results/latest.json` for the next Gemini generation.
Until a 24h observation exists, this file is absent and V2 keeps its current
prompt. The n8n V2 integration fetches this public JSON once in the existing
execution, before the Gemini script node, with a fallback for unavailable
feedback. It never starts a second n8n execution or 24-hour Wait node.

The Command Center reads these JSONs and shows a concise 1h/24h summary,
analysis and a link to all seven actions. Refresh is still hourly at minute 17.

## API documentation checked

- [YouTube Data API videos.list](https://developers.google.com/youtube/v3/docs/videos/list)
- [YouTube video statistics](https://developers.google.com/youtube/v3/docs/videos)
- [YouTube Analytics reports.query](https://developers.google.com/youtube/analytics/reference/reports/query)
- [YouTube Analytics channel reports](https://developers.google.com/youtube/analytics/channel_reports)
- [YouTube Analytics metrics](https://developers.google.com/youtube/analytics/metrics)
- [Gemini structured JSON output](https://ai.google.dev/gemini-api/docs/structured-output)

## Operational checks

1. Confirm the Action's scheduled run succeeded and did not reveal secrets.
2. At/after 1h and 24h, inspect the slot status and `captured_at` in the
   `improvement-results/<job_id>.json` file. A missing Analytics scope or data
   lag can leave retention/subscription values null.
3. Confirm `docs/COMMAND_CENTER.md` refreshed, then inspect the next V2 Gemini
   input for generalized feedback when a 24h result is available.
