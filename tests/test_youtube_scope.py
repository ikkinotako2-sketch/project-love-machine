import copy,json,pathlib,unittest
from unittest.mock import Mock,patch
from readiness import youtube_scope_diagnostic as e,youtube_scope_once as g
ROOT=pathlib.Path(__file__).resolve().parents[1]
BUNDLE=json.dumps({'client_id':'PUBLIC_FIXTURE_CLIENT','client_secret':'PUBLIC_FIXTURE_SECRET','refresh_token':'PUBLIC_FIXTURE_REFRESH'})
def reply(scope='https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly'):
 d={'access_token':'PUBLIC_FIXTURE_ACCESS','token_type':'Bearer','expires_in':3600}
 if scope is not None:d['scope']=scope
 return json.dumps(d).encode()
def fixture():
 files={p:(ROOT/p).read_bytes() for p in g.PINS.values()};before='a'*40;after='b'*40
 m={k:g.sha(files[p]) for k,p in g.PINS.items()};m.update(identity=g.ID,state='CONSUMED_BEFORE_REMOTE',prepared_commit_sha=before,secret_reference='PLM_YOUTUBE_GAME_001',scope_execution_approved=True);files[g.MARKER]=json.dumps(m).encode()
 env={'GITHUB_REPOSITORY':g.REPO,'GITHUB_REF':g.BRANCH,'GITHUB_RUN_ATTEMPT':'1','GITHUB_EVENT_NAME':'push','GITHUB_SHA':after,**{x:'true' for x in ['TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP']}}
 event={'before':before,'after':after,'head_commit':{'id':after,'message':g.MESSAGE},'commits':[{}]}
 facts={'full_history':True,'root':g.PARENT,'prepared_parent':g.PARENT,'count':1,'diff':json.loads(files[g.PLAN])['preparation_files'],'head':after,'head_parent':before,'head_message':g.MESSAGE,'marker_diff':[g.MARKER],'marker_absent_before':True,'marker_absent_root':True,'protected_absent':True}
 return env,event,facts,files
class ScopeTests(unittest.TestCase):
 def test_read_upload_present(self):
  t=Mock(return_value=(200,reply()));r=e.diagnose(BUNDLE,t);self.assertTrue(r['channels_read']);self.assertTrue(r['youtube_upload']);self.assertEqual(t.call_count,1)
 def test_upload_only_missing(self):
  r=e.diagnose(BUNDLE,lambda f:(200,reply('https://www.googleapis.com/auth/youtube.upload')));self.assertFalse(r['channels_read']);self.assertEqual(r['classification'],'SCOPE_MISSING_REAUTH_REQUIRED_STOP')
 def test_readonly_upload_absent(self):self.assertFalse(e.diagnose(BUNDLE,lambda f:(200,reply('https://www.googleapis.com/auth/youtube.readonly')))['youtube_upload'])
 def test_scope_absent_unknown_not_missing(self):
  r=e.diagnose(BUNDLE,lambda f:(200,reply(None)));self.assertEqual(r['classification'],'UNKNOWN_SCOPE_NOT_REPORTED_STOP');self.assertIsNone(r['channels_read'])
 def test_broad_scope(self):self.assertTrue(e.diagnose(BUNDLE,lambda f:(200,reply('https://www.googleapis.com/auth/youtube')))['channels_read'])
 def test_audit_only_not_routine(self):self.assertFalse(e.diagnose(BUNDLE,lambda f:(200,reply('https://www.googleapis.com/auth/youtubepartner-channel-audit')))['channels_read'])
 def test_analytics_optional(self):
  r=e.diagnose(BUNDLE,lambda f:(200,reply()));self.assertFalse(r['analytics_read']);self.assertEqual(r['classification'],'SCOPE_CONFIRMED_STOP_BEFORE_CHANNEL')
 def test_scope_case_sensitive(self):self.assertFalse(e.diagnose(BUNDLE,lambda f:(200,reply('https://www.googleapis.com/auth/YOUTUBE.READONLY')))['channels_read'])
 def test_bad_scope(self):
  for s in ['',True,['scope'],'bad\nvalue','x'*4097]:
   r=e.diagnose(BUNDLE,lambda f:(200,reply(s)));self.assertEqual(r['classification'],'SCOPE_DIAGNOSTIC_BLOCKED');self.assertIsNone(r['channels_read'])
 def test_http_failures_no_retry(self):
  for status in [400,401,403,302,429,500]:
   t=Mock(return_value=(status,b'REMOTE_PRIVATE_BODY'));r=e.diagnose(BUNDLE,t);self.assertEqual(t.call_count,1);self.assertNotIn('REMOTE_PRIVATE_BODY',json.dumps(r))
 def test_timeout_unknown_safe(self):
  t=Mock(side_effect=TimeoutError('PRIVATE_TOKEN'));r=e.diagnose(BUNDLE,t);self.assertEqual(t.call_count,1);self.assertNotIn('PRIVATE_TOKEN',json.dumps(r))
 def test_missing_secret_remote_zero(self):
  t=Mock();e.diagnose('',t);t.assert_not_called()
 def test_bad_token_cannot_confirm_scope(self):
  d=json.loads(reply());d['access_token']='';r=e.diagnose(BUNDLE,lambda f:(200,json.dumps(d).encode()));self.assertIsNone(r['channels_read'])
 def test_no_sensitive_output(self):
  r=e.diagnose(BUNDLE,lambda f:(200,reply()));self.assertNotIn('PUBLIC_FIXTURE',json.dumps(r));self.assertNotIn('https://',json.dumps(r));self.assertEqual(r['tokeninfo_requests'],0)
 def test_refresh_form_no_scope_expansion(self):
  from urllib.parse import parse_qs
  def t(f):self.assertEqual(set(parse_qs(f.decode())),{'client_id','client_secret','refresh_token','grant_type'});return 200,reply()
  e.diagnose(BUNDLE,t)
 def test_request_url_never_contains_token(self):
  self.assertEqual(e.auth.URL,'https://oauth2.googleapis.com/token');self.assertNotIn('?',e.auth.URL)
