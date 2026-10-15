"""Bounded one-shot OAuth code exchange and separate candidate Secret creation.

No import-time I/O. Current source plan disables execution before credential reads.
Only metadata, fixed reason codes and numeric status are eligible for output.
"""
import argparse,base64,ctypes,ctypes.util,hashlib,http.client,json,os,re,time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode,parse_qs
from .oauth_reuse import EXISTING,CANDIDATE,REDIRECT,SCOPES,CLIENT,parse,text,combine_bundle
from ..execution_gate import GitAudit
from ..ledger import require,Stop

ROOT=Path(__file__).resolve().parents[3]
PLAN='readiness/oauth-client-reuse-exchange-plan.json'
MANIFEST='readiness/oauth-client-reuse-exchange-hashes.json'
REPO='ikkinotako2-sketch/project-love-machine'
PREFIX='/repos/'+REPO+'/actions/secrets/'
HANDOFF='PLM_YOUTUBE_REAUTH_HANDOFF_ONCE'
WRITER='PLM_GITHUB_OAUTH_SECRET_WRITER'
SAFE={k:'true' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}
_SEAL=object()

def sha(raw):return hashlib.sha256(raw).hexdigest()
def duplicate_free(raw):
    def pairs(xs):
        d={}
        for k,v in xs:require(k not in d,'DUPLICATE_INPUT_STOP');d[k]=v
        return d
    try:return json.loads(raw,object_pairs_hook=pairs)
    except Exception:raise Stop('INPUT_JSON_STOP') from None

@dataclass(repr=False)
class Permit:
    plan:dict
    mode:str
    seal:object
    used:bool=False
    def __repr__(self):return '<OAuthExchangePermit REDACTED>'

