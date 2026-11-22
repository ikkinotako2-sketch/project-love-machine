// TEST_ONLY reference Worker. No SNS endpoint, adapter, or deployment side effect.
export const REPOSITORY = 'ikkinotako2-sketch/project-love-machine';
export const REF = 'plm-serverless-architecture-v1';
export const WORKFLOW = 'plm-serverless-test.yml';
const ID = /^test-[a-z0-9][a-z0-9-]{0,47}$/;
const HASH = /^[a-f0-9]{64}$/;
const SAFE = { TEST_ONLY: 'true', DRY_RUN: 'true', NO_PUBLISH: 'true' };
function guard(env) {
  if (Object.entries(SAFE).some(([k,v]) => env[k] !== v) || env.EMERGENCY_STOP !== 'false')
    throw Error('disabled');
}
function exact(object, keys) {
  if (!object || typeof object !== 'object' || Array.isArray(object)
      || Object.keys(object).sort().join(',') !== keys.sort().join(',')) throw Error('invalid_payload');
}
export function validateJob(job) {
  exact(job, ['platform','account_id','job_id','content_fingerprint','TEST_ONLY','DRY_RUN','NO_PUBLISH']);
  if (job.platform !== 'test' || job.account_id !== 'test_reference_001'
      || typeof job.job_id!=='string' || typeof job.content_fingerprint!=='string'
      || !ID.test(job.job_id) || !HASH.test(job.content_fingerprint)
      || Object.keys(SAFE).some(k => job[k] !== true)) throw Error('invalid_payload');
  return job;
}
export async function signature(key, timestamp, body) {
  if (typeof key !== 'string' || key.length < 32) throw Error('missing_auth');
  const imported = await crypto.subtle.importKey('raw', new TextEncoder().encode(key),
    {name:'HMAC',hash:'SHA-256'},false,['sign']);
  const bytes = await crypto.subtle.sign('HMAC',imported,new TextEncoder().encode(`${timestamp}.${body}`));
  return [...new Uint8Array(bytes)].map(x=>x.toString(16).padStart(2,'0')).join('');
}
async function authenticate(request, key, body, now) {
  const timestamp = request.headers.get('x-plm-timestamp');
  const received = request.headers.get('x-plm-signature') || '';
  if (!/^\d{13}$/.test(timestamp || '') || Math.abs(now-Number(timestamp))>300000
      || !HASH.test(received)) throw Error('unauthorized');
  const expected = await signature(key,timestamp,body);
  let difference=0;
  for(let i=0;i<64;i++) difference |= expected.charCodeAt(i)^received.charCodeAt(i);
  if(difference) throw Error('unauthorized');
}
const identity = job => ['test','test_reference_001',job.job_id];
const WHERE = 'platform=? AND account_id=? AND job_id=?';
export async function readJob(db, job) {
  return db.prepare(`SELECT * FROM test_jobs WHERE ${WHERE}`).bind(...identity(job)).first();
}
export async function claimTest(db, job, now=Date.now()) {
  validateJob(job);
  const ticket=crypto.randomUUID();
  // Hard lifetime cap, not a promise about account-wide quota or hostile ingress.
  const result = await db.batch([
    db.prepare(`INSERT INTO test_jobs (platform,account_id,job_id,content_fingerprint,claimant,state,version,last_operation,created_at,updated_at)
      SELECT ?,?,?,?,?,'ready',1,'claim',?,? WHERE (SELECT count(*) FROM test_jobs)<10
      ON CONFLICT(platform,account_id,job_id) DO NOTHING`)
      .bind(...identity(job),job.content_fingerprint,ticket,now,now),
    db.prepare(`SELECT * FROM test_jobs WHERE ${WHERE}`).bind(...identity(job))
  ]);
  const row=result[1].results[0];
  if(!row) throw Error('budget_exhausted');
  if(row.content_fingerprint !== job.content_fingerprint) throw Error('fingerprint_conflict');
  return row;
}
export async function dispatchTest(env, job, fetcher=fetch, now=Date.now()) {
  guard(env); validateJob(job);
  if(typeof env.GITHUB_DISPATCH_TOKEN !== 'string' || !env.GITHUB_DISPATCH_TOKEN) throw Error('missing_auth');
  const before=await claimTest(env.DB,job,now);
  const updated=await env.DB.prepare(`UPDATE test_jobs SET state='dispatching',version=version+1,last_operation='dispatch_attempt',updated_at=?
    WHERE ${WHERE} AND state='ready' AND version=?`)
    .bind(now,...identity(job),before.version).run();
  if(updated.meta.changes !== 1) return readJob(env.DB,job); // Queue replay: no second dispatch.
  try {
    const response=await fetcher(`https://api.github.com/repos/${REPOSITORY}/actions/workflows/${WORKFLOW}/dispatches`,{
      method:'POST',redirect:'error',signal:AbortSignal.timeout(10000),headers:{
        'Authorization':`Bearer ${env.GITHUB_DISPATCH_TOKEN}`,'User-Agent':'PLM-Test-Only',
        'Accept':'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'},
      body:JSON.stringify({ref:REF,inputs:{job_id:job.job_id,dispatch_id:before.claimant,
        TEST_ONLY:'true',DRY_RUN:'true',NO_PUBLISH:'true'}})
    });
    if(response.status !== 204) throw Error('dispatch_unconfirmed');
  } catch {
    await env.DB.prepare(`UPDATE test_jobs SET state='unknown',version=version+1,last_operation='ambiguous_dispatch',updated_at=?
      WHERE ${WHERE} AND state='dispatching'`).bind(now,...identity(job)).run();
  }
  return readJob(env.DB,job);
}
export async function applyCallback(db, data, now=Date.now()) {
  exact(data,['job_id','dispatch_id','run_id','status','TEST_ONLY','DRY_RUN','NO_PUBLISH']);
  if(['job_id','dispatch_id','run_id','status'].some(k=>typeof data[k]!=='string')
      || !ID.test(data.job_id) || !/^[a-f0-9-]{36}$/.test(data.dispatch_id)
      || !/^[1-9][0-9]{0,19}$/.test(data.run_id) || !['started','succeeded'].includes(data.status)
      || Object.keys(SAFE).some(k=>data[k]!==true)) throw Error('invalid_callback');
  const state=data.status==='started'?'running':'succeeded';
  const sql=data.status==='started'
    ? `UPDATE test_jobs SET state='running',run_id=?,version=version+1,last_operation='runner_start',updated_at=?
       WHERE ${WHERE} AND claimant=? AND state IN ('dispatching','unknown') AND run_id IS NULL`
    : `UPDATE test_jobs SET state='succeeded',version=version+1,last_operation='runner_done',updated_at=?
       WHERE ${WHERE} AND claimant=? AND state='running' AND run_id=?`;
  const args=data.status==='started'
    ? [data.run_id,now,...identity(data),data.dispatch_id]
    : [now,...identity(data),data.dispatch_id,data.run_id];
  const changed=await db.prepare(sql).bind(...args).run();
  const record=await readJob(db,data);
  if(!record || record.claimant!==data.dispatch_id || record.run_id!==data.run_id
      || (changed.meta.changes!==1 && record.state!==state)) throw Error('callback_conflict');
  return {job_id:data.job_id,status:record.state};
}
export async function expireJob(db, job, cutoff, now=Date.now()) {
  return db.prepare(`UPDATE test_jobs SET state='unknown',version=version+1,last_operation='timeout',updated_at=?
    WHERE ${WHERE} AND state IN ('dispatching','running') AND updated_at<?`).bind(now,...identity(job),cutoff).run();
}
export function retryDelay(attempt) { // Only for safe reads/callback transport, never initialize or dispatch.
  if(!Number.isInteger(attempt)||attempt<1||attempt>3) throw Error('retry_exhausted');
  return 5*2**(attempt-1);
}
export default {
  async fetch(request,env) {
    try {
      guard(env);
      const path=new URL(request.url).pathname;
      if(request.method!=='POST'||!['/test-jobs','/test-callback'].includes(path)) return Response.json({error:'not_found'},{status:404});
      const reader=request.body?.getReader(); let length=0; const chunks=[];
      if(!reader) throw Error('invalid_payload');
      for(;;) { const {value,done}=await reader.read(); if(done)break;length+=value.length;
        if(length>4096){await reader.cancel();throw Error('invalid_payload');}chunks.push(value); }
      const bytes=new Uint8Array(length);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}
      const body=new TextDecoder().decode(bytes);
      await authenticate(request,path==='/test-jobs'?env.TEST_REQUEST_KEY:env.TEST_CALLBACK_KEY,body,Date.now());
      const data=JSON.parse(body);
      const result=path==='/test-jobs'?await dispatchTest(env,data):await applyCallback(env.DB,data);
      return Response.json({job_id:result.job_id,status:result.state||result.status});
    } catch { return Response.json({error:'request_rejected'},{status:409}); } // Never expose raw responses/errors.
  }
};
