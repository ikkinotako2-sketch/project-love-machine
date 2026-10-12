import {Boundary,SQL,need,hash,FIELDS} from '../youtube-live/worker.mjs';
import {mapCheckpoint,canon} from './mapping.mjs';
import {CHECKPOINT_SQL,saveStage} from './checkpoint.mjs';
import {abortableOneSend} from './dispatch.mjs';
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
export default {async fetch(){return new Response('STOP_DEPLOYED_DISABLED',{status:503});},async scheduled(){throw new Error('TRIGGER_DISABLED');},async queue(){throw new Error('CONSUMER_DISABLED');}};
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
