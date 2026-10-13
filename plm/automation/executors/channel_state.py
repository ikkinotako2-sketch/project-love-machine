"""Separate channel/session and create-if-absent State initialization kernels."""
import base64,hashlib,json,re
from .authority import start,adapter_for
from .transports import REF,REFS,STATE
from ..ledger import require,Stop
from ..production_bridge import CHANNEL
from ..shared_lifecycle import initial,GitContentsCAS

def initial_bytes():return (json.dumps(initial(),sort_keys=True,separators=(',',':'))+'\n').encode()
def initial_sha():return hashlib.sha256(initial_bytes()).hexdigest()
def blob_sha(raw):return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()

class ChannelExecutor:
    def __init__(self,fresh):self.fresh=fresh
    def run(self,permit):
        start(permit,'channel');adapter_for(permit,self.fresh);session=None
        try:
            # FreshChannel uses MemoryOAuthRefresh/provider and same bearer mine GET.
            session=self.fresh.create()
            require(session.channel==CHANNEL,'CHANNEL_MISMATCH_STOP')
            session.token() # expiry validation; never returned/logged/stored
            return permit.receipt('VERIFIED',{'channel_id':CHANNEL,'upload_scope':True,
                'readonly_scope':True,'channel_match':True,'oauth_refresh_POST_max':1,'channels_GET_max':1})
        except Exception:raise Stop('CHANNEL_VERIFICATION_STOP_NO_RETRY') from None
        finally:
            if session is not None:session.clear()

class StateInitExecutor:
    """GET ref; optional create-ref POST; GET Contents; one create-only PUT.
    No sha field on PUT means an existing file is never overwritten. Ref ACK and
    Contents blob/parent ACK are both exact; UNKNOWN never probes or writes again.
    """
    def __init__(self,transport):
        self.transport=transport;self.used=False;self.uncertain=False;self.calls=[]
    def request(self,method,path,body=None):
        require(not self.uncertain,'STATE_UNKNOWN_NO_MORE_IO');self.uncertain=True
        require(method in ('GET','POST','PUT') and sum(1 for m,_ in self.calls if m==method)<{'GET':2,'POST':1,'PUT':1}[method],'STATE_REQUEST_BUDGET_STOP')
        require((method=='GET' and path in (REF,STATE+'?ref='+GitContentsCAS.BRANCH)) or (method=='POST' and path==REFS) or (method=='PUT' and path==STATE),'STATE_TARGET_STOP')
        self.calls.append((method,path))
        try:status,p=self.transport(method,path,body)
        except Exception:raise Stop('STATE_INIT_UNKNOWN_NO_RETRY') from None
        require(type(status) is int and isinstance(p,dict),'STATE_INIT_UNKNOWN_NO_RETRY')
        if status not in (200,201,404):raise Stop('STATE_INIT_HTTP_STOP_NO_RETRY')
        self.uncertain=False;return status,p
    def run(self,permit):
        try:return self._run(permit)
        except Exception:
            self.uncertain=True
            raise Stop('STATE_INIT_STOP_NO_RETRY') from None
    def _run(self,permit):
        start(permit,'state_init');adapter_for(permit,self.transport);require(not self.used,'STATE_INIT_CONSUMED');self.used=True
        spec=permit.spec;expected=spec['state_base_commit']
        require(re.fullmatch('[a-f0-9]{40}',expected) and initial_sha()==spec['initial_state_sha256'],'INITIAL_STATE_SOURCE_STOP')
        raw=initial_bytes();status,p=self.request('GET',REF)
        if status==404:
            require(spec['create_branch_if_absent'] is True,'STATE_BRANCH_NOT_INITIALIZED')
            status,p=self.request('POST',REFS,{'ref':'refs/heads/'+GitContentsCAS.BRANCH,'sha':expected})
            require(status==201,'STATE_BRANCH_CONFLICT_STOP')
        require(status in (200,201) and p.get('ref')=='refs/heads/'+GitContentsCAS.BRANCH and p.get('object',{}).get('type')=='commit' and p['object'].get('sha')==expected,'STATE_BRANCH_DRIFT_STOP')
        status,p=self.request('GET',STATE+'?ref='+GitContentsCAS.BRANCH)
        require(status==404,'EXISTING_STATE_NEVER_OVERWRITE')
        # The write is marked uncertain before send; a lost ACK is permanent STOP.
        status,p=self.request('PUT',STATE,{'branch':GitContentsCAS.BRANCH,'message':'PLM initialize shared lifecycle once','content':base64.b64encode(raw).decode()})
        self.uncertain=True
        require(status==201 and p.get('content',{}).get('path')=='automation-state/lifecycle.json' and p['content'].get('sha')==blob_sha(raw) and re.fullmatch('[a-f0-9]{40}',str(p.get('commit',{}).get('sha',''))) and [x.get('sha') for x in p['commit'].get('parents',[])]==[expected],'STATE_INIT_ACK_UNKNOWN_NO_RETRY')
        self.uncertain=False
        return permit.receipt('VERIFIED',{'state_branch':GitContentsCAS.BRANCH,
            'state_path':'automation-state/lifecycle.json','initial_state_sha256':initial_sha(),
            'initial_blob_sha':blob_sha(raw),'state_commit':p['commit']['sha'],'overwritten':False})
