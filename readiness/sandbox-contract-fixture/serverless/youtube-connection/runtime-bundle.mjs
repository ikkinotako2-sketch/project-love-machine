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
const historicalParkedWorker = {
 async fetch(){return new Response('STOP_DEPLOYED_DISABLED',{status:503});},
 async scheduled(){throw new Error('TRIGGER_DISABLED');},
 async queue(){throw new Error('CONSUMER_DISABLED_NO_DISPATCH');}
};

// MODULE mapping.mjs
export function canon(value){if(Array.isArray(value))return '['+value.map(canon).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canon(value[k])).join(',')+'}';need(typeof value!=='number'||Number.isFinite(value),'JSON_FINITE');return JSON.stringify(value);}
export const PIPELINE_FIELDS='job_id account_id oauth_secret_name title hook narration speaker scenes_json captions_json bgm_json output_json description tags privacy_status scheduled_for made_for_kids contains_synthetic_media notify_subscribers'.split(' ').sort();
function text(x,n){need(typeof x==='string'&&x.trim().length>0&&x.length<=n&&!/[\x00-\x08\x0b-\x1f]/.test(x),'SCRIPT_TEXT');}
export async function mapCheckpoint(raw,expectedSha,job,policy){
 need(typeof raw==='string'&&new TextEncoder().encode(raw).length<=65536&&await hash(raw)===expectedSha,'SCRIPT_HASH');
 let s;try{s=JSON.parse(raw);}catch{throw new Error('SCRIPT_JSON');}
 need(Object.keys(s).sort().join('|')==='bgm|hook|narration|scenes|title','SCRIPT_FORMAT');
 text(s.title,100);text(s.hook,240);text(s.narration,4000);
 need(Array.isArray(s.scenes)&&s.scenes.length>=1&&s.scenes.length<=60,'SCENES');let prior=0;
 for(const v of s.scenes){need(Object.keys(v).sort().join('|')==='caption|emphasis_words|end|motion|sfx|start|visual_keyword','SCENE_FIELDS');need(Number.isFinite(v.start)&&Number.isFinite(v.end)&&v.start>=prior&&v.end>v.start&&v.end<=60,'SCENE_TIME');prior=v.end;text(v.caption,240);text(v.visual_keyword,240);need(['zoom_in','zoom_out','pan_left','pan_right','none'].includes(v.motion)&&['pop','none'].includes(v.sfx)&&Array.isArray(v.emphasis_words)&&v.emphasis_words.length<=10,'SCENE_STYLE');v.emphasis_words.forEach(x=>text(x,40));}
 need(s.bgm&&Object.keys(s.bgm).sort().join('|')==='mood|volume'&&Number.isFinite(s.bgm.volume)&&s.bgm.volume>=0&&s.bgm.volume<=1,'BGM');text(s.bgm.mood,40);
 // Audience/disclosure decisions must be explicit trusted policy, never model output.
 need(policy&&typeof policy.made_for_kids==='boolean'&&typeof policy.contains_synthetic_media==='boolean','EXPLICIT_POLICY');
 const inputs={job_id:job,account_id:'youtube_game_001',oauth_secret_name:'PLM_YOUTUBE_GAME_001',title:s.title,hook:s.hook,narration:s.narration,speaker:'1',scenes_json:JSON.stringify(s.scenes),captions_json:JSON.stringify(s.scenes.map((v,i)=>({index:i+1,start_seconds:v.start,end_seconds:v.end,text:v.caption}))),bgm_json:JSON.stringify(s.bgm),output_json:JSON.stringify({format:'mp4',width:1080,height:1920,fps:30}),description:'',tags:'game,shorts',privacy_status:'private',scheduled_for:'',made_for_kids:policy.made_for_kids,contains_synthetic_media:policy.contains_synthetic_media,notify_subscribers:false};
 need(Object.keys(inputs).sort().join('|')===PIPELINE_FIELDS.join('|')&&JSON.stringify(inputs).length<=65535,'PIPELINE_CONTRACT');return inputs;
}

