"""Successor voice/render contract; legacy speaker=1 paths are untouched."""
import hashlib,json
from .ledger import require
from .production_bridge import MEDIA
VOICE={'engine':'VOICEVOX','speaker_id':3,'voice_name':'ずんだもん','style_name':'ノーマル'}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def inventory_gate(speakers):
    matches=[(s.get('name'),t.get('name')) for s in speakers for t in s.get('styles',[]) if t.get('id')==3]
    require(matches==[('ずんだもん','ノーマル')],'VOICE_MODEL_STYLE_STOP');return True
def contract(script_raw,*,mode,voice,media_sha=None,audio_sha=None,caption_sha=None):
    require(mode in ('NEW_RENDER','REUSE_PINNED') and voice==VOICE,'RENDER_VOICE_MODE_STOP')
    script=json.loads(script_raw)
    require(isinstance(script.get('narration'),str) and script['narration']==''.join(s['caption'] for s in script['scenes']),'SCRIPT_CAPTION_STOP')
    for value in (media_sha,audio_sha,caption_sha):
        require(value is None or __import__('re').fullmatch('[a-f0-9]{64}',value),'RENDER_HASH_SHAPE_STOP')
    if mode=='REUSE_PINNED':require(media_sha==MEDIA and audio_sha is not None and caption_sha is not None,'REUSE_ASSET_STOP')
    return {'version':1,'mode':mode,'voice':VOICE,'script_sha256':sha(script_raw.encode()),'media_sha256':media_sha,'audio_sha256':audio_sha,'caption_sha256':caption_sha}
def render_gate(c,*,script_raw,voice_inventory,media,audio,captions,evidence):
    inventory_gate(voice_inventory)
    require(c['voice']==VOICE and c['script_sha256']==sha(script_raw.encode()),'SCRIPT_VOICE_BINDING_STOP')
    require(evidence.get('voice')==VOICE and evidence.get('script_sha256')==c['script_sha256'] and evidence.get('quality_pass') is True,'RENDER_EVIDENCE_STOP')
    actual={'media_sha256':sha(media),'audio_sha256':sha(audio),'caption_sha256':sha(captions)}
    require(all(evidence.get(k)==v for k,v in actual.items()),'RENDER_BYTES_STOP')
    if c['mode']=='REUSE_PINNED':require(all(c[k]==v for k,v in actual.items()) and actual['media_sha256']==MEDIA,'REUSE_ASSET_STOP')
    else:require(c['mode']=='NEW_RENDER' and evidence.get('render_mode')=='NEW_RENDER','NEW_RENDER_PROOF_STOP')
    return {**c,**actual}
