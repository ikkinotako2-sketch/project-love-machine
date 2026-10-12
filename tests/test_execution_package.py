import copy,hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from plm.automation.execution_gate import (GitAudit,Stop,MARKER_KEYS,digest,
    preparation_paths,load_pinned_plan,local_event_gate,credential_boundary,
    historical_gate,validate_receipt)
ROOT=Path(__file__).resolve().parents[1]
PLAN=json.loads((ROOT/'readiness/execution-package-plan.json').read_bytes())

def raw(value):return (json.dumps(value,sort_keys=True)+'\n').encode()

def plan_gate(value):
    data=raw(value);return load_pinned_plan(data,digest(data))

class PlanTests(unittest.TestCase):
    def test_frozen_plan_safe(self):
        self.assertEqual(len(plan_gate(PLAN)['operations']),8)
    def test_plan_hash_substitution_rejected(self):
        with self.assertRaises(Stop):load_pinned_plan(raw(PLAN),'0'*64)
    def test_protected_channel_reuse(self):
        p=copy.deepcopy(PLAN);p['operations']['channel']['identity']=p['protected_unconsumed_identity']
        with self.assertRaises(Stop):plan_gate(p)
    def test_consumed_oauth_reuse(self):
        for identity in ('provider-neutral-youtube-oauth-verify-20261012-r1',
                         'provider-neutral-youtube-oauth-verify-20261012-r2',
                         'provider-neutral-youtube-oauth-scope-diagnostic-20261012-r1'):
            p=copy.deepcopy(PLAN);p['operations']['channel']['identity']=identity
            with self.assertRaises(Stop):plan_gate(p)
    def test_live_enabled_rejected(self):
        p=copy.deepcopy(PLAN);p['launchable']=True
        with self.assertRaises(Stop):plan_gate(p)
    def test_retry_rejected(self):
        p=copy.deepcopy(PLAN);p['operations']['channel']['retry']=1
        with self.assertRaises(Stop):plan_gate(p)
    def test_dependency_cycle_rejected(self):
        p=copy.deepcopy(PLAN);p['operations']['channel']['requires']=['private_upload']
        with self.assertRaises(Stop):plan_gate(p)
    def test_path_traversal_duplicate_marker_rejected(self):
        for values in (['../x'],['x','x'],['audit-evidence/consumed/x.json'],['/x'],['a\\x']):
            with self.assertRaises(Stop):preparation_paths(values)
    def test_event_attempt_exact(self):
        e={'repository':PLAN['repository'],'branch':PLAN['branch'],'event':'push','attempt':1}
        local_event_gate(e,PLAN)
        for key,value in [('attempt',2),('attempt',True),('event','workflow_dispatch'),('branch','main')]:
            with self.assertRaises(Stop):local_event_gate(dict(e,**{key:value}),PLAN)
    def test_credential_boundary_never_calls_transport(self):
        calls=[]
        with patch.dict(os.environ,{'PLM_YOUTUBE_GAME_001':'DO_NOT_READ'}),self.assertRaises(Stop):
            credential_boundary(lambda:calls.append(1),approved=True)
        self.assertEqual(calls,[])
    def test_parked_workflow_has_no_secrets(self):
        w=(ROOT/PLAN['workflow_path']).read_text()
        self.assertIn('if: ${{ false }}',w);self.assertNotIn('secrets.',w)
        self.assertNotIn('push:',w);self.assertIn('fetch-depth: 0',w)
    def test_markers_absent(self):
        for op in PLAN['operations'].values():self.assertFalse((ROOT/op['marker_path']).exists())
    def test_receipt_ack_cannot_complete(self):
        expected=dict(job_id='job-a',identity='upload-a',run_id='123',commit='a'*40,media_sha256='b'*64)
        good=dict(expected,verified=True,proof_basis='INDEPENDENT_GITHUB_API',phase='completed',run_attempt=1)
        self.assertTrue(validate_receipt(good,expected))
        for key,value in [('phase','before_upload'),('job_id','job-b'),('proof_basis','HMAC_ONLY'),('run_attempt',2)]:
            with self.assertRaises(Stop):validate_receipt(dict(good,**{key:value}),expected)
    def test_historical_exact_not_success_prerequisite(self):
        m=b'{"state":"CONSUMED_BEFORE_REMOTE"}'
        doc=raw({'consumed':[{'identity':'old','raw_sha256':digest(m)}]})
        self.assertTrue(historical_gate(doc,digest(doc),{'old':m}))
        with self.assertRaises(Stop):historical_gate(doc,digest(doc),{'old':b'changed'})
    def test_migration_executor_not_claimed_complete(self):
        for name in ('migration','migration_postcheck','worker_deploy','worker_postcheck'):
            self.assertEqual(PLAN['operations'][name]['adapter'],'NO_REMOTE_EXECUTOR_PREPARED')
            self.assertEqual(PLAN['operations'][name]['budget'],{})

