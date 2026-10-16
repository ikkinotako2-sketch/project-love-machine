import base64,copy,ctypes,io,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.parse import parse_qs
from plm.automation.executors import oauth_exchange as x
from plm.automation.ledger import Stop
from tests.test_oauth_client_reuse import CID,OLD,NEW,Fixture,response
ROOT=Path(__file__).resolve().parents[1]
PLAN=json.loads((ROOT/x.PLAN).read_bytes())

def permit(mode='OFFLINE_CONTRACT'):
 p=copy.deepcopy(PLAN);p.update(client_id=CID,consent_state='s'*48)
 return x.Permit(p,mode,x._SEAL)
def handoff(**updates):
 d={'client_id':CID,'redirect_uri':x.REDIRECT,'state':'s'*48,'code':'FIXTURE_CODE','issued_at':1000};d.update(updates);return json.dumps(d)
class Encryptor:
 def encrypt(self,key,raw):return 'FIXTURE_ENCRYPTED_ONLY'
class ExchangeTests(unittest.TestCase):
 def setup_engine(self,*,payload=None,status=200,ack=201):
  replies=iter([(404,{}),(200,{'key_id':'fixed-key-id','key':base64.b64encode(b'p'*32).decode()}),(ack,{})])
  writer=Fixture(lambda *args:next(replies));post=Fixture(lambda *args:(status,response() if payload is None else payload))
  e=x.ExchangeExecutor(permit(),post,x.SecretWriter(writer,Encryptor()),lambda:1100)
  return e,writer,post
 def load(self,name):return {x.EXISTING:OLD,x.HANDOFF:handoff()}[name]
 def test_exact_bounded_exchange_and_candidate_only(self):
  e,w,p=self.setup_engine();r=e.run(self.load)
  self.assertEqual([(a[0],a[1]) for a in w.calls],[('GET',x.PREFIX+x.CANDIDATE),('GET',x.PREFIX+'public-key'),('PUT',x.PREFIX+x.CANDIDATE)])
  self.assertEqual(len(p.calls),1);self.assertEqual(p.calls[0][:2],('POST','/token'))
  q=parse_qs(p.calls[0][2].decode());self.assertEqual(q['client_secret'],['FIXTURE_CLIENT_SECRET']);self.assertNotIn('refresh_token',q)
  self.assertTrue(r['candidate_saved']);self.assertEqual(r['refresh_currently_valid'],'NOT_TESTED');self.assertEqual(r['channel_match'],'UNVERIFIED')
  self.assertNotIn('FIXTURE_CLIENT_SECRET',json.dumps(r));self.assertEqual(json.loads(OLD)['refresh_token'],'FIXTURE_OLD_REFRESH')
 def test_second_exchange_no_io(self):
  e,w,p=self.setup_engine();e.run(self.load)
  with self.assertRaises(Stop):e.run(self.load)
  self.assertEqual((len(w.calls),len(p.calls)),(3,1))
 def test_missing_existing_or_handoff_before_io(self):
  for missing in (x.EXISTING,x.HANDOFF):
   e,w,p=self.setup_engine()
   with self.assertRaises(Stop):e.run(lambda n:None if n==missing else self.load(n))
   self.assertEqual(w.calls,[]);self.assertEqual(p.calls,[])
 def test_client_and_redirect_and_state_mismatch_before_io(self):
  for change in ({'client_id':'99-other.apps.googleusercontent.com'},{'redirect_uri':'https://evil.example/'},{'state':'wrong'}):
   e,w,p=self.setup_engine()
   with self.assertRaises(Stop):e.run(lambda n:handoff(**change) if n==x.HANDOFF else OLD)
   self.assertEqual(w.calls,[]);self.assertEqual(p.calls,[])
 def test_handoff_expired(self):
  e,w,p=self.setup_engine();e.clock=lambda:1300
  with self.assertRaises(Stop):e.run(self.load)
  self.assertEqual(p.calls,[])
 def test_preflight_expiry_blocks_post_and_put(self):
  for after in (1300,1301,999):
   with self.subTest(after=after):
    e,w,p=self.setup_engine();clock=[1100];e.clock=lambda:clock[0]
    original=e.writer.preflight
    def delayed_preflight():
     original();clock[0]=after
    e.writer.preflight=delayed_preflight
    with self.assertRaises(Stop) as cm:e.run(self.load)
    self.assertEqual(str(cm.exception),'HANDOFF_LOCAL_WINDOW_STOP')
    self.assertEqual(e.posts,0);self.assertFalse(e.write_attempted)
    self.assertEqual(p.calls,[]);self.assertEqual([a[0] for a in w.calls],['GET','GET'])
    with self.assertRaises(Stop):e.run(self.load)
    self.assertEqual(len(w.calls),2);self.assertEqual(p.calls,[])
 def test_post_immediately_before_deadline_allowed_once(self):
  e,w,p=self.setup_engine();times=iter((1100,1100,1299,1299));e.clock=lambda:next(times)
  self.assertTrue(e.run(self.load)['candidate_saved'])
  self.assertEqual(e.posts,1);self.assertEqual(len(p.calls),1)
 def test_expiry_during_form_construction_blocks_post(self):
  e,w,p=self.setup_engine();clock=[1100];e.clock=lambda:clock[0]
  original=x.urlencode
  def slow_form(data):
   result=original(data);clock[0]=1300;return result
  with patch.object(x,'urlencode',side_effect=slow_form):
   with self.assertRaises(Stop):e.run(self.load)
  self.assertEqual(e.posts,0);self.assertEqual(p.calls,[]);self.assertEqual(len(w.calls),2)
 def test_candidate_exists_prevents_oauth(self):
  e,w,p=self.setup_engine();w.fn=lambda *args:(200,{'name':x.CANDIDATE})
  with self.assertRaises(Stop):e.run(self.load)
  self.assertEqual(len(w.calls),1);self.assertEqual(p.calls,[])
 def test_writer_permission_denied_before_oauth(self):
  e,w,p=self.setup_engine();w.fn=lambda *args:(403,{})
  with self.assertRaises(Stop):e.run(self.load)
  self.assertEqual(p.calls,[])
 def test_invalid_public_key_before_oauth(self):
  e,w,p=self.setup_engine();w.fn=lambda *args:(404,{}) if len(w.calls)==1 else (200,{'key':'bad','key_id':'fixed'})
  with self.assertRaises(Stop):e.run(self.load)
  self.assertEqual(p.calls,[])
 def test_missing_refresh_no_save(self):
  r=response();r.pop('refresh_token');e,w,p=self.setup_engine(payload=r)
  with self.assertRaises(Stop):e.run(self.load)
  self.assertEqual(len(w.calls),2)
 def test_missing_scope_unknown_no_save(self):
  r=response();r.pop('scope');e,w,p=self.setup_engine(payload=r)
  with self.assertRaises(Stop) as cm:e.run(self.load)
  self.assertEqual(str(cm.exception),'GRANTED_SCOPE_UNKNOWN_STOP');self.assertEqual(len(w.calls),2)
 def test_insufficient_scope_no_save(self):
  r=response();r['scope']=x.SCOPES[0];e,w,p=self.setup_engine(payload=r)
  with self.assertRaises(Stop):e.run(self.load)
  self.assertEqual(len(w.calls),2)
 def test_http_or_redirect_no_save_or_retry(self):
  for status in (400,403,302):
   e,w,p=self.setup_engine(status=status)
   with self.assertRaises(Stop):e.run(self.load)
   with self.assertRaises(Stop):e.run(self.load)
   self.assertEqual((len(w.calls),len(p.calls)),(2,1))
 def test_oauth_timeout_no_retry(self):
  e,w,p=self.setup_engine();p.fn=lambda *a:(_ for _ in ()).throw(TimeoutError('PRIVATE_ERROR'))
  with self.assertRaises(Stop):e.run(self.load)
  with self.assertRaises(Stop):e.run(self.load)
  self.assertEqual(len(p.calls),1);self.assertEqual(len(w.calls),2)
 def test_write_unexpected_update_is_unknown(self):
  e,w,p=self.setup_engine(ack=204)
  with self.assertRaises(Stop) as cm:e.run(self.load)
  self.assertEqual(str(cm.exception),'SECRET_WRITE_UNKNOWN_NO_RETRY')
  with self.assertRaises(Stop):e.run(self.load)
  self.assertEqual((len(w.calls),len(p.calls)),(3,1))
 def test_write_ack_lost_no_more_requests(self):
  e,w,p=self.setup_engine();old=w.fn
  w.fn=lambda *a:old(*a) if len(w.calls)<3 else (_ for _ in ()).throw(TimeoutError())
  with self.assertRaises(Stop):e.run(self.load)
  with self.assertRaises(Stop):e.run(self.load)
  self.assertEqual((len(w.calls),len(p.calls)),(3,1))
 def test_v2_provider_no_missing_fallback(self):
  post=Fixture(lambda form:(200,response()))
  provider=x.CandidateOAuthTokenProvider(lambda n:OLD if n==x.EXISTING else None,post,lambda:1000)
  with self.assertRaises(Stop):provider.get_access_token()
  self.assertEqual(post.calls,[])
 def test_v2_provider_reuses_old_secret_and_new_refresh(self):
  post=Fixture(lambda form:(200,response()));p=x.CandidateOAuthTokenProvider(lambda n:OLD if n==x.EXISTING else NEW,post,lambda:1000)
  self.assertEqual(p.get_access_token(),'FIXTURE_ACCESS');q=parse_qs(post.calls[0][0].decode())
  self.assertEqual(q['client_secret'],['FIXTURE_CLIENT_SECRET']);self.assertEqual(q['refresh_token'],['FIXTURE_NEW_REFRESH'])
 def test_native_provider_rejects_no_permit(self):
  with self.assertRaises(Stop):x.CandidateOAuthTokenProvider(Mock(),Mock(offline_mock=False),lambda:1000)
 def test_parked_gate_does_not_load_credentials(self):
  self.assertIsNone(x.local_gate(ROOT,{}))
  with patch.dict(os.environ,{'PLM_YOUTUBE_GAME_001':'PRIVATE_FIXTURE'}):
   out=subprocess.check_output(['python','-m','plm.automation.executors.oauth_exchange','--execute'],cwd=ROOT)
  self.assertEqual(json.loads(out)['status'],'PARKED');self.assertNotIn(b'PRIVATE_FIXTURE',out)
 def test_candidate_client_and_256_bit_state_are_pinned_without_execution(self):
  self.assertEqual(PLAN['client_id'],'559247977069-e50008qnmkuath6qbkbmetqsu6lvls84.apps.googleusercontent.com')
  self.assertEqual(PLAN['consent_state_entropy_bits'],256)
  nonce=base64.urlsafe_b64decode(PLAN['consent_state']+'=')
  self.assertEqual(len(nonce),32)
  self.assertFalse(PLAN['client_id_owner_verified']);self.assertFalse(PLAN['enabled'])
  self.assertFalse(PLAN['owner_approved']);self.assertFalse(PLAN['writer_permissions_reviewed'])
 def test_false_activation_cannot_bypass_unverified_client_gate(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=copy.deepcopy(PLAN);p.update(enabled=True,owner_approved=True,writer_permissions_reviewed=True,handoff_approved=True,operational_exclusion_attested=True)
   dest=Path(tmp)/x.PLAN;dest.parent.mkdir(parents=True);dest.write_text(json.dumps(p))
   with patch.object(x,'GitAudit') as git:
    with self.assertRaises(Stop) as cm:x.local_gate(tmp,{})
    self.assertEqual(str(cm.exception),'PUBLIC_CLIENT_ID_UNVERIFIED_STOP');git.assert_not_called()
 def test_full_workflow_parked_secret_after_gate_only(self):
  w=(ROOT/PLAN['workflow_path']).read_text()
  self.assertIn('if: ${{ false }}',w);self.assertNotIn('workflow_dispatch',w)
  self.assertLess(w.index('--prepare'),w.index('secrets.'));self.assertIn('persist-credentials: false',w)
  self.assertNotIn('upload-artifact',w)
  for key in x.SAFE:self.assertIn(key+": 'true'",w)
 def test_marker_absent_and_old_identity_unmodified(self):
  self.assertFalse((ROOT/PLAN['marker_path']).exists())
  self.assertNotIn('oauth-verify-20261012-r1',PLAN['identity'])
  self.assertFalse((ROOT/('audit-evidence/consumed/'+PLAN['protected_identity']+'.json')).exists())
 def test_libsodium_encryption_real_roundtrip_and_randomness(self):
  seal=x.SealedBox();lib=seal.lib
  lib.crypto_box_keypair.argtypes=[ctypes.c_void_p,ctypes.c_void_p];lib.crypto_box_keypair.restype=ctypes.c_int
  lib.crypto_box_seal_open.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulonglong,ctypes.c_void_p,ctypes.c_void_p];lib.crypto_box_seal_open.restype=ctypes.c_int
  pk=ctypes.create_string_buffer(32);sk=ctypes.create_string_buffer(32);self.assertEqual(lib.crypto_box_keypair(pk,sk),0)
  raw=NEW.encode();a=base64.b64decode(seal.encrypt(pk.raw,raw));b=base64.b64decode(seal.encrypt(pk.raw,raw));self.assertNotEqual(a,b)
  out=ctypes.create_string_buffer(len(raw));self.assertEqual(lib.crypto_box_seal_open(out,a,len(a),pk,sk),0);self.assertEqual(out.raw,raw)
 def test_native_transport_roles_sequence_and_error_body_zero(self):
  conn=Mock();r=Mock(status=403);conn.getresponse.return_value=r
  client=x.FixedHTTP(permit('LIVE_REVIEWED'),'google',connector=Mock(return_value=conn))
  form=b'client_id=fixture&client_secret=fixture&code=fixture&grant_type=authorization_code&redirect_uri=https%3A%2F%2Fdevelopers.google.com%2Foauthplayground'
  self.assertEqual(client('POST','/token',form),(403,{}));r.read.assert_not_called()
  with self.assertRaises(Stop):client('POST','/token',form)
  self.assertEqual(conn.request.call_count,1)
 def test_old_secret_and_other_repo_unaddressable(self):
  client=x.FixedHTTP(permit('LIVE_REVIEWED'),'github','FIXTURE_WRITER',connector=Mock())
  for method,path in [('PUT',x.PREFIX+x.EXISTING),('DELETE',x.PREFIX+x.CANDIDATE),('GET','/repos/other/project/actions/secrets/public-key')]:
   with self.assertRaises(Stop):client(method,path,{})
  self.assertEqual(client.calls,0);client.connector.assert_not_called()
 def test_save_http_sends_ciphertext_only(self):
  conn=Mock();r=Mock(status=201);conn.getresponse.return_value=r
  client=x.FixedHTTP(permit('LIVE_REVIEWED'),'github','FIXTURE_WRITER',connector=Mock(return_value=conn));client.calls=2
  client('PUT',x.PREFIX+x.CANDIDATE,{'encrypted_value':'CIPHERTEXT_ONLY','key_id':'fixed'})
  body=conn.request.call_args.kwargs['body'];self.assertNotIn(b'FIXTURE_NEW_REFRESH',body);self.assertEqual(set(json.loads(body)),{'encrypted_value','key_id'});r.read.assert_not_called()

