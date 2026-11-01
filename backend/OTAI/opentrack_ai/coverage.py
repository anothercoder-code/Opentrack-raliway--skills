"""Read a versioned static coverage snapshot without refreshing it implicitly."""
import datetime
import json
from pathlib import Path
import re

from . import __version__
from .errors import APIError
import hashlib

def digest(data):return hashlib.sha256(data).hexdigest()
def inside(path,bases):
    path=Path(path).resolve()
    if not any(path==Path(base).resolve() or path.is_relative_to(Path(base).resolve()) for base in bases):
        raise APIError('PATH_OUTSIDE_SCOPE','Coverage path must remain inside its declared roots',str(path))
    return path

def page(rows,limit,offset):
    return {'items':rows[offset:offset+limit],'total_count':len(rows),'offset':offset,
            'has_more':offset+limit<len(rows),'next_offset':offset+limit if offset+limit<len(rows) else None}

def binary_path(root,name):
    
    paths={'opentrack':Path(root)/'OpenTrack.app/OpenTrack.exe',
           'foundation':Path('C:/NEXT/NextLibrary/Executables/Foundation.dll'),
           'appkit':Path('C:/NEXT/NextLibrary/Executables/AppKit.dll')}
    if name not in paths:raise APIError('BINARY_MISSING','Unknown legacy binary identity')
    path=paths[name]
    if not path.is_file():raise APIError('BINARY_MISSING','Legacy fingerprint file is unavailable',str(path))
    return path


REPORTS={'summary':'summary.json','native':'native-functions.json','python':'python-functions.json','enhancement':'handwritten-c-functions.json'}


