"""Offline source-drift gate. No network and no credential reads."""
import hashlib,json
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
def verify(manifest,root=ROOT):
    pins=manifest.get('source_sha256')
    if not isinstance(pins,dict) or not pins:raise ValueError('SOURCE_MANIFEST_STOP')
    for path,expected in pins.items():
        p=PurePosixPath(path)
        if p.is_absolute() or '..' in p.parts or str(p)!=path or (root/path).is_symlink():raise ValueError('SOURCE_PATH_STOP')
        if hashlib.sha256((root/path).read_bytes()).hexdigest()!=expected:raise ValueError('SOURCE_DRIFT_STOP')
    return True
if __name__=='__main__':
    verify(json.loads((ROOT/'readiness/final-candidate-source-hashes.json').read_text()))
    print('FINAL_CANDIDATE_SOURCE_HASHES_PASS')
