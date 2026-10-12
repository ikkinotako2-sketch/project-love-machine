import {CheckpointD1Adapter,CONNECTION_SQL} from './connection.mjs';
import {ensure} from './runtime-contract.mjs';
import {hash} from '../youtube-live/worker.mjs';
export const GENERATION_SQL=`SELECT j.*,s.state AS script_state,s.script_sha256,s.script_json,s.owner AS script_owner,s.owner_epoch AS script_epoch,s.fencing_token AS script_fence,e.state AS generation_state,e.owner AS generation_owner,e.owner_epoch AS generation_epoch,e.fencing_token AS generation_fence FROM plm_rt_v2_job j JOIN plm_rt_v2_script s ON s.job_id=j.job_id JOIN plm_rt_v2_effect e ON e.job_id=j.job_id AND e.kind='GENERATION' WHERE j.job_id=?`;
export class GenerationCheckpointAdapter extends CheckpointD1Adapter{
 stmt(n,args){ensure(Object.hasOwn(CONNECTION_SQL,n)||n==='generation','FIXED_QUERY_ONLY');return this.db.prepare(n==='generation'?GENERATION_SQL:CONNECTION_SQL[n]).bind(...args);}
}
export async function generationProof(adapter,d){
 const row=await adapter.read('generation',[d.job_id]);
 ensure(row&&row.state==='ACTIVE'&&row.script_state==='COMPLETED'&&row.generation_state==='CONFIRMED','GENERATION_CHECKPOINT_INCOMPLETE');
 for(const k of ['job_id','intent_id','account_id','owner','owner_epoch','fencing_token','script_sha256'])ensure(row[k]===d[k],'GENERATION_IDENTITY');
 ensure(row.script_owner===d.owner&&row.generation_owner===d.owner&&row.script_epoch===d.owner_epoch&&row.generation_epoch===d.owner_epoch&&row.script_fence===d.fencing_token&&row.generation_fence===d.fencing_token&&await hash(row.script_json)===d.script_sha256,'GENERATION_SCRIPT_FENCE');return row;
}
export async function enqueueGeneration(boundary,d,notBefore,now){
 ensure(Number.isSafeInteger(notBefore)&&notBefore>0,'QUEUE_TIME');await generationProof(boundary.a,d);
 const entry=Object.fromEntries(['job_id','account_id','intent_id','script_sha256','owner','owner_epoch','fencing_token'].map(k=>[k,d[k]]));entry.not_before=notBefore;
 const prior=await boundary.a.read('row',[d.job_id]);
 if(prior){ensure(prior.state==='QUEUED'&&Object.keys(entry).every(k=>prior[k]===entry[k]),'ENQUEUE_DUPLICATE_CHANGED');return {enqueueNoop:true};}
 await boundary.enqueue(entry,now);return {enqueued:true};
}
