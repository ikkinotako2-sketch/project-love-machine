import base64,copy,hashlib,io,json,os,subprocess,tempfile,threading,unittest
from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
from unittest.mock import Mock,patch
from plm.automation.executors.authority import OfflineAuthority,ExecutorAudit,production_entry,live_authority,Receipt
from plm.automation.executors.channel_state import ChannelExecutor,StateInitExecutor,initial_bytes,initial_sha,blob_sha
from plm.automation.executors.transports import StateInitHTTP,REF,REFS,STATE,channel_transports,strict_upload_transport
from plm.automation.executors.posting import UploadExecutor,FinalizeExecutor,RunProofAdapter,JOB_ID,ARTIFACT,ARCHIVE,RENDER_COMMIT
from plm.automation.executors.lifecycle import ExecutorLifecycle
from plm.automation.shared_lifecycle import SQLiteCAS,GitContentsCAS
from plm.automation.evidence_adapters import FreshChannel,MemoryOAuthRefresh,ProcessedReadback,GitHubCompletionAuthority
from plm.automation.live_factory import CallbackOnce
from plm.automation.production_bridge import READ,UPLOAD,CHANNEL,MEDIA
from plm.automation.quota_contract import FIELDS
from plm.automation.render_contract import contract,VOICE
from plm.automation.execution_gate import digest,load_pinned_plan,MARKER_KEYS
from plm.automation.ledger import Stop
ROOT=Path(__file__).resolve().parents[1]
PLAN=json.loads((ROOT/'readiness/executor-final-plan.json').read_bytes())
ASSET=Path(os.environ.get('PLM_OFFLINE_MEDIA',str(ROOT.parent/'deliverables/plm-offline-proof/short.mp4')))
NOW=1791849600

class FixtureFunction:
    offline_mock=True
    def __init__(self,fn):self.fn=fn;self.calls=0
    def __call__(self,*args,**kwargs):self.calls+=1;return self.fn(*args,**kwargs)

class FreshFixture:
    offline_mock=True
    def __init__(self,now=NOW,scopes=None,channel=CHANNEL,status=200):
        self.sends=[];self.reads=[];self.scopes=[READ,UPLOAD] if scopes is None else scopes
        def send(form):
            self.sends.append('POST');return status,{'access_token':'FIXTURE_TOKEN_DO_NOT_LOG','expires_in':3600,'token_type':'Bearer','scope':' '.join(self.scopes)}
        self.refresh=MemoryOAuthRefresh({'client_id':'FIXTURE_CLIENT','client_secret':'FIXTURE_SECRET_DO_NOT_LOG','refresh_token':'FIXTURE_REFRESH_DO_NOT_LOG'},send,lambda:now,approved=True)
        def get_for_token(token):
            def get(path):
                self.reads.append(path);return 200,{'kind':'youtube#channelListResponse','items':[{'id':channel}]}
            return get
        self.fresh=FreshChannel(self.refresh,get_for_token,lambda:now);self.last=None
    def create(self):self.last=self.fresh.create();return self.last

class StateService:
    offline_mock=True
    def __init__(self,base,*,branch_exists=True,barrier=None,lose_write=False):
        self.base=base;self.branch=branch_exists;self.file=None;self.calls=[];self.lock=threading.Lock();self.barrier=barrier;self.lose_write=lose_write
    def __call__(self,method,path,body):
        self.calls.append((method,path))
        if method=='GET' and path==REF:return (200,{'ref':'refs/heads/'+GitContentsCAS.BRANCH,'object':{'type':'commit','sha':self.base}}) if self.branch else (404,{})
        if method=='POST' and path==REFS:
            with self.lock:
                if self.branch:return 422,{}
                self.branch=True;return 201,{'ref':body['ref'],'object':{'type':'commit','sha':body['sha']}}
        if method=='GET':
            value=(404,{}) if self.file is None else (200,{'sha':blob_sha(self.file)})
            if self.barrier:self.barrier.wait()
            return value
        assert method=='PUT' and path==STATE and 'sha' not in body and body['branch']!='main'
        with self.lock:
            if self.file is not None:return 409,{}
            self.file=base64.b64decode(body['content'])
            if self.lose_write:raise TimeoutError('ARBITRARY_REMOTE_SECRET_MUST_NOT_LOG')
            return 201,{'content':{'path':'automation-state/lifecycle.json','sha':blob_sha(self.file)},'commit':{'sha':'d'*40,'parents':[{'sha':self.base}]}}


