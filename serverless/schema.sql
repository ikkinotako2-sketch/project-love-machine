-- Offline PoC schema; not applied to Cloudflare in this PR.
CREATE TABLE IF NOT EXISTS test_jobs (
 platform TEXT NOT NULL CHECK(platform='test'),
 account_id TEXT NOT NULL CHECK(account_id='test_reference_001'),
 job_id TEXT NOT NULL,
 content_fingerprint TEXT NOT NULL,
 claimant TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('ready','dispatching','running','succeeded','unknown')),
 version INTEGER NOT NULL CHECK(version>0),
 last_operation TEXT NOT NULL,
 run_id TEXT,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 PRIMARY KEY(platform,account_id,job_id)
);
-- Proposed publish record only; no posting implementation uses this table.
CREATE TABLE IF NOT EXISTS publish_claims (
 platform TEXT NOT NULL,
 account_id TEXT NOT NULL,
 job_id TEXT NOT NULL,
 content_fingerprint TEXT NOT NULL,
 claimant TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('claimed','initializing','initialized','transferring','processing','succeeded','failed','unknown','reconciliation_required')),
 version INTEGER NOT NULL CHECK(version>0),
 last_operation TEXT NOT NULL,
 publish_id TEXT,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 PRIMARY KEY(platform,account_id,job_id)
);
CREATE TRIGGER IF NOT EXISTS publish_id_immutable
BEFORE UPDATE OF publish_id ON publish_claims
WHEN OLD.publish_id IS NOT NULL AND NEW.publish_id IS NOT OLD.publish_id
BEGIN SELECT RAISE(ABORT,'publish_id immutable'); END;
