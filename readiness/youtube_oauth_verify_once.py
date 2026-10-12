"""One-shot auth-only execution gate; credential injection follows local proof."""
import hashlib,json,pathlib,re,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
IDENTITY='provider-neutral-youtube-oauth-verify-20261012-r1'
REPO='ikkinotako2-sketch/project-love-machine'
BRANCH='refs/heads/plm-youtube-oauth-readiness-20261012-r1'
PARENT='367f92a2510e616054dcf6106c3e724b1f6c4091'
MARKER='audit-evidence/consumed/'+IDENTITY+'.json'
MESSAGE='PLM YouTube OAuth verify once '+IDENTITY
PLAN='readiness/youtube-oauth-verify-once-plan.json'
SCHEMA='readiness/youtube-oauth-verify-once-marker.schema.json'
WORKFLOW='.github/workflows/plm-youtube-oauth-verify-once.yml'
HELPER='readiness/youtube_oauth_verify_once.py'
WRAPPER='readiness/youtube_oauth_verify.py'
PROVIDER='plm/social_adapters/youtube/oauth.py'
SELECTOR='PLM_YOUTUBE_GAME_001'
PINS={'workflow_sha256':WORKFLOW,'executor_sha256':HELPER,'plan_sha256':PLAN,'schema_sha256':SCHEMA,'wrapper_sha256':WRAPPER,'provider_sha256':PROVIDER}
HEX40=re.compile(r'^[a-f0-9]{40}$')
class Stop(Exception):pass
def exact_json(raw):
    def pairs(items):
        out={}
        for key,value in items:
            if key in out:raise Stop("OAUTH_LOCAL_GATE_STOP")
            out[key]=value
        return out
    return json.loads(raw,object_pairs_hook=pairs)
def need(ok):
    if not ok:raise Stop('OAUTH_LOCAL_GATE_STOP')
