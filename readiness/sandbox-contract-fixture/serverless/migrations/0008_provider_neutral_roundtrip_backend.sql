-- Candidate only: new plm_rt_v2 namespace. No existing object is modified.
CREATE TABLE plm_rt_v2_job (
 job_id TEXT PRIMARY KEY CHECK(length(job_id) BETWEEN 1 AND 64),
 platform TEXT NOT NULL CHECK(platform='youtube'),
 account_id TEXT NOT NULL CHECK(length(account_id) BETWEEN 1 AND 64),
 intent_id TEXT NOT NULL CHECK(length(intent_id) BETWEEN 1 AND 96),
 owner TEXT NOT NULL CHECK(length(owner) BETWEEN 1 AND 64),
 owner_epoch INTEGER NOT NULL CHECK(typeof(owner_epoch)='integer' AND owner_epoch>0),
 fencing_token INTEGER NOT NULL CHECK(typeof(fencing_token)='integer' AND fencing_token>0),
 version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version>0),
 state TEXT NOT NULL CHECK(state IN ('ACTIVE','UNKNOWN','SUCCEEDED')),
 old_owner_stop_proof TEXT CHECK(old_owner_stop_proof IS NULL OR (length(old_owner_stop_proof)=64 AND old_owner_stop_proof NOT GLOB '*[^0-9a-f]*')),
 result_id TEXT UNIQUE CHECK(result_id IS NULL OR length(result_id) BETWEEN 1 AND 128),
 created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>0),
 updated_at INTEGER NOT NULL CHECK(typeof(updated_at)='integer' AND updated_at>=created_at),
 UNIQUE(platform,account_id,intent_id),
 CHECK((state IN ('ACTIVE','UNKNOWN') AND result_id IS NULL) OR (state='SUCCEEDED' AND result_id IS NOT NULL))
);
CREATE TABLE plm_rt_v2_script (
 checkpoint_id TEXT PRIMARY KEY CHECK(length(checkpoint_id) BETWEEN 1 AND 96),
 job_id TEXT NOT NULL UNIQUE REFERENCES plm_rt_v2_job(job_id),
 owner TEXT NOT NULL,
 owner_epoch INTEGER NOT NULL,
 fencing_token INTEGER NOT NULL,
 version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version IN (1,2)),
 state TEXT NOT NULL CHECK(state IN ('STARTED','UNKNOWN','COMPLETED')),
 provider TEXT NOT NULL CHECK(typeof(provider)='text' AND length(provider) BETWEEN 2 AND 32 AND provider NOT GLOB '*[^a-z0-9_-]*' AND substr(provider,1,1) GLOB '[a-z]'),
 model TEXT NOT NULL CHECK(length(model) BETWEEN 1 AND 96),
 request_sha256 TEXT NOT NULL CHECK(length(request_sha256)=64 AND request_sha256 NOT GLOB '*[^0-9a-f]*'),
 script_json TEXT CHECK(script_json IS NULL OR (json_valid(script_json) AND json_type(script_json)='object' AND length(CAST(script_json AS BLOB))<=65536)),
 script_sha256 TEXT CHECK(script_sha256 IS NULL OR (length(script_sha256)=64 AND script_sha256 NOT GLOB '*[^0-9a-f]*')),
 created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>0),
 updated_at INTEGER NOT NULL CHECK(typeof(updated_at)='integer' AND updated_at>=created_at),
 CHECK((state='STARTED' AND version=1 AND script_json IS NULL AND script_sha256 IS NULL) OR
 (state='UNKNOWN' AND version=2 AND script_json IS NULL AND script_sha256 IS NULL) OR
 (state='COMPLETED' AND version=2 AND script_json IS NOT NULL AND script_sha256 IS NOT NULL))
);
CREATE TABLE plm_rt_v2_render (
 artifact_id TEXT PRIMARY KEY CHECK(length(artifact_id) BETWEEN 1 AND 96),
 job_id TEXT NOT NULL UNIQUE REFERENCES plm_rt_v2_job(job_id),
 owner TEXT NOT NULL,
 owner_epoch INTEGER NOT NULL,
 fencing_token INTEGER NOT NULL,
 script_sha256 TEXT NOT NULL CHECK(length(script_sha256)=64 AND script_sha256 NOT GLOB '*[^0-9a-f]*'),
 artifact_sha256 TEXT NOT NULL CHECK(length(artifact_sha256)=64 AND artifact_sha256 NOT GLOB '*[^0-9a-f]*'),
 artifact_ref TEXT NOT NULL CHECK(length(artifact_ref) BETWEEN 12 AND 256 AND artifact_ref GLOB 'artifact://*' AND artifact_ref NOT GLOB '*[?&#]*'),
 render_run_id TEXT NOT NULL CHECK(length(render_run_id) BETWEEN 1 AND 32 AND render_run_id NOT GLOB '*[^0-9]*'),
 quality_gate TEXT NOT NULL CHECK(quality_gate='PASS'),
 created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>0)
);
CREATE TABLE plm_rt_v2_effect (
 effect_id TEXT PRIMARY KEY CHECK(length(effect_id) BETWEEN 1 AND 96),
 job_id TEXT NOT NULL REFERENCES plm_rt_v2_job(job_id),
 kind TEXT NOT NULL CHECK(kind IN ('GENERATION','RENDER','UPLOAD')),
 owner TEXT NOT NULL,
 owner_epoch INTEGER NOT NULL,
 fencing_token INTEGER NOT NULL,
 request_sha256 TEXT NOT NULL CHECK(length(request_sha256)=64 AND request_sha256 NOT GLOB '*[^0-9a-f]*'),
 delivery_id TEXT NOT NULL UNIQUE CHECK(length(delivery_id) BETWEEN 1 AND 96),
 result_id TEXT UNIQUE CHECK(result_id IS NULL OR length(result_id) BETWEEN 1 AND 128),
 version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version>0),
 state TEXT NOT NULL CHECK(state IN ('RESERVED','SENT','UNKNOWN','CONFIRMED')),
 created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>0),
 updated_at INTEGER NOT NULL CHECK(typeof(updated_at)='integer' AND updated_at>=created_at),
 UNIQUE(job_id,kind),
 CHECK((state IN ('RESERVED','SENT','UNKNOWN') AND result_id IS NULL) OR (state='CONFIRMED' AND result_id IS NOT NULL))
);
CREATE TABLE plm_rt_v2_callback (
 delivery_id TEXT PRIMARY KEY REFERENCES plm_rt_v2_effect(delivery_id),
 callback_id TEXT NOT NULL UNIQUE CHECK(length(callback_id) BETWEEN 1 AND 96),
 job_id TEXT NOT NULL REFERENCES plm_rt_v2_job(job_id),
 account_id TEXT NOT NULL,
 owner_epoch INTEGER NOT NULL,
 fencing_token INTEGER NOT NULL,
 payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256)=64 AND payload_sha256 NOT GLOB '*[^0-9a-f]*'),
 result_id TEXT NOT NULL UNIQUE CHECK(length(result_id) BETWEEN 1 AND 128),
 state TEXT NOT NULL CHECK(state='CONFIRMED'),
 consumed_at INTEGER NOT NULL CHECK(typeof(consumed_at)='integer' AND consumed_at>0)
);
CREATE TRIGGER plm_rt_v2_job_insert BEFORE INSERT ON plm_rt_v2_job
WHEN NEW.state!='ACTIVE' OR NEW.version!=1 OR NEW.owner_epoch!=1 OR NEW.fencing_token!=1 OR NEW.old_owner_stop_proof IS NOT NULL
BEGIN SELECT RAISE(ABORT,'rt_job_initial_state'); END;
CREATE TRIGGER plm_rt_v2_job_guard BEFORE UPDATE ON plm_rt_v2_job
WHEN NEW.job_id IS NOT OLD.job_id OR NEW.platform IS NOT OLD.platform OR NEW.account_id IS NOT OLD.account_id
 OR NEW.intent_id IS NOT OLD.intent_id OR NEW.created_at IS NOT OLD.created_at OR NEW.updated_at<OLD.updated_at OR NEW.version!=OLD.version+1
 OR NOT((OLD.state='ACTIVE' AND NEW.state='ACTIVE' AND NEW.owner IS NOT OLD.owner
 AND NEW.owner_epoch=OLD.owner_epoch+1 AND NEW.fencing_token=OLD.fencing_token+1 AND NEW.old_owner_stop_proof IS NOT NULL
 AND NOT EXISTS(SELECT 1 FROM plm_rt_v2_script WHERE job_id=OLD.job_id)
 AND NOT EXISTS(SELECT 1 FROM plm_rt_v2_effect WHERE job_id=OLD.job_id))
 OR (NEW.owner IS OLD.owner AND NEW.owner_epoch=OLD.owner_epoch AND NEW.fencing_token=OLD.fencing_token
 AND NEW.old_owner_stop_proof IS OLD.old_owner_stop_proof
 AND ((OLD.state='ACTIVE' AND NEW.state='UNKNOWN' AND EXISTS(SELECT 1 FROM plm_rt_v2_effect WHERE job_id=OLD.job_id AND state='UNKNOWN'))
 OR (OLD.state IN ('ACTIVE','UNKNOWN') AND NEW.state='SUCCEEDED' AND EXISTS(SELECT 1 FROM plm_rt_v2_callback c WHERE c.job_id=OLD.job_id AND c.result_id=NEW.result_id)))))
