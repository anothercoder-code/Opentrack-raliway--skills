"""Build the bounded native 3x3 station-yard profile from six external donors.

This is the actual turning-yard profile, not grid_generation.py's planning-only
line graph. Never launches OpenTrack. Default preview writes no project files.
"""
import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / 'assets/grid-yard-profile'
SCHEMA = 'nine-station-native-yard-request/1'
ROLES = {'header', 'shapes', 'depot_template', 'trains_template',
         'courses_template', 'timetable_template'}

def need(ok, message):
    if not ok:
        raise ValueError(message)

def sha(value):
    return hashlib.sha256(value).hexdigest()

def checked_request(path):
    from yard import unique_pairs
    raw = Path(path).read_bytes()
    need(len(raw) <= 1024 * 1024, 'Request exceeds 1 MiB')
    def invalid(value):
        raise ValueError('Nonfinite JSON constant: ' + value)
    req = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique_pairs,
                     parse_constant=invalid)
    need(type(req) is dict and set(req) == {'schema', 'sources', 'execution_root', 'accept_proxy_physics'},
         'Exact schema/sources/execution_root/accept_proxy_physics required')
    need(req['schema'] == SCHEMA, 'Unknown grid yard request schema')
    need(req['accept_proxy_physics'] is True, 'Explicit acceptance of inherited uncalibrated proxy physics required')
    need(type(req['sources']) is dict and set(req['sources']) == ROLES, 'Exactly six donor roles required')
    known = json.loads((ASSETS / 'profile-provenance.json').read_text('utf-8'))['external_donor_sha256']
    for role, source in req['sources'].items():
        need(type(source) is dict and set(source) == {'path', 'sha256'}, 'Exact donor path/sha256 required: ' + role)
        need(type(source['path']) is str and 1 <= len(source['path']) <= 500, 'Bounded donor path required')
        need(type(source['sha256']) is str and re.fullmatch('[0-9a-f]{64}', source['sha256']) is not None,
             'Lowercase SHA-256 required')
        need(source['sha256'] == known[role], 'This bounded profile requires the verified donor identity: ' + role)
    need(type(req['execution_root']) is str, 'Explicit actual execution_root required')
    req['execution_root'].encode('ascii')
    need(all(32 <= ord(c) <= 126 for c in req['execution_root']), 'Native execution path must be printable ASCII')
    return req

def initialize():
    from yard import initialize_backend
    initialize_backend()
    sys.path.insert(0, str(ASSETS))
    import build_project as profile
    return profile

def final_layout(profile, docs, proofs, header):
    """Apply explicit graphic-only template and four reviewed physical extensions."""
    gg = profile.gg
    w, rf = gg.w, gg.rf
    layout = json.loads((ASSETS / 'final-layout.json').read_text('utf-8'))
    result = {}
    for dn, raw in docs.items():
        specs = layout[dn]
        captions = [row for row in specs['models'] if row.get('text') in ('Outside Junction', 'Approach Overpasses')]
        need(len(captions) == 2, 'Two explicit extra captions required')
        
        captions.sort(key=lambda row: row['id'])
        for row in captions:
            raw, _ = gg.labels.add_labels(raw, [{'key':row['text'].replace(' ', '_'),
                'text':row['text'], 'rect':row['groups']['8']}], template_document=header)
        root, version = w.load_next_compatible(raw)
        _, byid = rf.document(root)
        for row in specs['models']:
            model = byid[row['id']]
            need(w.kind(model) == row['kind'], 'Graphic template class/ID differs: ' + dn)
            for index, values in row['groups'].items():
                model.contents[int(index)].values = values
            if 'text' in row:
                payload = gg.labels.RTF_PREFIX + row['text'].encode('ascii') + gg.labels.RTF_SUFFIX
                data = model.contents[7].value
                data.contents[0].value = len(payload)
                data.contents[1] = w.TypedGroup([('['+str(len(payload))+'c]').encode('ascii')], [w.Array(payload)])
        for index, values in specs['root_groups'].items():
            root.contents[int(index)].values = values
        for port in gg.PORTS:
            key = gg.name(port, 'MERGE') + '__' + gg.name(port, 'I_A')
            edge = byid[proofs[dn]['base']['edge_ids'][key]]
            need(w.kind(edge) == 'OTEdgeModel' and edge.contents[9].values[1] == 100,
                 'Expected 100m pre-extension edge required')
            edge.contents[9].values[1] = 1100
        result[dn] = w.dump_verified(root, version)
    return result

