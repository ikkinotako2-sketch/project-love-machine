// Preparation-only composition. No ambient credential, target, DB, clock or transport.
export const REMOTE_ACTIVATION_SUPPORTED=false;
export const SAFE_DEFAULTS=Object.freeze({TEST_ONLY:true,DRY_RUN:true,NO_PUBLISH:true,EMERGENCY_STOP:true});
export const RUNTIME_ROUTES=Object.freeze({ENQUEUE:null,DISPATCH:null,BIND:'/youtube/checkpoint',RENDER:'/youtube/checkpoint',RESULT:'/youtube/result'});
export const ROLE_ENV=Object.freeze({dispatch:'PLM_GITHUB_DISPATCH_TOKEN',checkpoint:'PLM_YOUTUBE_CHECKPOINT_KEY',callback:'PLM_YOUTUBE_RESULT_CALLBACK_KEY'});
export const SOURCE_FILES=Object.freeze(['serverless/youtube-live/worker.mjs',...['connection.mjs','checkpoint.mjs','dispatch.mjs','mapping.mjs','sender.mjs','bundle.mjs','runtime-contract.mjs','operation-gate.mjs','generation-adapter.mjs','runtime.mjs','runtime-bundle.mjs'].map(x=>'serverless/youtube-connection/'+x)]);
export const ensure=(condition,code)=>{if(!condition)throw new Error(code);};
export const runtimeId=x=>typeof x==='string'&&/^[A-Za-z0-9_-]{1,96}$/.test(x);
export const runtimeSha=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
export const runtimeInt=x=>Number.isSafeInteger(x)&&x>0;
export async function bytesSha(bytes){ensure(bytes instanceof Uint8Array,'BYTES_REQUIRED');return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');}
export async function verifySources(manifest,bytes,expectedDigest){
 ensure(manifest&&bytes&&runtimeSha(expectedDigest),'SOURCE_MANIFEST_REQUIRED');
 ensure(Object.keys(manifest).sort().join('|')===SOURCE_FILES.slice().sort().join('|')&&Object.keys(bytes).sort().join('|')===Object.keys(manifest).sort().join('|'),'SOURCE_SET');
 const canonical=JSON.stringify(Object.fromEntries(Object.keys(manifest).sort().map(k=>[k,manifest[k]])));
 ensure(await bytesSha(new TextEncoder().encode(canonical))===expectedDigest,'SOURCE_MANIFEST_DRIFT');
 for(const path of SOURCE_FILES)ensure(runtimeSha(manifest[path])&&await bytesSha(bytes[path])===manifest[path],'SOURCE_DRIFT');
}
export function validateTarget(t){
 const fields='repository workflow workflow_sha256 sender_path sender_sha256 candidate_entrypoint_path candidate_sha256 required_commit_sha run_attempt privacy notify_subscribers approval_status'.split(' ').sort();
 ensure(t&&Object.keys(t).sort().join('|')===fields.join('|'),'EXACT_TARGET_REQUIRED');
 ensure(t.repository==='ikkinotako2-sketch/project-love-machine'&&t.workflow==='.github/workflows/youtube-pipeline.yml'&&/^[a-f0-9]{40}$/.test(t.required_commit_sha),'EXACT_TARGET_REF');
 ensure(t.sender_path==='plm/entrypoints/yt_serverless_candidate.py'&&t.candidate_entrypoint_path===t.sender_path&&runtimeSha(t.workflow_sha256)&&runtimeSha(t.sender_sha256)&&t.candidate_sha256===t.sender_sha256,'TARGET_HASH');
 ensure(t.run_attempt===1&&t.privacy==='private'&&t.notify_subscribers===false,'PRIVATE_ATTEMPT1_ONLY');
 ensure(t.approval_status==='OFFLINE_CANDIDATE','OFFLINE_TARGET_ONLY');return structuredClone(t);
}
export async function validateKeys(keys){
 ensure(keys&&Object.keys(keys).sort().join('|')==='callback|checkpoint|dispatch','KEY_ROLES_REQUIRED');
 const ids=new Set(),digests=new Set();
 for(const role of ['dispatch','checkpoint','callback']){
  const k=keys[role];ensure(k&&k.role===role&&runtimeId(k.id)&&k.required_env===ROLE_ENV[role]&&k.material instanceof Uint8Array&&k.material.length>=32,'KEY_ROLE_OR_MATERIAL');
  ensure(k.material_class==='INJECTED_NON_FIXTURE'&&!/PUBLIC_|FIXTURE|TEST_KEY/i.test(new TextDecoder().decode(k.material)),'FIXTURE_KEY_REJECTED');
  const digest=await bytesSha(k.material);ensure(!ids.has(k.id)&&!digests.has(digest),'INDEPENDENT_KEY_ROLES');ids.add(k.id);digests.add(digest);
 }
}
