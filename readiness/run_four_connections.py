"""Delta tests only, real provider networking impossible in this runner."""
import json,sys,unittest
from pathlib import Path
from readiness.run_final_candidate import deny
def main():
    sys.addaudithook(deny)
    suite=unittest.defaultTestLoader.discover('tests',pattern='test_four_connections.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'mode':'OFFLINE_DELTA','tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'virtual_hours':48,'real_oauth_posts':0,'real_youtube_gets':0,'real_uploads':0,'cloudflare_requests':0,'live_entry':'PARKED','simulation_media_mode':'REUSE_EXISTING_MP4_NO_NEW_RENDER'}
    Path('four-evidence').mkdir(exist_ok=True);Path('four-evidence/summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    if not result.wasSuccessful() or result.skipped:raise SystemExit(1)
if __name__=='__main__':main()
