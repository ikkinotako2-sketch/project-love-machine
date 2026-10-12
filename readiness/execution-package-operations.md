# Frozen execution preparation; no activation

This package builds on commit 26da3b48e26d7ee8a75e70798fb00847d8fa8f04.
Its eight operation identities are proposed only. No marker exists; no identity
is approved or consumed. Both the CLI and workflow remain unconditionally parked.
A valid history/marker fixture does not authorize a transport or inject Secrets.

## Resume order

1. Owner grants youtube.upload + youtube.readonly using the existing OAuth client.
   Work cannot bypass Google consent. Secret replacement requires separate approval.
2. Review and prepare an enabled successor channel executor, then separately approve
   one refresh POST and one channels.list(mine=true) GET. Scope omission is UNKNOWN;
   channel mismatch is STOP. Protect the unused historical channel identity.
3. Prepare a dedicated protected State branch using the offline initial document.
   Require repository-scoped Contents write only; no force updates, tombstone
   deletion or main write. Initialization and upload consumption are distinct actions.
4. Freeze artifact origin/archive digest/media digest; exact upload protocol and
   HTTP limits; current quota observation; the independent upload run proof; separate
   finalize run proof; and approval markers. Upload is private, notify false.
   An ACK is ACKNOWLEDGED, not Done. Unknown state writes stop all further writes.
5. Only separately reviewed completed-run/readback/callback receipts authorize the
   coordinator to complete this job and propose a distinct next job. Same-job
   tombstones never reset. Release of global STOP needs separate authority.
6. Cloudflare 0011 application, postcheck, successor runtime deploy and postcheck
   require their own bounded executors and approvals. They are intentionally not
   executable in this package. Never apply both old and successor 0011. Fresh source,
   routes/exposure, bindings, actual quota and operational exclusion gates are required.

## Hash and history contract

The externally reviewed plan hash is authoritative. It pins the exact preparation
file list; one preparation commit; base parent; operation identities and budgets.
The externally reviewed marker hash pins the one added marker file; that marker
pins prepared commit, plan, source manifest, schema, executor and parked workflow.
Source manifest hashes all existing candidate files plus this package, excluding
itself. Never derive an approval hash from untrusted working-tree data alone.
All Git audit reads are local, full-history, bounded, credential-free and immutable.
Protected consumed marker hashes are historical evidence, never success prerequisites.

## Boundaries still unapproved

Upload budget is a logical attempt, not a claim of one HTTP request. Resumable
session creation/media transmission must be frozen before approving a live uploader;
no timeout recovery, status probing, chunk retry or resume may be silently added.
The candidate factory remains offline-only. The package does not unlock it.
Post-upload readback needs separate read scope and approval. Incomplete processing
is UNKNOWN with no automatic polling or reupload.
Mutable main fallback is forbidden. Raw SHA dispatch acceptance remains UNVERIFIED.
Actual free account balances remain UNKNOWN, never inferred from fixture budgets.
No cron, consumer, public route or runtime activation is enabled here.

## Incident response

UNKNOWN: stop, persist only sanitized evidence where safe, no resend/reclaim or
automatic rollback. A lost State write ACK poisons the session. Independent completed
run proof is required even if a later read finds a Done row. Do not delete any marker.
Restore previous parked Worker only under a new explicit rollback approval after fresh
read-only inspection. OAuth expiry stops and enqueues an undelivered notification.
