# PLM Serverless Architecture v1 — GitHub Actions + Cloudflare

Audit/design/reference PoC, 2026-10-01. Status: PARTIAL; no live Cloudflare
resources, credentials, dispatch, SNS request, posting, or n8n mutation.
No PC is an execution dependency in the target design. The existing Render
Action's Docker container runs on GitHub's disposable hosted runner, not a
home PC. Nothing in this PR is deployed or merged.

## 1. Read-only evidence

Fetched main at `fb44be6` and PR #15 head `a3bad01`. The repository is public.
The GitHub REST open-PR list contained only Draft #15. Its ClaimStore,
in-memory recovery and SQLite reference were inspected without changes.
Seven existing workflows were inspected. Latest results observed:
Command Center #48 success; Improvement #94 success; Render #2, Adapter #1,
Pipeline #15, delayed 1h #7 and Test PLM Core #51 all success. Live n8n
UI/paused-state and Cloudflare account/plan/resources were not accessible.
Local read-only audit inputs were the V2 JSON, Queue backup, and exported
11-workflow ZIP; exported content does not establish current live activation.

| Class | Evidence and migration boundary |
| --- | --- |
| A: already Actions | render-short (VOICEVOX, FFmpeg, quality gate), youtube-adapter, youtube-pipeline, plm-results JSON, command-center, youtube-improvement, delayed 1h dispatch |
| B: n8n dependence | V2 theme schedule and Data Table claim, manual Form entry, Gemini script/payload generation, GitHub dispatch, result wait/poll, queue done/failed/timeout updates; Bluesky and recovery/collector workflows in ZIP |
| C: move to Cloudflare gradually | schedules, durable job/claim state, dispatch coordination, callback reconciliation, delayed metrics timers, emergency stop, admission/rate/budget guards |
| D: keep Actions | video/audio generation, upload adapters, bounded API processing, metrics collection and improvement computation; preserve successful workflow interfaces |
| E: potentially retire later | V2 scheduler/poll/wait and Local Service URL Receiver once replacement is verified; Bluesky daily reset and retry coordination after parity. Keep all exports; delete/disable nothing now |
| F: unverified | live n8n status/credentials, Cloudflare entitlement/billing/other-account usage, exact LLM free quota, actual MP4 artifact size/daily demand, Bluesky parity, authenticated billing and environment settings |

V2 JSON confirms the schedule path Get rows -> If -> Get rows1 -> Claim
Marker -> Update rows -> Verify Claim -> Claim Success Guard -> HTTP Request.
The manual form goes directly to HTTP Request, bypassing queue claim. It
also contains legacy local-service/media nodes; presence alone does not mean
they are on the current successful execution path. Treat backup content as
static evidence, not live workflow status. No V1 or V2 JSON is edited.

The existing SocialHub uses `InMemoryIdempotencyStore`; it is not a durable
cross-run guarantee. Existing pipeline concurrency is not a replacement for
one. Dispatching the existing posting pipeline from Cloudflare would expose
this boundary; this PR therefore dispatches **only a new test workflow**.

## 2. Target responsibilities and lifecycle

1. **Job lifecycle:** schedule/admit -> content ready -> dispatch claimed ->
   dispatched/running -> succeeded/failed/unknown. Separate content generation,
   render, per-platform publish, and observation records. A TikTok failure
   does not rewrite YouTube success.
2. **Durable claim:** primary authority is proposed D1 key
   `(platform, account_id, job_id)`. Immutable content fingerprint, claimant,
   version, state, last_operation, publish_id and timestamps match PR #15's
   conceptual record. An unclaimed job is the absence of a record.
3. **Idempotency:** stable job ID identifies a posting intent; canonical hash
   binds media bytes and creator-confirmed metadata. Changed content with
   the same identity is a conflict, not an update.
4. **Duplicate prevention:** one claim and version-CAS; persist the attempt
   marker before external initialize, persist publish_id once immediately
   after receipt. Unknown/ambiguous results cannot initialize again.
5. **Retry:** at most three retries of explicitly safe reads/transport, with
   bounded exponential delay and Retry-After handling. Never blindly retry
   an initialize, upload publication, or ambiguous dispatch.
6. **Dead letter:** terminal validation failures and exhausted safe retries
   enter D1 dead-letter records with allowlisted reasons; Queue DLQ is a
   notification transport, not the durable archive. Operator reconciliation
   is required before a new side effect.
