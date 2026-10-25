import base64,copy,contextlib,hashlib,io,json,os,re,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from plm.automation.executors import oauth_exchange_r2 as x
from plm.automation.executors.oauth_handoff_r2 import parse_handoff
from plm.automation.ledger import Stop
from tests.test_oauth_client_reuse import CID,OLD,Fixture,response
from tests.test_oauth_exchange import Encryptor

ROOT=Path(__file__).resolve().parents[1]
PLAN=json.loads((ROOT/x.PLAN).read_text())
R1='audit-evidence/consumed/provider-neutral-youtube-client-reuse-exchange-20261015-r1.json'
R1_HASH='b836f8d0ac4f20cdf7fe1a42bebdae9978139798ae37e7dfcd0182b0f4d348d8'

def dummy(code='FIXTURE_CODE'):
    # Executes actual HTML handler and owner pasteback in Node VM; not compose-only.
    return subprocess.check_output(['node','tests/oauth_handoff_r2_dom.cjs',code],cwd=ROOT,text=True)

class R2Tests(unittest.TestCase):
    def engine(self,raw=None,status=200,ack=201,payload=None):
        raw=dummy() if raw is None else raw
        p=copy.deepcopy(PLAN);p.update(client_id='123-fixture.apps.googleusercontent.com',consent_state='D'*43)
        replies=iter([(404,{}),(200,{'key_id':'fixture','key':base64.b64encode(b'p'*32).decode()}),(ack,{})])
        writer=Fixture(lambda *a:next(replies));post=Fixture(lambda *a:(status,response() if payload is None else payload))
        engine=x.ExchangeExecutor(x.Permit(p,'OFFLINE_CONTRACT',x._SEAL),post,x.SecretWriter(writer,Encryptor()),lambda:1792843210)
        old=json.loads(OLD);old['client_id']=p['client_id'];old=json.dumps(old)
        return engine,writer,post,lambda n:old if n==x.EXISTING else raw

    def test_actual_html_copy_environment_string_runner_exchange(self):
        e,w,p,load=self.engine();before=load(x.EXISTING);result=e.run(load)
        self.assertTrue(result['candidate_saved']);self.assertEqual((len(w.calls),len(p.calls)),(3,1))
        self.assertEqual(before,load(x.EXISTING));self.assertEqual(result['channel_match'],'UNVERIFIED')

    def test_escaping_roundtrip(self):
        for code in ['FIXTURE_"\\/+=%&','FIXTURE_PERCENT%20PLUS+','FIXTURE_!~{}[]:;']:
            with self.subTest():self.assertEqual(parse_handoff(dummy(code))['code'],code)

    def test_json_whitespace_crlf_and_utf8_bytes(self):
        d=json.loads(dummy());raw=' \r\n'+json.dumps(d,indent=2).replace('\n','\r\n')+'\r\n'
        self.assertEqual(parse_handoff(raw),d);self.assertEqual(parse_handoff(raw.encode().decode('utf-8')),d)

    def test_ascii_unicode_escapes(self):
        raw=dummy().replace('FIXTURE_CODE',r'FIXTURE_\u0043ODE');self.assertEqual(parse_handoff(raw)['code'],'FIXTURE_CODE')

    def test_malformed_json_rejected_without_remote(self):
        raw=dummy()
        for value in [raw[1:],raw[:-1],raw+',', 'https://example.invalid/?code=FIXTURE', 'FIXTURE_CODE',"{'code':'FIXTURE'}",'\ufeff'+raw]:
            with self.subTest():
                e,w,p,load=self.engine(value)
                with self.assertRaises(Stop) as cm:e.run(load)
                self.assertEqual(str(cm.exception),'HANDOFF_JSON_SYNTAX_STOP');self.assertEqual((w.calls,p.calls),([],[]))

    def test_duplicate_key_not_swallowed_as_syntax(self):
        raw=dummy();raw=raw[:-1]+',"code":"SECOND_FIXTURE"}'
        with self.assertRaises(Stop) as cm:parse_handoff(raw)
        self.assertEqual(str(cm.exception),'HANDOFF_DUPLICATE_KEY_STOP')

    def test_missing_extra_and_double_encoded_rejected(self):
        d=json.loads(dummy())
        for value in [json.dumps({k:v for k,v in d.items() if k!='code'}),json.dumps({**d,'extra':'FIXTURE'}),json.dumps(dummy()),'[]','null']:
            with self.subTest(),self.assertRaises(Stop):parse_handoff(value)

    def test_time_types_rejected(self):
        d=json.loads(dummy())
        for issued in [True,'1792843200',1792843200.0,None,-1,0]:
            with self.subTest(),self.assertRaises(Stop) as cm:parse_handoff(json.dumps({**d,'issued_at':issued}))
            self.assertEqual(str(cm.exception),'HANDOFF_TIME_TYPE_STOP')

    def test_nan_infinity_invalid_encoding_size(self):
        for raw in ['{"issued_at":NaN}','{"issued_at":Infinity}','\ud800','x'*65537]:
            with self.subTest(),self.assertRaises(Stop):parse_handoff(raw)

    def test_control_or_unicode_credential_rejected(self):
        for code in ['FIXTURE\nCODE','FIXTURE\x00CODE','ダミー']:
            d=json.loads(dummy());d['code']=code
            with self.subTest(),self.assertRaises(Stop):parse_handoff(json.dumps(d))

    def test_no_secret_or_empty_stops_zero_requests(self):
        for missing in [x.EXISTING,x.HANDOFF]:
            e,w,p,load=self.engine()
            with self.assertRaises(Stop):e.run(lambda n:None if n==missing else load(n))
            self.assertEqual((w.calls,p.calls),([],[]))

    def test_wrong_client_redirect_state_stop(self):
        for key,value in [('client_id',CID),('redirect_uri','https://example.invalid/'),('state','WRONG_FIXTURE')]:
            d=json.loads(dummy());d[key]=value;e,w,p,load=self.engine(json.dumps(d))
            with self.subTest(),self.assertRaises(Stop):e.run(load)
            self.assertEqual((w.calls,p.calls),([],[]))

    def test_expiry_and_future_receipt_zero_requests(self):
        for now in [1792843500,1792843501,1792843199]:
            e,w,p,load=self.engine();e.clock=lambda:now
            with self.subTest(),self.assertRaises(Stop) as cm:e.run(load)
            self.assertEqual(str(cm.exception),'HANDOFF_LOCAL_WINDOW_STOP');self.assertEqual((w.calls,p.calls),([],[]))

    def test_deadline_rechecked_after_preflight(self):
        e,w,p,load=self.engine();now=[1792843210];e.clock=lambda:now[0];pre=e.writer.preflight
        def delayed():pre();now[0]=1792843500
        e.writer.preflight=delayed
        with self.assertRaises(Stop):e.run(load)
        self.assertEqual(len(w.calls),2);self.assertEqual(p.calls,[]);self.assertFalse(e.write_attempted)

    def test_missing_or_insufficient_scope_never_saves(self):
        for scope in [None,x.SCOPES[0]]:
            payload=response()
            if scope is None:payload.pop('scope')
            else:payload['scope']=scope
            e,w,p,load=self.engine(payload=payload)
            with self.subTest(),self.assertRaises(Stop):e.run(load)
            self.assertEqual((len(w.calls),len(p.calls)),(2,1))

    def test_google_error_no_retry(self):
        e,w,p,load=self.engine(status=400)
        with self.assertRaises(Stop):e.run(load)
        with self.assertRaises(Stop):e.run(load)
        self.assertEqual((len(w.calls),len(p.calls)),(2,1))

    def test_google_unknown_no_retry(self):
        e,w,p,load=self.engine();p.fn=lambda *a:(_ for _ in ()).throw(TimeoutError('PRIVATE_FIXTURE'))
        with self.assertRaises(Stop):e.run(load)
        with self.assertRaises(Stop):e.run(load)
        self.assertEqual((len(w.calls),len(p.calls)),(2,1))

    def test_candidate_exists_or_denied_no_oauth(self):
        for status in [200,403,500]:
            e,w,p,load=self.engine();w.fn=lambda *a:(status,{})
            with self.subTest(),self.assertRaises(Stop):e.run(load)
            self.assertEqual((len(w.calls),len(p.calls)),(1,0))

    def test_put_only_201_and_unknown_is_terminal(self):
        for ack in [204,403,500]:
            e,w,p,load=self.engine(ack=ack)
            with self.subTest(),self.assertRaises(Stop):e.run(load)
            with self.assertRaises(Stop):e.run(load)
            self.assertEqual((len(w.calls),len(p.calls)),(3,1))

    def test_secret_and_error_text_not_logged(self):
        e,w,p,load=self.engine('PRIVATE_INPUT_NOT_JSON');out=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(out):
            with self.assertRaises(Stop) as cm:e.run(load)
        self.assertEqual(out.getvalue(),'');self.assertEqual(str(cm.exception),'HANDOFF_JSON_SYNTAX_STOP')

    def test_parked_entry_even_with_secret_values(self):
        with patch.dict(os.environ,{x.EXISTING:'PRIVATE_FIXTURE',x.HANDOFF:'PRIVATE_FIXTURE',x.WRITER:'PRIVATE_FIXTURE'}):
            result=subprocess.check_output(['python','-m','plm.automation.executors.oauth_exchange_r2','--execute'],cwd=ROOT,text=True)
        self.assertNotIn('PRIVATE_FIXTURE',result);r=json.loads(result)
        self.assertEqual((r['status'],r['credentials_read'],r['oauth_POST'],r['secret_PUT']),('PARKED',0,0,0))

    def test_r1_evidence_and_r2_identity_separation(self):
        self.assertEqual(hashlib.sha256((ROOT/R1).read_bytes()).hexdigest(),R1_HASH)
        self.assertFalse((ROOT/PLAN['marker_path']).exists());self.assertNotIn('20261015-r1',PLAN['identity'])
        self.assertEqual(PLAN['historical_consumed_markers'],{R1:R1_HASH})
        self.assertNotEqual(x.HANDOFF,'PLM_YOUTUBE_REAUTH_HANDOFF_ONCE');self.assertIs(PLAN['enabled'],PLAN['release_configured'])

    def test_marker_workflow_cannot_start_or_load_secrets(self):
        w=(ROOT/PLAN['workflow_path']).read_text();self.assertIn("github.event_name == 'push'",w);self.assertIn('paths: ['+PLAN['marker_path']+']',w)
        if not PLAN['enabled']:self.assertIn('${{ false &&',w)
        self.assertNotIn('workflow_dispatch',w);self.assertNotIn('schedule:',w)
        self.assertIn('github.run_attempt == 1',w);self.assertIn('persist-credentials: false',w)
        self.assertLess(w.index('--prepare'),w.index('secrets.'))
        for k in x.SAFE:self.assertIn(k+": 'true'",w)

    def test_release_configuration_is_not_execution_approval(self):
        self.assertTrue(PLAN['enabled']);self.assertTrue(PLAN['release_configured'])
        self.assertFalse((ROOT/PLAN['marker_path']).exists())
        self.assertIsNone(x.local_gate(ROOT,{}))
        for key in ['owner_approved','handoff_approved','operational_exclusion_attested','writer_permissions_reviewed']:
            self.assertIs(PLAN[key],False)

    def test_unused_state_matches_actual_helper_and_retires_prior_consent(self):
        html=(ROOT/PLAN['local_handoff_helper']['entry']).read_text()
        config=json.loads(re.search(r'const CONFIG=(.*?);',html).group(1))
        self.assertEqual(config['state'],PLAN['consent_state'])
        self.assertEqual(config['client_id'],PLAN['client_id'])
        self.assertEqual(config['redirect_uri'],PLAN['redirect_uri'])
        self.assertEqual(len(base64.urlsafe_b64decode(config['state']+'=')),32)
        self.assertIs(PLAN['consent_state_used'],False)
        retired=PLAN['superseded_consent_contexts']
        self.assertTrue(retired)
        self.assertNotIn(hashlib.sha256(config['state'].encode()).hexdigest(),[v['state_sha256'] for v in retired])
        self.assertTrue(all(v['state_reuse_forbidden'] and not v['marker_created'] and not v['oauth_post_attempted'] for v in retired))

    def test_plan_cannot_claim_separate_execution_approval(self):
        for key in ['owner_approved','handoff_approved','operational_exclusion_attested','writer_permissions_reviewed']:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                p=copy.deepcopy(PLAN);p[key]=True;f=Path(tmp)/x.PLAN;f.parent.mkdir(parents=True);f.write_text(json.dumps(p))
                with patch.object(x,'GitAudit') as git,self.assertRaises(Stop) as cm:x.local_gate(tmp,{})
                self.assertEqual(str(cm.exception),'RELEASE_APPROVAL_IN_PLAN_STOP');git.assert_not_called()

    def test_old_secret_other_repo_and_redirect_forbidden(self):
        p=copy.deepcopy(PLAN);permit=x.Permit(p,'LIVE_REVIEWED',x._SEAL);connect=Mock()
        client=x.FixedHTTP(permit,'github','FIXTURE_WRITER',connector=connect)
        for verb,path in [('PUT',x.PREFIX+x.EXISTING),('DELETE',x.PREFIX+x.CANDIDATE),('GET','/repos/other/repo/actions/secrets/public-key')]:
            with self.subTest(),self.assertRaises(Stop):client(verb,path,{})
        connect.assert_not_called()

