"""Read historical coverage after the user's full-software-license attestation."""
import argparse
import json
from ot import main
from yard import require_software_authorization

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', required=True)
parser.add_argument('--args-file')
a = parser.parse_args()
try:
    require_software_authorization(a.root)
    args = ['--root', a.root, '--profile', 'all', 'call', 'opentrack_get_function_coverage']
    if a.args_file:
        args += ['--args-file', a.args_file]
    else:
        args += ['--json', '{"section":"summary","require_fresh":false}']
    raise SystemExit(main(args))
except ValueError as exc:
    print(json.dumps({'passed':False,'error':str(exc),'code':getattr(exc,'code',None)}))
    raise SystemExit(2)
