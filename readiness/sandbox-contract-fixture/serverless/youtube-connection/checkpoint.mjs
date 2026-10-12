import {need,hash} from '../youtube-live/worker.mjs';
import {canon} from './mapping.mjs';
export const STAGE_FIELDS='protocol event key_id account_id intent_id job_id owner owner_epoch fencing_token dispatch_id run_id render_run_id run_attempt workflow_sha256 script_sha256 dispatch_payload_sha256 media_sha256 artifact_ref quality_gate issued_at'.split(' ').sort();
export async function signedStage(body,key){const raw=canon(body);need(key instanceof Uint8Array&&key.length>=32,'CHECKPOINT_KEY');const k=await crypto.subtle.importKey('raw',key,{name:'HMAC',hash:'SHA-256'},false,['sign']);const sig=[...new Uint8Array(await crypto.subtle.sign('HMAC',k,new TextEncoder().encode('plm-youtube-checkpoint-v1\n'+raw)))].map(x=>x.toString(16).padStart(2,'0')).join('');return {raw,signature:sig};}
export async function verifiedStage(raw,signature,key,keyId,now){
 let b;try{b=JSON.parse(raw);}catch{throw new Error('STAGE_JSON');}
 need(new TextEncoder().encode(raw).length<=8192&&b&&Object.keys(b).sort().join('|')===STAGE_FIELDS.join('|')&&canon(b)===raw,'STAGE_CANONICAL');
 need(key instanceof Uint8Array&&key.length>=32&&b.protocol==='plm-youtube-checkpoint-v1'&&b.key_id===keyId&&['bind','render'].includes(b.event)&&/^[a-f0-9]{64}$/.test(signature),'STAGE_SCOPE');
 need(Number.isSafeInteger(b.issued_at)&&b.issued_at>0&&Number.isSafeInteger(now)&&now>0&&now-b.issued_at<=300&&b.issued_at-now<=30,'STAGE_SKEW');
 need(b.run_attempt===1&&typeof b.run_id==='string'&&/^[1-9][0-9]{0,19}$/.test(b.run_id)&&b.render_run_id===b.run_id,'WORKFLOW_CALL_RUN_MAPPING');
 for(const k of ['dispatch_id','workflow_sha256','script_sha256','dispatch_payload_sha256'])need(typeof b[k]==='string'&&/^[a-f0-9]{64}$/.test(b[k]),'STAGE_HASH');
 need(['owner_epoch','fencing_token'].every(k=>Number.isSafeInteger(b[k])&&b[k]>0),'STAGE_FENCE');
 if(b.event==='bind')need(b.media_sha256===null&&b.artifact_ref===null&&b.quality_gate===null,'BIND_NO_RENDER');
 if(b.event==='render')need(/^[a-f0-9]{64}$/.test(b.media_sha256)&&typeof b.artifact_ref==='string'&&/^artifact:\/\/[A-Za-z0-9_/-]{1,240}$/.test(b.artifact_ref)&&b.quality_gate==='PASS','RENDER_CHECKPOINT');
 const k=await crypto.subtle.importKey('raw',key,{name:'HMAC',hash:'SHA-256'},false,['verify']);
 need(await crypto.subtle.verify('HMAC',k,Uint8Array.from(signature.match(/../g),s=>parseInt(s,16)),new TextEncoder().encode('plm-youtube-checkpoint-v1\n'+raw)),'STAGE_SIGNATURE');return b;
}
export const CHECKPOINT_SQL={
 binding:'SELECT * FROM plm_ytp_v1_binding WHERE job_id=?',
 bind:`INSERT INTO plm_ytp_v1_binding VALUES (?,?,?,?,1,?,?,?,?)`,
 effect:`INSERT INTO plm_rt_v2_effect VALUES (?,?,? ,?,?,?, ?,?,NULL,1,'RESERVED',?,?)`,
 effectSent:`UPDATE plm_rt_v2_effect SET state='SENT',version=2,updated_at=? WHERE effect_id=? AND state='RESERVED'`,
 renderInsert:`INSERT INTO plm_rt_v2_render VALUES (?,?,?,?,?,?,?,?,?,'PASS',?)`,
 renderConfirm:`UPDATE plm_rt_v2_effect SET state='CONFIRMED',version=3,result_id=?,updated_at=? WHERE effect_id=? AND state='SENT'`,
 renderReplay:`SELECT r.*,e.state AS upload_state FROM plm_rt_v2_render r JOIN plm_rt_v2_effect e ON e.job_id=r.job_id AND e.kind='UPLOAD' WHERE r.job_id=?`
};
export async function saveStage(boundary,raw,sig,key,keyId,now){
 need(!boundary.stopped,'STOP');const b=await verifiedStage(raw,sig,key,keyId,now);
 const q=await boundary.a.read('row',[b.job_id]);const o=await boundary.a.read('outbox',[b.dispatch_id]);
 need(q?.state==='DISPATCHED'&&q.job_state==='ACTIVE'&&o?.state==='SENT'&&o.send_attempts===1&&o.job_id===b.job_id&&o.payload_sha256===b.dispatch_payload_sha256&&b.workflow_sha256===boundary.target.workflow_sha256,'STAGE_DISPATCH_BINDING');
 for(const k of ['account_id','intent_id','owner','owner_epoch','fencing_token','script_sha256'])need(q[k]===b[k],'STAGE_QUEUE_BINDING');
 const prior=await boundary.a.read('binding',[b.job_id]);
 const effectId=await hash('render:'+b.dispatch_id);const delivery=await hash('render-delivery:'+b.dispatch_id);
 if(b.event==='bind'){
  if(prior){need(prior.bind_payload_sha256===await hash(raw),'STAGE_BIND_REPLAY_CHANGED');return {replay:true};}
  await boundary.a.batch([['bind',[b.job_id,b.dispatch_id,b.run_id,b.render_run_id,b.workflow_sha256,b.dispatch_payload_sha256,await hash(raw),now]],['effect',[effectId,b.job_id,'RENDER',b.owner,b.owner_epoch,b.fencing_token,b.script_sha256,delivery,now,now]],['effectSent',[now,effectId]]]);return {runBound:true};
 }
 need(prior&&prior.dispatch_id===b.dispatch_id&&prior.pipeline_run_id===b.run_id&&prior.render_run_id===b.render_run_id&&prior.workflow_sha256===b.workflow_sha256&&prior.dispatch_payload_sha256===b.dispatch_payload_sha256,'PREEXISTING_RUN_REQUIRED');
 const old=await boundary.a.read('renderReplay',[b.job_id]);
 if(old){need(old.artifact_sha256===b.media_sha256&&old.artifact_ref===b.artifact_ref&&old.script_sha256===b.script_sha256&&old.render_run_id===b.run_id&&old.upload_state==='SENT','RENDER_REPLAY_CHANGED');return {replay:true};}
 const uploadId=await hash('upload:'+b.dispatch_id);const uploadDelivery=await hash('upload-delivery:'+b.dispatch_id);
 await boundary.a.batch([['renderInsert',[await hash('artifact:'+b.dispatch_id),b.job_id,b.owner,b.owner_epoch,b.fencing_token,b.script_sha256,b.media_sha256,b.artifact_ref,b.render_run_id,now]],['renderConfirm',[await hash('render-result:'+b.dispatch_id),now,effectId]],['effect',[uploadId,b.job_id,'UPLOAD',b.owner,b.owner_epoch,b.fencing_token,b.media_sha256,uploadDelivery,now,now]],['effectSent',[now,uploadId]]]);return {renderSaved:true,uploadReserved:true};
}
