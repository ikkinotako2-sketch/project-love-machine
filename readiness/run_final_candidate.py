"""Reproducible 48-hour virtual E2E; all network disabled before imports."""
import argparse,json,sys
from pathlib import Path
def deny(event,args):
    if event.startswith('socket.') or event in ('urllib.Request','http.client.connect'):raise RuntimeError('OFFLINE_NETWORK_FORBIDDEN')
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--media',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    sys.addaudithook(deny)
    from plm.automation.final_candidate import IntegratedCandidate,command_center
    args.output.mkdir(parents=True,exist_ok=True)
    db=args.output/'simulation.sqlite'
    if db.exists():raise SystemExit('SIMULATION_ALREADY_CONSUMED_USE_NEW_OUTPUT_DIRECTORY')
    now=[1791763200];p=IntegratedCandidate(db,args.media,clock=lambda:now[0],artifact_expires_at=1794355200)
    try:
        for hour in range(49):
            now[0]=1791763200+hour*3600
            if hour in (0,12,24,36):
                job='offline-final-0' if p.next_id is None else p.next_id
                result=p.tick(job)
                if result.get('state')!='Done':raise SystemExit('SIMULATION_STOP')
        report={**p.report(),'virtual_hours':48,'fixture_real_network_calls':0,'render_reused':True}
        (args.output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        (args.output/'command-center.html').write_text(command_center(report))
        (args.output/'upload-result.json').write_text(json.dumps(p.pending_result,indent=2)+'\n')
        print(json.dumps({'mode':'OFFLINE_SIMULATION','virtual_hours':48,'completed_jobs':report['counts']['Done'],'real_network_calls':0}))
    finally:p.close()
if __name__=='__main__':main()
