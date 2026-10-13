"""Complete production wiring; reviewed releases are all disabled in this build.

local Git gate → independent current/prerequisite GitHub proof → role-limited
SecretScope → existing operation kernel → sanitized local result artifact.
No default retry, dispatch, global activation, rollback or Secret modification.
"""
import json,time
from pathlib import Path
from . import authority as a
from .release import audited,frozen_policy,release_gate,issue_live,SecretScope,revoke
from .run_reader import OperationRunReader
from .channel_state import ChannelExecutor,StateInitExecutor
from .posting import UploadExecutor,FinalizeExecutor,RunProofAdapter,fixed_job
from .lifecycle import ExecutorLifecycle
from . import transports as t
from ..ledger import require,Stop
from ..execution_gate import SAFE
from ..evidence_adapters import HTTPSReader,GitHubCompletionAuthority
from ..render_contract import contract,VOICE
ROOT=Path(__file__).resolve().parents[3]
CF_OPS=('migration','migration_postcheck','worker_deploy','worker_postcheck')


def read_event(env):
    attempt=env.get('GITHUB_RUN_ATTEMPT','')
    return {'repository':env.get('GITHUB_REPOSITORY',''),'branch':env.get('GITHUB_REF','').removeprefix('refs/heads/'),'event':env.get('GITHUB_EVENT_NAME',''),'attempt':int(attempt) if attempt.isdecimal() else None,'sha':env.get('GITHUB_SHA',''),'run_id':env.get('GITHUB_RUN_ID',''),'safe_flags':{k:(env[k]=='true') if env.get(k) in ('true','false') else None for k in SAFE}}


def render_assets(path,identity,root=ROOT):
    job=fixed_job(identity);e=json.loads((Path(root)/'readiness/reused-render-evidence.json').read_bytes())
    script={'title':job['title'],'hook':job['sentences'][0],'narration':''.join(job['sentences']),'scenes':[{'start':x['start_seconds'],'end':x['end_seconds'],'caption':x['text'],'visual_keyword':'study','motion':'none','sfx':'none','emphasis_words':[]} for x in e['timing']],'bgm':{'mood':'calm','volume':0}}
    raw=json.dumps(script,ensure_ascii=False,separators=(',',':'))
    c=contract(raw,mode='REUSE_PINNED',voice=VOICE,media_sha=e['media_sha256'],audio_sha=e['audio_sha256'],caption_sha=e['caption_sha256'])
    p=Path(path)
    return {'media_path':p,'quality_evidence':e,'render_contract':c,'script_raw':raw,'voice_inventory':[{'name':'ずんだもん','styles':[{'id':3,'name':'ノーマル'}]}],'audio':p.with_name('audio.wav').read_bytes(),'captions':p.with_name('captions.ass').read_bytes(),'render_evidence':{'voice':VOICE,'script_sha256':c['script_sha256'],'quality_pass':True,**{k:e[k] for k in ('media_sha256','audio_sha256','caption_sha256')}}}


def run_expected(checked,root=ROOT):
    plan=checked.plan;o=plan['operations'][checked.operation];e=checked.event
    return {'repository':plan['repository'],'run_id':e['run_id'],'attempt':1,'commit':checked.head,'prepared_commit':checked.prepared,'branch':plan['branch'],'workflow_path':o['workflow_path'],'job_name':o.get('job_name','execute'),'job_id':plan['job_id'],'identity':o['identity'],'media_sha256':plan['media_sha256'],'artifact_id':11746833809,'artifact_archive_sha256':'1f741c38d667267d4713bbbeb67b2645308336cbb9876aa4616d5710460bb61d','artifact_run_id':38250671983,'artifact_commit':'4b881ed39a867769f99613327c6c7653b152c7f0','marker_path':o['marker_path'],'marker_sha256':checked.marker_sha,'workflow_sha256':a.digest(a.ExecutorAudit(root).raw(checked.prepared,o['workflow_path'])),'approval_field':'finalize_approved' if checked.operation=='finalize' else 'upload_approved'}

