"""Real render artifact feeds upload mock and durable results; no remote APIs."""
import hashlib,json,pathlib,tempfile
from plm.automation.ledger import Ledger
from plm.automation.strict_upload import CHANNEL,ChannelSession,StrictUploader
from plm.automation.loop import OfflineLoop,mock
ROOT=pathlib.Path(__file__).resolve().parents[1]
class UploadMock:
    offline_mock=True
    def __init__(self,ledger):self.l=ledger;self.calls=[]
    def init(self,token,metadata,size):
        assert self.l.progress()['counts']['Processing']==1
        assert self.l.db.execute('SELECT count(*) FROM jobs WHERE sent=1').fetchone()[0]>=1
        assert metadata['status']['privacyStatus']=='private'
        self.calls.append('POST_MOCK');return 'OFFLINE_SESSION'
    def media(self,token,path,media):
        self.calls.append('PUT_MOCK');assert media.read(1)
        return 200,json.dumps({'id':'offline0001','snippet':{'channelId':CHANNEL},'status':{'privacyStatus':'private'}}).encode()

def run(media_path,evidence,output):
    output=pathlib.Path(output);output.mkdir(parents=True,exist_ok=True)
    plan=json.loads((ROOT/'readiness/youtube-automation-plan.json').read_text())
    with tempfile.TemporaryDirectory() as tmp:
        l=Ledger(pathlib.Path(tmp)/'simulation.sqlite');now=1791792000;transport=UploadMock(l)
        try:
            @mock
            def theme():return 'original-technical-test'
            @mock
            def script(topic):return {'topic':topic,'rights_verified':True,'narration':'offline generated test'}
            @mock
            def render(payload):return {'quality_pass':evidence['quality']['ok'],'media_sha256':evidence['media_sha256'],'path':str(media_path)}
            @mock
            def upload(claim,media):
                session=ChannelSession.from_mine_response('PUBLIC_OFFLINE_FIXTURE',200,json.dumps({'kind':'youtube#channelListResponse','items':[{'id':CHANNEL}]}).encode(),now+3600,lambda:now)
                identity='simulation-'+claim['job_id']
                proof={'upload_approved':True,'marker_consumed_before_remote':True,'marker_identity':identity,'source_pins_exact':True,'rights_verified':True,'quality_pass':True,'run_attempt':1,'job_id':claim['job_id'],'expected_channel_id':CHANNEL,'privacy_status':'private','notify_subscribers':False,'scheduled_for':'','made_for_kids':False,'contains_synthetic_media':True,'title':'offline fixture','description':'VOICEVOX:ずんだもん','media_sha256':media['media_sha256']}
                return StrictUploader(l,transport,lambda:now).upload(claim,identity,session,media_path,proof)
            @mock
            def metrics(result):return {'source':'OFFLINE_FIXTURE','views':0,'likes':0,'comments':0}
            loop=OfflineLoop(l,plan,theme=theme,script=script,render=render,upload_mock=upload,metrics_mock=metrics,clock=lambda:now)
            outcomes=[]
            for tick in range(24):
                try:outcomes.append(loop.tick('simulation-'+str(tick)))
                except Exception:break
                if loop.stopped:break
                now+=3600
            report={'mode':'OFFLINE_E2E','stages':{'theme':'PASS_MOCK','script':'PASS_MOCK','render':'PASS_REAL_ARTIFACT','reservation':'PASS_LOCAL_SQLITE','channel':'PASS_FIXTURE_ONLY_LIVE_UNVERIFIED','upload':'PASS_MOCK','results':'PASS_LOCAL_SQLITE','metrics':'PASS_MOCK','improvement':'PASS_EXISTING_RULES','next_job':'PASS_BOUNDED_SIMULATION'},'outcomes':outcomes,'progress':loop.report(),'transport_calls':transport.calls,'stop_reason':'DAILY_BUDGET_STOP','real_oauth_posts':0,'real_youtube_gets':0,'real_uploads':0,'cloudflare_requests':0,'channel_match_live':'UNVERIFIED'}
            assert transport.calls==['POST_MOCK','PUT_MOCK']*2 and l.progress()['counts']['Done']==2
            assert loop.stopped
            (output/'offline-e2e.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            (output/'progress.json').write_text(json.dumps(loop.report(),ensure_ascii=False,indent=2)+'\n')
            print(json.dumps({'offline_e2e':'PASS','mock_uploads':2,'budget_halt':True,'real_requests':0}))
            return report
        finally:l.close()
if __name__=='__main__':
    output=ROOT/'offline-evidence';e=json.loads((output/'render-evidence.json').read_text());run(output/'short.mp4',e,output)
