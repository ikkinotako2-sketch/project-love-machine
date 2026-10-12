# YouTube channel and private recovery preparation — 2026-10-12

## Evidence and limits
- Repository main verified: 6ed3b3d284d23f66f96030282add75aec16377ac.
- OAuth branch verified: 029855e0625f6b93ff1a2405fcd4d68db857d0a1.
- OAuth r2 run 38225716925: attempt 1, completed success, exact marker HEAD. Authentication success does not establish channel ownership or granted read/upload scopes.
- OAuth r1 and r2 markers remain immutable and permanently consumed.
- Historical pipeline run 36153932146: attempt 1 success at 2fa012dd4f9630bf414533e4977b8390952a6794. Artifact inventory still lists claim and pipeline-result-yt-1243-1790349856887. No new upload performed; result archive not downloaded. Historical video-to-channel mapping remains unverified.
- Candidate channel UCJdTc1jznWNFlp0qy0SQ6uQ is owner supplied, valid identifier shape. Public search gave no result and public page retrieval was unavailable. Public existence and OAuth channel equality are UNVERIFIED, not false.

## New verification
Identity provider-neutral-youtube-channel-verify-20261012-r1. Dedicated branch plm-youtube-channel-readiness-20261012-r1. Expected fresh preparation parent 029855e0625f6b93ff1a2405fcd4d68db857d0a1.
Future consumed marker audit-evidence/consumed/provider-neutral-youtube-channel-verify-20261012-r1.json, absent during preparation. Marker binds prepared SHA, workflow/executor/plan/schema, channel verifier, unchanged OAuth provider and wrapper, historical evidence hashes, exact secret selector and explicit execution approval. Plan pins expected channel.
Only separate approval may create one marker-only commit. Attempt 1 only, exact preparation diff/history, local gate before credential injection; permanent consumption for every result.
Maximum one OAuth refresh POST then one GET https://www.googleapis.com/youtube/v3/channels?part=id&mine=true&maxResults=50. Exactly one returned channel equal to expected, no next/previous page token. No fallback/public-id lookup to manufacture ownership proof. Zero/multiple/mismatch/HTTP failure/timeout/unknown stop permanently. No token retention or remote error-body reads. No upload follows a match.
Scopes: actual granted scopes are UNKNOWN. youtube.readonly is the narrow read scope to request if current credentials cannot perform channels.mine; youtube.upload is retained only for separately approved upload. Refresh cannot expand grants. Reauthorization must select the correct Google/Brand Account channel, existing matching OAuth client, offline access and consent; update secret through GitHub's secure UI without pasting credentials into chat. Do not repeatedly mint tokens. An auth-only PASS does not verify upload rights.
Official references: https://developers.google.com/youtube/v3/docs/channels/list ; https://developers.google.com/identity/protocols/oauth2/scopes ; https://developers.google.com/identity/protocols/oauth2 .

## Reuse audit
- render-short.yml reuses VOICEVOX on GitHub runner, FFmpeg/Noto fonts, render-worker/render.py and Quality Gate; output MP4 1080x1920 at 30fps. Render artifact retention one day means render-to-upload handoff must occur within retention or a new separately approved render is needed.
- youtube-pipeline.yml initializes/publishes normalized result, uses reusable renderer and adapter; private default, explicit audience and synthetic declarations, notify false. serverless_context defaults empty. No existing workflow/runtime source changed.
- youtube-adapter.yml injects selected PLM_YOUTUBE_* secret; legacy max attempts/resume default 3. serverless_guard reduces to 1 but underlying api.py still calls recovery/status PUT on timeout. Therefore existing legacy workflow MUST NOT be dispatched as the strict one-shot test.
- Cross-run artifact claim retained 30 days is not a permanent tombstone. New test needs immutable consumed upload marker plus atomic claim before transport. Offline PrivateOnce models this boundary; no real transport/claim implementation is provided or enabled. Missing approval/rights/channel/quality/media binding fails before claim. Duplicate claim and timeout cannot send again.
- Candidate job plm-private-channel-recovery-20261012-r1: one private video, notifications off, schedule blank; original technical-test narration and plain background; no external music/images/video. Adult technical test, made_for_kids=false; synthetic speech conservatively declared. Voice license/style/required attribution still requires owner review; do not claim ownership over licensed voice assets. No upload marker or real job created.
- Next upload preparation must supply reviewed voice attribution, render quality proof/media hash, bounded init+media transport (no status recovery/redirect), durable marker, sanitized result store and fresh channel binding to the same in-memory credential used for upload. A previous channel PASS alone cannot cover a later replaced secret.

## 24-hour integration readiness
| Stage | Reused component | Remaining gate |
|---|---|---|
| Theme/script | Existing orchestration | Current autonomous scheduler, input rights and policy gate not proven |
| Render | VOICEVOX/FFmpeg/Quality Gate | Review final artifact and pin media bytes |
| Reserve | Legacy artifact claim; Cloudflare queue/outbox schema | Durable one-shot claim and approved runtime activation absent |
| Upload | Existing adapter semantics | Strict no-resume transport boundary must be wired before private test |
| Results | Normalized result/artifact/results branch | Approve bounded result writes for future test; UNKNOWN never reupload |
| Metrics/improvement | Existing metrics/improvement workflows | Actual analytics grant/quota and closed-loop provenance not verified |
| Next job | Parked runtime composition | Cron/consumer stay disabled; separate activation and bounded E2E required |

Cloudflare parked deploy/postcheck PASS are inherited evidence; no fresh Cloudflare access in this task. No D1 writes, cron, consumer or live factory enabled. Safe flags remain true. Full autonomous E2E is not claimed tested.
External Google OAuth application in Testing normally issues seven-day refresh tokens for YouTube scopes. Owner must check publishing status, consent scopes and any verification obligations, move to appropriate production status through a separate authorized process, then reauthorize if required. Production status does not guarantee perpetual tokens: revocation/expiry must stop safely and alert, never retry upload. Avoid duplicate authorizations that invalidate older tokens. No Google settings changed.
$0 operation requires measured render time, Actions/storage allowance and API quota caps; no paid fallback. Twenty-four-hour scheduling does not imply unlimited continuous rendering. Account-specific available budget is not yet verified.

## Approval boundaries
Next approval only: channel verification marker commit once; OAuth POST max 1 and channels.mine GET max 1; no retry, upload, publish, dispatch or Cloudflare changes. Upload requires later approval after channel match and outstanding media/rights/transport gates. No execution marker is created during this preparation.
