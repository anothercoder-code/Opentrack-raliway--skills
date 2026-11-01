"""Preview, stage or freshly publish the bounded three-station native yard.

Requires six external native donors; never operates or starts OpenTrack.
Preview writes nothing. Stage/publish use the paired backend's existing Windows
x64 fixed-local-NTFS no-replace project publisher and fresh-byte validators.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import sys


SCHEMA = 'three-station-yard-request/1'
ROLES = frozenset({'header', 'shapes', 'depot_template', 'trains_template',
                   'courses_template', 'timetable_template'})


def need(ok, message):
    if not ok:
        raise ValueError(message)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_request(path):
    blob = Path(path).read_bytes()
    need(len(blob) <= 1024 * 1024, 'Request exceeds 1 MiB')
    def invalid(value):
        raise ValueError('Nonfinite JSON constant: ' + value)
    result = json.loads(blob.decode('utf-8'), object_pairs_hook=unique_pairs,
                        parse_constant=invalid)
    return check_request(result)


def check_request(request):
    need(type(request) is dict and set(request) ==
         {'schema', 'sources', 'recipe', 'accept_proxy_physics'},
         'Exact schema/sources/recipe/accept_proxy_physics request required')
    need(request['schema'] == SCHEMA, 'Unknown yard request schema')
    need(request['accept_proxy_physics'] is True,
         'Explicit accept_proxy_physics=true is required for the uncalibrated inherited proxy')
    sources = request['sources']
    need(type(sources) is dict and set(sources) == ROLES,
         'Exactly six external native donor roles required')
    for role, item in sources.items():
        need(type(item) is dict and set(item) == {'path', 'sha256'},
             'Exact donor path/sha256 required: ' + role)
        need(type(item['path']) is str and 1 <= len(item['path']) <= 500,
             'Bounded donor path required: ' + role)
        need(type(item['sha256']) is str and
             re.fullmatch('[0-9a-f]{64}', item['sha256']) is not None,
             'Exact lowercase SHA-256 required: ' + role)
    need(type(request['recipe']) is dict, 'Explicit yard recipe required')
    return request


def initialize_backend():
    
    
    
    from ot import check_python, locate_backend
    check_python()
    parent, entry = locate_backend(Path(__file__).with_name('ot.py'), os.environ)
    sys.path.insert(0, str(entry.parent))
    from opentrack_ai import __version__
    from ot import EXPECTED_VERSION
    need(__version__ == EXPECTED_VERSION, 'Loaded backend version differs from the paired bridge')
    return entry.parent


def require_software_authorization(data_root):
    """Require the user's full-license attestation, never infer it from an EXE."""
    initialize_backend()
    from opentrack_ai.license_authorization import require_authorization
    return require_authorization(data_root)


def prepare(data_root, request):
    """Securely read six bound donors and generate all seventeen new members."""
    require_software_authorization(data_root)
    check_request(request)
    from opentrack_ai.current_archive.tools import ArchiveTools
    from yard_profile import composition, topology
    reader = ArchiveTools(data_root)
    topology.configuration(request['recipe'])
    sources, inputs = {}, {}
    for role, item in request['sources'].items():
        path = reader.path(item['path'])
        value = reader.secure_bytes(path)
        need(hashlib.sha256(value).hexdigest() == item['sha256'],
             'Donor SHA-256 differs: ' + role)
        if path in inputs:
            need(inputs[path] == value, 'Repeated donor changed between reads')
        inputs[path] = value
        sources[role] = value
    files, receipt = composition.build(sources, request['recipe'])
    def recheck():
        for path, value in inputs.items():
            need(reader.secure_bytes(path) == value, 'Donor changed during generation/publication')
    recheck()
    return reader, files, receipt, recheck


def execute(data_root, request, *, mode='preview', target=None):
    require_software_authorization(data_root)
    need(mode in ('preview', 'stage', 'publish'), 'Unknown yard command')
    need((mode == 'preview') == (target is None),
         'Preview has no target; stage/publish require an explicit fresh target')
    
    if target is not None:
        from opentrack_ai.current_archive.tools import ArchiveTools
        from opentrack_ai.current_archive.zero_operations import run_bundle as rb
        destination = ArchiveTools(data_root).path(target)
        if mode == 'stage':
            need(destination.is_relative_to(ArchiveTools(data_root).root / 'OTAI/workspaces'),
                 'Staging is restricted to OTAI/workspaces; use publish for a formal project')
        else:
            actual_root = rb.root_path(destination.as_posix(), 'windows')
            need(actual_root.casefold() == request['recipe']['execution_root'].casefold(),
                 'Published execution_root must equal the actual fresh target')
    reader, files, receipt, recheck = prepare(data_root, request)
    result = {'command': mode, 'backend_version': '0.33.1-zeroaccept1',
              'saved': False, 'staged': False, 'published': False,
              'project_files_delivered': False,
              'native_application_executed': False, 'native_runtime_verified': False,
              'candidate_receipt': receipt, 'publication': None}
    if mode == 'preview':
        return result
    from opentrack_ai.current_archive.windows_publish import publish_project
    from yard_profile.composition import validate_seventeen
    def validate(actual):
        need({name: {'sha256': hashlib.sha256(value).hexdigest(), 'bytes': len(value)}
              for name, value in actual.items()} == receipt['members'],
             'Actual seventeen-member readback differs from the generated candidate')
        return validate_seventeen(actual, request['recipe'])
    destination = reader.path(target)
    publication = publish_project(reader.root, destination, files, recheck=recheck,
        validate_bundle=validate, empty_directories=('output', 'output-failure'))
    result.update(saved=True, staged=mode == 'stage', published=mode == 'publish',
                  project_files_delivered=mode == 'publish', publication=publication,
                  target_directory=target,
                  execution_root_matches_target=(destination.as_posix().casefold() ==
                      request['recipe']['execution_root'].casefold()))
    return result


def main(arguments=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preview', 'stage', 'publish'))
    parser.add_argument('--root', required=True,
                        help='Authorized data root containing OTProjects and OTAI/workspaces')
    parser.add_argument('--request', required=True, type=Path,
                        help='UTF-8 three-station-yard-request/1 JSON file')
    parser.add_argument('--target', help='Fresh relative directory under the authorized data root')
    args = parser.parse_args(arguments)
    try:
        require_software_authorization(args.root)
        result = execute(args.root, read_request(args.request),
                         mode=args.command, target=args.target)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except Exception as exc:
        
        
        print(json.dumps({'passed': False, 'error_type': type(exc).__name__,
                          'error': str(exc), 'code': getattr(exc, 'code', None),
                          'details': getattr(exc, 'details', None),
                          'native_application_executed': False}, ensure_ascii=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
