import base64,copy,hashlib,json,os,pathlib,tempfile,threading,unittest
from unittest.mock import Mock
from plm.automation.ledger import Stop
from plm.automation.shared_lifecycle import SQLiteCAS,SharedLifecycle,GitContentsCAS
from plm.automation.render_contract import VOICE,contract,render_gate,inventory_gate
from plm.automation.evidence_adapters import GitHubProvenance,GitHubCompletionAuthority,ProcessedReadback,FreshChannel,MemoryOAuthRefresh,HTTPSReader
from plm.automation.live_factory import CandidateFactory,production_entry,DispatchOnce,CallbackOnce
from plm.automation.production_bridge import READ,UPLOAD,CHANNEL
from plm.automation.content_adapters import MetricsAdapter
from plm.automation.loop import FLAGS
from plm.automation.quota_contract import budget_gate,FIELDS as BUDGET_FIELDS
ROOT=pathlib.Path(__file__).resolve().parents[1]
ASSET=pathlib.Path(os.environ.get('PLM_OFFLINE_MEDIA',str(ROOT.parent/'deliverables/plm-offline-proof/short.mp4')))

def valid_video(video='offline0001'):
 return {'kind':'youtube#videoListResponse','items':[{'id':video,'snippet':{'channelId':CHANNEL},'status':{'privacyStatus':'private','uploadStatus':'processed'},'processingDetails':{'processingStatus':'succeeded'}}]}
def proof_fixture(job='job',run='123',phase='completed'):
 marker={'identity':'upload-'+job,'job_id':job,'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':'b'*40,'media_sha256':'c'*64,'upload_approved':True};raw=json.dumps(marker).encode();workflow=b'parked workflow';path='audit-evidence/consumed/'+marker['identity']+'.json'
 e={'repository':'ikkinotako2-sketch/project-love-machine','run_id':run,'attempt':1,'commit':'a'*40,'prepared_commit':'b'*40,'branch':'approved-branch','workflow_path':'.github/workflows/approved.yml','job_name':'upload-once','job_id':job,'identity':marker['identity'],'media_sha256':'c'*64,'artifact_id':1,'artifact_archive_sha256':'d'*64,'workflow_sha256':hashlib.sha256(workflow).hexdigest(),'marker_path':path,'marker_sha256':hashlib.sha256(raw).hexdigest()}
 responses=[{'id':int(run),'repository':{'full_name':e['repository']},'run_attempt':1,'head_sha':e['commit'],'head_branch':e['branch'],'path':e['workflow_path'],'event':'push','status':'completed' if phase=='completed' else 'in_progress','conclusion':'success' if phase=='completed' else None},
 {'total_count':1,'jobs':[{'name':e['job_name'],'run_id':int(run),'status':'completed' if phase=='completed' else 'in_progress','conclusion':'success' if phase=='completed' else None}]},
 {'total_count':1,'artifacts':[{'id':1,'expired':False,'digest':'sha256:'+e['artifact_archive_sha256'],'workflow_run':{'id':int(run),'head_sha':e['commit']}}]},
 {'encoding':'base64','content':base64.b64encode(raw).decode()}, {'encoding':'base64','content':base64.b64encode(workflow).decode()},
 {'parents':[{'sha':e['prepared_commit']}],'files':[{'filename':path,'status':'added'}]}]
 return e,responses

class SharedTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.now=1791763200;self.b=SQLiteCAS(pathlib.Path(self.tmp.name)/'state.db',initialize=True);self.proven=set();self.s=SharedLifecycle(self.b,lambda:self.now,completion_authority=lambda r:r['job_id'] in self.proven)
 def tearDown(self):self.b.close();self.tmp.cleanup()
 def claim(self,job='job',identity=None):return self.s.claim(job,'a'*64,identity or 'upload-'+job,'owner',self.now,day='2026-10-12')
 def done(self,job):
  c=self.claim(job);self.s.consume(c,c['identity'],self.now);self.s.finish(c,'Done','offline0001');self.proven.add(job);self.s.complete(c,{'job_id':job,'video_id':'offline0001','processed':True,'callback':'ACK','run_id':'123'});return c
 def test_distinct_success_jobs_allowed_tombstones_permanent(self):
  self.done('job-a');self.done('job-b');self.assertEqual(len(self.s.doc['jobs']),2)
  for job in ['job-a','job-b']:
   with self.assertRaises(Stop):self.claim(job)
  self.assertTrue(all(x['consumed'] for x in self.s.doc['jobs'].values()))
 def test_two_runners_one_atomic_winner(self):
  barrier=threading.Barrier(2);results=[]
  def run(i):
   b=SQLiteCAS(pathlib.Path(self.tmp.name)/'state.db');s=SharedLifecycle(b,lambda:self.now,completion_authority=lambda r:True);barrier.wait()
   try:s.claim('job-'+str(i),'a'*64,'op-'+str(i),'owner',self.now,day='2026-10-12');results.append(True)
   except Stop:results.append(False)
   finally:b.close()
  ts=[threading.Thread(target=run,args=(i,)) for i in range(2)]
  for t in ts:t.start()
  for t in ts:t.join()
  self.assertEqual(sorted(results),[False,True])
 def test_lease_expiry_no_reclaim(self):
  c=self.claim();self.now+=301
  with self.assertRaises(Stop):self.s.consume(c,c['identity'],self.now)
  with self.assertRaises(Stop):self.claim('different')
 def test_unknown_stops_all_and_unique_notice(self):
  c=self.claim();self.s.consume(c,c['identity'],self.now);self.s.finish(c,'UNKNOWN',reason='UPLOAD_UNKNOWN')
  with self.assertRaises(Stop):self.claim('different')
  self.s.halt(c,'READBACK_UNKNOWN');self.assertEqual(len(self.s.doc['notices']),1)
 def test_cas_lost_ack_no_second_write_or_new_runner(self):
  original=self.b.cas;calls=[]
  def lose(sha,body):calls.append(1);original(sha,body);raise TimeoutError()
  self.b.cas=lose
  with self.assertRaises(Stop):self.claim()
  with self.assertRaises(Stop):self.claim('different')
  fresh=SharedLifecycle(self.b,lambda:self.now,completion_authority=lambda r:True)
  with self.assertRaises(Stop):fresh.claim('other','b'*64,'new','owner',self.now,day='2026-10-12')
  self.assertEqual(len(calls),1)
 def test_done_ack_loss_requires_independent_success_not_record(self):
  c=self.claim();self.s.consume(c,c['identity'],self.now);self.s.finish(c,'Done','offline0001');self.proven.add('job')
  original=self.b.cas
  def lose(sha,body):original(sha,body);raise TimeoutError()
  self.b.cas=lose
  with self.assertRaises(Stop):self.s.complete(c,{'job_id':'job','video_id':'offline0001','processed':True,'callback':'ACK','run_id':'123'})
  fresh=SharedLifecycle(self.b,lambda:self.now,completion_authority=lambda r:False)
  with self.assertRaises(Stop):fresh.claim('next','b'*64,'op-next','owner',self.now,day='2026-10-12')
 def test_release_independent_approval_never_erases_tombstone(self):
  c=self.claim();self.s.halt(c,'AUTH_STOP')
  with self.assertRaises(Stop):self.s.release_stop({'identity':'release','operation_kind':'RELEASE_GLOBAL_STOP','expected_state_sha':self.s.sha})
  self.s.release_authority=lambda a:True;self.s.release_stop({'identity':'release','operation_kind':'RELEASE_GLOBAL_STOP','expected_state_sha':self.s.sha})
  with self.assertRaises(Stop):self.claim()
  self.assertTrue(self.s.doc['jobs']['job']['consumed']);self.claim('another')
 def test_corrupt_state_no_send(self):
  sha,d=self.b.read();d['last_completed']='missing';self.b.cas(sha,d)
  with self.assertRaises(Stop):SharedLifecycle(self.b,lambda:self.now,completion_authority=lambda r:True)
 def test_previous_completion_wrong_job_not_accepted(self):
  self.done('job-a');self.proven.clear()
  with self.assertRaises(Stop):self.claim('job-b')
 def test_duplicate_no_double_budget(self):
  self.done('job')
  with self.assertRaises(Stop):self.claim('job')
  self.assertEqual(self.s.doc['budgets']['2026-10-12'],1)
 def test_git_cas_branch_fixed_no_retry(self):
  t=Mock(return_value=(403,{}));b=GitContentsCAS(t)
  with self.assertRaises(Stop):b.read()
  with self.assertRaises(Stop):b.read()
  self.assertEqual(t.call_count,1);self.assertIn('ref=plm-execution-state-v2',t.call_args.args[1])

