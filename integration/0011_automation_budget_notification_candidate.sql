-- OFFLINE proposal ONLY. Not applied; cannot be imported by an execution workflow.
CREATE TABLE plm_auto_v1_budget(day TEXT PRIMARY KEY, jobs INTEGER NOT NULL DEFAULT 0 CHECK(jobs BETWEEN 0 AND 2), units INTEGER NOT NULL DEFAULT 0 CHECK(units BETWEEN 0 AND 1000));
CREATE TABLE plm_auto_v1_notice(job_id TEXT PRIMARY KEY REFERENCES plm_rt_v2_job(job_id), reason TEXT NOT NULL CHECK(reason IN ('UNKNOWN','AUTH_STOP','BUDGET_STOP','CONFIG_STOP')), delivered INTEGER NOT NULL DEFAULT 0 CHECK(delivered IN (0,1)));
CREATE TRIGGER plm_auto_v1_notice_no_delete BEFORE DELETE ON plm_auto_v1_notice BEGIN SELECT RAISE(ABORT,'notice_tombstone'); END;
