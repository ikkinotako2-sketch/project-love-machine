"""Integrated OFFLINE successor. There is deliberately no live factory.

Existing renderer evidence, StrictUploader, Ledger and content adapters are reused.
Fixtures assert ownership/provenance only in the simulation, never for production.
"""
import hashlib
import html
import json
import re
from pathlib import Path
from .ledger import Ledger, Stop, require
from .loop import FLAGS
from .production_bridge import MEDIA, CHANNEL, media_gate, scope_gate, READ, UPLOAD, digest
from .strict_upload import ChannelSession, StrictUploader
from .content_adapters import ThemeAdapter, ScriptAdapter, MetricsAdapter, next_job

REPO = 'ikkinotako2-sketch/project-love-machine'
BRANCH = 'plm-youtube-final-candidate-20261012-r1'
REASONS = frozenset('API_STOP RENDER_STOP ACTIONS_STOP WORKER_PARKED CLAIM_CONFLICT_STOP D1_UNKNOWN STATE_WRITE_UNKNOWN UPLOAD_UNKNOWN AUTH_EXPIRED_STOP QUOTA_STOP FREE_BUDGET_STOP CALLBACK_UNKNOWN SIGNATURE_STOP SHA_STOP ARTIFACT_EXPIRED SECRET_MISSING EMERGENCY_STOP CONFIG_STOP RIGHTS_STOP'.split())

def reject_live(*args, **kwargs):
    raise Stop('LIVE_EXECUTION_UNIMPLEMENTED_PARKED')

def publication_gate(facts, now):
    """Pure future gate, never sufficient to enable the current entrypoint."""
    require(facts.get('flags') == FLAGS, 'FLAGS_STOP')
    require(facts.get('execution_approved') is True, 'APPROVAL_REQUIRED')
    require(facts.get('repository') == REPO and facts.get('attempt') == 1 and type(facts.get('attempt')) is int, 'PROVENANCE_STOP')
    require(re.fullmatch(r'[1-9][0-9]{0,19}', str(facts.get('run_id',''))) is not None, 'PROVENANCE_STOP')
    require(re.fullmatch(r'[a-f0-9]{40}', str(facts.get('commit',''))) is not None and facts.get('commit') == facts.get('approved_commit'), 'SHA_STOP')
    for field in ('source_hashes_exact','workflow_hash_exact','artifact_origin_exact','marker_only_history_exact','marker_consumed','durable_state_ready','shared_uncertainty_guard_ready','budget_observation_fresh','callback_provenance_ready'):
        require(facts.get(field) is True, 'UNVERIFIED_'+field.upper())
    require(type(facts.get('artifact_expires_at')) is int and facts['artifact_expires_at'] > now, 'ARTIFACT_EXPIRED')
    require(type(facts.get('credential_expires_at')) is int and facts['credential_expires_at'] > now+180, 'AUTH_EXPIRED_STOP')
    require(facts.get('channel_verified') is True and facts.get('channel_id') == CHANNEL, 'CHANNEL_UNVERIFIED_STOP')
    scope_gate(facts.get('scopes'), facts.get('scope_proven'))
    require(facts.get('privacy') == 'private' and facts.get('notify_subscribers') is False, 'PRIVATE_POLICY_STOP')
    remaining=facts.get('remaining_budget')
    require(isinstance(remaining,dict) and set(remaining)=={'jobs','minutes','units','bytes'} and all(type(v) is int and v>0 for v in remaining.values()), 'BUDGET_UNKNOWN_STOP')
    return True

