"""Long-lived candidate state; one CAS document, per-job permanent tombstones.

No live backend is created here. Cross-run continuation needs an independent
completion authority: a stored Done alone is insufficient after a lost CAS ACK.
"""
import copy,json,re,sqlite3,threading
from .ledger import require,Stop,ID

def initial():return {'version':1,'stopped':False,'reason':None,'active':None,'last_completed':None,'jobs':{},'notices':{},'budgets':{},'release_identities':[]}

class SQLiteCAS:
    offline_mock=True
    def __init__(self,path,*,initialize=False):
        self.db=sqlite3.connect(path,isolation_level=None,timeout=5,check_same_thread=False);self.lock=threading.Lock()
        self.db.executescript('PRAGMA journal_mode=WAL;PRAGMA synchronous=FULL;CREATE TABLE IF NOT EXISTS lifecycle(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,body TEXT NOT NULL);')
        if initialize:self.db.execute('INSERT OR IGNORE INTO lifecycle VALUES(1,1,?)',(json.dumps(initial()),))
    def read(self):
        row=self.db.execute('SELECT revision,body FROM lifecycle WHERE id=1').fetchone()
        return (f'{row[0]:040x}',json.loads(row[1])) if row else None
    def cas(self,sha,body):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                n=self.db.execute('UPDATE lifecycle SET revision=revision+1,body=? WHERE id=1 AND revision=?',(json.dumps(body,sort_keys=True),int(sha,16))).rowcount
                require(n==1,'STATE_CAS_CONFLICT_STOP');out=self.db.execute('SELECT revision FROM lifecycle').fetchone()[0];self.db.execute('COMMIT');return f'{out:040x}'
            except Exception:self.db.execute('ROLLBACK');raise
    def close(self):self.db.close()