class EvidenceTests(unittest.TestCase):
 def test_provenance_six_exact_reads_pass(self):
  e,p=proof_fixture();get=Mock(side_effect=[(200,x) for x in p]);out=GitHubProvenance(get).verify(e);self.assertTrue(out['verified']);self.assertEqual(get.call_count,6)
 def test_current_run_requires_before_upload_phase(self):
  e,p=proof_fixture(phase='before_upload');self.assertEqual(GitHubProvenance(Mock(side_effect=[(200,x) for x in p])).verify(e,phase='before_upload')['phase'],'before_upload')
 def test_wrong_repository_artifact_origin_and_expiry_stop(self):
  for field in ['repository','artifact_origin','expired']:
   e,p=proof_fixture()
   if field=='repository':p[0]['repository']['full_name']='unrelated/repo'
   elif field=='artifact_origin':p[2]['artifacts'][0]['workflow_run']['head_sha']='f'*40
   else:p[2]['artifacts'][0]['expired']=True
   with self.subTest(field=field),self.assertRaises(Stop):GitHubProvenance(Mock(side_effect=[(200,x) for x in p])).verify(e)
 def test_provenance_each_binding_mutation_stops(self):
  for field,value in [('head_sha','f'*40),('head_branch','main'),('run_attempt',2),('path','.github/workflows/wrong.yml'),('event','workflow_dispatch'),('conclusion','failure')]:
   e,p=proof_fixture();p[0][field]=value;get=Mock(side_effect=[(200,x) for x in p])
   with self.subTest(field=field),self.assertRaises(Stop):GitHubProvenance(get).verify(e)
 def test_marker_workflow_and_artifact_not_hmac(self):
  for index in (2,3,4):
   e,p=proof_fixture()
   if index==2:p[2]['artifacts'][0]['digest']='sha256:'+'e'*64
   else:p[index]['content']=base64.b64encode(b'changed').decode()
   with self.assertRaises(Stop):GitHubProvenance(Mock(side_effect=[(200,x) for x in p])).verify(e)
 def test_processed_readback_exact(self):
  get=Mock(return_value=(200,valid_video()));r=ProcessedReadback(get,approved=True,read_scope_proven=True);self.assertTrue(r.verify('offline0001','job')['processed'])
  with self.assertRaises(Stop):r.verify('offline0001','job')
  self.assertEqual(get.call_count,1)
 def test_readback_bad_processing_private_channel_no_retry(self):
  for section,field,value in [('snippet','channelId','wrong'),('status','privacyStatus','public'),('status','uploadStatus','uploaded'),('processingDetails','processingStatus','processing')]:
   d=valid_video();d['items'][0][section][field]=value;get=Mock(return_value=(200,d));r=ProcessedReadback(get,approved=True,read_scope_proven=True)
   with self.assertRaises(Stop):r.verify('offline0001','job')
   with self.assertRaises(Stop):r.verify('offline0001','job')
   self.assertEqual(get.call_count,1)
 def test_readback_timeout_unknown(self):
  get=Mock(side_effect=TimeoutError());r=ProcessedReadback(get,approved=True,read_scope_proven=True)
  with self.assertRaises(Stop):r.verify('offline0001','job')
  self.assertEqual(get.call_count,1)
 def test_readback_wrong_video_id_unknown(self):
  r=ProcessedReadback(Mock(return_value=(200,valid_video('different01'))),approved=True,read_scope_proven=True)
  with self.assertRaises(Stop):r.verify('offline0001','job')
 def test_missing_scope_no_readback_call(self):
  get=Mock()
  with self.assertRaises(Stop):ProcessedReadback(get,approved=True).verify('offline0001','job')
  get.assert_not_called()
 def test_provider_reuse_single_refresh_and_secret_redaction(self):
  sender=Mock(return_value=(200,{'access_token':'FIXTURE_BEARER','expires_in':3600,'token_type':'Bearer','scope':READ+' '+UPLOAD}));r=MemoryOAuthRefresh({'client_id':'fixture-client','client_secret':'fixture-secret','refresh_token':'fixture-refresh'},sender,lambda:100,approved=True)
  out=r();self.assertTrue(out['scope_proven']);self.assertNotIn('fixture-secret',repr(r))
  with self.assertRaises(Stop):r()
  self.assertEqual(sender.call_count,1)
 def test_absent_response_scope_unknown_before_channel(self):
  sender=Mock(return_value=(200,{'access_token':'FIXTURE','expires_in':3600,'token_type':'Bearer'}));r=MemoryOAuthRefresh({'client_id':'f','client_secret':'f','refresh_token':'f'},sender,lambda:100,approved=True)
  with self.assertRaises(Stop):r()
 def test_fresh_channel_uses_same_bearer(self):
  get=Mock(return_value=(200,{'kind':'youtube#channelListResponse','items':[{'id':CHANNEL}]}));factory=Mock(return_value=get)
  r=FreshChannel(lambda:{'access_token':'FIXTURE','expires_at':1000,'scopes':[READ,UPLOAD],'scope_proven':True},factory,lambda:100);session=r.create();self.assertEqual(session.token(),'FIXTURE');factory.assert_called_once_with('FIXTURE');session.clear()
 def test_default_read_transport_not_approved(self):
  with self.assertRaises(Stop):HTTPSReader('www.googleapis.com','FIXTURE')
 def test_state_transport_rejects_main_and_defaults_before_connection(self):
  from plm.automation.state_transport import StateHTTPTransport
  with self.assertRaises(Stop):StateHTTPTransport('FIXTURE')
  connector=Mock();t=StateHTTPTransport('FIXTURE',approved=True,connector=connector)
  with self.assertRaises(Stop):t('PUT','/repos/ikkinotako2-sketch/project-love-machine/contents/automation-state/lifecycle.json',{'branch':'main','sha':'a'*40,'message':'x','content':'x'})
  connector.assert_not_called();self.assertNotIn('FIXTURE',repr(t))
 def test_stored_done_cannot_override_failed_coordinator_ack_loss(self):
  e,p=proof_fixture();ce,cp=proof_fixture(run='999');ce['approval_field']='finalize_approved';cp[0]['conclusion']='failure'
  authority=GitHubCompletionAuthority(Mock(side_effect=[(200,x) for x in p+cp]),lambda row:ce)
  row={'job_id':'job','identity':'upload-job','run_id':'123','state':'Done','provenance_expected':e,'continuation':{'coordinator_run_id':'999'}}
  self.assertFalse(authority(row))

