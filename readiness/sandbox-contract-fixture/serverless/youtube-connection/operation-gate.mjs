import {ensure,runtimeId,runtimeSha,runtimeInt,RUNTIME_ROUTES} from './runtime-contract.mjs';
import {canon} from './mapping.mjs';
import {hash} from '../youtube-live/worker.mjs';
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
