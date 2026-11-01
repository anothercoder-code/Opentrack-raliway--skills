"""Explicit user attestation of a valid full OpenTrack software licence.

This is a workflow precondition, not vendor activation, licence verification or
DRM. Never infer it from an executable, a running process, or save capability.
The record contains no licence key, serial number or activation material.
"""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

AUTHORIZATION_GATE_REVISION = 'full-license-attestation-1'
REQUIRED_ORIGINAL_LICENSE = 'full'
SCHEMA = 'original-opentrack-full-license-attestation/1'
METADATA_TOOLS = frozenset({'opentrack_capabilities', 'opentrack_get_schema'})
MAX_RECORD_BYTES = 16384
FIELDS = frozenset({'schema','software','entitlement','confirmed_full_license',
    'declared_by','user_statement','user_scope','purpose','data_root','confirmed_at','status'})

class SoftwareAuthorizationError(ValueError):
    code = 'SOFTWARE_AUTHORIZATION_REQUIRED'
    def __init__(self, reason, path):
        super().__init__('A valid full OpenTrack software licence, explicitly confirmed by the user for this scope, is required before railway data or native operations. No confirmation is inferred from program availability.')
        self.details={'reason':reason,'record_path':str(path),
                      'required_original_license':'full','attestation_only':True}
    def as_dict(self):
        return {'code':self.code,'message':str(self),'details':self.details}

def normalized_root(root):
    return os.path.normcase(str(Path(root).expanduser().resolve()))

def record_path(root):
    return Path(os.path.abspath(Path(root).expanduser()))/'OTAI/software-authorization.json'

def plain_path(path):
    
    for item in (path, *path.parents):
        try:
            info=item.lstat()
        except FileNotFoundError:
            continue
        if item.is_symlink() or getattr(info,'st_file_attributes',0) & 0x400:
            return False
    return True

def _read_record(root):
    path=record_path(root)
    if not plain_path(path):
        raise SoftwareAuthorizationError('record_path_is_reparse_or_symlink',path)
    try:
        if not path.is_file() or path.stat().st_size > MAX_RECORD_BYTES:
            raise SoftwareAuthorizationError('record_missing_or_not_bounded_file',path)
        raw=path.read_bytes()
        if len(raw)>MAX_RECORD_BYTES:
            raise SoftwareAuthorizationError('record_too_large',path)
        def unique(pairs):
            out={}
            for key,value in pairs:
                if key in out: raise ValueError('duplicate field')
                out[key]=value
            return out
        data=json.loads(raw.decode('utf-8'),object_pairs_hook=unique)
    except (OSError,ValueError,UnicodeError) as exc:
        if isinstance(exc,SoftwareAuthorizationError):raise
        raise SoftwareAuthorizationError('record_unreadable_or_invalid',path) from exc
    if not isinstance(data,dict) or not FIELDS <= set(data) or set(data)-FIELDS-{'expires_at'}:
        raise SoftwareAuthorizationError('record_schema_fields_invalid',path)
    expected={'schema':SCHEMA,'software':'OpenTrack','entitlement':'full',
              'confirmed_full_license':True,'declared_by':'user','status':'active'}
    if any(data.get(k)!=v or (k=='confirmed_full_license' and type(data.get(k)) is not bool)
           for k,v in expected.items()):
        raise SoftwareAuthorizationError('full_licence_not_confirmed_or_record_revoked',path)
    if data['data_root']!=normalized_root(root):
        raise SoftwareAuthorizationError('data_root_scope_mismatch',path)
    for key,limit in [('user_statement',4000),('user_scope',500),('purpose',1000)]:
        if not isinstance(data.get(key),str) or not data[key].strip() or len(data[key])>limit:
            raise SoftwareAuthorizationError('user_statement_or_scope_missing',path)
    try:
        stamp=datetime.fromisoformat(data['confirmed_at'])
        if stamp.tzinfo is None:raise ValueError('timezone required')
    except (ValueError,TypeError):
        raise SoftwareAuthorizationError('confirmation_timestamp_invalid',path)
    expires=None
    if 'expires_at' in data:
        try:
            expires=datetime.fromisoformat(data['expires_at'])
            if expires.tzinfo is None:raise ValueError('timezone required')
            expires=expires.astimezone(timezone.utc)
        except (ValueError,TypeError):
            raise SoftwareAuthorizationError('expiry_timestamp_invalid',path)
        if expires <= datetime.now(timezone.utc):
            raise SoftwareAuthorizationError('record_expired',path)
    return {**data,'record_path':str(path),'record_sha256':hashlib.sha256(raw).hexdigest(),
            'expires_at':expires.isoformat() if expires else None,
            'expires_unix_seconds':int(expires.timestamp()) if expires else 0}

