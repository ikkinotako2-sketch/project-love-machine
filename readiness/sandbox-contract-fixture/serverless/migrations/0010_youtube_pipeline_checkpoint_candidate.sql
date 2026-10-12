-- Independent OFFLINE candidate; neither 0008 nor 0009 is changed.
CREATE TABLE plm_ytp_v1_binding (
 job_id TEXT PRIMARY KEY REFERENCES plm_ytq_v1_queue(job_id),
 dispatch_id TEXT NOT NULL UNIQUE REFERENCES plm_ytq_v1_outbox(dispatch_id),
 pipeline_run_id TEXT NOT NULL UNIQUE CHECK(pipeline_run_id NOT GLOB '*[^0-9]*' AND length(pipeline_run_id) BETWEEN 1 AND 20),
 render_run_id TEXT NOT NULL CHECK(render_run_id=pipeline_run_id),
 run_attempt INTEGER NOT NULL CHECK(run_attempt=1),
 workflow_sha256 TEXT NOT NULL CHECK(length(workflow_sha256)=64 AND workflow_sha256 NOT GLOB '*[^0-9a-f]*'),
 dispatch_payload_sha256 TEXT NOT NULL CHECK(length(dispatch_payload_sha256)=64 AND dispatch_payload_sha256 NOT GLOB '*[^0-9a-f]*'),
 bind_payload_sha256 TEXT NOT NULL CHECK(length(bind_payload_sha256)=64 AND bind_payload_sha256 NOT GLOB '*[^0-9a-f]*'),
 bound_at INTEGER NOT NULL CHECK(bound_at>0)
);
CREATE TRIGGER plm_ytp_v1_binding_insert BEFORE INSERT ON plm_ytp_v1_binding
WHEN NOT EXISTS(SELECT 1 FROM plm_ytq_v1_queue q JOIN plm_ytq_v1_outbox o ON o.job_id=q.job_id JOIN plm_rt_v2_job j ON j.job_id=q.job_id WHERE q.job_id=NEW.job_id AND q.state='DISPATCHED' AND o.state='SENT' AND o.send_attempts=1 AND o.dispatch_id=NEW.dispatch_id AND o.payload_sha256=NEW.dispatch_payload_sha256 AND j.state='ACTIVE' AND j.owner=q.owner AND j.owner_epoch=q.owner_epoch AND j.fencing_token=q.fencing_token AND NEW.bound_at>=q.updated_at)
BEGIN SELECT RAISE(ABORT,'pipeline_unbound_dispatch'); END;
CREATE TRIGGER plm_ytp_v1_binding_update BEFORE UPDATE ON plm_ytp_v1_binding
BEGIN SELECT RAISE(ABORT,'pipeline_binding_immutable'); END;
CREATE TRIGGER plm_ytp_v1_binding_delete BEFORE DELETE ON plm_ytp_v1_binding
BEGIN SELECT RAISE(ABORT,'pipeline_binding_consumed'); END;