class Journal:
    """Local durable reference, same SQLite DB/transaction domain as Ledger.

    An unfinished SENT after restart is UNKNOWN. This is not proof that a
    runner-local database is durable across GitHub-hosted runner destruction.
    A shared, reviewed production uncertainty guard is a remaining live gate.
    """
    def __init__(self, ledger):
        self.l=ledger
        self.l.db.executescript('''
CREATE TABLE IF NOT EXISTS candidate_control(id INTEGER PRIMARY KEY CHECK(id=1), stopped INTEGER NOT NULL CHECK(stopped IN(0,1)), reason TEXT);
INSERT OR IGNORE INTO candidate_control VALUES(1,0,NULL);
CREATE TABLE IF NOT EXISTS candidate_events(job_id TEXT PRIMARY KEY REFERENCES jobs(job_id), started INTEGER NOT NULL, ended INTEGER, callback TEXT NOT NULL DEFAULT 'NOT_SENT', render_ok INTEGER NOT NULL DEFAULT 0, next_job TEXT);
CREATE TABLE IF NOT EXISTS candidate_outbox(key TEXT PRIMARY KEY, reason TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0 CHECK(delivered IN(0,1)));
CREATE TRIGGER IF NOT EXISTS candidate_outbox_no_delete BEFORE DELETE ON candidate_outbox BEGIN SELECT RAISE(ABORT,'tombstone'); END;
''')
        unfinished=self.l.db.execute("SELECT job_id FROM jobs WHERE state='Processing' AND sent=1").fetchall()
        for row in unfinished:
            self.l.db.execute("UPDATE jobs SET state='UNKNOWN',result=json_object('job_id',job_id,'state','UNKNOWN','reason_code','UPLOAD_UNKNOWN') WHERE job_id=?",(row['job_id'],))
        if unfinished:self.halt('UPLOAD_UNKNOWN')
        elif self.l.progress()['stopped']:self.halt('CONFIG_STOP')
        elif self.l.db.execute("SELECT 1 FROM candidate_events e JOIN jobs j ON j.job_id=e.job_id WHERE j.state='Done' AND (e.callback!='ACK' OR e.next_job IS NULL) LIMIT 1").fetchone():self.halt('CALLBACK_UNKNOWN')
        elif self.l.db.execute("SELECT 1 FROM jobs WHERE state IN('Pending','Processing') LIMIT 1").fetchone():self.halt('CONFIG_STOP')
    def halt(self,reason):
        require(reason in REASONS,'REASON_STOP')
        self.l.db.execute('BEGIN IMMEDIATE')
        try:
            self.l.db.execute('UPDATE candidate_control SET stopped=1,reason=COALESCE(reason,?) WHERE id=1',(reason,))
            self.l.db.execute('INSERT OR IGNORE INTO candidate_outbox(key,reason) VALUES(?,?)',('halt-'+reason,reason))
            self.l.db.execute('COMMIT')
        except Exception:self.l.db.execute('ROLLBACK');raise
    def stopped(self):return bool(self.l.db.execute('SELECT stopped FROM candidate_control').fetchone()[0])
    def start(self,job,now):self.l.db.execute('INSERT INTO candidate_events(job_id,started) VALUES(?,?)',(job,now))
    def rendered(self,job):self.l.db.execute('UPDATE candidate_events SET render_ok=1 WHERE job_id=?',(job,))
    def callback(self,job,status,now):
        require(status in ('ACK','UNKNOWN'),'CALLBACK_STATE_STOP')
        self.l.db.execute('UPDATE candidate_events SET callback=?,ended=? WHERE job_id=?',(status,now,job))
    def next(self,job,identifier):
        row=self.l.db.execute('SELECT callback FROM candidate_events WHERE job_id=?',(job,)).fetchone()
        require(row and row['callback']=='ACK' and self.l.get(job)['state']=='Done','NO_NEXT_WITHOUT_CONFIRMED_CALLBACK')
        self.l.db.execute('UPDATE candidate_events SET next_job=? WHERE job_id=? AND next_job IS NULL',(identifier,job))

class FixtureUpload:
    offline_mock=True
    def __init__(self,ledger,fault=None):self.l=ledger;self.fault=fault;self.calls=[];self.job=None
    def init(self,token,metadata,size):
        require(self.l.get(self.job)['sent']==1,'SENT_BEFORE_SEND_REQUIRED')
        require(metadata['status']['privacyStatus']=='private','PRIVATE_POLICY_STOP')
        self.calls.append('MOCK_INIT')
        if self.fault=='UPLOAD_UNKNOWN':raise TimeoutError()
        return 'fixture-session'
    def media(self,token,path,media):
        require(self.calls[-1]=='MOCK_INIT' and path=='fixture-session','NO_RESUME')
        require(hashlib.sha256(media.read()).hexdigest()==MEDIA,'MEDIA_HASH_STOP')
        self.calls.append('MOCK_MEDIA')
        return 200,json.dumps({'id':'offline0001','snippet':{'channelId':CHANNEL},'status':{'privacyStatus':'private'}}).encode()

