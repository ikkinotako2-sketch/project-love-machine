import {need} from '../youtube-live/worker.mjs';
import {canon} from './mapping.mjs';
export function liveDispatchCandidate(fetchImpl,credential,{timeoutMs=30000}={}){
 need(typeof fetchImpl==='function'&&typeof credential==='string'&&credential.length>0&&Number.isSafeInteger(timeoutMs)&&timeoutMs>=1&&timeoutMs<=30000,'TRANSPORT_CONFIGURATION');
 // Dependency injection only. No global fetch or environment lookup.
 return {abortable:true,async send(target,payload,signal){
  need(signal instanceof AbortSignal&&!signal.aborted&&/^[a-f0-9]{40}$/.test(target.ref)&&payload.ref===target.ref&&target.repository==='ikkinotako2-sketch/project-love-machine'&&target.workflow==='.github/workflows/youtube-pipeline.yml','EXACT_TARGET');
  const url='https://api.github.com/repos/'+target.repository+'/actions/workflows/youtube-pipeline.yml/dispatches';
  const response=await fetchImpl(url,{method:'POST',redirect:'error',signal,headers:{'Authorization':'Bearer '+credential,'Accept':'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'},body:canon(payload)});
  if(response.body)await response.body.cancel();return response.status;
 },timeoutMs};
}
export async function abortableOneSend(boundary,dispatch,transport,now){
 need(!boundary.stopped&&transport?.abortable===true&&typeof transport.send==='function'&&Number.isSafeInteger(now)&&now>0,'SEND_CONFIGURATION');
 const cap=boundary.capabilities.get(dispatch);need(cap,'NO_RESUME');boundary.capabilities.delete(dispatch);
 await boundary.a.batch([['sent',[dispatch]]]);
 const controller=new AbortController();const timeout=transport.timeoutMs??30000;need(Number.isSafeInteger(timeout)&&timeout>=1&&timeout<=30000,'TIMEOUT_BOUND');let timer;
 try{
  const status=await Promise.race([Promise.resolve().then(()=>{need(!controller.signal.aborted,'ABORTED_BEFORE_SEND');return transport.send(boundary.target,structuredClone(cap.payload),controller.signal);}),new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(new Error('TIMEOUT'));},timeout);})]);
  clearTimeout(timer);need(status===204,'NON204');return {accepted:true,uploadSucceeded:false,nextEligible:false};
 }catch{
  clearTimeout(timer);controller.abort();boundary.stopped=true;
  await boundary.a.batch([['unknownOut',[dispatch]],['unknownQueue',[now,cap.q.job_id]]]);throw new Error('UNKNOWN_ABORTED_NO_RETRY');
 }
}
