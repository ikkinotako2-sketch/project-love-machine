"""Proposed one-send stage/callback sender. No IO on import; no raw logs."""
import hashlib
import hmac
import json
import re
from pathlib import Path

FIELDS=set('protocol key_id account_id intent_id job_id owner owner_epoch fencing_token dispatch_id run_id run_attempt workflow_sha256 script_sha256 media_sha256 result_id video_id privacy_status notify_subscribers processing_status quality_gate issued_at'.split())

def need(ok,code):
    if not ok:raise ValueError(code)

def canonical(value):
    # Signed envelopes contain strings, booleans, null and integer counters only.
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))

def digest(raw):return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def sign(body,key,domain):
    need(type(key) is bytes and len(key)>=32,'DEDICATED_KEY_REQUIRED')
    raw=canonical(body)
    return raw,hmac.new(key,(domain+'\n'+raw).encode('utf-8'),hashlib.sha256).hexdigest()

def context(event,run_id,attempt,commit,workflow_bytes,now,key_id):
    inputs=event['inputs'];ctx=json.loads(inputs['serverless_context'])
    fields=set('account_id intent_id job_id owner owner_epoch fencing_token dispatch_id script_sha256 workflow_sha256 production_ref'.split())
    need(type(ctx) is dict and set(ctx)==fields,'CONTEXT_FIELDS')
    need(ctx['job_id']==inputs['job_id'] and ctx['account_id']==inputs['account_id']=='youtube_game_001','CONTEXT_SCOPE')
    need(re.fullmatch('[1-9][0-9]{0,19}',run_id) and attempt=='1' and ctx['production_ref']==commit and re.fullmatch('[a-f0-9]{40}',commit),'EXACT_RUN_REF')
    need(hashlib.sha256(workflow_bytes).hexdigest()==ctx['workflow_sha256'],'WORKFLOW_SHA')
    need(inputs['privacy_status']=='private' and inputs['scheduled_for']=='' and inputs['notify_subscribers'] in (False,'false'),'PRIVATE_INPUTS')
    # workflow_dispatch event boolean inputs are stringified by GitHub. Restore the
    # three exact schema booleans to reconstruct the dispatch API JSON bytes.
    restored=dict(inputs)
    for k in ('made_for_kids','contains_synthetic_media','notify_subscribers'):
        need(restored[k] in (True,False,'true','false'),'BOOLEAN_INPUT')
        restored[k]=restored[k] is True or restored[k]=='true'
    payload={'ref':commit,'inputs':restored}
    return {'protocol':'plm-youtube-checkpoint-v1','event':'bind','key_id':key_id,
      **{k:ctx[k] for k in fields if k!='production_ref'},'run_id':run_id,'render_run_id':run_id,'run_attempt':1,
      'dispatch_payload_sha256':digest(canonical(payload)),'media_sha256':None,'artifact_ref':None,'quality_gate':None,'issued_at':now}

def render_checkpoint(base,render_result,media_bytes,artifact_name,now):
    need(render_result.get('ok') is True and render_result.get('quality_gate',{}).get('ok') is True and render_result.get('stages',{}).get('quality_gate')=='succeeded','QUALITY_GATE_PASS_REQUIRED')
    need(artifact_name=='rendered-short-'+base['job_id'],'ARTIFACT_BINDING')
    return {**base,'event':'render','media_sha256':hashlib.sha256(media_bytes).hexdigest(),
            'artifact_ref':'artifact://'+base['run_id']+'/'+artifact_name,'quality_gate':'PASS','issued_at':now}

def result_payload(base,checkpoint,adapter,status,now,key_id):
    result=adapter.get('result',{})
    need(adapter.get('ok') is True and result.get('account_id')==base['account_id'] and result.get('platform')=='youtube','ADAPTER_RESULT')
    video=result.get('post_id');need(type(video) is str and re.fullmatch('[A-Za-z0-9_-]{11}',video),'VIDEO_ID')
    need(status.get('id')==video and status.get('status',{}).get('privacyStatus')=='private' and status.get('status',{}).get('uploadStatus')=='processed' and status.get('processingDetails',{}).get('processingStatus')=='succeeded','PROCESSING_NOT_COMPLETE_STOP')
    need(checkpoint['run_id']==base['run_id'] and checkpoint['script_sha256']==base['script_sha256'] and checkpoint['quality_gate']=='PASS','CHECKPOINT_BINDING')
    body={'protocol':'plm-youtube-result-v2','key_id':key_id,
      **{k:base[k] for k in ('account_id','intent_id','job_id','owner','owner_epoch','fencing_token','dispatch_id','run_id','run_attempt','workflow_sha256','script_sha256')},
      'media_sha256':checkpoint['media_sha256'],'result_id':digest('plm-youtube-result-v2:'+base['dispatch_id']+':'+base['run_id']),
      'video_id':video,'privacy_status':'private','notify_subscribers':False,'processing_status':'processed','quality_gate':'PASS','issued_at':now}
    need(set(body)==FIELDS,'RESULT_FIELDS');return body

