import {need,hash} from '../youtube-live/worker.mjs';
export function canon(value){if(Array.isArray(value))return '['+value.map(canon).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canon(value[k])).join(',')+'}';need(typeof value!=='number'||Number.isFinite(value),'JSON_FINITE');return JSON.stringify(value);}
export const PIPELINE_FIELDS='job_id account_id oauth_secret_name title hook narration speaker scenes_json captions_json bgm_json output_json description tags privacy_status scheduled_for made_for_kids contains_synthetic_media notify_subscribers'.split(' ').sort();
function text(x,n){need(typeof x==='string'&&x.trim().length>0&&x.length<=n&&!/[\x00-\x08\x0b-\x1f]/.test(x),'SCRIPT_TEXT');}
export async function mapCheckpoint(raw,expectedSha,job,policy){
 need(typeof raw==='string'&&new TextEncoder().encode(raw).length<=65536&&await hash(raw)===expectedSha,'SCRIPT_HASH');
 let s;try{s=JSON.parse(raw);}catch{throw new Error('SCRIPT_JSON');}
 need(Object.keys(s).sort().join('|')==='bgm|hook|narration|scenes|title','SCRIPT_FORMAT');
 text(s.title,100);text(s.hook,240);text(s.narration,4000);
 need(Array.isArray(s.scenes)&&s.scenes.length>=1&&s.scenes.length<=60,'SCENES');let prior=0;
 for(const v of s.scenes){need(Object.keys(v).sort().join('|')==='caption|emphasis_words|end|motion|sfx|start|visual_keyword','SCENE_FIELDS');need(Number.isFinite(v.start)&&Number.isFinite(v.end)&&v.start>=prior&&v.end>v.start&&v.end<=60,'SCENE_TIME');prior=v.end;text(v.caption,240);text(v.visual_keyword,240);need(['zoom_in','zoom_out','pan_left','pan_right','none'].includes(v.motion)&&['pop','none'].includes(v.sfx)&&Array.isArray(v.emphasis_words)&&v.emphasis_words.length<=10,'SCENE_STYLE');v.emphasis_words.forEach(x=>text(x,40));}
 need(s.bgm&&Object.keys(s.bgm).sort().join('|')==='mood|volume'&&Number.isFinite(s.bgm.volume)&&s.bgm.volume>=0&&s.bgm.volume<=1,'BGM');text(s.bgm.mood,40);
 // Audience/disclosure decisions must be explicit trusted policy, never model output.
 need(policy&&typeof policy.made_for_kids==='boolean'&&typeof policy.contains_synthetic_media==='boolean','EXPLICIT_POLICY');
 const inputs={job_id:job,account_id:'youtube_game_001',oauth_secret_name:'PLM_YOUTUBE_GAME_001',title:s.title,hook:s.hook,narration:s.narration,speaker:'1',scenes_json:JSON.stringify(s.scenes),captions_json:JSON.stringify(s.scenes.map((v,i)=>({index:i+1,start_seconds:v.start,end_seconds:v.end,text:v.caption}))),bgm_json:JSON.stringify(s.bgm),output_json:JSON.stringify({format:'mp4',width:1080,height:1920,fps:30}),description:'',tags:'game,shorts',privacy_status:'private',scheduled_for:'',made_for_kids:policy.made_for_kids,contains_synthetic_media:policy.contains_synthetic_media,notify_subscribers:false};
 need(Object.keys(inputs).sort().join('|')===PIPELINE_FIELDS.join('|')&&JSON.stringify(inputs).length<=65535,'PIPELINE_CONTRACT');return inputs;
}
