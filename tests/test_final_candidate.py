import copy,json,pathlib,tempfile,unittest
from unittest.mock import Mock
from plm.automation.final_candidate import IntegratedCandidate, Journal, REASONS, FLAGS, publication_gate, reject_live, command_center
from plm.automation.production_bridge import GitClaimLedger,GitHubContentsBackend,ExclusiveGitClaimLedger,READ,UPLOAD,CHANNEL
from plm.automation.ledger import Ledger,Stop

ROOT=pathlib.Path(__file__).resolve().parents[1]
MEDIA=pathlib.Path(__import__('os').environ.get('PLM_OFFLINE_MEDIA', str(ROOT.parent/'deliverables/plm-offline-proof/short.mp4')))

class Gates(unittest.TestCase):
 def facts(self):return {'flags':FLAGS,'execution_approved':True,'repository':'ikkinotako2-sketch/project-love-machine','attempt':1,'run_id':'123','commit':'a'*40,'approved_commit':'a'*40,**{k:True for k in ['source_hashes_exact','workflow_hash_exact','artifact_origin_exact','marker_only_history_exact','marker_consumed','durable_state_ready','shared_uncertainty_guard_ready','budget_observation_fresh','callback_provenance_ready']},'artifact_expires_at':10000,'credential_expires_at':10000,'channel_verified':True,'channel_id':CHANNEL,'scopes':[READ,UPLOAD],'scope_proven':True,'privacy':'private','notify_subscribers':False,'remaining_budget':{'jobs':1,'minutes':10,'units':1000,'bytes':1000000}}
 def test_pure_gate_and_live_unconditionally_unreachable(self):
  self.assertTrue(publication_gate(self.facts(),100))
  for flags in (FLAGS,{k:False for k in FLAGS}):
   with self.assertRaises(Stop):reject_live(flags=flags,approved=True)
 def test_each_required_proof_missing_stops(self):
  for key in self.facts():
   if key=='flags':continue
   bad=self.facts();bad.pop(key)
   with self.subTest(key=key),self.assertRaises(Stop):publication_gate(bad,100)
 def test_scope_upload_only_no_gate(self):
  bad=self.facts();bad['scopes']=[UPLOAD]
  with self.assertRaises(Stop):publication_gate(bad,100)
 def test_artifact_expired(self):
  bad=self.facts();bad['artifact_expires_at']=99
  with self.assertRaises(Stop):publication_gate(bad,100)
 def test_unknown_budget(self):
  bad=self.facts();bad['remaining_budget']=None
  with self.assertRaises(Stop):publication_gate(bad,100)
 def test_channel_mismatch(self):
  bad=self.facts();bad['channel_id']='wrong'
  with self.assertRaises(Stop):publication_gate(bad,100)
 def test_no_secret_binding_and_job_never_runs(self):
  source=(ROOT/'.github/workflows/plm-youtube-production-candidate-parked.yml').read_text()
  self.assertIn('if: ${{ false }}',source);self.assertNotIn('secrets.',source);self.assertNotIn('schedule:',source)
 def test_read_uncertainty_blocks_subsequent_claim(self):
  backend=Mock();backend.read.side_effect=TimeoutError();l=GitClaimLedger(backend,'plm-execution-state')
  for job in ['job','different-job']:
   with self.assertRaises(Stop):l.claim(job,'a'*64,'op','owner',100)
  self.assertEqual(backend.read.call_count,1);backend.write.assert_not_called()
 def test_backend_write_unknown_permanently_latches(self):
  transport=Mock(return_value=(200,{'content':{}}));b=GitHubContentsBackend(transport)
  with self.assertRaises(Stop):b.write('youtube-once/job.json',None,{'job_id':'job'})
  with self.assertRaises(Stop):b.read('youtube-once/other.json')
  self.assertEqual(transport.call_count,1)
 def test_unrelated_repo_and_traversal_rejected(self):
  t=Mock();b=GitHubContentsBackend(t)
  for path in ['../x','youtube-once/../x.json','youtube-once/a.json?ref=main']:
   with self.assertRaises(Stop):b.read(path)
  t.assert_not_called()
 def test_report_html_escaping_and_unknown_fields_not_leaked(self):
  d={'mode':'OFFLINE_SIMULATION','live_enabled':False,'last_success':'<script>alert(1)</script>','token':'DO_NOT_SHOW'}
  h=command_center(d);self.assertNotIn('<script>',h);self.assertNotIn('DO_NOT_SHOW',h);self.assertIn('&lt;script&gt;',h)
 def test_shared_global_claim_survives_lost_ack_and_new_runner(self):
  rows={};guard=Mock()
  guard.read.side_effect=lambda path:rows.get(path)
  def write(path,sha,row):rows[path]=('a'*40,row);raise TimeoutError()
  guard.write.side_effect=write;backend=Mock()
  first=ExclusiveGitClaimLedger(backend,guard,'plm-execution-state')
  with self.assertRaises(Stop):first.claim('job','a'*64,'op','owner',100)
  second=ExclusiveGitClaimLedger(backend,guard,'plm-execution-state')
  with self.assertRaises(Stop):second.claim('different-job','b'*64,'new-op','new-owner',100)
  self.assertEqual(guard.write.call_count,1);backend.write.assert_not_called()
 def test_global_lock_is_not_released_even_on_success(self):
  guard=Mock();guard.read.return_value=None;guard.write.return_value='a'*40
  backend=Mock();backend.read.return_value=None;backend.write.return_value='b'*40
  l=ExclusiveGitClaimLedger(backend,guard,'plm-execution-state');l.claim('job','a'*64,'op','owner',100)
  with self.assertRaises(Stop):l.claim('next','b'*64,'next-op','owner',101)
  self.assertEqual(guard.write.call_count,1);self.assertEqual(backend.write.call_count,1)
 def test_two_different_jobs_global_atomic_claim_one_winner(self):
  import threading
  lock=threading.Lock();barrier=threading.Barrier(2);rows={};writes=[];wins=[]
  class Guard:
   def read(self,path):barrier.wait();return None
   def write(self,path,sha,row):
    with lock:
     if path in rows:raise Stop('CAS_CONFLICT')
     rows[path]=row;writes.append(path);return 'a'*40
  def run(i):
   backend=Mock();backend.read.return_value=None;backend.write.return_value='b'*40
   ledger=ExclusiveGitClaimLedger(backend,Guard(),'plm-execution-state')
   try:ledger.claim('job-'+str(i),'a'*64,'op-'+str(i),'owner',100);wins.append(True)
   except Stop:wins.append(False)
  ts=[threading.Thread(target=run,args=(i,)) for i in range(2)]
  for t in ts:t.start()
  for t in ts:t.join()
  self.assertEqual(sorted(wins),[False,True]);self.assertEqual(len(writes),1)
 def test_source_drift_rejected(self):
  from readiness.verify_final_sources import verify
  p='readiness/final_candidate_entrypoint.py';h=__import__('hashlib').sha256((ROOT/p).read_bytes()).hexdigest()
  self.assertTrue(verify({'source_sha256':{p:h}}))
  with self.assertRaises(ValueError):verify({'source_sha256':{p:'0'*64}})