7. **Delayed execution:** Workflows sleeps for 70-minute and 24-hour metrics
   timers; no runner sleeps for hours. D1 `due_at` is the durable source of
   truth, so a lost timer can be discovered by a bounded indexed sweep.
8. **Metrics:** `(platform, account_id, job_id, slot)` unique observation
   tasks. Existing 1h/24h collector is reused after separate parity review;
   do not activate a second scheduler alongside it without an ownership gate.
9. **Improvement:** metrics and analysis are independent jobs with bounded
   input selection. Keep current rules fallback; enable Gemini only when its
   model-specific free quota and cost ceiling are verified.
10. **Account isolation:** account enable/disable, daily limits, credential
    reference, platform quota and schedules. Current AccountManager caps
    configured accounts at 100; expanding past 100 needs a separate review.
11. **Platform isolation:** separate rate budgets and publish records; no
    platform failure is an upstream media-generation failure.
12. **Secrets:** see the dedicated section below; none in payloads, D1,
    public result JSON, artifact snapshots, logs, or git.
13. **Audit:** append sanitized event code, identity, expected/result version,
    actor/run identifier and time. No freeform raw API error. D1 proposed
    event/outbox tables require a separate implementation and retention test.
14. **Recovery:** preserve attempt and remote ID, reconcile authoritative
    remote status, never infer non-publication from missing local data. D1
    restore/Time Travel cannot rewind external SNS effects.
15. **GitHub dispatch:** fixed repository, reviewed workflow allowlist and
    immutable approved ref; no caller-supplied workflow, token or URL. The
    test PoC uses a fixed branch, and no existing posting workflow.
16. **Cloudflare authentication:** future GitHub App with Actions-write on
    only PLM, short-lived installation tokens; an expiring fine-grained PAT
    is an optional test bootstrap, requiring human permission. None created.
17. **Callback:** separate test HMAC secret over timestamp and exact body,
    five-minute freshness, strict payload shape and run/dispatch binding.
    Replays are idempotent; conflicting runs cannot start. Future production
    uses GitHub OIDC with verified issuer/audience/repo/ref/workflow/run claims
    or reviewed rotating per-job capabilities; do not grant all runners a
    universal production callback secret.
18. **D1 schema:** test_jobs is implemented for local PoC; publish_claims is
    an SQL proposal. Future accounts, schedule, outbox, due-observation,
    audit and quota tables use composite identity and indexed due-state.
19. **Queue:** IDs and bounded intent only, under 4KB; at-least-once delivery,
    explicit ack after durable transition, duplicate deliveries read current
    state. Avoid raw captions/credentials/media. Batch and global concurrency
    stay small; DLQ configured before live use.
20. **Workflows:** stable instance IDs, bounded steps, safe operation-specific
    retry, timer wakeups, callback-wait/timeout and terminal persistence in D1.
    Completed free Workflow logs last only three days. No real binding exists
    yet; no Workflow or Queue consumer is implemented in this PoC.
21. **Cost guard:** one shared account budget for all PLM stages plus known
    other-account use; refuse admissions before thresholds, and require
    Free plan proof and $0 spend limits before deployment. Do not auto-upgrade.
22. **Rate guard:** token buckets per provider/account, request-timeout,
    one dispatch/second maximum and at most two active heavy jobs. Stop on
    secondary rate limits; preserve state rather than dispatch in a retry loop.
23. **Emergency stop:** default disabled, global and per-account checks
    before dispatch and each side effect. Already sent requests cannot be
    cancelled by changing a flag; record and reconcile them.
24. **Command Center:** keep current generated results untouched. First add
    a separate authenticated read-only state projection, later export only
    allowlisted summary to the existing public dashboard after review.

## 3. D1 adaptation of PR #15

Do not port Python `BEGIN IMMEDIATE` to D1 blindly. D1 uses prepared bindings
and auto-commit; its batch API groups statements transactionally. Use unique
insert plus primary read in one batch, and single conditional updates with
`WHERE identity AND claimant AND version AND allowed_state`; require
`meta.changes == 1`. Conditional quotas, outbox and audit writes must share
the same transactional operation. This PR tests SQL locally but is **not a
D1 ClaimStore adapter** and does not prove remote D1 semantics. A future
adapter must preserve all PR #15 transitions, validation and recovery tests.