def expected_proof(operation,run='123',phase='before_upload',mutate=None):
    op=PLAN['operations'][operation]
    prepared='b'*40;commit='a'*40 if run=='123' else 'd'*40
    marker={'identity':op['identity'],'operation':operation,'job_id':JOB_ID,'media_sha256':MEDIA,'state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':prepared,'approved':True,'upload_approved':operation=='private_upload','finalize_approved':operation=='finalize'}
    marker_raw=json.dumps(marker).encode();workflow=(ROOT/op['workflow_path']).read_bytes()
    e={'repository':PLAN['repository'],'run_id':run,'attempt':1,'commit':commit,'prepared_commit':prepared,'branch':PLAN['branch'],'workflow_path':op['workflow_path'],'job_name':operation,'job_id':JOB_ID,'identity':op['identity'],'media_sha256':MEDIA,'artifact_id':ARTIFACT,'artifact_archive_sha256':ARCHIVE,'artifact_run_id':38250671983,'artifact_commit':RENDER_COMMIT,'marker_path':op['marker_path'],'marker_sha256':digest(marker_raw),'workflow_sha256':digest(workflow),'approval_field':'finalize_approved' if operation=='finalize' else 'upload_approved'}
    responses=[{'id':int(run),'repository':{'full_name':e['repository']},'run_attempt':1,'head_sha':commit,'head_branch':e['branch'],'path':e['workflow_path'],'event':'push','status':'completed' if phase=='completed' else 'in_progress','conclusion':'success' if phase=='completed' else None},
        {'total_count':1,'jobs':[{'name':operation,'run_id':int(run),'status':'completed' if phase=='completed' else 'in_progress','conclusion':'success' if phase=='completed' else None}]},
        {'total_count':1,'artifacts':[{'id':ARTIFACT,'expired':False,'expires_at':'2026-11-11T12:43:33Z','digest':'sha256:'+ARCHIVE,'workflow_run':{'id':38250671983,'head_sha':RENDER_COMMIT}}]},
        {'encoding':'base64','content':base64.b64encode(marker_raw).decode()},
        {'encoding':'base64','content':base64.b64encode(workflow).decode()},
        {'parents':[{'sha':prepared}],'files':[{'filename':e['marker_path'],'status':'added'}]}]
    if mutate:mutate(responses)
    calls=[]
    def get(path):
        calls.append(path);return 200,responses.pop(0)
    return e,FixtureFunction(get),calls


def valid_video(video='offline0001'):
    return {'kind':'youtube#videoListResponse','items':[{'id':video,'snippet':{'channelId':CHANNEL},'status':{'privacyStatus':'private','uploadStatus':'processed'},'processingDetails':{'processingStatus':'succeeded'}}]}

class AuthorityTests(unittest.TestCase):
    def setUp(self):self.authority=OfflineAuthority(PLAN)
    def test_no_approval_or_marker(self):
        for kwargs in ({},{'approved':True},{'marker_consumed':True},{'approved':True,'marker_consumed':True,'attempt':2}):
            with self.assertRaises(Stop):self.authority.issue('channel',**kwargs)
    def test_old_identity_and_channel_marker_protected(self):
        identities=[o['identity'] for o in PLAN['operations'].values()]
        self.assertEqual(len(set(identities)),4)
        for p in ['provider-neutral-youtube-channel-verify-20261012-r1','provider-neutral-youtube-oauth-verify-20261012-r1','provider-neutral-youtube-oauth-verify-20261012-r2']:
            self.assertNotIn(p,identities)
        for o in PLAN['operations'].values():self.assertFalse((ROOT/o['marker_path']).exists())
    def test_forged_claims_cannot_release_credentials_or_network(self):
        loader=Mock(side_effect=AssertionError('SECRET_READ_FORBIDDEN'))
        for operation in PLAN['operations']:
            for flags in [PLAN['safe_flags'],dict.fromkeys(PLAN['safe_flags'],False)]:
                result=production_entry(operation,credentials_loader=loader,approved=True,scope_readonly=True,channel_match=True,marker_consumed=True,safe_flags=flags)
                self.assertEqual(result['requests'],0);self.assertTrue(result['status'].startswith('PARKED'))
        loader.assert_not_called()
    def test_fixture_receipt_not_live_authority(self):
        p=self.authority.issue('channel',approved=True,marker_consumed=True)
        with self.assertRaises(Stop):StateInitHTTP('FIXTURE_TOKEN',p)
        with self.assertRaises(Stop):channel_transports(p,{},lambda:NOW)
        with self.assertRaises(Stop):strict_upload_transport(p)
    def test_dictionary_receipt_not_accepted(self):
        with self.assertRaises(Stop):self.authority.issue('state_init',prerequisites=({'status':'VERIFIED','channel_match':True},),approved=True,marker_consumed=True)
    def test_identity_issue_once(self):
        self.authority.issue('channel',approved=True,marker_consumed=True)
        with self.assertRaises(Stop):self.authority.issue('channel',approved=True,marker_consumed=True)
    def test_workflows_disabled_full_history_no_secrets(self):
        for o in PLAN['operations'].values():
            w=(ROOT/o['workflow_path']).read_text()
            for t in ['if: ${{ false }}','fetch-depth: 0','persist-credentials: false']:self.assertIn(t,w)
            self.assertNotIn('secrets.',w);self.assertNotIn('schedule:',w)
    def test_plan_initial_source_exact(self):
        self.assertEqual((ROOT/'readiness/executor-initial-state.json').read_bytes(),initial_bytes())
        self.assertEqual(initial_sha(),PLAN['operations']['state_init']['initial_state_sha256'])
        self.assertTrue(load_pinned_plan(json.dumps(PLAN).encode(),digest(json.dumps(PLAN).encode())))

