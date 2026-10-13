"""Separate simulation and reviewed production operation capabilities.

A dictionary, flag or mock receipt cannot grant production I/O. Real transports
require registered LIVE_VERIFIED authority. All current release records are disabled.
"""
import copy,json,re
from dataclasses import dataclass
from pathlib import Path
from ..execution_gate import GitAudit,load_pinned_plan,local_event_gate,digest,MARKER_KEYS,SHA,HASH
from ..ledger import require,Stop

_SEAL=object()
_LIVE_REGISTRY={}
@dataclass(frozen=True)
class Receipt:
    operation:str
    identity:str
    basis:str
    status:str
    data:dict
    _seal:object
    def public(self):return {'operation':self.operation,'identity':self.identity,'basis':self.basis,'status':self.status,**copy.deepcopy(self.data)}

class Permit:
    __slots__=('operation','identity','mode','spec','plan','prerequisites','used','_seal')
    def __init__(self,operation,plan,prerequisites,seal):
        require(seal is _SEAL,'PERMIT_NOT_AUTHORIZED')
        self.operation=operation;self.identity=plan['operations'][operation]['identity']
        self.mode='OFFLINE_CONTRACT';self.spec=copy.deepcopy(plan['operations'][operation]);self.plan=copy.deepcopy(plan)
        self.prerequisites=tuple(prerequisites);self.used=False;self._seal=seal
    def __repr__(self):return '<OperationPermit '+self.operation+' OFFLINE_ONLY>'
    def begin(self,operation):
        require(type(self) is Permit and self._seal is _SEAL and self.mode in ('OFFLINE_CONTRACT','LIVE_VERIFIED') and self.operation==operation and not self.used,'OPERATION_APPROVAL_STOP')
        if self.mode=='LIVE_VERIFIED':live_authority(self)
        self.used=True
    def receipt(self,status,data):
        require(self.used and status in ('VERIFIED','ACKNOWLEDGED','Done'),'RECEIPT_STATUS_STOP')
        return Receipt(self.operation,self.identity,self.mode,status,copy.deepcopy(data),_SEAL)

class OfflineAuthority:
    """Only a simulation issuer. Its results can never authorize a real transport."""
    def __init__(self,plan):self.plan=copy.deepcopy(plan);self.issued=set()
    def issue(self,operation,*,prerequisites=(),approved=False,marker_consumed=False,attempt=1):
        require(approved is True and marker_consumed is True and type(attempt) is int and attempt==1,'OFFLINE_APPROVAL_FIXTURE_REQUIRED')
        require(operation in self.plan['operations'],'OPERATION_STOP')
        spec=self.plan['operations'][operation]
        require(spec['identity'] not in self.issued,'IDENTITY_ALREADY_CONSUMED')
        require(len(prerequisites)==len(spec['requires']),'PREREQUISITE_STOP')
        for required,receipt in zip(spec['requires'],prerequisites):
            require(type(receipt) is Receipt and receipt._seal is _SEAL and receipt.basis=='OFFLINE_CONTRACT' and receipt.status==spec.get('required_statuses',{}).get(required,'ACKNOWLEDGED' if required=='private_upload' else 'VERIFIED') and receipt.operation==required and receipt.identity==self.plan['operations'][required]['identity'],'PREREQUISITE_STOP')
        self.issued.add(spec['identity'])
        return Permit(operation,self.plan,prerequisites,_SEAL)


def start(permit,operation):
    require(type(permit) is Permit,'OPERATION_APPROVAL_STOP');permit.begin(operation)


def offline_adapter(adapter):
    require(getattr(adapter,'offline_mock',False) is True,'MOCK_CANNOT_AUTHORIZE_REAL_IO')
    return adapter


def adapter_for(permit,adapter):
    require(type(permit) is Permit,'OPERATION_APPROVAL_STOP')
    if permit.mode=='OFFLINE_CONTRACT':return offline_adapter(adapter)
    live_authority(permit)
    require(getattr(adapter,'offline_mock',False) is not True,'MOCK_NOT_PRODUCTION_EVIDENCE')
    return adapter

