"""Bounded offline loop only. No cron, API fetch, dispatch or live factory."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from plm.improvement.core import guidance
from .ledger import Stop,require
FLAGS={'TEST_ONLY':True,'DRY_RUN':True,'NO_PUBLISH':True,'EMERGENCY_STOP':True}
class OfflineLoop:
    def __init__(self,ledger,config,*,theme,script,render,upload_mock,metrics_mock,clock):
        require(config.get('offline_only') is True and config.get('live_enabled') is False and config.get('flags')==FLAGS,'PARKED_CONFIG_STOP')
        require(config.get('interval_seconds',0)>=3600 and config.get('maximum_ticks',0) in range(1,25),'SCHEDULE_BOUND_STOP')
        require(all(getattr(x,'offline_mock',False) is True for x in (theme,script,render,upload_mock,metrics_mock)),'OFFLINE_FUNCTIONS_REQUIRED')
        self.l=ledger;self.c=config;self.stages=(theme,script,render,upload_mock,metrics_mock);self.clock=clock;self.stopped=False;self.ticks=0;self.improvements=[]
    def tick(self,job_id):
        require(not self.stopped and self.ticks<self.c['maximum_ticks'],'LOOP_STOP')
        self.ticks+=1;now=self.clock();require(type(now) is int and now>0,'CLOCK_STOP')
        if self.l.progress()['stopped']:self.stopped=True;return {'state':'STOP','reason':'PREVIOUS_TERMINAL_ERROR'}
        if self.c.get('operator_stop') is True:self.stopped=True;self.l.notify('loop-emergency','EMERGENCY_STOP');return {'state':'STOP','reason':'EMERGENCY_STOP'}
        theme,script,render,upload,metrics=self.stages
        claim=None;phase="CONFIG"
        try:
            idea=theme();payload=script(idea)
            require(isinstance(payload,dict) and payload.get('rights_verified') is True,'RIGHTS_STOP')
            raw=json.dumps(payload,sort_keys=True,ensure_ascii=False).encode();fingerprint=hashlib.sha256(raw).hexdigest()
            if not self.l.add(job_id,fingerprint,now):return {'state':'DUPLICATE_NO_OP','job_id':job_id}
            day=datetime.fromtimestamp(now,timezone.utc).strftime('%Y-%m-%d')
            self.l.reserve_budget(day,self.c['estimated_cost'],self.c['daily_limits'])
            claim=self.l.claim(job_id,'offline-loop',now,self.c['lease_seconds'])
            phase="RENDER";media=render(payload);require(media.get('quality_pass') is True,'RENDER_STOP')
            # Offline upload must also exercise consume-before-send, not bypass it.
            phase="UPLOAD";result=upload(claim,media)
            require(result.get('state') in {'Done','UNKNOWN','Failed'},'RESULT_STOP')
            require(self.l.get(job_id)['state']==result['state'],'DURABLE_RESULT_REQUIRED')
            if result['state']!='Done':self.stopped=True;return result
            observations=metrics(result)
            require(observations.get('source')=='OFFLINE_FIXTURE','METRICS_SOURCE_STOP')
            self.improvements.append(guidance(None,{'metrics':observations}))
            return result
        except Exception:
            self.stopped=True
            if claim and self.l.get(job_id)['state']=='Processing':
                reason='UPLOAD_UNKNOWN' if self.l.get(job_id)['sent'] else ('AUTH_STOP' if phase=='UPLOAD' else 'RENDER_FAILED')
                return self.l.finish(claim,'UNKNOWN' if self.l.get(job_id)['sent'] else 'Failed',reason=reason)
            self.l.notify('loop-stop','BUDGET_STOP' if claim is None else 'CONFIG_STOP')
            return {'state':'STOP','reason':'CONFIG_OR_BUDGET_STOP'}
    def report(self):return {**self.l.progress(),'ticks':self.ticks,'loop_stopped':self.stopped,'improvement_hypotheses':len(self.improvements),'mode':'OFFLINE_SIMULATION','live_enabled':False}

def mock(fn):fn.offline_mock=True;return fn
