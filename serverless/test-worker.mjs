import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DatabaseSync} from 'node:sqlite';
import {mkdtempSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import worker,{claimTest,dispatchTest,applyCallback,readJob,expireJob,retryDelay,signature,validateJob} from './worker.mjs';
import {runTest} from './test-runner.mjs';

const job=()=>({platform:'test',account_id:'test_reference_001',job_id:'test-demo',content_fingerprint:'a'.repeat(64),TEST_ONLY:true,DRY_RUN:true,NO_PUBLISH:true});
const schema=readFileSync(new URL('./schema.sql',import.meta.url),'utf8');
class D1Local {
  constructor(path=':memory:') {this.db=new DatabaseSync(path);this.db.exec('PRAGMA busy_timeout=5000;'+schema);}
  prepare(sql) {const db=this.db;let params=[];return {
    bind(...p){params=p;return this;},
    async run(){const r=db.prepare(sql).run(...params);return {meta:{changes:Number(r.changes)}};},
    async first(){return db.prepare(sql).get(...params)||null;},
    all(){return {results:db.prepare(sql).all(...params)};}
  };}
  async batch(statements){this.db.exec('BEGIN IMMEDIATE');try {
    const results=[];for(const stmt of statements) results.push(stmt.all());
    this.db.exec('COMMIT');return results;
  }catch(e){this.db.exec('ROLLBACK');throw e;}}
  close(){this.db.close();}
}
const env=db=>({DB:db,TEST_ONLY:'true',DRY_RUN:'true',NO_PUBLISH:'true',EMERGENCY_STOP:'false',GITHUB_DISPATCH_TOKEN:'mock-only',TEST_REQUEST_KEY:'r'.repeat(32),TEST_CALLBACK_KEY:'c'.repeat(32)});
async function signed(path,data,e,key=e.TEST_REQUEST_KEY,time=Date.now()) {
  const body=JSON.stringify(data),timestamp=String(time);
  return new Request('https://mock.invalid'+path,{method:'POST',body,headers:{'x-plm-timestamp':timestamp,'x-plm-signature':await signature(key,timestamp,body)}});
}
test('first claim, duplicate replay, changed fingerprint, exact payload',async()=>{
 const db=new D1Local();try {
  const first=await claimTest(db,job());assert.equal((await claimTest(db,job())).claimant,first.claimant);
  await assert.rejects(claimTest(db,{...job(),content_fingerprint:'b'.repeat(64)}));
  assert.throws(()=>validateJob({...job(),job_id:'../bad'}));
  assert.throws(()=>validateJob({...job(),access_token:'mock'}));
  assert.throws(()=>validateJob({...job(),platform:'youtube'}));
  assert.throws(()=>validateJob({...job(),NO_PUBLISH:false}));
 }finally{db.close();}
});
test('exact Github test dispatch; queue replay does not dispatch twice',async()=>{
 const db=new D1Local();let calls=0;try {
  const mock=async(url,options)=>{calls++;assert.match(url,/workflows\/plm-serverless-test.yml\/dispatches$/);
   const body=JSON.parse(options.body);assert.equal(body.ref,'plm-serverless-architecture-v1');
   assert.equal(body.inputs.NO_PUBLISH,'true');return new Response(null,{status:204});};
  await dispatchTest(env(db),job(),mock);await dispatchTest(env(db),job(),mock);assert.equal(calls,1);
 }finally{db.close();}
});
test('timeout/ambiguous dispatch fail closed without automatic resend',async()=>{
 const db=new D1Local();let calls=0;try {
  const mock=async()=>{calls++;throw Error('mock response lost');};
  assert.equal((await dispatchTest(env(db),job(),mock)).state,'unknown');
  await dispatchTest(env(db),job(),mock);assert.equal(calls,1);
 }finally{db.close();}
});
test('callback authenticates, runs once, terminal replay is idempotent',async()=>{
 const db=new D1Local();try {
  const e=env(db);const record=await dispatchTest(e,job(),async()=>new Response(null,{status:204}));
  const start={job_id:job().job_id,dispatch_id:record.claimant,run_id:'123',status:'started',TEST_ONLY:true,DRY_RUN:true,NO_PUBLISH:true};
  const request=await signed('/test-callback',start,e,e.TEST_CALLBACK_KEY);
  assert.equal((await worker.fetch(request,e)).status,200);
  await assert.rejects(applyCallback(db,{...start,run_id:'456'}));
  await applyCallback(db,{...start,status:'succeeded'});await applyCallback(db,{...start,status:'succeeded'});
  assert.equal((await readJob(db,job())).state,'succeeded');
 }finally{db.close();}
});
test('invalid callback signature, stale auth, emergency stop and missing secret',async()=>{
 const db=new D1Local();try {
  const e=env(db);assert.equal((await worker.fetch(await signed('/test-jobs',job(),e,'x'.repeat(32)),e)).status,409);
  assert.equal((await worker.fetch(await signed('/test-jobs',job(),e,e.TEST_REQUEST_KEY,Date.now()-400000),e)).status,409);
  await assert.rejects(dispatchTest({...e,EMERGENCY_STOP:'true'},job(),()=>{throw Error('must not run');}));
  await assert.rejects(dispatchTest({...e,GITHUB_DISPATCH_TOKEN:undefined},job()));
  assert.equal(await readJob(db,job()),null);
 }finally{db.close();}
});
test('stale claim CAS, timeout, reconnect never resends',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'plm-test-'));const path=join(dir,'jobs.db');let db=new D1Local(path);try {
  const claimed=await claimTest(db,job());const dispatched=await dispatchTest(env(db),job(),async()=>new Response(null,{status:204}),1);
  assert.ok(dispatched.version>claimed.version);
  const stale=await db.prepare("UPDATE test_jobs SET state='ready' WHERE job_id=? AND version=?").bind(job().job_id,claimed.version).run();assert.equal(stale.meta.changes,0);
  await expireJob(db,job(),10,20);db.close();db=new D1Local(path);
  assert.equal((await readJob(db,job())).state,'unknown');
  await dispatchTest(env(db),job(),()=>{throw Error('must never dispatch');});
 }finally{db.close();rmSync(dir,{recursive:true,force:true});}
});
test('independent connections racing get one dispatch winner',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'plm-race-'));const path=join(dir,'jobs.db');const a=new D1Local(path),b=new D1Local(path);try {
  await claimTest(a,job());let calls=0;
  const mock=async()=>{calls++;return new Response(null,{status:204});};
  await Promise.all([dispatchTest(env(a),job(),mock),dispatchTest(env(b),job(),mock)]);assert.equal(calls,1);
 }finally{a.close();b.close();rmSync(dir,{recursive:true,force:true});}
});
test('bounded safe retry and hard test budget',async()=>{
 assert.deepEqual([1,2,3].map(retryDelay),[5,10,20]);assert.throws(()=>retryDelay(4));
 const db=new D1Local();try {
  for(let i=0;i<10;i++)await claimTest(db,{...job(),job_id:`test-${i}`});
  await assert.rejects(claimTest(db,{...job(),job_id:'test-eleven'}));
  assert.ok(await claimTest(db,{...job(),job_id:'test-0'}));
 }finally{db.close();}
});
test('offline round trip uses actual runner and signed Worker callbacks',async()=>{
 const db=new D1Local();try {
  const e=env(db),record=await dispatchTest(e,job(),async()=>new Response(null,{status:204}));
  const input={job_id:job().job_id,dispatch_id:record.claimant,TEST_ONLY:'true',DRY_RUN:'true',NO_PUBLISH:'true'};
  const result=await runTest(input,'https://plm-mock.workers.dev/test-callback',e.TEST_CALLBACK_KEY,'123',
    (url,options)=>worker.fetch(new Request(url,options),e));
  assert.equal(result.platform,'test');assert.equal((await readJob(db,job())).state,'succeeded');
 }finally{db.close();}
});
test('runner refuses missing flags, arbitrary endpoints and rejected start',async()=>{
 const input={job_id:'test-demo',dispatch_id:crypto.randomUUID(),TEST_ONLY:'true',DRY_RUN:'true',NO_PUBLISH:'true'};
 await assert.rejects(runTest({...input,NO_PUBLISH:'false'},'https://mock.workers.dev/test-callback','c'.repeat(32),'123'));
 await assert.rejects(runTest(input,'https://example.com/test-callback','c'.repeat(32),'123'));
 let calls=0;
 await assert.rejects(runTest(input,'https://mock.workers.dev/test-callback','c'.repeat(32),'123',async()=>{calls++;return new Response(null,{status:409});}));
 assert.equal(calls,1);
});