def capture_revision(root,evidence_paths,report_dir,tool_names):
    root=Path(root);paths={root/path for path in evidence_paths}
    paths.update((root/'OTAI/opentrack_ai').glob('*.py'))
    paths.update((root/'OTUndo/tools').glob('*.py'))
    paths.update((root/'OTUndo/src').glob('*.c'))
    paths.update([root/'OTAI/server.py',root/'OTAI/audit_mcp_coverage.py',root/'OTAI/artifacts/native-class-catalog.json',root/'OTAI/artifacts/tool-schemas.json'])
    paths.update((root/'OTAI/resources').glob('native-shapes.*'));paths.update((root/'OTAI/resources').glob('function-bank.*'))
    inputs={str(path.relative_to(root)).replace('\\','/'):digest(path.read_bytes()) for path in sorted(paths) if path.is_file()}
    binaries={}
    for name in ['opentrack','foundation','appkit']:
        try:path=binary_path(root,name)
        except APIError:continue
        binaries[name]=digest(path.read_bytes())
    reports={path.name:digest(path.read_bytes()) for path in sorted(report_dir.iterdir())
        if path.is_file() and path.suffix in ['.json','.csv','.md'] and path.name!='revision.json'}
    return {'schema_version':1,'created_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'interface_version':__version__,'tool_names':list(tool_names),'input_hashes':inputs,'binary_hashes':binaries,'report_hashes':reports}


def load_json(path):
    if not path.is_file():raise APIError('COVERAGE_UNAVAILABLE','Run the installed Skill scripts/audit.py to generate a fresh coverage report.',str(path))
    if path.stat().st_size>32*1024*1024:raise APIError('COVERAGE_CORRUPT','Coverage file exceeds its bounded reader.')
    try:return json.loads(path.read_text(encoding='utf-8-sig'))
    except (UnicodeError,ValueError) as error:raise APIError('COVERAGE_CORRUPT','Coverage file is not valid UTF-8 JSON.') from error


def read_legacy_coverage(root,args):
    root=Path(root).resolve();folder=inside(root/'OTAI/artifacts/mcp-coverage',[root/'OTAI'])
    if (folder/'.refresh.lock').exists():raise APIError('COVERAGE_REFRESH_RUNNING','Coverage is being refreshed; retry after the audit finishes.')
    revision=load_json(folder/'revision.json')
    if not isinstance(revision,dict) or revision.get('schema_version')!=1:raise APIError('COVERAGE_CORRUPT','Unsupported coverage revision schema.')
    if not isinstance(revision.get('input_hashes'),dict) or not isinstance(revision.get('binary_hashes'),dict) or not isinstance(revision.get('report_hashes'),dict):
        raise APIError('COVERAGE_CORRUPT','Coverage revision lacks input/report fingerprints.')
    changed=[]
    if revision.get('interface_version')!=__version__:changed.append('interface_version')
    for relative,expected in revision['input_hashes'].items():
        if not isinstance(relative,str) or not isinstance(expected,str) or not re.fullmatch('[a-f0-9]{64}',expected):raise APIError('COVERAGE_CORRUPT','Invalid coverage input fingerprint.')
        try:path=inside(root/relative,[root/'OTUndo',root/'OTAI'])
        except APIError as error:raise APIError('COVERAGE_CORRUPT','Coverage inputs must stay inside OTUndo/OTAI.') from error
        if not path.is_file() or digest(path.read_bytes())!=expected:changed.append(relative)
    for name,expected in revision['binary_hashes'].items():
        if name not in ['opentrack','foundation','appkit']:raise APIError('COVERAGE_CORRUPT','Unknown binary fingerprint key.')
        try:path=binary_path(root,name)
        except APIError:changed.append('binary:'+name);continue
        if digest(path.read_bytes())!=expected:changed.append('binary:'+name)
    freshness={'fresh':not changed,'created_at':revision.get('created_at'),'interface_version':revision.get('interface_version'),
        'changed_input_count':len(changed),'changed_inputs':changed[:30]}
    if changed and args.require_fresh:raise APIError('COVERAGE_STALE','Run the installed Skill scripts/audit.py before treating this snapshot as current.',freshness)
    filename=REPORTS[args.section];path=inside(folder/filename,[folder]);expected=revision['report_hashes'].get(filename)
    if not path.is_file() or not isinstance(expected,str) or digest(path.read_bytes())!=expected:
        raise APIError('COVERAGE_CORRUPT','Coverage data changed after the audit revision was published.',filename)
    data=load_json(path)
    base={'section':args.section,'freshness':freshness,'native_invocation_exposed':False,
        'evidence_level':'Static inventory; metadata queries, bounded instruction windows and offline subsets do not establish native-function parity.'}
    if args.section=='summary':
        if any([args.query,args.binary,args.class_name,args.selector,args.status]):raise APIError('FILTER_NOT_APPLICABLE','Select native/python/enhancement to filter rows.')
        if not isinstance(data,dict):raise APIError('COVERAGE_CORRUPT','Summary must be an object.')
        return {**base,'summary':data}
    if not isinstance(data,list) or not all(isinstance(row,dict) for row in data):raise APIError('COVERAGE_CORRUPT','Function coverage must be an object array.')
    if args.section!='native' and any([args.binary,args.class_name,args.selector]):raise APIError('FILTER_NOT_APPLICABLE','binary/class_name/selector filters apply only to native methods.')
    rows=[]
    for row in data:
        if args.binary and row.get('binary')!=args.binary:continue
        if args.class_name and row.get('class')!=args.class_name:continue
        if args.selector and args.selector.casefold() not in row.get('selector','').casefold():continue
        if args.status and row.get('coverage_status',row.get('status'))!=args.status:continue
        if args.query and args.query.casefold() not in json.dumps(row,ensure_ascii=False).casefold():continue
        rows.append(row)
    return {**base,**page(rows,args.limit,args.offset)}


PACKAGED_REPORTS={'saved_data':'current-function-coverage.json','interfaces':'rebuild-interface-matrix.json','requirements':'requirements.json'}

def read_packaged_coverage(args):
    """Read maintained coverage metadata without decoding archives or native imports."""
    package=Path(__file__).resolve().parents[1]
    folder=package/'replica'
    revision=load_json(folder/'packaged-coverage-revision.json')
    if revision.get('schema_version')!=1 or not isinstance(revision.get('input_hashes'),dict):
        raise APIError('COVERAGE_CORRUPT','Invalid packaged coverage revision')
    required={'replica/'+name for name in PACKAGED_REPORTS.values()}
    if not required.issubset(revision['input_hashes']):raise APIError('COVERAGE_CORRUPT','Packaged revision must bind every exposed report')
    changed=[]
    for name,expected in revision['input_hashes'].items():
        if not isinstance(name,str) or not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected):
            raise APIError('COVERAGE_CORRUPT','Invalid packaged coverage fingerprint')
        path=inside(package/name,[package])
        if not path.is_file() or digest(path.read_bytes())!=expected:changed.append(name)
    fresh=not changed and revision.get('interface_version')==__version__
    if revision.get('interface_version')!=__version__:changed.append('interface_version')
    freshness={'fresh':fresh,'created_at':revision.get('created_at'),'interface_version':revision.get('interface_version'),
               'changed_input_count':len(changed),'changed_inputs':changed[:30]}
    if args.require_fresh and not fresh:raise APIError('COVERAGE_STALE','Packaged interface/report files differ from the explicit build revision; rebuild its metadata separately',freshness)
    if args.binary:raise APIError('FILTER_NOT_APPLICABLE','binary filter belongs to the legacy function-bank reports')
    base={'section':args.section,'source':'packaged','freshness':freshness,'native_invocation_exposed':False,
          'evidence_level':'Maintained saved-data/interface inventory. Historical function status is not a fresh native test or complete software parity.'}
    if args.section=='summary':
        if any((args.query,args.class_name,args.selector,args.status)):raise APIError('FILTER_NOT_APPLICABLE','Use a row section for filters')
        req=load_json(folder/'requirements.json');matrix=load_json(folder/'rebuild-interface-matrix.json');functions=load_json(folder/'current-function-coverage.json')
        return {**base,'summary':{'original_requirements':req['requirements_count'],'goal_complete':False,
                'saved_function_records':len(functions['functions']),'saved_function_record_provenance':'retained v11 bounded-function evidence; not re-certified by metadata reading',
                'rebuilt_interface_records':len(matrix['rows']),'generation_profile_tools':matrix['generation_profile_tools'],
                'new_interface_persistence':matrix['new_interface_export'],'available_sections':['saved_data','interfaces','requirements'],
                'legacy_function_bank_reports':'not included by this packaged dataset'}}
    if args.section not in PACKAGED_REPORTS:raise APIError('COVERAGE_SECTION','native/python/enhancement require legacy coverage reports; choose scope=legacy')
    obj=load_json(folder/PACKAGED_REPORTS[args.section]);rows=obj['functions' if args.section=='saved_data' else 'rows' if args.section=='interfaces' else 'requirements']
    if args.section!='saved_data' and (args.class_name or args.selector):raise APIError('FILTER_NOT_APPLICABLE','class_name/selector apply to saved_data or legacy native function rows')
    output=[]
    for row in rows:
        if args.class_name and row.get('class')!=args.class_name:continue
        if args.selector and args.selector.casefold() not in row.get('selector','').casefold():continue
        status=row.get('current_function_status',row.get('status',row.get('persistence','')))
        if getattr(args,'operation',None):
            status=row.get('operation_coverage',{}).get(args.operation,{}).get('status','not_reassessed')
        if args.status and status!=args.status:continue
        if args.query and args.query.casefold() not in json.dumps(row,ensure_ascii=False).casefold():continue
        output.append(row)
    return {**base,**page(output,args.limit,args.offset)}

def read_coverage(root,args):
    if getattr(args,'operation',None) and (args.section!='requirements' or args.scope=='legacy'):
        raise APIError('FILTER_NOT_APPLICABLE','operation filters apply only to packaged requirements')
    scope=getattr(args,'scope','auto')
    use_packaged=scope=='packaged' or (scope=='auto' and (args.section in PACKAGED_REPORTS or (args.section=='summary' and not (Path(root)/'OTAI/artifacts/mcp-coverage/revision.json').is_file())))
    if use_packaged:return read_packaged_coverage(args)
    if args.section not in REPORTS:raise APIError('COVERAGE_SECTION','This section belongs to scope=packaged')
    return read_legacy_coverage(root,args)
