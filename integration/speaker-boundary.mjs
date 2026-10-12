import {ConnectionBoundary} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/connection.mjs';
import {canon} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/mapping.mjs';
import {hash,need} from '../readiness/sandbox-contract-fixture/serverless/youtube-live/worker.mjs';
import {successorRenderInputs} from './speaker-contract.mjs';
export class SpeakerBoundary extends ConnectionBoundary{
 constructor(adapter,target,policy,renderContract){super(adapter,target,policy);this.renderContract=structuredClone(renderContract);}
 async reserve(job,version,inputs,now){
  need(!this.stopped&&Number.isSafeInteger(now)&&now>0,'BOUNDARY_STOP');
  const q=await this.a.read('row',[job]);need(q?.state==='CLAIMED'&&q.job_state==='ACTIVE'&&q.version===version,'CLAIM');
  const script=await this.a.read('script',[job]);need(script,'CHECKPOINT_REQUIRED');
  const mapped=await successorRenderInputs(script.script_json,q.script_sha256,job,this.policy,this.renderContract);need(canon(mapped)===canon(inputs),'EXACT_SUCCESSOR_MAPPING');
  const dispatch=await hash(canon({account_id:q.account_id,job_id:job,script_sha256:q.script_sha256,production_ref:this.target.ref,workflow_sha256:this.target.workflow_sha256}));
  const context={account_id:q.account_id,intent_id:q.intent_id,job_id:job,owner:q.owner,owner_epoch:q.owner_epoch,fencing_token:q.fencing_token,dispatch_id:dispatch,script_sha256:q.script_sha256,workflow_sha256:this.target.workflow_sha256,production_ref:this.target.ref};
  const payload={ref:this.target.ref,inputs:{...mapped,serverless_context:canon(context)}};need(new TextEncoder().encode(canon(payload)).length<=65535,'DISPATCH_SIZE');
  await this.a.batch([['reserve',[dispatch,job,await hash(canon(payload))]],['dispatched',[now,job,version]]]);this.capabilities.set(dispatch,{payload,q});return {dispatch_id:dispatch,payload:structuredClone(payload),context};
 }
}
