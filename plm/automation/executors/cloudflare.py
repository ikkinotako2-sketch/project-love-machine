"""Four separate sandbox-only transfer kernels, imports never contact Cloudflare.

D1 HTTP uses POST for fixed read queries as well as one separately approved DDL
batch. An ACK is not a postcheck. No route/cron/consumer/rollback mutation exists.
"""
import hashlib,json,re,posixpath,sqlite3,http.client,time
from datetime import datetime,timezone
from pathlib import Path
from email.parser import BytesParser
from email.policy import default as email_policy
from .authority import start,adapter_for,live_authority
from ..ledger import require,Stop
ROOT=Path(__file__).resolve().parents[3]
ACCOUNT='6c8ccd6aface937ab5dabef61cb64534'
WORKER='plm-serverless-sandbox-control'
DB='18050cf6-934e-4f3a-a1cd-5041bac1c35e'
DB_NAME='plm-serverless-sandbox-state'
DBPATH='/accounts/'+ACCOUNT+'/d1/database/'+DB
QUERY=DBPATH+'/query'
WP='/accounts/'+ACCOUNT+'/workers/scripts/'+WORKER
VERIFY='/accounts/'+ACCOUNT+'/tokens/verify'
OLD='8a6615fd020ca6590ba8f5e2c73a3844473d9e6ecd3babb19ea836d604d4a8a9'
ENTRY='integration/speaker-runtime.mjs'
SQL='integration/0011_automation_budget_notification_successor.sql'
FLAGS={k:'true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}
EXPOSURE=[WP+'/content/v2',WP+'/subdomain','/accounts/'+ACCOUNT+'/workers/domains?service='+WORKER,'/zones?account.id='+ACCOUNT+'&per_page=50&page=1',WP+'/schedules','/accounts/'+ACCOUNT+'/queues',WP+'/settings']
SCHEMA_QUERY="SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL AND (name LIKE 'plm_rt_v2_%' OR name LIKE 'plm_ytq_v1_%' OR name LIKE 'plm_ytp_v1_%' OR name LIKE 'plm_auto_v1_%') ORDER BY type,name;"
COUNTS_QUERY='SELECT count(*) AS jobs FROM plm_rt_v2_job;'
READ_QUERY=SCHEMA_QUERY+COUNTS_QUERY
LEDGER_SQL="""CREATE TABLE plm_auto_v1_migration_choice(choice INTEGER PRIMARY KEY CHECK(choice=11),source_sha256 TEXT NOT NULL,identity TEXT NOT NULL UNIQUE);
CREATE TRIGGER plm_auto_v1_migration_choice_no_update BEFORE UPDATE ON plm_auto_v1_migration_choice BEGIN SELECT RAISE(ABORT,'choice_immutable'); END;
CREATE TRIGGER plm_auto_v1_migration_choice_no_delete BEFORE DELETE ON plm_auto_v1_migration_choice BEGIN SELECT RAISE(ABORT,'choice_tombstone'); END;
"""
LEDGER_QUERY='SELECT choice,source_sha256,identity FROM plm_auto_v1_migration_choice;'
PARKED=b"export default {async fetch(){return new Response('PARKED_RUNTIME_COMPOSITION',{status:503});},async scheduled(){throw new Error('CRON_DISABLED');},async queue(){throw new Error('QUEUE_CONSUMER_DISABLED');}};"

def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def contract(root=ROOT):return json.loads((Path(root)/'readiness/cloudflare-transfer-contract.json').read_bytes())

def schema_hash(rows):
    require(isinstance(rows,list) and len(rows)<=100 and all(set(r)=={'type','name','sql'} and r['type'] in ('table','index','trigger') and isinstance(r['sql'],str) and len(r['sql'])<=16384 for r in rows),'D1_SCHEMA_SHAPE_STOP')
    require(len({r['name'] for r in rows})==len(rows),'D1_SCHEMA_DUPLICATE_STOP')
    return sha(canonical(sorted(rows,key=lambda x:(x['type'],x['name']))))

def migration_bytes(c,root=ROOT):
    raw=(Path(root)/SQL).read_bytes();require(sha(raw)==c['successor_sql_sha256'],'SUCCESSOR_SQL_DRIFT_STOP')
    require(c['selected_migration']==SQL and c['old_candidate_apply_allowed'] is False,'MIGRATION_SELECTION_STOP')
    return raw

def module_bytes(c,root=ROOT):
    modules={n:(Path(root)/n).read_bytes() for n in c['modules']}
    require(all(sha(v)==c['modules'][n] for n,v in modules.items()),'WORKER_MODULE_DRIFT_STOP')
    require(modules[ENTRY].rstrip().endswith(PARKED) and b"export function createLiveSpeakerComposition(){throw new Error('PREPARATION_ONLY_REMOTE_ACTIVATION_DISABLED');}" in modules[ENTRY],'WORKER_NOT_PARKED_STOP')
    return modules

def multipart(c,root=ROOT):
    modules=module_bytes(c,root);boundary=b'plm-speaker-runtime-parked-v1'
    metadata={'main_module':ENTRY,'compatibility_date':'2026-10-06','bindings':[{'type':'d1','name':'DB','id':DB}]+[{'type':'plain_text','name':k,'text':v} for k,v in FLAGS.items()],'keep_bindings':['secret_text']}
    parts=[('metadata',canonical(metadata),'application/json')]+[(n,modules[n],'application/javascript+module') for n in sorted(modules)]
    body=b''
    for name,raw,kind in parts:
        require(boundary not in raw and re.fullmatch('[A-Za-z0-9_./-]+',name),'MULTIPART_SHAPE_STOP')
        header=b'Content-Disposition: form-data; name="'+name.encode()+b'"'
        if name!='metadata':header+=b'; filename="'+name.encode()+b'"'
        body+=b'--'+boundary+b'\r\n'+header+b'\r\nContent-Type: '+kind.encode()+b'\r\n\r\n'+raw+b'\r\n'
    body+=b'--'+boundary+b'--\r\n';require(len(body)<=262144,'WORKER_PACKAGE_BOUND_STOP')
    return body,'multipart/form-data; boundary='+boundary.decode()

def comparable(raw,meta):
    require(isinstance(raw,bytes) and len(raw)<=262144,'SOURCE_BOUND_STOP')
    ctype=meta.get('content_type','');entry=meta.get('entrypoint')
    if ctype.split(';')[0] in ('application/javascript','application/javascript+module','text/javascript'):
        require(entry in (None,'runtime-bundle.mjs'),'SOURCE_SELECTOR_STOP');return {'runtime-bundle.mjs':sha(raw)},'runtime-bundle.mjs'
    require(ctype.startswith('multipart/form-data;'),'SOURCE_REPRESENTATION_UNVERIFIED_STOP')
    msg=BytesParser(policy=email_policy).parsebytes(('Content-Type: '+ctype+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
    require(msg.is_multipart() and not msg.defects,'SOURCE_REPRESENTATION_UNVERIFIED_STOP')
    modules={};selector=entry
    for part in msg.iter_parts():
        name=part.get_param('name',header='Content-Disposition');body=part.get_payload(decode=True)
        require(isinstance(name,str) and isinstance(body,bytes),'SOURCE_SHAPE_STOP')
        if name=='metadata':
            d=json.loads(body);candidate=d.get('main_module');require(selector is None or selector==candidate,'SOURCE_SELECTOR_STOP');selector=candidate;continue
        require(re.fullmatch('[A-Za-z0-9_./-]+',name) and '..' not in Path(name).parts and name not in modules and part.get_content_type() in ('application/javascript','application/javascript+module','text/javascript'),'SOURCE_MODULE_STOP')
        modules[name]=sha(body)
    require(selector in modules,'SOURCE_REPRESENTATION_UNVERIFIED_STOP')
    return modules,selector

def envelope(status,p):
    require(status==200 and isinstance(p,dict) and p.get('success') is True,'CF_HTTP_OR_API_STOP');return p['result']

def database_info(status,p):
    r=envelope(status,p);require(r.get('uuid',r.get('id'))==DB and r.get('name')==DB_NAME,'D1_IDENTITY_STOP')

def query_result(status,p,expected_count):
    rows=envelope(status,p);require(isinstance(rows,list) and len(rows)==expected_count and all(r.get('success') is True and isinstance(r.get('results',[]),list) for r in rows),'D1_RESULT_UNKNOWN_STOP');return [r.get('results',[]) for r in rows]

class TransferExecutor:
    def __init__(self,transport,*,root=ROOT):self.t=transport;self.root=Path(root);self.c=contract(root);self.calls=[];self.used=False;self.uncertain=False
    def request(self,method,path,body=None,content_type=None):
        require(not self.uncertain,'CF_UNKNOWN_NO_MORE_IO');self.uncertain=True;self.calls.append((method,path))
        try:out=self.t(method,path,body,content_type)
        except Exception:raise Stop('CF_TRANSPORT_UNKNOWN_NO_RETRY') from None
        require(type(out[0]) is int and out[0] in (200,201),'CF_HTTP_STOP_NO_RETRY');self.uncertain=False;return out
    def run(self,permit):
        start(permit,permit.operation);adapter_for(permit,self.t);require(not self.used,'CF_TRANSFER_CONSUMED');self.used=True
        try:
            if permit.operation in ('migration','migration_postcheck'):return self.migration(permit)
            if permit.operation in ('worker_deploy','worker_postcheck'):return self.worker(permit)
            raise Stop('CF_OPERATION_STOP')
        except Exception:
            self.uncertain=True;raise Stop('CF_TRANSFER_STOP_NO_RETRY') from None
    def migration(self,permit):
        database_info(*self.request('GET',DBPATH)[:2])
        post=permit.operation=='migration_postcheck';q=READ_QUERY+(LEDGER_QUERY if post else '')
        rows=query_result(*self.request('POST',QUERY,{'sql':q,'params':[]})[:2],3 if post else 2)
        require(rows[1]==[{'jobs':0}],'D1_NONEMPTY_RUNTIME_STOP')
        expected=self.c['post_schema_sha256'] if post else self.c['baseline_schema_sha256']
        require(schema_hash(rows[0])==expected,'D1_SCHEMA_OR_0011_COLLISION_STOP')
        if post:
            parent=permit.prerequisites[0]
            require(rows[2]==[{'choice':11,'source_sha256':self.c['successor_sql_sha256'],'identity':parent.identity}],'MIGRATION_CHOICE_BINDING_STOP')
            return permit.receipt('VERIFIED',{'migration_sha256':self.c['successor_sql_sha256'],'schema_sha256':expected,'DB_exact':True,'PARKED':True})
        raw=migration_bytes(self.c,self.root)
        sql=raw.decode()+LEDGER_SQL+'INSERT INTO plm_auto_v1_migration_choice VALUES(11,\''+self.c['successor_sql_sha256']+'\',\''+permit.identity+'\');'
        # One write request only. The HTTP batch transaction contract is a release gate,
        # not inferred from the local SQLite fixture or Workers binding documentation.
        result=envelope(*self.request('POST',QUERY,{'sql':sql,'params':[]})[:2])
        require(isinstance(result,list) and result and all(r.get('success') is True for r in result),'MIGRATION_ACK_UNKNOWN_STOP')
        return permit.receipt('ACKNOWLEDGED',{'migration_sha256':self.c['successor_sql_sha256'],'DB_exact':True,'postcheck_done':False})
    def worker(self,permit):
        post=permit.operation=='worker_postcheck'
        if not post:
            r=envelope(*self.request('GET',VERIFY)[:2]);require(r.get('status')=='active','TOKEN_INACTIVE_STOP')
            for name in ('expires_on','not_before'):
                if name not in r:continue
                try:value=datetime.fromisoformat(r[name].replace('Z','+00:00'));require(value.tzinfo is not None,'TOKEN_TIMESTAMP_STOP');stamp=value.timestamp()
                except Exception:raise Stop('TOKEN_TIMESTAMP_STOP') from None
                require(stamp>time.time()+180 if name=='expires_on' else stamp<=time.time(),'TOKEN_TIME_WINDOW_STOP')
        source=None
        for path in EXPOSURE:
            status,p,meta=self.request('GET',path)
            if path==WP+'/content/v2':
                hashes,entry=comparable(p,meta)
                if post:require(hashes==self.c['modules'] and entry==ENTRY,'WORKER_POST_SOURCE_STOP')
                else:require(hashes=={'runtime-bundle.mjs':OLD},'WORKER_SOURCE_DRIFT_STOP')
                source=hashes
                continue
            r=envelope(status,p)
            if path.endswith('/subdomain'):require(r.get('enabled') is False and r.get('previews_enabled') is False,'ACTIVE_WORKERS_DEV_STOP')
            elif '/workers/domains?' in path:require(r==[],'CUSTOM_DOMAIN_PRESENT_STOP')
            elif path.startswith('/zones?'):
                require(r==[] and p.get('result_info',{}).get('page',1)==1 and p.get('result_info',{}).get('per_page',50)==50,'ZONE_OR_ROUTE_INSPECTION_REQUIRED')
            elif path.endswith('/schedules'):require(r==[] or r=={'schedules':[]},'CRON_ACTIVE_STOP')
            elif path.endswith('/queues'):require(r==[],'CONSUMER_VISIBILITY_STOP')
            else:
                bindings=r.get('bindings');require(isinstance(bindings,list),'BINDINGS_UNKNOWN_STOP')
                d1=[b for b in bindings if b.get('type')=='d1'];require(d1==[{'type':'d1','name':'DB','id':DB}],'D1_BINDING_STOP')
                secrets=[b for b in bindings if b.get('type')=='secret_text']
                require(all(set(b)=={'type','name'} and b['name'] in ('PLM_YOUTUBE_CHECKPOINT_KEY','PLM_YOUTUBE_RESULT_CALLBACK_KEY','PLM_GITHUB_DISPATCH_TOKEN') for b in secrets),'SECRET_METADATA_STOP')
                for k,v in FLAGS.items():require(any(b.get('type')=='plain_text' and b.get('name')==k and b.get('text')==v for b in bindings),'SAFE_FLAGS_STOP')
                require(len({b.get('name') for b in bindings})==len(bindings) and all(b.get('type') in ('d1','plain_text','secret_text') and (b.get('type')=='secret_text' or b.get('name') in {'DB',*FLAGS}) for b in bindings),'UNAPPROVED_BINDING_STOP')
        if post:return permit.receipt('VERIFIED',{'module_manifest_sha256':self.c['module_manifest_sha256'],'source_representation_proven':True,'PARKED':True,'exposure_zero':True,'DB_exact':True})
        body,typ=multipart(self.c,self.root)
        r=envelope(*self.request('PUT',WP,body,typ)[:2]);require(r.get('id')==WORKER,'DEPLOY_ACK_UNKNOWN_STOP')
        return permit.receipt('ACKNOWLEDGED',{'worker':WORKER,'module_manifest_sha256':self.c['module_manifest_sha256'],'postcheck_done':False,'rollback_requires_separate_approval':True})

class CFHTTP:
    offline_mock=False
    def __init__(self,permit,read_token,write_token,*,connector=http.client.HTTPSConnection):
        live_authority(permit);require(permit.operation in ('migration','migration_postcheck','worker_deploy','worker_postcheck'),'CF_OPERATION_ROLE_STOP');self.permit=permit;self.read=read_token;self.write=write_token;self.connector=connector;self.used=0;self.unknown=False;self.statuses=[]
        for token in (read_token,write_token):require(isinstance(token,str) and token and all(32<ord(c)<127 for c in token),'TOKEN_SHAPE_STOP')
    def __repr__(self):return '<CFHTTP REDACTED>'
    def clear(self):self.read=None;self.write=None
    def __call__(self,method,path,body=None,content_type=None):
        require(not self.unknown,'CF_HTTP_UNKNOWN_NO_RETRY');op=self.permit.operation
        seq=([('GET',DBPATH),('POST',QUERY),('POST',QUERY)] if op=='migration' else [('GET',DBPATH),('POST',QUERY)] if op=='migration_postcheck' else [('GET',VERIFY)]+[('GET',p) for p in EXPOSURE]+[('PUT',WP)] if op=='worker_deploy' else [('GET',p) for p in EXPOSURE])
        require(self.used<len(seq) and seq[self.used]==(method,path),'CF_EXACT_REQUEST_SEQUENCE_STOP')
        self.used+=1;self.unknown=True
        if method=='POST':
            c=contract();readonly=body.get('sql') in (READ_QUERY,READ_QUERY+LEDGER_QUERY)
            expected=migration_bytes(c).decode()+LEDGER_SQL+'INSERT INTO plm_auto_v1_migration_choice VALUES(11,\''+c['successor_sql_sha256']+'\',\''+self.permit.identity+'\');'
            require(set(body)=={'sql','params'} and body['params']==[] and (readonly or op=='migration' and body['sql']==expected),'D1_SQL_ALLOWLIST_STOP')
        mutating=method=='PUT' or method=='POST' and body['sql'] not in (READ_QUERY,READ_QUERY+LEDGER_QUERY)
        token=self.write if mutating or path==VERIFY else self.read
        conn=self.connector('api.cloudflare.com',timeout=15)
        try:
            data=body if isinstance(body,bytes) else None if body is None else canonical(body)
            headers={'Authorization':'Bearer '+token,'Content-Type':content_type or 'application/json','Accept':'*/*'}
            conn.request(method,'/client/v4'+path,body=data,headers=headers);r=conn.getresponse();self.statuses.append(r.status)
            if r.status not in (200,201):return r.status,{},{}
            raw=r.read(262145);require(len(raw)<=262144,'CF_RESPONSE_BOUND_STOP')
            meta={'content_type':r.getheader('Content-Type') or '', 'entrypoint':r.getheader('cf-entrypoint')}
            result=raw if path==WP+'/content/v2' else json.loads(raw)
            self.unknown=False;return r.status,result,meta
        except Exception:raise Stop('CF_HTTP_UNKNOWN_STOP') from None
        finally:conn.close()