def live_authority(permit):
    require(type(permit) is Permit and permit._seal is _SEAL and permit.mode=='LIVE_VERIFIED','PARKED_REAL_IO_FORBIDDEN')
    entry=_LIVE_REGISTRY.get(id(permit))
    require(entry is not None and entry[0] is permit,'PARKED_REAL_IO_FORBIDDEN')
    return True

class ExecutorAudit(GitAudit):
    """Credential-free real local history/source checks for a future marker commit."""
    def before_credentials(self,*,event,prepared,head,plan_sha,manifest_sha,marker_sha,operation):
        require(SHA.fullmatch(prepared) and SHA.fullmatch(head),'COMMIT_STOP')
        plan_path=getattr(self,'plan_path','readiness/executor-final-plan.json')
        raw=self.raw(prepared,plan_path)
        plan=load_pinned_plan(raw,plan_sha);local_event_gate(event,plan)
        require(event.get('sha')==head and re.fullmatch('[1-9][0-9]{0,19}',str(event.get('run_id',''))),'EXECUTION_RUN_SHA_STOP')
        facts=self.preparation(plan,prepared)
        require(self.git('rev-parse','HEAD').decode().strip()==head and self.git('status','--porcelain')==b'','WORKTREE_STOP')
        require(self.git('show','-s','--format=%P',head).decode().strip()==prepared,'MARKER_ONLY_HISTORY_STOP')
        op=plan['operations'][operation];path=op['marker_path']
        require(self.git('show','-s','--format=%s',head).decode().strip()=='PLM executor once '+op['identity'],'MARKER_MESSAGE_STOP')
        require(self.git('diff','--name-status',prepared+'..'+head).decode().splitlines()==['A\t'+path],'MARKER_ONLY_HISTORY_STOP')
        marker_raw=self.raw(head,path);require(HASH.fullmatch(marker_sha) and digest(marker_raw)==marker_sha,'MARKER_HASH_STOP')
        def pairs(xs):
            out={}
            for k,v in xs:require(k not in out,'DUPLICATE_JSON_STOP');out[k]=v
            return out
        try:m=json.loads(marker_raw,object_pairs_hook=pairs)
        except Exception:raise Stop('MARKER_SHAPE_STOP') from None
        require(set(m)==MARKER_KEYS|{'job_id','media_sha256','upload_approved','finalize_approved'} and m['identity']==op['identity'] and m['operation']==operation and m['state']=='CONSUMED_BEFORE_REMOTE' and m['approved'] is True and m['prepared_commit_sha']==prepared,'MARKER_CONTRACT_STOP')
        require(m['job_id']==plan['job_id'] and m['media_sha256']==plan['media_sha256'] and m['upload_approved'] is (operation=='private_upload') and m['finalize_approved'] is (operation=='finalize'),'MARKER_OPERATION_APPROVAL_STOP')
        paths={'plan_sha256':plan_path,'source_manifest_sha256':plan['source_manifest'],'workflow_sha256':op['workflow_path'],'executor_sha256':op['executor_path'],'schema_sha256':plan['schema_path']}
        for key,p in paths.items():require(m[key]==digest(self.raw(prepared,p)),'MARKER_PIN_STOP')
        manifest_raw=self.raw(prepared,plan['source_manifest']);require(digest(manifest_raw)==manifest_sha,'SOURCE_MANIFEST_PIN_STOP')
        for p,h in json.loads(manifest_raw)['source_sha256'].items():
            require(digest(self.raw(prepared,p))==h and digest((self.root/p).read_bytes())==h,'SOURCE_DRIFT_STOP')
        return {**facts,'marker_exact':True,'credential_permission':False,'live_enabled':False}


def production_entry(operation,*,credentials_loader=None,**claims):
    # No inputs, environment flags, bearer or marker can release current build.
    require(operation in ('channel','state_init','private_upload','finalize'),'OPERATION_STOP')
    return {'status':'PARKED_OWNER_READ_SCOPE_AND_SEPARATE_APPROVAL_REQUIRED','operation':operation,'credentials_read':0,'requests':0,'state_writes':0,'markers_created':0}
