# Existing OAuth client reuse — OFFLINE only

Base repository: ikkinotako2-sketch/project-love-machine
Base branch: plm-youtube-production-connections-20261013-r1
Base HEAD: 5eaa0debe46aa394d8d6c509d02022f13eec7a6a

## Decision and evidence

Preserve both Google client secrets and the original PLM_YOUTUBE_GAME_001 JSON.
Run 38225716925, attempt 1 SUCCESS, injected that exact Secret reference after
its local gate and reported HTTP 200 / refresh POST 1. This proves historical
client-secret usability; current validity and which of the two Google secrets
is stored are UNKNOWN. Run 38258935081 is also historical SUCCESS. Neither run
nor any consumed identity is executed again.

The existing provider expects client_id/client_secret/refresh_token JSON. The
current SecretScope accepts that exact shape. It currently has no second-secret
selector. A small opt-in combiner can retain client_id/client_secret from the
original and take refresh_token from a client-bound candidate Secret. The new
module is NOT connected to any currently enabled workflow or release policy.
Old code, frozen source manifests, old markers and all safe flags are unchanged.

## Recover without seeing or replacing the client secret

1. Independently pin the public Client ID shown on the existing PLM YouTube OAuth
   Web application. Name equality alone is insufficient. This identifier is not
   the Client secret. Match it inside Actions against original JSON before any
   OAuth request; mismatch stops. Owner confirms exact registered redirect URI.
2. Prepare a public Google authorization URL with that Client ID, exact
   https://developers.google.com/oauthplayground redirect, response_type=code,
   the two scopes youtube.upload/youtube.readonly, access_type=offline,
   prompt=consent and a random, one-use state of at least 256 bits.
   No client_secret is required in that URL. Never put client_secret, access token
   or refresh token in any URL. A 300-second local admission window is a local
   safety rule, NOT a statement of Google's actual authorization-code lifetime.
   No authorization link is opened in this preparation.
3. Owner signs in and consents in the normal Google browser. Do not use the
   Playground default client and do not press its token-exchange button. The
   Google consent is what grants readonly; editing local scope strings is not.
   If selecting a Brand channel is offered, owner selects the intended channel;
   even then authenticated channel equality remains UNVERIFIED until separate
   channels.list(mine=true) verification.
4. Store the returned authorization code and returned state through an approved
   secure input (e.g. dedicated temporary GitHub Secret), never chat, workflow
   input/event payload, repository, log, URL copied to chat or artifact. Validate
   returned state against the pinned one-use context before exchange. Configure
   the reviewed exchange BEFORE starting consent so that a code does not sit
   waiting for workflow development. Never treat a missing/expired/unknown code
   as permission for a retry or a new consent automatically.
5. Separately approved, independently pinned one-shot Actions execution injects
   original JSON and secure code ONLY after its secret-free local gate. It sends
   ONE authorization_code POST to https://oauth2.googleapis.com/token, using
   original client_secret in memory, exact Client ID and redirect URI.
   Old refresh_token is neither refreshed nor replaced in this exchange. Require
   an actual new refresh_token and both returned grant scopes. Missing scope is
   UNKNOWN; insufficient scope stops; missing new refresh_token never falls back
   to the old token. No YouTube request is part of this execution.
6. Save only {client_id,refresh_token} into a distinct proposed candidate Secret
   PLM_YOUTUBE_GAME_001_REFRESH_V2. Do not overwrite the original JSON. Saving
   requires a separately approved GitHub credential with Secrets:write for ONLY
   this repository, not Contents/main write, Cloudflare or other repositories.
   The normal read-only GITHUB_TOKEN is not presumed sufficient. The connector
   currently available to Work does not expose Secret writes. Owner provisioning
   of this writer credential is still a blocker; none is created here.
   Preflight candidate metadata absent and repository encryption public key
   BEFORE OAuth exchange. Encrypt via reviewed LibSodium sealed-box implementation
   in memory and PUT only the exact candidate name. GitHub PUT is create-or-update,
   NOT atomic create-if-absent/CAS; owner operational exclusion and a unique
   approved candidate name are required. ACK missing/conflict/error => UNKNOWN,
   no second OAuth POST, no repeat Secret PUT, no old-secret modification.