BEGIN SELECT RAISE(ABORT,'rt_job_fence_or_transition'); END;
CREATE TRIGGER plm_rt_v2_script_insert BEFORE INSERT ON plm_rt_v2_script
WHEN NEW.state!='STARTED' OR NEW.version!=1 OR NOT EXISTS(SELECT 1 FROM plm_rt_v2_job j WHERE j.job_id=NEW.job_id AND j.state='ACTIVE' AND j.owner=NEW.owner AND j.owner_epoch=NEW.owner_epoch AND j.fencing_token=NEW.fencing_token AND NEW.created_at>=j.updated_at)
BEGIN SELECT RAISE(ABORT,'rt_script_identity'); END;
CREATE TRIGGER plm_rt_v2_script_guard BEFORE UPDATE ON plm_rt_v2_script
WHEN NEW.checkpoint_id IS NOT OLD.checkpoint_id OR NEW.job_id IS NOT OLD.job_id OR NEW.owner IS NOT OLD.owner
 OR NEW.owner_epoch!=OLD.owner_epoch OR NEW.fencing_token!=OLD.fencing_token OR NEW.provider IS NOT OLD.provider OR NEW.model IS NOT OLD.model
 OR NEW.request_sha256 IS NOT OLD.request_sha256 OR NEW.created_at IS NOT OLD.created_at OR NEW.updated_at<OLD.updated_at
 OR OLD.state!='STARTED' OR NEW.state NOT IN ('COMPLETED','UNKNOWN') OR NEW.version!=OLD.version+1
 OR NOT EXISTS(SELECT 1 FROM plm_rt_v2_job j WHERE j.job_id=OLD.job_id AND j.state IN ('ACTIVE','UNKNOWN') AND j.owner=NEW.owner AND j.owner_epoch=NEW.owner_epoch AND j.fencing_token=NEW.fencing_token)
 OR NOT EXISTS(SELECT 1 FROM plm_rt_v2_effect e WHERE e.job_id=OLD.job_id AND e.kind='GENERATION' AND e.state IN ('SENT','UNKNOWN') AND e.request_sha256=OLD.request_sha256 AND e.owner=NEW.owner AND e.owner_epoch=NEW.owner_epoch AND e.fencing_token=NEW.fencing_token)
