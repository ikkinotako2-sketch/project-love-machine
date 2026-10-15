"""Credential-preserving OFFLINE preparation. No native I/O or environment reads.

An existing Actions JSON secret supplies client_id/client_secret in memory.
A new refresh-token secret is opt-in, client-bound and never falls back.
CodeExchangeSimulation accepts only offline adapters; it cannot authorize live I/O.
"""
import hmac,json,re
from dataclasses import dataclass
from urllib.parse import urlencode
from ..ledger import Stop,require

EXISTING='PLM_YOUTUBE_GAME_001'
CANDIDATE='PLM_YOUTUBE_GAME_001_REFRESH_V2'
REDIRECT='https://developers.google.com/oauthplayground'
SCOPES=('https://www.googleapis.com/auth/youtube.upload','https://www.googleapis.com/auth/youtube.readonly')
CLIENT=re.compile(r'[0-9]+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com')

def text(value):
    return isinstance(value,str) and 0<len(value)<=16384 and all(32<ord(c)<127 for c in value)

def parse(raw,keys):
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise Stop('DUPLICATE_CREDENTIAL_FIELD_STOP')
            d[k]=v
        return d
    try:d=json.loads(raw,object_pairs_hook=unique)
    except Exception:raise Stop('CREDENTIAL_JSON_SHAPE_STOP') from None
    require(isinstance(d,dict) and set(d)==set(keys) and all(text(v) for v in d.values()),'CREDENTIAL_FIELDS_STOP')
    require(CLIENT.fullmatch(d['client_id']) is not None,'CLIENT_ID_SHAPE_STOP')
    return d

def combine_bundle(existing_raw,candidate_raw=None,*,use_candidate=False):
    """Return provider-compatible memory JSON fields, without modifying either input.
    Explicit selection, absent/mismatched candidate STOP; no old-token fallback.
    Strings are not logged or hashed. Caller clears references after provider use.
    """
    old=parse(existing_raw,('client_id','client_secret','refresh_token'))
    require(type(use_candidate) is bool,'CANDIDATE_SELECTION_STOP')
    if not use_candidate:
        require(candidate_raw is None,'UNAPPROVED_CANDIDATE_INPUT_STOP')
        return old
    require(candidate_raw is not None,'CANDIDATE_SECRET_MISSING_STOP')
    new=parse(candidate_raw,('client_id','refresh_token'))
    require(hmac.compare_digest(old['client_id'],new['client_id']),'CANDIDATE_CLIENT_MISMATCH_STOP')
    return {'client_id':old['client_id'],'client_secret':old['client_secret'],'refresh_token':new['refresh_token']}

@dataclass(frozen=True)
class ConsentContext:
    client_id:str
    state:str
    created_at:int
    expires_at:int
    def __repr__(self):return '<ConsentContext PUBLIC_CLIENT_STATE_REDACTED>'

def authorization_url(context):
    require(type(context) is ConsentContext and CLIENT.fullmatch(context.client_id) and re.fullmatch('[A-Za-z0-9_-]{43,128}',context.state),'CONSENT_CONTEXT_STOP')
    require(type(context.created_at) is int and type(context.expires_at) is int and context.created_at<context.expires_at<=context.created_at+300,'CONSENT_LOCAL_WINDOW_STOP')
    # Client secret is NOT an authorization-URL parameter. No code/token in URL.
    return 'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({'client_id':context.client_id,'redirect_uri':REDIRECT,'response_type':'code','scope':' '.join(SCOPES),'access_type':'offline','prompt':'consent','include_granted_scopes':'true','state':context.state})

class CodeExchangeSimulation:
    """Protocol fixture only: POST≤1, candidate save≤1, no retries or activation.
    Future real runner still needs separate approval/marker/history and Secret-writer
    authority. Scope match never proves channel match. Error bodies are discarded.
    """
    def __init__(self,post,save,clock):
        require(getattr(post,'offline_mock',False) is True and getattr(save,'offline_mock',False) is True,'PARKED_NATIVE_EXCHANGE_FORBIDDEN')
        self.post=post;self.save=save;self.clock=clock;self.used=False;self.posts=0;self.saves=0
    def __repr__(self):return '<CodeExchangeSimulation OFFLINE_ONLY REDACTED>'
    def run(self,existing_raw,code,returned_state,context):
        require(not self.used,'EXCHANGE_IDENTITY_CONSUMED');self.used=True
        authorization_url(context)
        now=self.clock();require(type(now) is int and context.created_at<=now<context.expires_at,'CONSENT_LOCAL_WINDOW_EXPIRED_STOP')
        require(isinstance(returned_state,str) and hmac.compare_digest(returned_state,context.state),'CONSENT_STATE_MISMATCH_STOP')
        old=parse(existing_raw,('client_id','client_secret','refresh_token'))
        require(hmac.compare_digest(old['client_id'],context.client_id) and text(code),'CONSENT_CLIENT_CODE_STOP')
        form=urlencode({'client_id':old['client_id'],'client_secret':old['client_secret'],'code':code,'grant_type':'authorization_code','redirect_uri':REDIRECT}).encode()
        candidate=None;payload=None
        try:
            self.posts+=1
            try:status,payload=self.post(form)
            except Exception:raise Stop('CODE_EXCHANGE_UNKNOWN_NO_RETRY') from None
            require(type(status) is int and status==200 and isinstance(payload,dict),'CODE_EXCHANGE_HTTP_STOP')
            require(text(payload.get('refresh_token')) and text(payload.get('access_token')),'NEW_REFRESH_TOKEN_MISSING_STOP')
            require(isinstance(payload.get('scope'),str),'GRANTED_SCOPE_UNKNOWN_STOP')
            require(set(SCOPES)<=set(payload['scope'].split()),'GRANTED_SCOPE_INSUFFICIENT_STOP')
            require(payload.get('token_type','').lower()=='bearer' and type(payload.get('expires_in')) is int and payload['expires_in']>180,'TOKEN_RESPONSE_SHAPE_STOP')
            candidate=json.dumps({'client_id':old['client_id'],'refresh_token':payload['refresh_token']},separators=(',',':'))
            self.saves+=1
            try:ack=self.save(CANDIDATE,candidate)
            except Exception:raise Stop('CANDIDATE_WRITE_UNKNOWN_NO_RETRY') from None
            require(ack=='CREATED','CANDIDATE_WRITE_UNKNOWN_NO_RETRY')
            return {'basis':'OFFLINE_CONTRACT','status':'CANDIDATE_SAVED_NOT_ACTIVATED','upload_scope':True,'readonly_scope':True,'channel_match':'UNVERIFIED','existing_secret_modified':False,'google_client_secrets_modified':False,'refresh_POST':0,'code_exchange_POST':self.posts,'candidate_save':self.saves}
        finally:
            old.clear();form=None;candidate=None;payload=None;code=None

def production_entry():
    return {'status':'PARKED','oauth_requests':0,'secret_operations':0,'identity_consumed':False}