// MODULE dispatch.mjs
export function liveDispatchCandidate(fetchImpl,credential,{timeoutMs=30000}={}){
 need(typeof fetchImpl==='function'&&typeof credential==='string'&&credential.length>0&&Number.isSafeInteger(timeoutMs)&&timeoutMs>=1&&timeoutMs<=30000,'TRANSPORT_CONFIGURATION');
 // Dependency injection only. No global fetch or environment lookup.
 return {abortable:true,async send(target,payload,signal){
  need(signal instanceof AbortSignal&&!signal.aborted&&/^[a-f0-9]{40}$/.test(target.ref)&&payload.ref===target.ref&&target.repository==='ikkinotako2-sketch/project-love-machine'&&target.workflow==='.github/workflows/youtube-pipeline.yml','EXACT_TARGET');
  const url='https://api.github.com/repos/'+target.repository+'/actions/workflows/youtube-pipeline.yml/dispatches';
  const response=await fetchImpl(url,{method:'POST',redirect:'error',signal,headers:{'Authorization':'Bearer '+credential,'Accept':'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'},body:canon(payload)});
  if(response.body)await response.body.cancel();return response.status;
 },timeoutMs};
}
export async function abortableOneSend(boundary,dispatch,transport,now){
 need(!boundary.stopped&&transport?.abortable===true&&typeof transport.send==='function'&&Number.isSafeInteger(now)&&now>0,'SEND_CONFIGURATION');
 const cap=boundary.capabilities.get(dispatch);need(cap,'NO_RESUME');boundary.capabilities.delete(dispatch);
 await boundary.a.batch([['sent',[dispatch]]]);
 const controller=new AbortController();const timeout=transport.timeoutMs??30000;need(Number.isSafeInteger(timeout)&&timeout>=1&&timeout<=30000,'TIMEOUT_BOUND');let timer;
 try{
  const status=await Promise.race([Promise.resolve().then(()=>{need(!controller.signal.aborted,'ABORTED_BEFORE_SEND');return transport.send(boundary.target,structuredClone(cap.payload),controller.signal);}),new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(new Error('TIMEOUT'));},timeout);})]);
  clearTimeout(timer);need(status===204,'NON204');return {accepted:true,uploadSucceeded:false,nextEligible:false};
 }catch{
  clearTimeout(timer);controller.abort();boundary.stopped=true;
  await boundary.a.batch([['unknownOut',[dispatch]],['unknownQueue',[now,cap.q.job_id]]]);throw new Error('UNKNOWN_ABORTED_NO_RETRY');
 }
}

// MODULE checkpoint.mjs
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

// MODULE sender.mjs
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

