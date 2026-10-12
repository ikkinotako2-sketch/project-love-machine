"""Bounded independent readers. No default network, ambient Secret or retry."""
import base64,hashlib,json,re,http.client
from .ledger import require,Stop
from .strict_upload import CHANNEL,ChannelSession
from .production_bridge import scope_gate
REPO='ikkinotako2-sketch/project-love-machine'
RUN=re.compile('[1-9][0-9]{0,19}')
SHA=re.compile('[a-f0-9]{40}')

class HTTPSReader:
    """Future GET-only bearer transport; approval explicit, values memory-only.
    Redirects/errors are returned as status only; error bodies are never read.
    """
    def __init__(self,host,token,*,approved=False,maximum=1,connector=http.client.HTTPSConnection):
        require(approved is True and host in ('api.github.com','www.googleapis.com') and isinstance(token,str) and token and '\n' not in token and '\r' not in token and type(maximum) is int and 0<maximum<=6,'READ_APPROVAL_REQUIRED')
        self.host=host;self.token=token;self.maximum=maximum;self.calls=0;self.connector=connector;self.poisoned=False
    def __repr__(self):return '<HTTPSReader REDACTED>'
    def clear(self):self.token=None
    def __call__(self,path):
        require(not self.poisoned and self.token and self.calls<self.maximum and path.startswith('/') and not any(x in path for x in ['access_token','refresh_token','client_secret','://']),'READ_PATH_STOP')
        if self.host=='www.googleapis.com':require(re.fullmatch(r'/youtube/v3/(channels\?part=id&mine=true&maxResults=50|videos\?part=id,snippet,status,processingDetails&id=[A-Za-z0-9_-]{11})',path),'YOUTUBE_PATH_STOP')
        else:require(path.startswith('/repos/'+REPO+'/') and '..' not in path,'GITHUB_PATH_STOP')
        self.calls+=1;self.poisoned=True;c=self.connector(self.host,timeout=15)
        try:
            c.request('GET',path,headers={'Authorization':'Bearer '+self.token,'Accept':'application/json','User-Agent':'plm-bounded-proof'})
            r=c.getresponse()
            if r.status!=200:return r.status,{}
            raw=r.read(65537);require(len(raw)<=65536,'RESPONSE_BOUND_STOP')
            d=json.loads(raw);self.poisoned=False;return 200,d
        except Exception:raise Stop('READ_TRANSPORT_UNKNOWN_NO_RETRY') from None
        finally:c.close()

class GitHubProvenance:
    maximum_gets=6
    def __init__(self,get):self.get=get;self.used=False
    def verify(self,expected,*,phase='completed'):
        require(not self.used,'PROVENANCE_ONCE_ONLY');self.used=True
        e=expected
        require(e['repository']==REPO and RUN.fullmatch(str(e['run_id'])) and SHA.fullmatch(e['commit']) and SHA.fullmatch(e['prepared_commit']) and e['attempt']==1 and type(e['attempt']) is int,'PROVENANCE_EXPECTATION_STOP')
        require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,95}',e['identity']) and e['marker_path']=='audit-evidence/consumed/'+e['identity']+'.json' and e['workflow_path'].startswith('.github/workflows/') and '..' not in e['workflow_path'] and e['workflow_path'].endswith('.yml'),'PROVENANCE_PATH_STOP')
        def get(path):
            status,d=self.get('/repos/'+REPO+path);require(status==200 and isinstance(d,dict),'PROVENANCE_HTTP_STOP');return d
        run=get('/actions/runs/'+str(e['run_id']))
        require(run.get('repository',{}).get('full_name')==REPO and str(run.get('id'))==str(e['run_id']) and run.get('run_attempt')==1 and type(run.get('run_attempt')) is int and run.get('head_sha')==e['commit'] and run.get('head_branch')==e['branch'] and run.get('path')==e['workflow_path'] and run.get('event')=='push','RUN_BINDING_STOP')
        require(phase in ('before_upload','completed'),'PROVENANCE_PHASE_STOP')
        require((run.get('status')=='completed' and run.get('conclusion')=='success') if phase=='completed' else (run.get('status')=='in_progress' and run.get('conclusion') is None),'RUN_NOT_SUCCESS_STOP')
        jobs=get('/actions/runs/'+str(e['run_id'])+'/jobs?per_page=100')
        require(type(jobs.get('total_count')) is int and jobs['total_count']==len(jobs.get('jobs',[])) and 0<jobs['total_count']<=100,'JOB_INVENTORY_STOP')
        matching=[x for x in jobs['jobs'] if x.get('name')==e['job_name'] and (x.get('conclusion')=='success' if phase=='completed' else x.get('status')=='in_progress') and x.get('run_id')==int(e['run_id'])]
        require(len(matching)==1,'JOB_BINDING_STOP')
        artifact_run=e.get('artifact_run_id',e['run_id']);artifact_commit=e.get('artifact_commit',e['commit'])
        require(RUN.fullmatch(str(artifact_run)) and SHA.fullmatch(artifact_commit),'ARTIFACT_ORIGIN_STOP')
        artifacts=get('/actions/runs/'+str(artifact_run)+'/artifacts?per_page=100')
        require(artifacts.get('total_count')==len(artifacts.get('artifacts',[])) and artifacts['total_count']<=100,'ARTIFACT_INVENTORY_STOP')
        a=[a for a in artifacts['artifacts'] if a.get('id')==e['artifact_id']]
        require(len(a)==1 and a[0].get('expired') is False and a[0].get('digest')=='sha256:'+e['artifact_archive_sha256'] and a[0].get('workflow_run',{}).get('head_sha')==artifact_commit and str(a[0].get('workflow_run',{}).get('id'))==str(artifact_run),'ARTIFACT_BINDING_STOP')
        def content(path):
            d=get('/contents/'+path+'?ref='+e['commit']);require(d.get('encoding')=='base64','CONTENT_SHAPE_STOP');raw=base64.b64decode(d['content']);require(len(raw)<=65536,'CONTENT_BOUND_STOP');return raw
        marker_raw=content(e['marker_path']);require(hashlib.sha256(marker_raw).hexdigest()==e['marker_sha256'],'MARKER_HASH_STOP');marker=json.loads(marker_raw)
        require(marker.get('identity')==e['identity'] and marker.get('job_id')==e['job_id'] and marker.get('state')=='CONSUMED_BEFORE_REMOTE' and marker.get('prepared_commit_sha')==e['prepared_commit'] and marker.get('media_sha256')==e['media_sha256'],'MARKER_JOB_STOP')
        approval_field=e.get('approval_field','upload_approved');require(approval_field in ('upload_approved','finalize_approved') and marker.get(approval_field) is True,'MARKER_APPROVAL_STOP')
        require(hashlib.sha256(content(e['workflow_path'])).hexdigest()==e['workflow_sha256'],'WORKFLOW_SHA_STOP')
        commit=get('/commits/'+e['commit'])
        require([x.get('sha') for x in commit.get('parents',[])]==[e['prepared_commit']] and len(commit.get('files',[]))==1 and commit['files'][0].get('filename')==e['marker_path'] and commit['files'][0].get('status')=='added','MARKER_ONLY_HISTORY_STOP')
        return {'verified':True,'phase':phase,'run_id':str(e['run_id']),'run_attempt':1,'workflow_sha256':e['workflow_sha256'],'job_id':e['job_id'],'identity':e['identity'],'media_sha256':e['media_sha256'],'commit':e['commit'],'proof_basis':'INDEPENDENT_GITHUB_API','completion_known_ack_required':True}