class ChannelTests(unittest.TestCase):
    def permit(self):return OfflineAuthority(PLAN).issue('channel',approved=True,marker_consumed=True)
    def test_fresh_same_credential_channel_success(self):
        f=FreshFixture();out=ChannelExecutor(f).run(self.permit())
        self.assertEqual(out.status,'VERIFIED');self.assertEqual(out.basis,'OFFLINE_CONTRACT')
        self.assertEqual(f.sends,['POST']);self.assertEqual(len(f.reads),1)
        with self.assertRaises(Stop):f.last.token()
    def test_upload_only_scope_no_channel_get(self):
        f=FreshFixture(scopes=[UPLOAD])
        with self.assertRaises(Stop):ChannelExecutor(f).run(self.permit())
        self.assertEqual(f.reads,[]);self.assertEqual(len(f.sends),1)
    def test_wrong_channel_stops(self):
        f=FreshFixture(channel='wrong')
        with self.assertRaises(Stop):ChannelExecutor(f).run(self.permit())
        self.assertEqual(len(f.reads),1)
    def test_refresh_error_no_read_retry(self):
        f=FreshFixture(status=400);p=self.permit();x=ChannelExecutor(f)
        for _ in range(2):
            with self.assertRaises(Stop):x.run(p)
        self.assertEqual(f.sends,['POST']);self.assertEqual(f.reads,[])
    def test_sanitized_output_no_credential(self):
        s=io.StringIO();f=FreshFixture()
        with redirect_stdout(s),redirect_stderr(s):result=ChannelExecutor(f).run(self.permit())
        text=s.getvalue()+json.dumps(result.public())+repr(f.refresh)
        for v in ['FIXTURE_TOKEN_DO_NOT_LOG','FIXTURE_SECRET_DO_NOT_LOG','FIXTURE_REFRESH_DO_NOT_LOG']:self.assertNotIn(v,text)

class InitTests(unittest.TestCase):
    def setUp(self):
        self.a=OfflineAuthority(PLAN)
        self.channel=ChannelExecutor(FreshFixture()).run(self.a.issue('channel',approved=True,marker_consumed=True))
        self.base=PLAN['operations']['state_init']['state_base_commit']
    def permit(self):return self.a.issue('state_init',prerequisites=(self.channel,),approved=True,marker_consumed=True)
    def test_existing_branch_new_state_atomic(self):
        t=StateService(self.base);out=StateInitExecutor(t).run(self.permit())
        self.assertEqual(out.status,'VERIFIED');self.assertEqual([m for m,_ in t.calls],['GET','GET','PUT'])
        self.assertEqual(t.file,initial_bytes())
    def test_absent_branch_create_once(self):
        t=StateService(self.base,branch_exists=False);out=StateInitExecutor(t).run(self.permit())
        self.assertEqual(out.status,'VERIFIED');self.assertEqual([m for m,_ in t.calls],['GET','POST','GET','PUT'])
    def test_existing_state_never_overwritten(self):
        t=StateService(self.base);t.file=b'PERMANENT_TOMBSTONE'
        with self.assertRaises(Stop):StateInitExecutor(t).run(self.permit())
        self.assertEqual(t.file,b'PERMANENT_TOMBSTONE');self.assertEqual([m for m,_ in t.calls],['GET','GET'])
    def test_two_initializers_one_winner(self):
        t=StateService(self.base,barrier=threading.Barrier(2));out=[]
        def worker():
            a=OfflineAuthority(PLAN);c=ChannelExecutor(FreshFixture()).run(a.issue('channel',approved=True,marker_consumed=True))
            p=a.issue('state_init',prerequisites=(c,),approved=True,marker_consumed=True)
            try:out.append(StateInitExecutor(t).run(p).status)
            except Stop:out.append('STOP')
        ts=[threading.Thread(target=worker) for _ in range(2)]
        for x in ts:x.start()
        for x in ts:x.join()
        self.assertEqual(sorted(out),['STOP','VERIFIED']);self.assertEqual(t.file,initial_bytes())
    def test_lost_write_ack_no_read_or_write_after(self):
        t=StateService(self.base,lose_write=True);x=StateInitExecutor(t);p=self.permit()
        for _ in range(2):
            with self.assertRaises(Stop):x.run(p)
        self.assertEqual(len(t.calls),3);self.assertTrue(x.uncertain)
        with self.assertRaises(Stop):x.request('GET',REF)
        self.assertEqual(len(t.calls),3)
    def test_branch_drift_no_contents_write(self):
        t=StateService('f'*40)
        with self.assertRaises(Stop):StateInitExecutor(t).run(self.permit())
        self.assertEqual(len(t.calls),1)
    def test_source_hash_mismatch_no_io(self):
        p=self.permit();p.spec['initial_state_sha256']='0'*64;t=StateService(self.base)
        with self.assertRaises(Stop):StateInitExecutor(t).run(p)
        self.assertEqual(t.calls,[])

