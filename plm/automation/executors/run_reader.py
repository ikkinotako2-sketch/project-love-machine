"""Independent bounded GitHub proof for any operation/prerequisite result."""
import base64,hashlib,json,re
from dataclasses import dataclass
_RUN_SEAL=object()
@dataclass(frozen=True)
class RunEvidence:
    run_id:str
    head:str
    operation:str
    live:bool
    seal:object
from .authority import Receipt,_SEAL
from ..ledger import require,Stop
from ..evidence_adapters import REPO

class OperationRunReader:
    def __init__(self,get):self.get=get;self.calls=0;self.cache={};self.real_source=getattr(get,'real_network_read',False) is True and getattr(get,'offline_mock',False) is not True
    def read(self,path):
        if path in self.cache:return self.cache[path]
        require(self.calls<32 and path.startswith('/repos/'+REPO+'/'),'PROOF_TARGET_BUDGET_STOP')
        self.calls+=1
        try:status,d=self.get(path)
        except Exception:raise Stop('PROOF_HTTP_UNKNOWN_STOP') from None
        require(status==200 and isinstance(d,dict),'PROOF_HTTP_STOP')
        self.cache[path]=d;return d
    def current(self,checked):
        e=checked.event;o=checked.plan['operations'][checked.operation];prefix='/repos/'+REPO
        run=self.read(prefix+'/actions/runs/'+e['run_id'])
        require(run.get('id')==int(e['run_id']) and run.get('repository',{}).get('full_name')==REPO and run.get('run_attempt')==1 and type(run.get('run_attempt')) is int and run.get('head_sha')==checked.head and run.get('head_branch')==checked.plan['branch'] and run.get('path')==o['workflow_path'] and run.get('event')=='push' and run.get('status')=='in_progress','INDEPENDENT_CURRENT_RUN_STOP')
        jobs=self.read(prefix+'/actions/runs/'+e['run_id']+'/jobs?per_page=100')
        require(type(jobs.get('total_count')) is int and jobs['total_count']==len(jobs.get('jobs',[])) and 0<jobs['total_count']<=100,'JOB_INVENTORY_STOP')
        require(sum(1 for j in jobs['jobs'] if j.get('run_id')==int(e['run_id']) and j.get('name')==o.get('job_name','execute') and j.get('status')=='in_progress')==1,'INDEPENDENT_CURRENT_JOB_STOP')
        return RunEvidence(e['run_id'],checked.head,checked.operation,self.real_source,_RUN_SEAL)
    def prerequisite(self,descriptor,raw):
        """Receipt is supplied by pinned GitHub artifact, not arbitrary user JSON."""
        d=descriptor;prefix='/repos/'+REPO
        require(hashlib.sha256(raw).hexdigest()==d['receipt_sha256'],'PREREQUISITE_RECEIPT_HASH_STOP')
        r=json.loads(raw)
        require(r.get('basis')=='LIVE_VERIFIED' and r.get('identity')==d['identity'] and r.get('operation')==d['operation'] and r.get('status')==d['status'] and r.get('run_id')==d['run_id'] and r.get('commit')==d['commit'],'PREREQUISITE_FIXTURE_OR_STATE_STOP')
        require(re.fullmatch('[1-9][0-9]{0,19}',d['run_id']) and re.fullmatch('[a-f0-9]{40}',d['commit']),'PREREQUISITE_ID_STOP')
        run=self.read(prefix+'/actions/runs/'+d['run_id'])
        require(run.get('repository',{}).get('full_name')==REPO and run.get('id')==int(d['run_id']) and run.get('head_sha')==d['commit'] and run.get('head_branch')==d['branch'] and run.get('path')==d['workflow_path'] and run.get('run_attempt')==1 and type(run.get('run_attempt')) is int and run.get('status')=='completed' and run.get('conclusion')=='success' and run.get('event')=='push','PREREQUISITE_RUN_NOT_SUCCESS')
        jobs=self.read(prefix+'/actions/runs/'+d['run_id']+'/jobs?per_page=100')
        require(type(jobs.get('total_count')) is int and jobs.get('total_count')==len(jobs.get('jobs',[])) and jobs['total_count']<=100 and sum(1 for j in jobs['jobs'] if j.get('run_id')==int(d['run_id']) and j.get('name')==d['job_name'] and j.get('conclusion')=='success')==1,'PREREQUISITE_JOB_STOP')
        def content(path,sha):
            v=self.read(prefix+'/contents/'+path+'?ref='+d['commit']);require(v.get('encoding')=='base64','PREREQUISITE_CONTENT_STOP')
            b=base64.b64decode(v['content']);require(len(b)<=65536 and hashlib.sha256(b).hexdigest()==sha,'PREREQUISITE_SOURCE_HASH_STOP');return b
        marker=json.loads(content(d['marker_path'],d['marker_sha256']))
        require(marker.get('identity')==d['identity'] and marker.get('operation')==d['operation'] and marker.get('state')=='CONSUMED_BEFORE_REMOTE' and marker.get('prepared_commit_sha')==d['prepared_commit'] and marker.get('approved') is True,'PREREQUISITE_MARKER_STOP')
        content(d['workflow_path'],d['workflow_sha256'])
        commit=self.read(prefix+'/commits/'+d['commit'])
        require([p.get('sha') for p in commit.get('parents',[])]==[d['prepared_commit']] and [(f.get('filename'),f.get('status')) for f in commit.get('files',[])]==[(d['marker_path'],'added')],'PREREQUISITE_MARKER_HISTORY_STOP')
        artifacts=self.read(prefix+'/actions/runs/'+d['run_id']+'/artifacts?per_page=100')
        require(type(artifacts.get('total_count')) is int and artifacts.get('total_count')==len(artifacts.get('artifacts',[])) and artifacts['total_count']<=100,'PREREQUISITE_ARTIFACT_INVENTORY_STOP')
        matches=[a for a in artifacts['artifacts'] if a.get('id')==d['artifact_id'] and a.get('expired') is False and a.get('digest')=='sha256:'+d['artifact_archive_sha256'] and a.get('workflow_run',{}).get('head_sha')==d['commit'] and str(a.get('workflow_run',{}).get('id'))==d['run_id']]
        require(len(matches)==1,'PREREQUISITE_ARTIFACT_STOP')
        allowed={'operation','identity','basis','status','run_id','commit','workflow_path','channel_id','upload_scope','readonly_scope','channel_match','oauth_refresh_POST_max','channels_GET_max','state_branch','state_path','initial_state_sha256','initial_blob_sha','state_commit','overwritten','job_id','video_id','private','notify_subscribers','media_sha256','upload_state','processed','artifact_id','artifact_archive_sha256','script_sha256','audio_sha256','caption_sha256','next_job','done','next_job_dispatch','metrics_basis','processed_readback','callback','migration_sha256','schema_sha256','DB_exact','PARKED','postcheck_done','module_manifest_sha256','source_representation_proven','exposure_zero','worker','rollback_requires_separate_approval','http_statuses','github_GET_attempted','request_counts'}
        require(set(r)<=allowed,'PREREQUISITE_RESULT_FIELDS_STOP')
        require(type(r.get('github_GET_attempted',0)) is int and 0<=r.get('github_GET_attempted',0)<=32,'PREREQUISITE_DIAGNOSTIC_STOP')
        require(all(set(x)=={'service','status'} and x['service'] in ('GitHub','Cloudflare','OAuth','YouTube','Callback','Artifact') and type(x['status']) is int and 100<=x['status']<=599 for x in r.get('http_statuses',[])),'PREREQUISITE_DIAGNOSTIC_STOP')
        require(all(re.fullmatch('[A-Za-z_]+',k) and type(v) is int and 0<=v<=64 for k,v in r.get('request_counts',{}).items()),'PREREQUISITE_DIAGNOSTIC_STOP')
        data={k:v for k,v in r.items() if k not in ('operation','identity','basis','status')}
        return Receipt(d['operation'],d['identity'],'LIVE_VERIFIED' if self.real_source else 'OFFLINE_CONTRACT',d['status'],data,_SEAL)
