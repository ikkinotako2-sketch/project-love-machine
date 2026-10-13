"""Real API adapters behind an unreachable live capability boundary.

Conformance fakes are passed to executor kernels separately, never to these
constructors. No live credential loading, retries, redirects or error-body reads.
"""
import base64,hashlib,http.client,json,re
from .authority import live_authority
from ..ledger import require,Stop
from ..shared_lifecycle import GitContentsCAS
from ..strict_upload import HttpsSingleSend
from ..evidence_adapters import OAuthPostTransport,HTTPSReader
REPO='ikkinotako2-sketch/project-love-machine'
PREFIX='/repos/'+REPO
REF=PREFIX+'/git/ref/heads/'+GitContentsCAS.BRANCH
REFS=PREFIX+'/git/refs'
STATE=GitContentsCAS.PATH

class StateInitHTTP:
    offline_mock=False
    def __init__(self,token,permit,*,connector=http.client.HTTPSConnection):
        live_authority(permit);require(permit.operation=='state_init','STATE_INIT_ROLE_STOP')
        require(isinstance(token,str) and 0<len(token)<=16384 and all(32<ord(c)<127 for c in token),'TOKEN_SHAPE_STOP')
        self._token=token;self.connector=connector;self.calls={'GET':0,'POST':0,'PUT':0};self.poisoned=False;self.statuses=[]
    def __repr__(self):return '<StateInitHTTP REDACTED>'
    def clear(self):self._token=None
    def __call__(self,method,path,body=None):
        require(not self.poisoned and self._token and method in self.calls,'STATE_IO_STOP')
        limits={'GET':2,'POST':1,'PUT':1}
        require(self.calls[method]<limits[method],'STATE_BUDGET_STOP')
        require((method=='GET' and path in (REF,STATE+'?ref='+GitContentsCAS.BRANCH)) or
                (method=='POST' and path==REFS and set(body)=={'ref','sha'} and body['ref']=='refs/heads/'+GitContentsCAS.BRANCH and re.fullmatch('[a-f0-9]{40}',body['sha'])) or
                (method=='PUT' and path==STATE and set(body)=={'branch','message','content'} and body['branch']==GitContentsCAS.BRANCH),'STATE_TARGET_OR_OVERWRITE_STOP')
        if method=='PUT':
            from .channel_state import initial_bytes
            require(body['message']=='PLM initialize shared lifecycle once','STATE_MESSAGE_STOP')
            try:raw=base64.b64decode(body['content'],validate=True)
            except Exception:raise Stop('STATE_CONTENT_SHAPE_STOP') from None
            require(raw==initial_bytes(),'STATE_INITIAL_CONTENT_STOP')
        self.calls[method]+=1;self.poisoned=True
        c=self.connector('api.github.com',timeout=15)
        try:
            c.request(method,path,body=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+self._token,'Accept':'application/vnd.github+json','Content-Type':'application/json','User-Agent':'plm-state-init-once'})
            r=c.getresponse();self.statuses.append(r.status)
            if r.status not in (200,201):
                if method=='GET' and r.status==404:self.poisoned=False
                return r.status,{}
            raw=r.read(65537);require(len(raw)<=65536,'RESPONSE_BOUND_STOP')
            d=json.loads(raw);require(isinstance(d,dict),'RESPONSE_SHAPE_STOP');self.poisoned=False
            return r.status,d
        except Exception:raise Stop('STATE_TRANSPORT_UNKNOWN_NO_RETRY') from None
        finally:c.close()


def channel_transports(permit,bundle,clock,observer=None):
    live_authority(permit);require(permit.operation in ('channel','private_upload','finalize'),'CHANNEL_ROLE_STOP')
    from ..evidence_adapters import MemoryOAuthRefresh,FreshChannel
    post=OAuthPostTransport(approved=True)
    def send(form):
        if observer:observer('OAuth','POST',None)
        status,payload=post(form)
        if observer:observer('OAuth',None,status)
        return status,payload
    def reader(token):
        native=HTTPSReader('www.googleapis.com',token,approved=True,maximum=1)
        def get(path):
            if observer:observer('YouTube','GET',None)
            try:
                status,payload=native(path)
                if observer:observer('YouTube',None,status)
                return status,payload
            finally:native.clear()
        return get
    refresh=MemoryOAuthRefresh(bundle,send,clock,approved=True)
    return FreshChannel(refresh,reader,clock)


def strict_upload_transport(permit):
    live_authority(permit);require(permit.operation=='private_upload','UPLOAD_ROLE_STOP')
    return HttpsSingleSend(operation_approved=True)


def proof_transport(permit,token,*,maximum=6):
    live_authority(permit)
    return HTTPSReader('api.github.com',token,approved=True,maximum=maximum)


def readback_transport(permit,token):
    live_authority(permit);require(permit.operation=='finalize','READBACK_ROLE_STOP')
    return HTTPSReader('www.googleapis.com',token,approved=True,maximum=1)


def lifecycle_backend(permit,token):
    live_authority(permit);require(permit.operation in ('private_upload','finalize'),'STATE_ROLE_STOP')
    from ..state_transport import StateHTTPTransport
    return GitContentsCAS(StateHTTPTransport(token,approved=True,max_gets=1,max_puts=6))


def callback_transport(permit,send,context,checkpoint,key,key_id,*,origin,clock,dispatch_key):
    live_authority(permit);require(permit.operation=='finalize','CALLBACK_ROLE_STOP')
    from ..live_factory import CallbackOnce
    return CallbackOnce(send,context,checkpoint,key,key_id,origin=origin,approved=True,clock=clock,dispatch_key=dispatch_key)


def processed_reader(permit,token):
    live_authority(permit)
    from ..evidence_adapters import ProcessedReadback
    return ProcessedReadback(readback_transport(permit,token),approved=True,read_scope_proven=True)