class UploadFinalizeTests(unittest.TestCase):
    def setUp(self):
        if not ASSET.is_file():self.skipTest('Dedicated executor CI supplies unchanged approved movie artifact')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.now=NOW
        self.b=SQLiteCAS(Path(self.tmp.name)/'state.sqlite',initialize=True);self.addCleanup(self.b.close)
        self.s=ExecutorLifecycle(self.b,lambda:self.now,completion_authority=lambda row:False)
        self.a=OfflineAuthority(PLAN);self.c=ChannelExecutor(FreshFixture()).run(self.a.issue('channel',approved=True,marker_consumed=True))
        self.init=StateInitExecutor(StateService(PLAN['operations']['state_init']['state_base_commit'])).run(self.a.issue('state_init',prerequisites=(self.c,),approved=True,marker_consumed=True))
        e=json.loads((ROOT/'readiness/reused-render-evidence.json').read_bytes());job=json.loads((ROOT/'readiness/youtube-private-job.json').read_bytes())
        script={'title':job['title'],'hook':job['sentences'][0],'narration':''.join(job['sentences']),'scenes':[{'start':t['start_seconds'],'end':t['end_seconds'],'caption':t['text'],'visual_keyword':'study','motion':'none','sfx':'none','emphasis_words':[]} for t in e['timing']],'bgm':{'mood':'calm','volume':0}}
        raw=json.dumps(script,ensure_ascii=False,separators=(',',':'))
        rc=contract(raw,mode='REUSE_PINNED',voice=VOICE,media_sha=e['media_sha256'],audio_sha=e['audio_sha256'],caption_sha=e['caption_sha256'])
        self.assets={'media_path':ASSET,'quality_evidence':e,'render_contract':rc,'script_raw':raw,'voice_inventory':[{'name':'ずんだもん','styles':[{'id':3,'name':'ノーマル'}]}],'audio':ASSET.with_name('audio.wav').read_bytes(),'captions':ASSET.with_name('captions.ass').read_bytes(),'render_evidence':{'voice':VOICE,'script_sha256':rc['script_sha256'],'quality_pass':True,**{k:e[k] for k in ['media_sha256','audio_sha256','caption_sha256']}}}
        self.budget={'plan':'FREE','billing_cap_usd':0,'basis':'OFFLINE_FIXTURE','observed_at':self.now,'remaining':{k:1000000000 for k in FIELDS}};self.cost={k:1 for k in FIELDS}
        self.events=[];outer=self
        class Upload:
            offline_mock=True
            def init(self,token,metadata,size):
                assert outer.s.get(JOB_ID)['sent'] is True;outer.events.append('INIT');return '/fixture/upload'
            def media(self,token,path,media):
                outer.events.append('MEDIA');return 200,json.dumps({'id':'offline0001','snippet':{'channelId':CHANNEL},'status':{'privacyStatus':'private'}}).encode()
        self.upload=Upload()
    def upload_run(self,mutate=None,upload=None):
        p=self.a.issue('private_upload',prerequisites=(self.c,self.init),approved=True,marker_consumed=True)
        e,get,calls=expected_proof('private_upload',mutate=mutate);self.expected=e;self.upload_reads=calls
        engine=UploadExecutor(state=self.s,fresh=FreshFixture(self.now),provenance=RunProofAdapter(get,lambda:self.now),upload=upload or self.upload,clock=lambda:self.now)
        self.upload_engine=engine;self.upload_permit=p
        self.ack=engine.run(p,expected=e,assets=self.assets,budget_observation=self.budget,budget_cost=self.cost)
        return self.ack
    def final_run(self,mutate_upload=None,mutate_own=None,read=None,callback=None,own_run='999'):
        p=self.a.issue('finalize',prerequisites=(self.ack,),approved=True,marker_consumed=True)
        e,u,uc=expected_proof('private_upload',phase='completed',mutate=mutate_upload)
        own,o,oc=expected_proof('finalize',run=own_run,mutate=mutate_own)
        get=FixtureFunction(read or (lambda path:(200,valid_video())))
        def rb(token):
            r=ProcessedReadback(get,approved=True,read_scope_proven=True);r.offline_mock=True;return r
        cb=FixtureFunction(callback or (lambda receipt:'ACK'));self.readback_get=get;self.callback=cb;self.own_reads=oc;self.completed_reads=uc
        engine=FinalizeExecutor(state=self.s,upload_provenance=RunProofAdapter(u,lambda:self.now),own_provenance=RunProofAdapter(o,lambda:self.now),fresh=FreshFixture(self.now),readback_for_token=FixtureFunction(rb),callback=cb,clock=lambda:self.now)
        self.final_engine=engine;self.final_permit=p;self.own_expected=own
        return engine.run(p,own_expected=own,script_sha256=self.assets['render_contract']['script_sha256'])
    def test_four_executors_e2e_ack_then_independent_done(self):
        ack=self.upload_run();self.assertEqual(ack.status,'ACKNOWLEDGED');self.assertEqual(self.s.get(JOB_ID)['state'],'ACKNOWLEDGED')
        self.assertEqual(self.events,['INIT','MEDIA']);self.assertEqual(len(self.upload_reads),6)
        with self.assertRaises(Stop):self.s.claim('next-job','c'*64,'next-op','owner',self.now,day='2026-10-13')
        done=self.final_run();self.assertEqual(done.status,'Done');self.assertFalse(done.data['next_job_dispatch'])
        self.assertEqual(len(self.completed_reads),6);self.assertEqual(len(self.own_reads),6);self.assertEqual(self.readback_get.calls,1);self.assertEqual(self.callback.calls,1)
        self.assertTrue(self.s.get(JOB_ID)['consumed']);self.assertTrue(self.s.get(JOB_ID)['finalizer']['consumed'])
        with self.assertRaises(Stop):self.s.claim(JOB_ID,'c'*64,'different-op','owner',self.now,day='2026-10-13')
    def test_duplicate_strict_upload_no_second_init(self):
        self.upload_run()
        for _ in range(2):
            with self.assertRaises(Stop):self.upload_engine.run(self.upload_permit,expected=self.expected,assets=self.assets,budget_observation=self.budget,budget_cost=self.cost)
        self.assertEqual(self.events,['INIT','MEDIA'])
    def test_upload_timeout_quarantines_no_resend(self):
        def media(token,path,media):self.events.append('MEDIA_TIMEOUT');raise TimeoutError()
        self.upload.media=media
        with self.assertRaises(Stop):self.upload_run()
        self.assertEqual(self.s.get(JOB_ID)['state'],'UNKNOWN');self.assertTrue(self.s.doc['stopped'])
        self.assertEqual(self.events,['INIT','MEDIA_TIMEOUT'])
    def test_claim_write_unknown_no_oauth_or_upload(self):
        original=self.b.cas;count=[]
        def lose(sha,d):count.append(1);original(sha,d);raise TimeoutError()
        self.b.cas=lose
        with self.assertRaises(Stop):self.upload_run()
        self.assertTrue(self.s.uncertain);self.assertEqual(self.events,[]);self.assertEqual(count,[1])
    def test_sent_write_unknown_no_upload(self):
        original=self.b.cas;calls=[]
        def lose(sha,d):
            calls.append(1);value=original(sha,d)
            if d['jobs'][JOB_ID]['sent']:raise TimeoutError()
            return value
        self.b.cas=lose
        with self.assertRaises(Stop):self.upload_run()
        self.assertTrue(self.s.uncertain);self.assertEqual(self.events,[]);self.assertEqual(len(calls),2)
    def test_wrong_run_attempt_no_claim(self):
        with self.assertRaises(Stop):self.upload_run(mutate=lambda xs:xs[0].update(run_attempt=2))
        self.assertEqual(self.s.doc['jobs'],{});self.assertEqual(self.events,[])
    def test_expired_artifact_no_claim(self):
        with self.assertRaises(Stop):self.upload_run(mutate=lambda xs:xs[2]['artifacts'][0].update(expires_at='2026-01-01T00:00:00Z'))
        self.assertEqual(self.s.doc['jobs'],{})
    def test_unknown_budget_no_claim(self):
        self.budget['remaining']['youtube_insert_calls']=None
        with self.assertRaises(Stop):self.upload_run()
        self.assertEqual(self.s.doc['jobs'],{});self.assertEqual(self.events,[])
    def test_media_caption_voice_or_credit_mismatch_no_claim(self):
        self.assets['render_contract']['voice']={**VOICE,'speaker_id':1}
        with self.assertRaises(Stop):self.upload_run()
        self.assertEqual(self.s.doc['jobs'],{});self.assertEqual(self.events,[])
    def test_upload_receipt_survives_restart_no_token(self):
        self.upload_run();s=ExecutorLifecycle(self.b,lambda:self.now,completion_authority=lambda row:False)
        row=s.get(JOB_ID);self.assertEqual(row['upload_receipt']['media_sha256'],MEDIA)
        text=json.dumps(row)
        for x in ['FIXTURE_TOKEN_DO_NOT_LOG','FIXTURE_SECRET_DO_NOT_LOG','FIXTURE_REFRESH_DO_NOT_LOG']:self.assertNotIn(x,text)
    def test_finalize_requires_completed_success_run_before_write(self):
        self.upload_run();sha=self.s.sha
        with self.assertRaises(Stop):self.final_run(mutate_upload=lambda xs:xs[0].update(conclusion='failure'))
        self.assertEqual(self.s.sha,sha);self.assertNotIn('finalizer',self.s.get(JOB_ID))
    def test_finalize_independent_identity_and_run(self):
        self.upload_run()
        with self.assertRaises(Stop):self.final_run(own_run='123')
        self.assertNotIn('finalizer',self.s.get(JOB_ID))
    def test_processed_unknown_quarantines_not_done(self):
        self.upload_run()
        with self.assertRaises(Stop):self.final_run(read=lambda path:(403,{}))
        self.assertEqual(self.s.get(JOB_ID)['state'],'UNKNOWN');self.assertTrue(self.s.doc['stopped']);self.assertEqual(self.callback.calls,0)
        self.assertEqual(self.events,['INIT','MEDIA'])
    def test_readback_channel_or_processing_mismatch(self):
        self.upload_run()
        d=valid_video();d['items'][0]['snippet']['channelId']='wrong'
        with self.assertRaises(Stop):self.final_run(read=lambda path:(200,d))
        self.assertEqual(self.s.get(JOB_ID)['state'],'UNKNOWN');self.assertEqual(self.callback.calls,0)
    def test_callback_unknown_stops_no_second_delivery(self):
        self.upload_run()
        def cb(receipt):raise TimeoutError()
        with self.assertRaises(Stop):self.final_run(callback=cb)
        self.assertEqual(self.s.get(JOB_ID)['state'],'UNKNOWN');self.assertEqual(self.s.get(JOB_ID)['callback'],'SENT');self.assertEqual(self.callback.calls,1)
        with self.assertRaises(Stop):self.final_engine.run(self.final_permit,own_expected=self.own_expected,script_sha256=self.assets['render_contract']['script_sha256'])
        self.assertEqual(self.callback.calls,1)
    def test_expired_upload_lease_finalization_only_safe_transfer(self):
        self.upload_run();self.now+=301;done=self.final_run()
        self.assertEqual(done.status,'Done');self.assertEqual(self.s.get(JOB_ID)['owner'],'finalize-999')
        self.assertEqual(self.events,['INIT','MEDIA'])
    def test_finalize_cas_ack_loss_no_next_even_if_stored_done(self):
        self.upload_run();original=self.b.cas
        def lose(sha,d):
            v=original(sha,d)
            if d['jobs'][JOB_ID]['state']=='Done':raise TimeoutError()
            return v
        self.b.cas=lose
        with self.assertRaises(Stop):self.final_run()
        self.assertTrue(self.s.uncertain)
        s=ExecutorLifecycle(self.b,lambda:self.now,completion_authority=lambda row:False)
        self.assertEqual(s.get(JOB_ID)['state'],'Done')
        with self.assertRaises(Stop):s.claim('next-job','c'*64,'next-op','owner',self.now,day='2026-10-13')
    def test_two_finalizers_one_fenced_winner(self):
        self.upload_run();other=ExecutorLifecycle(self.b,lambda:self.now,completion_authority=lambda row:False)
        self.final_run()
        proof={'verified':True,'phase':'completed','proof_basis':'INDEPENDENT_GITHUB_API','job_id':JOB_ID,'identity':PLAN['operations']['private_upload']['identity'],'run_id':'123','media_sha256':MEDIA}
        with self.assertRaises(Stop):other.finalize_claim(other.get(JOB_ID),'different-finalizer','1000',proof)
        self.assertEqual(self.s.get(JOB_ID)['state'],'Done')
    def test_done_not_enough_for_next_without_coordinator_success(self):
        self.upload_run();self.final_run()
        with self.assertRaises(Stop):self.s.claim('next-job','c'*64,'next-op','owner',self.now,day='2026-10-13')
        e,up,_=expected_proof('private_upload',phase='completed');ce,co,_=expected_proof('finalize',run='999',phase='completed')
        calls=[]
        def get(path):
            # GitHubCompletionAuthority checks uploader then independent coordinator.
            calls.append(path);return up(path) if len(calls)<=6 else co(path)
        authority=GitHubCompletionAuthority(get,lambda row:ce)
        self.s.authority=authority
        nxt=self.s.claim('next-job','c'*64,'next-op','owner',self.now,day='2026-10-13')
        self.assertEqual(nxt['job_id'],'next-job');self.assertEqual(len(calls),12)
        self.assertTrue(self.s.get(JOB_ID)['consumed'])

    def test_upload_missing_read_scope_fresh_session_stops_no_send(self):
        p=self.a.issue('private_upload',prerequisites=(self.c,self.init),approved=True,marker_consumed=True)
        e,get,_=expected_proof('private_upload');fresh=FreshFixture(scopes=[UPLOAD])
        x=UploadExecutor(state=self.s,fresh=fresh,provenance=RunProofAdapter(get,lambda:self.now),upload=self.upload,clock=lambda:self.now)
        with self.assertRaises(Stop):x.run(p,expected=e,assets=self.assets,budget_observation=self.budget,budget_cost=self.cost)
        self.assertEqual(fresh.reads,[]);self.assertEqual(self.events,[]);self.assertTrue(self.s.doc['stopped'])
    def test_corrupted_saved_movie_hash_no_claim(self):
        p=Path(self.tmp.name)/'corrupt.mp4';data=bytearray(ASSET.read_bytes());data[-1]^=1;p.write_bytes(data)
        self.assets['media_path']=p
        with self.assertRaises(Stop):self.upload_run()
        self.assertEqual(self.s.doc['jobs'],{});self.assertEqual(self.events,[])
    def test_wrong_scope_or_channel_proof_dictionary_does_not_start_upload(self):
        with self.assertRaises(Stop):self.a.issue('private_upload',prerequisites=({'channel_match':True},self.init),approved=True,marker_consumed=True)
        self.assertEqual(self.events,[])

    def test_finalize_uses_existing_signed_callback_contract(self):
        self.upload_run();seen=[]
        context={'account_id':'youtube_game_001','intent_id':'intent-job','job_id':JOB_ID,'owner':'owner','owner_epoch':1,'fencing_token':1,'dispatch_id':'d'*64,'run_id':'123','run_attempt':1,'workflow_sha256':'a'*64,'script_sha256':self.assets['render_contract']['script_sha256']}
        checkpoint={'run_id':'123','script_sha256':context['script_sha256'],'media_sha256':MEDIA,'quality_gate':'PASS'}
        def send(url,body,signature):
            seen.append((url,json.loads(body),signature));return 200
        callback=CallbackOnce(send,context,checkpoint,b'K'*32,'fixture-callback-v1',origin='callback.example.com',approved=True,clock=lambda:self.now,dispatch_key=b'D'*32)
        result=self.final_run(callback=callback)
        self.assertEqual(result.status,'Done');self.assertEqual(len(seen),1)
        self.assertEqual(seen[0][0],'https://callback.example.com/youtube/result')
        self.assertEqual(seen[0][1]['protocol'],'plm-youtube-result-v2');self.assertEqual(len(seen[0][2]),64)
        self.assertEqual(self.s.get(JOB_ID)['completion_receipt']['callback'],'ACK')
    def test_finalizer_render_hash_must_match_durable_upload(self):
        self.upload_run()
        p=self.a.issue('finalize',prerequisites=(self.ack,),approved=True,marker_consumed=True)
        e,u,_=expected_proof('private_upload',phase='completed');own,o,_=expected_proof('finalize',run='999')
        rb=FixtureFunction(lambda token:None);cb=FixtureFunction(lambda receipt:'ACK')
        x=FinalizeExecutor(state=self.s,upload_provenance=RunProofAdapter(u,lambda:self.now),own_provenance=RunProofAdapter(o,lambda:self.now),fresh=FreshFixture(self.now),readback_for_token=rb,callback=cb,clock=lambda:self.now)
        with self.assertRaises(Stop):x.run(p,own_expected=own,script_sha256='0'*64)
        self.assertEqual(u.calls,0);self.assertEqual(o.calls,0);self.assertNotIn('finalizer',self.s.get(JOB_ID))

class PreflightHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'repo';self.root.mkdir();self.plan=copy.deepcopy(PLAN)
        self.git('init','-q');self.git('config','user.name','Fixture');self.git('config','user.email','fixture@example.invalid')
        self.write('base.txt',b'base');self.commit('base');self.base=self.head();self.plan['preparation_parent']=self.base
        for p in self.plan['preparation_files']:self.write(p,b'fixture\n')
        self.write('readiness/executor-final-plan.json',(json.dumps(self.plan)+'\n').encode())
        self.write(self.plan['source_manifest'],json.dumps({'source_sha256':{self.plan['operations']['channel']['executor_path']:digest(b'fixture\n')}}).encode())
        self.commit('prepare');self.prepared=self.head();self.audit=ExecutorAudit(self.root)
    def git(self,*args):return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.DEVNULL)
    def write(self,p,raw):f=self.root/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(raw)
    def commit(self,m):self.git('add','.');self.git('commit','-q','-m',m)
    def head(self):return self.git('rev-parse','HEAD').decode().strip()
    def marker(self,extra=None,modify=None):
        o=self.plan['operations']['channel'];m={'identity':o['identity'],'operation':'channel','state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':self.prepared,'approved':True,'job_id':JOB_ID,'media_sha256':MEDIA,'upload_approved':False,'finalize_approved':False}
        paths={'plan_sha256':'readiness/executor-final-plan.json','source_manifest_sha256':self.plan['source_manifest'],'workflow_sha256':o['workflow_path'],'executor_sha256':o['executor_path'],'schema_sha256':self.plan['schema_path']}
        m.update({k:digest((self.root/p).read_bytes()) for k,p in paths.items()})
        if modify:modify(m)
        raw=(json.dumps(m)+'\n').encode();self.write(o['marker_path'],raw)
        if extra:self.write(extra,b'extra')
        self.commit('PLM executor once '+o['identity']);self.marker_hash=digest(raw)
    def audit_args(self):
        return {'event':{'repository':PLAN['repository'],'branch':PLAN['branch'],'event':'push','attempt':1,'sha':self.head(),'run_id':'123'},'prepared':self.prepared,'head':self.head(),'plan_sha':digest(self.audit.raw(self.prepared,'readiness/executor-final-plan.json')),'manifest_sha':digest(self.audit.raw(self.prepared,self.plan['source_manifest'])),'marker_sha':self.marker_hash,'operation':'channel'}
    def test_real_full_history_marker_source_preflight(self):
        self.marker();proof=self.audit.before_credentials(**self.audit_args())
        self.assertTrue(proof['full_history']);self.assertTrue(proof['marker_exact']);self.assertFalse(proof['credential_permission'])
    def test_run_attempt_2_rejected(self):
        self.marker();args=self.audit_args();args['event']['attempt']=2
        with self.assertRaises(Stop):self.audit.before_credentials(**args)
    def test_head_mismatch_rejected(self):
        self.marker();args=self.audit_args();args['head']='0'*40
        with self.assertRaises(Stop):self.audit.before_credentials(**args)
    def test_marker_not_created_rejected(self):
        self.marker_hash='0'*64
        with self.assertRaises(Stop):self.audit.before_credentials(**self.audit_args())
    def test_marker_consumed_replay_extra_commit_rejected(self):
        self.marker();self.git('commit','--allow-empty','-q','-m','replay')
        with self.assertRaises(Stop):self.audit.before_credentials(**self.audit_args())
    def test_extra_marker_file_rejected(self):
        self.marker(extra='audit-evidence/consumed/unrelated.json')
        with self.assertRaises(Stop):self.audit.before_credentials(**self.audit_args())
    def test_source_manifest_hash_rejected(self):
        self.marker();args=self.audit_args();args['manifest_sha']='0'*64
        with self.assertRaises(Stop):self.audit.before_credentials(**args)
    def test_marker_source_hash_rejected(self):
        self.marker(modify=lambda m:m.update(executor_sha256='0'*64))
        with self.assertRaises(Stop):self.audit.before_credentials(**self.audit_args())
    def test_cross_operation_approval_rejected(self):
        self.marker(modify=lambda m:m.update(upload_approved=True))
        with self.assertRaises(Stop):self.audit.before_credentials(**self.audit_args())
    def test_shallow_history_rejected(self):
        self.marker();args=self.audit_args();clone=Path(self.tmp.name)/'clone'
        subprocess.check_call(['git','clone','--depth','1','-q',self.root.as_uri(),str(clone)],stderr=subprocess.DEVNULL)
        with self.assertRaises(Stop):ExecutorAudit(clone).before_credentials(**args)