def require_authorization(root):
    """Return the scope-bound explicit user attestation, or fail closed."""
    return _read_record(root)

def authorization_status(root):
    result={'required_original_license':REQUIRED_ORIGINAL_LICENSE,
        'authorization_gate_revision':AUTHORIZATION_GATE_REVISION,
        'attestation_only':True,'vendor_verification_performed':False,
        'record_path':str(record_path(root)), 'attested':False}
    try:
        record=require_authorization(root)
    except SoftwareAuthorizationError as exc:
        result['reason']=exc.details['reason']
    else:
        result.update({'attested':True,'reason':'explicit_user_attestation_present',
            'record_sha256':record['record_sha256'], 'user_scope':record['user_scope'],
            'purpose':record['purpose'], 'confirmed_at':record['confirmed_at'],
            'expires_at':record['expires_at'],'expires_unix_seconds':record['expires_unix_seconds']})
    return result

def record_authorization(root, *, user_statement, user_scope, purpose, expires_at=None, replace=False):
    """Called only after the actual user has explicitly confirmed the full licence."""
    path=record_path(root)
    if not plain_path(path):raise SoftwareAuthorizationError('record_path_is_reparse_or_symlink',path)
    for value,limit in [(user_statement,4000),(user_scope,500),(purpose,1000)]:
        if not isinstance(value,str) or not value.strip() or len(value)>limit:
            raise ValueError('A bounded verbatim user statement, user scope and purpose are required')
    if path.exists() and not replace:
        raise ValueError('An authorization record exists; inspect it, then explicitly replace if reconfirmed')
    data={'schema':SCHEMA,'software':'OpenTrack','entitlement':'full',
        'confirmed_full_license':True,'declared_by':'user','user_statement':user_statement,
        'user_scope':user_scope,'purpose':purpose,'data_root':normalized_root(root),
        'confirmed_at':datetime.now(timezone.utc).isoformat(),'status':'active'}
    if expires_at is not None:
        try:
            expires=datetime.fromisoformat(expires_at)
            if expires.tzinfo is None:raise ValueError('timezone required')
            expires=expires.astimezone(timezone.utc)
        except (ValueError,TypeError) as exc:
            raise ValueError('expires_at must be a timezone-aware ISO8601 timestamp') from exc
        if expires <= datetime.now(timezone.utc):raise ValueError('expires_at is already expired')
        data['expires_at']=expires.isoformat()
    path.parent.mkdir(parents=True,exist_ok=True)
    if not plain_path(path):raise SoftwareAuthorizationError('record_path_is_reparse_or_symlink',path)
    raw=(json.dumps(data,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
    if replace:
        import tempfile
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.software-authorization-',delete=False) as tmp:
            tmp.write(raw);temp=Path(tmp.name)
        try:os.replace(temp,path)
        finally:
            if temp.exists():temp.unlink()
    else:
        with path.open('xb') as out:out.write(raw)
    return authorization_status(root)

def revoke_authorization(root):
    record=require_authorization(root)
    path=Path(record['record_path'])
    record={key:value for key,value in record.items() if key in FIELDS or key=='expires_at' and value is not None}
    record['status']='revoked'
    import tempfile
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.software-authorization-',delete=False) as tmp:
        tmp.write((json.dumps(record,indent=2,ensure_ascii=False)+'\n').encode('utf-8'));temp=Path(tmp.name)
    try:os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()
    return authorization_status(root)
