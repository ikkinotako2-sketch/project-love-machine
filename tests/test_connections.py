import copy,json,pathlib,threading,unittest
from unittest.mock import Mock
from plm.automation.production_bridge import GitClaimLedger,scope_gate,READ,UPLOAD,media_gate
from plm.automation.content_adapters import ThemeAdapter,ScriptAdapter,MetricsAdapter,next_job
from plm.automation.ledger import Stop
class Backend:
 def __init__(self):self.record=None;self.sha=None;self.n=0;self.lock=threading.Lock()
 def read(self,path):return (self.sha,copy.deepcopy(self.record)) if self.record else None
 def write(self,path,sha,row):
  with self.lock:
   if self.sha!=sha:raise Stop('CAS_CONFLICT')
   self.n+=1;self.sha=f'{self.n:040x}';self.record=copy.deepcopy(row);return self.sha
class ConnectionTests(unittest.TestCase):
 def setup(self):b=Backend();l=GitClaimLedger(b,'plm-execution-state');c=l.claim('job','a'*64,'op','owner',100);return b,l,c
 def test_git_claim_send_result_persistent(self):
  b,l,c=self.setup();l.consume(c,'op',100);out=l.finish(c,'Done','offline0001');self.assertEqual(out['state'],'Done');self.assertEqual(b.n,3)
  with self.assertRaises(Stop):GitClaimLedger(b,'plm-execution-state').claim('job','a'*64,'op','owner',100)
 def test_atomic_creation_one_winner(self):
  b=Backend();barrier=threading.Barrier(2);results=[]
  def run(i):
   try:
    l=GitClaimLedger(b,'plm-execution-state');barrier.wait();l.claim('job','a'*64,'op','o'+str(i),100);results.append(True)
   except Stop:results.append(False)
  ts=[threading.Thread(target=run,args=(i,)) for i in range(2)]
  for t in ts:t.start()
  for t in ts:t.join()
  self.assertEqual(sorted(results),[False,True]);self.assertEqual(b.n,1)
 def test_write_uncertainty_no_more_writes(self):
  b,l,c=self.setup();b.write=Mock(side_effect=TimeoutError())
  with self.assertRaises(TimeoutError):l.consume(c,'op',100)
  with self.assertRaises(Stop):l.finish(c,'UNKNOWN',reason='UPLOAD_UNKNOWN')
  self.assertEqual(b.write.call_count,1)
 def test_unknown_persistent_no_reclaim(self):
  b,l,c=self.setup();l.consume(c,'op',100);l.finish(c,'UNKNOWN',reason='UPLOAD_UNKNOWN')
  self.assertTrue(b.record['notification_pending'])
  with self.assertRaises(Stop):GitClaimLedger(b,'plm-execution-state').claim('job','a'*64,'newop','new',999)
 def test_scope_upload_only_blocked(self):
  with self.assertRaises(Stop):scope_gate([UPLOAD],True)
 def test_scope_unknown_blocked(self):
  with self.assertRaises(Stop):scope_gate([UPLOAD,READ],False)
 def test_scope_read_and_upload(self):self.assertTrue(scope_gate([UPLOAD,READ],True))
 def test_unsupported_theme_rights(self):
  with self.assertRaises(Stop):ThemeAdapter(lambda:{'topic':'test','license':'unknown','verified':False,'source_id':'x'},rights_policy=['original']).next()
 def test_missing_generator_capability(self):
  f=Mock()
  with self.assertRaises(Stop):ScriptAdapter(f).generate({})
  f.assert_not_called()
 def test_theme_script_metrics_improvement_next(self):
  theme=ThemeAdapter(lambda:{'topic':'technical','source_id':'fixture','license':'original','verified':True},rights_policy=['original']).next()
  script=ScriptAdapter(lambda t:{'narration':'original','rights_verified':True},capability_verified=True).generate(theme)
  m=MetricsAdapter(lambda id:{'views':0,'likes':0,'comments':0},capability_verified=True);result={'state':'Done','job_id':'job','video_id':'offline0001'}
  self.assertEqual(m.improve(m.collect(result))['method'],'rules');seen=set();next_job(result,script,seen)
  with self.assertRaises(Stop):next_job(result,script,seen)
  with self.assertRaises(Stop):next_job({**result,'state':'UNKNOWN'},script,set())
 def test_metrics_missing_grant_never_reads(self):
  f=Mock()
  with self.assertRaises(Stop):MetricsAdapter(f).collect({'state':'Done'})
  f.assert_not_called()
 def test_machine_media_gate(self):
  root=pathlib.Path(__file__).resolve().parents[1];e=json.loads((root/'readiness/reused-render-evidence.json').read_text());j=json.loads((root/'readiness/youtube-private-job.json').read_text())
  # Test SHA without shipping/re-generating binary to CI: byte source is injected.
  with __import__('unittest.mock',fromlist=['patch']).patch('plm.automation.production_bridge.hashlib.sha256') as h:
   h.return_value.hexdigest.return_value=e['media_sha256'];self.assertTrue(media_gate(Mock(),e,j))
   j['description']='missing credit'
   with self.assertRaises(Stop):media_gate(Mock(),e,j)
 def test_unknown_scope_before_state_or_session(self):
  from plm.automation.production_bridge import execute_private
  ledger=Mock();session=Mock()
  with self.assertRaises(Stop):execute_private(scope_evidence={'scopes':['https://www.googleapis.com/auth/youtube.upload'],'proven':True},gate=lambda:True,media=Mock(),evidence={},job={},session_factory=session,ledger=ledger,upload_transport=Mock(),callback=Mock(),clock=lambda:100,run={})
  session.assert_not_called();ledger.claim.assert_not_called()
 def test_contents_budget_and_no_main_branch(self):
  from plm.automation.production_bridge import GitHubContentsBackend
  transport=Mock(side_effect=[(404,{}),(201,{'content':{'sha':'a'*40}})])
  b=GitHubContentsBackend(transport);self.assertIsNone(b.read('youtube-once/job.json'));self.assertEqual(b.write('youtube-once/job.json',None,{'job_id':'job'}),'a'*40)
  self.assertEqual(transport.call_args[0][2]['branch'],'plm-execution-state')
  with self.assertRaises(Stop):b.read('youtube-once/../main.json')
 def test_transport_not_authorized_is_parked(self):
  from plm.automation.production_bridge import BoundedGitHubTransport
  with self.assertRaises(Stop):BoundedGitHubTransport('FIXTURE')
 def test_credits_audience_and_render_evidence_immutable(self):
  root=pathlib.Path(__file__).resolve().parents[1]
  e=json.loads((root/'readiness/reused-render-evidence.json').read_text());j=json.loads((root/'readiness/youtube-private-job.json').read_text())
  with __import__('unittest.mock',fromlist=['patch']).patch('plm.automation.production_bridge.hashlib.sha256') as h:
   h.return_value.hexdigest.return_value=e['media_sha256']
   for field,value in [('notify_subscribers',True),('contains_synthetic_media',False),('made_for_kids',True),('privacy_status','public')]:
    bad=copy.deepcopy(j);bad[field]=value
    with self.assertRaises(Stop):media_gate(Mock(),e,bad)
