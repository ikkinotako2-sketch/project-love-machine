"""Explicit capability adapters; no hidden remote fallback."""
import hashlib,json
from plm.improvement.core import guidance
from .ledger import require
class ThemeAdapter:
    def __init__(self,source,*,rights_policy):self.source=source;self.policy=rights_policy
    def next(self):
        item=self.source()
        require(isinstance(item,dict) and set(item)=={'topic','source_id','license','verified'} and item['verified'] is True and item['license'] in self.policy and 0<len(item['topic'])<=120,'THEME_RIGHTS_BLOCKED')
        return item
class ScriptAdapter:
    def __init__(self,generator,*,capability_verified=False):self.generator=generator;self.capability=capability_verified
    def generate(self,theme):
        require(self.capability is True,'SCRIPT_CAPABILITY_BLOCKED')
        d=self.generator(theme)
        require(isinstance(d,dict) and isinstance(d.get('narration'),str) and 0<len(d['narration'])<=500 and d.get('rights_verified') is True,'SCRIPT_CONTRACT_STOP')
        return {**d,'script_sha256':hashlib.sha256(json.dumps(d,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
class MetricsAdapter:
    def __init__(self,read,*,capability_verified=False):self.read=read;self.capability=capability_verified
    def collect(self,result):
        require(result['state']=='Done' and self.capability is True,'METRICS_CAPABILITY_BLOCKED')
        d=self.read(result['video_id']);require(isinstance(d,dict) and all(d.get(k) is None or type(d[k]) is int and d[k]>=0 for k in ['views','likes','comments']),'METRICS_SHAPE_STOP')
        return d
    def improve(self,observations):return guidance(None,{'metrics':observations})
def next_job(current,script,seen):
    require(current['state']=='Done','UNKNOWN_NO_NEXT_JOB')
    identifier='plm-loop-'+hashlib.sha256((current['job_id']+script['script_sha256']).encode()).hexdigest()[:24]
    require(identifier not in seen,'DUPLICATE_NEXT_JOB_STOP');seen.add(identifier);return identifier
