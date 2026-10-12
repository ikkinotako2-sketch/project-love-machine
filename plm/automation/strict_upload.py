"""Dedicated one-shot path: no status recovery, resume, redirect or refresh.
Legacy YouTubeRestApi stays byte-identical. Live CLI/workflow is absent.
"""
import hashlib
import http.client
import json
import os
import re
import time
import tempfile
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from .ledger import Stop,require
CHANNEL='UCJdTc1jznWNFlp0qy0SQ6uQ'
INIT='/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status&notifySubscribers=false'
LIMIT=32768

class ChannelSession:
    """Fresh mine response and upload token remain in one memory-only object."""
    def __init__(self,token,channel,expires_at,clock,*,_verified=False):
        require(_verified is True,'FRESH_CHANNEL_PROOF_REQUIRED')
        self._token=token;self.channel=channel;self.expires_at=expires_at;self.clock=clock
    def __repr__(self):return '<ChannelSession REDACTED>'
    @classmethod
    def from_mine_response(cls,token,status,body,expires_at,clock):
        require(status==200 and isinstance(body,bytes) and len(body)<=LIMIT,'CHANNEL_HTTP_STOP')
        def pairs(values):
            d={}
            for k,v in values:
                require(k not in d,'DUPLICATE_JSON_STOP');d[k]=v
            return d
        try:d=json.loads(body,object_pairs_hook=pairs)
        except Exception:raise Stop('CHANNEL_SHAPE_STOP') from None
        require(isinstance(d,dict) and d.get('kind')=='youtube#channelListResponse' and not d.get('nextPageToken') and not d.get('prevPageToken'),'CHANNEL_AMBIGUOUS_STOP')
        items=d.get('items');require(isinstance(items,list) and len(items)==1 and isinstance(items[0],dict) and items[0].get('id')==CHANNEL,'CHANNEL_MISMATCH_STOP')
        require(isinstance(token,str) and 0<len(token)<=16384 and all(32<ord(c)<127 for c in token),'TOKEN_SHAPE_STOP')
        require(type(expires_at) in (int,float) and expires_at>clock()+180,'TOKEN_EXPIRY_STOP')
        return cls(token,CHANNEL,expires_at,clock,_verified=True)
    def token(self):
        require(self._token is not None and self.expires_at>self.clock()+1,'AUTH_EXPIRED_STOP');return self._token
    def clear(self):self._token=None

def valid_location(location):
    require(isinstance(location,str) and len(location)<=4096 and all(32<ord(c)<127 for c in location),'LOCATION_STOP')
    p=urlsplit(location)
    require(p.scheme=='https' and p.netloc=='www.googleapis.com' and p.path=='/upload/youtube/v3/videos' and not p.fragment,'LOCATION_STOP')
    q=parse_qs(p.query,strict_parsing=True)
    require(set(q)<= {'upload_id','uploadType','part','notifySubscribers'} and len(q.get('upload_id',[]))==1 and re.fullmatch(r'[A-Za-z0-9_-]{1,2048}',q['upload_id'][0]) and all(len(v)==1 for v in q.values()),'LOCATION_STOP')
    return p.path+'?'+p.query