class HistoryTests(unittest.TestCase):
 def fixture(self,extra_actual=False,extra_expected=False):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);root=Path(t.name)
  def git(*args):return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.DEVNULL).decode().strip()
  git('init');git('config','user.email','fixture@example.invalid');git('config','user.name','Offline fixture')
  (root/'base.txt').write_text('base');git('add','.');git('commit','-m','fixture base');parent=git('rev-parse','HEAD')
  p=copy.deepcopy(PLAN);p.update(enabled=True,client_id_owner_verified=True,owner_approved=True,operational_exclusion_attested=True,writer_permissions_reviewed=True,handoff_approved=True,client_id=CID,consent_state='s'*48,preparation_parent=parent)
  p['preparation_files']=sorted([x.PLAN,x.MANIFEST,p['workflow_path'],p['executor_path'],p['schema_path']]+(['base.txt'] if extra_expected else []))
  for f in p['preparation_files']:
   (root/f).parent.mkdir(parents=True,exist_ok=True);(root/f).write_text('fixture')
  if extra_expected:(root/'base.txt').write_text('base')
  if extra_actual:(root/'extra.txt').write_text('unapproved')
  (root/x.PLAN).write_text(json.dumps(p))
  (root/x.MANIFEST).write_text(json.dumps({'source_sha256':{f:x.sha((root/f).read_bytes()) for f in p['preparation_files'] if f!=x.MANIFEST}}))
  git('add','.');git('commit','-m','fixture preparation');prepared=git('rev-parse','HEAD')
  plan_sha=x.sha((root/x.PLAN).read_bytes());manifest_sha=x.sha((root/x.MANIFEST).read_bytes())
  m={'identity':p['identity'],'state':'CONSUMED_BEFORE_REMOTE','approved':True,'prepared_commit_sha':prepared,'plan_sha256':plan_sha,'manifest_sha256':manifest_sha,'workflow_sha256':x.sha((root/p['workflow_path']).read_bytes()),'executor_sha256':x.sha((root/p['executor_path']).read_bytes()),'schema_sha256':x.sha((root/p['schema_path']).read_bytes())}
  (root/p['marker_path']).parent.mkdir(parents=True);(root/p['marker_path']).write_text(json.dumps(m));git('add','.');git('commit','-m',p['marker_message']);head=git('rev-parse','HEAD')
  env={'GITHUB_REPOSITORY':x.REPO,'GITHUB_REF':'refs/heads/'+p['branch'],'GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':head,'GITHUB_RUN_ID':'123',**x.SAFE}
  return root,git,env,{'prepared':prepared,'plan_sha':plan_sha,'manifest_sha':manifest_sha}
 def test_actual_full_history_and_marker_chain_pass(self):
  root,git,env,pins=self.fixture();p=x.local_gate(root,env,**pins);self.assertEqual(p.mode,'LIVE_REVIEWED')
 def test_attempt_two_or_wrong_head_rejected(self):
  root,git,env,pins=self.fixture()
  for change in ({'GITHUB_RUN_ATTEMPT':'2'},{'GITHUB_SHA':'f'*40},{'GITHUB_REPOSITORY':'other/project'}):
   with self.assertRaises(Stop):x.local_gate(root,{**env,**change},**pins)
 def test_plan_or_manifest_pin_mismatch(self):
  root,git,env,pins=self.fixture()
  for key in ('plan_sha','manifest_sha'):
   with self.assertRaises(Stop):x.local_gate(root,env,**{**pins,key:'0'*64})
 def test_dirty_marker_or_worktree_refused(self):
  root,git,env,pins=self.fixture();(root/'unapproved.txt').write_text('not allowed')
  with self.assertRaises(Stop):x.local_gate(root,env,**pins)
 def test_shallow_repository_refused(self):
  root,git,env,pins=self.fixture();(root/'.git/shallow').write_text(git('rev-parse','HEAD')+'\n')
  with self.assertRaises(Stop):x.local_gate(root,env,**pins)


 def test_extra_actual_preparation_file_stops(self):
  root,git,env,pins=self.fixture(extra_actual=True)
  with self.assertRaises(Stop) as cm:x.local_gate(root,env,**pins)
  self.assertEqual(str(cm.exception),'PREPARATION_DIFF_STOP')
 def test_missing_actual_preparation_file_stops(self):
  root,git,env,pins=self.fixture(extra_expected=True)
  with self.assertRaises(Stop) as cm:x.local_gate(root,env,**pins)
  self.assertEqual(str(cm.exception),'PREPARATION_DIFF_STOP')
