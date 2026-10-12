import copy,hashlib,json,pathlib,unittest
from unittest.mock import patch
from readiness import youtube_channel_verify_once as g
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
  source=(ROOT/g.HELPER).read_text();self.assertGreater(source.index('from readiness import youtube_channel_verify as auth'),source.index('load_gate()\n'))
 def test_secret_step_after_gate(self):
  y=(ROOT/g.WORKFLOW).read_text();self.assertLess(y.index('Secret-free local gate'),y.index('secrets.PLM_YOUTUBE_GAME_001'));self.assertIn('fetch-depth: 0',y);self.assertIn('persist-credentials: false',y)
 def test_future_marker_absent(self):self.assertFalse((ROOT/g.MARKER).exists())
 def test_gate_failure_remote_zero(self):
  with patch.object(g,'load_gate',side_effect=g.Stop('bad')),patch('readiness.youtube_oauth_verify.authorized_https_transport') as transport:
   with self.assertRaises(SystemExit):g.main()
   transport.assert_not_called()


from readiness import youtube_channel_verify as c
BUNDLE=json.dumps({'client_id':'fixture-client','client_secret':'fixture-secret','refresh_token':'fixture-refresh'})
GOOD=json.dumps({'access_token':'fixture-access','expires_in':3600,'token_type':'Bearer'}).encode()
def payload(items=None,**kw):
 return json.dumps({'kind':'youtube#channelListResponse','items':items if items is not None else [{'id':c.EXPECTED}],**kw}).encode()
class ChannelTests(unittest.TestCase):
 def run_case(self,body=None,oauth=200,http=200):
  calls=[]
  def refresh(form):calls.append('POST');return oauth,GOOD
  def channel(token):calls.append('GET');return http,body if body is not None else payload()
  return c.verify(BUNDLE,refresh,channel),calls
 def test_exact_match(self):
  o,calls=self.run_case();self.assertTrue(o['channel_match']);self.assertEqual(calls,['POST','GET'])
 def test_oauth_failure_no_get(self):
  for status in (400,401,403,429,500,302):
   o,calls=self.run_case(oauth=status);self.assertFalse(o['channel_match']);self.assertEqual(calls,['POST'])
 def test_http_no_retry(self):
  for status in (400,401,403,429,500,302):
   o,calls=self.run_case(http=status);self.assertFalse(o['channel_match']);self.assertEqual(calls,['POST','GET'])
 def test_wrong_channel(self):self.assertFalse(self.run_case(payload([{'id':'UC'+'a'*22}]))[0]['channel_match'])
 def test_empty(self):self.assertFalse(self.run_case(payload([]))[0]['channel_match'])
 def test_multiple(self):self.assertFalse(self.run_case(payload([{'id':c.EXPECTED}]*2))[0]['channel_match'])
 def test_pagination(self):self.assertFalse(self.run_case(payload(nextPageToken='next'))[0]['channel_match'])
 def test_malformed(self):self.assertFalse(self.run_case(b'invalid')[0]['channel_match'])
 def test_duplicate_json_keys(self):self.assertFalse(self.run_case(b'{"items":[],"items":[]}')[0]['channel_match'])
 def test_body_bound(self):self.assertFalse(self.run_case(b'x'*32769)[0]['channel_match'])
 def test_missing_secret_remote_zero(self):
  from unittest.mock import Mock
  a=Mock();b=Mock();o=c.verify('',a,b);a.assert_not_called();b.assert_not_called();self.assertFalse(o['channel_match'])
 def test_timeout_no_resend_and_no_exception_text(self):
  from unittest.mock import Mock
  a=Mock(return_value=(200,GOOD));b=Mock(side_effect=TimeoutError('SECRET_REMOTE_BODY'))
  o=c.verify(BUNDLE,a,b);self.assertEqual(b.call_count,1);self.assertNotIn('SECRET_REMOTE_BODY',json.dumps(o))
 def test_no_token_in_result(self):
  o,_=self.run_case();self.assertNotIn('fixture-',json.dumps(o));self.assertEqual(o['raw_retention'],0)
 def test_r1_r2_rejected(self):
  for ident in ('provider-neutral-youtube-oauth-verify-20261012-r1','provider-neutral-youtube-oauth-verify-20261012-r2'):
   x=fixture();m=json.loads(x[3][g.MARKER]);m['identity']=ident;x[3][g.MARKER]=json.dumps(m).encode()
   with self.assertRaises(g.Stop):g.gate(*x)
 def test_historical_markers_exact(self):
  for p,h in g.HISTORICAL.items():self.assertEqual(g.digest((ROOT/p).read_bytes()),h)
 def test_private_job_parked(self):
  p=json.loads((ROOT/'readiness/youtube-private-test-job.json').read_bytes())
  self.assertEqual(p['privacy_status'],'private');self.assertFalse(p['notify_subscribers']);self.assertFalse(p['execution_approved']);self.assertEqual(p['max_videos'],1)
if __name__=='__main__':unittest.main()

from readiness.youtube_private_once import PrivateOnce,Stop as PrivateStop
class UploadBoundaryTests(unittest.TestCase):
 def proof(self):return {**{k:True for k in ('channel_exact','rights_attested','render_quality_pass','upload_approved','source_pins_exact')},'job_id':'job','media_sha256':'hash','privacy_status':'private','notify_subscribers':False,'run_attempt':1}
 def test_claim_before_send_once(self):
  order=[]
  x=PrivateOnce('job',lambda *a:order.append('claim') or True,lambda:order.append('init') or 'session',lambda s:order.append('send') or True)
  self.assertEqual(x.execute(self.proof(),'hash'),'UPLOAD_ACK_STOP');self.assertEqual(order,['claim','init','send'])
  with self.assertRaises(PrivateStop):x.execute(self.proof(),'hash')
 def test_duplicate_claim_no_remote(self):
  from unittest.mock import Mock
  a=Mock();b=Mock();x=PrivateOnce('job',lambda *a:False,a,b);self.assertEqual(x.execute(self.proof(),'hash'),'CLAIM_STOP');a.assert_not_called();b.assert_not_called()
 def test_unknown_no_resume(self):
  from unittest.mock import Mock
  send=Mock(side_effect=TimeoutError());x=PrivateOnce('job',lambda *a:True,lambda:'s',send)
  self.assertEqual(x.execute(self.proof(),'hash'),'UNKNOWN_NO_RESEND')
  with self.assertRaises(PrivateStop):x.execute(self.proof(),'hash')
  self.assertEqual(send.call_count,1)
 def test_every_missing_gate_prevents_claim(self):
  from unittest.mock import Mock
  for k in ('channel_exact','rights_attested','render_quality_pass','upload_approved','source_pins_exact'):
   p=self.proof();p[k]=False;c=Mock();x=PrivateOnce('job',c,Mock(),Mock())
   with self.assertRaises(PrivateStop):x.execute(p,'hash')
   c.assert_not_called()

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


