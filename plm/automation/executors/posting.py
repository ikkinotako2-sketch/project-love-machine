"""Private upload ACK phase and separately approved processed-finalize phase.

This wires real candidate components. Only fixture adapters are reachable in
this build; production entry/real transport authority remain unconditionally off.
"""
import copy,hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path
from .authority import start,adapter_for
from .lifecycle import ExecutorLifecycle
from ..ledger import require,Stop
from ..production_bridge import CHANNEL,MEDIA,media_gate,digest,scope_gate
from ..strict_upload import StrictUploader
from ..render_contract import render_gate
from ..quota_contract import budget_gate
from ..evidence_adapters import GitHubProvenance,ProcessedReadback
from ..live_factory import CandidateFactory
from ..content_adapters import MetricsAdapter
ROOT=Path(__file__).resolve().parents[3]
JOB_ID='plm-private-channel-recovery-20261012-r1'
ARTIFACT=11746833809
ARCHIVE='1f741c38d667267d4713bbbeb67b2645308336cbb9876aa4616d5710460bb61d'
RENDER_COMMIT='4b881ed39a867769f99613327c6c7653b152c7f0'

class RunProofAdapter:
    """Reuse independent six-GET reader; also enforce exact artifact expiry/origin."""
    def __init__(self,get,clock):self.get=get;self.clock=clock;self.used=False
    def verify(self,expected,*,phase,permit):
        try:return self._verify(expected,phase=phase,permit=permit)
        except Exception:raise Stop('INDEPENDENT_PROVENANCE_STOP_NO_RETRY') from None
    def _verify(self,expected,*,phase,permit):
        adapter_for(permit,self.get)
        require(not self.used,'PROVENANCE_ONCE_ONLY');self.used=True
        require(expected.get('artifact_id')==ARTIFACT and expected.get('artifact_archive_sha256')==ARCHIVE and str(expected.get('artifact_run_id'))=='38250671983' and expected.get('artifact_commit')==RENDER_COMMIT and expected.get('media_sha256')==MEDIA and expected.get('job_id')==JOB_ID,'ARTIFACT_EXPECTATION_STOP')
        observed=[]
        def read(path):
            status,d=self.get(path)
            if '/artifacts?' in path and status==200 and isinstance(d,dict):
                observed.extend(a for a in d.get('artifacts',[]) if a.get('id')==ARTIFACT)
            return status,d
        proof=GitHubProvenance(read).verify(expected,phase=phase)
        require(len(observed)==1,'ARTIFACT_ORIGIN_STOP');a=observed[0]
        try:
            expiry=datetime.fromisoformat(a['expires_at'].replace('Z','+00:00'))
            require(expiry.tzinfo is not None and expiry.timestamp()>self.clock(),'ARTIFACT_EXPIRED_STOP')
        except (ValueError,TypeError,KeyError):raise Stop('ARTIFACT_EXPIRY_UNKNOWN_STOP') from None
        return proof


def fixed_job(identity):
    job=json.loads((ROOT/'readiness/youtube-private-job.json').read_bytes())
    require(job['job_id']==JOB_ID and job['speaker']==3 and job['voice_name']=='ずんだもん' and job['voice_style']=='ノーマル','FIXED_JOB_STOP')
    job['upload_identity']=identity;job['rights_verified']=True
    return job


def state_adapter(state,permit):
    require(type(state) is ExecutorLifecycle,'EXECUTOR_LIFECYCLE_REQUIRED')
    adapter_for(permit,state.backend)
    require(not state.uncertain and not state.doc['stopped'],'STATE_UNKNOWN_OR_STOPPED')