// MODULE connection.mjs
export const CONNECTION_SQL={...SQL,...CHECKPOINT_SQL};
export class CheckpointD1Adapter{
 constructor(db){need(db&&typeof db.withSession==='function','D1_REQUIRED');this.db=db.withSession('first-primary');this.stopped=false;this.writeStatements=0;}
 stmt(n,a){need(Object.hasOwn(CONNECTION_SQL,n),'FIXED_QUERY_ONLY');return this.db.prepare(CONNECTION_SQL[n]).bind(...a);}
 async read(n,a){need(!this.stopped,'D1_STOPPED');try{return await this.stmt(n,a).first();}catch{this.stopped=true;throw new Error('D1_READ_UNKNOWN');}}
 async batch(entries){need(!this.stopped&&entries.length>=1&&entries.length<=4,'BATCH_MAX4');this.writeStatements+=entries.length;try{const r=await this.db.batch(entries.map(([n,a])=>this.stmt(n,a)));need(r.length===entries.length&&r.every(x=>x.success===true&&x.meta?.changes===1),'D1_AMBIGUOUS');return r;}catch{this.stopped=true;throw new Error('D1_WRITE_UNKNOWN_NO_RETRY');}}
}
export class ConnectionBoundary extends Boundary{
 constructor(a,target,policy){super(a);need(target.repository==='ikkinotako2-sketch/project-love-machine'&&target.workflow==='.github/workflows/youtube-pipeline.yml'&&/^[a-f0-9]{40}$/.test(target.ref)&&/^[a-f0-9]{64}$/.test(target.workflow_sha256),'FIXED_TARGET');this.target=Object.freeze({...target});this.policy=Object.freeze({...policy});}
 async reserve(job,version,inputs,now){
  need(!this.stopped&&Number.isSafeInteger(now)&&now>0);const q=await this.a.read('row',[job]);need(q?.state==='CLAIMED'&&q.job_state==='ACTIVE'&&q.version===version,'CLAIM');
  const script=await this.a.read('script',[job]);need(script,'CHECKPOINT_REQUIRED');
  const mapped=await mapCheckpoint(script.script_json,q.script_sha256,job,this.policy);need(canon(mapped)===canon(inputs),'EXACT_INPUT_MAPPING');
  const dispatch=await hash(canon({account_id:q.account_id,job_id:job,script_sha256:q.script_sha256,production_ref:this.target.ref,workflow_sha256:this.target.workflow_sha256}));
  const context={account_id:q.account_id,intent_id:q.intent_id,job_id:job,owner:q.owner,owner_epoch:q.owner_epoch,fencing_token:q.fencing_token,dispatch_id:dispatch,script_sha256:q.script_sha256,workflow_sha256:this.target.workflow_sha256,production_ref:this.target.ref};
  const payload={ref:this.target.ref,inputs:{...mapped,serverless_context:canon(context)}};need(new TextEncoder().encode(canon(payload)).length<=65535,'DISPATCH_SIZE');
  await this.a.batch([['reserve',[dispatch,job,await hash(canon(payload))]],['dispatched',[now,job,version]]]);this.capabilities.set(dispatch,{payload,q});return {dispatch_id:dispatch,payload:structuredClone(payload),context};
 }
 async send(dispatch,transport,now){return abortableOneSend(this,dispatch,transport,now);}
 async stage(raw,sig,key,keyId,now){return saveStage(this,raw,sig,key,keyId,now);}
 async callback(raw,signature,key,keyId,now){
  need(!this.stopped,'STOP');let b;try{b=JSON.parse(raw);}catch{throw new Error('JSON');}
  need(typeof raw==='string'&&new TextEncoder().encode(raw).length<=8192&&b&&Object.keys(b).sort().join('|')===FIELDS.join('|')&&canon(b)===raw,'EXACT_CALLBACK');
  need(b.protocol==='plm-youtube-result-v2'&&b.key_id===keyId&&b.account_id==='youtube_game_001'&&b.workflow_sha256===this.target.workflow_sha256&&b.run_attempt===1&&typeof b.run_id==='string'&&/^[1-9][0-9]{0,19}$/.test(b.run_id),'CALLBACK_SCOPE');
  need(Number.isSafeInteger(now)&&now>0&&Number.isSafeInteger(b.issued_at)&&b.issued_at>0&&now-b.issued_at<=300&&b.issued_at-now<=30,'CALLBACK_SKEW');
  need(['intent_id','job_id','owner','result_id'].every(k=>typeof b[k]==='string'&&/^[A-Za-z0-9_-]{1,64}$/.test(b[k]))&&['owner_epoch','fencing_token'].every(k=>Number.isSafeInteger(b[k])&&b[k]>0),'CALLBACK_IDENTITY');
  need(['dispatch_id','script_sha256','media_sha256'].every(k=>typeof b[k]==='string'&&/^[a-f0-9]{64}$/.test(b[k]))&&b.privacy_status==='private'&&b.notify_subscribers===false&&b.processing_status==='processed'&&b.quality_gate==='PASS'&&typeof b.video_id==='string'&&/^[A-Za-z0-9_-]{11}$/.test(b.video_id),'PRIVATE_QG');
  need(key instanceof Uint8Array&&key.length>=32&&typeof signature==='string'&&/^[a-f0-9]{64}$/.test(signature),'CALLBACK_KEY');
  const k=await crypto.subtle.importKey('raw',key,{name:'HMAC',hash:'SHA-256'},false,['verify']);need(await crypto.subtle.verify('HMAC',k,Uint8Array.from(signature.match(/../g),s=>parseInt(s,16)),new TextEncoder().encode('plm-youtube-result-v2\n'+raw)),'SIGNATURE');
  const digest=await hash(raw);const prior=await this.a.read('replay',[b.result_id,b.job_id]);if(prior){need(prior.result_id===b.result_id&&prior.job_id===b.job_id&&prior.payload_sha256===digest,'REPLAY_CHANGED');return {replay:true};}
  const q=await this.a.read('row',[b.job_id]);const o=await this.a.read('outbox',[b.dispatch_id]);const r=await this.a.read('render',[b.job_id]);const bind=await this.a.read('binding',[b.job_id]);
  need(q?.state==='DISPATCHED'&&q.job_state==='ACTIVE'&&o?.job_id===b.job_id&&o.state==='SENT'&&o.send_attempts===1,'DISPATCH_BINDING');
  for(const field of ['account_id','intent_id','owner','owner_epoch','fencing_token','script_sha256'])need(q[field]===b[field],'QUEUE_BINDING');
  need(bind&&bind.pipeline_run_id===b.run_id&&bind.render_run_id===r?.render_run_id&&bind.dispatch_id===b.dispatch_id&&bind.workflow_sha256===b.workflow_sha256&&bind.dispatch_payload_sha256===o.payload_sha256&&r.artifact_sha256===b.media_sha256&&r.script_sha256===b.script_sha256&&r.owner===b.owner&&r.owner_epoch===b.owner_epoch&&r.fencing_token===b.fencing_token&&r.quality_gate==='PASS'&&r.upload_state==='SENT','PREEXISTING_CHECKPOINT_BINDING');
  await this.a.batch([['callback',[r.delivery_id,b.result_id,b.job_id,b.account_id,b.owner_epoch,b.fencing_token,digest,b.result_id,now]],['result',[b.job_id,b.result_id,b.video_id,b.media_sha256,now]]]);
  const saved=await this.a.read('row',[b.job_id]);const out=await this.a.read('outbox',[b.dispatch_id]);need(saved.state==='COMPLETE'&&saved.job_state==='SUCCEEDED'&&out.state==='CONFIRMED','ATOMIC_READBACK');return {resultSaved:true,queueComplete:true};
 }
}
const inheritedParkedConnection = {async fetch(){return new Response('STOP_DEPLOYED_DISABLED',{status:503});},async scheduled(){throw new Error('TRIGGER_DISABLED');},async queue(){throw new Error('CONSUMER_DISABLED');}};
export function candidateIngress(boundary,keys,clock){
 return async request=>{
  try{
   const path=new URL(request.url).pathname;need(request.method==='POST'&&['/youtube/checkpoint','/youtube/result'].includes(path)&&request.headers.get('content-type')==='application/json','ROUTE');
   need(keys.checkpoint instanceof Uint8Array&&keys.callback instanceof Uint8Array&&await hash(new TextDecoder().decode(keys.checkpoint))!==await hash(new TextDecoder().decode(keys.callback)),'INDEPENDENT_KEYS');
   const reader=request.body?.getReader();need(reader,'BODY');let count=0;const chunks=[];
   while(true){const {done,value}=await reader.read();if(done)break;count+=value.length;if(count>8192){await reader.cancel();throw new Error('BODY_LIMIT');}chunks.push(value);}
   const bytes=new Uint8Array(count);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
   const raw=new TextDecoder('utf-8',{fatal:true}).decode(bytes);const sig=request.headers.get('x-plm-signature');
   if(path==='/youtube/checkpoint')await boundary.stage(raw,sig,keys.checkpoint,keys.checkpointId,clock());else await boundary.callback(raw,sig,keys.callback,keys.callbackId,clock());
   return new Response('DURABLE_ACCEPTED',{status:200});
  }catch{return new Response('STOP_REJECTED',{status:409});}
 };
}
export async function boundedQueueCandidate(boundary,messages,transport,now){
 need(Array.isArray(messages)&&messages.length===1&&messages[0]&&Object.keys(messages[0]).sort().join('|')==='account_id|job_id'&&messages[0].account_id==='youtube_game_001','QUEUE_MAX_ONE_EXACT_SCOPE');
 const job=messages[0].job_id;const q=await boundary.a.read('row',[job]);need(q&&q.account_id===messages[0].account_id,'QUEUE_IDENTITY');
 if(q.state==='COMPLETE')return {acknowledgeMessage:true,dispatchSends:0};
 need(q.state==='QUEUED'&&q.job_state==='ACTIVE'&&!boundary.stopped,'QUEUE_UNKNOWN_OR_CONSUMED_STOP');
 const eligible=await boundary.eligible(now);need(eligible?.job_id===job,'QUEUE_NOT_ELIGIBLE');
 const s=await boundary.a.read('script',[job]);const inputs=await mapCheckpoint(s.script_json,q.script_sha256,job,boundary.policy);
 const claimed=await boundary.claim(job,q.owner,q.owner_epoch,q.fencing_token,q.version,now);const receipt=await boundary.reserve(job,claimed.version,inputs,now);
 const accepted=await boundary.send(receipt.dispatch_id,transport,now);return {...accepted,receipt,acknowledgeMessage:false,dispatchSends:1};
}

