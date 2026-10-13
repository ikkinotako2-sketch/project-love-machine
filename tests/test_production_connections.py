import copy,hashlib,json,sqlite3,tempfile,unittest,subprocess,base64,zipfile,io
from pathlib import Path
from unittest.mock import Mock,patch
from plm.automation.executors import authority as a
from plm.automation.executors.release import SecretScope,frozen_policy,release_gate,CheckedAudit,issue_live,POLICY_SHA
from plm.automation.executors.runner import ProductionRunner,read_event
from plm.automation.executors.run_reader import OperationRunReader
from plm.automation.executors import cloudflare as c
from plm.automation.executors.callback_http import CallbackHTTP
from plm.automation.executors.artifact_input import ArtifactInput
from plm.automation.ledger import Stop
ROOT=Path(__file__).resolve().parents[1]
PLAN=json.loads((ROOT/'readiness/executor-final-plan.json').read_bytes())
CFPLAN=json.loads((ROOT/'readiness/cloudflare-transfer-plan.json').read_bytes())

class Fn:
 offline_mock=True
 def __init__(self,fn):self.fn=fn;self.calls=[]
 def __call__(self,*args):self.calls.append(args[:2]);return self.fn(*args)

class WiringTests(unittest.TestCase):
 def test_frozen_all_eight_disabled_and_scope_false(self):
  p=frozen_policy();self.assertEqual(len(p['releases']),8)
  self.assertTrue(all(r['enabled'] is False for r in p['releases'].values()))
  self.assertFalse(p['frozen_knowledge']['youtube_readonly'])
 def test_all_real_runners_zero_secret_and_zero_io(self):
  load=Mock(side_effect=AssertionError('SECRET_READ_FORBIDDEN'))
  for op in frozen_policy()['releases']:
   out=ProductionRunner().execute(op,event={},pins={},secret_loader=load)
   self.assertEqual(out['status'],'PARKED');self.assertEqual(out['credentials_read'],0);self.assertEqual(out['real_requests'],0)
  load.assert_not_called()
 def test_policy_tampering_not_input_approval(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'readiness';p.mkdir();v=frozen_policy();v['releases']['channel']['enabled']=True
   (p/'execution-release-policy.json').write_text(json.dumps(v))
   with self.assertRaises(Stop):frozen_policy(Path(tmp))
 def test_enabled_but_unknown_environment_or_budget_stops(self):
  p=frozen_policy();p['releases']['state_init'].update(enabled=True,owner_approved=True,environment_reviewed=True,owner_exclusion_attested=True,reviewed_target_exact=True)
  with self.assertRaises(Stop):release_gate('state_init',p)
  p['releases']['state_init']['budget_actual_verified']=True
  with self.assertRaises(Stop):release_gate('state_init',p)
  p['releases']['state_init']['required_flags']['DRY_RUN']=False;p['releases']['state_init']['required_flags']['EMERGENCY_STOP']=False
  self.assertTrue(release_gate('state_init',p)['enabled'])
 def test_scope_false_cannot_be_promoted(self):
  p=frozen_policy();p['releases']['private_upload'].update(enabled=True,owner_approved=True,environment_reviewed=True,owner_exclusion_attested=True,reviewed_target_exact=True,budget_actual_verified=True)
  with self.assertRaises(Stop):release_gate('private_upload',p)
 def test_callback_null_stops_before_secret(self):
  p=frozen_policy();r=p['releases']['finalize'];r.update(enabled=True,owner_approved=True,environment_reviewed=True,owner_exclusion_attested=True,reviewed_target_exact=True,budget_actual_verified=True,read_scope_verified=True,channel_match_verified=True)
  with self.assertRaises(Stop):release_gate('finalize',p)
 def test_secret_allowlist_missing_memory_clear(self):
  load=Mock(return_value='FIXTURE_PRIVATE_VALUE');s=SecretScope(load,['only'])
  with self.assertRaises(Stop):s.get('unrelated')
  load.assert_not_called();self.assertEqual(s.get('only'),'FIXTURE_PRIVATE_VALUE');self.assertNotIn('FIXTURE_PRIVATE_VALUE',repr(s))
  s.clear();self.assertEqual(s.values,{})
  with self.assertRaises(Stop):s.get('only')
 def test_secret_missing_stop_no_value_output(self):
  s=SecretScope(lambda name:None,['only'])
  with self.assertRaises(Stop) as cm:s.get('only')
  self.assertEqual(str(cm.exception),'SECRET_MISSING_STOP')
 def test_mock_receipt_no_live_constructor(self):
  a1=a.OfflineAuthority(PLAN);p=a1.issue('channel',approved=True,marker_consumed=True);p.mode='LIVE_VERIFIED'
  with self.assertRaises(Stop):a.live_authority(p)
  with self.assertRaises(Stop):CallbackHTTP(p,'callback.example.com')
 def test_actual_metadata_attempt_two_visible_to_gate(self):
  e=read_event({'GITHUB_RUN_ATTEMPT':'2','GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123'})
  self.assertEqual(e['attempt'],2)
 def test_workflow_secret_step_is_after_gate_and_disabled(self):
  for plan in (PLAN,CFPLAN):
   for op in plan['operations'].values():
    w=(ROOT/op['workflow_path']).read_text()
    self.assertIn('if: ${{ false }}',w);self.assertIn("if: ${{ steps.local.outputs.ready == 'true' }}",w)
    self.assertLess(w.index('--prepare'),w.index('secrets.'));self.assertIn('persist-credentials: false',w)
    self.assertIn(op['marker_path'],w);self.assertNotIn('schedule:',w)
 def test_no_real_markers_or_other_repository_changes(self):
  for plan in (PLAN,CFPLAN):
   for op in plan['operations'].values():self.assertFalse((ROOT/op['marker_path']).exists())
  self.assertEqual(CFPLAN['operations']['migration']['budget']['D1_DDL_POST'],1)

class RunReaderTests(unittest.TestCase):
 def test_current_independent_run_two_reads_not_hmac(self):
  checked=Mock();checked.event={'run_id':'123'};checked.head='a'*40;checked.operation='channel';checked.plan=PLAN
  run={'id':123,'repository':{'full_name':PLAN['repository']},'run_attempt':1,'head_sha':'a'*40,'head_branch':PLAN['branch'],'path':PLAN['operations']['channel']['workflow_path'],'event':'push','status':'in_progress'}
  jobs={'total_count':1,'jobs':[{'run_id':123,'name':'execute','status':'in_progress'}]}
  get=Fn(Mock(side_effect=[(200,run),(200,jobs)]));reader=OperationRunReader(get);proof=reader.current(checked)
  self.assertFalse(proof.live);self.assertEqual(reader.calls,2)
 def test_attempt_two_or_wrong_sha_rejected(self):
  checked=Mock();checked.event={'run_id':'123'};checked.head='a'*40;checked.operation='channel';checked.plan=PLAN
  for attempt in (2,True):
   get=Fn(lambda path:(200,{'run_attempt':attempt}))
   with self.assertRaises(Stop):OperationRunReader(get).current(checked)
 def test_http_unknown_not_retried(self):
  get=Fn(Mock(side_effect=TimeoutError('PRIVATE_ERROR_BODY')));r=OperationRunReader(get)
  with self.assertRaises(Stop) as cm:r.read('/repos/'+PLAN['repository']+'/actions/runs/123')
  self.assertNotIn('PRIVATE_ERROR_BODY',str(cm.exception));self.assertEqual(len(get.calls),1)
 def test_unrelated_repo_no_request(self):
  get=Fn(Mock());r=OperationRunReader(get)
  with self.assertRaises(Stop):r.read('/repos/unrelated/project/actions/runs/123')
  self.assertEqual(get.calls,[])
 def test_fixture_json_not_prerequisite_success(self):
  r=OperationRunReader(Fn(Mock()));raw=b'{"basis":"OFFLINE_CONTRACT"}'
  with self.assertRaises(Stop):r.prerequisite({'receipt_sha256':hashlib.sha256(raw).hexdigest()},raw)
  self.assertEqual(r.calls,0)

class CloudflareTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;self.addCleanup(self.db.close)
  for n in ('0008_provider_neutral_roundtrip_backend.sql','0009_youtube_queue_result_proposal.sql','0010_youtube_pipeline_checkpoint_candidate.sql'):
   self.db.executescript((ROOT/'readiness/sandbox-contract-fixture/serverless/migrations'/n).read_text())
  self.authority=a.OfflineAuthority(CFPLAN)
  self.transport=Fn(self.handle)
 def handle(self,method,path,body,content_type):
  if method=='GET':return 200,{'success':True,'result':{'uuid':c.DB,'name':c.DB_NAME}},{}
  if body['sql'] in (c.READ_QUERY,c.READ_QUERY+c.LEDGER_QUERY):
   rows=[dict(x) for x in self.db.execute(c.SCHEMA_QUERY)]
   results=[{'success':True,'results':rows},{'success':True,'results':[dict(x) for x in self.db.execute(c.COUNTS_QUERY)]}]
   if body['sql'].endswith(c.LEDGER_QUERY):results.append({'success':True,'results':[dict(x) for x in self.db.execute(c.LEDGER_QUERY)]})
   return 200,{'success':True,'result':results},{}
  # Local transaction model only; never promotes REST atomicity to verified.
  try:self.db.executescript('BEGIN;'+body['sql']+'COMMIT;')
  except Exception:
   self.db.rollback();raise
  return 200,{'success':True,'result':[{'success':True,'results':[]}]},{}
 def permit(self,op,prior=()):return self.authority.issue(op,prerequisites=prior,approved=True,marker_consumed=True)
 def test_migration_and_separate_readonly_postcheck(self):
  ack=c.TransferExecutor(self.transport).run(self.permit('migration'));self.assertEqual(ack.status,'ACKNOWLEDGED')
  verified=c.TransferExecutor(self.transport).run(self.permit('migration_postcheck',(ack,)));self.assertEqual(verified.status,'VERIFIED')
  self.assertEqual([m for m,_ in self.transport.calls],['GET','POST','POST','GET','POST'])
  self.assertEqual(self.db.execute('SELECT count(*) FROM plm_auto_v1_migration_choice').fetchone()[0],1)
 def test_old_candidate_collision_stops_before_write(self):
  self.db.execute('CREATE TABLE plm_auto_v1_budget(x)')
  with self.assertRaises(Stop):c.TransferExecutor(self.transport).run(self.permit('migration'))
  self.assertEqual(len(self.transport.calls),2)
 def test_schema_drift_stops(self):
  self.db.execute('CREATE TABLE plm_rt_v2_unapproved(x)')
  with self.assertRaises(Stop):c.TransferExecutor(self.transport).run(self.permit('migration'))
  self.assertEqual(len(self.transport.calls),2)
 def test_apply_ack_unknown_no_postcheck_or_retry(self):
  t=Fn(lambda *args:self.handle(*args) if len(t.calls)<3 else (_ for _ in ()).throw(TimeoutError()))
  e=c.TransferExecutor(t);p=self.permit('migration')
  for _ in range(2):
   with self.assertRaises(Stop):e.run(p)
  self.assertEqual(len(t.calls),3);self.assertTrue(e.uncertain)
 def test_wrong_database_identity_no_query(self):
  t=Fn(lambda *args:(200,{'success':True,'result':{'uuid':'other','name':c.DB_NAME}},{}))
  with self.assertRaises(Stop):c.TransferExecutor(t).run(self.permit('migration'))
  self.assertEqual(len(t.calls),1)
 def test_module_closure_exact_and_parked_multimodule_roundtrip(self):
  d=c.contract();body,typ=c.multipart(d);hashes,entry=c.comparable(body,{'content_type':typ})
  self.assertEqual(hashes,d['modules']);self.assertEqual(entry,c.ENTRY);self.assertEqual(len(hashes),11)
  self.assertFalse(d['old_candidate_apply_allowed'])
 def test_source_representation_unknown_not_hash_guessed(self):
  with self.assertRaises(Stop):c.comparable(b'unknown',{'content_type':'application/octet-stream'})
 def worker_transport(self,post=False,active=False,wrong_source=False):
  d=c.contract()
  def send(method,path,body,kind):
   if method=='PUT':return 200,{'success':True,'result':{'id':c.WORKER}},{}
   if path==c.VERIFY:r={'status':'active'}
   elif path.endswith('/content/v2'):
    if post:
     raw,ct=c.multipart(d);return 200,raw,{'content_type':ct}
    raw=(ROOT/d['rollback_source_path']).read_bytes();return 200,b'wrong' if wrong_source else raw,{'content_type':'application/javascript'}
   elif path.endswith('/subdomain'):r={'enabled':active,'previews_enabled':False}
   elif path.endswith('/settings'):r={'bindings':[{'type':'d1','name':'DB','id':c.DB}]+[{'type':'plain_text','name':k,'text':v} for k,v in c.FLAGS.items()]}
   else:r=[]
   return 200,{'success':True,'result':r},{}
  return Fn(send)
 def worker_permit(self):
  ack=c.TransferExecutor(self.transport).run(self.permit('migration'))
  check=c.TransferExecutor(self.transport).run(self.permit('migration_postcheck',(ack,)))
  return self.permit('worker_deploy',(check,))
 def test_worker_one_put_after_eight_reads_postcheck_separate(self):
  t=self.worker_transport();ack=c.TransferExecutor(t).run(self.worker_permit());self.assertEqual(ack.status,'ACKNOWLEDGED')
  self.assertEqual([m for m,_ in t.calls],['GET']*8+['PUT'])
  p=self.permit('worker_postcheck',(ack,));pt=self.worker_transport(post=True);done=c.TransferExecutor(pt).run(p)
  self.assertEqual(done.status,'VERIFIED');self.assertEqual([m for m,_ in pt.calls],['GET']*7)
 def test_source_drift_no_put(self):
  t=self.worker_transport(wrong_source=True)
  with self.assertRaises(Stop):c.TransferExecutor(t).run(self.worker_permit())
  self.assertEqual(len(t.calls),2);self.assertFalse(any(m=='PUT' for m,_ in t.calls))
 def test_active_exposure_stops_before_write(self):
  t=self.worker_transport(active=True)
  with self.assertRaises(Stop):c.TransferExecutor(t).run(self.worker_permit())
  self.assertEqual(len(t.calls),3)
 def test_native_cf_forbids_other_project_and_routes(self):
  x=object.__new__(c.CFHTTP);x.permit=Mock(operation='worker_deploy');x.used=0;x.unknown=False;x.connector=Mock();x.read='FIXTURE';x.write='FIXTURE'
  for method,path in [('PUT','/accounts/other/workers/scripts/discord'),('POST',c.WP+'/schedules'),('DELETE',c.WP)]:
   with self.assertRaises(Stop):x(method,path)
  x.connector.assert_not_called()
 def test_rest_atomicity_not_promoted_from_sqlite_success(self):
  self.assertEqual(c.contract()['REST_DDL_batch_atomicity'],'UNVERIFIED_RELEASE_BLOCKER')
  p=frozen_policy();r=p['releases']['migration'];r.update(enabled=True,owner_approved=True,environment_reviewed=True,owner_exclusion_attested=True,reviewed_target_exact=True,budget_actual_verified=True)
  with self.assertRaises(Stop):release_gate('migration',p)

if __name__=='__main__':unittest.main()

class NativeBoundaryTests(unittest.TestCase):
 def live_fixture(self,op):
  plan=CFPLAN if op.startswith(('migration','worker')) else PLAN
  p=a.Permit(op,plan,(),a._SEAL);p.mode='LIVE_VERIFIED';a._LIVE_REGISTRY[id(p)]=(p,'a'*40,'b'*64)
  self.addCleanup(a._LIVE_REGISTRY.pop,id(p),None);return p
 def test_workflow_exact_environment_names(self):
  for plan in (PLAN,CFPLAN):
   for op in plan['operations'].values():
    text=(ROOT/op['workflow_path']).read_text()
    for k in ('TEST_ONLY','DRY_RUN','NO_PUBLISH','EMERGENCY_STOP'):self.assertIn("      "+k+": 'true'",text)
    self.assertIn('PLM_MARKER_SHA: ${{ vars.PLM_APPROVED_MARKER_SHA256 }}',text)
 def test_callback_actual_string_contract_and_header(self):
  conn=Mock();response=Mock(status=200);conn.getresponse.return_value=response
  send=CallbackHTTP(self.live_fixture('finalize'),'callback.example.com',connector=Mock(return_value=conn))
  self.assertEqual(send('https://callback.example.com/youtube/result','{"x":1}','b'*64),200)
  self.assertEqual(conn.request.call_args.kwargs['body'],b'{"x":1}')
  self.assertEqual(conn.request.call_args.kwargs['headers']['X-PLM-Signature'],'b'*64)
  response.read.assert_not_called()
  with self.assertRaises(Stop):send('https://callback.example.com/youtube/result','{}','b'*64)
  self.assertEqual(conn.request.call_count,1)
 def test_callback_timeout_no_retry_and_no_body(self):
  conn=Mock();conn.getresponse.side_effect=TimeoutError('PRIVATE_TOKEN')
  send=CallbackHTTP(self.live_fixture('finalize'),'callback.example.com',connector=Mock(return_value=conn))
  with self.assertRaises(Stop) as cm:send('https://callback.example.com/youtube/result',b'{}','b'*64)
  self.assertNotIn('PRIVATE_TOKEN',str(cm.exception))
  with self.assertRaises(Stop):send('https://callback.example.com/youtube/result',b'{}','b'*64)
  self.assertEqual(conn.request.call_count,1)
 def artifact(self,status=200):
  from plm.automation.executors.run_reader import RunEvidence,_RUN_SEAL
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:z.writestr('runtime-receipt.json',b'{}')
  raw=b.getvalue();api=Mock();storage=Mock()
  r=Mock(status=302);r.getheader.return_value='https://productionresultssa7.blob.core.windows.net/actions-results/f?sig=PRIVATE_URL'
  api.getresponse.return_value=r;s=Mock(status=status);s.read.return_value=raw;storage.getresponse.return_value=s
  connect=Mock(side_effect=[api,storage]);p=RunEvidence('123','a'*40,'state_init',True,_RUN_SEAL)
  return ArtifactInput(p,'PRIVATE_TOKEN',connector=connect),raw,api,storage
 def test_artifact_handoff_bearer_never_forwarded(self):
  x,raw,api,storage=self.artifact()
  with tempfile.TemporaryDirectory() as tmp:
   path=x.download(12,hashlib.sha256(raw).hexdigest(),allowed_names=['runtime-receipt.json'],output=tmp)
   self.assertEqual((path/'runtime-receipt.json').read_bytes(),b'{}')
  self.assertEqual(x.calls,2);self.assertEqual(x.statuses,[302,200])
  self.assertNotIn('headers',storage.request.call_args.kwargs);self.assertNotIn('PRIVATE_TOKEN',repr(x))
  x.clear();self.assertIsNone(x.token)
 def test_artifact_second_redirect_not_followed(self):
  x,raw,api,storage=self.artifact(status=302)
  with tempfile.TemporaryDirectory() as tmp:
   with self.assertRaises(Stop):x.download(12,hashlib.sha256(raw).hexdigest(),allowed_names=['runtime-receipt.json'],output=tmp)
   with self.assertRaises(Stop):x.download(12,hashlib.sha256(raw).hexdigest(),allowed_names=['runtime-receipt.json'],output=tmp)
  self.assertEqual(x.calls,2);storage.getresponse.return_value.read.assert_not_called()
 def test_artifact_unrelated_origin_no_second_get(self):
  x,raw,api,storage=self.artifact();api.getresponse.return_value.getheader.return_value='https://evil.example/file'
  with tempfile.TemporaryDirectory() as tmp:
   with self.assertRaises(Stop):x.download(12,hashlib.sha256(raw).hexdigest(),allowed_names=['runtime-receipt.json'],output=tmp)
  self.assertEqual(x.calls,1);storage.request.assert_not_called()
 def test_artifact_budget_before_first_get(self):
  x,raw,api,storage=self.artifact();x.calls=5
  with self.assertRaises(Stop):x.download(12,hashlib.sha256(raw).hexdigest(),allowed_names=['runtime-receipt.json'],output='/unused')
  api.request.assert_not_called()
 def test_native_role_mismatch_before_connector(self):
  from plm.automation.executors import transports as t
  p=self.live_fixture('channel');connect=Mock()
  with self.assertRaises(Stop):t.StateInitHTTP('PRIVATE_TOKEN',p,connector=connect)
  with self.assertRaises(Stop):t.strict_upload_transport(p)
  with self.assertRaises(Stop):t.lifecycle_backend(p,'PRIVATE_TOKEN')
  connect.assert_not_called()
 def test_fixture_run_evidence_cannot_issue_live(self):
  from plm.automation.executors.release import _AUDIT_SEAL
  from plm.automation.executors.run_reader import RunEvidence,_RUN_SEAL
  checked=CheckedAudit('channel',PLAN,{'run_id':'123'},'a'*40,'b'*40,'c'*64,{},_AUDIT_SEAL,str(ROOT))
  with self.assertRaises(Stop):issue_live(checked,prerequisites=[],policy=frozen_policy(),run_evidence=RunEvidence('123','b'*40,'channel',False,_RUN_SEAL))
 def test_cli_all_eight_parked_no_credentials(self):
  import os
  for op in frozen_policy()['releases']:
   out=subprocess.check_output(['python','-m','plm.automation.executors.entrypoint','--operation',op],cwd=ROOT,env={**os.environ,'PLM_YOUTUBE_GAME_001':'PRIVATE_VALUE'})
   d=json.loads(out);self.assertEqual(d['status'],'PARKED');self.assertEqual(d['credentials_read'],0);self.assertNotIn(b'PRIVATE_VALUE',out)