class UploadExecutor:
    def __init__(self,*,state,fresh,provenance,upload,clock):
        require(type(provenance) is RunProofAdapter,'INDEPENDENT_READER_REQUIRED')
        self.state=state;self.fresh=fresh;self.provenance=provenance
        self.upload=upload;self.clock=clock
    def run(self,permit,*,expected,assets,budget_observation,budget_cost):
        start(permit,'private_upload');state_adapter(self.state,permit);adapter_for(permit,self.fresh);adapter_for(permit,self.upload)
        job=fixed_job(permit.identity)
        require(expected['identity']==permit.identity and expected['job_id']==JOB_ID and expected.get('approval_field','upload_approved')=='upload_approved','UPLOAD_PROVENANCE_EXPECTATION_STOP')
        # Exact saved movie/voice/caption/script/credit gates before claim or OAuth.
        media_path=Path(assets['media_path']);require(media_path.is_file() and not media_path.is_symlink() and 10000<=media_path.stat().st_size<=16*1024*1024,'MEDIA_BOUND_STOP');media_gate(media_path,assets['quality_evidence'],job)
        media=media_path.read_bytes()
        render_gate(assets['render_contract'],script_raw=assets['script_raw'],voice_inventory=assets['voice_inventory'],media=media,audio=assets['audio'],captions=assets['captions'],evidence=assets['render_evidence'])
        budget_gate(budget_observation,budget_cost,self.clock(),offline_only=permit.mode=='OFFLINE_CONTRACT')
        proof=self.provenance.verify(expected,phase='before_upload',permit=permit)
        require(proof['identity']==permit.identity and proof['job_id']==JOB_ID and proof['media_sha256']==MEDIA,'PROVENANCE_BINDING_STOP')
        claim=self.state.claim(JOB_ID,digest(job),permit.identity,'actions-'+str(proof['run_id']),self.clock(),day=datetime.fromtimestamp(self.clock(),timezone.utc).strftime('%Y-%m-%d'))
        session=None;phase='AUTH'
        try:
            session=self.fresh.create();require(session.channel==CHANNEL,'CHANNEL_MISMATCH_STOP')
            phase='UPLOAD'
            upload_proof={**job,'media_sha256':MEDIA,'source_pins_exact':True,'rights_verified':True,'quality_pass':True,'upload_approved':True,'marker_consumed_before_remote':True,'marker_identity':permit.identity,'run_attempt':1}
            ack=StrictUploader(self.state,self.upload,self.clock).upload(claim,permit.identity,session,media_path,upload_proof)
            require(ack['state']=='ACKNOWLEDGED','UPLOAD_UNKNOWN_NO_RESEND')
            phase='SAVE'
            receipt=self.state.save_upload_ack(claim,ack,expected,{'id':ARTIFACT,'archive_sha256':ARCHIVE},assets['render_contract'])
            # No readback/callback/metrics/next dispatch in this operation.
            return permit.receipt('ACKNOWLEDGED',{**receipt,'next_job':None,'done':False})
        except Exception:
            if not self.state.uncertain and self.state.get(JOB_ID)['state'] not in ('UNKNOWN','Failed','Done'):
                self.state.halt(claim,{'AUTH':'AUTH_STOP','UPLOAD':'UPLOAD_UNKNOWN','SAVE':'CONFIG_STOP'}[phase])
            raise Stop('UPLOAD_EXECUTOR_STOP_NO_RESEND') from None
        finally:
            if session is not None:session.clear()