7. Separate release review explicitly selects the candidate. Combine the new
   refresh token and original client_secret in memory and reuse MemoryOAuthRefresh
   and the existing OAuth provider. Missing/mismatched candidate must STOP; no
   fallback to old readonly-less grant. Independently approve channel verification
   (refresh POST <=1, mine GET <=1); no upload or activation follows automatically.

## Future bounded exchange approval, not granted here

Proposed identity: provider-neutral-youtube-client-reuse-exchange-20261014-r1
Marker: audit-evidence/consumed/provider-neutral-youtube-client-reuse-exchange-20261014-r1.json
State: NOT_CREATED / NOT_CONSUMED. Exact execution preparation is not yet published.
A real future runner needs its own fixed hashes, full-history gate, attempt=1,
marker-only commit, source/Client ID/redirect/state/source-secret/name/target pins,
protected Environment and explicit OAuth exchange plus candidate write approval.
Budget: OAuth authorization-code POST <=1, OAuth refresh POST=0, candidate metadata
GET<=1, repository encryption public-key GET<=1, candidate Secret PUT<=1. These
exclude separately bounded GitHub run/provenance prerequisite reads, whose exact
list must be fixed before future execution. YouTube/Cloudflare/State writes=0.
Retry/rerun/resume/redirect/fallback=0; raw/error body retention=0.

Offline code is pure memory composition and fixture protocol kernels. Its native
entry is PARKED. It intentionally cannot register a live capability or update a
real Secret. Native one-shot writer/encryption, approved workflow and adoption of
candidate references remain NOT_PREPARED until owner approves the new permission
and secure code-input mechanism. Do not call this production executor complete.

## Two existing Google secrets: fallback only if reuse cannot work

Do NOT disable or delete either secret merely because the owner cannot find its
value. Last successful refresh does not identify which of the two is stored.
If independently authorized reuse fails, distinguish wrong client/code/expired
code/scope/transport failure before declaring a client secret unusable.
Inventory consumers and enabled-secret metadata through owner-visible configuration;
unknown consumer association prevents disabling either secret. New Client ID is
not needed. Adding a secret to this SAME client can be proposed only after owner
identifies a safely replaceable slot (Google permits at most two secrets). That
specific disable/delete/add, secure registration, validation, consumer migration
and later cleanup each require explicit scope/approval. Do not assume the other
Google secret is unused. Preserve existing working grants until replacement is
independently proven. No such rotation is performed here.

## Local test result

22 focused tests PASS with socket/HTTP connection audit deny. Tests use synthetic
FIXTURE values only. Existing provider reuse, old JSON unchanged, opt-in selection,
client mismatch, duplicate fields, missing token/scope, state/time gate, errors,
redirect, timeout, unknown save, once-only behavior, no credential stdout/repr,
no native adapter authorization and no channel-match promotion are covered.
No renderer, historical CI or consumed OAuth run was rerun.

# 2026-10-15 implementation revision (supersedes NOT_PREPARED adapter statements)

Recovered the original 22 tests unchanged. Added the native implementation in
plm/automation/executors/oauth_exchange.py and a separate PARKED exchange workflow.
Its proposed identity is provider-neutral-youtube-client-reuse-exchange-20261015-r1,
not the previous unexecuted 20261014 proposal. No execution marker is created.
The current plan is disabled, with Client ID/state unset and every approval false.

## Implemented, not remotely exercised

* Exact local Git preflight before Secret injection: external prepared/plan/manifest
  pins, complete history, one preparation commit, plan-bound exact file diff,
  exact marker-only parent/message/content, repository/ref/push/run/attempt=1,
  clean source and safe flags. All prepared files except the manifest itself are
  covered. Neither a Secret nor workflow input can enable the current plan.
