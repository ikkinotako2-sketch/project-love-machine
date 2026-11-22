# TikTok Durable Claim SQLite Reference v1 (offline)

This is a reference implementation of `ClaimStore`, **not a production-store
decision**. `plm/tiktok/sqlite_claim.py` uses only Python's `sqlite3` and a
caller-supplied absolute local database path. It has no TikTok client, network
call, posting workflow, or automatic ownership takeover. No existing Action
invokes it. The next phase may compose it with offline render/preflight/mock
stages, but this phase adds no pipeline or posting permission.

## Schema and operations

`tiktok_claims` holds exactly `platform`, `account_id`, `job_id`,
`content_fingerprint`, `claimant`, `state`, `version`, `last_operation`,
`publish_id`, `created_at`, and `updated_at`. Timestamps are UTC ISO 8601;
they are observational and never grant ownership. The composite PRIMARY KEY
is `(platform, account_id, job_id)`. A trigger prevents changes to an existing
non-null `publish_id`, including clearing it. No secrets, credentials, OAuth
tokens, upload URL, Authorization header, raw API response, or arbitrary error
text belong in this schema. Access to the database file itself must be
restricted and backed up appropriately in any future deployment.

The first claim inserts; `ON CONFLICT ... DO NOTHING` then reads the existing
row within `BEGIN IMMEDIATE`. A same-claimant/same-fingerprint retry returns
the same record with `created=False`; a different claimant or fingerprint
raises `ClaimConflict`. This does **not** permit a second initialize. Every
state mutation reads the row under `BEGIN IMMEDIATE`, validates claimant,
version, and transition, then updates with `WHERE claimant=? AND version=?`
and increments the version. A stale write raises `InvalidClaimTransition`.
The transaction commits before the method returns. The in-memory and SQLite
stores share the existing `ClaimStore` method contract and recovery decision.

The reference opens one connection per instance with autocommit/explicit
`BEGIN IMMEDIATE` transactions, a five-second busy timeout by default,
`synchronous=FULL`, and the default DELETE rollback journal. It refuses an
existing database in another journal mode rather than silently changing it.
`SQLITE_BUSY`, I/O errors, or a failed commit are **not** posting permission;
callers must stop and read the authoritative record later. There is no
automatic retry around an ambiguous external operation.

## Crash boundary and recovery

| Durable state after connection close/reopen | Offline decision |
| --- | --- |
| claimed | Same claimant can recover the claim; independent consent and policy gates still apply |
| initializing, no publish_id | Manual reconciliation; never resend initialize |
| initialized, publish_id | Reconcile status; never resend initialize |
| transferring or processing, publish_id | Reconcile status; never resend initialize |
| unknown, publish_id | Reconcile status; never resend initialize |
| reconciliation_required, no publish_id | Manual reconciliation; never resend initialize |
| succeeded | Terminal no-op |

`begin_initialize` would commit the `initializing` marker before any future
external request. Yet a process can crash **after TikTok accepts initialize
but before the response or publish_id commit**. SQLite cannot commit atomically
with TikTok's remote service. On restart the record remains `initializing`,
or `reconciliation_required` if the ambiguity was saved. With no publish_id,
automatic status lookup may not be possible. Keep the job blocked for manual
reconciliation; never assume failure and retry initialize. No API integration
or manual reconciliation procedure is implemented here.

The tests close and reopen connections, exercise independent simultaneous
connections, and reject stale versions. They simulate process restart, not
power loss, filesystem failure, or a multi-machine production deployment.
Preflight PASS and claim existence still do not constitute creator consent or
posting authorization.

## Ownership takeover (unimplemented blocker)

An expired timestamp alone is unsafe: a paused or slow worker, delayed
network response, or clock skew can allow both the old and new workers to
act. Safe takeover would require a single authoritative store, durable
ownership epochs/fencing tokens checked on **every** mutation and before
external side effects, a way to prove or reconcile any in-flight remote
initialize, and an auditable operator decision when its outcome is unknown.
Even a DB fence cannot cancel an already sent TikTok request. This reference
therefore refuses other claimants indefinitely; manual review is needed.

## Operational assessment before production selection

- **Transactions and contention:** SQLite permits one writer at a time;
  `BEGIN IMMEDIATE` obtains a write transaction up front. Busy timeout only
  bounds lock waiting and does not turn a failure into success. Many readers
  can coexist with a writer subject to journal-mode locking behavior.
- **Durability:** `synchronous=FULL` requests filesystem sync at commit;
  guarantees still depend on OS, filesystem, storage hardware, and power
  behavior. The reference checks for DELETE journal mode. WAL might be
  evaluated later, but it requires co-located processes and is unsuitable
  across a network filesystem. Do not copy this SQLite file independently
  to multiple runners or place it on unvalidated shared storage.
- **Backup:** Use SQLite's online backup API (Python `Connection.backup`) or
  a verified consistent snapshot, not a live raw file copy. Test restore and
  `PRAGMA integrity_check` on the restored copy. Maintain permissions and
  backup retention without storing secrets in the claim record.
- **Corruption/recovery:** On integrity errors, I/O errors, or uncertain
  commits, stop writes and posting, preserve evidence, and restore/compare a
  known-good backup. Do not infer from missing local state that a remote
  initialize did not occur. A future runbook must define recovery authority.
- **Deployment:** Validate actual self-hosted volume lifecycle, local
  filesystem locking, backups, permissions, process boundaries, and
  concurrent-runner topology before selecting SQLite. None are configured
  or tested on Windows/Docker/n8n in this phase.

## Official references checked 2026-09-30

- https://www.sqlite.org/lang_transaction.html
- https://www.sqlite.org/pragma.html
- https://www.sqlite.org/wal.html
- https://www.sqlite.org/backup.html
- https://www.sqlite.org/howtocorrupt.html
- https://docs.python.org/3/library/sqlite3.html