class HttpsSingleSend:
    """Explicitly injected future transport; never instantiated by an active workflow."""
    def __init__(self,*,operation_approved=False,connection=http.client.HTTPSConnection,clock=time.monotonic):
        require(operation_approved is True,'UPLOAD_NOT_APPROVED')
        self.connection=connection;self.clock=clock;self.calls=[];self.session=None
    def _open(self):return self.connection('www.googleapis.com',timeout=30)
    def init(self,token,metadata,size):
        require(self.calls==[],'SECOND_INIT_STOP');self.calls.append('POST')
        conn=self._open()
        try:
            conn.request('POST',INIT,body=json.dumps(metadata,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json; charset=UTF-8','X-Upload-Content-Length':str(size),'X-Upload-Content-Type':'video/mp4'})
            r=conn.getresponse()
            require(r.status==200,'INIT_HTTP_STOP')
            path=valid_location(r.getheader('Location'));self.session=path
            return path
        finally:conn.close()
    def media(self,token,path,media):
        require(self.calls==['POST'] and path==self.session,'MEDIA_POLICY_STOP');self.calls.append('PUT')
        conn=self._open();deadline=self.clock()+120
        try:
            conn.connect();conn.sock.settimeout(30)
            conn.putrequest('PUT',path);conn.putheader('Authorization','Bearer '+token)
            conn.putheader('Content-Type','video/mp4');conn.putheader('Content-Length',str(os.fstat(media.fileno()).st_size));conn.endheaders()
            while True:
                require(self.clock()<deadline,'UPLOAD_TIMEOUT_STOP')
                conn.sock.settimeout(min(30,max(.001,deadline-self.clock())))
                block=media.read(1024*1024)
                if not block:break
                conn.send(block)
            conn.sock.settimeout(min(30,max(.001,deadline-self.clock())))
            response=conn.getresponse();status=response.status
            if status not in (200,201):return status,b'' # no remote error read
            blocks=[];size=0
            while True:
                require(self.clock()<deadline,'UPLOAD_TIMEOUT_STOP')
                conn.sock.settimeout(min(30,max(.001,deadline-self.clock())))
                b=response.read1(min(4096,LIMIT+1-size))
                if not b:break
                blocks.append(b);size+=len(b);require(size<=LIMIT,'ACK_BOUND_STOP')
            return status,b''.join(blocks)
        finally:conn.close()

class StrictUploader:
    def __init__(self,ledger,transport,clock):self.ledger=ledger;self.transport=transport;self.clock=clock
    def upload(self,claim,operation,session,media_path,proof):
        try:return self._upload(claim,operation,session,media_path,proof)
        finally:
            if isinstance(session,ChannelSession):session.clear()
    def _upload(self,claim,operation,session,media_path,proof):
        # Everything reversible is checked before durable consumption.
        require(isinstance(session,ChannelSession) and session.channel==CHANNEL,'CHANNEL_PROOF_STOP')
        require(proof.get('upload_approved') is True and proof.get('marker_consumed_before_remote') is True and proof.get('marker_identity')==operation,'MARKER_APPROVAL_STOP')
        require(all(proof.get(k) is True for k in ('source_pins_exact','rights_verified','quality_pass')),'PRE_GATE_STOP')
        require(proof.get('run_attempt')==1 and type(proof.get('run_attempt')) is int and proof.get('job_id')==claim['job_id'],'RUN_BINDING_STOP')
        require(proof.get('expected_channel_id')==CHANNEL and proof.get('privacy_status')=='private' and proof.get('notify_subscribers') is False and proof.get('scheduled_for')=='','PRIVATE_POLICY_STOP')
        require(type(proof.get('made_for_kids')) is bool and type(proof.get('contains_synthetic_media')) is bool,'AUDIENCE_STOP')
        require(isinstance(proof.get('title'),str) and 0<len(proof['title'])<=100 and isinstance(proof.get('description'),str) and len(proof['description'])<=5000,'METADATA_STOP')
        p=Path(media_path);require(p.is_file() and not p.is_symlink(),'MEDIA_PATH_STOP')
        with p.open('rb') as original,tempfile.TemporaryFile() as media:
            before=os.fstat(original.fileno());require(10000<=before.st_size<=16*1024*1024,'MEDIA_BOUND_STOP')
            h=hashlib.sha256();size=0
            for chunk in iter(lambda:original.read(1024*1024),b''):
                size+=len(chunk);require(size<=16*1024*1024,'MEDIA_BOUND_STOP');h.update(chunk);media.write(chunk)
            require(size==before.st_size and h.hexdigest()==proof.get('media_sha256'),'MEDIA_SHA_STOP');media.flush();media.seek(0)
            before=os.fstat(media.fileno())
            token=session.token()
            metadata={'snippet':{'title':proof['title'],'description':proof['description']},'status':{'privacyStatus':'private','selfDeclaredMadeForKids':proof['made_for_kids'],'containsSyntheticMedia':proof['contains_synthetic_media']}}
            self.ledger.consume(claim,operation,self.clock())
            try:
                path=self.transport.init(token,metadata,before.st_size)
                # Detect drift between hash and transport; never restart session.
                after=os.fstat(media.fileno());require((after.st_size,after.st_mtime_ns)==(before.st_size,before.st_mtime_ns),'MEDIA_DRIFT_STOP')
                status,body=self.transport.media(token,path,media)
                require(status in (200,201) and isinstance(body,bytes) and len(body)<=LIMIT,'ACK_HTTP_STOP')
                def pairs(values):
                    d={}
                    for k,v in values:require(k not in d,'ACK_DUPLICATE_STOP');d[k]=v
                    return d
                ack=json.loads(body,object_pairs_hook=pairs)
                require(isinstance(ack,dict) and re.fullmatch(r'[A-Za-z0-9_-]{11}',ack.get('id','')) and ack.get('snippet',{}).get('channelId')==CHANNEL and ack.get('status',{}).get('privacyStatus')=='private','ACK_BINDING_STOP')
                return self.ledger.finish(claim,'Done',video_id=ack['id'])
            except Exception:
                return self.ledger.finish(claim,'UNKNOWN',reason='UPLOAD_UNKNOWN')
            finally:session.clear();token=None

def main():print(json.dumps({'status':'PARKED','upload_requests':0}))
if __name__=='__main__':main()
