"""Secret-free one-shot marker/history gate, then explicitly authorized refresh."""
import hashlib,json,pathlib,re,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
ID='provider-neutral-youtube-oauth-scope-diagnostic-20261012-r1'
REPO='ikkinotako2-sketch/project-love-machine'
BRANCH='refs/heads/plm-youtube-scope-readiness-20261012-r1'
PARENT='0b2ae2b5e1031eb7336e57abf0a632141b2d44b6'
MARKER='audit-evidence/consumed/'+ID+'.json'
MESSAGE='PLM YouTube OAuth scope once '+ID
PLAN='readiness/youtube-scope-once-plan.json'
SCHEMA='readiness/youtube-scope-once-marker.schema.json'
PINS={'workflow_sha256':'.github/workflows/plm-youtube-scope-once.yml','executor_sha256':'readiness/youtube_scope_once.py','engine_sha256':'readiness/youtube_scope_diagnostic.py','plan_sha256':PLAN,'schema_sha256':SCHEMA,'wrapper_sha256':'readiness/youtube_oauth_verify.py','provider_sha256':'plm/social_adapters/youtube/oauth.py','historical_evidence_sha256':'readiness/youtube-scope-historical-evidence.json'}
PROTECTED='audit-evidence/consumed/provider-neutral-youtube-channel-verify-20261012-r1.json'
class Stop(Exception):pass
def need(b):
 if not b:raise Stop('SCOPE_LOCAL_GATE_STOP')
def parse(raw):
 def pairs(items):
  d={}
  for k,v in items:need(k not in d);d[k]=v
  return d
 return json.loads(raw,object_pairs_hook=pairs)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def gate(env,event,facts,files):
 need(env.get('GITHUB_REPOSITORY')==REPO and env.get('GITHUB_REF')==BRANCH and env.get('GITHUB_RUN_ATTEMPT')=='1' and env.get('GITHUB_EVENT_NAME')=='push')
 need(all(env.get(k)=='true' for k in ['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP']))
 before=event['before'];after=event['after'];need(re.fullmatch('[a-f0-9]{40}',before) and re.fullmatch('[a-f0-9]{40}',after) and env['GITHUB_SHA']==after)
 need(event['head_commit']['id']==after and event['head_commit']['message']==MESSAGE and len(event['commits'])==1)
 p=parse(files[PLAN]);m=parse(files[MARKER]);s=parse(files[SCHEMA])
 need(p['identity']==ID and p['parent']==PARENT and p['maximum_refresh_posts']==1 and p['tokeninfo_requests']==p['youtube_requests']==p['retry']==p['fallback']==0)
 need(set(m)==set(PINS)|{'identity','state','prepared_commit_sha','secret_reference','scope_execution_approved'})
 need(m['identity']==ID and m['state']=='CONSUMED_BEFORE_REMOTE' and m['prepared_commit_sha']==before and m['secret_reference']=='PLM_YOUTUBE_GAME_001' and m['scope_execution_approved'] is True)
 need(set(s['required'])==set(m) and s['additionalProperties'] is False)
 for key,path in PINS.items():need(m[key]==sha(files[path]))
 need(m['wrapper_sha256']=='9531fa5871700ef90f89bdbc190981a95963cfe36e6d0c28b08b20d9cac6ea7e' and m['provider_sha256']=='9fbce205a267ee3a880eb3d34b6e02d410e9aa249d78b16a686a0f559639a8e9')
 need(facts['full_history'] and facts['root']==PARENT and facts['prepared_parent']==PARENT and facts['count']==1)
 expected=p['preparation_files'];need(len(expected)==len(set(expected)) and all(isinstance(x,str) and not x.startswith('/') and '..' not in x.split('/') and not x.startswith('audit-evidence/') for x in expected))
 need(sorted(facts['diff'])==sorted(expected) and facts['head']==after and facts['head_parent']==before and facts['head_message']==MESSAGE and facts['marker_diff']==[MARKER] and facts['marker_absent_before'] and facts['marker_absent_root'] and facts['protected_absent'])
 return True

def load_gate():
 import os
 env={k:os.environ.get(k) for k in ['GITHUB_REPOSITORY','GITHUB_REF','GITHUB_RUN_ATTEMPT','GITHUB_EVENT_NAME','GITHUB_SHA','GITHUB_EVENT_PATH','TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP']};event=parse(pathlib.Path(env['GITHUB_EVENT_PATH']).read_bytes());before=event['before'];after=event['after']
 need(re.fullmatch('[a-f0-9]{40}',before) and re.fullmatch('[a-f0-9]{40}',after))
 ge={'PATH':os.environ.get('PATH',''),'GIT_CONFIG_NOSYSTEM':'1','GIT_TERMINAL_PROMPT':'0'}
 def git(*args):
  p=subprocess.run(['git',*args],cwd=ROOT,env=ge,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL);need(p.returncode==0);return p.stdout.decode().strip()
 def exists(ref,path):return subprocess.run(['git','cat-file','-e',ref+':'+path],cwd=ROOT,env=ge,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
 facts={'full_history':git('rev-parse','--is-shallow-repository')=='false','root':git('merge-base',PARENT,before),'prepared_parent':git('rev-parse',before+'^'),'count':int(git('rev-list','--count',PARENT+'..'+before)),'diff':git('diff','--name-only',PARENT+'..'+before).splitlines(),'head':git('rev-parse','HEAD'),'head_parent':git('rev-parse','HEAD^'),'head_message':git('log','-1','--format=%B'),'marker_diff':git('diff','--name-only',before+'..'+after).splitlines(),'marker_absent_before':not exists(before,MARKER),'marker_absent_root':not exists(PARENT,MARKER),'protected_absent':not (ROOT/PROTECTED).exists() and not exists(after,PROTECTED)}
 files={p:(ROOT/p).read_bytes() for p in set(PINS.values())|{MARKER}};return gate(env,event,facts,files)
def main():
 try:load_gate()
 except Exception:print(json.dumps({'identity':ID,'classification':'SCOPE_LOCAL_GATE_STOP','refresh_posts':0}));raise SystemExit(1) from None
 if '--gate' in sys.argv:print(json.dumps({'identity':ID,'local_gate':'PASS','refresh_posts':0}));return
 import os
 from readiness import youtube_scope_diagnostic as engine
 from readiness.youtube_oauth_verify import authorized_https_transport
 secret=os.environ.pop('PLM_YOUTUBE_OAUTH_JSON','')
 try:result=engine.diagnose(secret,authorized_https_transport)
 finally:secret=None
 print(json.dumps(result))
 if result['classification'] not in ['SCOPE_CONFIRMED_STOP_BEFORE_CHANNEL','SCOPE_MISSING_REAUTH_REQUIRED_STOP']:raise SystemExit(1)
if __name__=='__main__':main()
