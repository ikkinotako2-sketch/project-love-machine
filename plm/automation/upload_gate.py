"""Pure future marker/history validator. No credentials or transports imported."""
import hashlib,json,re
from .ledger import require
REPO='ikkinotako2-sketch/project-love-machine'
IDENTITY='provider-neutral-youtube-private-upload-20261012-r1'
MARKER='audit-evidence/consumed/'+IDENTITY+'.json'
JOB='plm-private-channel-recovery-20261012-r1'
CHANNEL='UCJdTc1jznWNFlp0qy0SQ6uQ'
def validate(marker,env,facts,manifest,source_bytes,media_sha256):
    require(set(marker)=={'identity','state','prepared_commit_sha','job_id','expected_channel_id','media_sha256','source_manifest_sha256','upload_approved'},'MARKER_SHAPE_STOP')
    require(marker['identity']==IDENTITY and marker['state']=='CONSUMED_BEFORE_REMOTE' and marker['job_id']==JOB and marker['expected_channel_id']==CHANNEL and marker['upload_approved'] is True,'MARKER_IDENTITY_STOP')
    require(env.get('repository')==REPO and env.get('event')=='push' and env.get('run_attempt')==1 and type(env.get('run_attempt')) is int,'RUN_STOP')
    require(env.get('flags')=={'TEST_ONLY':True,'DRY_RUN':True,'NO_PUBLISH':True,'EMERGENCY_STOP':True},'FLAGS_STOP')
    require(facts.get('full_history') is True and facts.get('marker_absent_parent') is True and facts.get('marker_diff')==[MARKER] and facts.get('parent')==marker['prepared_commit_sha'] and facts.get('head_parent')==facts.get('parent'),'MARKER_HISTORY_STOP')
    require(re.fullmatch('[a-f0-9]{40}',marker['prepared_commit_sha']) and facts.get('message')=='PLM YouTube private upload once '+IDENTITY,'MARKER_COMMIT_STOP')
    require(marker['media_sha256']==media_sha256 and re.fullmatch('[a-f0-9]{64}',media_sha256),'MEDIA_STOP')
    raw=json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()
    require(marker['source_manifest_sha256']==hashlib.sha256(raw).hexdigest(),'MANIFEST_STOP')
    pins=manifest.get('candidate_sha256');require(isinstance(pins,dict) and pins and set(pins)==set(source_bytes),'SOURCE_SET_STOP')
    for path,h in pins.items():
        require(isinstance(path,str) and not path.startswith('/') and '..' not in path.split('/') and hashlib.sha256(source_bytes[path]).hexdigest()==h,'SOURCE_DRIFT_STOP')
    require(facts.get('historical_markers_unchanged') is True and facts.get('existing_runs')==0 and facts.get('channel_prerequisite_verified') is True,'PREREQUISITE_STOP')
    return True
if __name__=='__main__':print('PARKED_NO_UPLOAD_WORKFLOW')