class GateTests(unittest.TestCase):
 def test_valid_gate(self):self.assertTrue(g.gate(*fixture()))
 def test_history_failures(self):
  for k,v in [('full_history',False),('count',2),('marker_absent_before',False),('protected_absent',False),('marker_diff',['other']),('diff',[])]:
   x=fixture();x[2][k]=v
   with self.assertRaises(g.Stop):g.gate(*x)
 def test_attempt_two_stops(self):
  x=fixture();x[0]['GITHUB_RUN_ATTEMPT']='2'
  with self.assertRaises(g.Stop):g.gate(*x)
 def test_all_hash_drifts_stop(self):
  for p in g.PINS.values():
   x=fixture();x[3][p]+=b'x'
   with self.assertRaises(Exception):g.gate(*x)
 def test_old_identity_stops(self):
  x=fixture();m=json.loads(x[3][g.MARKER]);m['identity']='provider-neutral-youtube-oauth-verify-20261012-r2';x[3][g.MARKER]=json.dumps(m).encode()
  with self.assertRaises(g.Stop):g.gate(*x)
 def test_credential_after_gate(self):
  y=(ROOT/g.PINS['workflow_sha256']).read_text();self.assertLess(y.index('--gate'),y.index('secrets.PLM_YOUTUBE_GAME_001'));self.assertIn('fetch-depth: 0',y)
 def test_gate_failure_no_remote(self):
  with patch.object(g,'load_gate',side_effect=g.Stop()),patch('readiness.youtube_oauth_verify.authorized_https_transport') as t:
   with self.assertRaises(SystemExit):g.main()
   t.assert_not_called()
 def test_marker_absent(self):self.assertFalse((ROOT/g.MARKER).exists())
class MoreTests(unittest.TestCase):
 def test_secret_claimed_scopes_are_not_proof(self):
  bundle=json.loads(BUNDLE);bundle['scope']='https://www.googleapis.com/auth/youtube.readonly'
  r=e.diagnose(json.dumps(bundle),lambda f:(200,reply(None)));self.assertIsNone(r['channels_read'])
 def test_local_full_history_marker_chain(self):
  import os,subprocess,tempfile
  with tempfile.TemporaryDirectory() as directory:
   r=pathlib.Path(directory);ge={**os.environ,'GIT_AUTHOR_NAME':'Offline','GIT_AUTHOR_EMAIL':'offline@example.invalid','GIT_COMMITTER_NAME':'Offline','GIT_COMMITTER_EMAIL':'offline@example.invalid'}
   def git(*args):return subprocess.run(['git',*args],cwd=r,env=ge,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout.decode().strip()
   git('init');p=r/'plm/social_adapters/youtube/oauth.py';p.parent.mkdir(parents=True);p.write_bytes((ROOT/'plm/social_adapters/youtube/oauth.py').read_bytes());git('add','.');git('commit','-m','root');parent=git('rev-parse','HEAD')
   plan=json.loads((ROOT/g.PLAN).read_bytes());plan['parent']=parent
   for path in plan['preparation_files']:
    p=r/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/path).read_bytes())
   (r/g.PLAN).write_text(json.dumps(plan));git('add','.');git('commit','-m','prepare');before=git('rev-parse','HEAD')
   m={k:g.sha((r/p).read_bytes()) for k,p in g.PINS.items()};m.update(identity=g.ID,state='CONSUMED_BEFORE_REMOTE',prepared_commit_sha=before,secret_reference='PLM_YOUTUBE_GAME_001',scope_execution_approved=True)
   p=r/g.MARKER;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(m));git('add',g.MARKER);git('commit','-m',g.MESSAGE);after=git('rev-parse','HEAD')
   event={'before':before,'after':after,'head_commit':{'id':after,'message':g.MESSAGE},'commits':[{}]};p=r/'event.json';p.write_text(json.dumps(event));env=fixture()[0];env.update(GITHUB_SHA=after,GITHUB_EVENT_PATH=str(p))
   with patch.object(g,'ROOT',r),patch.object(g,'PARENT',parent),patch.dict(os.environ,env):
    self.assertTrue(g.load_gate());(r/'.git/shallow').write_text(parent+'\n')
    with self.assertRaises(g.Stop):g.load_gate()