def prepare(root, req):
    from yard import require_software_authorization
    require_software_authorization(root)
    profile = initialize()
    from opentrack_ai.current_archive.tools import ArchiveTools
    from opentrack_ai.current_archive.zero_operations import run_bundle as rb
    from verify_project import validate
    reader = ArchiveTools(root)
    canonical = rb.root_path(req['execution_root'], 'windows')
    need(canonical == req['execution_root'], 'Use canonical forward-slash Windows execution_root')
    target = Path(canonical)
    need(target.is_relative_to(reader.root), 'execution_root must lie within the authorized data root')
    profile.TARGET = target
    profile.DOC_PATHS = {n: target.as_posix()+'/OTDocuments/'+n+'.opentrack' for n in profile.STATIONS}
    sources, originals = {}, {}
    for role, row in req['sources'].items():
        path = reader.path(row['path'])
        raw = reader.secure_bytes(path)
        need(sha(raw) == row['sha256'], 'Donor SHA-256 changed: ' + role)
        sources[role], originals[path] = raw, raw
    docs, stations, proofs, local, cross, conns = profile.infrastructure(sources)
    docs = final_layout(profile, docs, proofs, sources['header'])
    plans = profile.make_plans()
    for plan in plans:
        plan.update(leg_distance_m=6000, unified_platform_bay=True)
        for index, visit in enumerate(plan['visits']):
            visit['seconds'] = plan['start_s'] + index * 420
    docs, dest = profile.movements(docs, proofs, local, cross, plans)
    files, traces, operating = profile.operating(sources, docs, dest, stations, plans)
    review = validate(files, plans, proofs, traces)
    proof_json = {dn:{key:value for key,value in proof.items() if key != 'sequences'}
                  for dn,proof in proofs.items()}
    receipt = {'schema':'nine-station-native-yard-candidate/1', 'execution_root':canonical,
               'members':{name:{'bytes':len(value),'sha256':sha(value)} for name,value in files.items()},
               'sources':req['sources'], 'plans':plans, 'proofs':proof_json, 'traces':traces,
               'connections':conns, 'operating':operating, 'validation':review,
               'native_application_executed':False, 'native_runtime_verified':False}
    def recheck():
        for path, old in originals.items():
            need(reader.secure_bytes(path) == old, 'Donor changed during generation/publication')
    recheck()
    return reader, files, receipt, recheck, lambda actual: validate(actual, plans, proofs, traces)

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('preview', 'stage', 'publish'))
    parser.add_argument('--root', required=True, help='Authorized data root')
    parser.add_argument('--request', required=True, type=Path)
    parser.add_argument('--target', help='Fresh relative directory within --root; stage requires OTAI/workspaces')
    parser.add_argument('--receipt', type=Path, help='Optional fresh JSON receipt path in authorized OTAI/workspaces')
    args = parser.parse_args(argv)
    try:
        from yard import require_software_authorization
        require_software_authorization(args.root)
        req = checked_request(args.request)
        need((args.command == 'preview') == (args.target is None), 'Preview has no target; stage/publish require one')
        
        initialize()
        from opentrack_ai.current_archive.tools import ArchiveTools
        from opentrack_ai.current_archive.windows_publish import publish_project
        scope = ArchiveTools(args.root)
        target = scope.path(args.target) if args.target else None
        if target:
            need(not target.exists(), 'Target exists; use the current-project edit workflow instead')
            if args.command == 'stage':
                need(target.is_relative_to(scope.root/'OTAI/workspaces'), 'Stage target must be under OTAI/workspaces')
            else:
                need(target.as_posix() == req['execution_root'], 'Publish target must equal actual execution_root')
        if args.receipt:
            args.receipt = scope.path(str(args.receipt))
            need(args.receipt.is_relative_to(scope.root/'OTAI/workspaces') and not args.receipt.exists(),
                 'Receipt must be fresh and under authorized OTAI/workspaces')
        reader, files, receipt, recheck, validate = prepare(args.root, req)
        result = {'command':args.command, 'native_application_executed':False,
                  'native_runtime_verified':False, 'published':False, 'staged':False,
                  'input_members':len(files), 'validation':receipt['validation']}
        if target:
            result['publication'] = publish_project(reader.root, target, files, recheck=recheck,
                validate_bundle=validate, empty_directories=('output',))
            result.update(published=args.command == 'publish', staged=args.command == 'stage')
        if args.receipt:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            with args.receipt.open('x', encoding='utf-8') as out:
                json.dump(receipt, out, indent=2);out.write('\n')
            result['candidate_receipt'] = str(args.receipt)
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except Exception as exc:
        print(json.dumps({'passed':False, 'error_type':type(exc).__name__, 'error':str(exc),
                          'code':getattr(exc,'code',None), 'details':getattr(exc,'details',None),
                          'native_application_executed':False}, ensure_ascii=True))
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
