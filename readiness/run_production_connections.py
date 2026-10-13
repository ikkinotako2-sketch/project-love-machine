"""Only new connection tests; actual preparation/source gate; provider network denied."""
import json,sys,unittest
from pathlib import Path
from readiness.run_executor_final import gate,scenario_ids
from readiness.run_final_candidate import deny
from plm.automation.execution_gate import GitAudit,load_pinned_plan,digest
from plm.automation.executors.release import frozen_policy
ROOT=Path(__file__).resolve().parents[1]
def main():
    sys.addaudithook(deny)
    plan,manifest,head,proof=gate()
    raw=(ROOT/'readiness/cloudflare-transfer-plan.json').read_bytes();cf=load_pinned_plan(raw,digest(raw))
    cfproof=GitAudit(ROOT).preparation(cf,head)
    for p in (plan,cf):
        for op in p['operations'].values():
            if (ROOT/op['marker_path']).exists():raise ValueError('EXECUTION_MARKER_PRESENT_STOP')
    policy=frozen_policy(ROOT)
    if any(r['enabled'] for r in policy['releases'].values()):raise ValueError('RELEASE_NOT_PARKED_STOP')
    suite=unittest.defaultTestLoader.discover('tests',pattern='test_production_connections.py')
    ids=list(scenario_ids(suite));result=unittest.TextTestRunner(verbosity=2).run(suite)
    passed=result.wasSuccessful() and not result.skipped
    report={'status':'PRODUCTION_CONNECTIONS_OFFLINE_PASS_PARKED' if passed else 'OFFLINE_TEST_FAIL','commit':head,'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'source_files':len(manifest['source_sha256']),'history':proof,'cloudflare_history':cfproof,'scenarios':ids,'prior_61_test_evidence':'38348714174_SUCCESS_ATTEMPT_1','prior_48h_e2e':'REUSED_NOT_REGENERATED','native_releases_enabled':0,'oauth_posts':0,'youtube_requests':0,'cloudflare_requests':0,'state_remote_writes':0,'secret_operations':0,'execution_markers_created':0}
    out=ROOT/'connection-evidence';out.mkdir(exist_ok=True);(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='scenarios'}))
    if not passed:raise SystemExit(1)
if __name__=='__main__':main()
