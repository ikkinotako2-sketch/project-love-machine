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
