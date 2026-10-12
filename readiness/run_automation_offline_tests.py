"""Deny all network APIs while running focused tests and mocks."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def deny(event,args):
    if event.startswith('socket.') or event in ('urllib.Request','http.client.connect'):raise RuntimeError('OFFLINE_NETWORK_FORBIDDEN')
def main():
    sys.addaudithook(deny)
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_automation*.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():raise SystemExit(1)
if __name__=='__main__':main()
