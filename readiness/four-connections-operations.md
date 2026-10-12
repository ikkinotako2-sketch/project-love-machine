# Final four connections — OFFLINE candidate / production PARKED

Parent 62018663fc33ab05d001d44c088e49128f1b1b42. Independent branch plm-youtube-four-connections-20261012-r1.
Historical 48-hour proof, actual MP4, legacy uploader and immutable sandbox modules are reused. No new render or live request is performed.

## A — Shared lifecycle

`SharedLifecycle` stores control/active/last-completed separately from immutable job tombstones in one CAS document. Claims and daily reservations are one CAS. Every job consumes its own identity permanently. Only independent completed-run evidence permits next admission. Lease expiration never permits another owner to resend; an active record blocks all new claims. Read/write uncertainty poisons the instance; no further write or reconciliation request is issued automatically.

GitHub adapter targets only `automation-state/lifecycle.json` on a separately initialized `plm-execution-state-v2` branch. No branch creation, delete, main write, or fallback. SQLite is an OFFLINE transactional CAS reference, not proof of hosted-runner local disk durability. D1 uses the independent additive successor described below.

Upload ACK is ACKNOWLEDGED, not Done. A processed/private readback and callback ACK produce a durable receipt. Actions returns AWAITING_COMPLETED_RUN_PROOF. A separately approved coordinator can reload that receipt after restart and verify terminal GitHub success before atomic Done/metrics/next-job state.

Cross-run ACK loss: a Done record is insufficient. `GitHubCompletionAuthority` independently verifies the upload run and the separately approved coordinator run. A failed/UNKNOWN coordinator denies the next job even if its last CAS actually reached GitHub. No HMAC or memory boolean substitutes for these API records. Production executor must exit nonzero on every uncertainty; the present production entry is unconditionally PARKED.

Explicit global STOP release uses a separate identity, expected state SHA and injected release authority. It never resets any job tombstone. No release is authorized or executed here. Capacity is bounded to 64 jobs / 32KiB state; capacity exhaustion stops, does not discard tombstones. Sharding/archival requires its own reviewed lifecycle.

## B — Voice contract

Successor voice is VOICEVOX / speaker 3 / ずんだもん / ノーマル. Python and Worker require matching inventory and script/caption identity. NEW_RENDER and REUSE_PINNED are distinct. New-render test fixtures prove contract parsing, not actual audio synthesis. Actual old MP4 is reused with exact media/audio/caption hashes. Runtime dispatch now uses speaker 3 through independent SpeakerBoundary/SpeakerComposition. Legacy mapCheckpoint and deployed Worker source remain unchanged, including unrelated speaker 1 paths.

The successor composition separately verifies its three new source modules before dispatch. Existing 0008/9/10 operation/fencing/queue/SENT/checkpoint/result/HMAC logic is reused, not weakened. Independent run provenance and fresh account budget admission precede the respective side effects.

## C — Independent evidence

GitHubProvenance: six bounded GETs per proof (run, jobs, artifacts, marker bytes, workflow bytes, marker-only commit). It validates repository, job, approved identity, branch, run/attempt/SHA, artifact archive digest/origin, workflow hash, marker hash and parent-only chain. Artifact archive digest is not MP4 SHA; the media bytes are checked independently by the factory. before_upload accepts only the intended in-progress run; completed accepts only terminal success.

ProcessedReadback: a separately approved read token/scope and one GET of exact videos ID, id/snippet/status/processingDetails. ID/channel/private/processed/succeeded must all match. Missing/in-progress/malformed/error/timeout is UNKNOWN, never reupload, no poll/retry. This readback is distinct from the channel mine GET.

FreshChannel reuses the existing OAuth provider through a memory-only injected bundle and a bounded opener. It requires scopes from that same refresh response and passes the same bearer to mine GET, Strict Upload, and independent readback. Response scope absence remains UNKNOWN. Tokeninfo is not used. No default environment/Secret lookup. Error bodies are not read by the new opener/transport. Future OAuth POST maximum1, channel GET1, readback GET1 per separately approved operation budget.

## D — Factory and activation

CandidateFactory connects operation gate → scope/explicit budget observation → independent run reader → voice/media bytes → shared claim → fresh channel → StrictUploader → independent processed readback → durable callback SENT → canonical signed callback → durable completion receipt. A separate finalizer verifies completed run → Metrics/Improvement → atomic Done/next-job.

DispatchOnce uses raw immutable 40hex only, sentinel-before-POST, POST1/no retry. Raw SHA dispatch acceptance is still UNVERIFIED, so real dispatch is blocked. CallbackOnce reuses the frozen candidate sender's result_payload and sign functions with independent callback key and exact approved HTTPS origin/path. HMAC is not run provenance.

No production executor is enabled: existing parked workflow has job if=false and entrypoint always rejects. createLiveSpeakerComposition also rejects. Current scope has upload but not read; channel remains UNVERIFIED. No marker, Secret, runtime flag, Worker, route, cron, consumer or D1 is changed.

## Budget/migration successor

`0011_automation_budget_notification_successor.sql` replaces the UNAPPLIED old 0011 candidate; never apply both. It adds budget/reservation/notice only. BEFORE INSERT guard uses explicit RAISE(ABORT) so INSERT OR IGNORE cannot silently ignore a trigger's budget CHECK violation. Duplicate job does not charge twice. Batch rollback protects capacity. Unknown D1 response blocks further admission and notice writes. Notices are deduplicated and cannot be deleted. Tests preserve 0008/9/10 schema bytes and rows.

All counts in simulation are fixtures, not account quota. Fresh quota contract requires per-service remaining amounts, plan FREE, billing cap0, observation age<=300s and sufficient cost allowance. Unknown/stale/missing balance stops before I/O. API-observation data must be acquired under separate read-only approval; current account balances are UNKNOWN.

Applying 0011 and its read-only postcheck are separate approval identities. Later Worker deployment and its postcheck are also separate. No execution workflows or consumed markers are generated for these actions here.

## Remaining live prerequisites / minimum next step

1. Owner consent for youtube.upload + youtube.readonly, correct Google account/client/channel, safe manual GitHub Secret replacement. Current read scope is confirmed missing; old OAuth/scope identities remain consumed.
2. Prepare a scope-aware independent channel verification successor without consuming old channel r1; its eventual POST1 + mine GET1 requires separate approval.
3. Initialize independent state branch and minimum repository-scoped Contents token under separate approval. Do not claim a token has API-level branch-only permission. Protect main with repository rules and exact code paths.
4. Pin finalizer/provenance workflow/identity/marker/artifact manifests, key roles, immutable ref acceptance, callback origin, real remaining quotas and OAuth expiry. The future read scopes and Metrics capability must be proved; current fixtures are not live capabilities.
5. Review prepared source/bundle, apply 0011 successor and postcheck, deploy the new candidate and postcheck with distinct one-shot approvals; keep existing PARKED until activation approval.
6. Approve private1 upload/readback/callback, then 24-hour observation (max2 jobs/day). No automatic rollback or resend. Retain UNKNOWN and undelivered outbox.

No OAuth, YouTube, Cloudflare, D1 remote or dispatch communication is performed in this preparation. Safe flags all true. State/transport/request/marker approval data are explicit inputs; the live credential-injection workflow and owner approval still need a final execution preparation and review. This is tested candidate code, not a live operational success.