class RenderTests(unittest.TestCase):
 def test_voice_id_style_engine_exact(self):
  self.assertTrue(inventory_gate([{'name':'ずんだもん','styles':[{'id':3,'name':'ノーマル'}]}]))
  for inventory in [[{'name':'other','styles':[{'id':3,'name':'ノーマル'}]}],[{'name':'ずんだもん','styles':[{'id':1,'name':'ノーマル'}]}]]:
   with self.assertRaises(Stop):inventory_gate(inventory)
 def test_new_render_not_mislabeled_reused(self):
  raw=json.dumps({'narration':'test','scenes':[{'caption':'test'}]});c=contract(raw,mode='NEW_RENDER',voice=VOICE);self.assertIsNone(c['media_sha256'])
  with self.assertRaises(Stop):contract(raw,mode='REUSE_PINNED',voice=VOICE,media_sha='a'*64,audio_sha='b'*64,caption_sha='c'*64)
 def test_unknown_remaining_or_stale_budget_stops(self):
  cost={k:1 for k in BUDGET_FIELDS};obs={'plan':'FREE','billing_cap_usd':0,'basis':'API_OBSERVATION','observed_at':100,'remaining':{k:10 for k in BUDGET_FIELDS}}
  self.assertTrue(budget_gate(obs,cost,100)['actual_account_verified'])
  for bad in [{**obs,'observed_at':0},{**obs,'remaining':{k:None for k in BUDGET_FIELDS}}]:
   with self.assertRaises(Stop):budget_gate(bad,cost,1000)
 def test_fixture_budget_never_promoted_to_live(self):
  cost={k:1 for k in BUDGET_FIELDS};obs={'plan':'FREE','billing_cap_usd':0,'basis':'OFFLINE_FIXTURE','observed_at':100,'remaining':{k:10 for k in BUDGET_FIELDS}}
  with self.assertRaises(Stop):budget_gate(obs,cost,100)
  self.assertFalse(budget_gate(obs,cost,100,offline_only=True)['actual_account_verified'])
 def test_mismatched_narration_or_voice_stops(self):
  with self.assertRaises(Stop):contract(json.dumps({'narration':'wrong','scenes':[{'caption':'test'}]}),mode='NEW_RENDER',voice=VOICE)
  with self.assertRaises(Stop):contract('{}',mode='NEW_RENDER',voice={**VOICE,'speaker_id':1})

