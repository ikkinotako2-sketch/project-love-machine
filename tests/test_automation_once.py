import hashlib,json,pathlib,sqlite3,tempfile,threading,unittest
from unittest.mock import Mock
from plm.automation.ledger import Ledger,Stop
from plm.automation.strict_upload import ChannelSession,StrictUploader,HttpsSingleSend,valid_location,CHANNEL
from plm.automation.loop import OfflineLoop,FLAGS,mock
ROOT=pathlib.Path(__file__).resolve().parents[1]
NOW=1000
class Fixture(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=pathlib.Path(self.temp.name)/'ledger.sqlite';self.l=Ledger(self.path);self.addCleanup(self.l.close)
  self.media=pathlib.Path(self.temp.name)/'test.mp4';self.media.write_bytes(b'x'*12000);self.sha=hashlib.sha256(self.media.read_bytes()).hexdigest()
 def job(self):self.l.add('job','a'*64,NOW);return self.l.claim('job','owner',NOW)
 def session(self,channel=CHANNEL):return ChannelSession.from_mine_response('FIXTURE_NOT_LIVE',200,json.dumps({'kind':'youtube#channelListResponse','items':[{'id':channel}]}).encode(),NOW+3600,lambda:NOW)
 def proof(self):return {'upload_approved':True,'marker_consumed_before_remote':True,'marker_identity':'upload-op','source_pins_exact':True,'rights_verified':True,'quality_pass':True,'run_attempt':1,'job_id':'job','expected_channel_id':CHANNEL,'privacy_status':'private','notify_subscribers':False,'scheduled_for':'','made_for_kids':False,'contains_synthetic_media':True,'title':'fixture','description':'VOICEVOX:ずんだもん','media_sha256':self.sha}
 def transport(self):
  t=Mock();t.init.return_value='session';t.media.return_value=(200,json.dumps({'id':'offline0001','snippet':{'channelId':CHANNEL},'status':{'privacyStatus':'private'}}).encode());return t

class LedgerTests(Fixture):
 def test_duplicate_same_no_op_changed_rejected(self):
  self.l.add('job','a'*64,NOW);self.assertFalse(self.l.add('job','a'*64,NOW));
  with self.assertRaises(Stop):self.l.add('job','b'*64,NOW)
 def test_claim_survives_restart(self):
  claim=self.job();other=Ledger(self.path)
  try:
   self.assertEqual(other.get('job'),claim)
   with self.assertRaises(Stop):other.claim('job','another',NOW)
  finally:other.close()
 def test_lease_pre_sent_reclaim_fences_old_owner(self):
  c=self.job();n=self.l.claim('job','next',NOW+301);self.assertEqual(n['fence'],2)
  with self.assertRaises(Stop):self.l.consume(c,'old',NOW+301)
  self.l.consume(n,'new',NOW+301)
 def test_sent_lease_never_reclaims(self):
  c=self.job();self.l.consume(c,'upload-op',NOW)
  with self.assertRaises(Stop):self.l.claim('job','next',NOW+301)
  self.l.recover_crash(NOW+301);self.assertEqual(self.l.get('job')['state'],'UNKNOWN')
  with self.assertRaises(Stop):self.l.claim('job','next',NOW+500)
 def test_sent_tombstone_not_deletable(self):
  c=self.job();self.l.consume(c,'upload-op',NOW)
  with self.assertRaises(sqlite3.IntegrityError):self.l.db.execute('DELETE FROM jobs')
  with self.assertRaises(sqlite3.IntegrityError):self.l.db.execute('UPDATE jobs SET sent=0')
 def test_terminal_unknown_immutable(self):
  c=self.job();self.l.consume(c,'upload-op',NOW);self.l.finish(c,'UNKNOWN',reason='UPLOAD_UNKNOWN')
  with self.assertRaises(sqlite3.IntegrityError):self.l.db.execute("UPDATE jobs SET state='Pending'")
 def test_stale_result_rejected(self):
  c=self.job();self.l.claim('job','next',NOW+301)
  with self.assertRaises(Stop):self.l.finish(c,'Done','offline0001')
 def test_eight_competing_claims_one_winner(self):
  self.l.add('job','a'*64,NOW);barrier=threading.Barrier(8);wins=[];errs=[]
  def run(i):
   l=Ledger(self.path)
   try:
    barrier.wait();l.claim('job','owner-'+str(i),NOW);wins.append(i)
   except Stop:pass
   except Exception as e:errs.append(type(e).__name__)
   finally:l.close()
  ts=[threading.Thread(target=run,args=(i,)) for i in range(8)]
  for t in ts:t.start()
  for t in ts:t.join(10)
  self.assertEqual(len(wins),1);self.assertEqual(errs,[])
 def test_budget_persists_and_concurrent_reservations(self):
  cost={'jobs':1,'minutes':20,'units':100,'bytes':1};limits={'jobs':1,'minutes':20,'units':100,'bytes':1}
  self.l.reserve_budget('2026-10-12',cost,limits)
  with self.assertRaises(Stop):self.l.reserve_budget('2026-10-12',cost,limits)
 def test_negative_budget_stops(self):
  with self.assertRaises(Stop):self.l.reserve_budget('2026-10-12',{'jobs':-1},{'jobs':1})
 def test_no_freeform_error_storage(self):
  with self.assertRaises(Stop):self.l.finish(self.job(),'Failed',reason='Bearer BAD_TOKEN')
 def test_progress_omits_arbitrary_payload(self):
  c=self.job();self.l.finish(c,'Failed',reason='RENDER_FAILED');p=self.l.progress();self.assertTrue(p['stopped']);self.assertEqual(p['success_rate'],0);self.assertEqual(len(p['notifications']),1)

class UploadTests(Fixture):
 def test_ack_durable_and_session_cleared(self):
  c=self.job();s=self.session();t=self.transport();out=StrictUploader(self.l,t,lambda:NOW).upload(c,'upload-op',s,self.media,self.proof())
  self.assertEqual(out['state'],'Done');self.assertIsNone(s._token);self.assertEqual(t.init.call_count,1);self.assertEqual(t.media.call_count,1)
 def test_sentinel_before_init_and_media(self):
  t=self.transport();t.init.side_effect=lambda *a: 'session' if self.l.get('job')['sent']==1 else self.fail('SENT_NOT_DURABLE')
  StrictUploader(self.l,t,lambda:NOW).upload(self.job(),'upload-op',self.session(),self.media,self.proof())
 def test_every_gate_prevents_all_transport(self):
  for k in ['upload_approved','marker_consumed_before_remote','source_pins_exact','rights_verified','quality_pass']:
   with self.subTest(k=k):
    t=self.transport();p=self.proof();p[k]=False
    c=self.l.get('job') or self.job()
    with self.assertRaises(Stop):StrictUploader(self.l,t,lambda:NOW).upload(c,'upload-op',self.session(),self.media,p)
    t.init.assert_not_called();t.media.assert_not_called();self.assertEqual(self.l.get('job')['sent'],0)
 def test_policy_mismatch_stops(self):
  c=self.job()
  for k,v in [('run_attempt',2),('run_attempt',True),('privacy_status','public'),('notify_subscribers',True),('scheduled_for','tomorrow'),('expected_channel_id','wrong'),('marker_identity','other'),('media_sha256','b'*64),('made_for_kids',None)]:
   p=self.proof();p[k]=v;t=self.transport()
   with self.assertRaises(Stop):StrictUploader(self.l,t,lambda:NOW).upload(c,'upload-op',self.session(),self.media,p)
   t.init.assert_not_called()
 def test_timeout_init_no_media_and_no_resend(self):
  c=self.job();t=self.transport();t.init.side_effect=TimeoutError('SECRET_BODY')
  out=StrictUploader(self.l,t,lambda:NOW).upload(c,'upload-op',self.session(),self.media,self.proof());self.assertEqual(out['state'],'UNKNOWN');t.media.assert_not_called();self.assertNotIn('SECRET_BODY',json.dumps(out))
  with self.assertRaises(Stop):StrictUploader(self.l,self.transport(),lambda:NOW).upload(c,'upload-op',self.session(),self.media,self.proof())
 def test_timeout_media_no_recovery(self):
  t=self.transport();t.media.side_effect=TimeoutError();out=StrictUploader(self.l,t,lambda:NOW).upload(self.job(),'upload-op',self.session(),self.media,self.proof());self.assertEqual(out['state'],'UNKNOWN');self.assertEqual(t.media.call_count,1)
 def test_non_ack_unknown(self):
  for status in [308,302,403,429,500]:
   with self.subTest(status=status):
    job='job'+str(status);self.l.add(job,'a'*64,NOW);c=self.l.claim(job,'owner',NOW);p=self.proof();p['job_id']=job;p['marker_identity']='op'+str(status)
    t=self.transport();t.media.return_value=(status,b'RAW_SECRET_ERROR');out=StrictUploader(self.l,t,lambda:NOW).upload(c,p['marker_identity'],self.session(),self.media,p);self.assertEqual(out['state'],'UNKNOWN');self.assertNotIn('RAW_SECRET_ERROR',json.dumps(out))
 def test_ack_wrong_channel_or_public_unknown(self):
  for i,ack in enumerate([{'id':'offline0001','snippet':{'channelId':'wrong'},'status':{'privacyStatus':'private'}},{'id':'offline0001','snippet':{'channelId':CHANNEL},'status':{'privacyStatus':'public'}},{}]):
   job='j'+str(i);self.l.add(job,'a'*64,NOW);c=self.l.claim(job,'owner',NOW);p=self.proof();p.update(job_id=job,marker_identity='op'+str(i));t=self.transport();t.media.return_value=(200,json.dumps(ack).encode());self.assertEqual(StrictUploader(self.l,t,lambda:NOW).upload(c,p['marker_identity'],self.session(),self.media,p)['state'],'UNKNOWN')
 def test_channel_proof_wrong_or_ambiguous_rejected(self):
  for body in [{'kind':'youtube#channelListResponse','items':[]},{'kind':'youtube#channelListResponse','items':[{'id':CHANNEL}]*2},{'kind':'youtube#channelListResponse','items':[{'id':CHANNEL}],'nextPageToken':'next'}]:
   with self.assertRaises(Stop):ChannelSession.from_mine_response('FIXTURE',200,json.dumps(body).encode(),NOW+3600,lambda:NOW)
  with self.assertRaises(Stop):self.session('wrong')
 def test_expired_token_never_refreshes(self):
  with self.assertRaises(Stop):ChannelSession.from_mine_response('FIXTURE',200,json.dumps({'kind':'youtube#channelListResponse','items':[{'id':CHANNEL}]}).encode(),NOW+100,lambda:NOW)
 def test_token_repr_redacted(self):self.assertNotIn('FIXTURE',repr(self.session()))
 def test_live_transport_requires_explicit_permission(self):
  with self.assertRaises(Stop):HttpsSingleSend()
 def test_location_allowlist(self):
  self.assertEqual(valid_location('https://www.googleapis.com/upload/youtube/v3/videos?upload_id=fixture'),'/upload/youtube/v3/videos?upload_id=fixture')
  for url in ['http://www.googleapis.com/upload/youtube/v3/videos?upload_id=x','https://evil.test/upload/youtube/v3/videos?upload_id=x','https://www.googleapis.com@evil.test/upload/youtube/v3/videos?upload_id=x','https://www.googleapis.com/upload/youtube/v3/videos?upload_id=x&upload_id=y','https://www.googleapis.com/upload/youtube/v3/videos?unknown=x&upload_id=x']:
   with self.assertRaises(Stop):valid_location(url)

class LoopTests(Fixture):
 def setup_loop(self,**overrides):
  config=json.loads((ROOT/'readiness/youtube-automation-plan.json').read_text());config.update(overrides)
  @mock
  def upload(c,m):
   self.l.consume(c,'op-'+c['job_id'],NOW);return self.l.finish(c,'Done','offline0001')
  return OfflineLoop(self.l,config,theme=mock(lambda:'theme'),script=mock(lambda t:{'rights_verified':True,'narration':'original'}),render=mock(lambda p:{'quality_pass':True}),upload_mock=upload,metrics_mock=mock(lambda r:{'source':'OFFLINE_FIXTURE','views':0}),clock=lambda:NOW)
 def test_bounded_day_two_jobs_then_stop(self):
  loop=self.setup_loop();self.assertEqual(loop.tick('j1')['state'],'Done');self.assertEqual(loop.tick('j2')['state'],'Done');self.assertEqual(loop.tick('j3')['state'],'STOP');self.assertTrue(loop.stopped)
 def test_duplicate_job_no_second_upload(self):
  loop=self.setup_loop();loop.tick('j1');self.assertEqual(loop.tick('j1')['state'],'DUPLICATE_NO_OP');self.assertEqual(self.l.get('j1')['sent'],1)
 def test_emergency_stop_no_job(self):
  loop=self.setup_loop(operator_stop=True);self.assertEqual(loop.tick('j1')['reason'],'EMERGENCY_STOP');self.assertIsNone(self.l.get('j1'))
 def test_render_failure_safe_and_notification(self):
  loop=self.setup_loop();stages=list(loop.stages);stages[2]=mock(lambda p: {'quality_pass':False});loop.stages=tuple(stages)
  self.assertEqual(loop.tick('j1')['state'],'Failed');self.assertEqual(self.l.get('j1')['sent'],0);self.assertEqual(len(self.l.progress()['notifications']),1)
 def test_live_config_rejected(self):
  with self.assertRaises(Stop):self.setup_loop(live_enabled=True)
 def test_flags_rejected(self):
  for flag in FLAGS:
   with self.assertRaises(Stop):self.setup_loop(flags={**FLAGS,flag:False})
 def test_unknown_halts_future_jobs(self):
  loop=self.setup_loop();stages=list(loop.stages)
  @mock
  def unknown(c,m):self.l.consume(c,'unknown-op',NOW);return self.l.finish(c,'UNKNOWN',reason='UPLOAD_UNKNOWN')
  stages[3]=unknown;loop.stages=tuple(stages);self.assertEqual(loop.tick('j1')['state'],'UNKNOWN')
  with self.assertRaises(Stop):loop.tick('j2')
 def test_non_mock_transport_rejected(self):
  config=json.loads((ROOT/'readiness/youtube-automation-plan.json').read_text())
  with self.assertRaises(Stop):OfflineLoop(self.l,config,theme=lambda:'theme',script=lambda x:x,render=lambda x:x,upload_mock=lambda x,y:None,metrics_mock=lambda x:x,clock=lambda:NOW)
 def test_real_artifact_to_mock_results(self):
  from readiness.simulate_automation import run
  report=run(self.media,{'media_sha256':self.sha,'quality':{'ok':True}},pathlib.Path(self.temp.name)/'evidence')
  self.assertEqual(report['real_uploads'],0);self.assertEqual(report['progress']['counts']['Done'],2)

class SourceIsolationTests(unittest.TestCase):
 def test_main_runtime_bytes_unchanged(self):
  manifest=json.loads((ROOT/'readiness/youtube-automation-source-hashes.json').read_text())
  for p,h in manifest['legacy_sha256'].items():self.assertEqual(hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),h)
 def test_no_execution_marker(self):
  self.assertFalse((ROOT/'audit-evidence/consumed/provider-neutral-youtube-private-upload-20261012-r1.json').exists())
  self.assertFalse((ROOT/'audit-evidence/consumed/provider-neutral-youtube-channel-verify-20261012-r1.json').exists())
 def test_ci_has_no_secret_dispatch_or_cron(self):
  workflow=(ROOT/'.github/workflows/plm-youtube-offline-automation.yml').read_text()
  for forbidden in ['secrets.','workflow_dispatch:','schedule:','wrangler','youtube_job','strict_upload']:
   self.assertNotIn(forbidden,workflow)
 def test_sandbox_source_pins_and_schema(self):
  fixture=ROOT/'readiness/sandbox-contract-fixture';manifest=json.loads((fixture/'readiness/runtime-composition-source-hashes.json').read_text())
  for p,h in manifest.items():self.assertEqual(hashlib.sha256((fixture/p).read_bytes()).hexdigest(),h)
  db=sqlite3.connect(':memory:');db.execute('PRAGMA foreign_keys=ON')
  for name in ['0008_provider_neutral_roundtrip_backend.sql','0009_youtube_queue_result_proposal.sql','0010_youtube_pipeline_checkpoint_candidate.sql']:
   db.executescript((fixture/'serverless/migrations'/name).read_text())
  for namespace,expected in [('plm_ytq_v1_',{'table':3,'trigger':10,'index':6}),('plm_ytp_v1_',{'table':1,'trigger':3,'index':3})]:
   counts={k:db.execute("SELECT count(*) FROM sqlite_master WHERE type=? AND (name LIKE ? OR (type='index' AND tbl_name LIKE ?))",(k,namespace+'%',namespace+'%')).fetchone()[0] for k in expected}
   self.assertEqual(counts,expected)
  db.close()