* FixedHTTP accepts Google authorization-code POST /token at most once. It never
  follows a redirect or reads an error body. HTTP/transport ambiguity is STOP.
* SecretWriter uses candidate metadata GET, repository public-key GET, candidate
  PUT only. No old-secret GET/PUT/delete, other name or other repository is allowed.
  Public key encoding and libsodium encryption are tested BEFORE OAuth exchange.
  crypto_box_seal is the official libsodium sealed-box function, called through a
  small ctypes binding. No custom encryption algorithm or paid service is used.
* Candidate save requires HTTP 201. HTTP 204 means unexpected update and stops as
  UNKNOWN. This does not make GitHub PUT atomic create-only; owner exclusion is a
  mandatory real execution prerequisite. Lost ACK never triggers readback/retry.
* CandidateOAuthTokenProvider loads the original JSON plus the candidate JSON,
  verifies Client ID, and reuses MemoryOAuthRefresh/the existing provider in memory.
  Missing candidate never falls back to the upload-only grant. Its interface is
  refresh() or get_access_token(); real transports require an existing separately
  approved channel/upload/finalize capability. Current old workflows remain intact;
  adoption of this new explicit provider is a separately reviewed release change.
* Only fixed reason codes, integer statuses, counters and grant-presence booleans
  appear in the exchange CLI output. No token/code/raw body, encrypted value or
  client-secret fingerprint is written to the result or any artifact.

## Still required BEFORE starting Google consent

1. Public Client ID from the existing PLM YouTube OAuth Web application. It must
   equal the original JSON's client_id in memory; matching a display name is not
   sufficient. Never supply Client secret, refresh token or auth code through chat.
2. Owner-approved temporary writer credential, limited to THIS repository with
   Secrets:write; permissions cover Secrets across the selected repository, not
   one individual secret. Code restricts the exact name, but token-level per-secret
   scoping is not claimed. Contents/Workflows/Admin/Cloudflare access is unnecessary.
   Standard GITHUB_TOKEN sufficiency is not assumed. Required environment name:
   plm-oauth-client-reuse-once, with owner approval/branch access protections checked.
3. Secure handoff approval: temporary environment Secret
   PLM_YOUTUBE_REAUTH_HANDOFF_ONCE containing only the below JSON structure with
   real values entered directly in GitHub, never ChatGPT or workflow dispatch:
   {"client_id":"PUBLIC_CLIENT_ID","code":"SECRET_AUTH_CODE","state":"EXPECTED_STATE","redirect_uri":"https://developers.google.com/oauthplayground","issued_at":0}
   issued_at is the owner-observed Unix time in seconds, checked within a 300s
   local admission window. This is not proof of Google's actual code expiry.
   GitHub Secrets have no assumed automatic TTL: owner cleanup of the handoff and
   revocation of the temporary writer are separate follow-up operations.
4. Consent state: a fresh cryptographically random 256-bit one-use public nonce,
   pinned alongside Client ID, redirect URI and the two scopes in the final reviewed
   release plan. Prepare and review this release BEFORE the owner starts consent.
   Use authorization_url(ConsentContext(...)) from oauth_reuse.py; do not include
   client_secret, code or tokens in that generated URL. It is not opened here.
5. Google normally delivers its authorization code via the registered redirect
   query. This inherent protocol step is NOT a mechanism for putting codes into
   a user-generated URL, logs or chat. Do not copy/share/store the full callback
   URL; do not inspect or screenshot it through Work. The code must be transferred
   directly by the owner into the secure handoff. Browser history/Playground's
   own handling has not been independently verified here. If the policy forbids
   even a transient Google callback query, the existing Playground redirect is
   incompatible and execution must STOP pending a separately approved receiver;
   this preparation does not silently replace redirect URIs or claim to prevent
   Google/browser URL history. No OOB flow is introduced.
