import {need,hash,FIELDS} from '../youtube-live/worker.mjs';
import {canon} from './mapping.mjs';
export function processedVideo(status,video){need(status?.id===video&&status.status?.privacyStatus==='private'&&status.status?.uploadStatus==='processed'&&status.processingDetails?.processingStatus==='succeeded','PROCESSED_PRIVATE_VIDEO_REQUIRED');return 'processed';}
export async function callbackPayload(context,checkpoint,adapter,status,now,keyId){
 need(adapter?.ok===true&&adapter.result?.account_id===context.account_id&&adapter.result?.platform==='youtube'&&typeof adapter.result.post_id==='string','ADAPTER_RESULT');
 const video=adapter.result.post_id;processedVideo(status,video);
 need(checkpoint.run_id===context.run_id&&checkpoint.render_run_id===context.run_id&&checkpoint.script_sha256===context.script_sha256&&checkpoint.quality_gate==='PASS','SENDER_CHECKPOINT');
 const result_id=await hash('plm-youtube-result-v2:'+context.dispatch_id+':'+context.run_id);
 const body={protocol:'plm-youtube-result-v2',key_id:keyId,account_id:context.account_id,intent_id:context.intent_id,job_id:context.job_id,owner:context.owner,owner_epoch:context.owner_epoch,fencing_token:context.fencing_token,dispatch_id:context.dispatch_id,run_id:context.run_id,run_attempt:1,workflow_sha256:context.workflow_sha256,script_sha256:context.script_sha256,media_sha256:checkpoint.media_sha256,result_id,video_id:video,privacy_status:'private',notify_subscribers:false,processing_status:'processed',quality_gate:'PASS',issued_at:now};
 need(Object.keys(body).sort().join('|')===FIELDS.join('|'),'CALLBACK_FIELDS');return body;
}
export async function signCallback(body,key){need(key instanceof Uint8Array&&key.length>=32,'DEDICATED_CALLBACK_KEY');const raw=canon(body);const k=await crypto.subtle.importKey('raw',key,{name:'HMAC',hash:'SHA-256'},false,['sign']);const signature=[...new Uint8Array(await crypto.subtle.sign('HMAC',k,new TextEncoder().encode('plm-youtube-result-v2\n'+raw)))].map(x=>x.toString(16).padStart(2,'0')).join('');return {raw,signature};}
