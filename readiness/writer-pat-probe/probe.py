"""Independent, read-only writer check. Never reads response bodies."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = 'ikkinotako2-sketch/project-love-machine'
BRANCH = 'plm-writer-pat-probe-20261028-r1'
BASE = 'e2b47c43163ea42a23044457c24c9347445b253d'
WORKFLOW = '.github/workflows/plm-writer-pat-probe-once.yml'
ROOT = Path(__file__).resolve().parents[2]
FILES = {WORKFLOW, 'readiness/writer-pat-probe/probe.py',
         'readiness/writer-pat-probe/test_probe.py', 'readiness/writer-pat-probe/manifest.json'}

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()

def gate(env, event):
    return (env.get('GITHUB_REPOSITORY') == REPO
            and env.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and env.get('GITHUB_EVENT_NAME') == 'push'
            and env.get('GITHUB_RUN_ATTEMPT') == '1'
            and env.get('GITHUB_RUN_ID', '').isdigit()
            and event.get('created') is True
            and event.get('deleted') is False
            and event.get('forced') is False
            and event.get('before') == '0' * 40
            and event.get('after') == env.get('GITHUB_SHA')
            and all(env.get(k) == 'true' for k in
                    ['TEST_ONLY', 'DRY_RUN', 'NO_PUBLISH', 'EMERGENCY_STOP']))

def history_ok(data, env):
    runs = data.get('workflow_runs', [])
    return (data.get('total_count') == 1 and len(runs) == 1
            and str(runs[0].get('id')) == env['GITHUB_RUN_ID']
            and runs[0].get('run_attempt') == 1
            and runs[0].get('head_sha') == env['GITHUB_SHA']
            and runs[0].get('head_branch') == BRANCH
            and runs[0].get('event') == 'push'
            and runs[0].get('path') == WORKFLOW)

class Once:
    def __init__(self, connection=http.client.HTTPSConnection):
        self.connection = connection
        self.used = False

    def status(self, token):
        if self.used:
            return {'reason': 'ALREADY_USED_STOP', 'requests': 0, 'http_status': None}
        self.used = True
        if not token or any(c in token for c in '\r\n'):
            return {'reason': 'TOKEN_INPUT_STOP', 'requests': 0, 'http_status': None}
        conn = None
        sent = 0
        try:
            conn = self.connection('api.github.com', timeout=15)
            sent = 1  # A send attempt is consumed even when its ACK is unknown.
            conn.request('GET', '/repos/' + REPO + '/actions/secrets?per_page=1',
                         headers={'Authorization': 'Bearer ' + token,
                                  'Accept': 'application/vnd.github+json',
                                  'X-GitHub-Api-Version': '2022-11-28',
                                  'User-Agent': 'PLM-writer-probe-once'})
            status = conn.getresponse().status
            reason = ('SECRETS_READ_PASS' if status == 200 else
                      'AUTH_REJECTED_STOP' if status == 401 else
                      'PERMISSION_OR_POLICY_STOP' if status in (403, 404) else
                      'HTTP_STOP')
            return {'reason': reason, 'requests': sent, 'http_status': status}
        except Exception:
            return {'reason': 'TRANSPORT_UNKNOWN_STOP', 'requests': sent, 'http_status': None}
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

def prepare():
    env = os.environ
    event = json.loads(Path(env['GITHUB_EVENT_PATH']).read_text())
    if not gate(env, event) or git('rev-parse', 'HEAD') != env['GITHUB_SHA']:
        raise ValueError('local')
    if git('rev-parse', 'HEAD^') != BASE:
        raise ValueError('parent')
    if set(git('diff', '--name-only', 'HEAD^', 'HEAD').splitlines()) != FILES:
        raise ValueError('diff')
    manifest = json.loads((ROOT / 'readiness/writer-pat-probe/manifest.json').read_text())
    if set(manifest) != FILES - {'readiness/writer-pat-probe/manifest.json'}:
        raise ValueError('manifest')
    for path, digest in manifest.items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest:
            raise ValueError('hash')
    # Separate ordinary GITHUB_TOKEN read, never the writer PAT; detects prior runs.
    token = env.pop('PROVENANCE_TOKEN')
    conn = http.client.HTTPSConnection('api.github.com', timeout=15)
    try:
        conn.request('GET', '/repos/' + REPO + '/actions/workflows/'
                     + WORKFLOW.rsplit('/', 1)[1] + '/runs?per_page=100',
                     headers={'Authorization': 'Bearer ' + token,
                              'Accept': 'application/vnd.github+json',
                              'User-Agent': 'PLM-writer-probe-provenance'})
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError('provenance')
        data = json.loads(response.read(1048576))
        if not history_ok(data, env):
            raise ValueError('previous')
    finally:
        conn.close()
    with open(env['GITHUB_OUTPUT'], 'a') as out:
        out.write('ready=true\n')
    print('LOCAL_GATE_PASS')

def main():
    try:
        if sys.argv[1:] == ['prepare']:
            prepare()
            return 0
        if sys.argv[1:] != ['execute'] or os.environ.get('LOCAL_READY') != 'true':
            print('LOCAL_GATE_STOP')
            return 1
        result = Once().status(os.environ.pop('WRITER_PAT', ''))
        # Only fixed reason, numeric status and count; no body/headers/secret names.
        print(json.dumps(result, sort_keys=True))
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as out:
            out.write(json.dumps(result, sort_keys=True) + '\nSecrets write: NOT_TESTED\n')
        return 0 if result['reason'] == 'SECRETS_READ_PASS' else 1
    except Exception:
        print('LOCAL_OR_PROVENANCE_UNKNOWN_STOP')
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
