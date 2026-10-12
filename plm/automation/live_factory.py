"""Future factory with explicit injected I/O. Production entry remains parked.

Actions phase saves upload/readback/callback receipts. A separate coordinator
phase requires a COMPLETED GitHub run proof before Done/metrics/next admission.
"""
import copy,hashlib,json,re
from pathlib import Path
from .ledger import Stop,require
from .production_bridge import digest,scope_gate,CHANNEL
from .strict_upload import StrictUploader
from .render_contract import render_gate
from .content_adapters import MetricsAdapter,next_job
from .loop import FLAGS
from .quota_contract import budget_gate

def production_entry(*args,**kwargs):raise Stop('FACTORY_PARKED_NO_LIVE_APPROVAL')

class DispatchOnce:
    """Target-only API POST candidate; sender injected; no default credential."""
    maximum_posts=1
    def __init__(self,send):self.send=send;self.used=False
    def dispatch(self,target,inputs,*,approved=False,immutable_ref_proven=False,sentinel):
        require(approved is True and immutable_ref_proven is True and not self.used and sentinel() is True,'DISPATCH_GATE_STOP')
        require(set(target)=={'repository','workflow','ref'} and target['repository']=='ikkinotako2-sketch/project-love-machine' and target['workflow']=='youtube-pipeline.yml' and re.fullmatch('[a-f0-9]{40}',target['ref']),'IMMUTABLE_DISPATCH_STOP')
        self.used=True
        try:status=self.send('/repos/'+target['repository']+'/actions/workflows/'+target['workflow']+'/dispatches',{'ref':target['ref'],'inputs':inputs})
        except Exception:raise Stop('DISPATCH_UNKNOWN_NO_RESEND') from None
        require(status==204,'DISPATCH_UNKNOWN_NO_RESEND');return True

class CandidateFactory:
    def __init__(self,*,state,channel,provenance,readback_for_token,upload_transport,callback,metrics,clock,offline_only=True):
        # This constructor is available only for injected OFFLINE orchestration.
        # A future remote entry needs a separately reviewed marker/credential gate.
        require(offline_only is True,'FACTORY_PARKED_NO_LIVE_APPROVAL')
        self.state=state;self.channel=channel;self.provenance=provenance;self.readback=readback_for_token;self.upload=upload_transport;self.callback=callback;self.metrics=metrics;self.clock=clock;self.calls=set();self.receipts={};self.seen=set()
    def run(self,job,*,scope,operation,provenance_expected,render_contract,script_raw,voice_inventory,media,audio,captions,render_evidence,media_path,day,budget_known,budget_observation,budget_cost,claim=None):
        # Cheap reversible gates before any state or credential operation.
        require(operation.get('flags')==FLAGS and operation.get('approved') is True and operation.get('marker_consumed') is True and operation.get('identity')==job['upload_identity'] and operation.get('source_pins_exact') is True and operation.get('artifact_fresh') is True,'OPERATION_GATE_STOP')
        scope_gate(scope.get('scopes'),scope.get('proven'))
        require(job['job_id'] not in self.calls and job['expected_channel_id']==CHANNEL and job['privacy_status']=='private' and job['notify_subscribers'] is False and budget_known is True,'JOB_CHANNEL_BUDGET_STOP')
        budget_gate(budget_observation,budget_cost,self.clock(),offline_only=True)
        p=self.provenance(provenance_expected,phase='before_upload')
        require(p.get('verified') is True and p.get('phase')=='before_upload' and p['job_id']==job['job_id'] and p['identity']==job['upload_identity'] and p['media_sha256']==hashlib.sha256(media).hexdigest(),'INDEPENDENT_PROVENANCE_STOP')
        render_gate(render_contract,script_raw=script_raw,voice_inventory=voice_inventory,media=media,audio=audio,captions=captions,evidence=render_evidence)
        require(Path(media_path).read_bytes()==media,'MEDIA_PATH_BINDING_STOP')
        self.calls.add(job['job_id'])
        if claim is None:claim=self.state.claim(job['job_id'],digest(job),job['upload_identity'],'actions-'+str(p['run_id']),self.clock(),day=day)
        session=None;token=None;phase='AUTH'
        try:
            channel=self.channel(job['job_id']) if callable(self.channel) else self.channel
            session=channel.create();token=session.token()
            proof={**job,'media_sha256':hashlib.sha256(media).hexdigest(),'source_pins_exact':True,'rights_verified':job.get('rights_verified') is True,'quality_pass':True,'upload_approved':True,'marker_consumed_before_remote':True,'marker_identity':job['upload_identity'],'run_attempt':1}
            phase='UPLOAD'
            ack=StrictUploader(self.state,self.upload,self.clock).upload(claim,job['upload_identity'],session,media_path,proof)
            require(ack['state']=='ACKNOWLEDGED','UPLOAD_UNKNOWN_NO_RESEND')
            phase='READBACK'
            receipt=self.readback(token).verify(ack['video_id'],job['job_id'])
            self.state.mark_callback_sent(claim)
            phase='CALLBACK'
            try:response=self.callback({**receipt,'run_id':p['run_id'],'identity':job['upload_identity'],'media_sha256':proof['media_sha256']})
            except Exception:raise Stop('CALLBACK_UNKNOWN') from None
            require(response=='ACK','CALLBACK_UNKNOWN')
            receipt.update(callback='ACK',run_id=p['run_id']);self.state.save_receipt(claim,receipt,provenance_expected)
            return {**receipt,'state':'AWAITING_COMPLETED_RUN_PROOF','next_job':None}
        except Exception as exc:
            if not self.state.uncertain:
                reason={'AUTH':'AUTH_STOP','UPLOAD':'UPLOAD_UNKNOWN','READBACK':'READBACK_UNKNOWN','CALLBACK':'CALLBACK_UNKNOWN'}[phase]
                self.state.halt(claim,reason)
            raise Stop('FACTORY_UNKNOWN_STOP_NO_RESEND') from None
        finally:
            if session:session.clear()
            token=None
    def finalize(self,job_id,script,*,coordinator_run_id,finalizer_approval):
        require(not self.state.uncertain,'COMPLETION_RECEIPT_REQUIRED')
        claim=self.state.get(job_id);receipt=claim.get('completion_receipt');expected=claim.get('provenance_expected')
        require(isinstance(receipt,dict) and isinstance(expected,dict),'COMPLETION_RECEIPT_REQUIRED')
        require(finalizer_approval.get('approved') is True and finalizer_approval.get('marker_consumed') is True and finalizer_approval.get('operation_kind')=='FINALIZE_SHARED_JOB' and finalizer_approval.get('identity')!=claim['identity'] and finalizer_approval.get('job_id')==job_id and str(finalizer_approval.get('run_id'))==str(coordinator_run_id),'FINALIZER_INDEPENDENT_APPROVAL_REQUIRED')
        p=self.provenance(expected,phase='completed')
        require(p.get('verified') is True and p.get('phase')=='completed' and p['job_id']==job_id and p['run_id']==receipt['run_id'] and p['identity']==claim['identity'],'COMPLETION_PROVENANCE_STOP')
        try:
            result={'job_id':job_id,'state':'Done','video_id':receipt['video_id']} # proposal from independent proofs; not yet stored Done
            observations=self.metrics.collect(result);improvement=self.metrics.improve(observations);identifier=next_job(result,script,self.seen)
        except Exception:
            self.state.halt(claim,'CONFIG_STOP');raise Stop('METRICS_UNKNOWN_STOP') from None
        result=self.state.complete(claim,receipt,{'next_job':identifier,'improvement_method':improvement['method'],'coordinator_run_id':str(coordinator_run_id)})
        return {**result,'next_job':identifier,'improvement_method':improvement['method']}