class SharedLifecycle:
    def __init__(self,backend,clock,*,completion_authority,release_authority=lambda approval:False):
        self.backend=backend;self.clock=clock;self.authority=completion_authority;self.release_authority=release_authority;self.uncertain=False
        self.refresh()
    def refresh(self):
        require(not self.uncertain,'STATE_UNKNOWN_NO_MORE_IO')
        try:response=self.backend.read()
        except Exception:self.uncertain=True;raise Stop('STATE_READ_UNKNOWN') from None
        require(response is not None,'STATE_NOT_INITIALIZED')
        self.sha,self.doc=response
        require(re.fullmatch('[a-f0-9]{40}',str(self.sha)) and set(self.doc)==set(initial()) and self.doc['version']==1,'STATE_SHAPE_STOP')
        require(type(self.doc['stopped']) is bool and isinstance(self.doc['jobs'],dict) and len(self.doc['jobs'])<=64,'STATE_SHAPE_STOP')
        for key,row in self.doc['jobs'].items():
            require(ID.fullmatch(key) and row.get('job_id')==key and row.get('consumed') is True and row.get('state') in ('Processing','ACKNOWLEDGED','Done','Failed','UNKNOWN'),'STATE_INCONSISTENT_STOP')
            if row['state']=='Done':require(row.get('callback')=='ACK' and isinstance(row.get('video_id'),str) and re.fullmatch('[A-Za-z0-9_-]{11}',row['video_id']) and re.fullmatch(r'[1-9][0-9]{0,19}',str(row.get('run_id',''))),'STATE_INCONSISTENT_STOP')
        if self.doc['active'] is not None:require(self.doc['active'] in self.doc['jobs'] and self.doc['jobs'][self.doc['active']]['state']!='Done','STATE_INCONSISTENT_STOP')
        if self.doc['last_completed'] is not None:require(self.doc['last_completed'] in self.doc['jobs'] and self.doc['jobs'][self.doc['last_completed']]['state']=='Done','STATE_INCONSISTENT_STOP')
    def commit(self,doc):
        require(not self.uncertain,'STATE_UNKNOWN_NO_MORE_IO');self.uncertain=True
        try:sha=self.backend.cas(self.sha,doc)
        except Exception:raise Stop('STATE_WRITE_UNKNOWN_NO_RETRY') from None
        require(re.fullmatch('[a-f0-9]{40}',str(sha)) is not None,'STATE_WRITE_UNKNOWN_NO_RETRY')
        self.sha=sha;self.doc=doc;self.uncertain=False
    def claim(self,job,fingerprint,identity,owner,now,*,day,cost=1,limit=2,lease=300):
        require(not self.uncertain,'STATE_UNKNOWN_NO_MORE_IO')
        require(ID.fullmatch(job) and ID.fullmatch(identity) and ID.fullmatch(owner) and re.fullmatch('[a-f0-9]{64}',fingerprint),'CLAIM_SHAPE_STOP')
        require(type(now) is int and now==self.clock() and type(lease) is int and 0<lease<=900 and re.fullmatch(r'\d{4}-\d{2}-\d{2}',day) and type(cost) is int and cost>0 and type(limit) is int and 0<limit<=2,'BUDGET_OR_LEASE_STOP')
        from datetime import datetime,timezone
        require(day==datetime.fromtimestamp(now,timezone.utc).strftime('%Y-%m-%d'),'BUDGET_DAY_STOP')
        require(not self.doc['stopped'],'GLOBAL_STOP')
        require(job not in self.doc['jobs'] and identity not in [r['identity'] for r in self.doc['jobs'].values()],'PERMANENT_JOB_TOMBSTONE')
        require(self.doc['active'] is None,'ACTIVE_OPERATION_NO_RECLAIM')
        previous=self.doc['last_completed']
        if previous is not None:
            # Independent Actions completion evidence, not the contents record.
            require(self.authority(copy.deepcopy(self.doc['jobs'][previous])) is True,'PREVIOUS_COMPLETION_UNVERIFIED_STOP')
        require(len(self.doc['jobs'])<64,'STATE_CAPACITY_STOP')
        d=copy.deepcopy(self.doc);used=d['budgets'].get(day,0);require(used+cost<=limit,'BUDGET_STOP')
        d['budgets'][day]=used+cost
        row={'job_id':job,'fingerprint':fingerprint,'identity':identity,'owner':owner,'epoch':len(d['jobs'])+1,'fence':len(d['jobs'])+1,'state':'Processing','sent':False,'consumed':True,'lease_until':now+lease,'video_id':None,'run_id':None,'callback':'NOT_SENT'}
        d['jobs'][job]=row;d['active']=job;self.commit(d);return copy.deepcopy(row)
    def checked(self,claim):
        require(not self.uncertain,'STATE_UNKNOWN_NO_MORE_IO')
        row=self.doc['jobs'].get(claim['job_id'])
        require(row and all(row[k]==claim[k] for k in ['owner','epoch','fence','fingerprint','identity']) and self.doc['active']==claim['job_id'],'STALE_OWNER_FENCE_STOP')
        require(row['lease_until']>self.clock(),'LEASE_EXPIRED_NO_RECLAIM')
        return row
    def consume(self,claim,identity,now):
        row=self.checked(claim);require(not row['sent'] and row['state']=='Processing' and identity==row['identity'] and now==self.clock(),'SENT_CONFLICT_STOP')
        d=copy.deepcopy(self.doc);d['jobs'][claim['job_id']]['sent']=True;self.commit(d)
    def finish(self,claim,state,video_id=None,reason=None):
        row=self.checked(claim);require(row['state']=='Processing' and state in ['Done','UNKNOWN','Failed'],'TERMINAL_STOP')
        d=copy.deepcopy(self.doc);r=d['jobs'][claim['job_id']]
        if state=='Done':
            require(row['sent'] and isinstance(video_id,str) and re.fullmatch('[A-Za-z0-9_-]{11}',video_id),'ACK_BINDING_STOP');r.update(state='ACKNOWLEDGED',video_id=video_id)
        else:r['state']=state;d['stopped']=True;d['reason']='UPLOAD_UNKNOWN' if state=='UNKNOWN' else 'OPERATION_FAILED';d['notices'].setdefault(claim['job_id']+':STOP',{'reason':d['reason'],'delivered':False})
        self.commit(d);return {'job_id':claim['job_id'],'state':r['state'],'video_id':r['video_id'],'reason_code':d['reason']}
    def complete(self,claim,receipt,continuation=None):
        row=self.checked(claim)
        require(row['state']=='ACKNOWLEDGED' and receipt.get('job_id')==row['job_id'] and receipt.get('video_id')==row['video_id'] and receipt.get('processed') is True and receipt.get('callback')=='ACK' and re.fullmatch(r'[1-9][0-9]{0,19}',str(receipt.get('run_id',''))),'COMPLETION_BINDING_STOP')
        require(self.authority({**row,'run_id':receipt['run_id']}) is True,'INDEPENDENT_COMPLETION_STOP')
        d=copy.deepcopy(self.doc);d['jobs'][row['job_id']].update(state='Done',callback='ACK',run_id=receipt['run_id'])
        if continuation is not None:
            require(set(continuation)=={'next_job','improvement_method','coordinator_run_id'} and ID.fullmatch(continuation['next_job']) and continuation['next_job'] not in d['jobs'] and continuation['improvement_method']=='rules' and re.fullmatch(r'[1-9][0-9]{0,19}',str(continuation['coordinator_run_id'])),'CONTINUATION_STOP')
            d['jobs'][row['job_id']]['continuation']=copy.deepcopy(continuation)
        d['active']=None;d['last_completed']=row['job_id'];self.commit(d)
        return {'job_id':row['job_id'],'state':'Done','video_id':row['video_id']}
    def save_receipt(self,claim,receipt,expected):
        row=self.checked(claim)
        require(row['state']=='ACKNOWLEDGED' and receipt.get('job_id')==row['job_id'] and receipt.get('video_id')==row['video_id'] and receipt.get('processed') is True and receipt.get('callback')=='ACK','RECEIPT_BINDING_STOP')
        allowed={'repository','run_id','attempt','commit','prepared_commit','branch','workflow_path','job_name','job_id','identity','media_sha256','artifact_id','artifact_archive_sha256','artifact_run_id','artifact_commit','marker_path','marker_sha256','workflow_sha256','approval_field'}
        require(set(expected)<=allowed and expected.get('job_id')==row['job_id'] and expected.get('identity')==row['identity'] and str(expected.get('run_id'))==str(receipt['run_id']),'RECEIPT_EXPECTED_STOP')
        require(all(type(v) in (str,int) and (type(v) is int or len(v)<=512) for v in expected.values()),'RECEIPT_SHAPE_STOP')
        safe={k:receipt[k] for k in ['job_id','video_id','processed','callback','run_id']}
        d=copy.deepcopy(self.doc);d['jobs'][row['job_id']]['completion_receipt']=safe;d['jobs'][row['job_id']]['provenance_expected']=copy.deepcopy(expected);self.commit(d)
    def mark_callback_sent(self,claim):
        row=self.checked(claim);require(row['state']=='ACKNOWLEDGED' and row['callback']=='NOT_SENT','CALLBACK_ALREADY_CONSUMED')
        d=copy.deepcopy(self.doc);d['jobs'][row['job_id']]['callback']='SENT';self.commit(d);return True
    def halt(self,claim,reason):
        require(not self.uncertain,'STATE_UNKNOWN_NO_MORE_IO')
        require(reason in ['READBACK_UNKNOWN','CALLBACK_UNKNOWN','UPLOAD_UNKNOWN','AUTH_STOP','QUOTA_STOP','LEASE_EXPIRED','D1_UNKNOWN','CONFIG_STOP'],'REASON_STOP')
        d=copy.deepcopy(self.doc);job=claim['job_id'];require(job in d['jobs'],'JOB_STOP')
        if d['jobs'][job]['state']!='Done':d['jobs'][job]['state']='UNKNOWN'
        d['stopped']=True;d['reason']=reason;d['notices'].setdefault(job+':STOP',{'reason':reason,'delivered':False});self.commit(d)
    def release_stop(self,approval):
        require(not self.uncertain and self.doc['stopped'] and approval.get('operation_kind')=='RELEASE_GLOBAL_STOP' and approval.get('expected_state_sha')==self.sha and ID.fullmatch(str(approval.get('identity',''))) and approval['identity'] not in self.doc['release_identities'] and self.release_authority(approval) is True,'INDEPENDENT_RELEASE_APPROVAL_REQUIRED')
        d=copy.deepcopy(self.doc);d['stopped']=False;d['reason']=None;d['active']=None;d['release_identities'].append(approval['identity']);self.commit(d)
    def get(self,job):return copy.deepcopy(self.doc['jobs'][job])