class R2HistoryTests(unittest.TestCase):
    def fixture(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);root=Path(t.name)
        def git(*a):return subprocess.check_output(['git','-C',str(root),*a],stderr=subprocess.DEVNULL).decode().strip()
        git('init');git('config','user.email','fixture@example.invalid');git('config','user.name','Offline fixture')
        historical=root/R1;historical.parent.mkdir(parents=True);historical.write_text('fixture consumed evidence')
        git('add','.');git('commit','-m','historical fixture');parent=git('rev-parse','HEAD')
        p=copy.deepcopy(PLAN);p.update(enabled=True,release_configured=True,preparation_parent=parent,historical_consumed_markers={R1:x.sha(historical.read_bytes())})
        files=sorted([x.PLAN,x.MANIFEST,p['workflow_path'],p['executor_path'],p['schema_path']]);p['preparation_files']=files
        for f in files:(root/f).parent.mkdir(parents=True,exist_ok=True);(root/f).write_text('fixture')
        (root/x.PLAN).write_text(json.dumps(p));(root/x.MANIFEST).write_text(json.dumps({'source_sha256':{f:x.sha((root/f).read_bytes()) for f in files if f!=x.MANIFEST}}))
        git('add','.');git('commit','-m','fixture preparation');prepared=git('rev-parse','HEAD')
        pins={'prepared':prepared,'plan_sha':x.sha((root/x.PLAN).read_bytes()),'manifest_sha':x.sha((root/x.MANIFEST).read_bytes())}
        marker={'identity':p['identity'],'state':'CONSUMED_BEFORE_REMOTE','approved':True,'prepared_commit_sha':prepared,'plan_sha256':pins['plan_sha'],'manifest_sha256':pins['manifest_sha'],'workflow_sha256':x.sha((root/p['workflow_path']).read_bytes()),'executor_sha256':x.sha((root/p['executor_path']).read_bytes()),'schema_sha256':x.sha((root/p['schema_path']).read_bytes()),'execution_approval':{k:True for k in ('owner_approved','operational_exclusion_attested','writer_permissions_reviewed','handoff_approved')}}
        target=root/p['marker_path'];target.write_text(json.dumps(marker));git('add','.');git('commit','-m',p['marker_message']);head=git('rev-parse','HEAD')
        env={'GITHUB_REPOSITORY':x.REPO,'GITHUB_REF':'refs/heads/'+p['branch'],'GITHUB_EVENT_NAME':'push','GITHUB_RUN_ATTEMPT':'1','GITHUB_SHA':head,'GITHUB_RUN_ID':'123',**x.SAFE}
        return root,git,p,env,pins

    def test_full_history_exact_marker_chain(self):
        root,git,p,env,pins=self.fixture();self.assertEqual(x.local_gate(root,env,**pins).mode,'LIVE_REVIEWED')

    def test_attempt_two_wrong_head_branch_or_repo(self):
        root,git,p,env,pins=self.fixture()
        for change in [{'GITHUB_RUN_ATTEMPT':'2'},{'GITHUB_SHA':'0'*40},{'GITHUB_REF':'refs/heads/main'},{'GITHUB_REPOSITORY':'other/repo'}]:
            with self.subTest(),self.assertRaises(Stop):x.local_gate(root,{**env,**change},**pins)

    def test_source_hash_mismatch(self):
        root,git,p,env,pins=self.fixture()
        for key in ['plan_sha','manifest_sha']:
            with self.subTest(),self.assertRaises(Stop):x.local_gate(root,env,**{**pins,key:'0'*64})

    def test_dirty_or_second_marker_commit_stop(self):
        root,git,p,env,pins=self.fixture();(root/'extra').write_text('fixture')
        with self.assertRaises(Stop):x.local_gate(root,env,**pins)
        git('add','.');git('commit','-m','second commit');env['GITHUB_SHA']=git('rev-parse','HEAD')
        with self.assertRaises(Stop):x.local_gate(root,env,**pins)

    def test_historical_marker_modification_stop(self):
        root,git,p,env,pins=self.fixture();(root/R1).write_text('modified')
        with self.assertRaises(Stop):x.local_gate(root,env,**pins)

    def test_prepared_without_r2_marker_no_permit(self):
        root,git,p,env,pins=self.fixture();git('reset','--hard',pins['prepared']);env['GITHUB_SHA']=pins['prepared']
        self.assertIsNone(x.local_gate(root,env,**pins))

    def test_marker_consumed_even_post_zero(self):
        root,git,p,env,pins=self.fixture();permit=x.local_gate(root,env,**pins);permit.mode='OFFLINE_CONTRACT'
        e,w,post,load=R2Tests().engine('NOT_JSON_FIXTURE');e.permit=permit;before=(root/p['marker_path']).read_bytes()
        with self.assertRaises(Stop):e.run(load)
        with self.assertRaises(Stop):e.run(load)
        self.assertTrue(permit.used);self.assertEqual((w.calls,post.calls),([],[]));self.assertEqual((root/p['marker_path']).read_bytes(),before)
