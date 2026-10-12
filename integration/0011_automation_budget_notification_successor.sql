-- Independent OFFLINE successor to unapplied 0011. Do not apply both candidates.
CREATE TABLE plm_auto_v1_budget(day TEXT PRIMARY KEY,jobs INTEGER NOT NULL DEFAULT 0 CHECK(jobs BETWEEN 0 AND 2),units INTEGER NOT NULL DEFAULT 0 CHECK(units BETWEEN 0 AND 1000));
CREATE TABLE plm_auto_v1_reservation(job_id TEXT PRIMARY KEY REFERENCES plm_rt_v2_job(job_id),day TEXT NOT NULL REFERENCES plm_auto_v1_budget(day),units INTEGER NOT NULL CHECK(units BETWEEN 1 AND 1000));
CREATE TRIGGER plm_auto_v1_reserve_guard BEFORE INSERT ON plm_auto_v1_reservation
WHEN NOT EXISTS(SELECT 1 FROM plm_auto_v1_reservation WHERE job_id=NEW.job_id)
 AND (NOT EXISTS(SELECT 1 FROM plm_auto_v1_budget WHERE day=NEW.day) OR EXISTS(SELECT 1 FROM plm_auto_v1_budget WHERE day=NEW.day AND (jobs>=2 OR units+NEW.units>1000)))
BEGIN SELECT RAISE(ABORT,'atomic_budget_limit'); END;
CREATE TRIGGER plm_auto_v1_reserve_budget AFTER INSERT ON plm_auto_v1_reservation BEGIN UPDATE plm_auto_v1_budget SET jobs=jobs+1,units=units+NEW.units WHERE day=NEW.day; END;
CREATE TRIGGER plm_auto_v1_reservation_immutable BEFORE UPDATE ON plm_auto_v1_reservation BEGIN SELECT RAISE(ABORT,'reservation_immutable'); END;
CREATE TRIGGER plm_auto_v1_reservation_no_delete BEFORE DELETE ON plm_auto_v1_reservation BEGIN SELECT RAISE(ABORT,'reservation_tombstone'); END;
CREATE TABLE plm_auto_v1_notice(job_id TEXT PRIMARY KEY REFERENCES plm_rt_v2_job(job_id),reason TEXT NOT NULL CHECK(reason IN ('UNKNOWN','AUTH_STOP','BUDGET_STOP','CONFIG_STOP')),delivered INTEGER NOT NULL DEFAULT 0 CHECK(delivered IN(0,1)));
CREATE TRIGGER plm_auto_v1_notice_no_delete BEFORE DELETE ON plm_auto_v1_notice BEGIN SELECT RAISE(ABORT,'notice_tombstone'); END;
