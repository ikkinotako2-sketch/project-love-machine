// Offline-reviewed YouTube boundary. No ambient transport or credential lookup.
export const TARGET=Object.freeze({repository:'ikkinotako2-sketch/project-love-machine',workflow:'.github/workflows/youtube-pipeline.yml',ref:'b0c7f429a1f58726c4a75f4fb090928cf567b585',workflow_sha256:'5f3550854efc85ec46c6e4bbb5061c009530f6760f3ac1ebc5c64f63aa2b4928'});
export const FLAGS=['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'];
export function need(ok,code='STOP'){if(!ok)throw new Error(code);}
const enc=new TextEncoder();
export const canonical=x=>JSON.stringify(Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])));
export async function hash(text){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',enc.encode(text)))].map(x=>x.toString(16).padStart(2,'0')).join('');}
const id=x=>typeof x==='string'&&/^[A-Za-z0-9_-]{1,64}$/.test(x);
const sha=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
const integer=x=>Number.isSafeInteger(x)&&x>0;
export const FIELDS='protocol key_id account_id intent_id job_id owner owner_epoch fencing_token dispatch_id run_id run_attempt workflow_sha256 script_sha256 media_sha256 result_id video_id privacy_status notify_subscribers processing_status quality_gate issued_at'.split(' ').sort();
export async function verifyCallback(raw,signature,key,keyId,now){
 need(typeof raw==='string'&&enc.encode(raw).length<=8192,'BODY_LIMIT');
 need(key instanceof Uint8Array&&key.length>=32&&id(keyId)&&integer(now),'KEY_OR_CLOCK');
 let b;try{b=JSON.parse(raw);}catch{throw new Error('BODY_JSON');}
 need(b&&typeof b==='object'&&!Array.isArray(b)&&Object.keys(b).sort().join('|')===FIELDS.join('|')&&canonical(b)===raw,'EXACT_CANONICAL_BODY');
 need(b.protocol==='plm-youtube-result-v2'&&b.key_id===keyId&&b.account_id==='youtube_game_001','SCOPE');
 for(const k of ['intent_id','job_id','owner','result_id'])need(id(b[k]),'IDENTITY');
 for(const k of ['dispatch_id','workflow_sha256','script_sha256','media_sha256'])need(sha(b[k]),'HASH');
 need(b.workflow_sha256===TARGET.workflow_sha256&&typeof b.run_id==='string'&&/^[1-9][0-9]{0,19}$/.test(b.run_id)&&b.run_attempt===1,'RUN_WORKFLOW');
 need(integer(b.owner_epoch)&&integer(b.fencing_token)&&integer(b.issued_at)&&now-b.issued_at<=300&&b.issued_at-now<=30,'FENCE_SKEW');
 need(b.privacy_status==='private'&&b.notify_subscribers===false&&b.processing_status==='processed'&&b.quality_gate==='PASS'&&typeof b.video_id==='string'&&/^[A-Za-z0-9_-]{11}$/.test(b.video_id),'PRIVATE_QG');
 need(sha(signature),'SIGNATURE_FORMAT');
 const imported=await crypto.subtle.importKey('raw',key,{name:'HMAC',hash:'SHA-256'},false,['verify']);
 // Platform cryptographic verify, no JavaScript string equality for signatures.
 const bytes=Uint8Array.from(signature.match(/../g),s=>parseInt(s,16));
 need(await crypto.subtle.verify('HMAC',imported,bytes,enc.encode('plm-youtube-result-v2\n'+raw)),'SIGNATURE');
 return b;
}
export const SQL=Object.freeze({
 enqueue:`INSERT INTO plm_ytq_v1_queue VALUES (?,?,?,?,?,?,?,?,'QUEUED',1,?,?)`,
 script:`SELECT script_json,script_sha256 FROM plm_rt_v2_script WHERE job_id=? AND state='COMPLETED'`,
 row:`SELECT q.*,j.state AS job_state FROM plm_ytq_v1_queue q JOIN plm_rt_v2_job j ON j.job_id=q.job_id AND j.owner=q.owner AND j.owner_epoch=q.owner_epoch AND j.fencing_token=q.fencing_token WHERE q.job_id=?`,
 eligible:`SELECT job_id FROM plm_ytq_v1_queue q WHERE state='QUEUED' AND not_before<=? AND NOT EXISTS(SELECT 1 FROM plm_ytq_v1_queue a WHERE a.account_id=q.account_id AND a.state IN ('CLAIMED','DISPATCHED','UNKNOWN')) ORDER BY not_before,created_at,job_id LIMIT 1`,
 claim:`UPDATE plm_ytq_v1_queue SET state='CLAIMED',version=version+1,updated_at=? WHERE job_id=? AND state='QUEUED' AND owner=? AND owner_epoch=? AND fencing_token=? AND version=?`,
 reserve:`INSERT INTO plm_ytq_v1_outbox VALUES (?,?,?,'RESERVED',0)`,
 dispatched:`UPDATE plm_ytq_v1_queue SET state='DISPATCHED',version=version+1,updated_at=? WHERE job_id=? AND state='CLAIMED' AND version=?`,
 sent:`UPDATE plm_ytq_v1_outbox SET state='SENT',send_attempts=1 WHERE dispatch_id=? AND state='RESERVED' AND send_attempts=0`,
 outbox:`SELECT * FROM plm_ytq_v1_outbox WHERE dispatch_id=?`,
 unknownOut:`UPDATE plm_ytq_v1_outbox SET state='UNKNOWN' WHERE dispatch_id=? AND state='SENT'`,
 unknownQueue:`UPDATE plm_ytq_v1_queue SET state='UNKNOWN',version=version+1,updated_at=? WHERE job_id=? AND state='DISPATCHED'`,
 render:`SELECT r.*,e.delivery_id,e.state AS upload_state FROM plm_rt_v2_render r JOIN plm_rt_v2_effect e ON e.job_id=r.job_id AND e.kind='UPLOAD' WHERE r.job_id=?`,
 replay:`SELECT * FROM plm_rt_v2_callback WHERE result_id=? OR job_id=?`,
 callback:`INSERT INTO plm_rt_v2_callback VALUES (?,?,?,?,?,?,?,?, 'CONFIRMED',?)`,
 result:`INSERT INTO plm_ytq_v1_result VALUES (?,?,?,?,'private',0,'processed',?)`
});
export class D1Adapter{
 constructor(db){need(db&&typeof db.withSession==='function','D1_SESSION_REQUIRED');this.db=db.withSession('first-primary');this.stopped=false;this.writeStatements=0;}
 stmt(name,args){need(Object.hasOwn(SQL,name),'FIXED_QUERY_ONLY');return this.db.prepare(SQL[name]).bind(...args);}
 async read(name,args){need(!this.stopped,'ADAPTER_STOPPED');try{return await this.stmt(name,args).first();}catch{this.stopped=true;throw new Error('D1_READ_UNKNOWN');}}
 async batch(entries){need(!this.stopped&&entries.length<=2,'D1_BATCH_BOUND');this.writeStatements+=entries.length;
 try{const r=await this.db.batch(entries.map(([n,a])=>this.stmt(n,a)));need(r.length===entries.length&&r.every(x=>x.success===true&&x.meta?.changes===1),'D1_WRITE_UNKNOWN');return r;}catch{this.stopped=true;throw new Error('D1_WRITE_UNKNOWN_NO_RETRY');}}
}
export class Boundary{
 constructor(adapter){this.a=adapter;this.capabilities=new Map();this.stopped=false;}
 async enqueue(entry,now){
 need(!this.stopped&&entry&&Object.keys(entry).sort().join('|')==='account_id|fencing_token|intent_id|job_id|not_before|owner|owner_epoch|script_sha256'&&entry.account_id==='youtube_game_001'&&['job_id','intent_id','owner'].every(k=>id(entry[k]))&&sha(entry.script_sha256)&&[entry.owner_epoch,entry.fencing_token,entry.not_before,now].every(integer),'ENQUEUE_FIELDS');
 await this.a.batch([['enqueue',[entry.job_id,entry.account_id,entry.intent_id,entry.script_sha256,entry.owner,entry.owner_epoch,entry.fencing_token,entry.not_before,now,now]]]);
 }
 async eligible(now){need(!this.stopped&&integer(now));return this.a.read('eligible',[now]);}
 async claim(job,owner,epoch,fence,version,now){need(!this.stopped&&id(job)&&id(owner)&&[epoch,fence,version,now].every(integer),'CLAIM_FIELDS');await this.a.batch([['claim',[now,job,owner,epoch,fence,version]]]);return this.a.read('row',[job]);}
 async reserve(job,version,inputs,now){
 need(!this.stopped&&integer(now)&&integer(version),'STOP');const q=await this.a.read('row',[job]);
 need(q?.state==='CLAIMED'&&q.job_state==='ACTIVE'&&q.version===version,'STALE_CLAIM');
 // Inputs derived from the exact durable script by the integration adapter; no new production inputs.
 need(inputs?.job_id===job&&inputs.account_id===q.account_id&&inputs.privacy_status==='private'&&inputs.notify_subscribers==='false'&&inputs.scheduled_for===''&&typeof inputs.narration==='string'&&inputs.narration.length>0,'DISPATCH_INPUTS');
 const script=await this.a.read('script',[job]);
 need(script&&await hash(script.script_json)===q.script_sha256,'DURABLE_SCRIPT_HASH');
 let saved;try{saved=JSON.parse(script.script_json).dispatch_inputs;}catch{throw new Error('SCRIPT_MAPPING');}
 need(saved&&canonical(saved)===canonical(inputs),'SCRIPT_INPUT_BINDING');
 const payload={ref:TARGET.ref,inputs};const payloadHash=await hash(canonical(payload));
 const dispatch=await hash(canonical({job_id:job,account_id:q.account_id,script_sha256:q.script_sha256,payload_sha256:payloadHash}));
 await this.a.batch([['reserve',[dispatch,job,payloadHash]],['dispatched',[now,job,version]]]);
 this.capabilities.set(dispatch,{payload,q});return dispatch;
 }
 async mockSend(dispatch,transport,now,timeoutMs=30000){
 need(!this.stopped&&transport?.offlineMock===true&&typeof transport.send==='function'&&integer(now)&&integer(timeoutMs)&&timeoutMs<=30000,'OFFLINE_TRANSPORT_REQUIRED');
 const cap=this.capabilities.get(dispatch);need(cap,'NO_RESUME');this.capabilities.delete(dispatch);
 await this.a.batch([['sent',[dispatch]]]);
 let timer;try{const status=await Promise.race([Promise.resolve().then(()=>transport.send(TARGET,structuredClone(cap.payload))),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('TIMEOUT')),timeoutMs);})]);clearTimeout(timer);need(status===204,'NON204');return {accepted:true,uploadSucceeded:false,nextEligible:false};}
 catch{clearTimeout(timer);this.stopped=true;await this.a.batch([['unknownOut',[dispatch]],['unknownQueue',[now,cap.q.job_id]]]);throw new Error('UNKNOWN_PERMANENT_STOP');}
 }
 async callback(raw,signature,key,keyId,now){
 need(!this.stopped,'STOP');const b=await verifyCallback(raw,signature,key,keyId,now);const digest=await hash(raw);
 const prior=await this.a.read('replay',[b.result_id,b.job_id]);
 if(prior){need(prior.result_id===b.result_id&&prior.job_id===b.job_id&&prior.payload_sha256===digest,'REPLAY_CHANGED');return {replay:true};}
 const q=await this.a.read('row',[b.job_id]);const o=await this.a.read('outbox',[b.dispatch_id]);const r=await this.a.read('render',[b.job_id]);
 need(q?.state==='DISPATCHED'&&q.job_state==='ACTIVE'&&o?.job_id===b.job_id&&o.state==='SENT'&&o.send_attempts===1,'DISPATCH_BINDING');
 for(const k of ['job_id','account_id','intent_id','owner','owner_epoch','fencing_token','script_sha256'])need(q[k]===b[k],'QUEUE_BINDING');
 // Run/media binding MUST preexist in durable render/upload checkpoint, not trusted solely from callback.
 need(r&&r.render_run_id===b.run_id&&r.artifact_sha256===b.media_sha256&&r.script_sha256===b.script_sha256&&r.owner===b.owner&&r.owner_epoch===b.owner_epoch&&r.fencing_token===b.fencing_token&&r.quality_gate==='PASS'&&r.upload_state==='SENT','RENDER_RUN_BINDING');
 await this.a.batch([['callback',[r.delivery_id,b.result_id,b.job_id,b.account_id,b.owner_epoch,b.fencing_token,digest,b.result_id,now]],['result',[b.job_id,b.result_id,b.video_id,b.media_sha256,now]]]);
 return {resultSaved:true,queueComplete:true};
 }
}
// One message/one job offline orchestration. Never ACK upload success from HTTP 204.
export async function offlineBoundedTrigger(boundary,entry,inputs,transport,now){
 need(transport?.offlineMock===true&&integer(now),'OFFLINE_TRIGGER_ONLY');
 const eligible=await boundary.eligible(now);need(eligible?.job_id===entry.job_id,'NO_ELIGIBLE_JOB');
 const claimed=await boundary.claim(entry.job_id,entry.owner,entry.owner_epoch,entry.fencing_token,entry.version,now);
 const dispatch=await boundary.reserve(entry.job_id,claimed.version,inputs,now);
 return {...await boundary.mockSend(dispatch,transport,now),dispatch_id:dispatch,acknowledgeMessage:false};
}
export function offlineIngress(boundary,key,keyId,clock){
 return async request=>{
  try{
   need(request.method==='POST'&&new URL(request.url).pathname==='/youtube/result','INGRESS_ROUTE');
   need(request.headers.get('content-type')==='application/json','CONTENT_TYPE');
   const reader=request.body?.getReader();need(reader,'BODY_REQUIRED');let size=0;const chunks=[];
   while(true){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>8192){await reader.cancel();throw new Error('BODY_LIMIT');}chunks.push(value);}
   const bytes=new Uint8Array(size);let at=0;for(const chunk of chunks){bytes.set(chunk,at);at+=chunk.length;}
   const raw=new TextDecoder('utf-8',{fatal:true}).decode(bytes);
   await boundary.callback(raw,request.headers.get('x-plm-signature'),key,keyId,clock());
   return new Response('RESULT_SAVED',{status:200});
  }catch{return new Response('STOP_CALLBACK_REJECTED',{status:409});}
 };
}
// Deployable parked ingress. Gate activation requires a separately reviewed successor.
// No fetch(), cron, Queue consumer, or ambient secrets in the deploy bundle.
export default {
 async fetch(){return new Response('STOP_DEPLOYED_DISABLED',{status:503});},
 async scheduled(){throw new Error('TRIGGER_DISABLED');},
 async queue(){throw new Error('CONSUMER_DISABLED_NO_DISPATCH');}
};
