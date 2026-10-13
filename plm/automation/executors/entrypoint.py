"""Parked CLI. Optional preflight reads Git only; never reads Secrets."""
import argparse,json,os
from .authority import ExecutorAudit,production_entry
from ..ledger import Stop

def main():
    p=argparse.ArgumentParser();p.add_argument('--operation',choices=['channel','state_init','private_upload','finalize'],required=True)
    p.add_argument('--audit',action='store_true')
    for key in ('prepared','head','plan_sha','manifest_sha','marker_sha'):p.add_argument('--'+key.replace('_','-'))
    args=p.parse_args()
    if args.audit:
        if not all(getattr(args,k) for k in ('prepared','head','plan_sha','manifest_sha','marker_sha')):
            print(json.dumps({'status':'BLOCKED','reason_code':'AUDIT_PINS_REQUIRED','credentials_read':0,'requests':0}));return 1
        try:
            # Explicit event data would come from the trusted GitHub runner. Here
            # no live workflow invokes this mode and it never mints authority.
            attempt=os.environ.get('GITHUB_RUN_ATTEMPT','')
            event={'repository':os.environ.get('GITHUB_REPOSITORY',''),'branch':os.environ.get('GITHUB_REF','').removeprefix('refs/heads/'),'event':os.environ.get('GITHUB_EVENT_NAME',''),'attempt':int(attempt) if attempt.isdecimal() else None,'sha':os.environ.get('GITHUB_SHA',''),'run_id':os.environ.get('GITHUB_RUN_ID','')}
            facts=ExecutorAudit('.').before_credentials(event=event,prepared=args.prepared,head=args.head,plan_sha=args.plan_sha,manifest_sha=args.manifest_sha,marker_sha=args.marker_sha,operation=args.operation)
        except Exception:
            print(json.dumps({'status':'BLOCKED','reason_code':'LOCAL_AUDIT_STOP','credentials_read':0,'requests':0}));return 1
        print(json.dumps({'local_gate':facts}))
    print(json.dumps(production_entry(args.operation)))
    return 0
if __name__=='__main__':raise SystemExit(main())
