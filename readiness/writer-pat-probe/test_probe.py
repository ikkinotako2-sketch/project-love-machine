import contextlib
import io
import unittest
from unittest.mock import patch
import probe

class Response:
    status = 200
    def read(self, *args):
        raise AssertionError('response body must not be read')

class Connection:
    calls = []
    status = 200
    fail = False
    def __init__(self, host, timeout):
        assert host == 'api.github.com' and timeout == 15
    def request(self, method, path, headers):
        self.calls.append((method, path, headers))
        if self.fail:
            raise TimeoutError('dummy-sensitive-error-never-output')
    def getresponse(self):
        r = Response()
        r.status = self.status
        return r
    def close(self):
        pass

class Tests(unittest.TestCase):
    def setUp(self):
        Connection.calls = []
        Connection.fail = False
        Connection.status = 200
        self.env = dict(GITHUB_REPOSITORY=probe.REPO,
                        GITHUB_REF='refs/heads/'+probe.BRANCH,
                        GITHUB_EVENT_NAME='push', GITHUB_RUN_ATTEMPT='1',
                        GITHUB_RUN_ID='123', GITHUB_SHA='a'*40,
                        TEST_ONLY='true', DRY_RUN='true', NO_PUBLISH='true',
                        EMERGENCY_STOP='true')
        self.event = dict(created=True, deleted=False, forced=False,
                          before='0'*40, after='a'*40)
    def test_success_one_get_no_body(self):
        r = probe.Once(Connection).status('DUMMY')
        self.assertEqual(r, dict(reason='SECRETS_READ_PASS', requests=1, http_status=200))
        self.assertEqual(Connection.calls[0][0], 'GET')
        self.assertEqual(Connection.calls[0][1], '/repos/'+probe.REPO+'/actions/secrets?per_page=1')
    def test_duplicate_refused(self):
        once = probe.Once(Connection)
        once.status('DUMMY')
        self.assertEqual(once.status('DUMMY')['reason'], 'ALREADY_USED_STOP')
        self.assertEqual(len(Connection.calls), 1)
    def test_timeout_no_retry(self):
        Connection.fail = True
        once = probe.Once(Connection)
        r = once.status('DUMMY')
        self.assertEqual(r['reason'], 'TRANSPORT_UNKNOWN_STOP')
        self.assertNotIn('dummy-sensitive', str(r))
        once.status('DUMMY')
        self.assertEqual(len(Connection.calls), 1)
    def test_redirect_not_followed(self):
        Connection.status = 302
        self.assertEqual(probe.Once(Connection).status('DUMMY')['reason'], 'HTTP_STOP')
        self.assertEqual(len(Connection.calls), 1)
    def test_http_failures(self):
        for status in (401,403,404,429,500):
            with self.subTest(status=status):
                Connection.status = status
                r = probe.Once(Connection).status('DUMMY')
                self.assertNotEqual(r['reason'], 'SECRETS_READ_PASS')
                self.assertEqual(r['http_status'], status)
    def test_absent_and_malformed_secret(self):
        for token in ('', 'DUMMY\nBAD', 'DUMMY\rBAD'):
            self.assertEqual(probe.Once(Connection).status(token)['requests'], 0)
        self.assertEqual(Connection.calls, [])
    def test_gate_pass(self):
        self.assertTrue(probe.gate(self.env, self.event))
    def test_gate_environment_mutations(self):
        for key in self.env:
            with self.subTest(key=key):
                e = dict(self.env, **{key:'INVALID'})
                self.assertFalse(probe.gate(e, self.event))
    def test_gate_event_mutations(self):
        for key, value in [('created',False),('deleted',True),('forced',True),
                           ('before','b'*40),('after','b'*40)]:
            self.assertFalse(probe.gate(self.env, dict(self.event, **{key:value})))
    def test_rerun_rejected(self):
        self.assertFalse(probe.gate(dict(self.env,GITHUB_RUN_ATTEMPT='2'), self.event))
    def test_history_valid(self):
        self.assertTrue(probe.history_ok(self.history(), self.env))
    def history(self):
        return dict(total_count=1, workflow_runs=[dict(id=123, run_attempt=1,
            head_sha='a'*40, head_branch=probe.BRANCH, event='push', path=probe.WORKFLOW)])
    def test_previous_run_refused(self):
        d = self.history(); d['total_count']=2
        self.assertFalse(probe.history_ok(d,self.env))
    def test_wrong_provenance_refused(self):
        for key in self.history()['workflow_runs'][0]:
            d = self.history(); d['workflow_runs'][0][key]='INVALID'
            self.assertFalse(probe.history_ok(d,self.env))
    def test_no_gate_no_secret_no_network(self):
        out = io.StringIO()
        with patch.dict(probe.os.environ, {'WRITER_PAT':'DUMMY'},clear=True), \
             patch.object(probe.sys,'argv',['probe.py','execute']), \
             patch.object(probe.http.client,'HTTPSConnection', side_effect=AssertionError), \
             contextlib.redirect_stdout(out):
            self.assertEqual(probe.main(),1)
        self.assertNotIn('DUMMY',out.getvalue())
    def test_workflow_only_writer_and_fixed_environment(self):
        text = (probe.ROOT/probe.WORKFLOW).read_text()
        self.assertEqual(text.count('secrets.'),1)
        self.assertIn('secrets.PLM_GITHUB_OAUTH_SECRET_WRITER', text)
        for forbidden in ('workflow_dispatch:', 'schedule:', 'PLM_YOUTUBE_GAME_001',
                          'HANDOFF', 'upload-artifact', 'curl ', 'continue-on-error'):
            self.assertNotIn(forbidden, text)
        self.assertIn('environment: plm-oauth-client-reuse-once',text)

if __name__ == '__main__':
    unittest.main()
