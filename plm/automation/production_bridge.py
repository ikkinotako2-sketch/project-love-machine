"""Future GitHub durable claim and Actions composition, all I/O injected.
No default transport, credentials, dispatch, or executable live CLI.
"""
import hashlib,json,re
from .ledger import require,Stop,ID
from .strict_upload import StrictUploader,CHANNEL
READ='https://www.googleapis.com/auth/youtube.readonly'
UPLOAD='https://www.googleapis.com/auth/youtube.upload'
MEDIA='4157384237670fb10ffd83de891d2d207003367601bc5970b0c6a37b13ff2110'
def digest(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def scope_gate(scopes,proven):
    require(proven is True and isinstance(scopes,list),'GRANTED_SCOPES_UNVERIFIED_STOP')
    require(any(s in scopes for s in [READ,'https://www.googleapis.com/auth/youtube','https://www.googleapis.com/auth/youtube.force-ssl']),'CHANNEL_SCOPE_MISSING_STOP')
    require(UPLOAD in scopes or 'https://www.googleapis.com/auth/youtube' in scopes or 'https://www.googleapis.com/auth/youtube.force-ssl' in scopes,'UPLOAD_SCOPE_MISSING_STOP')
    return True
class GitClaimLedger:
    """Contents API create/CAS semantics; record branch is separate from main.
    Backend contract: read(path)->(sha, record)|None; write(path,expected_sha,record)
    ->new_sha. Missing expected_sha means create-if-absent (409 is STOP).
    Remote uncertainty is never retried or resolved by a second write.
    """
    def __init__(self,backend,branch):
        require(branch=='plm-execution-state','STATE_BRANCH_STOP');self.backend=backend;self.branch=branch;self.rows={};self.uncertain=False
    def write(self,path,sha,record):
        require(not self.uncertain,"STATE_WRITE_UNKNOWN_STOP")
        self.uncertain=True
        new_sha=self.backend.write(path,sha,record)
        require(isinstance(new_sha,str) and re.fullmatch("[a-f0-9]{40}",new_sha),"STATE_WRITE_UNKNOWN_STOP")
        self.uncertain=False;return new_sha
    def path(self,job):require(ID.fullmatch(job),'JOB_STOP');return 'youtube-once/'+job+'.json'
    def claim(self,job,fingerprint,identity,owner,now):
        require(not self.uncertain,'STATE_WRITE_UNKNOWN_STOP')
        path=self.path(job);require(ID.fullmatch(identity) and ID.fullmatch(owner) and re.fullmatch('[a-f0-9]{64}',fingerprint),'CLAIM_SHAPE_STOP')
        try:existing=self.backend.read(path)
        except Exception:
            self.uncertain=True
            raise Stop('STATE_READ_UNKNOWN_STOP') from None
        require(existing is None,'PERMANENTLY_CONSUMED_STOP')
        record={'job_id':job,'fingerprint':fingerprint,'identity':identity,'owner':owner,'epoch':1,'fence':1,'state':'Processing','sent':False,'created_at':now,'reason_code':None,'video_id':None}
        # This durable claim consumes the identity even if later gates fail.
        sha=self.write(path,None,record);require(isinstance(sha,str) and re.fullmatch('[a-f0-9]{40}',sha),'CLAIM_WRITE_UNKNOWN_STOP')
        self.rows[job]=(sha,record);return dict(record)
    def consume(self,claim,identity,now):
        sha,row=self.rows[claim['job_id']]
        require(row['state']=='Processing' and row['sent'] is False and row['identity']==identity and all(row[k]==claim[k] for k in ['owner','epoch','fence','fingerprint']),'CLAIM_CAS_STOP')
        updated={**row,'sent':True}
        next_sha=self.write(self.path(row['job_id']),sha,updated)
        require(isinstance(next_sha,str) and re.fullmatch('[a-f0-9]{40}',next_sha),'SENT_WRITE_UNKNOWN_STOP')
        self.rows[row['job_id']]=(next_sha,updated)
    def finish(self,claim,state,video_id=None,reason=None):
        sha,row=self.rows[claim['job_id']];require(state in ['Done','UNKNOWN','Failed'] and row['state']=='Processing','TERMINAL_STOP')
        require(video_id is None or re.fullmatch('[A-Za-z0-9_-]{11}',video_id),'VIDEO_STOP')
        require(reason in [None,'UPLOAD_UNKNOWN','AUTH_STOP','RENDER_FAILED'],'REASON_STOP')
        updated={**row,'state':state,'video_id':video_id,'reason_code':reason,'notification_pending':state!='Done'}
        next_sha=self.write(self.path(row['job_id']),sha,updated)
        require(isinstance(next_sha,str) and re.fullmatch('[a-f0-9]{40}',next_sha),'RESULT_WRITE_UNKNOWN_STOP')
        self.rows[row['job_id']]=(next_sha,updated)
        return {k:updated[k] for k in ['job_id','state','video_id','reason_code']}
    def get(self,job):return self.rows[ job ][1].copy()

def media_gate(path,evidence,job):
    require(job['job_id']=='plm-private-channel-recovery-20261012-r1' and job['expected_channel_id']==CHANNEL,'JOB_BINDING_STOP')
    require(job['privacy_status']=='private' and job['notify_subscribers'] is False and job['made_for_kids'] is False and job['contains_synthetic_media'] is True,'PRIVACY_AUDIENCE_STOP')
    require(job['credit']=='VOICEVOX:ずんだもん' and job['credit'] in job['description'] and job['sentences']==['これは非公開の動作確認動画です。','画面と音声の同期を確認しています。','この動画を公開する予定はありません。'],'CONTENT_CREDIT_STOP')
    quality=evidence['quality'];require(quality['ok'] is True and (quality['width'],quality['height'],quality['fps'])==(1080,1920,30) and quality['subtitles'] is True and quality['audio_codec']=='aac','QUALITY_STOP')
    require(evidence.get('voice_style_verified') is True and evidence['voice']==job['credit'],'VOICE_STOP')
    timings=evidence['timing'];require(len(timings)==3 and [x['text'] for x in timings]==job['sentences'] and timings[0]['start_seconds']==0 and all(0<x['end_seconds']-x['start_seconds']<10 for x in timings) and all(abs(timings[i]['end_seconds']-timings[i+1]['start_seconds'])<.001 for i in [0,1]),'CAPTION_TIMING_STOP')
    require(evidence['media_sha256']==MEDIA and hashlib.sha256(path.read_bytes()).hexdigest()==MEDIA,'MEDIA_HASH_STOP')
    return True

def execute_private(*,scope_evidence,gate,media,evidence,job,session_factory,ledger,upload_transport,callback,clock,run):
    """Gate and media validation precede any OAuth; callback never repeats upload."""
    scope_gate(scope_evidence['scopes'],scope_evidence['proven'])
    require(gate() is True and type(run['attempt']) is int and run['attempt']==1 and isinstance(run['id'],str) and re.fullmatch('[1-9][0-9]{0,19}',run['id']) and re.fullmatch('[a-f0-9]{40}',run['sha']) and run['sha']==run['approved_sha'],'PROVENANCE_STOP')
    media_gate(media,evidence,job)
    identity=job['upload_identity'];claim=ledger.claim(job['job_id'],digest(job),identity,'actions-'+run['id'],clock())
    session=None
    try:
        # Future provider wrapper must mint a fresh ChannelSession from same token.
        session=session_factory()
        proof={**job,'media_sha256':MEDIA,'source_pins_exact':True,'rights_verified':True,'quality_pass':True,'upload_approved':True,'marker_consumed_before_remote':True,'marker_identity':identity,'run_attempt':1}
        result=StrictUploader(ledger,upload_transport,clock).upload(claim,identity,session,media,proof)
    except Exception:
        require(not getattr(ledger,'uncertain',False),'STATE_WRITE_UNKNOWN_STOP')
        row=ledger.get(job['job_id'])
        if row['state']!='Processing':raise Stop('PERMANENT_STOP') from None
        if row['sent']:raise Stop('STATE_UNKNOWN_PERMANENT_STOP') from None
        result=ledger.finish(claim,'Failed',reason='AUTH_STOP')
    finally:
        if session:session.clear()
    # Separate callback exactly once. Failure is a delivery blocker, not reupload.
    try: callback(result,run)
    except Exception:return {**result,'callback':'UNKNOWN_NO_RETRY'}
    return {**result,'callback':'ACK'}

class GitHubContentsBackend:
    """Future bounded repository-scoped state I/O; caller injects credentials.
    No invocation in CI; no branch creation or main writes supported.
    """
    def __init__(self,transport):self.transport=transport;self.calls=0
    def request(self,method,path,body=None):
        require(not getattr(self,'uncertain',False),'STATE_IO_UNKNOWN_STOP')
        pattern=r'/repos/ikkinotako2-sketch/project-love-machine/contents/youtube-once/[A-Za-z0-9][A-Za-z0-9._-]{0,63}\.json'
        require(self.calls<4 and method in ['GET','PUT'] and re.fullmatch(pattern+(r'\?ref=plm-execution-state' if method=='GET' else ''),path),'GITHUB_REQUEST_STOP')
        self.uncertain=True
        self.calls+=1;status,payload=self.transport(method,path,body)
        if method=='GET' and status==404:self.uncertain=False;return None
        require(status in [200,201] and isinstance(payload,dict),'GITHUB_HTTP_STOP')
        if method=='PUT':require(re.fullmatch('[a-f0-9]{40}',str(payload.get('content',{}).get('sha',''))),'STATE_WRITE_UNKNOWN_STOP')
        self.uncertain=False
        return payload
    def read(self,path):
        require(path.startswith('youtube-once/') and ID.fullmatch(path.removeprefix('youtube-once/').removesuffix('.json')),'STATE_PATH_STOP')
        data=self.request('GET','/repos/ikkinotako2-sketch/project-love-machine/contents/'+path+'?ref=plm-execution-state')
        if data is None:return None
        require(isinstance(data.get('sha'),str) and re.fullmatch('[a-f0-9]{40}',data['sha']),'STATE_SHAPE_STOP')
        # Any pre-existing record is permanently consumed; no body/secret parsing.
        return data['sha'],{'state':'CONSUMED'}
    def write(self,path,sha,row):
        import base64
        require(path.startswith('youtube-once/') and ID.fullmatch(path.removeprefix('youtube-once/').removesuffix('.json')),'STATE_PATH_STOP')
        body={'branch':'plm-execution-state','message':'PLM once state '+row['job_id'],'content':base64.b64encode(json.dumps(row,sort_keys=True).encode()).decode()}
        if sha is not None:body['sha']=sha
        data=self.request('PUT','/repos/ikkinotako2-sketch/project-love-machine/contents/'+path,body)
        return data.get('content',{}).get('sha')

class ExclusiveGitClaimLedger(GitClaimLedger):
    """One private-test operation per durable state initialization.

    Create-if-absent global tombstone BEFORE any job claim. Never released,
    deleted or retried. A lost create ACK is fenced by the stored tombstone on
    another runner. Two backend instances share the same repository transport;
    the guard uses at most 2 requests and the existing job path at most 4.
    This is not an automatically reusable scheduler lock.
    """
    def __init__(self,backend,guard_backend,branch):
        super().__init__(backend,branch);self.guard=guard_backend;self.guard_acquired=False
    def claim(self,job,fingerprint,identity,owner,now):
        require(not self.guard_acquired and not self.uncertain,'EXCLUSIVE_OPERATION_CONSUMED_STOP')
        self.path(job)
        require(isinstance(identity,str) and ID.fullmatch(identity) and isinstance(owner,str) and ID.fullmatch(owner) and isinstance(fingerprint,str) and re.fullmatch('[a-f0-9]{64}',fingerprint) and type(now) is int and now>0,'CLAIM_SHAPE_STOP')
        self.uncertain=True
        path='youtube-once/exclusive-private-test.json'
        try:
            require(self.guard.read(path) is None,'EXCLUSIVE_OPERATION_CONSUMED_STOP')
            sha=self.guard.write(path,None,{'job_id':'exclusive-private-test','identity':identity,'state':'CONSUMED_BEFORE_JOB_CLAIM','target_job_id':job,'owner':owner,'created_at':now})
            require(isinstance(sha,str) and re.fullmatch('[a-f0-9]{40}',sha),'EXCLUSIVE_WRITE_UNKNOWN_STOP')
        except Exception:raise Stop('EXCLUSIVE_OPERATION_STOP_NO_RETRY') from None
        self.guard_acquired=True;self.uncertain=False
        return super().claim(job,fingerprint,identity,owner,now)

class BoundedGitHubTransport:
    def __init__(self,token,*,approved=False,connector=None):
        require(approved is True and isinstance(token,str) and token and '\n' not in token and '\r' not in token,'STATE_IO_NOT_APPROVED')
        self._token=token;self.connector=connector
    def __repr__(self):return '<BoundedGitHubTransport REDACTED>'
    def clear(self):self._token=None
    def __call__(self,method,path,body):
        import http.client
        require(self._token is not None and method in ['GET','PUT'] and path.startswith('/repos/ikkinotako2-sketch/project-love-machine/contents/youtube-once/'),'STATE_TRANSPORT_STOP')
        conn=(self.connector or http.client.HTTPSConnection)('api.github.com',timeout=20)
        try:
            conn.request(method,path,body=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+self._token,'Accept':'application/vnd.github+json','Content-Type':'application/json','User-Agent':'plm-once-state'})
            response=conn.getresponse()
            if response.status not in [200,201]:return response.status,{} # never read error body
            raw=response.read(32769);require(len(raw)<=32768,'STATE_BOUND_STOP')
            return response.status,json.loads(raw)
        finally:conn.close()