// SUCCESSOR MODULE runtime-contract.mjs
// Preparation-only composition. No ambient credential, target, DB, clock or transport.
export const REMOTE_ACTIVATION_SUPPORTED=false;
export const SAFE_DEFAULTS=Object.freeze({TEST_ONLY:true,DRY_RUN:true,NO_PUBLISH:true,EMERGENCY_STOP:true});
export const RUNTIME_ROUTES=Object.freeze({ENQUEUE:null,DISPATCH:null,BIND:'/youtube/checkpoint',RENDER:'/youtube/checkpoint',RESULT:'/youtube/result'});
export const ROLE_ENV=Object.freeze({dispatch:'PLM_GITHUB_DISPATCH_TOKEN',checkpoint:'PLM_YOUTUBE_CHECKPOINT_KEY',callback:'PLM_YOUTUBE_RESULT_CALLBACK_KEY'});
export const SOURCE_FILES=Object.freeze(['serverless/youtube-live/worker.mjs',...['connection.mjs','checkpoint.mjs','dispatch.mjs','mapping.mjs','sender.mjs','bundle.mjs','runtime-contract.mjs','operation-gate.mjs','generation-adapter.mjs','runtime.mjs','runtime-bundle.mjs'].map(x=>'serverless/youtube-connection/'+x)]);
export const ensure=(condition,code)=>{if(!condition)throw new Error(code);};
export const runtimeId=x=>typeof x==='string'&&/^[A-Za-z0-9_-]{1,96}$/.test(x);
export const runtimeSha=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
export const runtimeInt=x=>Number.isSafeInteger(x)&&x>0;
export async function bytesSha(bytes){ensure(bytes instanceof Uint8Array,'BYTES_REQUIRED');return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');}
export async function verifySources(manifest,bytes,expectedDigest){
 ensure(manifest&&bytes&&runtimeSha(expectedDigest),'SOURCE_MANIFEST_REQUIRED');
 ensure(Object.keys(manifest).sort().join('|')===SOURCE_FILES.slice().sort().join('|')&&Object.keys(bytes).sort().join('|')===Object.keys(manifest).sort().join('|'),'SOURCE_SET');
 const canonical=JSON.stringify(Object.fromEntries(Object.keys(manifest).sort().map(k=>[k,manifest[k]])));
 ensure(await bytesSha(new TextEncoder().encode(canonical))===expectedDigest,'SOURCE_MANIFEST_DRIFT');
 for(const path of SOURCE_FILES)ensure(runtimeSha(manifest[path])&&await bytesSha(bytes[path])===manifest[path],'SOURCE_DRIFT');
}
export function validateTarget(t){
 const fields='repository workflow workflow_sha256 sender_path sender_sha256 candidate_entrypoint_path candidate_sha256 required_commit_sha run_attempt privacy notify_subscribers approval_status'.split(' ').sort();
 ensure(t&&Object.keys(t).sort().join('|')===fields.join('|'),'EXACT_TARGET_REQUIRED');
 ensure(t.repository==='ikkinotako2-sketch/project-love-machine'&&t.workflow==='.github/workflows/youtube-pipeline.yml'&&/^[a-f0-9]{40}$/.test(t.required_commit_sha),'EXACT_TARGET_REF');
 ensure(t.sender_path==='plm/entrypoints/yt_serverless_candidate.py'&&t.candidate_entrypoint_path===t.sender_path&&runtimeSha(t.workflow_sha256)&&runtimeSha(t.sender_sha256)&&t.candidate_sha256===t.sender_sha256,'TARGET_HASH');
 ensure(t.run_attempt===1&&t.privacy==='private'&&t.notify_subscribers===false,'PRIVATE_ATTEMPT1_ONLY');
 ensure(t.approval_status==='OFFLINE_CANDIDATE','OFFLINE_TARGET_ONLY');return structuredClone(t);
}
export async function validateKeys(keys){
 ensure(keys&&Object.keys(keys).sort().join('|')==='callback|checkpoint|dispatch','KEY_ROLES_REQUIRED');
 const ids=new Set(),digests=new Set();
 for(const role of ['dispatch','checkpoint','callback']){
  const k=keys[role];ensure(k&&k.role===role&&runtimeId(k.id)&&k.required_env===ROLE_ENV[role]&&k.material instanceof Uint8Array&&k.material.length>=32,'KEY_ROLE_OR_MATERIAL');
  ensure(k.material_class==='INJECTED_NON_FIXTURE'&&!/PUBLIC_|FIXTURE|TEST_KEY/i.test(new TextDecoder().decode(k.material)),'FIXTURE_KEY_REJECTED');
  const digest=await bytesSha(k.material);ensure(!ids.has(k.id)&&!digests.has(digest),'INDEPENDENT_KEY_ROLES');ids.add(k.id);digests.add(digest);
 }
}

// SUCCESSOR MODULE operation-gate.mjs
export const OP_FIELDS='operation_id operation_kind job_id intent_id account_id owner owner_epoch fencing_token script_sha256 media_sha256 dispatch_id dispatch_payload_sha256 bind_payload_sha256 pipeline_run_id run_attempt expected_state target workflow_sha256 sender_sha256 callback_key_id checkpoint_key_id dispatch_key_id route created_at expires_at consumed_state source_manifest_sha256'.split(' ').sort();
const STATES=Object.freeze({ENQUEUE:'ACTIVE',DISPATCH:'QUEUED',BIND:'DISPATCHED',RENDER:'DISPATCHED',RESULT:'DISPATCHED'});
// Offline reference ledger only. A future durable atomic ledger is a separate deployment dependency.
export class OfflineOperationLedger{
 #records=new Map();offlineOnly=true;
 async consume(id,fingerprint){if(this.#records.has(id))return false;this.#records.set(id,{fingerprint,state:'CONSUMED'});return true;}
 async lookup(id){const r=this.#records.get(id);return r?structuredClone(r):null;}
 async seal(id,fingerprint,state,replayDigest=null){const r=this.#records.get(id);ensure(r&&r.fingerprint===fingerprint&&r.state==='CONSUMED','LEDGER_UNKNOWN_STOP_NO_RESEND');this.#records.set(id,{fingerprint,state,replayDigest});}
}
export class OperationGate{
 #ledger;#clock;
 constructor(ledger,clock){ensure(ledger&&ledger.offlineOnly===true&&['consume','lookup','seal'].every(k=>typeof ledger[k]==='function')&&typeof clock==='function','ATOMIC_OPERATION_LEDGER_REQUIRED');this.#ledger=ledger;this.#clock=clock;}
 validate(d,target,keys,sourceDigest){
  const now=this.#clock();ensure(d&&Object.keys(d).sort().join('|')===OP_FIELDS.join('|'),'OPERATION_DESCRIPTOR_REQUIRED');
  ensure(Object.hasOwn(STATES,d.operation_kind)&&d.expected_state===STATES[d.operation_kind]&&runtimeId(d.operation_id),'OPERATION_STATE');
  ensure(['job_id','intent_id','owner'].every(k=>runtimeId(d[k]))&&d.account_id==='youtube_game_001'&&[d.owner_epoch,d.fencing_token].every(runtimeInt),'OPERATION_IDENTITY');
  ensure(runtimeInt(now)&&runtimeInt(d.created_at)&&runtimeInt(d.expires_at)&&d.created_at<=now&&now<d.expires_at&&d.expires_at-d.created_at<=300,'OPERATION_EXPIRED_OR_CLOCK');
  ensure(d.run_attempt===1&&d.workflow_sha256===target.workflow_sha256&&d.sender_sha256===target.sender_sha256&&canon(d.target)===canon(target)&&d.source_manifest_sha256===sourceDigest,'OPERATION_TARGET_HASH');
  ensure(d.dispatch_key_id===keys.dispatch.id&&d.checkpoint_key_id===keys.checkpoint.id&&d.callback_key_id===keys.callback.id&&d.route===RUNTIME_ROUTES[d.operation_kind],'OPERATION_KEY_ROUTE');
  ensure(['script_sha256','dispatch_id','dispatch_payload_sha256'].every(k=>runtimeSha(d[k])),'OPERATION_HASH');
  if(['BIND','RENDER','RESULT'].includes(d.operation_kind))ensure(typeof d.pipeline_run_id==='string'&&/^[1-9][0-9]{0,19}$/.test(d.pipeline_run_id)&&runtimeSha(d.bind_payload_sha256),'OPERATION_RUN_BINDING');
  else ensure(d.pipeline_run_id===null&&d.bind_payload_sha256===null,'NO_EARLY_RUN_BINDING');
  if(['RENDER','RESULT'].includes(d.operation_kind))ensure(runtimeSha(d.media_sha256),'MEDIA_SHA_REQUIRED');else ensure(d.media_sha256===null,'NO_EARLY_MEDIA');
  ensure(['FRESH','CONSUMED'].includes(d.consumed_state),'STOP_NO_RESEND');return now;
 }
 async execute(d,action,{replayDigest=null,replay=null}={}){
  const fingerprint=await hash(canon(Object.fromEntries(Object.entries(d).filter(([k])=>k!=='consumed_state'))));
  const old=await this.#ledger.lookup(d.operation_id);
  if(old){ensure(old.fingerprint===fingerprint,'OPERATION_REPLAY_CHANGED');ensure(old.state==='CONFIRMED'&&d.operation_kind==='RESULT'&&runtimeSha(replayDigest)&&old.replayDigest===replayDigest&&typeof replay==='function','CONSUMED_OR_UNKNOWN_STOP_NO_RESEND');return replay();}
  ensure(d.consumed_state==='FRESH','ALREADY_CONSUMED');ensure(await this.#ledger.consume(d.operation_id,fingerprint),'ATOMIC_CONSUMPTION_LOST');
  try{const out=await action();await this.#ledger.seal(d.operation_id,fingerprint,'CONFIRMED',replayDigest);return out;}
  catch{try{await this.#ledger.seal(d.operation_id,fingerprint,'UNKNOWN');}catch{}throw new Error('OPERATION_UNKNOWN_STOP_NO_RESEND');}
 }
}

// SUCCESSOR MODULE generation-adapter.mjs
export const GENERATION_SQL=`SELECT j.*,s.state AS script_state,s.script_sha256,s.script_json,s.owner AS script_owner,s.owner_epoch AS script_epoch,s.fencing_token AS script_fence,e.state AS generation_state,e.owner AS generation_owner,e.owner_epoch AS generation_epoch,e.fencing_token AS generation_fence FROM plm_rt_v2_job j JOIN plm_rt_v2_script s ON s.job_id=j.job_id JOIN plm_rt_v2_effect e ON e.job_id=j.job_id AND e.kind='GENERATION' WHERE j.job_id=?`;
export class GenerationCheckpointAdapter extends CheckpointD1Adapter{
 stmt(n,args){ensure(Object.hasOwn(CONNECTION_SQL,n)||n==='generation','FIXED_QUERY_ONLY');return this.db.prepare(n==='generation'?GENERATION_SQL:CONNECTION_SQL[n]).bind(...args);}
}
export async function generationProof(adapter,d){
 const row=await adapter.read('generation',[d.job_id]);
 ensure(row&&row.state==='ACTIVE'&&row.script_state==='COMPLETED'&&row.generation_state==='CONFIRMED','GENERATION_CHECKPOINT_INCOMPLETE');
 for(const k of ['job_id','intent_id','account_id','owner','owner_epoch','fencing_token','script_sha256'])ensure(row[k]===d[k],'GENERATION_IDENTITY');
 ensure(row.script_owner===d.owner&&row.generation_owner===d.owner&&row.script_epoch===d.owner_epoch&&row.generation_epoch===d.owner_epoch&&row.script_fence===d.fencing_token&&row.generation_fence===d.fencing_token&&await hash(row.script_json)===d.script_sha256,'GENERATION_SCRIPT_FENCE');return row;
}
export async function enqueueGeneration(boundary,d,notBefore,now){
 ensure(Number.isSafeInteger(notBefore)&&notBefore>0,'QUEUE_TIME');await generationProof(boundary.a,d);
 const entry=Object.fromEntries(['job_id','account_id','intent_id','script_sha256','owner','owner_epoch','fencing_token'].map(k=>[k,d[k]]));entry.not_before=notBefore;
 const prior=await boundary.a.read('row',[d.job_id]);
 if(prior){ensure(prior.state==='QUEUED'&&Object.keys(entry).every(k=>prior[k]===entry[k]),'ENQUEUE_DUPLICATE_CHANGED');return {enqueueNoop:true};}
 await boundary.enqueue(entry,now);return {enqueued:true};
}

// SUCCESSOR MODULE runtime.mjs
export function createLiveComposition(){throw new Error('PREPARATION_ONLY_REMOTE_ACTIVATION_DISABLED');}
export async function createOfflineComposition(options){
 ensure(options&&options.offlineOnly===true&&options.gate instanceof OperationGate,'OPERATION_GATE_REQUIRED');
 ensure(options.db&&typeof options.db.withSession==='function','DB_BINDING_REQUIRED');
 ensure(typeof options.clock==='function'&&canon(options.flags)===canon(SAFE_DEFAULTS),'SAFE_FLAGS_REQUIRED');
 const target=validateTarget(options.target);await validateKeys(options.keys);
 await verifySources(options.sourceManifest,options.sourceBytes,options.expectedSourceManifestSha);
 ensure(options.transport?.offlineMock===true&&options.transport?.abortable===true&&typeof options.transport.send==='function'&&options.transport.key_id===options.keys.dispatch.id,'OFFLINE_TRANSPORT_ONLY');
 const keys=Object.fromEntries(Object.entries(options.keys).map(([r,k])=>[r,{...k,material:k.material.slice()}]));
 const transport={...options.transport,send:options.transport.send.bind(options.transport)};
 const policy=structuredClone(options.policy);
 const boundary=new ConnectionBoundary(new GenerationCheckpointAdapter(options.db),{repository:target.repository,workflow:target.workflow,ref:target.required_commit_sha,workflow_sha256:target.workflow_sha256},policy);
 const sourceDigest=options.expectedSourceManifestSha,gate=options.gate,clock=options.clock;
 async function packet(d,envelope){
  ensure(envelope&&typeof envelope.raw==='string'&&new TextEncoder().encode(envelope.raw).length<=8192,'BODY_LIMIT');
  let b;if(d.operation_kind==='RESULT'){
   try{b=JSON.parse(envelope.raw);}catch{throw new Error('CALLBACK_JSON');}ensure(b&&Object.keys(b).sort().join('|')===FIELDS.join('|')&&canon(b)===envelope.raw,'EXACT_CALLBACK');
   const k=await crypto.subtle.importKey('raw',keys.callback.material,{name:'HMAC',hash:'SHA-256'},false,['verify']);
   ensure(typeof envelope.signature==='string'&&/^[a-f0-9]{64}$/.test(envelope.signature)&&await crypto.subtle.verify('HMAC',k,Uint8Array.from(envelope.signature.match(/../g),s=>parseInt(s,16)),new TextEncoder().encode('plm-youtube-result-v2\n'+envelope.raw)),'CALLBACK_SIGNATURE');
   ensure(b.protocol==='plm-youtube-result-v2'&&b.key_id===keys.callback.id&&b.privacy_status==='private'&&b.notify_subscribers===false,'CALLBACK_ROLE_PRIVATE');
  }else{b=await verifiedStage(envelope.raw,envelope.signature,keys.checkpoint.material,keys.checkpoint.id,clock());ensure(b.event===(d.operation_kind==='BIND'?'bind':'render'),'STAGE_EVENT');}
  for(const field of ['job_id','intent_id','account_id','owner','owner_epoch','fencing_token','dispatch_id','script_sha256','workflow_sha256','run_attempt'])ensure(b[field]===d[field],'PACKET_IDENTITY');
  ensure(b.run_id===d.pipeline_run_id,'PIPELINE_RUN');
  if(d.operation_kind==='BIND')ensure(await hash(envelope.raw)===d.bind_payload_sha256&&b.dispatch_payload_sha256===d.dispatch_payload_sha256,'BIND_PAYLOAD');
  if(d.operation_kind==='RENDER')ensure(b.media_sha256===d.media_sha256&&b.dispatch_payload_sha256===d.dispatch_payload_sha256,'RENDER_PAYLOAD');
  if(d.operation_kind==='RESULT')ensure(b.media_sha256===d.media_sha256,'RESULT_MEDIA');return b;
 }
 async function exactExistingBinding(d){
  const bind=await boundary.a.read('binding',[d.job_id]);
  ensure(bind&&bind.dispatch_id===d.dispatch_id&&bind.pipeline_run_id===d.pipeline_run_id&&bind.render_run_id===d.pipeline_run_id&&bind.run_attempt===1&&bind.workflow_sha256===d.workflow_sha256&&bind.dispatch_payload_sha256===d.dispatch_payload_sha256&&bind.bind_payload_sha256===d.bind_payload_sha256,'PREEXISTING_BINDING_REQUIRED');
 }
 async function run(input,envelope=null){
  const d=structuredClone(input),now=gate.validate(d,target,keys,sourceDigest);
  const signed=['BIND','RENDER','RESULT'].includes(d.operation_kind);if(signed)await packet(d,envelope);
  const replayDigest=d.operation_kind==='RESULT'?await hash(envelope.raw):null;
  const apply=async()=>{
   if(d.operation_kind==='ENQUEUE')return enqueueGeneration(boundary,d,envelope?.not_before,now);
   if(d.operation_kind==='DISPATCH'){
    const s=await generationProof(boundary.a,d),q=await boundary.a.read('row',[d.job_id]);ensure(q?.state==='QUEUED'&&q.job_state==='ACTIVE','QUEUE_STATE_NO_RESEND');
    for(const k of ['owner','owner_epoch','fencing_token','script_sha256'])ensure(q[k]===d[k],'QUEUE_FENCE');
    ensure((await boundary.eligible(now))?.job_id===d.job_id,'QUEUE_NOT_ELIGIBLE');
    const inputs=await mapCheckpoint(s.script_json,d.script_sha256,d.job_id,policy);
    const dispatch=await hash(canon({account_id:d.account_id,job_id:d.job_id,script_sha256:d.script_sha256,production_ref:target.required_commit_sha,workflow_sha256:target.workflow_sha256}));
    const context={account_id:d.account_id,intent_id:d.intent_id,job_id:d.job_id,owner:d.owner,owner_epoch:d.owner_epoch,fencing_token:d.fencing_token,dispatch_id:dispatch,script_sha256:d.script_sha256,workflow_sha256:target.workflow_sha256,production_ref:target.required_commit_sha};
    ensure(dispatch===d.dispatch_id&&await hash(canon({ref:target.required_commit_sha,inputs:{...inputs,serverless_context:canon(context)}}))===d.dispatch_payload_sha256,'DISPATCH_PAYLOAD_BINDING');
    const claimed=await boundary.claim(d.job_id,d.owner,d.owner_epoch,d.fencing_token,q.version,now);
    const receipt=await boundary.reserve(d.job_id,claimed.version,inputs,now);
    return {...await boundary.send(receipt.dispatch_id,transport,now),receipt};
   }
   if(d.operation_kind==='BIND'){ensure(!(await boundary.a.read('binding',[d.job_id])),'DUPLICATE_BINDING');return boundary.stage(envelope.raw,envelope.signature,keys.checkpoint.material,keys.checkpoint.id,now);}
   await exactExistingBinding(d);
   if(d.operation_kind==='RENDER')return boundary.stage(envelope.raw,envelope.signature,keys.checkpoint.material,keys.checkpoint.id,now);
   return boundary.callback(envelope.raw,envelope.signature,keys.callback.material,keys.callback.id,now);
  };
  return gate.execute(d,apply,{replayDigest,replay:async()=>{await exactExistingBinding(d);const out=await boundary.callback(envelope.raw,envelope.signature,keys.callback.material,keys.callback.id,now);ensure(out.replay===true,'RESULT_REPLAY_ONLY');return out;}});
 }
 return Object.freeze({run,remoteActivationSupported:REMOTE_ACTIVATION_SUPPORTED});
}
// No activation branch, no env access, no ambient fetch. All flags/config remain parked.
export default {async fetch(){return new Response('PARKED_RUNTIME_COMPOSITION',{status:503});},async scheduled(){throw new Error('CRON_DISABLED');},async queue(){throw new Error('QUEUE_CONSUMER_DISABLED');}};