class ProcessedReadback:
    maximum_gets=1
    def __init__(self,get,*,approved=False,read_scope_proven=False):self.get=get;self.approved=approved;self.scope=read_scope_proven;self.used=False
    def verify(self,video,job):
        require(self.approved is True and self.scope is True and not self.used and re.fullmatch('[A-Za-z0-9_-]{11}',video),'READBACK_APPROVAL_SCOPE_STOP');self.used=True
        try:
            status,d=self.get('/youtube/v3/videos?part=id,snippet,status,processingDetails&id='+video)
            require(status==200 and isinstance(d,dict) and d.get('kind')=='youtube#videoListResponse' and len(d.get('items',[]))==1 and not d.get('nextPageToken'),'READBACK_UNKNOWN')
            v=d['items'][0]
            require(v.get('id')==video and v.get('snippet',{}).get('channelId')==CHANNEL and v.get('status',{}).get('privacyStatus')=='private' and v.get('status',{}).get('uploadStatus')=='processed' and v.get('processingDetails',{}).get('processingStatus')=='succeeded','READBACK_UNKNOWN')
        except Exception:raise Stop('READBACK_UNKNOWN_NO_REUPLOAD') from None
        return {'job_id':job,'video_id':video,'processed':True,'private':True,'channel_id':CHANNEL,'proof_basis':'INDEPENDENT_READBACK'}

class GitHubCompletionAuthority:
    """Cross-run ACK-loss fence. Both upload and coordinator must be SUCCESS.
    Coordinator expectations come from a frozen separately approved manifest.
    A failed/UNKNOWN coordinator cannot be bypassed by a stored Done record.
    """
    def __init__(self,get,coordinator_expected):self.get=get;self.coordinator_expected=coordinator_expected
    def __call__(self,row):
        try:
            e=row['provenance_expected'];p=GitHubProvenance(self.get).verify(e)
            require(p['job_id']==row['job_id'] and p['identity']==row['identity'] and p['run_id']==str(row['run_id']),'UPLOAD_COMPLETION_ID_STOP')
            if row['state']=='Done':
                run=str(row['continuation']['coordinator_run_id']);require(run!=str(row['run_id']),'INDEPENDENT_COORDINATOR_REQUIRED')
                ce=self.coordinator_expected(copy_dict(row));require(str(ce['run_id'])==run and ce['job_id']==row['job_id'] and ce.get('approval_field')=='finalize_approved','COORDINATOR_BINDING_STOP')
                cp=GitHubProvenance(self.get).verify(ce);require(cp['job_id']==row['job_id'],'COORDINATOR_JOB_STOP')
            return True
        except Exception:return False