class FinalizeExecutor:
    def __init__(self,*,state,upload_provenance,own_provenance,fresh,readback_for_token,callback,clock):
        require(type(upload_provenance) is RunProofAdapter and type(own_provenance) is RunProofAdapter,'INDEPENDENT_READER_REQUIRED')
        self.state=state;self.upload_provenance=upload_provenance;self.own_provenance=own_provenance
        self.fresh=fresh;self.readback_for_token=readback_for_token
        self.callback=callback;self.clock=clock
    def run(self,permit,*,own_expected,script_sha256):
        start(permit,'finalize');state_adapter(self.state,permit);adapter_for(permit,self.fresh);adapter_for(permit,self.readback_for_token);adapter_for(permit,self.callback)
        row=self.state.get(JOB_ID);receipt=row.get('upload_receipt');expected=row.get('provenance_expected')
        require(row['state']=='ACKNOWLEDGED' and row['sent'] is True and isinstance(receipt,dict) and isinstance(expected,dict),'DURABLE_UPLOAD_ACK_REQUIRED')
        require(receipt['job_id']==JOB_ID and receipt['identity']==row['identity'] and receipt['channel_id']==CHANNEL and receipt['private'] is True and receipt['notify_subscribers'] is False and receipt['media_sha256']==MEDIA and receipt['upload_state']=='ACKNOWLEDGED' and receipt['video_id']==row['video_id'],'FINALIZE_RECEIPT_BINDING_STOP')
        # Prerequisite receipt cannot be used for a different durable State row.
        prior=permit.prerequisites[0]
        require(prior.identity==row['identity'] and prior.data.get('video_id')==row['video_id'] and prior.data.get('run_id')==receipt['run_id'],'FINALIZE_PREREQUISITE_STOP')
        require(own_expected['identity']==permit.identity and own_expected['job_id']==JOB_ID and own_expected['approval_field']=='finalize_approved' and str(own_expected['run_id'])!=receipt['run_id'] and re.fullmatch('[a-f0-9]{64}',script_sha256),'FINALIZER_INDEPENDENT_STOP')
        require(script_sha256==receipt['script_sha256'] and all(re.fullmatch('[a-f0-9]{64}',receipt[k]) for k in ('audio_sha256','caption_sha256')),'FINALIZER_RENDER_BINDING_STOP')
        # No State write until independent uploader terminal success AND own run proof.
        completed=self.upload_provenance.verify(expected,phase='completed',permit=permit)
        self.own_provenance.verify(own_expected,phase='before_upload',permit=permit)
        claim=self.state.finalize_claim(row,permit.identity,own_expected['run_id'],completed)
        session=None;phase='AUTH'
        try:
            session=self.fresh.create();require(session.channel==CHANNEL,'CHANNEL_MISMATCH_STOP')
            phase='READBACK';readback=self.readback_for_token(session.token())
            adapter_for(permit,readback)
            processed=readback.verify(receipt['video_id'],JOB_ID)
            require(processed['channel_id']==CHANNEL and processed['private'] is True and processed['video_id']==receipt['video_id'],'READBACK_BINDING_STOP')
            self.state.mark_callback_sent(claim)
            phase='CALLBACK';response=self.callback({**processed,'run_id':receipt['run_id'],'identity':row['identity'],'media_sha256':MEDIA})
            require(response=='ACK','CALLBACK_UNKNOWN')
            phase='SAVE';processed.update(callback='ACK',run_id=receipt['run_id'])
            self.state.save_receipt(claim,processed,expected)
            # Reuse original completion/metrics/next proposal code without repeated GETs.
            def cached(e,phase):
                require(e==expected and phase=='completed','COMPLETION_PROOF_CACHE_STOP');return copy.deepcopy(completed)
            original=self.state.authority
            def authority(r):
                if r.get('state')=='ACKNOWLEDGED':return r['job_id']==JOB_ID and r['identity']==completed['identity'] and str(r.get('run_id'))==completed['run_id'] and r.get('provenance_expected')==expected
                # Stored Done alone never authorizes continuation after ACK loss.
                return original(r)
            self.state.authority=authority
            factory=CandidateFactory(state=self.state,channel=None,provenance=cached,readback_for_token=None,upload_transport=None,callback=None,metrics=MetricsAdapter(lambda video:{'views':None,'likes':None,'comments':None},capability_verified=True),clock=self.clock)
            done=factory.finalize(JOB_ID,{'script_sha256':script_sha256},coordinator_run_id=str(own_expected['run_id']),finalizer_approval={'approved':True,'marker_consumed':True,'operation_kind':'FINALIZE_SHARED_JOB','identity':permit.identity,'job_id':JOB_ID,'run_id':str(own_expected['run_id'])})
            return permit.receipt('Done',{**done,'next_job_dispatch':False,'metrics_basis':'NO_REMOTE_METRICS_COLD_START_RULES','processed_readback':True,'callback':'ACK'})
        except Exception:
            if not self.state.uncertain and self.state.get(JOB_ID)['state'] not in ('Done','UNKNOWN','Failed'):self.state.halt(claim,{'AUTH':'AUTH_STOP','READBACK':'READBACK_UNKNOWN','CALLBACK':'CALLBACK_UNKNOWN','SAVE':'CONFIG_STOP'}[phase])
            raise Stop('FINALIZE_UNKNOWN_NO_REUPLOAD') from None
        finally:
            if session is not None:session.clear()