class GateTests(unittest.TestCase):
 def fixture(self):
  from plm.automation import upload_gate as g
  source={'candidate.py':b'offline'};manifest={'candidate_sha256':{'candidate.py':hashlib.sha256(b'offline').hexdigest()}}
  marker={'identity':g.IDENTITY,'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':'a'*40,'job_id':g.JOB,'expected_channel_id':g.CHANNEL,'media_sha256':'b'*64,'source_manifest_sha256':hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'upload_approved':True}
  env={'repository':g.REPO,'event':'push','run_attempt':1,'flags':FLAGS.copy()}
  facts={'full_history':True,'marker_absent_parent':True,'marker_diff':[g.MARKER],'parent':'a'*40,'head_parent':'a'*40,'message':'PLM YouTube private upload once '+g.IDENTITY,'historical_markers_unchanged':True,'existing_runs':0,'channel_prerequisite_verified':True}
  return marker,env,facts,manifest,source,'b'*64
 def test_exact_future_gate(self):
  from plm.automation.upload_gate import validate
  self.assertTrue(validate(*self.fixture()))
 def test_missing_prior_channel_or_history_or_consumed_rejected(self):
  from plm.automation.upload_gate import validate
  for k,v in [('channel_prerequisite_verified',False),('full_history',False),('marker_absent_parent',False),('existing_runs',1),('historical_markers_unchanged',False),('marker_diff',['other'])]:
   a=self.fixture();a[2][k]=v
   with self.assertRaises(Stop):validate(*a)
 def test_source_drift_and_changed_marker_rejected(self):
  from plm.automation.upload_gate import validate
  a=self.fixture();a[4]['candidate.py']+=b'x'
  with self.assertRaises(Stop):validate(*a)
  a=self.fixture();a[0]['identity']='old'
  with self.assertRaises(Stop):validate(*a)