BEGIN SELECT RAISE(ABORT,'rt_script_immutable_or_unsent'); END;
CREATE TRIGGER plm_rt_v2_render_insert BEFORE INSERT ON plm_rt_v2_render
WHEN NOT EXISTS(SELECT 1 FROM plm_rt_v2_job j JOIN plm_rt_v2_script s ON s.job_id=j.job_id JOIN plm_rt_v2_effect e ON e.job_id=j.job_id AND e.kind='RENDER'
 WHERE j.job_id=NEW.job_id AND j.state IN ('ACTIVE','UNKNOWN') AND j.owner=NEW.owner AND j.owner_epoch=NEW.owner_epoch AND j.fencing_token=NEW.fencing_token
 AND s.state='COMPLETED' AND s.script_sha256=NEW.script_sha256 AND e.state IN ('SENT','UNKNOWN') AND e.owner=NEW.owner AND e.owner_epoch=NEW.owner_epoch AND e.fencing_token=NEW.fencing_token AND NEW.created_at>=e.updated_at)
BEGIN SELECT RAISE(ABORT,'rt_render_checkpoint_or_fence'); END;
CREATE TRIGGER plm_rt_v2_render_immutable BEFORE UPDATE ON plm_rt_v2_render
BEGIN SELECT RAISE(ABORT,'rt_render_immutable'); END;
CREATE TRIGGER plm_rt_v2_effect_insert BEFORE INSERT ON plm_rt_v2_effect
WHEN NEW.state!='RESERVED' OR NEW.version!=1 OR NOT EXISTS(SELECT 1 FROM plm_rt_v2_job j WHERE j.job_id=NEW.job_id AND j.state='ACTIVE' AND j.owner=NEW.owner AND j.owner_epoch=NEW.owner_epoch AND j.fencing_token=NEW.fencing_token AND NEW.created_at>=j.updated_at)
 OR (NEW.kind='GENERATION' AND NOT EXISTS(SELECT 1 FROM plm_rt_v2_script s WHERE s.job_id=NEW.job_id AND s.state='STARTED' AND s.request_sha256=NEW.request_sha256))
 OR (NEW.kind='RENDER' AND NOT EXISTS(SELECT 1 FROM plm_rt_v2_script s JOIN plm_rt_v2_effect e ON e.job_id=s.job_id AND e.kind='GENERATION' WHERE s.job_id=NEW.job_id AND s.state='COMPLETED' AND e.state='CONFIRMED'))
 OR (NEW.kind='UPLOAD' AND NOT EXISTS(SELECT 1 FROM plm_rt_v2_render r JOIN plm_rt_v2_effect e ON e.job_id=r.job_id AND e.kind='RENDER' WHERE r.job_id=NEW.job_id AND e.state='CONFIRMED'))
