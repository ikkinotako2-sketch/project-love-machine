import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {DatabaseSync} from 'node:sqlite';
import {fixture} from './runtime-fixture.mjs';
import {D1Admission,connectOffline} from './connection.mjs';
import {signCallback} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/sender.mjs';

test('Python actual-video Strict Upload → Worker signed result → D1 COMPLETE',async()=>{
 const result=JSON.parse(readFileSync(new URL('../final-evidence/upload-result.json',import.meta.url)));
 assert.equal(result.proof_basis,'OFFLINE_FIXTURE');assert.equal(result.processed_readback,'MOCK_ONLY');assert.equal(result.state,'Done');
 const f=await fixture({jobId:result.job_id,script:JSON.parse(result.script_raw)});
 try{
  const c=await connectOffline({...f.opts,remoteActivationApproved:false,day:'2026-10-12',admission:{reserve:async()=>true,notice:async()=>{}},provenance:async(run,attempt,sha)=>run==='123'&&attempt===1&&sha===f.opts.target.workflow_sha256});
  await c.enqueue(f.desc('ENQUEUE'),{not_before:104});f.setNow(105);await c.dispatch(f.desc('DISPATCH'));
  f.setNow(108);await c.checkpoint(f.desc('BIND'),f.bind);f.setNow(110);await c.checkpoint(f.desc('RENDER'),f.render);
  assert.equal(result.job_id,f.resultBody.job_id);
  assert.equal(result.script_sha256,f.resultBody.script_sha256);
  assert.equal(result.render_mode,'REUSE_EXACT_APPROVED_ASSET_NO_NEW_RENDER');
  assert.equal(result.media_sha256,f.resultBody.media_sha256);
  assert.equal(result.video_id,f.resultBody.video_id);
  const packet=await signCallback(f.resultBody,f.keys.callback.material);
  f.setNow(114);await c.result(f.desc('RESULT'),packet);
  assert.equal(f.db.prepare('SELECT state FROM plm_ytq_v1_queue').get().state,'COMPLETE');assert.equal(f.sends(),1);
  const writes=f.writes();await c.result(f.desc('RESULT'),packet);assert.equal(f.sends(),1);assert.equal(f.writes(),writes); // exact replay: existing idempotent no-op contract
 }finally{f.close();}
});
test('D1 batch timeout cannot issue reserve or notice again',async()=>{
 let calls=0;const s={prepare(){return{bind(){return{};}};},async batch(){calls++;throw Error('UNKNOWN');}};
 const a=new D1Admission({withSession(){return s;}});
 await assert.rejects(a.reserve('2026-10-12'));await assert.rejects(a.reserve('2026-10-12'));await assert.rejects(a.notice('job','UNKNOWN'));assert.equal(calls,1);
});
test('D1 partial success is ambiguity and further writes unreachable',async()=>{
 let calls=0;const s={prepare(){return{bind(){return{};}};},async batch(){calls++;return[{success:true}];}};
 const a=new D1Admission({withSession(){return s;}});await assert.rejects(a.reserve('2026-10-12'));await assert.rejects(a.notice('job','UNKNOWN'));assert.equal(calls,1);
});
test('0011 additive schema preserves 0008/9/10 exact structure and rows',()=>{
 const db=new DatabaseSync(':memory:');
 const snap=()=>db.prepare("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE tbl_name NOT LIKE 'plm_auto_v1_%' ORDER BY name").all();
 for(const path of ['0008_provider_neutral_roundtrip_backend.sql','0009_youtube_queue_result_proposal.sql','0010_youtube_pipeline_checkpoint_candidate.sql'])db.exec(readFileSync(new URL('../readiness/sandbox-contract-fixture/serverless/migrations/'+path,import.meta.url),'utf8'));
 const before=snap();db.exec(readFileSync(new URL('./0011_automation_budget_notification_candidate.sql',import.meta.url),'utf8'));assert.deepEqual(snap(),before);
 for(const table of ['plm_rt_v2_job','plm_ytq_v1_queue','plm_ytq_v1_outbox','plm_ytq_v1_result','plm_ytp_v1_binding'])assert.equal(db.prepare('SELECT count(*) n FROM '+table).get().n,0);
 db.close();
});
test('callback SHA/signature mismatch blocks result without second dispatch',async()=>{
 const f=await fixture();try{
  await f.through('render');const packet={...f.result,signature:'0'.repeat(64)};
  f.setNow(114);await assert.rejects(f.runtime.run(f.desc('RESULT'),packet));assert.equal(f.sends(),1);assert.equal(f.db.prepare('SELECT count(*) n FROM plm_ytq_v1_result').get().n,0);
 }finally{f.close();}
});
