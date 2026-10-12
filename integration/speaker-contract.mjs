// Successor only. mapCheckpoint and every legacy speaker=1 caller remain intact.
import {mapCheckpoint,PIPELINE_FIELDS} from '../readiness/sandbox-contract-fixture/serverless/youtube-connection/mapping.mjs';
import {hash} from '../readiness/sandbox-contract-fixture/serverless/youtube-live/worker.mjs';
export const VOICE=Object.freeze({engine:'VOICEVOX',speaker_id:3,voice_name:'ずんだもん',style_name:'ノーマル'});
const need=(ok,code)=>{if(!ok)throw Error(code);};
export async function successorRenderInputs(raw,expectedSha,job,policy,renderContract){
 need(renderContract?.version===1&&renderContract.script_sha256===expectedSha&&await hash(raw)===expectedSha,'SCRIPT_SHA_STOP');
 need(JSON.stringify(renderContract.voice)===JSON.stringify(VOICE)&&['NEW_RENDER','REUSE_PINNED'].includes(renderContract.mode),'VOICE_MODE_STOP');
 const parsed=JSON.parse(raw);need(parsed.narration===parsed.scenes.map(x=>x.caption).join(''),'SCRIPT_CAPTION_STOP');
 if(renderContract.mode==='REUSE_PINNED')need(renderContract.media_sha256==='4157384237670fb10ffd83de891d2d207003367601bc5970b0c6a37b13ff2110'&&/^[a-f0-9]{64}$/.test(renderContract.audio_sha256)&&/^[a-f0-9]{64}$/.test(renderContract.caption_sha256),'REUSE_ASSET_STOP');
 const inputs=await mapCheckpoint(raw,expectedSha,job,policy);
 inputs.speaker='3';inputs.description='オリジナル非公開テスト。VOICEVOX:ずんだもん。合成音声使用。';inputs.tags='technical,shorts';
 need(Object.keys(inputs).sort().join('|')===PIPELINE_FIELDS.join('|')&&inputs.privacy_status==='private'&&inputs.notify_subscribers===false,'PIPELINE_SHAPE_STOP');
 return inputs;
}