class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'repo';self.root.mkdir();self.plan=copy.deepcopy(PLAN)
        self.git('init','-q');self.git('config','user.name','Offline Fixture');self.git('config','user.email','fixture@example.invalid')
        self.write('baseline.txt',b'base');self.commit('baseline');self.base=self.head()
        self.plan['preparation_parent']=self.base
        # Genuine Git fixture uses the authoritative complete package file list.
        for p in self.plan['preparation_files']:self.write(p,b'fixture\n')
        self.write('readiness/execution-package-plan.json',raw(self.plan))
        self.write(self.plan['source_manifest'],raw({'source_sha256':{self.plan['executor_path']:digest(b'fixture\n')}}))
        self.commit('prepare');self.prepared=self.head();self.audit=GitAudit(self.root)
    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.DEVNULL)
    def write(self,p,data):
        f=self.root/p;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(data)
    def commit(self,message):self.git('add','.');self.git('commit','-q','-m',message)
    def head(self):return self.git('rev-parse','HEAD').decode().strip()
    def marker(self,extra=False,pin_drift=False):
        op=self.plan['operations']['channel'];m={'identity':op['identity'],'operation':'channel','state':'CONSUMED_BEFORE_REMOTE','prepared_commit_sha':self.prepared,'approved':True}
        pinpaths={'plan_sha256':'readiness/execution-package-plan.json','source_manifest_sha256':self.plan['source_manifest'],'workflow_sha256':self.plan['workflow_path'],'executor_sha256':self.plan['executor_path'],'schema_sha256':self.plan['schema_path']}
        m.update({k:digest((self.root/p).read_bytes()) for k,p in pinpaths.items()})
        if pin_drift:m['plan_sha256']='0'*64
        self.write(op['marker_path'],raw(m))
        if extra:self.write('unexpected.txt',b'extra')
        self.commit('PLM execution package once '+op['identity'])
        return digest(raw(m))
    def test_full_history_merge_base_rev_list_diff(self):
        p=self.audit.preparation(self.plan,self.prepared)
        self.assertTrue(p['full_history']);self.assertEqual(p['merge_base'],self.base);self.assertEqual(p['rev_list'],1)
    def test_missing_preparation_file(self):
        p=copy.deepcopy(self.plan);p['preparation_files']=p['preparation_files'][:-1]
        with self.assertRaises(Stop):self.audit.preparation(p,self.prepared)
    def test_extra_preparation_file(self):
        p=copy.deepcopy(self.plan);p['preparation_files']=sorted(p['preparation_files']+['extra.py'])
        with self.assertRaises(Stop):self.audit.preparation(p,self.prepared)
    def test_shallow_real_repository_rejected(self):
        clone=Path(self.tmp.name)/'shallow'
        subprocess.check_call(['git','clone','-q','--depth','1',self.root.as_uri(),str(clone)],stderr=subprocess.DEVNULL)
        with self.assertRaises(Stop):GitAudit(clone).preparation(self.plan,self.prepared)
    def test_exact_marker_one_commit(self):
        h=self.marker();facts=self.audit.marker_history(self.plan,self.prepared,self.head(),'channel',h)
        self.assertTrue(facts['marker_exact'])
    def test_marker_extra_file(self):
        h=self.marker(extra=True)
        with self.assertRaises(Stop):self.audit.marker_history(self.plan,self.prepared,self.head(),'channel',h)
    def test_marker_pin_drift(self):
        h=self.marker(pin_drift=True)
        with self.assertRaises(Stop):self.audit.marker_history(self.plan,self.prepared,self.head(),'channel',h)
    def test_marker_replay_new_commit(self):
        h=self.marker();self.git('commit','--allow-empty','-q','-m','replay')
        with self.assertRaises(Stop):self.audit.marker_history(self.plan,self.prepared,self.head(),'channel',h)
    def test_worktree_drift(self):
        h=self.marker();self.write('untracked.txt',b'drift')
        with self.assertRaises(Stop):self.audit.marker_history(self.plan,self.prepared,self.head(),'channel',h)
    def test_consumed_marker_in_preparation_rejected(self):
        self.git('reset','--hard',self.base)
        self.write(self.plan['operations']['channel']['marker_path'],b'consumed')
        for p in self.plan['preparation_files']:self.write(p,b'fixture\n')
        self.commit('illegal prepare')
        with self.assertRaises(Stop):self.audit.preparation(self.plan,self.head())
    def test_marker_hash_substitution(self):
        self.marker()
        with self.assertRaises(Stop):self.audit.marker_history(self.plan,self.prepared,self.head(),'channel','0'*64)
    def test_missing_commit_not_absent_path(self):
        with self.assertRaises(Stop):self.audit.absent('0'*40,self.plan['operations']['channel']['marker_path'])

if __name__=='__main__':unittest.main()
