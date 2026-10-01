// Manual dispatch only: signed start gate -> trivial test -> signed result.
import {writeFileSync} from 'node:fs';
import {signature} from './worker.mjs';

export async function runTest(input, callbackURL, key, runID, fetcher=fetch) {
  if(input.TEST_ONLY!=='true'||input.DRY_RUN!=='true'||input.NO_PUBLISH!=='true'
      || !/^test-[a-z0-9][a-z0-9-]{0,47}$/.test(input.job_id)
      || !/^[a-f0-9-]{36}$/.test(input.dispatch_id)|| !/^[1-9][0-9]{0,19}$/.test(runID)) throw Error('unsafe_test');
  const url=new URL(callbackURL);
  if(url.protocol!=='https:'||!url.hostname.endsWith('.workers.dev')||url.pathname!=='/test-callback'
      ||url.username||url.password||url.search||url.hash||url.port) throw Error('unsafe_callback_url');
  const base={job_id:input.job_id,dispatch_id:input.dispatch_id,run_id:runID,TEST_ONLY:true,DRY_RUN:true,NO_PUBLISH:true};
  async function callback(status) {
    const body=JSON.stringify({...base,status}), timestamp=String(Date.now());
    const response=await fetcher(url.href,{method:'POST',redirect:'error',signal:AbortSignal.timeout(10000),body,
      headers:{'Content-Type':'application/json','x-plm-timestamp':timestamp,'x-plm-signature':await signature(key,timestamp,body)}});
    if(response.status!==200)throw Error('callback_rejected');
  }
  await callback('started'); // A duplicate run cannot proceed beyond this gate.
  const result={job_id:input.job_id,platform:'test',status:'succeeded',TEST_ONLY:true,DRY_RUN:true,NO_PUBLISH:true};
  await callback('succeeded');return result;
}
if(import.meta.url===`file://${process.argv[1]}`) {
  const result=await runTest(process.env,process.env.PLM_TEST_CALLBACK_URL,
    process.env.PLM_TEST_CALLBACK_KEY,process.env.GITHUB_RUN_ID);
  writeFileSync('plm-test-result.json',JSON.stringify(result)+'\n');
}
