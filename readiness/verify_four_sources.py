import json
from pathlib import Path
from readiness.verify_final_sources import verify
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    verify(json.loads((ROOT/'readiness/four-connections-source-hashes.json').read_text()))
    print('FOUR_CONNECTION_SOURCE_HASHES_PASS')
