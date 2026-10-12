"""One refresh and one channels.mine read; injected transports, no upload imports."""
import http.client
import json
import time
from readiness import youtube_oauth_verify as auth
EXPECTED = 'UCJdTc1jznWNFlp0qy0SQ6uQ'
PATH = '/youtube/v3/channels?part=id&mine=true&maxResults=50'
refresh_transport = auth.authorized_https_transport

def channel_transport(token):
    conn = http.client.HTTPSConnection('www.googleapis.com', timeout=30)
    deadline = time.monotonic() + 30
    try:
        conn.connect()
        conn.sock.settimeout(max(0.001, deadline-time.monotonic()))
        conn.request('GET', PATH, headers={'Authorization':'Bearer '+token})
        conn.sock.settimeout(max(0.001, deadline-time.monotonic()))
        response=conn.getresponse()
        if response.status != 200: return response.status,b''
        chunks=[];size=0
        while True:
            left=deadline-time.monotonic()
            if left<=0: raise TimeoutError()
            conn.sock.settimeout(left)
            chunk=response.read1(min(4096,auth.LIMIT+1-size))
            if not chunk: break
            chunks.append(chunk);size+=len(chunk)
            if size>auth.LIMIT: raise ValueError()
        return 200,b''.join(chunks)
    finally: conn.close()

def verify(raw_bundle, refresh, channels):
    out={'classification':'CHANNEL_VERIFY_BLOCKED','reason_code':'LOCAL_CREDENTIAL_STOP',
         'expected_channel_id':EXPECTED,'channel_match':False,'refresh_posts':0,'channel_gets':0,
         'oauth_http_status':None,'channel_http_status':None,'retry':0,'redirect':0,'fallback':0,
         'raw_retention':0,'uploads':0,'publishes':0,'secret_exposure':0}
    provider=None;token=None;bundle=None;opener=auth.BoundedOpener(refresh)
    try:
        auth.need(isinstance(raw_bundle,str) and 0<len(raw_bundle.encode())<=auth.LIMIT,'CREDENTIAL_STOP')
        bundle=auth.exact_json(raw_bundle)
        auth.need(isinstance(bundle,dict) and all(isinstance(bundle.get(k),str) and 0<len(bundle[k])<=8192 for k in auth.FIELDS-{'grant_type'}),'CREDENTIAL_STOP')
        provider=auth.BundleProvider({k:bundle[k] for k in auth.FIELDS-{'grant_type'}},opener)
        bundle.clear();raw_bundle=None
        out['reason_code']='OAUTH_STOP'
        token=provider.get_access_token()
        out['reason_code']='CHANNEL_TRANSPORT_UNKNOWN_STOP'
        out['channel_gets']=1
        status,raw=channels(token)
        auth.need(type(status) is int and 100<=status<=599,'HTTP_STOP')
        out['channel_http_status']=status
        out['reason_code']='CHANNEL_HTTP_STOP'
        auth.need(status==200,'HTTP_STOP')
        out['reason_code']='CHANNEL_SHAPE_STOP'
        auth.need(isinstance(raw,bytes) and len(raw)<=auth.LIMIT,'BOUND_STOP')
        data=auth.exact_json(raw);raw=None
        auth.need(isinstance(data,dict) and data.get('kind')=='youtube#channelListResponse','SHAPE_STOP')
        auth.need(not data.get('nextPageToken') and not data.get('prevPageToken'),'PAGINATION_STOP')
        items=data.get('items');auth.need(isinstance(items,list),'SHAPE_STOP')
        out['reason_code']='CHANNEL_MISMATCH_OR_AMBIGUOUS_STOP'
        auth.need(len(items)==1 and isinstance(items[0],dict) and items[0].get('id')==EXPECTED,'MISMATCH_STOP')
        if 'pageInfo' in data:
            pi=data['pageInfo'];auth.need(isinstance(pi,dict) and type(pi.get('totalResults')) is int and pi['totalResults']==1,'SHAPE_STOP')
        out.update(classification='YOUTUBE_CHANNEL_EXACT_MATCH_STOP_BEFORE_UPLOAD',channel_match=True,reason_code=None)
    except Exception: pass # Fixed local code only; never exception text or remote body.
    finally:
        token=None;raw_bundle=None
        if isinstance(bundle,dict): bundle.clear()
        if provider: provider._token=None;provider.bundle.clear()
        out['refresh_posts']=opener.calls;out['oauth_http_status']=opener.http_status
    return out

if __name__=='__main__':
    print(json.dumps({'classification':'OFFLINE_PARKED','refresh_posts':0,'channel_gets':0}))
