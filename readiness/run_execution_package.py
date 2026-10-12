"""Changed boundary tests only; no provider networking or Secret reads."""
import json,sys,unittest,subprocess
from pathlib import Path
from readiness.run_final_candidate import deny
from readiness.verify_final_sources import verify
from plm.automation.execution_gate import GitAudit,load_pinned_plan,digest
ROOT=Path(__file__).resolve().parents[1]
def main():
    sys.addaudithook(deny)
    raw=(ROOT/'readiness/execution-package-plan.json').read_bytes()
    manifest=json.loads((ROOT/'readiness/execution-package-source-hashes.json').read_bytes())
    verify(manifest,ROOT)
    plan=load_pinned_plan(raw,digest(raw))
    head=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD']).decode().strip()
    proof=GitAudit(ROOT).preparation(plan,head)
    suite=unittest.defaultTestLoader.discover('tests',pattern='test_execution_package.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'status':'OFFLINE_EXECUTION_PACKAGE_PREPARED_PARKED','prepared_commit':head,
            'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'skipped':len(result.skipped),'history':proof,'source_files':len(manifest['source_sha256']),
            'oauth_posts':0,'youtube_requests':0,'cloudflare_requests':0,'state_writes':0,
            'execution_markers_created':0,'launchable':False}
    out=ROOT/'execution-evidence';out.mkdir(exist_ok=True)
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
    if not result.wasSuccessful() or result.skipped:raise SystemExit(1)
if __name__=='__main__':main()
