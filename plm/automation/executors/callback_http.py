"""Sole result callback to one reviewed HTTPS origin. No bearer or redirects."""
import http.client,re
from .authority import live_authority
from ..ledger import require,Stop
class CallbackHTTP:
    offline_mock=False
    def __init__(self,permit,origin,*,connector=http.client.HTTPSConnection):
        live_authority(permit);require(permit.operation=='finalize','CALLBACK_ROLE_STOP');require(re.fullmatch('[a-z0-9][a-z0-9.-]{1,250}',str(origin)),'CALLBACK_ORIGIN_STOP')
        self.origin=origin;self.used=False;self.connector=connector;self.statuses=[]
    def clear(self):pass
    def __call__(self,url,raw,signature):
        if isinstance(raw,str):raw=raw.encode('utf-8')
        require(not self.used and url=='https://'+self.origin+'/youtube/result' and isinstance(raw,bytes) and len(raw)<=8192 and re.fullmatch('[a-f0-9]{64}',signature),'CALLBACK_FIXED_ROUTE_STOP')
        self.used=True;c=self.connector(self.origin,timeout=15)
        try:
            c.request('POST','/youtube/result',body=raw,headers={'Content-Type':'application/json','X-PLM-Signature':signature})
            response=c.getresponse();self.statuses.append(response.status);return response.status # body/headers never retained
        except Exception:raise Stop('CALLBACK_HTTP_UNKNOWN_NO_RETRY') from None
        finally:c.close()
