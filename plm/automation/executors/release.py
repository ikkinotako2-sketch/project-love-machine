"""Production release issuer: reviewed file + real local audit, never input flags.

Current reviewed records are PARKED. Offline orchestration cannot register live
permits, and presence of a Secret cannot turn a disabled record into permission.
"""
import hashlib,json,re
from dataclasses import dataclass
from pathlib import Path
from . import authority as a
from ..ledger import require,Stop
from ..execution_gate import SAFE
ROOT=Path(__file__).resolve().parents[3]
POLICY_PATH='readiness/execution-release-policy.json'
POLICY_SHA='920a26de854a910ea6b8c94fa9cda40865dc2232fee8b9a34e4cd9419fad027f'
_AUDIT_SEAL=object()

@dataclass(frozen=True)
class CheckedAudit:
    operation:str
    plan:dict
    event:dict
    prepared:str
    head:str
    marker_sha:str
    facts:dict
    seal:object
    root:str


def audited(root,*,operation,**pins):
    audit=a.ExecutorAudit(root)
    if operation in ('migration','migration_postcheck','worker_deploy','worker_postcheck'):audit.plan_path='readiness/cloudflare-transfer-plan.json'
    facts=audit.before_credentials(operation=operation,**pins)
    plan=json.loads(audit.raw(pins['prepared'],getattr(audit,'plan_path','readiness/executor-final-plan.json')))
    return CheckedAudit(operation,plan,pins['event'],pins['prepared'],pins['head'],pins['marker_sha'],facts,_AUDIT_SEAL,str(Path(root).resolve()))


def frozen_policy(root=ROOT):
    raw=(Path(root)/POLICY_PATH).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==POLICY_SHA,'RELEASE_POLICY_DRIFT_STOP')
    p=json.loads(raw);require(p['version']==1 and p['safe_flags']==SAFE,'RELEASE_POLICY_SHAPE_STOP')
    return p


def release_gate(operation,policy):
    require(operation in policy['releases'],'OPERATION_STOP')
    r=policy['releases'][operation]
    require(r['enabled'] is True and r['owner_approved'] is True,'PARKED_OPERATION_RELEASE_REQUIRED')
    require(r['environment_reviewed'] is True,'PROTECTED_ENVIRONMENT_UNVERIFIED')
    require(r['owner_exclusion_attested'] is True and r['reviewed_target_exact'] is True,'OPERATION_EXCLUSION_OR_TARGET_STOP')
    if operation=='channel':require(r['google_additional_consent_attested'] is True,'GOOGLE_OWNER_CONSENT_REQUIRED')
    if operation in ('state_init','private_upload','finalize','migration','worker_deploy'):
        require(r['budget_actual_verified'] is True,'ACTUAL_BUDGET_UNKNOWN_STOP')
        require(r['required_flags']['DRY_RUN'] is False and r['required_flags']['EMERGENCY_STOP'] is False,'EMERGENCY_OR_DRY_RUN_STOP')
    if operation in ('private_upload','finalize'):
        require(r['read_scope_verified'] is True and r['channel_match_verified'] is True,'REAL_SCOPE_CHANNEL_REQUIRED')
        require(r['budget_actual_verified'] is True,'ACTUAL_BUDGET_UNKNOWN_STOP')
        if operation=='finalize':require(r['callback_route_verified'] is True,'CALLBACK_ROUTE_UNVERIFIED_STOP')
    if operation.startswith('migration'):require(r['rest_batch_contract_verified'] is True,'REST_BATCH_CONTRACT_UNVERIFIED_STOP')
    if operation=='worker_deploy':require(r['rollback_evidence_verified'] is True,'ROLLBACK_EVIDENCE_REQUIRED')
    require(set(r['required_flags'])==set(SAFE) and all(type(v) is bool for v in r['required_flags'].values()),'OPERATION_FLAGS_SHAPE_STOP')
    return r


