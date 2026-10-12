-- OFFLINE PROPOSAL ONLY; depends on exact unapproved 0008 candidate schema.
-- No existing object/row alteration and no Cloudflare application authorization.
CREATE TABLE plm_ytq_v1_queue (
 job_id TEXT PRIMARY KEY REFERENCES plm_rt_v2_job(job_id),
 account_id TEXT NOT NULL CHECK(account_id='youtube_game_001'),
 intent_id TEXT NOT NULL UNIQUE CHECK(length(intent_id) BETWEEN 1 AND 64),
 script_sha256 TEXT NOT NULL CHECK(length(script_sha256)=64 AND script_sha256 NOT GLOB '*[^0-9a-f]*'),
 owner TEXT NOT NULL CHECK(length(owner) BETWEEN 1 AND 64),
 owner_epoch INTEGER NOT NULL CHECK(typeof(owner_epoch)='integer' AND owner_epoch>0),
 fencing_token INTEGER NOT NULL CHECK(typeof(fencing_token)='integer' AND fencing_token>0),
 not_before INTEGER NOT NULL CHECK(typeof(not_before)='integer' AND not_before>0),
 state TEXT NOT NULL CHECK(state IN ('QUEUED','CLAIMED','DISPATCHED','UNKNOWN','COMPLETE')),
 version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version>0),
 created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>0),
 updated_at INTEGER NOT NULL CHECK(typeof(updated_at)='integer' AND updated_at>=created_at)
);
CREATE TABLE plm_ytq_v1_outbox (
 dispatch_id TEXT PRIMARY KEY CHECK(length(dispatch_id)=64 AND dispatch_id NOT GLOB '*[^0-9a-f]*'),
 job_id TEXT NOT NULL UNIQUE REFERENCES plm_ytq_v1_queue(job_id),
 payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256)=64 AND payload_sha256 NOT GLOB '*[^0-9a-f]*'),
 state TEXT NOT NULL CHECK(state IN ('RESERVED','SENT','UNKNOWN','CONFIRMED')),
 send_attempts INTEGER NOT NULL CHECK(typeof(send_attempts)='integer' AND send_attempts IN (0,1))
);
CREATE TABLE plm_ytq_v1_result (
 job_id TEXT PRIMARY KEY REFERENCES plm_ytq_v1_queue(job_id),
 result_id TEXT NOT NULL UNIQUE REFERENCES plm_rt_v2_callback(result_id),
 video_id TEXT NOT NULL CHECK(length(video_id)=11 AND video_id NOT GLOB '*[^A-Za-z0-9_-]*'),
 media_sha256 TEXT NOT NULL CHECK(length(media_sha256)=64 AND media_sha256 NOT GLOB '*[^0-9a-f]*'),
 privacy_status TEXT NOT NULL CHECK(privacy_status='private'),
 notify_subscribers INTEGER NOT NULL CHECK(notify_subscribers=0),
 upload_status TEXT NOT NULL CHECK(upload_status='processed'),
 saved_at INTEGER NOT NULL CHECK(typeof(saved_at)='integer' AND saved_at>0)
);
CREATE TRIGGER plm_ytq_v1_queue_insert BEFORE INSERT ON plm_ytq_v1_queue
WHEN NEW.state!='QUEUED' OR NEW.version!=1 OR (SELECT count(*) FROM plm_ytq_v1_queue)>=32
 OR NOT EXISTS(SELECT 1 FROM plm_rt_v2_job j JOIN plm_rt_v2_script s ON s.job_id=j.job_id
 JOIN plm_rt_v2_effect e ON e.job_id=j.job_id AND e.kind='GENERATION'
 WHERE j.job_id=NEW.job_id AND j.state='ACTIVE' AND j.account_id=NEW.account_id AND j.intent_id=NEW.intent_id
 AND j.owner=NEW.owner AND j.owner_epoch=NEW.owner_epoch AND j.fencing_token=NEW.fencing_token
 AND s.state='COMPLETED' AND s.script_sha256=NEW.script_sha256 AND e.state='CONFIRMED'
 AND NEW.created_at>=j.updated_at AND NEW.created_at>=s.updated_at)
BEGIN SELECT RAISE(ABORT,'ytq_checkpoint_or_capacity'); END;
CREATE TRIGGER plm_ytq_v1_queue_update BEFORE UPDATE ON plm_ytq_v1_queue
WHEN NEW.job_id IS NOT OLD.job_id OR NEW.account_id IS NOT OLD.account_id OR NEW.intent_id IS NOT OLD.intent_id
 OR NEW.script_sha256 IS NOT OLD.script_sha256 OR NEW.owner IS NOT OLD.owner
 OR NEW.owner_epoch!=OLD.owner_epoch OR NEW.fencing_token!=OLD.fencing_token
 OR NEW.not_before!=OLD.not_before OR NEW.created_at!=OLD.created_at OR NEW.updated_at<OLD.updated_at
 OR NEW.version!=OLD.version+1
 OR NOT EXISTS(SELECT 1 FROM plm_rt_v2_job j WHERE j.job_id=OLD.job_id AND j.owner=NEW.owner
 AND j.owner_epoch=NEW.owner_epoch AND j.fencing_token=NEW.fencing_token)
 OR NOT((OLD.state='QUEUED' AND NEW.state='CLAIMED' AND NEW.updated_at>=OLD.not_before
 AND EXISTS(SELECT 1 FROM plm_rt_v2_job j WHERE j.job_id=OLD.job_id AND j.state='ACTIVE')
 AND NOT EXISTS(SELECT 1 FROM plm_ytq_v1_queue q WHERE q.account_id=OLD.account_id AND q.state IN ('CLAIMED','DISPATCHED','UNKNOWN')))
 OR (OLD.state='CLAIMED' AND NEW.state='DISPATCHED' AND EXISTS(SELECT 1 FROM plm_ytq_v1_outbox o WHERE o.job_id=OLD.job_id AND o.state='RESERVED'))
 OR (OLD.state IN ('CLAIMED','DISPATCHED') AND NEW.state='UNKNOWN')
 OR (OLD.state='DISPATCHED' AND NEW.state='COMPLETE' AND EXISTS(SELECT 1 FROM plm_ytq_v1_result r WHERE r.job_id=OLD.job_id)))
