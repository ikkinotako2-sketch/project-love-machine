// Independent successor. Original runtime source remains byte-identical.
import {SpeakerBoundary} from './speaker-boundary.mjs';
import {successorRenderInputs} from './speaker-contract.mjs';
import {GenerationCheckpointAdapter,generationProof,enqueueGeneration} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/generation-adapter.mjs';
import {OperationGate} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/operation-gate.mjs';
import {SAFE_DEFAULTS,REMOTE_ACTIVATION_SUPPORTED,ensure,validateTarget,validateKeys,verifySources,bytesSha} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/runtime-contract.mjs';
import {hash,FIELDS} from '../readiness/sandbox-contract-fixture/serverless/youtube-live/worker.mjs';
import {canon,mapCheckpoint} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/mapping.mjs';
import {verifiedStage} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/checkpoint.mjs';
export function createLiveSpeakerComposition(){throw new Error('PREPARATION_ONLY_REMOTE_ACTIVATION_DISABLED');}
export async function createSpeakerComposition(options){
 ensure(options&&options.offlineOnly===true&&options.gate instanceof OperationGate,'OPERATION_GATE_REQUIRED');
 const successorPaths=['integration/speaker-boundary.mjs','integration/speaker-contract.mjs','integration/speaker-runtime.mjs'];
 ensure(options.successorManifest&&options.successorBytes&&Object.keys(options.successorManifest).sort().join('|')===successorPaths.slice().sort().join('|')&&Object.keys(options.successorBytes).sort().join('|')===successorPaths.slice().sort().join('|'),'SUCCESSOR_SOURCE_SET');
 ensure(await bytesSha(new TextEncoder().encode(canon(options.successorManifest)))===options.expectedSuccessorManifestSha,'SUCCESSOR_MANIFEST_SHA');
 for(const path of successorPaths)ensure(await bytesSha(options.successorBytes[path])===options.successorManifest[path],'SUCCESSOR_SOURCE_SHA');

 ensure(options.db&&typeof options.db.withSession==='function','DB_BINDING_REQUIRED');
 ensure(typeof options.provenance==='function'&&typeof options.admission?.reserve==='function','INDEPENDENT_PROVENANCE_ADMISSION_REQUIRED');
 ensure(typeof options.clock==='function'&&canon(options.flags)===canon(SAFE_DEFAULTS),'SAFE_FLAGS_REQUIRED');
 const target=validateTarget(options.target);await validateKeys(options.keys);
 await verifySources(options.sourceManifest,options.sourceBytes,options.expectedSourceManifestSha);
 ensure(options.transport?.offlineMock===true&&options.transport?.abortable===true&&typeof options.transport.send==='function'&&options.transport.key_id===options.keys.dispatch.id,'OFFLINE_TRANSPORT_ONLY');
 const keys=Object.fromEntries(Object.entries(options.keys).map(([r,k])=>[r,{...k,material:k.material.slice()}]));
 const transport={...options.transport,send:options.transport.send.bind(options.transport)};
 const policy=structuredClone(options.policy);
 const boundary=new SpeakerBoundary(new GenerationCheckpointAdapter(options.db),{repository:target.repository,workflow:target.workflow,ref:target.required_commit_sha,workflow_sha256:target.workflow_sha256},policy,options.renderContract);
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
  const signed=['BIND','RENDER','RESULT'].includes(d.operation_kind);
  if(signed){
   const proof=await options.provenance(d.pipeline_run_id,d.run_attempt,d.workflow_sha256,d.job_id);
   ensure(proof?.verified===true&&proof.run_id===d.pipeline_run_id&&proof.run_attempt===1&&proof.workflow_sha256===d.workflow_sha256&&proof.job_id===d.job_id,'INDEPENDENT_RUN_PROOF_STOP');
   await packet(d,envelope);
  }
  const replayDigest=d.operation_kind==='RESULT'?await hash(envelope.raw):null;
  const apply=async()=>{
   if(d.operation_kind==='ENQUEUE')return enqueueGeneration(boundary,d,envelope?.not_before,now);
   if(d.operation_kind==='DISPATCH'){
    ensure(options.accountBudgetFresh===true,'ACCOUNT_BUDGET_UNKNOWN_STOP');
    const day=new Date(clock()*1000).toISOString().slice(0,10);
    await options.admission.reserve(d.job_id,day,200);
    const s=await generationProof(boundary.a,d),q=await boundary.a.read('row',[d.job_id]);ensure(q?.state==='QUEUED'&&q.job_state==='ACTIVE','QUEUE_STATE_NO_RESEND');
    for(const k of ['owner','owner_epoch','fencing_token','script_sha256'])ensure(q[k]===d[k],'QUEUE_FENCE');
    ensure((await boundary.eligible(now))?.job_id===d.job_id,'QUEUE_NOT_ELIGIBLE');
    const inputs=await successorRenderInputs(s.script_json,d.script_sha256,d.job_id,policy,options.renderContract);
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
