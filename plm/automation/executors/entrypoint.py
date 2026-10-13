"""Two-stage CLI. Preflight has no Secret references, execution repeats the gate."""
import argparse,json,os
from pathlib import Path
from .runner import ProductionRunner,read_event

def main():
    p=argparse.ArgumentParser();p.add_argument('--operation',required=True)
    p.add_argument('--prepare',action='store_true');p.add_argument('--execute',action='store_true')
    p.add_argument('--output');p.add_argument('--inputs')
    for key in ('prepared','head','plan_sha','manifest_sha','marker_sha'):p.add_argument('--'+key.replace('_','-'))
    x=p.parse_args();runner=ProductionRunner();event=read_event(os.environ)
    pins={k:getattr(x,k) for k in ('prepared','head','plan_sha','manifest_sha','marker_sha')}
    # Missing release metadata returns PARKED before auditing or reading a Secret.
    try:
        checked=runner.preflight(x.operation,event=event,**pins)
        if checked is None:result={'status':'PARKED','operation':x.operation,'credentials_read':0,'real_requests':0};ready=False
        elif x.prepare:result={'status':'LOCAL_GATE_PASS','credentials_read':0,'real_requests':0};ready=True
        elif x.execute:
            result=runner.execute(x.operation,event=event,pins=pins,secret_loader=lambda name:os.environ.get(name),input_dir=x.inputs);ready=False
        else:result={'status':'PARKED_EXPLICIT_EXECUTE_REQUIRED','credentials_read':0,'real_requests':0};ready=False
    except Exception:result={'status':'BLOCKED','reason_code':'RUNNER_GATE_OR_EXECUTION_STOP_NO_RETRY'};ready=False
    if x.prepare and os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('ready='+('true' if ready else 'false')+'\n')
    if x.output:
        out=Path(x.output);out.parent.mkdir(parents=True,exist_ok=True)
        with out.open('x') as f:json.dump(result,f,sort_keys=True);f.write('\n')
    print(json.dumps(result,sort_keys=True))
    return 1 if result['status']=='BLOCKED' else 0
if __name__=='__main__':raise SystemExit(main())