class DispatchTests(unittest.TestCase):
 def test_immutable_dispatch_single_post_after_sentinel(self):
  send=Mock(return_value=204);d=DispatchOnce(send);target={'repository':'ikkinotako2-sketch/project-love-machine','workflow':'youtube-pipeline.yml','ref':'a'*40}
  self.assertTrue(d.dispatch(target,{},approved=True,immutable_ref_proven=True,sentinel=lambda:True))
  with self.assertRaises(Stop):d.dispatch(target,{},approved=True,immutable_ref_proven=True,sentinel=lambda:True)
  self.assertEqual(send.call_count,1)
 def test_missing_gate_no_dispatch(self):
  send=Mock();d=DispatchOnce(send)
  with self.assertRaises(Stop):d.dispatch({}, {},sentinel=lambda:True)
  send.assert_not_called()
 def test_dispatch_unknown_no_resend(self):
  send=Mock(side_effect=TimeoutError());d=DispatchOnce(send);t={'repository':'ikkinotako2-sketch/project-love-machine','workflow':'youtube-pipeline.yml','ref':'a'*40}
  for _ in range(2):
   with self.assertRaises(Stop):d.dispatch(t,{},approved=True,immutable_ref_proven=True,sentinel=lambda:True)
  self.assertEqual(send.call_count,1)
 def test_live_entry_cannot_be_unparked_with_flags(self):
  for flags in [FLAGS,{k:False for k in FLAGS}]:
   with self.assertRaises(Stop):production_entry(flags=flags,approved=True)
 def test_callback_reuses_signed_contract_once(self):
  context={'account_id':'youtube_game_001','intent_id':'intent-job','job_id':'job','owner':'owner','owner_epoch':1,'fencing_token':1,'dispatch_id':'d'*64,'run_id':'123','run_attempt':1,'workflow_sha256':'a'*64,'script_sha256':'b'*64};cp={'run_id':'123','script_sha256':'b'*64,'media_sha256':'c'*64,'quality_gate':'PASS'}
  send=Mock(return_value=200);c=CallbackOnce(send,context,cp,b'K'*32,'callback-v1',origin='callback.example.com',approved=True,clock=lambda:100,dispatch_key=b'D'*32)
  receipt={'proof_basis':'INDEPENDENT_READBACK','processed':True,'channel_id':CHANNEL,'private':True,'job_id':'job','run_id':'123','media_sha256':'c'*64,'video_id':'offline0001'}
  self.assertEqual(c(receipt),'ACK');url,raw,sig=send.call_args.args;self.assertEqual(url,'https://callback.example.com/youtube/result');self.assertEqual(json.loads(raw)['protocol'],'plm-youtube-result-v2');self.assertEqual(len(sig),64)
  with self.assertRaises(Stop):c(receipt)
  self.assertEqual(send.call_count,1)
 def test_same_callback_and_dispatch_key_rejected(self):
  with self.assertRaises(Stop):CallbackOnce(Mock(),{}, {},b'K'*32,'id',origin='callback.example.com',approved=True,clock=lambda:100,dispatch_key=b'K'*32)

