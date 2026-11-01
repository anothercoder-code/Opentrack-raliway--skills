"""Record only the user's explicit confirmation of a valid full OpenTrack licence.

This tool does not validate vendor activation. Do not record a confirmation on
behalf of a user who has not actually supplied it; no keys or serials are needed.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path
from ot import locate_backend, check_python

def main():
    check_python()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['status','record','revoke'])
    parser.add_argument('--root',required=True)
    parser.add_argument('--confirm-full-license',action='store_true')
    parser.add_argument('--user-statement')
    parser.add_argument('--user-scope')
    parser.add_argument('--purpose')
    parser.add_argument('--expires-at',help='Optional known licence/scope expiry as timezone-aware ISO8601')
    parser.add_argument('--replace',action='store_true')
    args=parser.parse_args()
    import os
    _,entry=locate_backend(Path(__file__).with_name('ot.py'),os.environ)
    spec=importlib.util.spec_from_file_location('skill_software_authorization',entry.parent/'opentrack_ai/license_authorization.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    try:
        if args.command=='status':result=module.authorization_status(args.root)
        elif args.command=='revoke':result=module.revoke_authorization(args.root)
        else:
            if not args.confirm_full_license or not args.user_statement or not args.user_scope or not args.purpose:
                parser.error('record requires --confirm-full-license and the actual verbatim --user-statement, --user-scope and --purpose; never infer or fabricate confirmation')
            result=module.record_authorization(args.root,user_statement=args.user_statement,
                user_scope=args.user_scope,purpose=args.purpose,expires_at=args.expires_at,replace=args.replace)
        print(json.dumps({'ok':True,'result':result},ensure_ascii=False))
        return 0
    except (ValueError,OSError) as exc:
        error=exc.as_dict() if hasattr(exc,'as_dict') else {'code':'SOFTWARE_AUTHORIZATION_RECORD','message':str(exc)}
        print(json.dumps({'ok':False,'error':error},ensure_ascii=False));return 2

if __name__=='__main__':
    raise SystemExit(main())
