# TikTok Durable Claim & Recovery v1 (offline contract)

This is an offline state contract and an in-memory test double, **not** a
posting implementation or a production durable store. No workflow or Action
invokes it. The open eligibility, developer review, and creator-facing UX
requirements in `TIKTOK_ADAPTER_V1_DESIGN.md` remain blockers.

## Identity and atomic operations

The unique key is `(platform=tiktok, account_id, job_id)`; the immutable
content fingerprint is a SHA-256 hex digest of a future canonical posting
intent. Canonicalization must bind video bytes and editable metadata after
creator confirmation; its exact definition remains to be designed. A store
must atomically insert the first claim, return an existing record only to the
same claimant with the same fingerprint, and reject other claimants or changed
content. Every mutation checks the stored version and claimant, and commits
durably before the caller proceeds. `ClaimStore` specifies this interface;
`InMemoryClaimStore` uses a lock solely to exercise it in tests. Its state
vanishes on process exit and is **not safe for live posting**. A real backend
must also define a fenced, auditable ownership handoff for dead workers; none
exists here, so another worker is rejected even after a crash.

The implementation validates account and job identifiers using existing PLM
rules and rejects obvious secret-bearing text; the record has an allowlisted
shape: key, fingerprint, claimant_id, state, version, last_operation, and
optional publish_id. It does not hold a credential, token, upload URL,
Authorization header, raw API response, or arbitrary error string. This
validation is defense in depth, not a substitute for access control or data
classification in a future store.

## Initialize and reconciliation boundary

`claimed` alone is only a candidate for a future initialize operation. After
fresh creator info, preview, editable caption, selected privacy, disclosures,
explicit creator consent, and policy eligibility are independently verified,
a future caller would commit `begin_initialize` (`initializing`) **before**
any network request. This marker makes a lost response conservative. If the
request succeeds and yields a publish_id, `persist_publish_id` must commit the
validated ID once immediately; a second write or initialize is rejected.
Tokens and raw responses are never persisted.

If the request might have reached TikTok but the response is lost, mark it
`reconciliation_required` if possible. A crash before this update leaves
`initializing`; both states require manual reconciliation and forbid automatic
initialize. Even an apparent HTTP failure after an attempt is not enough to
clear the marker unless a future authoritative protocol establishes that the
request could not have been accepted. There is an unavoidable window between
TikTok accepting the request and our publish_id commit. This contract cannot
recover that ID by itself and deliberately leaves the job blocked rather
than retrying. No live status lookup or reconciliation implementation exists.

Storage states `claimed` and `initializing` precede the existing offline
result states. `initialized`, `transferring`, `processing`, `succeeded`,
`failed`, and `unknown` align with the result/preflight vocabulary;
`reconciliation_required` is the explicit hold for ambiguous initialization.
Here `failed` is terminal: automatic retry would require a separately
reviewed policy and reconciliation. No transition returns to `claimed` or
`initializing` after an attempt. `recovery_decision` is a pure hint, never
posting authorization:

| Persisted condition | Hint | Initialize again? |
| --- | --- | --- |
| no claim | claim_candidate | No, claim and eligibility first |
| claimed, no publish_id, last operation claim | begin_initialize_candidate | Only after the independent gates and durable attempt marker |
| initializing or reconciliation_required | manual_reconciliation | No |
| initialized/transferring/processing/unknown, publish_id present | reconcile_status | No |
| those states without publish_id | manual_reconciliation | No |
| succeeded or failed | no_op | No |

## Offline crash scenarios

| Scenario | Persisted observation | Decision |
| --- | --- | --- |
| A. Stop before claim | no record | Claim candidate; no initialize occurred |
| B. Stop after claim, before attempt | claimed, no publish_id | Same claimant may reload; eligibility/consent gates still required |
| C. Stop after ID commit | initialized, publish_id | Reconcile status, never initialize again |
| D. Acceptance possible, response lost | initializing, then reconciliation_required if update succeeds | Manual reconciliation only |
| E. Stop during transfer | transferring, publish_id | Reconcile/resume plan; no initialize |
| F. Stop during processing | processing, publish_id | Reconcile status; no initialize |
| G. Repeat after success | succeeded | No-op |

The tests model a retained store and concurrent threads, not a process or
machine crash. Production crash safety is unproven until a durable backend is
selected and tested with forced process termination and concurrent runners.

## Storage candidates ($0 target, none adopted)

| Candidate | Atomicity/concurrent runners | Crash safety/durability | Backup, cost, complexity |
| --- | --- | --- | --- |
| Self-hosted n8n Data Table | Composite unique insert and compare-and-swap transaction guarantees for this contract are not established by the public Data Tables docs; must validate implementation and shared access | Depends on n8n database and backup; cannot assume an Upsert is an atomic claim | Existing infrastructure, $0 possible; backup with n8n DB; low integration effort but unproven semantics |
| SQLite on persistent shared host storage | Unique `(platform, account_id, job_id)` plus `BEGIN IMMEDIATE` transaction/version update can implement single-writer claim; must avoid separate runner-local copies | Transactional commit, subject to correctly configured persistent storage and durability settings | $0; file backup with consistent snapshot; moderate implementation/operations; shared network filesystem locking needs separate validation |
| Repository/file storage | Plain file existence/write is not a cross-run atomic unique transaction | Runner-local files disappear; a shared filesystem needs locking, fsync, recovery design | $0 possible; backup manageable; high concurrency risk |
| GitHub branch/result JSON | Actions concurrency and ordinary commit conflicts do not prove atomic first claim or fenced ownership across concurrent runners | Git history is durable but lost response and retry windows remain | $0 within plan limits; existing repo backup; high protocol/API complexity and unresolved atomicity |

No production backend is introduced in this PR. Selection, deployment,
transactional uniqueness/version enforcement, backup/restore testing, and
multi-runner crash tests remain blockers. A distributed runner setup needs a
single authoritative store; an Actions concurrency group alone is not one.

## Preflight boundary

`tiktok-preflight/<job_id>.json` reports static media/metadata evidence.
**Preflight PASS is not posting permission.** The future sequence is preflight,
durable claim, creator-facing confirmation and explicit consent, then the
durably committed initialize-attempt marker, and only then a separately
reviewed API integration. No code here creates or infers consent, chooses a
fixed privacy setting, makes an API call, or starts an Action.

## Documentation checked 2026-09-30

- https://www.sqlite.org/lang_transaction.html
- https://www.sqlite.org/atomiccommit.html
- https://docs.n8n.io/data/data-tables/
- https://docs.github.com/en/rest/git/refs
- https://developers.tiktok.com/docs/en/content-sharing-guidelines
