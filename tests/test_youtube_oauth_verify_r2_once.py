import copy,hashlib,json,pathlib,unittest
from unittest.mock import patch
from readiness import youtube_oauth_verify_r2_once as g
ROOT=pathlib.Path(__file__).resolve().parents[1]
def fixture():
 files={p:(ROOT/p).read_bytes() for p in g.PINS.values()}
 plan=json.loads(files[g.PLAN]);before='a'*40;after='b'*40
 marker={k:g.digest(files[p]) for k,p in g.PINS.items()}
 marker.update(identity=g.IDENTITY,state='CONSUMED_BEFORE_REMOTE',prepared_commit_sha=before,secret_reference=g.SELECTOR,oauth_execution_approved=True)
 files[g.MARKER]=json.dumps(marker).encode()
 env={'GITHUB_REPOSITORY':g.REPO,'GITHUB_REF':g.BRANCH,'GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':after,**{x:'true' for x in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}}
 event={'before':before,'after':after,'head_commit':{'id':after,'message':g.MESSAGE},'commits':[{}]}
 facts={'shallow':False,'merge_base':g.PARENT,'count':1,'preparation_files':plan['preparation_files'],'head':after,'head_parent':before,'parent':g.PARENT,'head_message':g.MESSAGE,'marker_diff':[g.MARKER],'marker_before_absent':True,'marker_root_absent':True,'wrapper_parent_hash':plan['wrapper_sha256'],'provider_parent_hash':plan['provider_sha256'],'immutable_root_hashes':g.HISTORICAL.copy()}
 return env,event,facts,files
class Tests(unittest.TestCase):
 def test_full_fixture_pass(self):self.assertTrue(g.gate(*fixture()))
 def blocked(self,args):
  with self.assertRaises(g.Stop):g.gate(*args)
 def test_wrong_repository(self):
  x=fixture();x[0]['GITHUB_REPOSITORY']='other';self.blocked(x)
 def test_wrong_branch(self):
  x=fixture();x[0]['GITHUB_REF']='refs/heads/main';self.blocked(x)
 def test_attempt2(self):
  x=fixture();x[0]['GITHUB_RUN_ATTEMPT']='2';self.blocked(x)
 def test_dispatch_rejected(self):
  x=fixture();x[0]['GITHUB_EVENT_NAME']='workflow_dispatch';self.blocked(x)
 def test_safe_flag_rejected(self):
  x=fixture();x[0]['DRY_RUN']='false';self.blocked(x)
 def test_shallow_rejected(self):
  x=fixture();x[2]['shallow']=True;self.blocked(x)
 def test_history_count_rejected(self):
  x=fixture();x[2]['count']=2;self.blocked(x)
 def test_missing_preparation_file(self):
  x=fixture();x[2]['preparation_files']=x[2]['preparation_files'][:-1];self.blocked(x)
 def test_extra_preparation_file(self):
  x=fixture();x[2]['preparation_files']=x[2]['preparation_files']+['plm/social_adapters/youtube/oauth.py'];self.blocked(x)
 def test_wrong_wrapper_hash(self):
  x=fixture();x[3][g.WRAPPER]+=b'\n';self.blocked(x)
 def test_wrong_marker_selector(self):
  x=fixture();m=json.loads(x[3][g.MARKER]);m['secret_reference']='OTHER';x[3][g.MARKER]=json.dumps(m).encode();self.blocked(x)
 def test_marker_approval_required(self):
  x=fixture();m=json.loads(x[3][g.MARKER]);m['oauth_execution_approved']=False;x[3][g.MARKER]=json.dumps(m).encode();self.blocked(x)
 def test_marker_only(self):
  x=fixture();x[2]['marker_diff'].append('other');self.blocked(x)
 def test_marker_previous_consumption(self):
  x=fixture();x[2]['marker_before_absent']=False;self.blocked(x)
 def test_no_provider_import_before_gate(self):
  source=(ROOT/g.HELPER).read_text();self.assertGreater(source.index('from readiness import youtube_oauth_verify as auth'),source.index('load_gate()\n'))
 def test_secret_step_after_gate(self):
  y=(ROOT/g.WORKFLOW).read_text();self.assertLess(y.index('Secret-free local gate'),y.index('secrets.PLM_YOUTUBE_GAME_001'));self.assertIn('fetch-depth: 0',y);self.assertIn('persist-credentials: false',y)
 def test_future_marker_absent(self):self.assertFalse((ROOT/g.MARKER).exists())
 def test_gate_failure_remote_zero(self):
  with patch.object(g,'load_gate',side_effect=g.Stop('bad')),patch('readiness.youtube_oauth_verify.authorized_https_transport') as transport:
   with self.assertRaises(SystemExit):g.main()
   transport.assert_not_called()