class HttpBoundaryTests(unittest.TestCase):
 class Response:
  def __init__(self,status=200,location='https://www.googleapis.com/upload/youtube/v3/videos?upload_id=fixture',body=b'{}'):self.status=status;self.location=location;self.body=body
  def getheader(self,k):return self.location
  def read1(self,n):b=self.body[:n];self.body=self.body[n:];return b
 class Conn:
  def __init__(self,response,events,fail=False):self.r=response;self.events=events;self.fail=fail;self.sock=Mock()
  def request(self,method,path,**kwargs):self.events.append(method)
  def connect(self):pass
  def putrequest(self,method,path):self.events.append(method)
  def putheader(self,*a):pass
  def endheaders(self):pass
  def send(self,data):
   if self.fail:raise TimeoutError('TOKEN_SECRET')
  def getresponse(self):return self.r
  def close(self):pass
 def test_init_once_media_once_no_status_request(self):
  events=[];factory=Mock(side_effect=[self.Conn(self.Response(),events),self.Conn(self.Response(body=b'{"id":"offline0001"}'),events)])
  t=HttpsSingleSend(operation_approved=True,connection=factory)
  p=t.init('FIXTURE',{},12000)
  with tempfile.TemporaryFile() as f:
   f.write(b'x'*12000);f.seek(0);status,body=t.media('FIXTURE',p,f)
  self.assertEqual(events,['POST','PUT']);self.assertEqual(status,200)
  with self.assertRaises(Stop):t.init('FIXTURE',{},12000)
  with self.assertRaises(Stop):t.media('FIXTURE',p,None)
 def test_error_body_never_read(self):
  r=self.Response(status=403,body=b'REMOTE_SECRET');r.read1=Mock(side_effect=AssertionError('ERROR_READ'))
  events=[];factory=Mock(side_effect=[self.Conn(self.Response(),events),self.Conn(r,events)])
  t=HttpsSingleSend(operation_approved=True,connection=factory);p=t.init('FIXTURE',{},12000)
  with tempfile.TemporaryFile() as f:
   f.write(b'x'*12000);f.seek(0);self.assertEqual(t.media('FIXTURE',p,f),(403,b''))
  r.read1.assert_not_called()
 def test_redirect_is_not_followed(self):
  events=[];t=HttpsSingleSend(operation_approved=True,connection=lambda *a,**k:self.Conn(self.Response(status=302),events))
  with self.assertRaises(Stop):t.init('FIXTURE',{},12000)
  self.assertEqual(events,['POST'])
 def test_timeout_no_recovery(self):
  events=[];factory=Mock(side_effect=[self.Conn(self.Response(),events),self.Conn(self.Response(),events,fail=True)])
  t=HttpsSingleSend(operation_approved=True,connection=factory);p=t.init('FIXTURE',{},12000)
  with tempfile.TemporaryFile() as f:
   f.write(b'x'*12000);f.seek(0)
   with self.assertRaises(TimeoutError):t.media('FIXTURE',p,f)
  self.assertEqual(factory.call_count,2);self.assertEqual(events,['POST','PUT'])
