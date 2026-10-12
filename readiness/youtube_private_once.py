"""Offline state boundary. No HTTP implementation or live CLI is provided."""
class Stop(Exception): pass
class PrivateOnce:
    def __init__(self, job_id, durable_claim, create_session, send_media):
        self.job_id=job_id;self.claim=durable_claim;self.start=create_session;self.send=send_media
        self.used=False
    def execute(self, proof, media_sha256):
        if self.used: raise Stop('CONSUMED_STOP')
        required=('channel_exact','rights_attested','render_quality_pass','upload_approved','source_pins_exact')
        if not all(proof.get(k) is True for k in required): raise Stop('PRE_GATE_STOP')
        if proof.get('privacy_status')!='private' or proof.get('notify_subscribers') is not False or proof.get('run_attempt')!=1: raise Stop('POLICY_STOP')
        if proof.get('job_id')!=self.job_id or proof.get('media_sha256')!=media_sha256: raise Stop('BINDING_STOP')
        # Durable create-if-absent must commit before *any* upload request.
        # An ambiguous claim is consumed locally and never followed by transport.
        self.used=True
        try:
            if self.claim(self.job_id,media_sha256) is not True: return 'CLAIM_STOP'
            session=self.start()
            ack=self.send(session)
            return 'UPLOAD_ACK_STOP' if ack is True else 'UNKNOWN_NO_RESEND'
        except Exception:
            return 'UNKNOWN_NO_RESEND'
if __name__=='__main__': print('OFFLINE_PARKED')