def local_gate(root,env,*,prepared=None,plan_sha=None,manifest_sha=None):
    root=Path(root);p=duplicate_free((root/PLAN).read_bytes())
    if p.get('enabled') is not True:return None
    require(re.fullmatch('[a-f0-9]{40}',prepared or '') and re.fullmatch('[a-f0-9]{64}',plan_sha or '') and re.fullmatch('[a-f0-9]{64}',manifest_sha or ''),'EXTERNAL_PINS_REQUIRED')
    g=GitAudit(root);head=g.git('rev-parse','HEAD').decode().strip()
    require(env.get('GITHUB_REPOSITORY')==REPO and env.get('GITHUB_REF')=='refs/heads/'+p['branch'] and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_RUN_ATTEMPT')=='1' and env.get('GITHUB_SHA')==head and re.fullmatch('[1-9][0-9]{0,19}',env.get('GITHUB_RUN_ID','')),'RUN_CONTEXT_STOP')
    require(all(env.get(k)==v for k,v in SAFE.items()),'SAFE_FLAGS_STOP')
    require(p['owner_approved'] is True and p['operational_exclusion_attested'] is True and p['writer_permissions_reviewed'] is True and p['handoff_approved'] is True,'RELEASE_APPROVAL_REQUIRED')
    require(CLIENT.fullmatch(p.get('client_id') or '') and p['redirect_uri']==REDIRECT and p['scopes']==list(SCOPES) and re.fullmatch('[A-Za-z0-9_-]{43,128}',p.get('consent_state') or ''),'CONSENT_PINS_REQUIRED')
    require(p['identity']=='provider-neutral-youtube-client-reuse-exchange-20261015-r1' and p['workflow_path']=='.github/workflows/plm-youtube-client-reuse-exchange-once.yml' and p['executor_path']=='plm/automation/executors/oauth_exchange.py' and p['schema_path']=='readiness/oauth-client-reuse-exchange-marker.schema.json','EXECUTION_TARGET_STOP')
    require(p['repository']==REPO and p['existing_secret']==EXISTING and p['candidate_secret']==CANDIDATE and p['handoff_secret']==HANDOFF and p['writer_secret']==WRITER,'CREDENTIAL_ROLE_STOP')
    require(g.git('rev-parse','--is-shallow-repository').strip()==b'false' and g.git('status','--porcelain')==b'','FULL_CLEAN_HISTORY_REQUIRED')
    require(g.git('merge-base',p['preparation_parent'],prepared).decode().strip()==p['preparation_parent'] and g.git('rev-list','--count',p['preparation_parent']+'..'+prepared).strip()==b'1','PREPARATION_HISTORY_STOP')
    files=p['preparation_files'];require(type(files) is list and len(files)==len(set(files)) and all(isinstance(x,str) and not x.startswith('/') and '..' not in Path(x).parts and not x.startswith('audit-evidence/') for x in files),'PREPARATION_FILES_STOP')
    require(sorted(g.git('diff','--name-only',p['preparation_parent']+'..'+prepared).decode().splitlines())==sorted(files),'PREPARATION_DIFF_STOP')
    require(g.git('show','-s','--format=%P',head).decode().strip()==prepared and g.git('show','-s','--format=%s',head).decode().strip()==p['marker_message'],'MARKER_HISTORY_STOP')
    path=p['marker_path'];require(path=='audit-evidence/consumed/'+p['identity']+'.json','MARKER_PATH_STOP')
    require(g.absent(prepared,path) and g.git('diff','--name-status',prepared+'..'+head).decode().splitlines()==['A\t'+path],'MARKER_ONLY_STOP')
    m=duplicate_free(g.raw(head,path))
    expected={'identity':p['identity'],'state':'CONSUMED_BEFORE_REMOTE','approved':True,'prepared_commit_sha':prepared,'plan_sha256':plan_sha,'manifest_sha256':manifest_sha,'workflow_sha256':sha(g.raw(prepared,p['workflow_path'])),'executor_sha256':sha(g.raw(prepared,p['executor_path'])),'schema_sha256':sha(g.raw(prepared,p['schema_path']))}
    require(m==expected and sha(g.raw(prepared,PLAN))==plan_sha and (root/PLAN).read_bytes()==g.raw(prepared,PLAN),'MARKER_SOURCE_PINS_STOP')
    manifest=g.raw(prepared,MANIFEST);require(sha(manifest)==manifest_sha,'MANIFEST_PIN_STOP')
    pins=duplicate_free(manifest)['source_sha256']
    require(set(files)-{MANIFEST}<=set(pins),'MANIFEST_COVERAGE_STOP')
    require((root/MANIFEST).read_bytes()==manifest,'MANIFEST_WORKTREE_STOP')
    for path,h in pins.items():
        require(not Path(path).is_absolute() and '..' not in Path(path).parts and sha(g.raw(prepared,path))==h and sha((root/path).read_bytes())==h,'SOURCE_DRIFT_STOP')
    return Permit(p,'LIVE_REVIEWED',_SEAL)

def native(permit):require(type(permit) is Permit and permit.seal is _SEAL and permit.mode=='LIVE_REVIEWED','PARKED_NATIVE_IO_FORBIDDEN')

class SealedBox:
    """Direct binding to official libsodium crypto_box_seal, not homegrown crypto."""
    def __init__(self):
        name=ctypes.util.find_library('sodium');require(name is not None,'LIBSODIUM_REQUIRED_BEFORE_OAUTH')
        try:
            self.lib=ctypes.CDLL(name);self.lib.sodium_init.restype=ctypes.c_int
            self.lib.crypto_box_seal.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulonglong,ctypes.c_void_p];self.lib.crypto_box_seal.restype=ctypes.c_int
            require(self.lib.sodium_init()>=0,'LIBSODIUM_INIT_STOP')
        except Exception:raise Stop('LIBSODIUM_INIT_STOP') from None
    def encrypt(self,key,raw):
        require(type(key) is bytes and len(key)==32 and type(raw) is bytes and len(raw)<=32768,'ENCRYPT_INPUT_STOP')
        out=ctypes.create_string_buffer(len(raw)+48)
        require(self.lib.crypto_box_seal(out,raw,len(raw),key)==0,'SEALED_BOX_STOP')
        return base64.b64encode(out.raw).decode('ascii')

