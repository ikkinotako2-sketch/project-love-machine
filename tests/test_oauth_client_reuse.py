import contextlib,copy,io,json,unittest
from urllib.parse import parse_qs,urlsplit
from plm.automation.executors.oauth_reuse import *
from plm.automation.evidence_adapters import MemoryOAuthRefresh

CID='123456-fixture.apps.googleusercontent.com'
OLD=json.dumps({'client_id':CID,'client_secret':'FIXTURE_CLIENT_SECRET','refresh_token':'FIXTURE_OLD_REFRESH'})
NEW=json.dumps({'client_id':CID,'refresh_token':'FIXTURE_NEW_REFRESH'})
CTX=ConsentContext(CID,'s'*48,1000,1300)
class Fixture:
    offline_mock=True
    def __init__(self,fn):self.fn=fn;self.calls=[]
    def __call__(self,*args):self.calls.append(args);return self.fn(*args)
def response():return {'access_token':'FIXTURE_ACCESS','refresh_token':'FIXTURE_NEW_REFRESH','scope':' '.join(SCOPES),'token_type':'Bearer','expires_in':3600}

class ReuseTests(unittest.TestCase):
    def engine(self,payload=None,status=200):
        p=Fixture(lambda form:(status,response() if payload is None else payload))
        s=Fixture(lambda name,value:'CREATED')
        return CodeExchangeSimulation(p,s,lambda:1100),p,s
    def test_keep_existing_secret_exact(self):
        before=OLD;self.assertEqual(combine_bundle(OLD),json.loads(OLD));self.assertEqual(OLD,before)
    def test_new_refresh_only_preserves_client_secret(self):
        b=combine_bundle(OLD,NEW,use_candidate=True)
        self.assertEqual(b['client_secret'],'FIXTURE_CLIENT_SECRET');self.assertEqual(b['refresh_token'],'FIXTURE_NEW_REFRESH')
    def test_missing_candidate_no_old_fallback(self):
        with self.assertRaises(Stop):combine_bundle(OLD,None,use_candidate=True)
    def test_wrong_client_stops(self):
        with self.assertRaises(Stop):combine_bundle(OLD,json.dumps({'client_id':'99-other.apps.googleusercontent.com','refresh_token':'FIXTURE_NEW'}),use_candidate=True)
    def test_candidate_cannot_enable_itself(self):
        with self.assertRaises(Stop):combine_bundle(OLD,NEW)
    def test_duplicate_secret_field_stop(self):
        raw=OLD[:-1]+',"client_secret":"FIXTURE_ATTACK"}'
        with self.assertRaises(Stop):combine_bundle(raw)
    def test_bad_json_fixed_error_no_secret_value(self):
        with self.assertRaises(Stop) as cm:combine_bundle('FIXTURE_PRIVATE_BODY')
        self.assertEqual(str(cm.exception),'CREDENTIAL_JSON_SHAPE_STOP')
    def test_authorization_url_no_client_secret_or_token(self):
        u=authorization_url(CTX);q=parse_qs(urlsplit(u).query)
        self.assertEqual(set(q['scope'][0].split()),set(SCOPES));self.assertEqual(q['access_type'],['offline'])
        self.assertFalse({'client_secret','code','refresh_token','access_token'}&set(q))
    def test_real_adapter_cannot_execute(self):
        with self.assertRaises(Stop):CodeExchangeSimulation(lambda _:None,lambda *_:None,lambda:1100)
    def test_current_production_entry_parked(self):
        self.assertEqual(production_entry()['oauth_requests'],0);self.assertFalse(production_entry()['identity_consumed'])
    def test_exchange_exact_protocol_only_new_secret_saved(self):
        e,p,s=self.engine();r=e.run(OLD,'FIXTURE_AUTH_CODE',CTX.state,CTX)
        fields=parse_qs(p.calls[0][0].decode());self.assertEqual(fields['grant_type'],['authorization_code']);self.assertEqual(fields['client_secret'],['FIXTURE_CLIENT_SECRET'])
        self.assertEqual(s.calls[0][0],CANDIDATE);self.assertNotEqual(s.calls[0][0],EXISTING)
        self.assertEqual(set(json.loads(s.calls[0][1])),{'client_id','refresh_token'})
        self.assertEqual(r['channel_match'],'UNVERIFIED');self.assertEqual(r['basis'],'OFFLINE_CONTRACT')
    def test_state_mismatch_remote_zero(self):
        e,p,s=self.engine()
        with self.assertRaises(Stop):e.run(OLD,'FIXTURE_AUTH_CODE','wrong',CTX)
        self.assertEqual(p.calls,[]);self.assertEqual(s.calls,[])
    def test_local_window_expired_remote_zero(self):
        e,p,s=self.engine();e.clock=lambda:1300
        with self.assertRaises(Stop):e.run(OLD,'FIXTURE_AUTH_CODE',CTX.state,CTX)
        self.assertEqual(p.calls,[])
    def test_client_mismatch_before_exchange(self):
        e,p,s=self.engine();ctx=ConsentContext('99-other.apps.googleusercontent.com',CTX.state,1000,1300)
        with self.assertRaises(Stop):e.run(OLD,'FIXTURE_AUTH_CODE',CTX.state,ctx)
        self.assertEqual(p.calls,[])
    def test_http_error_or_redirect_no_save_retry(self):
        for status in (400,401,403,302):
            e,p,s=self.engine(status=status)
            with self.assertRaises(Stop):e.run(OLD,'FIXTURE_AUTH_CODE',CTX.state,CTX)
            with self.assertRaises(Stop):e.run(OLD,'FIXTURE_AUTH_CODE',CTX.state,CTX)
            self.assertEqual(len(p.calls),1);self.assertEqual(s.calls,[])
    def test_timeout_never_repeated_no_error_body(self):
        e,p,s=self.engine();p.fn=lambda _ :(_ for _ in ()).throw(TimeoutError('FIXTURE_RAW_PRIVATE_ERROR'))
        with self.assertRaises(Stop) as cm:e.run(OLD,'FIXTURE_AUTH_CODE',CTX.state,CTX)
        self.assertNotIn('PRIVATE',str(cm.exception))
        with self.assertRaises(Stop):e.run(OLD,'FIXTURE_AUTH_CODE',CTX.state,CTX)
        self.assertEqual(len(p.calls),1)
    def test_refresh_absent_never_reuses_old(self):
        r=response();r.pop('refresh_token');e,p,s=self.engine(r)
        with self.assertRaises(Stop):e.run(OLD,'FIXTURE_AUTH_CODE',CTX.state,CTX)
        self.assertEqual(s.calls,[])
    def test_scope_missing_unknown_not_insufficient(self):
        r=response();r.pop('scope');e,p,s=self.engine(r)
        with self.assertRaises(Stop) as cm:e.run(OLD,'FIXTURE_AUTH_CODE',CTX.state,CTX)
        self.assertEqual(str(cm.exception),'GRANTED_SCOPE_UNKNOWN_STOP');self.assertEqual(s.calls,[])
    def test_scope_insufficient_never_saved(self):
        r=response();r['scope']=SCOPES[0];e,p,s=self.engine(r)
        with self.assertRaises(Stop):e.run(OLD,'FIXTURE_AUTH_CODE',CTX.state,CTX)
        self.assertEqual(s.calls,[])
    def test_write_unknown_no_second_save_or_exchange(self):
        e,p,s=self.engine();s.fn=lambda *_:(_ for _ in ()).throw(TimeoutError())
        with self.assertRaises(Stop):e.run(OLD,'FIXTURE_AUTH_CODE',CTX.state,CTX)
        with self.assertRaises(Stop):e.run(OLD,'FIXTURE_AUTH_CODE',CTX.state,CTX)
        self.assertEqual((len(p.calls),len(s.calls)),(1,1))
    def test_existing_provider_reused_with_candidate_in_memory(self):
        b=combine_bundle(OLD,NEW,use_candidate=True);seen=[]
        def send(form):seen.append(parse_qs(form.decode()));r=response();r.pop('refresh_token');return 200,r
        p=MemoryOAuthRefresh(b,send,lambda:1000,approved=True)
        out=p();self.assertEqual(seen[0]['refresh_token'],['FIXTURE_NEW_REFRESH']);self.assertTrue(out['scope_proven']);self.assertIsNone(p.bundle)
        with self.assertRaises(Stop):p()
    def test_stdout_repr_no_credentials(self):
        e,p,s=self.engine();buf=io.StringIO()
        with contextlib.redirect_stdout(buf):r=e.run(OLD,'FIXTURE_AUTH_CODE',CTX.state,CTX)
        evidence=json.dumps(r)+repr(e)+repr(CTX)+buf.getvalue()
        for value in ('FIXTURE_CLIENT_SECRET','FIXTURE_OLD_REFRESH','FIXTURE_NEW_REFRESH','FIXTURE_ACCESS','FIXTURE_AUTH_CODE'):self.assertNotIn(value,evidence)

if __name__=='__main__':unittest.main()
