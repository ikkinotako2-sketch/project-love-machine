"""Existing VOICEVOX/FFmpeg/Quality Gate, local engine only; no YouTube modules."""
import hashlib,http.client,json,os,pathlib,sys,wave
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'render-worker'))
import voicevox
from ffmpeg_builder import build_video
from quality_gate import validate_video

def local_post(url,body=b'',content_type=None):
    from urllib.parse import urlsplit
    p=urlsplit(url)
    if p.scheme!='http' or p.netloc!='127.0.0.1:50021' or p.path not in ['/audio_query','/synthesis']:raise ValueError('LOCAL_ENGINE_POLICY_STOP')
    conn=http.client.HTTPConnection('127.0.0.1',50021,timeout=120)
    try:
        conn.request('POST',p.path+'?'+p.query,body=body,headers={'Content-Type':content_type or 'application/json'})
        response=conn.getresponse()
        if response.status!=200:raise ValueError('LOCAL_ENGINE_HTTP_STOP')
        raw=response.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise ValueError('LOCAL_ENGINE_BOUND_STOP')
        return raw
    finally:conn.close()

def render(directory):
    job=json.loads((ROOT/'readiness/youtube-private-job.json').read_text())
    directory=pathlib.Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    conn=http.client.HTTPConnection('127.0.0.1',50021,timeout=30)
    try:
        conn.request('GET','/speakers');r=conn.getresponse()
        if r.status!=200:raise ValueError('ENGINE_IDENTITY_STOP')
        raw=r.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:raise ValueError('ENGINE_BOUND_STOP')
        speakers=json.loads(raw)
        matches=[(s['name'],style['name']) for s in speakers for style in s['styles'] if style['id']==job['speaker']]
        if matches!=[(job['voice_name'],job['voice_style'])]:raise ValueError('VOICE_STYLE_DRIFT_STOP')
    finally:conn.close()
    # Existing voice generation reused, network primitive restricted to loopback.
    original=voicevox._post;voicevox._post=local_post
    captions=[];frames=[];params=None;cursor=0
    try:
        for i,text in enumerate(job['sentences']):
            path=directory/f'voice-{i}.wav';voicevox.generate_voice(text,job['speaker'],str(path))
            with wave.open(str(path),'rb') as f:
                current=(f.getnchannels(),f.getsampwidth(),f.getframerate())
                if params is not None and params!=current:raise ValueError('PCM_SHAPE_STOP')
                if current!=(1,2,24000):raise ValueError('PCM_CONTRACT_STOP')
                params=current;raw=f.readframes(f.getnframes());frames.append(raw)
                span=f.getnframes()/f.getframerate();captions.append({'start_seconds':cursor,'end_seconds':cursor+span,'text':text});cursor+=span
    finally:voicevox._post=original
    if cursor>30:raise ValueError('PRIVATE_TEST_DURATION_BOUND_STOP')
    audio=directory/'audio.wav'
    with wave.open(str(audio),'wb') as f:f.setnchannels(params[0]);f.setsampwidth(params[1]);f.setframerate(params[2]);f.writeframes(b''.join(frames))
    payload={'title':job['title'],'narration':''.join(job['sentences']),'captions':captions,'scenes':[{'start':0,'end':cursor,'visual_keyword':'study'}],'bgm':{},'output':job['output']}
    previous=os.getcwd()
    try:
        os.chdir(directory);build_video(payload,str(audio.resolve()),'short.mp4');quality=validate_video('short.mp4')
    finally:os.chdir(previous)
    media=directory/'short.mp4'
    import subprocess
    subprocess.run(['ffmpeg','-v','error','-i',str(media),'-f','null','-'],check=True,timeout=60)
    if abs(quality['duration']-cursor)>0.15:raise ValueError('AV_DURATION_DRIFT_STOP')
    evidence={'mode':'OFFLINE_RENDER','quality':quality,'media_sha256':hashlib.sha256(media.read_bytes()).hexdigest(),'audio_sha256':hashlib.sha256(audio.read_bytes()).hexdigest(),'caption_sha256':hashlib.sha256((directory/'captions.ass').read_bytes()).hexdigest(),'timing':captions,'timing_basis':'Per-sentence PCM frame counts, concatenated without gaps; visual frame quantization <=1/30s','voice':job['credit'],'voice_style_verified':True,'channel_match':'UNVERIFIED','upload_approved':False,'youtube_requests':0,'oauth_posts':0}
    (directory/'render-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    (directory/'job.json').write_text(json.dumps(job,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'render':'PASS','width':quality['width'],'height':quality['height'],'duration':quality['duration'],'media_sha256':evidence['media_sha256']}))
    return evidence
if __name__=='__main__':render((ROOT/'offline-evidence').resolve())
