"""Future exact-repository Contents CAS transport; not invoked by workflows."""
import http.client,json
from .ledger import Stop,require
from .shared_lifecycle import GitContentsCAS
class StateHTTPTransport:
    def __init__(self,token,*,approved=False,max_gets=2,max_puts=6,connector=http.client.HTTPSConnection):
        require(approved is True and isinstance(token,str) and token and '\n' not in token and '\r' not in token and type(max_gets) is int and 0<max_gets<=2 and type(max_puts) is int and 0<max_puts<=6,'STATE_TRANSPORT_NOT_APPROVED')
        self.token=token;self.connector=connector;self.limits={'GET':max_gets,'PUT':max_puts};self.calls={'GET':0,'PUT':0};self.unknown=False
    def __repr__(self):return '<StateHTTPTransport REDACTED>'
    def clear(self):self.token=None
    def __call__(self,method,path,body):
        require(not self.unknown and self.token and method in self.limits and self.calls[method]<self.limits[method],'STATE_TRANSPORT_STOP')
        require(path==GitContentsCAS.PATH+('?ref='+GitContentsCAS.BRANCH if method=='GET' else ''),'STATE_TARGET_STOP')
        if method=='PUT':require(isinstance(body,dict) and body.get('branch')==GitContentsCAS.BRANCH and set(body)=={'branch','sha','message','content'},'STATE_BODY_STOP')
        self.calls[method]+=1;self.unknown=True;c=self.connector('api.github.com',timeout=15)
        try:
            c.request(method,path,body=None if body is None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','Content-Type':'application/json','User-Agent':'plm-shared-state'})
            r=c.getresponse()
            if r.status not in (200,201):return r.status,{}
            raw=r.read(65537);require(len(raw)<=65536,'STATE_RESPONSE_BOUND_STOP');p=json.loads(raw);self.unknown=False;return r.status,p
        except Exception:raise Stop('STATE_TRANSPORT_UNKNOWN_NO_RETRY') from None
        finally:c.close()
