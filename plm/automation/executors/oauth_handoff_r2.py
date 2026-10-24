"""Strict memory-only handoff parsing. Never repair, echo or fingerprint input."""
import json
from .oauth_reuse import text
from ..ledger import Stop, require

KEYS = {'client_id', 'code', 'state', 'redirect_uri', 'issued_at'}

def parse_handoff(raw):
    require(isinstance(raw, str) and 0 < len(raw) <= 65536, 'HANDOFF_INPUT_SIZE_STOP')
    try:
        raw.encode('utf-8', errors='strict')
    except UnicodeError:
        raise Stop('HANDOFF_ENCODING_STOP') from None
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'HANDOFF_DUPLICATE_KEY_STOP')
            result[key] = value
        return result
    def constant(_):
        raise Stop('HANDOFF_JSON_CONSTANT_STOP')
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except Stop:
        raise
    except (ValueError, TypeError, RecursionError):
        raise Stop('HANDOFF_JSON_SYNTAX_STOP') from None
    require(isinstance(value, dict) and set(value) == KEYS, 'HANDOFF_FIELDS_STOP')
    require(all(text(value[k]) for k in KEYS - {'issued_at'}), 'HANDOFF_STRING_STOP')
    require(type(value['issued_at']) is int and value['issued_at'] > 0, 'HANDOFF_TIME_TYPE_STOP')
    return value
