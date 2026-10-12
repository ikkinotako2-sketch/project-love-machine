import contextlib
import hashlib
import io
import json
import pathlib
import unittest
from unittest.mock import patch
from urllib.request import Request
from readiness import youtube_oauth_verify as w

BUNDLE = json.dumps({"client_id": "fixture-client", "client_secret": "FIXTURE_PRIVATE_SECRET", "refresh_token": "FIXTURE_PRIVATE_REFRESH"})
GOOD = json.dumps({"access_token": "FIXTURE_PRIVATE_ACCESS", "expires_in": 3600, "token_type": "Bearer"}).encode()

class Tests(unittest.TestCase):
    def run_verify(self, status=200, raw=GOOD, bundle=BUNDLE):
        calls=[]
        def transport(form):
            calls.append(form)
            return status, raw
        result=w.verify(bundle, transport)
        return result, calls
    def test_pass(self):
        r,c=self.run_verify();self.assertEqual(r["classification"],"OAUTH_REFRESH_AUTH_CONFIRMED_STOP_BEFORE_YOUTUBE");self.assertEqual(len(c),1)
    def test_missing_secret(self):
        r,c=self.run_verify(bundle="");self.assertEqual(len(c),0)
    def test_bad_bundle(self):
        for b in ["{", "[]", "{}", json.dumps({"client_id": 1})]:
            with self.subTest(b=b):self.assertEqual(self.run_verify(bundle=b)[1],[])
    def test_http_rejected(self):
        for status in [301,302,307,308,400,401,403,429,500,503]:
            with self.subTest(status=status):
                r,c=self.run_verify(status,b"PRIVATE_REMOTE_ERROR");self.assertEqual(r["reason_code"],"OAUTH_HTTP_STOP");self.assertEqual(len(c),1);self.assertEqual(r["http_status"],status)
    def test_timeout(self):
        def f(_):raise TimeoutError("PRIVATE_TOKEN")
        r=w.verify(BUNDLE,f);self.assertEqual(r["refresh_posts"],1);self.assertEqual(r["reason_code"],"OAUTH_TRANSPORT_OR_PROVIDER_UNKNOWN_STOP")
    def test_no_raw_error(self):
        r,_=self.run_verify(403,b"PRIVATE_REMOTE_ERROR");self.assertNotIn("PRIVATE",json.dumps(r))
    def test_secrets_not_output(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(out):r,_=self.run_verify()
        self.assertEqual(out.getvalue(),"");self.assertNotIn("PRIVATE",json.dumps(r))
    def test_response_shape(self):
        for raw in [b"bad",b"[]",b"{}",b"null"]:
            with self.subTest(raw=raw):self.assertNotEqual(self.run_verify(raw=raw)[0]["classification"],"OAUTH_REFRESH_AUTH_CONFIRMED_STOP_BEFORE_YOUTUBE")
    def test_expiry_shape(self):
        for expiry in [0,-1,True,"3600",1.5,86401,None]:
            with self.subTest(expiry=expiry):self.assertEqual(self.run_verify(raw=json.dumps({"access_token":"a","expires_in":expiry}).encode())[0]["reason_code"],"OAUTH_EXPIRY_STOP")
    def test_token_type(self):
        self.assertEqual(self.run_verify(raw=json.dumps({"access_token":"a","expires_in":1,"token_type":"Other"}).encode())[0]["reason_code"],"OAUTH_TOKEN_TYPE_STOP")
    def test_token_missing(self):
        for token in ["",None,True,"x\n"]:
            with self.subTest(token=token):self.assertEqual(self.run_verify(raw=json.dumps({"access_token":token,"expires_in":1}).encode())[0]["reason_code"],"OAUTH_TOKEN_SHAPE_STOP")
    def test_response_bound(self):self.assertEqual(self.run_verify(raw=b"x"*(w.LIMIT+1))[0]["reason_code"],"RESPONSE_BOUND_STOP")
    def test_second_post_rejected(self):
        opener=w.BoundedOpener(lambda _: (200,GOOD));req=Request(w.URL,data=b"client_id=a&client_secret=b&refresh_token=c&grant_type=refresh_token",method="POST")
        opener(req,30)
        with self.assertRaises(w.Stop):opener(req,30)
    def test_get_forbidden(self):
        with self.assertRaises(w.Stop):w.BoundedOpener(lambda _: (200,GOOD))(Request(w.URL),30)
    def test_other_endpoint_forbidden(self):
        with self.assertRaises(w.Stop):w.BoundedOpener(lambda _: (200,GOOD))(Request("https://www.googleapis.com/upload",data=b"a",method="POST"),30)
    def test_no_ambient_secret(self):
        self.assertEqual(w.BundleProvider({"client_id":"a"},None).env_name,"NO_AMBIENT_SECRET")
    def test_main_parked(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):w.main()
        self.assertEqual(json.loads(out.getvalue())["refresh_posts"],0)
    def test_zero_side_effects(self):
        r,_=self.run_verify()
        for k in ["retry","redirect","fallback","raw_retention","uploads","publishes","secret_exposure"]:self.assertEqual(r[k],0)
    def test_provider_hash_pinned(self):
        root=pathlib.Path(__file__).resolve().parents[1];plan=json.loads((root/"readiness/youtube-oauth-verify-plan.json").read_text())
        self.assertEqual(hashlib.sha256((root/plan["provider_path"]).read_bytes()).hexdigest(),plan["provider_sha256"])
    def test_legacy_provider_reused(self):self.assertTrue(issubclass(w.BundleProvider,w.EnvironmentOAuthTokenProvider))
    def test_missing_token_type(self):
        r,_=self.run_verify(raw=b'{"access_token":"a","expires_in":3600}')
        self.assertEqual(r["reason_code"],"OAUTH_TOKEN_TYPE_STOP")
    def test_malicious_stop_not_output(self):
        def f(_):raise w.Stop("SECRET_PRIVATE_ARBITRARY_REMOTE_TEXT")
        r=w.verify(BUNDLE,f);self.assertEqual(r["reason_code"],"OAUTH_TRANSPORT_OR_PROVIDER_UNKNOWN_STOP");self.assertNotIn("PRIVATE",json.dumps(r))
    def test_duplicate_response_keys(self):
        r,_=self.run_verify(raw=b'{"access_token":"a","access_token":"b","expires_in":3600,"token_type":"Bearer"}')
        self.assertEqual(r["reason_code"],"OAUTH_RESPONSE_SHAPE_STOP")
    def test_duplicate_credential_keys(self):
        r,c=self.run_verify(bundle='{"client_id":"a","client_id":"b","client_secret":"c","refresh_token":"d"}')
        self.assertEqual(c,[]);self.assertEqual(r["reason_code"],"OAUTH_CREDENTIAL_SHAPE_STOP")
    def fake_http(self,status=200,raw=GOOD,release_socket=False):
        class Sock:
            def settimeout(self,x):self.timeout=x
        sock=Sock()
        class Response:
            def __init__(self):
                self.status=status;self.buf=io.BytesIO(raw);self.reads=0
                self.fp=type('FP',(),{'raw':type('Raw',(),{'_sock':sock})()})()
            def read1(self,n):self.reads+=1;return self.buf.read(n)
        response=Response()
        class Connection:
            def __init__(self,*args,**kwargs):self.sock=sock;self.requests=[];self.closed=False
            def connect(self):pass
            def request(self,*args,**kwargs):self.requests.append((args,kwargs))
            def getresponse(self):
                if release_socket:self.sock=None
                return response
            def close(self):self.closed=True
        conn=Connection()
        return conn,response
    def test_real_transport_non200_never_reads_body(self):
        for status in [302,401,403,500]:
            with self.subTest(status=status):
                conn,response=self.fake_http(status,b'PRIVATE_REMOTE_ERROR')
                with patch('http.client.HTTPSConnection',return_value=conn):r=w.authorized_https_transport(b'approved-fixture')
                self.assertEqual(r,(status,b''));self.assertEqual(response.reads,0);self.assertEqual(len(conn.requests),1);self.assertTrue(conn.closed)
    def test_real_transport_no_redirect_one_post(self):
        conn,response=self.fake_http(302)
        with patch('http.client.HTTPSConnection',return_value=conn) as factory:w.authorized_https_transport(b'fixture')
        self.assertEqual(factory.call_args.args,('oauth2.googleapis.com',));self.assertEqual(conn.requests[0][0],('POST','/token'));self.assertEqual(len(conn.requests),1)
    def test_real_transport_deadline_before_post(self):
        conn,response=self.fake_http()
        with patch('http.client.HTTPSConnection',return_value=conn),patch.object(w.time,'monotonic',side_effect=[0,31]):
            with self.assertRaises(w.Stop):w.authorized_https_transport(b'fixture')
        self.assertEqual(conn.requests,[]);self.assertTrue(conn.closed)
    def test_real_transport_response_socket_fallback(self):
        conn,response=self.fake_http(release_socket=True)
        with patch('http.client.HTTPSConnection',return_value=conn):r=w.authorized_https_transport(b'fixture')
        self.assertEqual(r,(200,GOOD));self.assertEqual(len(conn.requests),1)

if __name__ == "__main__":unittest.main()
