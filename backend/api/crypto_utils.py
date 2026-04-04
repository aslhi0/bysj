import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

ENC_PREFIX = 'enc:'
MASK = '******'

DEFAULT_SENSITIVE_KEYS = {
    'password',
    'passwd',
    'pwd',
    'token',
    'access_token',
    'refresh_token',
    'secret',
    'client_secret',
    'api_key',
    'apikey',
    'authorization',
}

def _derive_key():
    raw = (getattr(settings, 'SECRET_KEY', '') or '').encode('utf-8')
    digest = hashlib.sha256(raw).digest()
    return base64.urlsafe_b64encode(digest)

def get_fernet():
    return Fernet(_derive_key())

def is_encrypted(value):
    return isinstance(value, str) and value.startswith(ENC_PREFIX)

def encrypt_str(value):
    if value is None:
        return value
    if not isinstance(value, str):
        value = str(value)
    if is_encrypted(value):
        return value
    token = get_fernet().encrypt(value.encode('utf-8')).decode('utf-8')
    return f'{ENC_PREFIX}{token}'

def decrypt_str(value):
    if value is None:
        return value
    if not is_encrypted(value):
        return value
    token = value[len(ENC_PREFIX):]
    try:
        return get_fernet().decrypt(token.encode('utf-8')).decode('utf-8')
    except InvalidToken:
        return value

def _walk(obj, *, fn, parent_key=None):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            out[k] = _walk(v, fn=fn, parent_key=str(k))
        return out
    if isinstance(obj, list):
        return [_walk(v, fn=fn, parent_key=parent_key) for v in obj]
    return fn(obj, parent_key)

def encrypt_json(obj, sensitive_keys=None):
    keys = sensitive_keys or DEFAULT_SENSITIVE_KEYS
    def _fn(v, k):
        if k and str(k).lower() in keys and v not in (None, ''):
            return encrypt_str(v)
        return v
    return _walk(obj, fn=_fn)

def decrypt_json(obj):
    def _fn(v, _k):
        return decrypt_str(v) if is_encrypted(v) else v
    return _walk(obj, fn=_fn)

def mask_json(obj, sensitive_keys=None):
    keys = sensitive_keys or DEFAULT_SENSITIVE_KEYS
    def _fn(v, k):
        if k and str(k).lower() in keys and v not in (None, ''):
            return MASK
        return v
    return _walk(obj, fn=_fn)

def merge_masked(old_obj, new_obj, sensitive_keys=None):
    keys = sensitive_keys or DEFAULT_SENSITIVE_KEYS
    if not isinstance(old_obj, dict) or not isinstance(new_obj, dict):
        return new_obj
    out = dict(old_obj)
    for k, v in new_obj.items():
        lk = str(k).lower()
        if lk in keys and v == MASK:
            continue
        out[k] = v
    return out