BEGIN SELECT RAISE(ABORT,'rt_effect_precondition'); END;
CREATE TRIGGER plm_rt_v2_effect_guard BEFORE UPDATE ON plm_rt_v2_effect
WHEN NEW.effect_id IS NOT OLD.effect_id OR NEW.job_id IS NOT OLD.job_id OR NEW.kind IS NOT OLD.kind OR NEW.owner IS NOT OLD.owner
 OR NEW.owner_epoch!=OLD.owner_epoch OR NEW.fencing_token!=OLD.fencing_token OR NEW.request_sha256 IS NOT OLD.request_sha256
 OR NEW.delivery_id IS NOT OLD.delivery_id OR NEW.created_at IS NOT OLD.created_at OR NEW.updated_at<OLD.updated_at OR NEW.version!=OLD.version+1
 OR NOT EXISTS(SELECT 1 FROM plm_rt_v2_job j WHERE j.job_id=OLD.job_id AND j.state IN ('ACTIVE','UNKNOWN') AND j.owner=NEW.owner AND j.owner_epoch=NEW.owner_epoch AND j.fencing_token=NEW.fencing_token)
 OR NOT((OLD.state='RESERVED' AND NEW.state='SENT') OR (OLD.state='SENT' AND NEW.state='UNKNOWN')
 OR (OLD.state IN ('SENT','UNKNOWN') AND NEW.state='CONFIRMED'
 AND ((OLD.kind='GENERATION' AND EXISTS(SELECT 1 FROM plm_rt_v2_script s WHERE s.job_id=OLD.job_id AND s.state='COMPLETED' AND s.request_sha256=OLD.request_sha256))
 OR (OLD.kind='RENDER' AND EXISTS(SELECT 1 FROM plm_rt_v2_render r WHERE r.job_id=OLD.job_id AND r.quality_gate='PASS'))
 OR (OLD.kind='UPLOAD' AND EXISTS(SELECT 1 FROM plm_rt_v2_callback c WHERE c.delivery_id=OLD.delivery_id AND c.job_id=OLD.job_id AND c.result_id=NEW.result_id)))))