class ExtraBoundaryTests(unittest.TestCase):
    def test_fake_live_mode_still_cannot_send(self):
        a=OfflineAuthority(PLAN);p=a.issue('channel',approved=True,marker_consumed=True);p.mode='LIVE_VERIFIED'
        f=FreshFixture()
        with self.assertRaises(Stop):ChannelExecutor(f).run(p)
        self.assertEqual(f.sends,[]);self.assertEqual(f.reads,[])
    def test_state_init_wrong_ack_permanent_stop(self):
        a=OfflineAuthority(PLAN);c=ChannelExecutor(FreshFixture()).run(a.issue('channel',approved=True,marker_consumed=True))
        p=a.issue('state_init',prerequisites=(c,),approved=True,marker_consumed=True)
        t=StateService(PLAN['operations']['state_init']['state_base_commit'])
        def wrong(method,path,body):
            status,d=t(method,path,body)
            if method=='PUT':d['content']['sha']='0'*40
            return status,d
        x=StateInitExecutor(FixtureFunction(wrong))
        with self.assertRaises(Stop):x.run(p)
        self.assertTrue(x.uncertain);self.assertEqual(t.file,initial_bytes())
        with self.assertRaises(Stop):x.request('GET',REF)
        self.assertEqual(len(t.calls),3)
    def test_native_transport_rejects_main_and_method_before_connection(self):
        # Exercise native policy using a fixture-injected object, not live issuance.
        x=object.__new__(StateInitHTTP);x._token='FIXTURE_TOKEN';x.connector=Mock();x.calls={'GET':0,'POST':0,'PUT':0};x.poisoned=False
        for method,path,body in [('DELETE',STATE,{}),('PUT',STATE,{'branch':'main','message':'x','content':'x'}),('GET',STATE+'?ref=main',None),('POST',REFS,{'ref':'refs/heads/main','sha':'a'*40})]:
            with self.assertRaises(Stop):x(method,path,body)
        x.connector.assert_not_called()
    def test_native_state_response_error_body_never_read(self):
        x=object.__new__(StateInitHTTP);x._token='FIXTURE_TOKEN';x.calls={'GET':0,'POST':0,'PUT':0};x.poisoned=False
        response=Mock();response.status=403;c=Mock();c.getresponse.return_value=response;x.connector=Mock(return_value=c)
        self.assertEqual(x('GET',REF),(403,{}));response.read.assert_not_called()
        with self.assertRaises(Stop):x('GET',REF)
        self.assertEqual(x.connector.call_count,1)
    def test_native_init_maximum_two_gets_no_redirect(self):
        x=object.__new__(StateInitHTTP);x._token='FIXTURE_TOKEN';x.calls={'GET':0,'POST':0,'PUT':0};x.poisoned=False
        response=Mock();response.status=200;response.read.return_value=b'{}';c=Mock();c.getresponse.return_value=response;x.connector=Mock(return_value=c)
        x('GET',REF);x('GET',STATE+'?ref='+GitContentsCAS.BRANCH)
        with self.assertRaises(Stop):x('GET',REF)
        self.assertEqual(x.connector.call_count,2)
    def test_provenance_exception_text_not_exposed(self):
        a=OfflineAuthority(PLAN);p=a.issue('channel',approved=True,marker_consumed=True)
        def get(path):raise TimeoutError('FIXTURE_SECRET_DO_NOT_LOG')
        e,_,_=expected_proof('private_upload');reader=RunProofAdapter(FixtureFunction(get),lambda:NOW)
        with self.assertRaises(Stop) as cm:reader.verify(e,phase='before_upload',permit=p)
        self.assertNotIn('FIXTURE_SECRET_DO_NOT_LOG',str(cm.exception))

if __name__=='__main__':unittest.main()