6. Publish a separately reviewed release update with exact hashes, Client ID/state,
   approved handoff/writer/operational exclusion and owner execution approval.
   Change the workflow job from unconditional false only under that release review.
   Marker-only commit before remote remains mandatory. All current safe flags true.

## Future exact requests and outcome

GitHub Secrets: GET candidate metadata once; GET repository public key once;
Google: authorization-code POST once; GitHub: candidate encrypted PUT once.
No refresh POST, tokeninfo, YouTube GET, upload, dispatch, CF or State call is added.
Scopes unknown/insufficient or new refresh token missing => no candidate write.
Save ACK success means only candidate storage acknowledged, NOT current refresh
validity or channel match. Verify the latter with its own independent identity and
approval. Never rerun this exchange after any outcome, including timeout/UNKNOWN.
If the writer permission cannot be provisioned, STOP before OAuth: do not exchange
and then print/download a refresh token for manual saving. A same-client Google
secret rotation is a separately approved last resort, after consumer impact review;
with two secrets already present, do not disable either merely to make room.

## 2026-10-16 deadline correction and saved Environment audit

The handoff local 300-second window is checked again immediately before the
sole Google POST, after writer preflight and form construction. Expiry at the
exact boundary, elapsed preflight, or a clock earlier than issued_at stops with
zero OAuth POST / candidate PUT; the permit remains used and cannot be retried.
This bounds local request admission, not Google's actual code lifetime or network
arrival time. GitHub queue and reviewer delays are not guaranteed to fit 300s.

Read-only owner UI audit: Environment plm-oauth-client-reuse-once exists, required
reviewer ikkinotako2-sketch, prevent_self_review=false, administrator bypass=false,
only branch plm-youtube-oauth-recovery-20261015-r1 (zero tags). No Environment
secrets or variables were present at the audit. No setting was changed by Work.

Client ID and cryptographic consent state remain unset, all approvals false,
plan disabled, workflow unconditional PARKED. No consent or handoff starts yet.
Before consent, freeze the public Client ID/state and release hashes; provision
the short-lived writer directly into the protected Environment with only this
repository selected and Secrets read/write, no additional optional permissions.
Set the three non-secret workflow pin variables only for that final release.
The original Secret stays repository-scoped and unchanged; the writer/handoff
are Environment-scoped. Never create a placeholder candidate Secret: it must
remain absent until the separately approved encrypted creation.

After explicit execution approval: owner consents, directly submits the handoff
JSON in GitHub, the one marker commit starts attempt 1, owner reviews promptly,
and the runner stops without exchange if the local window elapsed. No automatic
retry, new identity, new consent, handoff deletion or writer revocation follows.
Cleanup and revocation require their separately authorized owner actions.
Google callback URLs must not be copied to Work or captured in logs/screenshots.
The existing Playground redirect inherently returns the code in a query; browser
history retention is not proven absent. If that transient callback is unacceptable,
STOP and review a separate receiver rather than claiming this route is safe.

## 2026-10-16 public consent pin revision

The owner supplied candidate Client ID
559247977069-e50008qnmkuath6qbkbmetqsu6lvls84.apps.googleusercontent.com
is pinned as an UNVERIFIED screenshot transcription, not as a verified current
Google Cloud value. The Cloud Clients page is unavailable in this browser; the
referenced screenshot was not resolved. Do not start consent on this basis.
client_id_owner_verified=false is an additional secret-free admission gate, not
an owner attestation that Work may infer. Obtain a direct copy of the public
Client ID from the existing PLM YouTube OAuth Web application and its registered
Playground redirect. Do not ask for either client secret. Actions still compares
the pinned ID exactly against both the original Secret JSON and handoff JSON.

A single new public consent-state nonce was generated with Python secrets from
32 random bytes (256 bits) and pinned in the plan. It has not been used in any
Google request. Reuse this prepared nonce for this identity only; never reuse it
after execution/consent attempt. No URL containing a returned code is generated,
opened or saved. The plan and workflow remain PARKED; all approvals remain false.

