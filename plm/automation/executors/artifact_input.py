"""Bounded GitHub artifact handoff; OAuth/YouTube transports never redirect.

The single signed storage URL is memory-only, receives no Authorization header,
and is never printed or saved. Both GETs must be separately in the release budget.
"""
import http.client,hashlib,io,re,time,zipfile
from pathlib import Path
from urllib.parse import urlsplit
from .run_reader import RunEvidence,_RUN_SEAL
from ..ledger import require,Stop
REPO='ikkinotako2-sketch/project-love-machine'

class ArtifactInput:
    def __init__(self,read_evidence,token,*,connector=http.client.HTTPSConnection):
        require(type(read_evidence) is RunEvidence and read_evidence.seal is _RUN_SEAL and read_evidence.live is True,'REAL_GITHUB_INPUT_PROOF_REQUIRED');self.token=token;self.connector=connector;self.calls=0;self.unknown=False;self.statuses=[]
    def __repr__(self):return '<ArtifactInput REDACTED>'
    def clear(self):self.token=None
    def download(self,artifact_id,archive_sha,*,allowed_names,output):
        require(self.calls+2<=6,'ARTIFACT_GET_BUDGET_STOP')
        require(not self.unknown and type(artifact_id) is int and artifact_id>0 and re.fullmatch('[a-f0-9]{64}',archive_sha),'ARTIFACT_TARGET_STOP')
        self.unknown=True;self.calls+=1
        c=self.connector('api.github.com',timeout=15)
        try:
            c.request('GET','/repos/'+REPO+'/actions/artifacts/'+str(artifact_id)+'/zip',headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json'})
            r=c.getresponse();self.statuses.append(r.status);require(r.status==302,'ARTIFACT_HANDOFF_HTTP_STOP');location=r.getheader('Location')
        except Exception:raise Stop('ARTIFACT_HANDOFF_UNKNOWN_STOP') from None
        finally:c.close()
        try:
            p=urlsplit(location);require(p.scheme=='https' and p.netloc==p.hostname and re.fullmatch(r'productionresultssa[0-9]+\.blob\.core\.windows\.net',p.hostname or '') and p.path.startswith('/actions-results/') and not p.fragment and len(location)<=8192,'ARTIFACT_STORAGE_UNVERIFIED_STOP')
            self.calls+=1;require(self.calls<=6,'ARTIFACT_GET_BUDGET_STOP')
            c=self.connector(p.hostname,timeout=15)
            try:
                c.request('GET',p.path+'?'+p.query) # NO token/Authorization on storage.
                r=c.getresponse();self.statuses.append(r.status);require(r.status==200,'ARTIFACT_STORAGE_HTTP_STOP')
                raw=r.read(16*1024*1024+1);require(len(raw)<=16*1024*1024 and hashlib.sha256(raw).hexdigest()==archive_sha,'ARTIFACT_ARCHIVE_SHA_STOP')
            finally:c.close()
            z=zipfile.ZipFile(io.BytesIO(raw));require(len(z.infolist())<=64,'ARTIFACT_MEMBER_BOUND_STOP')
            chosen={};total=0
            for name in allowed_names:
                matches=[i for i in z.infolist() if i.filename==name]
                require(len(matches)==1 and matches[0].file_size<=16*1024*1024 and (matches[0].external_attr>>16)&0o170000!=0o120000,'ARTIFACT_MEMBER_STOP')
                b=z.read(matches[0]);total+=len(b);require(total<=32*1024*1024,'ARTIFACT_BYTES_BOUND_STOP');chosen[name]=b
            out=Path(output);out.mkdir(parents=True,exist_ok=True)
            for n,b in chosen.items():
                require(re.fullmatch('[A-Za-z0-9_.-]+',n) and not (out/n).exists(),'ARTIFACT_NO_OVERWRITE_STOP')
                with (out/n).open('xb') as f:f.write(b)
            self.unknown=False;return out
        except Exception:raise Stop('ARTIFACT_INPUT_UNKNOWN_NO_RETRY') from None
