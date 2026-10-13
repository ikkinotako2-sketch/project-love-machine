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