BEGIN SELECT RAISE(ABORT,'ytq_transition_or_fence'); END;
CREATE TRIGGER plm_ytq_v1_outbox_insert BEFORE INSERT ON plm_ytq_v1_outbox
WHEN NEW.state!='RESERVED' OR NEW.send_attempts!=0
 OR NOT EXISTS(SELECT 1 FROM plm_ytq_v1_queue q JOIN plm_rt_v2_job j ON j.job_id=q.job_id
 WHERE q.job_id=NEW.job_id AND q.state='CLAIMED' AND j.state='ACTIVE' AND j.owner=q.owner
 AND j.owner_epoch=q.owner_epoch AND j.fencing_token=q.fencing_token)
BEGIN SELECT RAISE(ABORT,'ytq_unclaimed_outbox'); END;
CREATE TRIGGER plm_ytq_v1_outbox_update BEFORE UPDATE ON plm_ytq_v1_outbox
WHEN NEW.dispatch_id IS NOT OLD.dispatch_id OR NEW.job_id IS NOT OLD.job_id OR NEW.payload_sha256 IS NOT OLD.payload_sha256
 OR NOT((OLD.state='RESERVED' AND NEW.state='SENT' AND OLD.send_attempts=0 AND NEW.send_attempts=1
 AND EXISTS(SELECT 1 FROM plm_ytq_v1_queue q JOIN plm_rt_v2_job j ON j.job_id=q.job_id
 WHERE q.job_id=OLD.job_id AND q.state='DISPATCHED' AND j.state='ACTIVE'
 AND j.owner=q.owner AND j.owner_epoch=q.owner_epoch AND j.fencing_token=q.fencing_token))
 OR (OLD.state='SENT' AND NEW.state='UNKNOWN' AND NEW.send_attempts=1)
 OR (OLD.state='SENT' AND NEW.state='CONFIRMED' AND NEW.send_attempts=1
 AND EXISTS(SELECT 1 FROM plm_ytq_v1_result r WHERE r.job_id=OLD.job_id)))
BEGIN SELECT RAISE(ABORT,'ytq_resend_or_fence'); END;
CREATE TRIGGER plm_ytq_v1_result_insert BEFORE INSERT ON plm_ytq_v1_result
WHEN NOT EXISTS(SELECT 1 FROM plm_ytq_v1_queue q JOIN plm_rt_v2_job j ON j.job_id=q.job_id
 JOIN plm_rt_v2_callback c ON c.job_id=j.job_id JOIN plm_rt_v2_render r ON r.job_id=j.job_id
 JOIN plm_ytq_v1_outbox o ON o.job_id=q.job_id
 WHERE q.job_id=NEW.job_id AND q.state='DISPATCHED' AND o.state='SENT' AND o.send_attempts=1
 AND j.state='SUCCEEDED' AND j.result_id=NEW.result_id AND c.result_id=NEW.result_id
 AND c.account_id=q.account_id AND c.owner_epoch=q.owner_epoch AND c.fencing_token=q.fencing_token
 AND j.owner=q.owner AND j.owner_epoch=q.owner_epoch AND j.fencing_token=q.fencing_token
 AND r.quality_gate='PASS' AND r.artifact_sha256=NEW.media_sha256 AND r.script_sha256=q.script_sha256
 AND NEW.saved_at>=j.updated_at AND NEW.saved_at>=c.consumed_at AND NEW.saved_at>=q.updated_at)
BEGIN SELECT RAISE(ABORT,'ytq_unconfirmed_result'); END;
CREATE TRIGGER plm_ytq_v1_result_apply AFTER INSERT ON plm_ytq_v1_result
BEGIN
 UPDATE plm_ytq_v1_outbox SET state='CONFIRMED' WHERE job_id=NEW.job_id AND state='SENT';
 SELECT CASE WHEN changes()!=1 THEN RAISE(ABORT,'ytq_outbox_atomicity') END;
 UPDATE plm_ytq_v1_queue SET state='COMPLETE',version=version+1,updated_at=NEW.saved_at WHERE job_id=NEW.job_id AND state='DISPATCHED';
 SELECT CASE WHEN changes()!=1 THEN RAISE(ABORT,'ytq_result_atomicity') END;
END;
CREATE TRIGGER plm_ytq_v1_result_update BEFORE UPDATE ON plm_ytq_v1_result
BEGIN SELECT RAISE(ABORT,'ytq_result_immutable'); END;
CREATE TRIGGER plm_ytq_v1_queue_delete BEFORE DELETE ON plm_ytq_v1_queue
BEGIN SELECT RAISE(ABORT,'ytq_consumed'); END;
CREATE TRIGGER plm_ytq_v1_outbox_delete BEFORE DELETE ON plm_ytq_v1_outbox
BEGIN SELECT RAISE(ABORT,'ytq_consumed'); END;
CREATE TRIGGER plm_ytq_v1_result_delete BEFORE DELETE ON plm_ytq_v1_result
BEGIN SELECT RAISE(ABORT,'ytq_consumed'); END;
