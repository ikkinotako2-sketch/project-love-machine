# OAuth repair R2 — OFFLINE, not execution approval

R1 run 40092439824, attempt 1, stopped at INPUT_JSON_STOP. Local gate passed;
Google POST 0, candidate PUT 0, GitHub writer requests 0. The existing credential
parser uses a different reason code, so this failure identifies the handoff
JSON parser. Invalid JSON and duplicate keys share that R1 reason code. The
specific saved content is UNKNOWN and must never be retrieved or echoed.
Truncation, an extra string wrapper, raw callback/code, or a replaced clipboard
are possible causes, not confirmed owner mistakes. The formatter itself emits
valid JSON for the tested inputs; that does not prove what GitHub stored.

## Reproduction and repair

Node executes the actual standalone HTML event handler with dummy pins, callback,
receipt time and clipboard. Python passes its exact string through a simulated
Environment loader into the R2 parser/executor. It never contacts Google/GitHub.
Cases include punctuation/escaping, CRLF, JSON whitespace, missing/extra/duplicate
keys, string-wrapped JSON, damaged copies, BOM, invalid encoding, float/bool/string
timestamps, and invalid Unicode/control characters. Invalid input is rejected,
never silently corrected. Errors are fixed reason codes without input text.

The new owner-local helper requires a pasteback comparison before advising
GitHub saving. It compares the clipboard string to the generated JSON in memory;
it does not read the clipboard itself or save the Secret. The owner must paste
the same entire JSON into the Environment Secret Value field without copying
anything else between the local check and GitHub. This cannot prove remote
storage correctness; the Runner still independently rejects malformed input.
Do not paste values, callback URLs or screenshots into ChatGPT.

## Independent R2

Identity: provider-neutral-youtube-client-reuse-exchange-20261024-r2

Marker: audit-evidence/consumed/provider-neutral-youtube-client-reuse-exchange-20261024-r2.json

The separately authorized release enables the plan and marker-only workflow.
Execution is still blocked before credential injection because no R2 marker exists.
All approval flags remain false. No marker is created by this preparation.
R1 marker SHA256 is pinned in the R2 plan and checked in parent, preparation,
execution HEAD and worktree by the future gate. R1 cannot be rerun. Legacy tests
now assert R1's consumed state is blocked; the R1 runtime and frozen pins stay
unchanged. The independent branch never changes main or the recovery branch.

## Separate future approvals and settings

1. Review the exact R2 source/manifest/plan and OFFLINE CI. Do not start consent.
2. A separately approved final release is required to enable the plan/workflow,
   pin that release's exact preparation history, and set R2 nonsecret variables:
   PLM_OAUTH_REUSE_R2_PREPARED, PLM_OAUTH_REUSE_R2_PLAN_SHA256,
   PLM_OAUTH_REUSE_R2_MANIFEST_SHA256. Release configuration may set only those three nonsecret variables.
3. The protected Environment currently restricts R1's branch. Separately approve
   an exact R2 branch rule; retain Required reviewer and no admin bypass. Do not
   loosen protection or change another project's settings.
4. Recheck the writer's repository-only Secrets Read/write permission and expiry
   (owner configured 2026-10-25). Never claim its validity from metadata alone.
5. New consent, original receipt time and handoff saving require separate approval.
   New handoff Environment Secret: PLM_YOUTUBE_REAUTH_HANDOFF_R2_ONCE. Never load
   stale R1 handoff. Existing PLM_YOUTUBE_GAME_001 is immutable. Candidate target
   remains PLM_YOUTUBE_GAME_001_REFRESH_V2; metadata must show absent before POST.
6. Approve exactly one future marker-only commit, then owner Environment review.
   R2 is permanently consumed on marker creation even if expiry causes POST 0.

Limits stay: candidate metadata GET 1, repository public-key GET 1, Google
authorization-code POST 1, candidate Secret PUT 1. Only PUT 201 is success.
300 seconds starts at the original code receipt; check before writer preflight
and immediately before POST. No retry/rerun/resume/redirect/fallback. Google error,
missing refresh token, absent/insufficient scopes or unknown save ACK stops.
No token-info GET, channel GET, upload, Cloudflare, cleanup or PAT revocation is
authorized here. Channel matching remains UNVERIFIED and needs separate approval.

R2 has a new unused 256-bit preparation state, not a new grant. Do not reuse R1
consent, codes or identity. A future release must review state validity and
supersede an unused state explicitly if needed; never reset a receipt timestamp.

Secret persistence ACK does not prove current token validity, channel match,
upload permission in practice, or any posting approval.

## Final release configuration (not OAuth execution authorization)

The state-refresh release is one exact commit after
680083fb5dca00bee6c288f00bafa76a25090c17. Its plan binds the five preparation
files exactly; the manifest covers the complete candidate plus historical
evidence. Executor, schema and workflow remain unchanged. The owner confirmed
using the prior R2 consent; that state is retired by hash. The replacement is
a fresh 256-bit preparation state, unused in Google consent. Only the helper
configuration and matching CSP hash change; no state value, code, token or
credential is logged. This update neither authorizes nor performs consent,
Secret operations, marker creation or exchange. A future execution approval
must explicitly bind the new immutable release HEAD.

Enabling the marker-only trigger is configuration only. All four plan approval
flags remain false and local_gate returns no permit before Secret injection if
the marker is absent. No dispatch, schedule or alternate execution entry is added.
The future exact marker requires independently authorized execution approvals.

Environment rule must be replaced from the consumed R1 branch to exactly
plm-youtube-oauth-repair-20261024-r2 (one branch, zero tags), never All branches.
Keep the existing reviewer and no administrator bypass. Do not edit old Secrets,
old nonsecret variables, or the consumed R1 marker. The new R2 handoff Secret
creation dialog may be opened empty; do not submit until separately approved.

Before a new Google consent, all screens and original-receipt clock entry must
be ready. The owner-local helper performs pasteback validation. Then only the
owner may save the new handoff and approve the Environment review; neither action
is authorized by final release configuration. The 300-second limit remains,
and marker creation consumes R2 permanently even if POST count stays zero.
