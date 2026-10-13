# Four connected executor kernels — current build PARKED

Base: e6ceb5658c41ce4300cf78957e898813ec874584. All four operations have distinct
new r2 identities in the frozen plan. Existing OAuth, scope and channel identities
are neither changed nor reused. No remote operation or consumption is authorized.

## Actual code connections

| Operation | Components used | Successful terminal output |
|---|---|---|
| A channel | existing provider → MemoryOAuthRefresh → FreshChannel → same bearer mine response | sealed channel receipt; token cleared |
| B state initialization | exact branch GET → optional create-ref POST → Contents GET → create-only PUT | exact blob hash and parent ACK; no overwrite |
| C private movie | render/media/credit gate → independent GitHub provenance → budget → Shared Lifecycle atomic claim → fresh same-credential session → durable SENT → StrictUploader | ACKNOWLEDGED durable receipt, never Done |
| D finalize | persisted C receipt → terminal uploader proof + independent current finalizer proof → fenced ACK-only lease → fresh session → separate processed readback → callback SENT → signed callback → receipt → existing factory completion/rules/next proposal | Done; next dispatch false |

A→B→C→D are not one approval. Each is issued separately, with its own marker and
budget. A failed, missing or UNKNOWN prerequisite cannot issue the next permit.
Current readonly scope is false; all real constructors and entrypoints remain
closed. An offline receipt has OFFLINE_CONTRACT basis and cannot open any real
transport, even when inputs claim authorization or alter the flags.

The raw State branch is not created here. Future B can create only the exact ref,
from the plan-pinned base commit, if absent. Existing ref must match that base and
existing lifecycle file blocks without any overwrite. No force/delete/update-ref
endpoint exists. Contents PUT omits sha (create only); the fixed initial JSON,
returned blob SHA, returned commit and expected parent must all match. A conflict
or lost ACK consumes the future operation and stops without a second request.
Repository-scoped Contents write is needed; Workflows write, admin and other
repositories are unnecessary. GitHub fine-grained tokens cannot be represented
here as branch-limited permissions; exact branch/file restrictions are enforced
by the transport and executor. Branch rules must be independently checked before
live initialization; they are not claimed verified by this package.

## Protocol budgets

A: refresh POST≤1, mine GET≤1. B: GitHub GET≤2, create-ref POST≤1, create-file PUT≤1.
C: independent GitHub GET≤6, State GET≤1/CAS PUT≤5, refresh POST≤1/mine GET≤1,
YouTube session-init POST≤1 and media PUT≤1. No status-recovery, chunk retry or resume.
D: independent GitHub GET≤12 (uploader completed + current finalizer), State GET≤1/
CAS PUT≤6, refresh POST≤1/mine GET≤1, processed GET≤1, callback POST≤1. No metrics API
call: metrics remain unavailable, and cold-start improvement uses existing rules.
No operation dispatches a next job in this package.

## Durable recovery boundary

C's receipt includes job/identity/run/video/channel/private/media/artifact bindings,
not tokens or raw bodies. D loads it after restart. Expired uploader lease never
allows reupload/reclaim. After independently proven uploader terminal success,
D may transfer only ACKNOWLEDGED state into a separately fenced finalization lease;
Processing/SENT/UNKNOWN states cannot transfer. Finalizer tombstone is permanent.

Callback or processed readback uncertainty causes global STOP and an undelivered
notice. Callback SENT is saved before its sole attempt. State write uncertainty
poisons the runner; no additional State write or GET follows. A subsequent runner
cannot promote a stored Done into continuation without independently verifying the
uploader and coordinator terminal runs. This includes lost Done-write ACKs.
The next-job proposal does not itself authorize dispatch or upload.

## Frozen local preflight before Secrets

External reviewed hashes are required for plan, source manifest and marker. Full
Git history, exact single preparation commit/file diff, exact marker-only commit,
run attempt 1, repo/ref/event/run/SHA, operation-specific approval flags and all
source bytes must match. Dirty worktree, replay, source mismatch or extra marker
stops before credential injection. The current CLI only audits and returns PARKED;
there is no live authority issuer and no Secret-value environment read.
A live release requires a separately reviewed source/workflow update and explicit
operation approval; changing input booleans cannot enable this frozen build.

## Remaining live conditions, not offline failures

Owner Google consent for youtube.upload + youtube.readonly; secure Secret update
under separate authorization; real channel match; State token registration and
branch access controls; fresh actual free quota; frozen live authority release;
exact HTTPS callback origin/key/provenance/Worker reservation; independent readback
approval. An offline callback fixture is never a pinned live callback route.

Cloudflare is untouched. 0008/0009/0010 and both 0011 candidate files are unchanged.
Optional Cloudflare migration/deploy/postcheck executors were not added in this
change; their separate approvals, fresh drift/exposure gates and rollback review
remain mandatory. Never apply both old and successor 0011.