SQLite is a reference, not a selected production database. D1 remains a
candidate. Remote concurrency, trigger support, response-loss after DB commit,
quota enforcement, consistent primary reads and backup recovery need actual
Free-account validation. Publish ID loss between SNS acceptance and D1 commit
still requires manual reconciliation. No automatic owner takeover by elapsed
time: a stale worker may still issue a side effect; fences do not revoke a
request already in flight.

## 4. Secret architecture for 100 accounts

GitHub limits repository secrets to 100 (48KB each); 100 account secrets plus
shared keys exhaust that limit. Workers Free permits 64 variables/secrets per
Worker, so one Worker-secret per account is not a scalable substitute.
Use separate reviewed account environments in a public repository, each with
its own named credentials and account-bound job permissions. Verify environment
features/count/policy on the actual account before choosing this. The current
pipeline's dynamic repository-secret interface stays unchanged and cannot
be migrated to this layout without a future additive adapter review.

Alternative: dedicated credential broker with narrowly scoped OIDC, encrypted
storage and rotating keys, evaluated separately for free-tier feasibility;
plain OAuth credentials in D1 are prohibited. A giant bundled secret would
broaden exposure and hit 48KB, so it is not the default. Credentials and keys
are created/registered only by the user in a later explicitly approved step.
GitHub App private key lives in a protected Worker secret, not in code/D1.

## 5. Official free-tier constraints (checked 2026-10-01)

| Product | Free constraints affecting PLM |
| --- | --- |
| Workers | 100,000 requests/day; HTTP/Cron CPU 10ms/invocation; 128MB memory; 50 external subrequests; 64 variables/Worker; 100 Workers; 5 Cron triggers/account |
| Workflows | requests share the 100,000/day allowance; pricing lists 10ms CPU/invocation, 3,000 steps/day, 1GB-month state; limits list 1,024 steps/instance, 100 running instances, sleep up to 365 days, completed retention 3 days |
| Queues | 10,000 operations/day; normally write/read/delete=3 per message; retries add reads; 24h retention on Free; delays up to 24h; max retries default 3, DLQ must be configured |
| D1 | 5 million rows read/day; 100,000 written/day; 5GB total, 10 DBs, 500MB/DB; indexes also count writes; 50 queries/invocation; 7-day Time Travel. Free quota excess blocks queries (enforced September 2026) |
| GitHub | Standard hosted runner time in public repo is free; larger runners charged. Free concurrency 20, hosted job max 6h, whole workflow max 35 days incl waiting. Artifact allowance 500MB shared with Packages and cache allowance 10GB; do not assume public compute makes storage unlimited |
| GitHub authentication | 100 repo secrets, 100 environment secrets, 48KB/secret. App/PAT typically 5,000 REST requests/hour; GITHUB_TOKEN 1,000/hour/repo; secondary limits apply |

Workflows limits and pricing describe CPU differently (limits also describes
a 30-second default configurable CPU ceiling). Design to the stricter 10ms
Free pricing envelope until the actual entitlement is tested. Keep steps
small and I/O-only; video and heavy crypto/content work belong on Actions.
GitHub schedule can be late or dropped and public inactive schedules can be
disabled; it is not an exact timer. Neither service promises uninterrupted
execution within a free plan. We can make execution independent of a home PC,
not promise a 24/7 SLA or unlimited usage.

## 6. Bounded usage envelope (proposal, not measured production)

Assumption: 100 accounts, **one publication/account/day**, two observation
jobs/publication, at most three retries of safe operations. These are total
platform/account tasks, not one extra set per SNS. Exceeding 100 posts or 300
total stage tasks/day stops admission. More accounts must share this ceiling.

| Meter | Conservative model | Proposed cap / official free limit |
| --- | --- | --- |
| Workers requests | <=40/post + 288 five-minute sweeps + 200 dashboard requests = 4,488/day | 10,000/day / 100,000 shared |
| Workflow steps | 100 lifecycle x12 + 200 observation x6 = 2,400/day, including retry budget | 2,400/day / 3,000 |
| Queue ops | 300 tasks x7 (base+retry/DLQ allowance) = 2,100/day | 5,000/day / 10,000 |
| D1 writes | 100 posts x100 + 200 observations x40 = 18,000/day, including indexes/audit | 30,000/day / 100,000 |
| D1 reads | 100 posts x200 + 200 observations x100 + 288 sweeps x50 = 54,400/day | 250,000/day / 5 million |
| D1 storage | 100 compact 1KB claim tombstones/day = ~36.5MB/year; bounded audit/metrics retention <100MB | 250MB planning cap / 500MB per DB |
| GitHub APIs | 300 dispatches/day plus bounded reconciliation, <=1/sec, typically <500/hour | stop at 50% token quota and honor secondary limits |
| GitHub compute | 100 x30 runner-min + 200 x2 = 3,400min/day (~102,000/month), subject to acceptable-use/capacity; two heavy jobs max | public standard runners only; no private/larger fallback |

