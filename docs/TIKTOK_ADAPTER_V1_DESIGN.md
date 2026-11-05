# TikTok adapter v1: offline design (2026-09-30)

**Status: blocked for live posting.** This branch adds only a result contract. It
does not register an adapter, alter YouTube, create an Action, authenticate, or
call TikTok. `config/platforms/platforms.json` remains `tiktok: future`.

## Existing PLM boundaries

- AccountManager accepts `tiktok_*_NNN` and credential references, with accounts
  disabled by default. SocialHub and its in-memory idempotency store are a
  reference implementation; the store is not durable across Actions runs.
- `render-short.yml` accepts `workflow_call` and produces
  `rendered-short-<render_id>` containing `short.mp4`, a payload snapshot, and
  `render-result.json`. The default render specification is MP4, 1080x1920,
  30 fps. Validate codec, actual size and duration on each output.
- `youtube-pipeline.yml` couples render and YouTube upload. A future TikTok
  workflow may call `render-short.yml` independently, but must never dispatch
  the existing YouTube pipeline to obtain media, or modify its result path.
- Keep `plm-results/tiktok-results/<job_id>.json` separate from
  `pipeline-results` and `improvement-results`. Command Center and Improvement
  Engine integration requires its own future review and must not change the
  current YouTube calculation.

## Official API shape, if eligibility is approved

Direct Post requires app and `video.publish` approval, user OAuth grant, fresh
`creator_info/query`, creator-selected privacy from returned options, a preview,
editable caption, interaction/commercial disclosures, and explicit consent
before sending material. Then call `/v2/post/publish/video/init/`, transfer the
media, persist `publish_id`, and reconcile with
`/v2/post/publish/status/fetch/` or validated webhooks. A `PUBLISH_COMPLETE`
status need not provide a public `post_id` for a private post.

Upload Draft instead uses `video.upload` and
`/v2/post/publish/inbox/video/init/`; the creator must finish inside TikTok.
It is unsuitable for unattended final publication. Neither route excuses the
user-facing posting controls in TikTok's sharing guidelines.

Use `PULL_FROM_URL` only with a verified, publicly accessible domain or URL
prefix owned by the app. GitHub Actions artifacts and `plm-results` are not
assumed to meet this condition. TikTok's guidelines say server-hosted media
should use this method. `FILE_UPLOAD` is described for media on a user's device;
its returned URL expires and chunk transmission has strict limits. Select a
transfer method only after the media ownership and UX are resolved.

Direct Post `post_info` includes `title` (caption, maximum 2200 UTF-16 units),
`privacy_level`, interaction settings, commercial disclosure and `is_aigc`.
For AI-generated media, explicitly determine and set the required disclosure.
The current renderer's MP4/1080x1920/30 fps defaults fit the listed container,
dimensions and frame rate, subject to actual codec, duration and 4 GB maximum.

## Future isolated contract

Input: `job_id`, `account_id`, artifact reference or verified video URL,
editable caption, creator-selected privacy, AI/commercial disclosures,
user consent event, and content metadata. Keep OAuth tokens in a secret store.
Only an approved posting workflow would invoke a platform-specific client.

Output: `schema_version`, `job_id`, `platform=tiktok`, `status`, `publish_id`,
optional `post_id`, `privacy`, timestamps, `failed_stage`, and allowlisted error
code. This branch's `plm.tiktok.result` only builds this offline record. Never
persist tokens, transfer URLs, response bodies, or freeform API messages in
public result JSON.

## Idempotency and failure isolation

Before any future init call, atomically claim `(tiktok account_id, job_id)` in
a durable store and persist the content fingerprint, consent reference and
state. Persist `publish_id` immediately after init. A timeout or crash after
init is `unknown`: query status for that `publish_id`; **do not init again**.
If init response is lost, block automatic replay and require reconciliation.
GitHub Actions concurrency alone and SocialHub's in-memory store are
insufficient across runs. Retry status reads and bounded transfer operations,
not an ambiguous init. Keep TikTok job failure independent of YouTube result.

## Eligibility blocker

TikTok's Content Sharing Guidelines describe an app limited to uploading for
accounts owned by the developer or their team as an unacceptable intended use.
They also require creator preview, editable text, and express consent before
upload. PLM's proposed fully unattended, multi-account publisher does not
currently meet that UX. Unaudited clients are private-only with additional
creator limits; public posting requires audit. Do not implement or enable a
posting client until TikTok confirms an eligible use case and compliant UX.
Browser posting is not a substitute.

## Optional future metrics

The posting status API reports transfer/publication state, not engagement.
With separately approved Display API and `video.list` user grant,
`/v2/video/query/` can return `view_count`, `like_count`, `comment_count`,
`share_count` for videos owned by that authorized user. The public `post_id`
may be absent for a private post. No automatic 1h/24h promise is made. Do not
use Research API as a surrogate for this account workflow.

## Developer setup checklist (no action taken)

1. Establish an intended use and creator-facing workflow that TikTok accepts.
2. Create a Developer App and add Content Posting API; configure Direct Post
   only if approved. Apply for `video.publish` (or `video.upload` for drafts).
3. Register the appropriate OAuth redirect URI, implement state checking and
   secure token storage, and have the creator authorize the requested scopes.
4. If using server-hosted video, verify ownership of the URL domain/prefix.
5. Prepare preview, editable caption and choices, disclosure, consent, and
   status feedback for app review / Content Posting audit.
6. Request Display API with `video.list` separately if engagement collection
   is justified and approved.

## Official references

- https://developers.tiktok.com/docs/en/content-sharing-guidelines
- https://developers.tiktok.com/docs/en/content-posting-api-get-started
- https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post
- https://developers.tiktok.com/docs/en/content-posting-api-reference-upload-video
- https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status
- https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide
- https://developers.tiktok.com/docs/en/login-kit-web
- https://developers.tiktok.com/docs/en/tiktok-api-v2-video-query