class IntegratedCandidate:
    def __init__(self,db_path,media,*,clock,artifact_expires_at,offline_only=True,flags=None):
        require(offline_only is True and (FLAGS if flags is None else flags)==FLAGS,'PARKED_CONFIG_STOP')
        self.l=Ledger(db_path);self.j=Journal(self.l);self.media=Path(media);self.clock=clock;self.artifact_expiry=artifact_expires_at
        root=Path(__file__).resolve().parents[2]
        self.job=json.loads((root/'readiness/youtube-private-job.json').read_text())
        self.evidence=json.loads((root/'readiness/reused-render-evidence.json').read_text())
        self.upload=FixtureUpload(self.l);self.results=[];self.seen=set();self.next_id=None;self.pending_result=None
        self.theme=ThemeAdapter(lambda:{'topic':'非公開の映像・音声確認','source_id':'original-fixture','license':'original','verified':True},rights_policy=['original'])
        self.script=ScriptAdapter(lambda t:{'narration':' '.join(self.job['sentences']),'rights_verified':True},capability_verified=True)
        self.metrics=MetricsAdapter(lambda vid:{'views':0,'likes':0,'comments':0},capability_verified=True)
    def close(self):self.l.close()
    def tick(self,job_id, fault=None):
        require(fault is None or fault in REASONS,'FAULT_SHAPE_STOP')
        if self.j.stopped():return {'state':'STOP','reason_code':'EMERGENCY_STOP'}
        now=self.clock();claim=None
        try:
            if fault in {'API_STOP','ACTIONS_STOP','WORKER_PARKED','AUTH_EXPIRED_STOP','QUOTA_STOP','FREE_BUDGET_STOP','SIGNATURE_STOP','SHA_STOP','SECRET_MISSING','EMERGENCY_STOP','D1_UNKNOWN','STATE_WRITE_UNKNOWN','RIGHTS_STOP'}:raise Stop(fault)
            require(type(self.artifact_expiry) is int and self.artifact_expiry>now and fault!='ARTIFACT_EXPIRED','ARTIFACT_EXPIRED')
            idea=self.theme.next();script=self.script.generate(idea)
            require(self.l.add(job_id,digest(script),now),'CLAIM_CONFLICT_STOP')
            self.j.start(job_id,now)
            from datetime import datetime,timezone
            day=datetime.fromtimestamp(now,timezone.utc).strftime('%Y-%m-%d')
            self.l.reserve_budget(day,{'jobs':1,'minutes':10,'units':200,'bytes':self.evidence['quality']['bytes']},{'jobs':2,'minutes':30,'units':1000,'bytes':1000000})
            claim=self.l.claim(job_id,'offline-integration',now)
            require(fault!='RENDER_STOP','RENDER_STOP')
            # Reuse generated video: no second VOICEVOX/FFmpeg generation.
            media_gate(self.media,self.evidence,self.job);self.j.rendered(job_id)
            scope_gate([READ,UPLOAD],True) # explicitly synthetic proof, never live evidence
            session=ChannelSession.from_mine_response('OFFLINE_FIXTURE',200,json.dumps({'kind':'youtube#channelListResponse','items':[{'id':CHANNEL}]}).encode(),now+3600,self.clock)
            self.upload.job=job_id;self.upload.fault=fault
            proof={**self.job,'job_id':job_id,'media_sha256':MEDIA,'source_pins_exact':True,'rights_verified':True,'quality_pass':True,'upload_approved':True,'marker_consumed_before_remote':True,'marker_identity':'fixture-'+job_id,'run_attempt':1}
            result=StrictUploader(self.l,self.upload,self.clock).upload(claim,'fixture-'+job_id,session,self.media,proof)
            if result['state']!='Done':self.j.halt('UPLOAD_UNKNOWN');return result
            self.pending_result={**result,'media_sha256':MEDIA,'channel_id':CHANNEL,'proof_basis':'OFFLINE_FIXTURE','processed_readback':'MOCK_ONLY'}
            require(fault!='CALLBACK_UNKNOWN','CALLBACK_UNKNOWN')
            self.j.callback(job_id,'ACK',now+1)
            observations=self.metrics.collect(result);improvement=self.metrics.improve(observations)
            identifier=next_job(result,script,self.seen);self.j.next(job_id,identifier);self.next_id=identifier
            out={**result,'callback':'ACK','next_job':identifier,'improvement_method':improvement['method'],'proof_basis':'OFFLINE_FIXTURE'}
            self.results.append(out);return out
        except Exception as exc:
            reason=str(exc) if isinstance(exc,Stop) and str(exc) in REASONS else 'CONFIG_STOP'
            if claim and self.l.get(job_id)['state']=='Processing':
                row=self.l.get(job_id)
                self.l.finish(claim,'UNKNOWN' if row['sent'] else 'Failed',reason='UPLOAD_UNKNOWN' if row['sent'] else 'RENDER_FAILED')
            if claim and reason=='CALLBACK_UNKNOWN':self.j.callback(job_id,'UNKNOWN',now+1)
            self.j.halt(reason)
            return {'state':'STOP','reason_code':reason}
    def report(self):
        progress=self.l.progress();events=[dict(r) for r in self.l.db.execute('SELECT * FROM candidate_events ORDER BY started')]
        rows=[dict(r) for r in self.l.db.execute('SELECT job_id,state,result FROM jobs ORDER BY created_at')]
        completed=[r for r in rows if r['state']=='Done'];failed=[r for r in rows if r['state'] in ('Failed','UNKNOWN')]
        return {'mode':'OFFLINE_SIMULATION','flags':FLAGS,'counts':progress['counts'],'last_success':completed[-1]['job_id'] if completed else None,'last_failure':failed[-1]['job_id'] if failed else None,'error_reason':self.l.db.execute('SELECT reason FROM candidate_control').fetchone()[0],'updated_at':self.clock(),'real_uploads':0,'mock_uploads':self.upload.calls.count('MOCK_MEDIA'),'stopped':self.j.stopped(),'render_success_rate':sum(e['render_ok'] for e in events)/len(events) if events else None,'durations_seconds':[e['ended']-e['started'] for e in events if e['ended'] is not None],'budgets':[dict(r) for r in self.l.db.execute('SELECT * FROM budgets')],'undelivered_notifications':self.l.db.execute('SELECT count(*) FROM candidate_outbox WHERE delivered=0').fetchone()[0],'oauth':'READ_SCOPE_MISSING_REAUTH_REQUIRED','channel':'UNVERIFIED','cloudflare':'PARKED_INHERITED_NOT_FRESH','live_enabled':False,'remaining_gates':['OWNER_REAUTH','FRESH_CHANNEL_MATCH','SHARED_DURABLE_STATE','ACCOUNT_BUDGET','0011_APPROVAL','CANDIDATE_DEPLOY_APPROVAL','IMMUTABLE_DISPATCH','INDEPENDENT_READBACK','SINGLE_UPLOAD_APPROVAL','24H_LIVE_OBSERVATION']}

def command_center(report):
    require(report.get('mode')=='OFFLINE_SIMULATION' and report.get('live_enabled') is False,'DISPLAY_SOURCE_STOP')
    allowed=['mode','counts','last_success','last_failure','error_reason','updated_at','real_uploads','mock_uploads','stopped','render_success_rate','durations_seconds','budgets','undelivered_notifications','oauth','channel','cloudflare','remaining_gates']
    cells=''.join('<tr><th>'+html.escape(k)+'</th><td>'+html.escape(json.dumps(report.get(k),ensure_ascii=False))+'</td></tr>' for k in allowed)
    return '<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>PLM Command Center — OFFLINE</title><style>body{font:16px system-ui;max-width:960px;margin:2rem auto;background:#101827;color:#e2e8f0}table{border-collapse:collapse;width:100%}td,th{padding:12px;text-align:left;border-bottom:1px solid #334155;overflow-wrap:anywhere}h1{color:#67e8f9}</style><h1>PLM Command Center</h1><p>OFFLINEシミュレーション。実投稿0。Cloudflare PARKED。本番API未接続。</p><table>'+cells+'</table></html>'
