"""Unconditionally parked candidate entrypoint. No credential or I/O imports."""
import json
def main():
    print(json.dumps({'status':'PARKED_APPROVAL_REQUIRED','oauth_posts':0,'youtube_requests':0,'state_writes':0,'dispatches':0,'deploys':0}))
if __name__=='__main__':main()