def digest(raw):return hashlib.sha256(raw).hexdigest()
def gate(env,event,facts,files):
    need(env.get('GITHUB_REPOSITORY')==REPO and env.get('GITHUB_REF')==BRANCH and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_RUN_ATTEMPT')=='1')
    need(all(env.get(x)=='true' for x in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')))
    before=event.get('before');after=event.get('after')
    need(isinstance(before,str) and bool(HEX40.fullmatch(before)) and after==env.get('GITHUB_SHA') and isinstance(after,str) and bool(HEX40.fullmatch(after)))
    hc=event.get('head_commit',{})
    need(hc.get('id')==after and hc.get('message')==MESSAGE and len(event.get('commits',[]))==1)
    plan=exact_json(files[PLAN]);marker=exact_json(files[MARKER]);schema=exact_json(files[SCHEMA])
    need(all(type(plan.get(k)) is int and plan[k]==0 for k in ('retry','redirect','fallback','maximum_uploads','maximum_publishes')))
    need(plan['identity']==IDENTITY and plan['preparation_parent']==PARENT and plan['secret_reference']==SELECTOR and plan['maximum_refresh_posts']==1)
    need(plan['wrapper_sha256']==digest(files[WRAPPER])=='9531fa5871700ef90f89bdbc190981a95963cfe36e6d0c28b08b20d9cac6ea7e' and plan['provider_sha256']==digest(files[PROVIDER])=='9fbce205a267ee3a880eb3d34b6e02d410e9aa249d78b16a686a0f559639a8e9')
    need(set(marker)==set(PINS)|{'identity','state','prepared_commit_sha','secret_reference','oauth_execution_approved'})
    need(marker['identity']==IDENTITY and marker['state']=='CONSUMED_BEFORE_REMOTE' and marker['prepared_commit_sha']==before and marker['secret_reference']==SELECTOR and marker['oauth_execution_approved'] is True)
    need(set(schema['required'])==set(marker) and schema['additionalProperties'] is False)
    for key,path in PINS.items():need(marker[key]==digest(files[path]))
    expected=plan['preparation_files'];need(isinstance(expected,list) and len(expected)==len(set(expected)) and all(isinstance(x,str) and '..' not in x.split('/') and not x.startswith('/') and x!=MARKER for x in expected))
    need(facts['shallow'] is False and facts['merge_base']==PARENT and facts['count']==1 and set(facts['preparation_files'])==set(expected) and len(facts['preparation_files'])==len(expected))
    need(facts['head']==after and facts['head_parent']==before and facts['head_message']==MESSAGE and facts['marker_diff']==[MARKER] and facts['marker_before_absent'] and facts['marker_root_absent'])
    need(facts['parent']==PARENT and facts['wrapper_parent_hash']==plan['wrapper_sha256'] and facts['provider_parent_hash']==plan['provider_sha256'])
    return True

def load_gate():
    import os
    env={k:os.environ.get(k) for k in ('GITHUB_REPOSITORY','GITHUB_REF','GITHUB_EVENT_NAME','GITHUB_RUN_ATTEMPT','GITHUB_SHA','GITHUB_EVENT_PATH','TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')};event=exact_json(pathlib.Path(env['GITHUB_EVENT_PATH']).read_bytes());before=event['before'];after=event['after']
    need(isinstance(before,str) and bool(HEX40.fullmatch(before)) and isinstance(after,str) and bool(HEX40.fullmatch(after)))
    git_env={'PATH':os.environ.get('PATH',''),'GIT_CONFIG_NOSYSTEM':'1','GIT_TERMINAL_PROMPT':'0'}
    def git(*args):
        p=subprocess.run(['git',*args],cwd=ROOT,env=git_env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False)
        need(p.returncode==0);return p.stdout
    def exists(ref,path):return subprocess.run(['git','cat-file','-e',ref+':'+path],cwd=ROOT,env=git_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    facts={'shallow':git('rev-parse','--is-shallow-repository').strip()!=b'false','merge_base':git('merge-base',PARENT,before).decode().strip(),'count':int(git('rev-list','--count',PARENT+'..'+before)),'preparation_files':git('diff','--name-only',PARENT+'..'+before).decode().splitlines(),'head':git('rev-parse','HEAD').decode().strip(),'head_parent':git('rev-parse','HEAD^').decode().strip(),'parent':git('rev-parse',before+'^').decode().strip(),'head_message':git('log','-1','--format=%B').decode().strip(),'marker_diff':git('diff','--name-only',before+'..'+after).decode().splitlines(),'marker_before_absent':not exists(before,MARKER),'marker_root_absent':not exists(PARENT,MARKER),'wrapper_parent_hash':digest(git('show',PARENT+':'+WRAPPER)),'provider_parent_hash':digest(git('show',PARENT+':'+PROVIDER))}
    files={p:(ROOT/p).read_bytes() for p in set(PINS.values())|{MARKER}}
    gate(env,event,facts,files)
    return True

def main():
    result={'identity':IDENTITY,'classification':'OAUTH_LOCAL_GATE_STOP','reason_code':'OAUTH_LOCAL_GATE_STOP','refresh_posts':0}
    try:
        load_gate()
        if '--gate' in sys.argv:
            print(json.dumps({'identity':IDENTITY,'local_gate':'PASS','refresh_posts':0}));return
        import os
        # The workflow injects only the exact approved selector after separate gate.
        from readiness import youtube_oauth_verify as auth
        raw_secret=os.environ.pop('PLM_YOUTUBE_OAUTH_JSON','')
        try:
            result=auth.verify(raw_secret,auth.authorized_https_transport)
        finally:
            del raw_secret
        result['identity']=IDENTITY
    except Exception:
        print(json.dumps(result));raise SystemExit(1) from None
    print(json.dumps(result))
    if result.get('classification')!='OAUTH_REFRESH_AUTH_CONFIRMED_STOP_BEFORE_YOUTUBE':raise SystemExit(1)
if __name__=='__main__':main()