Owner-only writer provisioning after separate access approval:
GitHub Settings > Developer settings > Personal access tokens > Fine-grained
tokens. Resource owner ikkinotako2-sketch; only selected repository
project-love-machine; Repository permissions Secrets: Read and write only, plus
GitHub's implicit Metadata read. Use a short available expiration, no Contents,
Actions, Workflows, Administration, Cloudflare, or other repository grants.
Token permissions cannot restrict one Secret name; code fixes the V2 name.
Enter the token directly into Environment plm-oauth-client-reuse-once as
PLM_GITHUB_OAUTH_SECRET_WRITER. Never put it into chat, a file or a variable.
Creation/registration is not authorized by this preparation and was not performed.
Do not create the V2 candidate or handoff yet. The V2 must be absent at execution.
The writer must be revoked and temporary handoff removed after the terminal
result under separate cleanup authority, including UNKNOWN; no exchange retry.

Before owner consent, a separately reviewed release must confirm the public ID,
redirect and writer permissions, freeze exact source/plan/manifest/commit pins
and populate the three nonsecret Environment pin variables referenced by the
workflow. Do not enable the runner or consume its marker in this preparation.

## 2026-10-18 bounded-attempt policy (supersedes the success-guarantee blocker)

Owner no longer requires exchange success within 300 seconds. The ONLY accepted
policy is BOUNDED_SINGLE_ATTEMPT_NO_SUCCESS_GUARANTEE. The 300s local cutoff,
Google's own code validity, pre-POST recheck and all no-retry limits are unchanged.
Owner-confirmed exact Client ID copy is now recorded; this is owner evidence,
not an independent Google Cloud API verification. Writer registration is previously
independently observed; current PAT permissions/expiry remain owner-attested and
must be checked in the owner UI before consent, without exercising the token.
Current enabled/owner_approved/handoff_approved/writer_permissions_reviewed and
operational_exclusion_attested remain false; workflow is still unconditional PARKED.

The existing 256-bit nonce is unused. First publication 2026-10-16T12:05:09Z is
recorded separately from exact generation time (not recorded). It is not an
authorization code and its age alone does not extend/shorten Google's code TTL.
Build a fresh timed ConsentContext immediately before actual owner consent under
separate approval; no Google URL has been opened. If any prior consent use is
unknown, STOP, never assume nonce or identity reuse is safe.

BEFORE consent, without code/token exchange:
- Freeze final reviewed commit/workflow/plan/manifest pins and marker bytes; verify
  clean full history, unused identity, no existing exchange run and candidate absent.
- Review workflow activation separately; keep safe flags true. Complete Environment
  reviewer/branch/no-admin-bypass settings, owner review availability, and writer
  selected-repository Secrets read/write + expiration check before asking for code.
- Separately authorize exact nonsecret Environment variables PLM_OAUTH_REUSE_PREPARED,
  PLM_OAUTH_REUSE_PLAN_SHA256 and PLM_OAUTH_REUSE_MANIFEST_SHA256 for that release.
  Do not set enabled/approval flags merely because these preparation tests pass.
- Prepare an empty local handoff FORM/TEMPLATE in the owner's trusted input surface,
  never a placeholder Secret. Prepare exact marker-only operation and review screen.
  No secret/candidate write, PAT use or marker creation occurs in this preparation.
- Owner agrees to exclusive updates of candidate/handoff for the entire attempt.
  Repository Secrets API PUT is not atomic create-only; do not claim a race is solved
  by a metadata GET. Public-key/absence GETs stay in the approved execution budget.

AFTER separate explicit consent/exchange/save/marker approval, not now:
1. Recheck HEAD, exact hashes, writer owner-visible expiration/permissions and
   protections BEFORE opening the correctly pinned Google authorization URL.
2. Owner logs in/consents; records actual code-receipt Unix time issued_at without
   resetting it later. Google returns code/state via the registered callback query.
   Never copy that URL into Work, logs, screenshots or artifacts. Playground/browser
   retention is not proved absent. If this handling is unacceptable, STOP.