def issue_live(checked,*,prerequisites,policy,run_evidence):
    require(type(checked) is CheckedAudit and checked.seal is _AUDIT_SEAL,'REAL_LOCAL_AUDIT_REQUIRED')
    from .run_reader import RunEvidence,_RUN_SEAL
    require(type(run_evidence) is RunEvidence and run_evidence.seal is _RUN_SEAL and run_evidence.live is True and run_evidence.run_id==checked.event['run_id'] and run_evidence.head==checked.head and run_evidence.operation==checked.operation,'INDEPENDENT_LIVE_RUN_PROOF_REQUIRED')
    require(policy==frozen_policy(Path(checked.root)),'CALLER_POLICY_CANNOT_AUTHORIZE')
    record=release_gate(checked.operation,policy)
    require(record['prepared_commit']==checked.prepared and record['approved_marker_sha256']==checked.marker_sha,'APPROVAL_SNAPSHOT_BINDING_STOP')
    require(checked.event.get('safe_flags')==record['required_flags'],'OPERATION_FLAG_CONTEXT_STOP')
    spec=checked.plan['operations'][checked.operation]
    require(len(prerequisites)==len(spec['requires']),'PREREQUISITE_STOP')
    for name,r in zip(spec['requires'],prerequisites):
        require(type(r) is a.Receipt and r._seal is a._SEAL and r.basis=='LIVE_VERIFIED' and r.operation==name and r.identity==checked.plan['operations'][name]['identity'] and r.status==spec.get('required_statuses',{}).get(name,'ACKNOWLEDGED' if name=='private_upload' else 'VERIFIED'),'REAL_PREREQUISITE_REQUIRED')
        if name=='channel':
            from ..production_bridge import CHANNEL
            require(r.data.get('channel_id')==CHANNEL and r.data.get('readonly_scope') is True and r.data.get('upload_scope') is True and r.data.get('channel_match') is True,'REAL_CHANNEL_RECEIPT_STOP')
        if name=='state_init':
            from .channel_state import initial_sha
            require(r.data.get('state_branch')=='plm-execution-state-v2' and r.data.get('initial_state_sha256')==initial_sha(),'REAL_STATE_RECEIPT_STOP')
        if name=='private_upload':
            require(r.data.get('job_id')==checked.plan['job_id'] and r.data.get('media_sha256')==checked.plan['media_sha256'] and r.data.get('upload_state')=='ACKNOWLEDGED' and r.data.get('private') is True and r.data.get('notify_subscribers') is False,'REAL_UPLOAD_RECEIPT_STOP')
    permit=a.Permit(checked.operation,checked.plan,prerequisites,a._SEAL)
    permit.mode='LIVE_VERIFIED'
    a._LIVE_REGISTRY[id(permit)]=(permit,checked.head,checked.marker_sha)
    return permit


def revoke(permit):a._LIVE_REGISTRY.pop(id(permit),None)

class SecretScope:
    """Allowlisted memory-only lookup; no repr/log/file/hash of values."""
    def __init__(self,load,allowed):self.load=load;self.allowed=frozenset(allowed);self.values={};self.closed=False
    def __repr__(self):return '<SecretScope REDACTED>'
    def get(self,name):
        require(not self.closed and name in self.allowed,'SECRET_ROLE_STOP')
        if name not in self.values:
            try:value=self.load(name)
            except Exception:raise Stop('SECRET_LOOKUP_STOP') from None
            require(isinstance(value,str) and value and len(value)<=32768,'SECRET_MISSING_STOP')
            self.values[name]=value
        return self.values[name]
    def bundle(self):
        try:b=json.loads(self.get('PLM_YOUTUBE_GAME_001'))
        except Exception:raise Stop('OAUTH_SECRET_SHAPE_STOP') from None
        require(set(b)=={'client_id','client_secret','refresh_token'} and all(isinstance(v,str) and v and '\n' not in v and '\r' not in v for v in b.values()),'OAUTH_SECRET_SHAPE_STOP')
        return b
    def key(self,name):
        v=self.get(name)
        if re.fullmatch('[a-f0-9]{64}',v):return bytes.fromhex(v)
        require(32<=len(v)<=512 and all(32<ord(c)<127 for c in v) and not v.startswith(('PUBLIC_','FIXTURE')),'SIGNING_KEY_ENCODING_STOP')
        return v.encode()
    def clear(self):self.values.clear();self.load=None;self.closed=True