These numbers are assumptions, not proof of the actual account-wide budget.
All caps need atomically reserved daily credits before live rollout. Untrusted
HTTP floods, another app's usage, unexpectedly large scans or provider policy
can exhaust shared limits; Free stops must fail closed. Counters alone cannot
guarantee arbitrary traffic fits the free plan.

**Media storage is a blocker for 100/day.** If each MP4 were 10MB and retained
one day, render artifacts alone would be ~1GB, above a 500MB allowance. Actual
artifact size and public storage treatment must be checked with authenticated
billing; do not enable this volume based on free runner minutes. Proposed
future admission reserves artifact bytes, caps concurrent retained bytes below
200MB, verifies early deletion after successful handoff, and accounts for
existing artifacts/Packages. That cleanup is not implemented or executed.
Until measured/validated, the 100-account publication schedule is BLOCKED.
LLM generation and SNS quotas/review are also separate free-tier blockers.

The current PoC reserves at most **10 jobs for its entire DB lifetime**,
under 4KB requests, one fixed test account, no media/cache/artifact upload,
no timer/poller, and a five-minute test runner timeout. Missing credentials,
disabled flags or invalid inputs fail closed. The cap is not reset via an
endpoint; no resource is created now, so current Cloudflare usage is zero.

## 7. PoC, validation and rollback

Files: Worker reference, local D1-compatible SQL, test runner, Node tests,
Python schema/real-connection tests, and one new test-only Actions workflow.
Local D1 API shim uses Node's SQLite; this is not Miniflare or a deployed D1.
Mocks intercept GitHub dispatch and signed Worker callback. Tests include
idempotency, competing CAS, queue replay, invalid payload, stale timestamp,
timeout, bounded retry, emergency stop, independent connections and restart.

Live round trip is BLOCKED: Cloudflare login/Free-plan proof and explicit
permission to register test-only authentication are absent. Also GitHub's
workflow_dispatch/repository_dispatch requires the workflow on the default
branch. This Draft-only new workflow cannot be registered by merging because
main merge is forbidden. PR-triggered offline tests are valid, but are not
proof of Cloudflare -> real dispatch -> live callback. A future approved
sandbox repository is an option; none is created or configured here.

Deployment preparation: name Worker `plm-test-control-v1`, D1 `plm-test-state-v1`,
Queues `plm-test-jobs-v1` / `plm-test-dlq-v1` and Workflow `plm-test-timers-v1`
only when separately approved. Keep emergency stop on and all flags required;
no production SNS credentials. Verify $0 spending settings/account headroom
and CPU measurements before enabling a single test job. No Wrangler deploy
config with real resource IDs or automatic deployment Action is provided.

Rollback: unmerged additions have no live effect. Close the new Draft PR or
leave it disabled. For any future deployed test, enable stop first, revoke
test dispatch/callback access and retain DB evidence; do not delete claims
or replay unknown work. Existing n8n and Actions remain the rollback baseline.

Next phases: human design review -> approved test sandbox/Free account and
test credentials -> one TEST_ONLY round trip -> remote D1 race/recovery tests
-> measured storage/CPU/budget guards -> content-engine parity -> independently
reviewed posting safety gate. No SNS rollout is authorized by this document.

## Official references

- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/workers/platform/pricing/
- https://developers.cloudflare.com/workflows/reference/limits/
- https://developers.cloudflare.com/queues/platform/pricing/
- https://developers.cloudflare.com/queues/configuration/batching-retries/
- https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- https://developers.cloudflare.com/d1/platform/pricing/
- https://developers.cloudflare.com/d1/platform/limits/
- https://developers.cloudflare.com/d1/worker-api/d1-database/
- https://developers.cloudflare.com/changelog/post/2026-09-01-d1-free-tier-limit-enforcement/
- https://docs.github.com/en/actions/reference/limits
- https://docs.github.com/en/actions/reference/security/secrets
- https://docs.github.com/en/billing/concepts/product-billing/github-actions
- https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
