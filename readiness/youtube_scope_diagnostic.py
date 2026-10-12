"""Grant scope metadata only. Existing token provider/wrapper reused unchanged."""
import json,re
from readiness import youtube_oauth_verify as auth
IDENTITY='provider-neutral-youtube-oauth-scope-diagnostic-20261012-r1'
BASE='https://www.googleapis.com/auth/'
READ={BASE+'youtube',BASE+'youtube.force-ssl',BASE+'youtube.readonly',BASE+'youtubepartner',BASE+'youtubepartner-channel-audit'}
UPLOAD={BASE+'youtube',BASE+'youtube.force-ssl',BASE+'youtube.upload',BASE+'youtubepartner'}
ANALYTICS={BASE+'yt-analytics.readonly',BASE+'yt-analytics-monetary.readonly'}
class ScopeOpener(auth.BoundedOpener):
    def __init__(self,transport):
        self.bits=None
        def capture(form):
            status,raw=transport(form)
            if type(status) is int and 100<=status<=599:self.http_status=status
            if status==200 and isinstance(raw,bytes) and len(raw)<=auth.LIMIT:
                data=auth.exact_json(raw)
                auth.need(isinstance(data,dict),'SCOPE_SHAPE_STOP')
                if 'scope' in data:
                    scope=data['scope']
                    auth.need(isinstance(scope,str) and 0<len(scope)<=4096 and re.fullmatch(r'[\x21\x23-\x5b\x5d-\x7e]+(?: [\x21\x23-\x5b\x5d-\x7e]+)*',scope),'SCOPE_SHAPE_STOP')
                    values=set(scope.split(' '))
                    self.bits={'channels_read':bool(values&READ),'youtube_upload':bool(values&UPLOAD),'analytics_read':bool(values&ANALYTICS),'audit_only_read':BASE+'youtubepartner-channel-audit' in values and not values&(READ-{BASE+'youtubepartner-channel-audit'})}
                    # Audit-only grant is not accepted as routine channel-read approval.
                    if self.bits['audit_only_read']:self.bits['channels_read']=False
                data.clear()
            return status,raw
        super().__init__(capture)

def diagnose(raw_secret,transport):
    out={'identity':IDENTITY,'classification':'SCOPE_DIAGNOSTIC_BLOCKED','reason_code':'CREDENTIAL_STOP','scope_present':False,'channels_read':None,'youtube_upload':None,'analytics_read':None,'refresh_posts':0,'http_status':None,'tokeninfo_requests':0,'youtube_requests':0,'retry':0,'redirect':0,'fallback':0,'raw_retention':0,'secret_exposure':0}
    provider=None;bundle=None;opener=ScopeOpener(transport)
    try:
        auth.need(isinstance(raw_secret,str) and 0<len(raw_secret.encode())<=auth.LIMIT,'CREDENTIAL_STOP')
        bundle=auth.exact_json(raw_secret)
        auth.need(isinstance(bundle,dict) and all(isinstance(bundle.get(k),str) and 0<len(bundle[k])<=8192 for k in auth.FIELDS-{'grant_type'}),'CREDENTIAL_STOP')
        provider=auth.BundleProvider({k:bundle[k] for k in auth.FIELDS-{'grant_type'}},opener)
        bundle.clear();raw_secret=None
        out['reason_code']='OAUTH_HTTP_OR_RESPONSE_STOP'
        token=provider.get_access_token();token=None
        if opener.bits is None:
            out.update(classification='UNKNOWN_SCOPE_NOT_REPORTED_STOP',reason_code='SCOPE_FIELD_ABSENT')
        else:
            out.update({k:opener.bits[k] for k in ['channels_read','youtube_upload','analytics_read']})
            out.update(scope_present=True,reason_code=None,classification='SCOPE_CONFIRMED_STOP_BEFORE_CHANNEL' if out['channels_read'] and out['youtube_upload'] else 'SCOPE_MISSING_REAUTH_REQUIRED_STOP')
    except Exception:pass # Never stringify exception/credential/remote response.
    finally:
        raw_secret=None
        if isinstance(bundle,dict):bundle.clear()
        if provider:provider._token=None;provider.bundle.clear()
        opener.bits=None
        out['refresh_posts']=opener.calls;out['http_status']=opener.http_status
    return out
if __name__=='__main__':print(json.dumps({'identity':IDENTITY,'status':'OFFLINE_PARKED','refresh_posts':0}))