class CallbackOnce:
    """Reuses historical canonical result/sign contract. No default HTTP sender.
    Exact approved HTTPS origin and /youtube/result only, callback key separate.
    Durable callback SENT is supplied by SharedLifecycle before this is called.
    """
    def __init__(self,send,context,checkpoint,key,key_id,*,origin,approved=False,clock,dispatch_key):
        import hmac
        require(approved is True and re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,250}',str(origin)) and type(key) is bytes and len(key)>=32 and type(dispatch_key) is bytes and len(dispatch_key)>=32 and not hmac.compare_digest(key,dispatch_key) and not key.startswith((b'PUBLIC_',b'FIXTURE')),'CALLBACK_APPROVAL_KEY_STOP')
        self.send=send;self.context=context;self.checkpoint=checkpoint;self.key=key;self.key_id=key_id;self.origin=origin;self.clock=clock;self.used=False
    def __repr__(self):return '<CallbackOnce REDACTED>'
    def __call__(self,receipt):
        import importlib.util
        require(not self.used and receipt.get('proof_basis')=='INDEPENDENT_READBACK' and receipt.get('processed') is True and receipt.get('channel_id')==CHANNEL and receipt.get('private') is True and receipt.get('job_id')==self.context['job_id'] and receipt.get('run_id')==self.context['run_id'] and receipt.get('media_sha256')==self.checkpoint['media_sha256'],'CALLBACK_BINDING_STOP');self.used=True
        path=Path(__file__).resolve().parents[2]/'readiness/sandbox-contract-fixture/readiness/production-candidate/source/plm/entrypoints/yt_serverless_candidate.py'
        spec=importlib.util.spec_from_file_location('plm_pinned_sender',path);sender=importlib.util.module_from_spec(spec);spec.loader.exec_module(sender)
        video=receipt['video_id'];status={'id':video,'status':{'privacyStatus':'private','uploadStatus':'processed'},'processingDetails':{'processingStatus':'succeeded'}}
        body=sender.result_payload(self.context,self.checkpoint,{'ok':True,'result':{'account_id':self.context['account_id'],'platform':'youtube','post_id':video}},status,self.clock(),self.key_id)
        raw,signature=sender.sign(body,self.key,'plm-youtube-result-v2')
        try:status=self.send('https://'+self.origin+'/youtube/result',raw,signature)
        except Exception:raise Stop('CALLBACK_UNKNOWN_NO_RETRY') from None
        finally:self.key=None
        require(status==200,'CALLBACK_UNKNOWN_NO_RETRY');return 'ACK'