def copy_dict(value):return json.loads(json.dumps(value))

class FreshChannel:
    maximum_refresh_posts=1
    maximum_channel_gets=1
    def __init__(self,refresh,get_for_token,clock):self.refresh=refresh;self.get_for_token=get_for_token;self.clock=clock;self.used=False
    def create(self):
        require(not self.used,'CHANNEL_SESSION_ONCE_ONLY');self.used=True
        # refresh adapter must return only memory data; no ambient Secret reads.
        bundle=self.refresh();scope_gate(bundle.get('scopes'),bundle.get('scope_proven'))
        token=bundle['access_token'];status,body=self.get_for_token(token)('/youtube/v3/channels?part=id&mine=true&maxResults=50')
        session=ChannelSession.from_mine_response(token,status,json.dumps(body).encode(),bundle['expires_at'],self.clock)
        return session

class MemoryOAuthRefresh:
    """Reuse legacy provider with injected bundle/opener; no environment reads.
    A Stop replaces any HTTPError before the legacy error-body reader is reached.
    """
    maximum_posts=1
    def __init__(self,bundle,send,clock,*,approved=False):self.bundle=bundle;self.send=send;self.clock=clock;self.approved=approved;self.used=False
    def __repr__(self):return '<MemoryOAuthRefresh REDACTED>'
    def __call__(self):
        from plm.social_adapters.youtube.oauth import EnvironmentOAuthTokenProvider
        require(self.approved is True and not self.used,'OAUTH_REFRESH_APPROVAL_STOP');self.used=True
        scope={};bundle=self.bundle;self.bundle=None
        require(isinstance(bundle,dict) and set(bundle)=={'client_id','client_secret','refresh_token'} and all(isinstance(v,str) and v and '\n' not in v and '\r' not in v for v in bundle.values()),'SECRET_SHAPE_STOP')
        send=self.send
        class Response:
            def __init__(self,raw):self.raw=raw
            def __enter__(self):return self
            def __exit__(self,*args):self.raw=None
            def read(self):return self.raw
        def opener(request,timeout):
            require(request.full_url==EnvironmentOAuthTokenProvider.TOKEN_URL and request.get_method()=='POST' and timeout==30,'OAUTH_REQUEST_STOP')
            try:status,p=send(request.data)
            except Exception:raise Stop('OAUTH_TRANSPORT_UNKNOWN_NO_RETRY') from None
            require(status==200 and isinstance(p,dict),'OAUTH_HTTP_STOP')
            require(type(p.get('expires_in')) is int and p['expires_in']>180 and p.get('token_type','').lower()=='bearer' and isinstance(p.get('scope'),str),'OAUTH_SCOPE_OR_EXPIRY_UNKNOWN')
            scope['scopes']=p['scope'].split();scope_gate(scope['scopes'],True)
            # Token response remains memory-only and is not returned to any logger.
            return Response(json.dumps({'access_token':p.get('access_token'),'expires_in':p['expires_in']}).encode())
        class Provider(EnvironmentOAuthTokenProvider):
            def _load_bundle(self):return bundle
        provider=Provider(opener=opener,clock=self.clock)
        try:
            token=provider.get_access_token()
            require(isinstance(token,str) and 0<len(token)<=16384 and all(32<ord(c)<127 for c in token),'TOKEN_SHAPE_STOP')
            return {'access_token':token,'expires_at':provider._expires_at,'scopes':scope['scopes'],'scope_proven':True}
        except Stop:raise
        except Exception:raise Stop('OAUTH_RESPONSE_STOP') from None
        finally:provider._token=None;bundle=None

class OAuthPostTransport:
    """Future sole OAuth POST; fixed host/path/form, redirect/retry/error-body0."""
    def __init__(self,*,approved=False,connector=http.client.HTTPSConnection):require(approved is True,'OAUTH_POST_NOT_APPROVED');self.connector=connector;self.used=False
    def __call__(self,form):
        from urllib.parse import parse_qs
        require(not self.used and isinstance(form,bytes) and len(form)<=32768,'OAUTH_POST_POLICY_STOP');self.used=True
        fields=parse_qs(form.decode(),strict_parsing=True)
        require(set(fields)=={'client_id','client_secret','refresh_token','grant_type'} and fields['grant_type']==['refresh_token'] and all(len(v)==1 for v in fields.values()),'OAUTH_FORM_STOP')
        c=self.connector('oauth2.googleapis.com',timeout=30)
        try:
            c.request('POST','/token',body=form,headers={'Content-Type':'application/x-www-form-urlencoded'})
            r=c.getresponse()
            if r.status!=200:return r.status,{}
            raw=r.read(32769);require(len(raw)<=32768,'OAUTH_BODY_BOUND_STOP');return 200,json.loads(raw)
        except Exception:raise Stop('OAUTH_TRANSPORT_UNKNOWN') from None
        finally:c.close()