## Production connection revision — all eight releases still PARKED

This revision supersedes the earlier CLI/no-issuer statements above. Preparation
root is 37eaf6495d62f53657d71eba987611b7eb765f56. The authoritative preparation
file list is in each hash-pinned plan, not a second hardcoded allowlist.
The proposed A/B/C/D identities are independent r3 identities; no old marker changes.

`entrypoint.py` now connects two-stage local preflight to `ProductionRunner`.
`release.py` checks a source-hash-frozen review record before any Secret lookup;
`run_reader.py` independently binds the current run and prerequisite receipt
artifacts to run/attempt/repository/ref/workflow/marker-only commit and exact hashes.
Only actual API proof, actual local Git audit and separately reviewed enabled
release records can register a live capability. Offline fixtures cannot promote
receipts to LIVE_VERIFIED. Every current release is disabled, and every operation
job is `if: false`. The safe flags remain true. No native request is reachable here.

Future activation requires an independently reviewed change for that operation:
protected environment/owner approval and operational exclusion, prepared/marker
pins, correct purpose-specific flags, actual budget evidence, role-specific Secrets,
prerequisite artifact/receipt hashes and separately fixed callback configuration.
An approval input or Secret presence alone cannot enable this revision. Google
additional consent is currently absent; upload scope is true, readonly false and
channel UNVERIFIED. A successful authenticated response must freshly prove both
scopes and the exact channel, not owner input claiming a match.

### Native evidence and inputs

Current/prerequisite GitHub proof uses at most 32 distinct GETs, with cache reuse
for subsequent provenance checks. Safe receipt diagnostics contain numeric statuses
and counters only. Inputs are fixed prerequisite JSON artifacts, and C reuses the
original MP4/audio/captions, never rerenders them. Artifact retrieval adds at most
six GETs: each uses one GitHub API GET and one signed Azure storage handoff.
This special protocol requires `artifact_handoff_reviewed`; storage receives no
Authorization header and its signed URL is never retained. OAuth, YouTube and
callback transports do not follow redirects. This handoff is an unverified native
service contract until independently reviewed; local test success is not remote proof.

Callback uses the existing `/youtube/result`, X-PLM-Signature and canonical HMAC
contract. Its origin/key id/context/checkpoint remain unpinned, so D is blocked.
The Worker is still PARKED and has no live callback route. Callback signing key
must differ from the existing dispatch key; no generated dummy key is accepted.
GitHub State Token requires only this repository's Contents write and State branch
access; GitHub does not offer branch-scoped token permissions. Branch protections
and exact transport path/CAS checks provide the separate restriction. Provenance
uses generated read-only GITHUB_TOKEN. No State branch or claim is created here.

### Separate Cloudflare operations

`cloudflare.py` supplies four native bounded kernels, never an automatic chain:

| Operation | Fixed future budget | Successful meaning |
|---|---|---|
| migration | GET 1, fixed read-query POST 1, DDL POST 1 | ACK only |
| migration_postcheck | GET 1, fixed read-query POST 1 | independent schema + immutable choice ledger verified |
| worker_deploy | GET 8, PUT 1 | new PARKED module package ACK only |
| worker_postcheck | GET 7 | independent module/source/exposure/DB/flags verification |

D1 REST query uses POST even for SELECT; read-query authorization must be separately
explicit. Successor 0011 is the only selected SQL. Baseline 0008/9/10 hashes, empty
runtime queue and absence of old 0011 schema are checked. The immutable choice
ledger records selected SQL hash and identity. Local transaction tests do not prove
REST multi-statement DDL atomicity: that remains a release blocker. Never apply both
0011 variants or automatically retry/rollback after an uncertain response.

The Worker package retains all 11 exact module hashes, DB binding, four safe flags,
zero routes/cron/consumers and disabled live composition; it is not activation.
Fresh source/exposure/token-window gates precede the sole PUT. Rollback evidence
pins the old source; actual rollback requires a different approval and identity.
No other account, Worker, D1, queue, route, Discord or SNS project is addressable.
Execution is prepared in this repository; CF role-specific credential registration
here is UNVERIFIED. Existing sandbox Secrets are not read or copied. Moving the
executor to the sandbox repository would itself require a separately reviewed
pinned preparation. The sandbox repository and its successful identities remain untouched.

### Remaining boundary

Native code is connected, but native service outcomes are NOT_TESTED. Outstanding
review/configuration includes owner Google consent, secure Secret registration,
channel match, State ACLs, real remaining free quotas, artifact handoff contract,
callback route/keys/checkpoint, D1 REST atomicity and Cloudflare credentials.
Each execution, migration and postcheck needs its own approval. After a successful
private upload, independent finalize is required; only then may a different job be
proposed. Continuous live dispatch/cron activation is a separate release, not a
result of these parked executors or the reused 48-hour simulation.
