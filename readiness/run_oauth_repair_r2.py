"""Only OFFLINE admission and changed-boundary tests; no credential access."""
import argparse,hashlib,json,subprocess,sys,unittest
from pathlib import Path
from readiness.run_final_candidate import deny
from readiness.verify_final_sources import verify
from plm.automation.execution_gate import GitAudit
from plm.automation.executors.oauth_exchange_r2 import PLAN,MANIFEST,local_gate

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--local',action='store_true');args=parser.parse_args()
    sys.addaudithook(deny)
    p=json.loads((ROOT/PLAN).read_text());m=json.loads((ROOT/MANIFEST).read_text());verify(m,ROOT)
    assert type(p['enabled']) is bool and p['enabled'] is p['release_configured']
    assert all(p[k] is False for k in ['owner_approved','operational_exclusion_attested','writer_permissions_reviewed','handoff_approved'])
    assert not (ROOT/p['marker_path']).exists() and local_gate(ROOT,{}) is None
    for path,digest in p['historical_consumed_markers'].items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest
    history='NOT_RUN_LOCAL'
    if not args.local:
        g=GitAudit(ROOT);head=g.git('rev-parse','HEAD').decode().strip();parent=p['preparation_parent']
        assert g.git('rev-parse','--is-shallow-repository').strip()==b'false'
        assert g.git('merge-base',parent,head).decode().strip()==parent
        assert g.git('rev-list','--count',parent+'..'+head).strip()==b'1'
        actual=g.git('diff','--name-only',parent+'..'+head).decode().splitlines()
        assert sorted(actual)==p['preparation_files'] and len(actual)==len(set(actual))
        for path,digest in p['historical_consumed_markers'].items():
            assert hashlib.sha256(g.raw(parent,path)).hexdigest()==digest
        assert not any(path.startswith('audit-evidence/') for path in actual)
        history='FULL_EXACT_ONE_PREPARATION_COMMIT'
    suite=unittest.defaultTestLoader.discover('tests',pattern='test_oauth_exchange_r2.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    subprocess.run(['node','--test','tests/test_oauth_handoff_r2.cjs'],cwd=ROOT,check=True)
    assert result.wasSuccessful() and not result.skipped
    report={'status':'OFFLINE_R2_PREPARATION_PASS','python_tests':result.testsRun,'node_tests':12,'history':history,'source_files':len(m['source_sha256']),'r1_marker_unchanged':True,'r2_marker_created':False,'r2_entry':'CONFIGURED_NO_EXECUTION_MARKER' if p['enabled'] else 'PARKED','actual_handoff_contents':'NOT_READ','exact_historical_cause':'UNKNOWN','google_oauth_calls':0,'secret_operations':0,'uploads':0,'cloudflare_calls':0}
    out=ROOT/'oauth-repair-r2-evidence';out.mkdir(exist_ok=True);(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