class ExtraTests(unittest.TestCase):
 def blocked(self,args):
  with self.assertRaises(g.Stop):g.gate(*args)
 def test_plan_selector_mismatch(self):
  x=fixture();p=json.loads(x[3][g.PLAN]);p['secret_reference']='OTHER';x[3][g.PLAN]=json.dumps(p).encode();self.blocked(x)
 def test_every_pin_drift_stops(self):
  for key,path in g.PINS.items():
   with self.subTest(key=key):
    x=fixture();x[3][path]+=b' ';self.blocked(x)
 def test_gate_only_missing_secret_does_not_touch_secret(self):
  import io,contextlib,os
  original=os.environ.get
  def get(k,*args):
   if k=='PLM_YOUTUBE_OAUTH_JSON':raise AssertionError('SECRET_ACCESSED_IN_GATE')
   return original(k,*args)
  with patch.object(g,'load_gate',return_value=True),patch.object(g.sys,'argv',['executor','--gate']),patch.object(os.environ,'get',side_effect=get),contextlib.redirect_stdout(io.StringIO()):g.main()
 def test_main_missing_secret_remote_zero(self):
  import io,contextlib
  with patch.object(g,'load_gate',return_value=True),patch.object(g.sys,'argv',['executor']),patch.dict('os.environ',{},clear=True),patch('readiness.youtube_oauth_verify.authorized_https_transport') as transport,contextlib.redirect_stdout(io.StringIO()):
   with self.assertRaises(SystemExit):g.main()
   transport.assert_not_called()
 def test_main_one_approved_post(self):
  import io,contextlib
  from test_youtube_oauth_verify import BUNDLE,GOOD
  with patch.object(g,'load_gate',return_value=True),patch.object(g.sys,'argv',['executor']),patch.dict('os.environ',{'PLM_YOUTUBE_OAUTH_JSON':BUNDLE}),patch('readiness.youtube_oauth_verify.authorized_https_transport',return_value=(200,GOOD)) as transport,contextlib.redirect_stdout(io.StringIO()) as out:
   g.main();self.assertEqual(transport.call_count,1);self.assertEqual(json.loads(out.getvalue())['refresh_posts'],1)



class ActualHistoryTests(unittest.TestCase):
 def test_full_git_history_and_shallow_rejection(self):
  import os,subprocess,tempfile
  with tempfile.TemporaryDirectory() as directory:
   repo=pathlib.Path(directory)
   git_env={'PATH':os.environ.get('PATH',''),'GIT_CONFIG_NOSYSTEM':'1','GIT_TERMINAL_PROMPT':'0','GIT_AUTHOR_NAME':'Offline Fixture','GIT_AUTHOR_EMAIL':'fixture@example.invalid','GIT_COMMITTER_NAME':'Offline Fixture','GIT_COMMITTER_EMAIL':'fixture@example.invalid'}
   def git(*args):return subprocess.run(['git',*args],cwd=repo,env=git_env,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout.decode().strip()
   git('init')
   for path in (g.WRAPPER,g.PROVIDER,*g.HISTORICAL):
    target=repo/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/path).read_bytes())
   git('add','.');git('commit','-m','fixture preparation root');parent=git('rev-parse','HEAD')
   plan=json.loads((ROOT/g.PLAN).read_bytes());plan['preparation_parent']=parent
   for path in plan['preparation_files']:
    target=repo/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/path).read_bytes())
   (repo/g.PLAN).write_text(json.dumps(plan))
   git('add','.');git('commit','-m','fixture preparation');prepared=git('rev-parse','HEAD')
   marker={k:g.digest((repo/path).read_bytes()) for k,path in g.PINS.items()};marker.update(identity=g.IDENTITY,state='CONSUMED_BEFORE_REMOTE',prepared_commit_sha=prepared,secret_reference=g.SELECTOR,oauth_execution_approved=True)
   path=repo/g.MARKER;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(marker))
   git('add',g.MARKER);git('commit','-m',g.MESSAGE);head=git('rev-parse','HEAD')
   event={'before':prepared,'after':head,'head_commit':{'id':head,'message':g.MESSAGE},'commits':[{}]};event_path=repo/'event.json';event_path.write_text(json.dumps(event))
   env={'PATH':git_env['PATH'],'GITHUB_REPOSITORY':g.REPO,'GITHUB_REF':g.BRANCH,'GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':head,'GITHUB_EVENT_PATH':str(event_path),**{x:'true' for x in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP')}}
   with patch.object(g,'ROOT',repo),patch.object(g,'PARENT',parent),patch.dict('os.environ',env,clear=True):
    self.assertTrue(g.load_gate())
    (repo/'.git/shallow').write_text(parent+'\n')
    with self.assertRaises(g.Stop):g.load_gate()


class R2ProtectionTests(unittest.TestCase):
 def test_r1_identity_rejected(self):
  x=fixture();m=json.loads(x[3][g.MARKER]);m['identity']='provider-neutral-youtube-oauth-verify-20261012-r1';x[3][g.MARKER]=json.dumps(m).encode()
  with self.assertRaises(g.Stop):g.gate(*x)
 def test_r1_marker_drift_stops(self):
  x=fixture();p=next(p for p in g.HISTORICAL if '/consumed/' in p);x[3][p]+=b' '
  with self.assertRaises(g.Stop):g.gate(*x)
 def test_r1_root_drift_stops(self):
  x=fixture();x[2]['immutable_root_hashes']={}
  with self.assertRaises(g.Stop):g.gate(*x)
 def test_r1_artifacts_unchanged(self):
  for p,h in g.HISTORICAL.items():self.assertEqual(g.digest((ROOT/p).read_bytes()),h)
 def test_new_identity_and_no_marker(self):
  self.assertEqual(g.IDENTITY,'provider-neutral-youtube-oauth-verify-20261012-r2');self.assertFalse((ROOT/g.MARKER).exists())
 def test_r1_failed_run_not_success(self):
  p=json.loads((ROOT/g.PLAN).read_bytes());self.assertEqual(p['historical_consumed_run_id'],38204853129);self.assertIs(p['historical_identity_success_prerequisite'],False)

if __name__=="__main__":unittest.main()