class FixedHTTP:
    offline_mock=False
    def __init__(self,permit,kind,token=None,*,connector=http.client.HTTPSConnection):
        native(permit);require(kind in ('github','google'),'HTTP_ROLE_STOP')
        if kind=='github':require(text(token),'WRITER_SECRET_MISSING_STOP')
        self.kind=kind;self._token=token;self.connector=connector;self.calls=0;self.poisoned=False;self.statuses=[]
    def __repr__(self):return '<FixedHTTP REDACTED>'
    def clear(self):self._token=None
    def __call__(self,method,path,body=None):
        require(not self.poisoned,'HTTP_UNKNOWN_NO_RETRY')
        if self.kind=='google':
            require(self.calls==0 and method=='POST' and path=='/token' and type(body) is bytes,'OAUTH_REQUEST_STOP')
            q=parse_qs(body.decode(),strict_parsing=True)
            require(set(q)=={'client_id','client_secret','code','grant_type','redirect_uri'} and q['grant_type']==['authorization_code'] and q['redirect_uri']==[REDIRECT] and all(len(v)==1 for v in q.values()),'OAUTH_FORM_STOP')
            host='oauth2.googleapis.com';data=body;headers={'Content-Type':'application/x-www-form-urlencoded'}
        else:
            seq=[('GET',PREFIX+CANDIDATE),('GET',PREFIX+'public-key'),('PUT',PREFIX+CANDIDATE)]
            require(self.calls<len(seq) and (method,path)==seq[self.calls],'GITHUB_SECRET_PATH_SEQUENCE_STOP')
            if method=='PUT':require(set(body)=={'encrypted_value','key_id'} and all(text(v) for v in body.values()),'SECRET_WRITE_BODY_STOP')
            host='api.github.com';data=None if body is None else json.dumps(body).encode();headers={'Authorization':'Bearer '+self._token,'Accept':'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'plm-oauth-reuse-once'}
        self.calls+=1;self.poisoned=True;c=self.connector(host,timeout=15)
        try:
            c.request(method,path,body=data,headers=headers);r=c.getresponse();s=r.status;self.statuses.append(s)
            if method=='PUT':return s,{} # never read write ACK/error body
            if s==404 and self.kind=='github' and self.calls==1:self.poisoned=False;return s,{}
            if s!=200:return s,{} # no error or redirect-body read
            raw=r.read(32769);require(len(raw)<=32768,'HTTP_RESPONSE_BOUND_STOP')
            d=duplicate_free(raw);require(isinstance(d,dict),'HTTP_RESPONSE_SHAPE_STOP');self.poisoned=False
            return s,d
        except Exception:raise Stop('HTTP_UNKNOWN_NO_RETRY') from None
        finally:c.close()

class SecretWriter:
    def __init__(self,transport,encryptor):self.t=transport;self.crypto=encryptor;self.ready=False;self.used=False;self.key=None;self.key_id=None
    def preflight(self):
        require(not self.used,'WRITER_ONCE_ONLY');self.used=True
        status,_=self.t('GET',PREFIX+CANDIDATE);require(status==404,'CANDIDATE_EXISTS_OR_ACCESS_UNKNOWN_STOP')
        status,d=self.t('GET',PREFIX+'public-key');require(status==200 and set(d)=={'key','key_id'} and text(d['key_id']),'REPOSITORY_KEY_STOP')
        try:key=base64.b64decode(d['key'],validate=True)
        except Exception:raise Stop('REPOSITORY_KEY_STOP') from None
        require(len(key)==32,'REPOSITORY_KEY_STOP');self.crypto.encrypt(key,b'');self.key=key;self.key_id=d['key_id'];self.ready=True
    def save(self,candidate):
        require(self.ready,'SECRET_SAVE_ONCE_ONLY');self.ready=False
        encrypted=self.crypto.encrypt(self.key,candidate)
        try:status,_=self.t('PUT',PREFIX+CANDIDATE,{'encrypted_value':encrypted,'key_id':self.key_id})
        except Exception:raise Stop('SECRET_WRITE_UNKNOWN_NO_RETRY') from None
        require(status==201,'SECRET_WRITE_UNKNOWN_NO_RETRY') # 204 is an unexpected overwrite, never success
        self.key=None;return True

class ExchangeExecutor:
    def __init__(self,permit,google,writer,clock=time.time):self.permit=permit;self.google=google;self.writer=writer;self.clock=clock;self.posts=0;self.write_attempted=False
    def run(self,load):
        p=self.permit;require(type(p) is Permit and p.seal is _SEAL and not p.used,'IDENTITY_CONSUMED_STOP');p.used=True
        if p.mode=='OFFLINE_CONTRACT':require(getattr(self.google,'offline_mock',False) is True and getattr(self.writer.t,'offline_mock',False) is True,'MOCK_ONLY_STOP')
        else:native(p)
        old=None;handoff=None;form=None;response=None;candidate=None
        try:
            try:old_raw=load(EXISTING);handoff_raw=load(HANDOFF)
            except Exception:raise Stop('SECRET_INPUT_MISSING_STOP') from None
            require(isinstance(old_raw,str) and isinstance(handoff_raw,str),'SECRET_INPUT_MISSING_STOP')
            old=parse(old_raw,('client_id','client_secret','refresh_token'));handoff=duplicate_free(handoff_raw)
            require(isinstance(handoff,dict) and set(handoff)=={'client_id','code','state','redirect_uri','issued_at'},'HANDOFF_SHAPE_STOP')
            require(old['client_id']==p.plan['client_id']==handoff['client_id'] and handoff['redirect_uri']==p.plan['redirect_uri']==REDIRECT and p.plan['scopes']==list(SCOPES),'CLIENT_REDIRECT_SCOPE_PIN_STOP')
            require(text(handoff['code']) and isinstance(handoff['state'],str) and __import__('hmac').compare_digest(handoff['state'],p.plan['consent_state']),'HANDOFF_CODE_STATE_STOP')
            require(type(handoff['issued_at']) is int and handoff['issued_at']<=self.clock()<handoff['issued_at']+300,'HANDOFF_LOCAL_WINDOW_STOP')
            self.writer.preflight() # absence/key/crypto dependency admission BEFORE sole token POST
            form=urlencode({'client_id':old['client_id'],'client_secret':old['client_secret'],'code':handoff['code'],'grant_type':'authorization_code','redirect_uri':REDIRECT}).encode()
            self.posts+=1
            try:status,response=self.google('POST','/token',form)
            except Exception:raise Stop('CODE_EXCHANGE_UNKNOWN_NO_RETRY') from None
            require(status==200 and isinstance(response,dict),'CODE_EXCHANGE_HTTP_STOP')
            require(text(response.get('refresh_token')) and text(response.get('access_token')),'NEW_REFRESH_TOKEN_MISSING_STOP')
            require(isinstance(response.get('scope'),str),'GRANTED_SCOPE_UNKNOWN_STOP')
            require(set(SCOPES)<=set(response['scope'].split()),'GRANTED_SCOPE_INSUFFICIENT_STOP')
            require(response.get('token_type','').lower()=='bearer' and type(response.get('expires_in')) is int and response['expires_in']>180,'TOKEN_RESPONSE_SHAPE_STOP')
            candidate=json.dumps({'client_id':old['client_id'],'refresh_token':response['refresh_token']},separators=(',',':')).encode()
            self.write_attempted=True;self.writer.save(candidate)
            return {'status':'CANDIDATE_SECRET_CREATE_ACKNOWLEDGED','basis':p.mode,'candidate_saved':True,'refresh_currently_valid':'NOT_TESTED','upload_scope':True,'readonly_scope':True,'channel_match':'UNVERIFIED','existing_secret_modified':False}
        finally:
            if isinstance(old,dict):old.clear()
            if isinstance(handoff,dict):handoff.clear()
            form=None;response=None;candidate=None;old_raw=None;handoff_raw=None

class CandidateOAuthTokenProvider:
    """Explicit V2 provider; no missing-candidate fallback, reuse old refresh code."""
    def __init__(self,load,send,clock,*,permit=None):
        if getattr(send,'offline_mock',False) is not True:
            from .authority import live_authority
            live_authority(permit);require(permit.operation in ('channel','private_upload','finalize'),'CANDIDATE_PROVIDER_ROLE_STOP')
        self.load=load;self.send=send;self.clock=clock;self.used=False
    def __repr__(self):return '<CandidateOAuthTokenProvider REDACTED>'
    def get_access_token(self):return self.refresh()['access_token']
    def refresh(self):
        require(not self.used,'CANDIDATE_PROVIDER_ONCE_ONLY');self.used=True
        try:
            old=self.load(EXISTING);new=self.load(CANDIDATE)
            require(new is not None,'CANDIDATE_SECRET_MISSING_STOP')
            bundle=combine_bundle(old,new,use_candidate=True)
            from ..evidence_adapters import MemoryOAuthRefresh
            return MemoryOAuthRefresh(bundle,self.send,self.clock,approved=True)()
        except Stop:raise
        except Exception:raise Stop('CANDIDATE_PROVIDER_STOP') from None
        finally:self.load=None

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--execute',action='store_true')
    for k in ('prepared','plan-sha','manifest-sha'):parser.add_argument('--'+k)
    args=parser.parse_args();clients=[];executor=None;out={'status':'PARKED','credentials_read':0,'oauth_POST':0,'secret_PUT':0};ready=False
    try:
        permit=local_gate(ROOT,os.environ,prepared=args.prepared,plan_sha=args.plan_sha,manifest_sha=args.manifest_sha)
        if permit is not None and args.prepare:ready=True;out={'status':'LOCAL_GATE_PASS','credentials_read':0,'oauth_POST':0,'secret_PUT':0}
        elif permit is not None and args.execute:
            token=os.environ.get(WRITER);crypto=SealedBox()
            github=FixedHTTP(permit,'github',token);google=FixedHTTP(permit,'google');clients=[github,google];token=None
            executor=ExchangeExecutor(permit,google,SecretWriter(github,crypto));out=executor.run(lambda name:os.environ.get(name))
    except Exception as e:
        reason=str(e) if isinstance(e,Stop) and re.fullmatch('[A-Z0-9_]{1,100}',str(e)) else 'FIXED_EXECUTION_STOP'
        out={'status':'UNKNOWN' if executor and (executor.posts or executor.write_attempted) else 'BLOCKED','reason_code':reason}
    finally:
        out['oauth_POST']=executor.posts if executor else 0
        out['secret_PUT']=int(executor.write_attempted) if executor else 0
        out['http_statuses']=[{'service':c.kind,'statuses':c.statuses} for c in clients]
        for c in clients:c.clear()
    if args.prepare and os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('ready='+str(ready).lower()+'\n')
    print(json.dumps(out,sort_keys=True))
    return 1 if out['status'] in ('BLOCKED','UNKNOWN') else 0
if __name__=='__main__':raise SystemExit(main())
