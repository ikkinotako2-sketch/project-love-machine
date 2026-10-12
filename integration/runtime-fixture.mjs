import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {readFileSync} from 'node:fs';
import worker,{createOfflineComposition,createLiveComposition} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/runtime.mjs';
import {OperationGate,OfflineOperationLedger} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/operation-gate.mjs';
import {SAFE_DEFAULTS,SOURCE_FILES,ROLE_ENV} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/runtime-contract.mjs';
import {hash} from '../readiness/sandbox-contract-fixture/serverless/youtube-live/worker.mjs';
import {canon,mapCheckpoint} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/mapping.mjs';
import {signedStage} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/checkpoint.mjs';
import {callbackPayload,signCallback} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/sender.mjs';
const script={title:'ゲーム',hook:'冒頭',narration:'テスト台本',scenes:[{start:0,end:5,caption:'字幕',visual_keyword:'game',motion:'none',sfx:'none',emphasis_words:[]}],bgm:{mood:'calm',volume:0.2}};
const policy={made_for_kids:false,contains_synthetic_media:true};
const file=p=>readFileSync(new URL('../readiness/sandbox-contract-fixture/'+p,import.meta.url));
// Synthetic byte arrays used only under offline factory, never live configuration.
const keys=()=>Object.fromEntries(['dispatch','checkpoint','callback'].map((r,i)=>[r,{role:r,id:r+'-candidate-v1',required_env:ROLE_ENV[r],material:new Uint8Array(32).fill(17*(i+1)),material_class:'INJECTED_NON_FIXTURE'}]));
async function fixture({transportStatus=204,complete=true,Implementation=createOfflineComposition,Gate=OperationGate,Ledger=OfflineOperationLedger}={}){
 const db=new DatabaseSync(':memory:');db.exec('PRAGMA foreign_keys=ON');
 for(const name of ['0008_provider_neutral_roundtrip_backend.sql','0009_youtube_queue_result_proposal.sql','0010_youtube_pipeline_checkpoint_candidate.sql'])db.exec(file('serverless/migrations/'+name).toString());
 const raw=JSON.stringify(script),sh=await hash(raw),req='a'.repeat(64),exec=(sql,a=[])=>db.prepare(sql).run(...a);
 exec("INSERT INTO plm_rt_v2_job VALUES ('job','youtube','youtube_game_001','intent-job','owner',1,1,1,'ACTIVE',NULL,NULL,100,100)");
 exec("INSERT INTO plm_rt_v2_script VALUES ('cp','job','owner',1,1,1,'STARTED','fixture','fixed',?,NULL,NULL,100,100)",[req]);
 exec("INSERT INTO plm_rt_v2_effect VALUES ('gen','job','GENERATION','owner',1,1,?,'gen-delivery',NULL,1,'RESERVED',100,100)",[req]);
 if(complete){exec("UPDATE plm_rt_v2_effect SET state='SENT',version=2,updated_at=101 WHERE effect_id='gen'");exec("UPDATE plm_rt_v2_script SET state='COMPLETED',version=2,script_json=?,script_sha256=?,updated_at=102 WHERE job_id='job'",[raw,sh]);exec("UPDATE plm_rt_v2_effect SET state='CONFIRMED',version=3,result_id='gen-result',updated_at=103 WHERE effect_id='gen'");}
 let writes=0,now=104,sends=0,aborted=false;const k=keys();
 const binding={withSession(mode){assert.equal(mode,'first-primary');return {prepare(sql){return {bind(...args){return {sql,args,first:async()=>db.prepare(sql).get(...args)||null};}};},async batch(ss){db.exec('BEGIN IMMEDIATE');try{const out=ss.map(s=>{const result=exec(s.sql,s.args);writes+=result.changes;return {success:true,meta:{changes:result.changes}};});db.exec('COMMIT');return out;}catch{db.exec('ROLLBACK');throw new Error('FIXED_SQL_FAILURE');}}};}};
 const target={repository:'ikkinotako2-sketch/project-love-machine',workflow:'.github/workflows/youtube-pipeline.yml',workflow_sha256:await hash(file('readiness/production-candidate/revised-source/.github/workflows/youtube-pipeline.yml').toString()),sender_path:'plm/entrypoints/yt_serverless_candidate.py',sender_sha256:await hash(file('readiness/production-candidate/source/plm/entrypoints/yt_serverless_candidate.py').toString()),candidate_entrypoint_path:'plm/entrypoints/yt_serverless_candidate.py',candidate_sha256:await hash(file('readiness/production-candidate/source/plm/entrypoints/yt_serverless_candidate.py').toString()),required_commit_sha:'a'.repeat(40),run_attempt:1,privacy:'private',notify_subscribers:false,approval_status:'OFFLINE_CANDIDATE'};
 const sourceBytes=Object.fromEntries(SOURCE_FILES.map(p=>[p,new Uint8Array(file(p))]));const sourceManifest=JSON.parse(file('readiness/runtime-composition-source-hashes.json'));
 const sourceDigest=await hash(canon(sourceManifest));const ledger=new Ledger();
 const transport={offlineMock:true,abortable:true,key_id:k.dispatch.id,timeoutMs:2,async send(t,p,signal){sends++;assert.equal(db.prepare('SELECT state FROM plm_ytq_v1_outbox').get().state,'SENT');assert.equal(db.prepare('SELECT state FROM plm_ytq_v1_queue').get().state,'DISPATCHED');assert.equal(t.ref,target.required_commit_sha);assert.equal(p.inputs.privacy_status,'private');assert.equal(p.inputs.notify_subscribers,false);assert.ok(signal instanceof AbortSignal);if(transportStatus==='TIMEOUT'){signal.addEventListener('abort',()=>aborted=true);return new Promise(()=>{});}return transportStatus;}};
 const opts={offlineOnly:true,gate:new Gate(ledger,()=>now),db:binding,clock:()=>now,flags:{...SAFE_DEFAULTS},target,keys:k,sourceManifest,sourceBytes,expectedSourceManifestSha:sourceDigest,transport,policy};
 const runtime=await Implementation(opts),inputs=await mapCheckpoint(raw,sh,'job',policy);
 const dispatch=await hash(canon({account_id:'youtube_game_001',job_id:'job',script_sha256:sh,production_ref:target.required_commit_sha,workflow_sha256:target.workflow_sha256}));
 const context={account_id:'youtube_game_001',intent_id:'intent-job',job_id:'job',owner:'owner',owner_epoch:1,fencing_token:1,dispatch_id:dispatch,script_sha256:sh,workflow_sha256:target.workflow_sha256,production_ref:target.required_commit_sha};
 const payloadHash=await hash(canon({ref:target.required_commit_sha,inputs:{...inputs,serverless_context:canon(context)}}));
 const body=event=>({protocol:'plm-youtube-checkpoint-v1',event,key_id:k.checkpoint.id,...Object.fromEntries(Object.entries(context).filter(([x])=>x!=='production_ref')),run_id:'123',render_run_id:'123',run_attempt:1,dispatch_payload_sha256:payloadHash,media_sha256:event==='render'?'4157384237670fb10ffd83de891d2d207003367601bc5970b0c6a37b13ff2110':null,artifact_ref:event==='render'?'artifact://123/rendered-short-job':null,quality_gate:event==='render'?'PASS':null,issued_at:event==='render'?110:108});
 const bind=await signedStage(body('bind'),k.checkpoint.material),render=await signedStage(body('render'),k.checkpoint.material);
 const bindHash=await hash(bind.raw);
 const resultBody=await callbackPayload({...context,run_id:'123'},{run_id:'123',render_run_id:'123',script_sha256:sh,media_sha256:'4157384237670fb10ffd83de891d2d207003367601bc5970b0c6a37b13ff2110',quality_gate:'PASS'},{ok:true,result:{account_id:'youtube_game_001',platform:'youtube',post_id:'offline0001'}},{id:'offline0001',status:{privacyStatus:'private',uploadStatus:'processed'},processingDetails:{processingStatus:'succeeded'}},114,k.callback.id);
 const result=await signCallback(resultBody,k.callback.material);
 const desc=kind=>({operation_id:'op-'+kind,operation_kind:kind,job_id:'job',intent_id:'intent-job',account_id:'youtube_game_001',owner:'owner',owner_epoch:1,fencing_token:1,script_sha256:sh,media_sha256:['RENDER','RESULT'].includes(kind)?'4157384237670fb10ffd83de891d2d207003367601bc5970b0c6a37b13ff2110':null,dispatch_id:dispatch,dispatch_payload_sha256:payloadHash,bind_payload_sha256:['BIND','RENDER','RESULT'].includes(kind)?bindHash:null,pipeline_run_id:['BIND','RENDER','RESULT'].includes(kind)?'123':null,run_attempt:1,expected_state:{ENQUEUE:'ACTIVE',DISPATCH:'QUEUED',BIND:'DISPATCHED',RENDER:'DISPATCHED',RESULT:'DISPATCHED'}[kind],target:structuredClone(target),workflow_sha256:target.workflow_sha256,sender_sha256:target.sender_sha256,callback_key_id:k.callback.id,checkpoint_key_id:k.checkpoint.id,dispatch_key_id:k.dispatch.id,route:{ENQUEUE:null,DISPATCH:null,BIND:'/youtube/checkpoint',RENDER:'/youtube/checkpoint',RESULT:'/youtube/result'}[kind],created_at:104,expires_at:164,consumed_state:'FRESH',source_manifest_sha256:sourceDigest});
 const enqueue=()=>runtime.run(desc('ENQUEUE'),{not_before:104});const dispatchRun=async()=>{now=105;return runtime.run(desc('DISPATCH'));};
 const through=async stage=>{await enqueue();await dispatchRun();if(stage==='dispatch')return;now=108;await runtime.run(desc('BIND'),bind);if(stage==='bind')return;now=110;await runtime.run(desc('RENDER'),render);if(stage==='render')return;now=114;return runtime.run(desc('RESULT'),result);};
 return {db,opts,runtime,desc,bind,render,result,resultBody,body,keys:k,ledger,enqueue,dispatchRun,through,setNow:x=>now=x,writes:()=>writes,sends:()=>sends,aborted:()=>aborted,close:()=>db.close()};
}
async function withFixture(fn,o){const f=await fixture(o);try{await fn(f);}finally{f.close();}}

export {fixture};