class GitContentsCAS:
    """Future state adapter: initialized independent branch; no default transport.
    One GET or CAS PUT per call; no retry, create, delete, or main writes.
    """
    PATH='/repos/ikkinotako2-sketch/project-love-machine/contents/automation-state/lifecycle.json'
    BRANCH='plm-execution-state-v2'
    def __init__(self,transport):self.transport=transport;self.poisoned=False
    def read(self):
        import base64
        require(not self.poisoned,'STATE_IO_STOP');self.poisoned=True
        try:
            status,p=self.transport('GET',self.PATH+'?ref='+self.BRANCH,None)
            require(status==200 and p.get('encoding')=='base64' and re.fullmatch('[a-f0-9]{40}',str(p.get('sha',''))),'STATE_GET_STOP')
            raw=base64.b64decode(p['content'],validate=False);require(len(raw)<=32768,'STATE_BOUND_STOP');d=json.loads(raw)
        except Exception:raise Stop('STATE_READ_UNKNOWN') from None
        self.poisoned=False;return p['sha'],d
    def cas(self,sha,doc):
        import base64
        require(not self.poisoned and re.fullmatch('[a-f0-9]{40}',sha),'STATE_IO_STOP');self.poisoned=True
        raw=json.dumps(doc,sort_keys=True,separators=(',',':')).encode();require(len(raw)<=32768,'STATE_BOUND_STOP')
        status,p=self.transport('PUT',self.PATH,{'branch':self.BRANCH,'sha':sha,'message':'PLM shared lifecycle CAS','content':base64.b64encode(raw).decode()})
        require(status in [200,201] and re.fullmatch('[a-f0-9]{40}',str(p.get('content',{}).get('sha',''))),'STATE_ACK_UNKNOWN')
        self.poisoned=False;return p['content']['sha']
