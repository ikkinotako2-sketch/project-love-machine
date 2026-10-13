"""ACK receipt/finalization fences extending, never resetting, existing lifecycle."""
import copy,re
from ..shared_lifecycle import SharedLifecycle
from ..ledger import require
from ..production_bridge import MEDIA,CHANNEL

class ExecutorLifecycle(SharedLifecycle):
    def save_upload_ack(self,claim,ack,expected,artifact,render_contract):
        row=self.checked(claim)
        require(row['state']=='ACKNOWLEDGED' and row['sent'] is True and ack['job_id']==row['job_id'] and ack['video_id']==row['video_id'] and expected['job_id']==row['job_id'] and expected['identity']==row['identity'] and expected['media_sha256']==MEDIA,'UPLOAD_RECEIPT_BINDING_STOP')
        require('upload_receipt' not in row,'UPLOAD_RECEIPT_ALREADY_SAVED')
        # No token, response, arbitrary remote text or channel session is retained.
        safe={'job_id':row['job_id'],'identity':row['identity'],'video_id':row['video_id'],
              'channel_id':CHANNEL,'private':True,'notify_subscribers':False,
              'media_sha256':MEDIA,'run_id':str(expected['run_id']),
              'upload_state':'ACKNOWLEDGED','processed':False,'artifact_id':artifact['id'],
              'artifact_archive_sha256':artifact['archive_sha256'],'script_sha256':render_contract['script_sha256'],'audio_sha256':render_contract['audio_sha256'],'caption_sha256':render_contract['caption_sha256']}
        require(all(re.fullmatch('[a-f0-9]{64}',safe[k]) for k in ('script_sha256','audio_sha256','caption_sha256')),'UPLOAD_RENDER_RECEIPT_STOP')
        allowed={'repository','run_id','attempt','commit','prepared_commit','branch','workflow_path','job_name','job_id','identity','media_sha256','artifact_id','artifact_archive_sha256','artifact_run_id','artifact_commit','marker_path','marker_sha256','workflow_sha256','approval_field'}
        require(set(expected)<=allowed and all(type(v) in (str,int) and (type(v) is int or len(v)<=512) for v in expected.values()),'UPLOAD_RECEIPT_SHAPE_STOP')
        d=copy.deepcopy(self.doc);d['jobs'][row['job_id']]['upload_receipt']=safe
        d['jobs'][row['job_id']]['provenance_expected']=copy.deepcopy(expected);self.commit(d)
        return copy.deepcopy(safe)
    def finalize_claim(self,claim,identity,run_id,completed_proof):
        require(not self.uncertain and not self.doc['stopped'],'STATE_STOP')
        row=self.doc['jobs'].get(claim['job_id'])
        require(row and self.doc['active']==row['job_id'] and all(row[k]==claim[k] for k in ('owner','epoch','fence','fingerprint','identity')),'FINALIZER_STATE_FENCE_STOP')
        require(row['state']=='ACKNOWLEDGED' and row['sent'] is True and isinstance(row.get('upload_receipt'),dict),'FINALIZE_ACK_REQUIRED')
        require(completed_proof.get('verified') is True and completed_proof.get('phase')=='completed' and completed_proof.get('proof_basis')=='INDEPENDENT_GITHUB_API' and completed_proof.get('job_id')==row['job_id'] and completed_proof.get('identity')==row['identity'] and completed_proof.get('run_id')==row['upload_receipt']['run_id'] and completed_proof.get('media_sha256')==MEDIA,'FINALIZER_COMPLETED_UPLOAD_PROOF_STOP')
        require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,95}',identity) and identity!=row['identity'] and str(run_id)!=row['upload_receipt']['run_id'] and re.fullmatch('[1-9][0-9]{0,19}',str(run_id)),'INDEPENDENT_FINALIZER_STOP')
        require('finalizer' not in row and not any(r.get('finalizer',{}).get('identity')==identity for r in self.doc['jobs'].values()),'FINALIZER_TOMBSTONE_STOP')
        # Only independently confirmed terminal uploader success allows transfer.
        # This is an ACK-only finalization lease, never a Processing/SENT reclaim.
        d=copy.deepcopy(self.doc);r=d['jobs'][row['job_id']]
        r['finalizer']={'identity':identity,'run_id':str(run_id),'consumed':True}
        r.update(owner='finalize-'+str(run_id),epoch=row['epoch']+1,fence=row['fence']+1,lease_until=self.clock()+300)
        self.commit(d);return copy.deepcopy(r)