class ProductionRunner:
    def __init__(self,root=ROOT,*,clock=time.time):self.root=Path(root);self.clock=lambda:int(clock());self.used=False;self.trace=[];self.counts={}
    def observe(self,service,method,status):
        if method:
            key=service+"_"+method;self.counts[key]=self.counts.get(key,0)+1
        if status is not None:self.trace.append({"service":service,"status":status})
    def diagnostics(self,clients,readers,backend=None):
        counts=dict(self.counts);statuses=self.trace.copy();counts["GitHub_GET"]=sum(r.calls for r in readers)
        for client in clients:
            name=type(client).__name__;service="Cloudflare" if name=="CFHTTP" else "Artifact" if name=="ArtifactInput" else "Callback" if name=="CallbackHTTP" else "GitHub"
            statuses += [{"service":service,"status":s} for s in getattr(client,"statuses",[])]
            calls=getattr(client,"calls",None)
            if isinstance(calls,dict):
                for method,n in calls.items():counts["StateInit_"+method]=n
            elif name=="ArtifactInput":counts["Artifact_GET"]=client.calls
            elif name=="CallbackHTTP":counts["Callback_POST"]=int(client.used)
            elif name=="CFHTTP":counts["Cloudflare_total"]=client.used
        if backend is not None:
            for method,n in backend.transport.calls.items():counts["StateCAS_"+method]=n
        return {"http_statuses":statuses,"github_GET_attempted":sum(r.calls for r in readers),"request_counts":counts}
    def preflight(self,operation,*,event,**pins):
        p=frozen_policy(self.root)
        # This fixed file/hash is checked before audit, token loading or any I/O.
        # Unapproved/UNKNOWN release returns PARKED even if Secrets are present.
        try:record=release_gate(operation,p)
        except Stop:return None
        require(event.get('safe_flags')==record['required_flags'],'SAFE_FLAG_CONTEXT_STOP')
        checked=audited(self.root,operation=operation,event=event,**pins)
        require(record['prepared_commit']==checked.prepared and record['approved_marker_sha256']==checked.marker_sha,'RELEASE_SOURCE_MARKER_STOP')
        return checked
    def execute(self,operation,*,event,pins,secret_loader,prerequisite_files=(),media_path=None,input_dir=None):
        require(not self.used,'RUNNER_ONCE_ONLY');self.used=True
        checked=self.preflight(operation,event=event,**pins)
        if checked is None:return {'status':'PARKED','operation':operation,'real_requests':0,'credentials_read':0,'source_release':False}
        policy=frozen_policy(self.root);record=policy['releases'][operation]
        require(len(record['prerequisites'])==len(checked.plan['operations'][operation]['requires']) and (input_dir is not None or len(prerequisite_files)==len(record['prerequisites'])),'PREREQUISITE_INPUT_STOP')
        scope=SecretScope(secret_loader,['GITHUB_TOKEN']+policy['secret_roles'][operation])
        permit=None;clients=[]
        try:
            # GITHUB_TOKEN is injected only after the actual local gate passes.
            github=HTTPSReader('api.github.com',scope.get('GITHUB_TOKEN'),approved=True,maximum=6)
            # Reader instance budget max6 is per chunk; source-locked operation reader
            # separately enforces total32. Resetting is not a retry; no request repeats.
            readers=[github]
            def get(path):
                current=readers[-1]
                require(sum(r.calls for r in readers)<32,'TOTAL_GITHUB_READ_BUDGET_STOP')
                if current.calls==6:
                    current=HTTPSReader('api.github.com',scope.get('GITHUB_TOKEN'),approved=True,maximum=6);readers.append(current)
                out=current(path);self.trace.append({'service':'GitHub','status':out[0]});return out
            get.real_network_read=True
            proof=OperationRunReader(get);current_proof=proof.current(checked)
            if input_dir is not None:
                require(record['artifact_handoff_reviewed'] is True,'ARTIFACT_HANDOFF_APPROVAL_REQUIRED')
                from .artifact_input import ArtifactInput
                download=ArtifactInput(current_proof,scope.get('GITHUB_TOKEN'));clients.append(download)
                files=[]
                for i,d in enumerate(record['prerequisites']):
                    folder=download.download(d['artifact_id'],d['artifact_archive_sha256'],allowed_names=['runtime-receipt.json'],output=Path(input_dir)/('prereq-'+str(i)))
                    files.append(folder/'runtime-receipt.json')
                prerequisite_files=files
                if operation=='private_upload':
                    folder=download.download(11746833809,'1f741c38d667267d4713bbbeb67b2645308336cbb9876aa4616d5710460bb61d',allowed_names=['short.mp4','audio.wav','captions.ass'],output=Path(input_dir)/'media');media_path=folder/'short.mp4'
            prior=[proof.prerequisite(d,Path(f).read_bytes()) for d,f in zip(record['prerequisites'],prerequisite_files)]
            permit=issue_live(checked,prerequisites=prior,policy=policy,run_evidence=current_proof)
            if operation=='channel':
                fresh=t.channel_transports(permit,scope.bundle(),self.clock,self.observe)
                out=ChannelExecutor(fresh).run(permit)
            elif operation=='state_init':
                client=t.StateInitHTTP(scope.get('PLM_GITHUB_STATE_TOKEN'),permit);clients.append(client)
                out=StateInitExecutor(client).run(permit)
            elif operation in ('private_upload','finalize'):
                backend=t.lifecycle_backend(permit,scope.get('PLM_GITHUB_STATE_TOKEN'))
                cached_get=lambda path:(200,proof.read(path))
                authority=GitHubCompletionAuthority(cached_get,lambda row:record['coordinator_terminal_expected'])
                state=ExecutorLifecycle(backend,self.clock,completion_authority=authority)
                fresh=t.channel_transports(permit,scope.bundle(),self.clock,self.observe)
                if operation=='private_upload':
                    require(media_path is not None,'MEDIA_REQUIRED')
                    engine=UploadExecutor(state=state,fresh=fresh,provenance=RunProofAdapter(cached_get,self.clock),upload=t.strict_upload_transport(permit),clock=self.clock)
                    out=engine.run(permit,expected=run_expected(checked,self.root),assets=render_assets(media_path,permit.identity,self.root),budget_observation=record['budget_observation'],budget_cost=record['budget_cost'])
                else:
                    route=policy['callback'];require(route['verified'] is True and route['origin'] is not None,'CALLBACK_TARGET_UNPINNED')
                    context=record['callback_context'];checkpoint=record['callback_checkpoint']
                    key=scope.key('PLM_YOUTUBE_RESULT_CALLBACK_KEY');dispatch=scope.get('PLM_GITHUB_DISPATCH_TOKEN').encode()
                    from .callback_http import CallbackHTTP
                    send=CallbackHTTP(permit,route['origin']);clients.append(send)
                    cb=t.callback_transport(permit,send,context,checkpoint,key,route['key_id'],origin=route['origin'],clock=self.clock,dispatch_key=dispatch)
                    def readback(token):return t.processed_reader(permit,token)
                    out=FinalizeExecutor(state=state,upload_provenance=RunProofAdapter(cached_get,self.clock),own_provenance=RunProofAdapter(cached_get,self.clock),fresh=fresh,readback_for_token=readback,callback=cb,clock=self.clock).run(permit,own_expected=run_expected(checked,self.root),script_sha256=record['script_sha256'])
            else:
                from .cloudflare import CFHTTP,TransferExecutor
                roles=policy['secret_roles'][operation]
                client=CFHTTP(permit,scope.get(roles[0]),scope.get(roles[-1]));clients.append(client)
                out=TransferExecutor(client,root=self.root).run(permit)
            payload=out.public();payload.update(run_id=event['run_id'],commit=checked.head,workflow_path=checked.plan['operations'][operation]['workflow_path'])
            payload.update(self.diagnostics(clients,readers,locals().get('backend')));return payload
        except Exception:
            return {'status':'BLOCKED','reason_code':'RUNNER_STOP_NO_RETRY','operation':operation,**self.diagnostics(clients,locals().get('readers',[]),locals().get('backend'))}
        finally:
            for client in clients:
                if hasattr(client,'clear'):client.clear()
            for reader in locals().get('readers',[]):reader.clear()
            if 'backend' in locals() and hasattr(backend.transport,'clear'):backend.transport.clear()
            scope.clear()
            if permit is not None:revoke(permit)