class Integrated(unittest.TestCase):
 def setUp(self):
  if not MEDIA.is_file():self.skipTest('Actual fixed MP4 required: dedicated CI downloads pinned artifact')
  self.tmp=tempfile.TemporaryDirectory();self.db=pathlib.Path(self.tmp.name)/'state.db';self.now=1791763200
  self.p=IntegratedCandidate(self.db,MEDIA,clock=lambda:self.now,artifact_expires_at=self.now+172900)
 def tearDown(self):self.p.close();self.tmp.cleanup()
 def test_48_hours_reuse_actual_video_strict_upload_result_metrics_next(self):
  for hour in range(49):
   self.now=1791763200+hour*3600
   if hour in (0,12,24,36):
    result=self.p.tick('first-job' if self.p.next_id is None else self.p.next_id);self.assertEqual(result['state'],'Done')
  r=self.p.report();self.assertEqual(r['counts']['Done'],4);self.assertFalse(r['stopped']);self.assertEqual(r['real_uploads'],0);self.assertEqual(r['render_success_rate'],1)
  self.assertTrue(all(x['jobs']<=2 for x in r['budgets']));self.assertEqual(len(self.p.upload.calls),8)
 def test_all_faults_halt_without_followup_after_restart(self):
  for i,reason in enumerate(sorted(REASONS-{'CLAIM_CONFLICT_STOP','CONFIG_STOP'})):
   with self.subTest(reason=reason):
    db=pathlib.Path(self.tmp.name)/f'fault-{i}.db';p=IntegratedCandidate(db,MEDIA,clock=lambda:self.now,artifact_expires_at=self.now+10000)
    result=p.tick('fault-job',reason);calls=len(p.upload.calls);self.assertNotEqual(result['state'],'Done');self.assertIsNone(p.next_id);self.assertTrue(p.j.stopped())
    self.assertEqual(p.tick('next')['state'],'STOP');self.assertEqual(len(p.upload.calls),calls);p.close()
    p=IntegratedCandidate(db,MEDIA,clock=lambda:self.now+100,artifact_expires_at=self.now+10000)
    self.assertEqual(p.tick('after-restart')['state'],'STOP');self.assertEqual(p.upload.calls,[]);self.assertGreater(p.report()['undelivered_notifications'],0);p.close()
 def test_duplicate_never_second_upload(self):
  self.assertEqual(self.p.tick('same')['state'],'Done');n=len(self.p.upload.calls)
  self.assertNotEqual(self.p.tick('same')['state'],'Done');self.assertEqual(len(self.p.upload.calls),n)
 def test_callback_unknown_blocks_next_but_retains_saved_upload(self):
  result=self.p.tick('callback','CALLBACK_UNKNOWN');self.assertEqual(result['reason_code'],'CALLBACK_UNKNOWN');self.assertEqual(self.p.l.get('callback')['state'],'Done');self.assertIsNone(self.p.next_id)
 def test_pending_sent_restart_is_unknown_not_reclaimed(self):
  self.p.l.add('crashed','a'*64,self.now);claim=self.p.l.claim('crashed','owner',self.now);self.p.l.consume(claim,'crash-op',self.now)
  self.p.close();self.p=IntegratedCandidate(self.db,MEDIA,clock=lambda:self.now,artifact_expires_at=self.now+10000)
  self.assertEqual(self.p.l.get('crashed')['state'],'UNKNOWN');self.assertEqual(self.p.tick('new')['state'],'STOP')
 def test_daily_budget_atomic_safe_stop(self):
  for i in range(2):self.assertEqual(self.p.tick('budget-'+str(i))['state'],'Done')
  self.assertEqual(self.p.tick('budget-third')['state'],'STOP');self.assertEqual(self.p.report()['budgets'][0]['jobs'],2);self.assertEqual(len(self.p.upload.calls),4)
 def test_live_flags_rejected_before_io(self):
  with self.assertRaises(Stop):IntegratedCandidate('unused',MEDIA,clock=lambda:100,artifact_expires_at=1000,flags={k:False for k in FLAGS})
 def test_render_output_hash_tamper_stops_no_upload(self):
  wrong=pathlib.Path(self.tmp.name)/'wrong.mp4';wrong.write_bytes(b'x'*20000);self.p.media=wrong
  self.assertEqual(self.p.tick('bad-media')['state'],'STOP');self.assertEqual(self.p.upload.calls,[])
 def test_crash_after_saved_upload_before_callback_blocks_restart(self):
  self.p.l.add('saved','a'*64,self.now);self.p.j.start('saved',self.now);claim=self.p.l.claim('saved','owner',self.now);self.p.l.consume(claim,'saved-op',self.now);self.p.l.finish(claim,'Done','offline0001')
  self.p.close();self.p=IntegratedCandidate(self.db,MEDIA,clock=lambda:self.now,artifact_expires_at=self.now+10000)
  self.assertEqual(self.p.tick('new')['state'],'STOP');self.assertEqual(self.p.l.get('saved')['state'],'Done');self.assertGreater(self.p.report()['undelivered_notifications'],0)