class FactoryTests(unittest.TestCase):
 def setUp(self):
  if not ASSET.is_file():self.skipTest('Dedicated CI supplies exact fixed MP4')
  self.tmp=tempfile.TemporaryDirectory();self.now=1791763200;self.b=SQLiteCAS(pathlib.Path(self.tmp.name)/'state.db',initialize=True);self.completed=set();self.state=SharedLifecycle(self.b,lambda:self.now,completion_authority=lambda r:r['job_id'] in self.completed)
  self.media=ASSET.read_bytes();self.audio=ASSET.with_name('audio.wav').read_bytes();self.captions=ASSET.with_name('captions.ass').read_bytes();self.job=json.loads((ROOT/'readiness/youtube-private-job.json').read_text());self.e=json.loads((ROOT/'readiness/reused-render-evidence.json').read_text())
  script={'title':self.job['title'],'hook':self.job['sentences'][0],'narration':''.join(self.job['sentences']),'scenes':[{'start':t['start_seconds'],'end':t['end_seconds'],'caption':t['text'],'visual_keyword':'study','motion':'none','sfx':'none','emphasis_words':[]} for t in self.e['timing']],'bgm':{'mood':'calm','volume':0}}
  self.raw=json.dumps(script,ensure_ascii=False,separators=(',',':'));self.c=contract(self.raw,mode='REUSE_PINNED',voice=VOICE,media_sha=self.e['media_sha256'],audio_sha=self.e['audio_sha256'],caption_sha=self.e['caption_sha256'])
  self.render={'voice':VOICE,'script_sha256':self.c['script_sha256'],'quality_pass':True,**{k:self.e[k] for k in ['media_sha256','audio_sha256','caption_sha256']}}
  self.inventory=[{'name':'ずんだもん','styles':[{'id':3,'name':'ノーマル'}]}];self.sent=[];self.callback=Mock(return_value='ACK');self.readback_get=Mock(return_value=(200,valid_video()))
  outer=self
  class Upload:
   def init(self,token,meta,size):
    assert outer.state.get(outer.current)['sent'];outer.sent.append(outer.current);return 'fixture'
   def media(self,token,path,media):return 200,json.dumps({'id':'offline0001','snippet':{'channelId':CHANNEL},'status':{'privacyStatus':'private'}}).encode()
  def provenance(e,phase):
   if phase=='completed':self.completed.add(e['job_id'])
   return {'verified':True,'phase':phase,'job_id':e['job_id'],'identity':e['identity'],'media_sha256':self.e['media_sha256'],'run_id':str(e['run_id'])}
  self.factory=CandidateFactory(state=self.state,channel=None,provenance=provenance,readback_for_token=lambda token:ProcessedReadback(self.readback_get,approved=True,read_scope_proven=True),upload_transport=Upload(),callback=self.callback,metrics=MetricsAdapter(lambda vid:{'views':0,'likes':0,'comments':0},capability_verified=True),clock=lambda:self.now)
 def tearDown(self):self.b.close();self.tmp.cleanup()
 def run_job(self,job='job',**overrides):
  self.current=job;self.factory.channel=FreshChannel(lambda:{'access_token':'OFFLINE_FIXTURE','expires_at':self.now+3600,'scopes':[READ,UPLOAD],'scope_proven':True},lambda token:lambda path:(200,{'kind':'youtube#channelListResponse','items':[{'id':CHANNEL}]}),lambda:self.now)
  j={**self.job,'job_id':job,'upload_identity':'upload-'+job,'rights_verified':True};op={'flags':FLAGS,'approved':True,'marker_consumed':True,'identity':j['upload_identity'],'source_pins_exact':True,'artifact_fresh':True}
  args=dict(job=j,scope={'scopes':[READ,UPLOAD],'proven':True},operation=op,provenance_expected={'job_id':job,'identity':j['upload_identity'],'run_id':123+len(self.sent)},render_contract=self.c,script_raw=self.raw,voice_inventory=self.inventory,media=self.media,audio=self.audio,captions=self.captions,render_evidence=self.render,media_path=ASSET,day=__import__('datetime').datetime.fromtimestamp(self.now,__import__('datetime').timezone.utc).strftime('%Y-%m-%d'),budget_known=True,budget_cost={k:1 for k in BUDGET_FIELDS},budget_observation={'plan':'FREE','billing_cap_usd':0,'basis':'OFFLINE_FIXTURE','observed_at':self.now,'remaining':{k:100 for k in BUDGET_FIELDS}});args.update(overrides);return self.factory.run(**args)
 def test_48h_distinct_jobs_tombstones_and_completed_run_required(self):
  for i,hour in enumerate([0,12,24,36]):
   self.now=1791763200+hour*3600;job='job-'+str(i);out=self.run_job(job);self.assertEqual(out['state'],'AWAITING_COMPLETED_RUN_PROOF');self.assertIsNone(out['next_job']);self.assertEqual(self.state.get(job)['state'],'ACKNOWLEDGED')
   done=self.factory.finalize(job,{'script_sha256':self.c['script_sha256']},coordinator_run_id='999',finalizer_approval={'approved':True,'marker_consumed':True,'operation_kind':'FINALIZE_SHARED_JOB','identity':'finalizer-'+job,'job_id':job,'run_id':'999'});self.assertEqual(done['state'],'Done');self.assertTrue(self.state.get(job)['consumed'])
  self.assertEqual(len(self.sent),4);self.assertEqual(len(self.state.doc['jobs']),4);self.assertTrue(all(v<=2 for v in self.state.doc['budgets'].values()))
 def test_scope_missing_zero_side_effects(self):
  with self.assertRaises(Stop):self.run_job(scope={'scopes':[UPLOAD],'proven':True})
  self.assertEqual(self.sent,[]);self.assertEqual(self.state.doc['jobs'],{})
 def test_absent_marker_zero_side_effects(self):
  with self.assertRaises(Stop):self.run_job(operation={'flags':FLAGS,'approved':True,'marker_consumed':False})
  self.assertEqual(self.sent,[])
 def test_callback_failure_global_stop_no_next(self):
  self.callback.side_effect=TimeoutError()
  with self.assertRaises(Stop):self.run_job()
  self.assertTrue(self.state.doc['stopped']);self.assertEqual(self.state.get('job')['state'],'UNKNOWN');self.assertEqual(len(self.sent),1)
  with self.assertRaises(Stop):self.run_job('other')
  self.assertEqual(len(self.sent),1)
 def test_readback_mismatch_global_unknown(self):
  d=valid_video();d['items'][0]['snippet']['channelId']='wrong';self.readback_get.return_value=(200,d)
  with self.assertRaises(Stop):self.run_job()
  self.assertTrue(self.state.doc['stopped']);self.callback.assert_not_called()
 def test_duplicate_after_done_no_second_upload(self):
  self.run_job();self.factory.finalize('job',{'script_sha256':self.c['script_sha256']},coordinator_run_id='999',finalizer_approval={'approved':True,'marker_consumed':True,'operation_kind':'FINALIZE_SHARED_JOB','identity':'finalizer-job','job_id':'job','run_id':'999'})
  with self.assertRaises(Stop):self.run_job()
  self.assertEqual(len(self.sent),1)
 def test_unknown_budget_or_sha_before_claim(self):
  for args in [{'budget_known':False},{'script_raw':self.raw+' '}]:
   with self.assertRaises(Stop):self.run_job(**args)
  self.assertEqual(self.state.doc['jobs'],{});self.assertEqual(self.sent,[])
 def test_expired_channel_token_no_upload_global_stop(self):
  self.factory.channel=Mock();self.factory.channel.create.side_effect=Stop('AUTH_EXPIRED_STOP')
  # run_job deliberately installs a fresh channel; replace the factory callback
  # after reversible gate invocation to test the actual session boundary.
  original=self.factory.provenance
  def expire(e,phase):
   p=original(e,phase);self.factory.channel=Mock();self.factory.channel.create.side_effect=Stop('AUTH_EXPIRED_STOP');return p
  self.factory.provenance=expire
  with self.assertRaises(Stop):self.run_job()
  self.assertEqual(self.sent,[]);self.assertTrue(self.state.doc['stopped'])
 def test_coordinator_restarts_with_durable_receipt_no_upload_resume(self):
  self.run_job();self.assertIn('completion_receipt',self.state.get('job'));sent=len(self.sent)
  new_state=SharedLifecycle(self.b,lambda:self.now,completion_authority=lambda r:r['job_id'] in self.completed)
  original=self.factory;self.factory=CandidateFactory(state=new_state,channel=Mock(),provenance=original.provenance,readback_for_token=Mock(),upload_transport=Mock(),callback=Mock(),metrics=original.metrics,clock=lambda:self.now)
  result=self.factory.finalize('job',{'script_sha256':self.c['script_sha256']},coordinator_run_id='999',finalizer_approval={'approved':True,'marker_consumed':True,'operation_kind':'FINALIZE_SHARED_JOB','identity':'finalizer-job','job_id':'job','run_id':'999'});self.assertEqual(result['state'],'Done');self.assertEqual(len(self.sent),sent);self.factory.upload.init.assert_not_called()
