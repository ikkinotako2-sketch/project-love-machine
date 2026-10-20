"""Actual source/history gate + only new/recovered OAuth tests; network denied."""
import json,sys,unittest
from pathlib import Path
from readiness.run_final_candidate import deny
from readiness.run_executor_final import scenario_ids
from readiness.verify_final_sources import verify
from plm.automation.execution_gate import GitAudit
from plm.automation.executors.oauth_exchange import PLAN,MANIFEST
ROOT=Path(__file__).resolve().parents[1]
def main():
 sys.addaudithook(deny)
 plan=json.loads((ROOT/PLAN).read_bytes());manifest=json.loads((ROOT/MANIFEST).read_bytes());verify(manifest,ROOT)
 g=GitAudit(ROOT);head=g.git('rev-parse','HEAD').decode().strip();parent=plan['preparation_parent']
 assert g.git('rev-parse','--is-shallow-repository').strip()==b'false'
 assert g.git('merge-base',parent,head).decode().strip()==parent
 assert g.git('rev-list','--count',parent+'..'+head).strip()==b'1'
 actual=g.git('diff','--name-only',parent+'..'+head).decode().splitlines()
 assert sorted(actual)==plan['preparation_files'] and len(actual)==len(set(actual))
 assert not (ROOT/plan['marker_path']).exists() and plan['enabled'] is True
 assert plan['release_configured'] is True and plan['execution_approval_source']=='FUTURE_MARKER_ONLY'
 assert all(plan[k] is False for k in ('owner_approved','handoff_approved','writer_permissions_reviewed','operational_exclusion_attested'))
 from plm.automation.executors.oauth_exchange import local_gate
 assert local_gate(ROOT,{}) is None
 verify(json.loads((ROOT/'readiness/executor-final-source-hashes.json').read_bytes()),ROOT)
 suite=unittest.TestSuite([unittest.defaultTestLoader.discover('tests',pattern=p) for p in ('test_oauth_client_reuse.py','test_oauth_exchange.py')]);ids=list(scenario_ids(suite))
 r=unittest.TextTestRunner(verbosity=2).run(suite);ok=r.wasSuccessful() and not r.skipped
 report={'status':'OAUTH_CLIENT_REUSE_RELEASE_PASS_WAITING_FOR_EXECUTION_APPROVAL' if ok else 'FAIL','prepared_commit':head,'preparation_parent':parent,'full_history':True,'rev_list':1,'preparation_files_exact':True,'source_files':len(manifest['source_sha256']),'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'skipped':len(r.skipped),'scenarios':ids,'google_oauth_calls':0,'secret_remote_operations':0,'uploads':0,'cloudflare_calls':0,'markers_created':0,'secret_values_retained':False,'native_crypto_test':'LIBSODIUM_SEALED_BOX_FIXTURE_ROUNDTRIP','production_entry':'CONFIGURED_NO_EXECUTION_MARKER','candidate_current_validity':'NOT_TESTED','channel_match':'UNVERIFIED'}
 out=ROOT/'oauth-reuse-evidence';out.mkdir(exist_ok=True);(out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='scenarios'}))
 if not ok:raise SystemExit(1)
if __name__=='__main__':main()