3. Owner enters the handoff JSON directly into the exact Environment Secret ONCE;
   complete its save before the marker push. Do not put it in repository Secrets.
4. Commit the one marker, trigger attempt 1, promptly obtain Environment review.
   Required review is per-run and cannot be pre-approved before the run exists.
5. Runner starts and obtains Environment Secrets at job start; local source gate
   runs before the explicit Secret-injection step. A running job is NOT assumed
   to reload later updates. Metadata presence/updated time does not prove content
   propagation. Missing/stale/mismatched/expired input => STOP; no updates and rerun.
6. Validate code/state/client/redirect and issued_at <= now < issued_at+300, do
   bounded candidate/key preflight GETs, then repeat the time check immediately
   before sole Google POST. Runner/review/network queues can consume the window.
7. Google rejection, timeout, redirect, UNKNOWN => terminal STOP, zero resend.
   Require a new refresh token and both explicitly returned scopes; absent scope
   is UNKNOWN. Encrypt candidate in memory; candidate PUT <=1, only 201 ACK passes.
8. Preserve marker regardless of outcome or POST count; show sanitized outcome.
   Cleanup handoff and revoke only this writer under separate cleanup authority.
   Storage ACK is not grant-current-validity/channel match/upload permission.
   Channel verification is a separately approved one-shot operation.

POST=0 with a marker is PERMANENTLY CONSUMED, never resumable. Future recovery
requires separately reviewed fixed new identity/state/source pins, evidence of
previous terminal outcome and owner approval for any new consent/exchange.
If POST/PUT was attempted and ACK is unknown, do not assume rollback/no token: use
only separately approved metadata/recovery inspection, never automatic resend.
Do not delete old consumed markers or recreate old handoffs.

Alternatives (not implemented or authorized here): current Environment handoff
uses existing infra and fails closed but incurs owner-review and runner latency;
a prestarted runner cannot receive a later Secret value automatically. A dedicated
short-lived encrypted authenticated handoff receiver could move queue/review before
code receipt, but needs separate hosting/credential/retention/redirect/security
review and authorization, and still cannot guarantee network success. Local owner
exchange would require handling client secret outside existing Actions and is not
selected. No measured success probability exists; do not claim either high or low
probability, extend the deadline, bypass reviews, or add hosting automatically.

## Final release configuration: configuration is not execution consent

This revision supersedes unconditional workflow PARKED and enabled=false statements
above. The existing marker-only push trigger, exact branch and attempt=1 job filter
are armed, with no dispatch/schedule/new entry. Plan enabled=true and
release_configured=true mean configuration only. The four plan execution approval
fields remain FALSE and changing them to true is rejected. Exact future marker
execution_approval must contain all four separately owner-approved attestations
TRUE. Missing marker returns PARKED before any Git/Secret/transport access.
A later separately approved marker-only commit is the sole execution admission;
no such marker is created by release configuration. Full history, exact preparation
diff and all source pins still apply after that future marker exists.

Owner attests writer selected repo, Secrets read/write, expiration 2026-10-23.
This is not a token-value inspection or a live validity probe. Keep Environment
reviewer, exact branch restriction, admin bypass prohibited. Populate ONLY the three
nonsecret pin variables from this actual release commit/plan/manifest, never its
PARKED predecessor. Settings approval is not OAuth consent or handoff approval.
The existing 300s local admission and immediate pre-POST recheck are unchanged.
Future exact marker includes identity/state/approved/prepared_commit_sha and five
source hash fields plus execution_approval with owner_approved,
operational_exclusion_attested, writer_permissions_reviewed, handoff_approved TRUE.
These attest actual separate future approval and fresh exclusion/handoff checks;
they must not be asserted from this configuration approval alone.

No Google consent/POST, PAT use, Secret operation, execution marker, YouTube,
Cloudflare or other project operation occurs in this release. Finalization stops
after source/CI/pin-variable readback and reports marker preview outside consumed
paths. Actual execution and cleanup require their separate owner approvals.
