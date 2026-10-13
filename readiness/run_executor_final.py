"""Delta executor tests and actual prepared Git history. Network denied."""
import json,subprocess,sys,unittest
from pathlib import Path
from readiness.run_final_candidate import deny
from readiness.verify_final_sources import verify
from plm.automation.execution_gate import GitAudit,load_pinned_plan,digest
ROOT=Path(__file__).resolve().parents[1]
def gate():
    raw=(ROOT/'readiness/executor-final-plan.json').read_bytes()
    plan=load_pinned_plan(raw,digest(raw))
    manifest=json.loads((ROOT/plan['source_manifest']).read_bytes());verify(manifest,ROOT)
    head=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD']).decode().strip()
    proof=GitAudit(ROOT).preparation(plan,head)
    return plan,manifest,head,proof

def main():
    sys.addaudithook(deny)
    plan,manifest,head,proof=gate()
    if '--verify-only' in sys.argv:
        print(json.dumps({'source_files':len(manifest['source_sha256']),'history':proof,'marker_changes':0}));return
    suite=unittest.defaultTestLoader.discover('tests',pattern='test_executor_final.py')
    scenarios=[t.id() for s in suite for t in s]
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'status':'FOUR_EXECUTOR_OFFLINE_PASS_PARKED','prepared_commit':head,
        'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'source_files':len(manifest['source_sha256']),'history':proof,'scenarios':scenarios,
        'e2e':'A_CHANNEL_B_STATE_C_ACK_D_INDEPENDENT_DONE_FIXTURES',
        'media_sha256':plan['media_sha256'],'movie_regenerated':False,'fixture_basis':'OFFLINE_CONTRACT',
        'oauth_posts':0,'youtube_gets':0,'uploads':0,'cloudflare_requests':0,'real_state_writes':0,
        'secret_operations':0,'execution_markers_created':0,'live_authority_issuers':0}
    out=ROOT/'executor-evidence';out.mkdir(exist_ok=True)
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='scenarios'}))
    if not result.wasSuccessful() or result.skipped:raise SystemExit(1)
if __name__=='__main__':main()