def send_once(url,raw,signature,sentinel,connector,origin,path):
    # Exact HTTPS origin/path, no redirects, no retries, consume before transport.
    from urllib.parse import urlsplit
    parsed=urlsplit(url)
    need(parsed.scheme=='https' and parsed.netloc==origin and parsed.path==path and not parsed.query and not parsed.fragment and not parsed.username,'EXACT_CALLBACK_URL')
    with Path(sentinel).open('x',encoding='ascii') as f:f.write('consumed\n')
    connection=connector(origin,timeout=30)
    try:
        connection.request('POST',path,body=raw.encode('utf-8'),headers={'Content-Type':'application/json','X-PLM-Signature':signature})
        response=connection.getresponse()
        need(response.status==200,'CALLBACK_UNKNOWN_NO_RETRY')
    except Exception:raise ValueError('CALLBACK_UNKNOWN_NO_RETRY') from None
    finally:connection.close()

def main():
    import os
    import sys
    import time
    import http.client
    env=os.environ;kind=sys.argv[1]
    try:
        need(kind in ('bind','render','result'),'STAGE_COMMAND')
        need(all(env.get(k)=='false' for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')),'APPROVAL_FLAGS_REQUIRED')
        event=json.loads(Path(env['GITHUB_EVENT_PATH']).read_text(encoding='utf-8'))
        need(env.get('PLM_SERVERLESS_OPERATION_APPROVED')==event['inputs']['job_id'],'EXACT_JOB_APPROVAL_REQUIRED')
        now=int(time.time());stage_key=env['PLM_YOUTUBE_CHECKPOINT_KEY'].encode('utf-8');callback_key=env['PLM_YOUTUBE_RESULT_CALLBACK_KEY'].encode('utf-8')
        need(len(stage_key)>=32 and len(callback_key)>=32 and not hmac.compare_digest(stage_key,callback_key) and not stage_key.startswith(b'PUBLIC_') and not callback_key.startswith(b'PUBLIC_'),'INDEPENDENT_LIVE_KEYS_REQUIRED')
        base=context(event,env['GITHUB_RUN_ID'],env['GITHUB_RUN_ATTEMPT'],env['GITHUB_SHA'],Path('.github/workflows/youtube-pipeline.yml').read_bytes(),now,env['PLM_CHECKPOINT_KEY_ID'])
        if kind=='bind':body=base;domain='plm-youtube-checkpoint-v1';key=stage_key;path='/youtube/checkpoint'
        else:
            render=json.loads(env['PLM_RENDER_RESULT_JSON']);media=Path('render-output/short.mp4').read_bytes()
            cp=render_checkpoint(base,render,media,'rendered-short-'+base['job_id'],now)
            if kind=='render':body=cp;domain='plm-youtube-checkpoint-v1';key=stage_key;path='/youtube/checkpoint'
            else:
                need(env['PLM_RENDER_JOB_STATUS']=='success' and env['PLM_YOUTUBE_JOB_STATUS']=='success','PIPELINE_STAGE_SUCCESS_REQUIRED')
                adapter=json.loads(Path('adapter-result/youtube-result.json').read_text(encoding='utf-8'))
                # One bounded owner-authenticated status read, never reupload or poll.
                from plm.social_adapters.youtube import EnvironmentOAuthTokenProvider,YouTubeRestApi,QuotaBudget
                api=YouTubeRestApi(EnvironmentOAuthTokenProvider(),quota=QuotaBudget(upload_limit=1,data_units=1),upload_resume_attempts=1)
                status=api.get_video(adapter['result']['post_id'])
                body=result_payload(base,cp,adapter,status,now,env['PLM_CALLBACK_KEY_ID']);domain='plm-youtube-result-v2';key=callback_key;path='/youtube/result'
        raw,sig=sign(body,key,domain)
        origin=env['PLM_SERVERLESS_ORIGIN'];need(re.fullmatch('[a-z0-9][a-z0-9.-]{1,252}',origin),'EXACT_ORIGIN')
        send_once('https://'+origin+path,raw,sig,'.plm-'+kind+'-consumed',http.client.HTTPSConnection,origin,path)
        return 0
    except Exception:
        print('STOP_SERVERLESS_STAGE_UNVERIFIED_OR_UNKNOWN')
        return 1

if __name__=='__main__':raise SystemExit(main())