BEGIN SELECT RAISE(ABORT,'rt_effect_no_resend_or_fence'); END;
CREATE TRIGGER plm_rt_v2_callback_insert BEFORE INSERT ON plm_rt_v2_callback
WHEN EXISTS(SELECT 1 FROM plm_rt_v2_callback c WHERE (c.delivery_id=NEW.delivery_id OR c.callback_id=NEW.callback_id OR c.result_id=NEW.result_id)
 AND (c.delivery_id IS NOT NEW.delivery_id OR c.callback_id IS NOT NEW.callback_id OR c.job_id IS NOT NEW.job_id OR c.account_id IS NOT NEW.account_id OR c.owner_epoch!=NEW.owner_epoch OR c.fencing_token!=NEW.fencing_token OR c.payload_sha256 IS NOT NEW.payload_sha256 OR c.result_id IS NOT NEW.result_id OR c.consumed_at!=NEW.consumed_at))
 OR (NOT EXISTS(SELECT 1 FROM plm_rt_v2_callback WHERE delivery_id=NEW.delivery_id)
 AND NOT EXISTS(SELECT 1 FROM plm_rt_v2_effect e JOIN plm_rt_v2_job j ON j.job_id=e.job_id JOIN plm_rt_v2_render r ON r.job_id=j.job_id
 WHERE e.delivery_id=NEW.delivery_id AND e.kind='UPLOAD' AND e.state IN ('SENT','UNKNOWN') AND e.job_id=NEW.job_id
 AND j.account_id=NEW.account_id AND j.state IN ('ACTIVE','UNKNOWN') AND j.owner=e.owner AND j.owner_epoch=NEW.owner_epoch AND e.owner_epoch=NEW.owner_epoch
 AND j.fencing_token=NEW.fencing_token AND e.fencing_token=NEW.fencing_token AND NEW.consumed_at>=e.updated_at AND NEW.consumed_at>=j.updated_at))
BEGIN SELECT RAISE(ABORT,'rt_callback_identity_or_fence'); END;
CREATE TRIGGER plm_rt_v2_callback_apply AFTER INSERT ON plm_rt_v2_callback
BEGIN
 UPDATE plm_rt_v2_effect SET state='CONFIRMED',result_id=NEW.result_id,version=version+1,updated_at=NEW.consumed_at WHERE delivery_id=NEW.delivery_id AND kind='UPLOAD' AND state IN ('SENT','UNKNOWN');
 SELECT CASE WHEN changes()!=1 THEN RAISE(ABORT,'rt_callback_effect_atomicity') END;
 UPDATE plm_rt_v2_job SET state='SUCCEEDED',result_id=NEW.result_id,version=version+1,updated_at=NEW.consumed_at WHERE job_id=NEW.job_id AND state IN ('ACTIVE','UNKNOWN') AND owner_epoch=NEW.owner_epoch AND fencing_token=NEW.fencing_token;
 SELECT CASE WHEN changes()!=1 THEN RAISE(ABORT,'rt_callback_job_atomicity') END;
END;
CREATE TRIGGER plm_rt_v2_callback_immutable BEFORE UPDATE ON plm_rt_v2_callback
BEGIN SELECT RAISE(ABORT,'rt_callback_immutable'); END;
