// Candidate only. Existing Worker remains untouched; default handlers are parked.
import {createOfflineComposition} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/runtime.mjs';
export const FLAGS=Object.freeze({TEST_ONLY:true,DRY_RUN:true,NO_PUBLISH:true,EMERGENCY_STOP:true});
const need=(b)=>{if(!b)throw Error('CONNECTION_GATE_STOP');};
export class D1Admission{
 constructor(db){need(db&&typeof db.withSession==='function');this.s=db.withSession('first-primary');this.uncertain=false;}
 async reserve(day){need(!this.uncertain&&/^\d{4}-\d{2}-\d{2}$/.test(day));this.uncertain=true;const result=await this.s.batch([this.s.prepare('INSERT OR IGNORE INTO plm_auto_v1_budget(day) VALUES (?)').bind(day),this.s.prepare('UPDATE plm_auto_v1_budget SET jobs=jobs+1, units=units+200 WHERE day=?').bind(day)]);need(Array.isArray(result)&&result.length===2&&result.every(r=>r.success===true)&&result[1].meta?.changes===1);this.uncertain=false;return true;}
 async notice(job,reason){need(!this.uncertain&&['UNKNOWN','AUTH_STOP','BUDGET_STOP','CONFIG_STOP'].includes(reason));this.uncertain=true;const result=await this.s.batch([this.s.prepare('INSERT OR IGNORE INTO plm_auto_v1_notice(job_id,reason) VALUES (?,?)').bind(job,reason)]);need(Array.isArray(result)&&result.length===1&&result[0].success===true);this.uncertain=false;}
}
export async function connectOffline(options){
 need(options.offlineOnly===true&&options.remoteActivationApproved===false&&typeof options.provenance==='function');
 const runtime=await createOfflineComposition(options);
 return Object.freeze({
  // Existing runtime supplies generation checkpoint/fencing, queue claim, SENT
  // dispatch sentinel, exact binding, render and result callback enforcement.
  async enqueue(d,p){return runtime.run(d,p);},
  async dispatch(d){await options.admission.reserve(options.day);try{return await runtime.run(d);}catch{await options.admission.notice(d.job_id,'UNKNOWN');throw Error('UNKNOWN_NO_REDISPATCH');}},
  async checkpoint(d,packet){need(await options.provenance(d.pipeline_run_id,d.run_attempt,d.workflow_sha256)===true);return runtime.run(d,packet);},
  async result(d,packet){need(await options.provenance(d.pipeline_run_id,d.run_attempt,d.workflow_sha256)===true);try{return await runtime.run(d,packet);}catch{await options.admission.notice(d.job_id,'UNKNOWN');throw Error('CALLBACK_BLOCKED_NO_REUPLOAD');}}
 });
}
export default {async fetch(){return new Response('PARKED_RESIDUAL_CONNECTION',{status:503});},async scheduled(){throw Error('CRON_DISABLED');},async queue(){throw Error('CONSUMER_DISABLED');}};
