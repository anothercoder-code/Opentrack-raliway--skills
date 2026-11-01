"""Prepare original OpenTrack train-diagram capture, H2 projection and export jobs.

Commands prepare files only. No command starts or attaches to OpenTrack, loads a
DLL, changes licence checks, or redraws curves. Native execution remains a
separate, explicitly requested action using the generated, reviewable job.
"""
import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ASSET = Path(__file__).resolve().parent.parent/'assets/native-diagram-bridge'
EXE_SHA = 'f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104'
DONOR_SHA = '6276294079eaca391576effe3ad67b3ebe5e181330ea3ef9736ec45250315e81'
COURSES = ('H2E1','H2E2','H2W1','H2W2','H2E1_FOLLOW')

def need(ok, message):
    if not ok: raise ValueError(message)

def sha(raw): return hashlib.sha256(raw).hexdigest()

def write(path, value):
    with path.open('x',encoding='utf-8') as out:
        json.dump(value,out,indent=2);out.write('\n')

def setup(root):
    from yard import require_software_authorization
    require_software_authorization(root)
    from grid_yard import initialize
    profile = initialize()
    from opentrack_ai.current_archive.tools import ArchiveTools
    return ArchiveTools(root), profile

def ascii_path(path):
    value = path.as_posix()
    value.encode('ascii')
    need(len(value) <= 480 and all(32<=ord(c)<=126 for c in value), 'Bounded printable ASCII native path required')
    need('"' not in value and '#' not in value and '%' not in value, 'Unsupported native/build path character')
    return value

def fresh(reader, name):
    import stat
    path = reader.path(name)
    need(path.is_relative_to(reader.root/'OTAI/workspaces'), 'Job must be within authorized OTAI/workspaces')
    need(not path.exists(), 'Job directory exists; preserve and inspect that job instead of overwriting')
    ascii_path(path)
    current=reader.root
    for part in ('.', *path.relative_to(reader.root).parts):
        if part!='.':current=current/part
        if current.exists() or current.is_symlink():
            meta=current.lstat()
            need(not stat.S_ISLNK(meta.st_mode) and not(getattr(meta,'st_file_attributes',0)&0x400),
                 'Fresh job path must not traverse symlinks or reparse points')
    return path

def dictionary(obj, pf):
    need(obj.clazz.name == b'NSMutableDictionary', 'Expected native mutable dictionary')
    need(len(obj.contents) == 1+2*obj.contents[0].value, 'Dictionary count differs')
    return {pf.string(obj.contents[i].value):obj.contents[i+1].value for i in range(1,len(obj.contents),2)}

def array(obj):
    need(obj.clazz.name == b'NSMutableArray' and len(obj.contents)==1+obj.contents[0].value, 'Native array count differs')
    return [g.value for g in obj.contents[1:]]

def prepare_capture(args):
    reader, profile = setup(args.root)
    w,pf,ns = profile.w,profile.pf,profile.ns
    project = reader.path(args.project)
    donor = reader.secure_bytes(reader.path(args.donor))
    need(sha(donor)==DONOR_SHA, 'The verified external v11 Corridor donor is required')
    original, version = w.load_next_compatible(donor)
    job = fresh(reader,args.job_dir)
    collector = job/'Grid3x3.otsimnet'
    empty = original.contents[1].value.contents[2].value
    need(dictionary(empty,pf)=={}, 'Donor dictionary must be empty')
    date = copy.deepcopy(original.contents[4].value)
    date.contents[0].values=[(datetime.now(timezone.utc)-datetime(2001,1,1,tzinfo=timezone.utc)).total_seconds()]
    blanks = [copy.deepcopy(empty) for _ in range(7)]
    sim = ns.obj([('OTTSimController',1),('NSObject',0)],[('@',[v]) for v in blanks[:3]])
    topo = ns.obj([('OTTDocTopoController',0),('NSObject',0)],[('@',[v]) for v in blanks[3:]])
    data = ns.obj([('OTSimData',0),('NSObject',0)],
                  [('ii',[0,0]),('ff',[1.0,0.0]),('fff',[32400.0,37800.0,ns.number(.2)])])
    root = ns.obj([('OTSimDocument',2),('NSObject',0)],
        [('@',[sim]),('@',[topo]),('@',[ns.string(ascii_path(collector))]),
         ('@',[ns.string('Grid3x3 Native Simulation')]),('@',[date]),('@',[ns.string('')]),
         ('@',[data]),('i',[1]),('ff',[32400.0,37800.0]),
         ('@',[ns.string('Pending native capture; no trajectories stored')]),('@',[ns.string('Grid3x3 Native Simulation')])])
    blank = w.dump_verified(root,version)
    root2,v2=w.load_next_compatible(blank)
    need(w.dump_verified(root2,v2)==blank,'Capture seed roundtrip differs')
    names=['grid.run']+['OTDocuments/'+n+'.opentrack' for n in profile.STATIONS]+list(profile.CATALOGS.values())
    inputs={n:reader.secure_bytes(project/n) for n in names}
    rows=[];used=set()
    replacements={'OutputPath':ascii_path(job/'capture-output'),'Output Train Diagram':'1',
                  'Adhesion Outside':'0','Adhesion Tunnel':'0','Performance':'1.00'}
    for line in inputs['grid.run'].decode('ascii').splitlines():
        key,value,tail=line.split('#');need(not tail,'Unexpected run record')
        need(key!='Train Diagram Document','Run already binds a diagram; inspect existing workflow first')
        if key in replacements:value=replacements[key];used.add(key)
        rows.append(key+'#'+value+'#')
    rows += [key+'#'+value+'#' for key,value in replacements.items() if key not in used]
    rows += ['Train Diagram Document#'+ascii_path(collector)+'#']
    job.mkdir(parents=True)
    (job/'capture-output').mkdir()
    (job/'Grid3x3.otsimnet').write_bytes(blank)
    (job/'capture.run').write_text('\n'.join(rows)+'\n',encoding='ascii')
    for name,raw in inputs.items():
        path=job/'inputs'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    receipt={'schema':'prepared-native-grid-capture/1','project':ascii_path(project),
             'original_exe_sha256_required':EXE_SHA,'input_sha256':{n:sha(v) for n,v in inputs.items()},
             'empty_collector_sha256':sha(blank),'fake_events_added':False,
             'native_application_executed':False,'collector_native_populated':False,
             'important_writeback':'Native -scriptinit may write actuals to the project timetable. Inputs are backed up; preserve actual writeback before restoring the clean plan.',
             'next':'Close conflicting native sessions, verify EXE SHA, then run original EXE -scriptinit -runfile=<this job>/capture.run. Require actual populated 33-course/9-station collector and fresh outputs.'}
    write(job/'capture-preparation.json',receipt)
    return {'prepared':str(job),'native_application_executed':False,'seed_bytes':len(blank),'input_files':len(inputs)}

def project_h2(args):
    reader,profile=setup(args.root)
    recipe_path=reader.path(args.recipe)
    recipe=json.loads(reader.secure_bytes(recipe_path).decode('utf-8-sig'))
    need({'plans','proofs','traces'}<=set(recipe),'Recipe must retain actual grid plans/proofs/traces')
    project=reader.path(args.project)
    need(Path(recipe['execution_root'])==project,'Recipe must describe this actual execution root')
    profile.TARGET=project
    profile.DOC_PATHS={n:project.as_posix()+'/OTDocuments/'+n+'.opentrack' for n in profile.STATIONS}
    source=reader.path(args.collector)
    need(sha(reader.secure_bytes(source))==args.collector_sha256,'Collector SHA differs')
    donor=reader.path(args.donor)
    need(sha(reader.secure_bytes(donor))==DONOR_SHA,'Verified external display donor required')
    output=reader.path(args.capture_output)
    for course in COURSES:reader.secure_bytes(output/('OT_'+course+'.st1'))
    job=fresh(reader,args.job_dir)
    sys.path.insert(0,str(ASSET))
    import h2_projection as h2
    h2.AUTHORIZATION_ROOT=reader.root
    h2.HERE=job;h2.BASE=recipe_path.parent;h2.RECIPE=recipe_path
    h2.SOURCE=source;h2.SOURCE_SHA=args.collector_sha256;h2.DONOR=donor
    h2.PROJECT=project;h2.OUTPUT=job/'H2_Actual.otsimcor';h2.CAPTURE_OUTPUT=output
    job.mkdir(parents=True)
    h2.main()
    return {'projected':str(h2.OUTPUT),'native_application_executed':False,
            'scope':'Five complete H2 through courses; preserve reported st1 residuals'}

def c_literal(text, wide=False):
    return ('L' if wide else '')+json.dumps(str(text),ensure_ascii=True)

def original_exe_bytes(root, path):
    """Read the explicit app path; archive-only readers reject app directories."""
    from yard import require_software_authorization
    require_software_authorization(root)
    import stat
    current=root
    for part in ('.', *path.relative_to(root).parts):
        if part!='.':current=current/part
        meta=current.lstat()
        need(not stat.S_ISLNK(meta.st_mode) and not (getattr(meta,'st_file_attributes',0)&0x400),
             'Original app path must not traverse symlinks or reparse points')
    need(path.is_file() and path.stat().st_size<=32*1024*1024,'Bounded original EXE required')
    return path.read_bytes()

def prepare_export(args):
    from yard import require_software_authorization
    authorization=require_software_authorization(args.root)
    reader,profile=setup(args.root)
    authorization_expiry=authorization.get('expires_unix_seconds',0)
    need(type(authorization_expiry) is int and authorization_expiry>=0,
         'Invalid normalized authorization expiry')
    need(not authorization.get('expires_at') or authorization_expiry>0,
         'Authorization expiry must be validated and normalized before preparing a native job')
    exe_relative=Path(args.exe)
    need(not exe_relative.is_absolute() and '..' not in exe_relative.parts,
         'EXE must be an explicit traversal-free relative path within --root')
    exe=reader.root/exe_relative
    corridor=reader.path(args.corridor)
    need(sha(original_exe_bytes(reader.root,exe))==EXE_SHA,'Unsupported original EXE SHA; do not change guard addresses')
    raw=reader.secure_bytes(corridor)
    need(len(raw)<=64*1024*1024,'Corridor exceeds bounded input size')
    w,pf=profile.w,profile.pf
    root,version=w.load_next_compatible(raw)
    need(w.kind(root)=='OTCorridorDocument' and root.clazz.version==11 and len(root.contents)==24,
         'Only the reviewed legacy v11 offline H2 Corridor profile is supported')
    need(root.contents[6].value==0 and root.contents[13].value==0x8508,
         'Offline, non-live, non-occupation display profile required')
    need(root.contents[7].values==[32400.0,33900.0], 'Only the reviewed 09:00-09:25 H2 window is supported')
    stations=array(root.contents[15].value)
    need([pf.string(s.contents[0].value) for s in stations]==['J21','J22','J23'],'Expected J21/J22/J23 H2 stations')
    need([s.contents[1].values[1] for s in stations]==[0,6000,12000],'Expected actual 12km H2 corridor')
    controller=root.contents[0].value
    need(w.kind(controller)=='OTTCorridorSimController' and controller.clazz.version==1 and len(controller.contents)==4,
         'Expected legacy v1 four-dictionary simulation controller')
    need(all(dictionary(controller.contents[i].value,pf)=={} for i in (0,2,3)),
         'Conflicts and occupation dictionaries must be empty in this actual-curve profile')
    events=dictionary(controller.contents[1].value,pf)
    need(set(events)==set(COURSES),'Only the five complete H2 course IDs are supported')
    counts=[len(array(events[c].contents[0].value)) for c in COURSES]
    need(all(100<n<=1000000 for n in counts),'Unexpected native point counts')
    for series in events.values():
        import math
        need(w.kind(series)=='OTSimEventArray' and len(series.contents)==2, 'Unexpected native event container')
        points=array(series.contents[0].value)
        for index,point in enumerate(points):
            need(w.kind(point)=='OTCorridorSimEvent' and len(point.contents)==3 and
                 [g.encodings for g in point.contents]==[[b'f'],[b'f'],[b'i']], 'Unexpected native point shape')
            time,metres,mode=[g.value for g in point.contents]
            need(math.isfinite(time) and math.isfinite(metres) and
                 32400<=time<=33900 and 0<=metres<=12000 and mode==(1 if index==0 else 0),
                 'Native point outside the finite H2 time/distance/draw domain')
        times=[p.contents[0].value for p in points]
        need(all(a<=b for a,b in zip(times,times[1:])),'Unordered native times')
    job=fresh(reader,args.job_dir)
    ascii_path(exe);ascii_path(corridor)
    job.mkdir(parents=True)
    for source in ASSET.glob('*'):
        if source.suffix in ('.c','.h'):
            text=source.read_text('utf-8-sig')
            if source.name=='direct_export.c':
                text=re.sub(r'static const unsigned g_expectedCounts\[5\] = \{[^}]+\};',
                            'static const unsigned g_expectedCounts[5] = {'+','.join(map(str,counts))+'};',text)
            (job/source.name).write_text(text,encoding='utf-8')
    definitions={'EXPORT_ROOT_W':c_literal(str(job),True),'EXPORT_ROOT_A':c_literal(job.as_posix()),
                 'ORIGINAL_EXE_W':c_literal(str(exe),True),'ORIGINAL_SHA':c_literal(EXE_SHA),
                 'ORIGINAL_COMMAND_W':c_literal('"'+str(exe)+'"',True),'ORIGINAL_CWD_W':c_literal(str(exe.parent),True),
                 'CORRIDOR_W':c_literal(str(corridor),True),'CORRIDOR_A':c_literal(corridor.as_posix()),
                 'CORRIDOR_SHA':c_literal(sha(raw)),
                 'AUTHORIZATION_RECORD_W':c_literal(authorization['record_path'],True),
                 'AUTHORIZATION_RECORD_SHA':c_literal(authorization['record_sha256']),
                 'AUTHORIZATION_EXPIRES_UNIX':str(authorization_expiry)+'ULL',
                 'EPS_A':'EXPORT_ROOT_A "/H2_Actual.eps"','TIFF_A':'EXPORT_ROOT_A "/H2_Actual.tiff"',
                 'READY_EVENT':'L"Local\\\\OpenTrack.NativeExport.Ready.%lu"',
                 'FAILED_EVENT':'L"Local\\\\OpenTrack.NativeExport.Failed.%lu"',
                 'OWNED_EVENT':'L"Local\\\\OpenTrack.NativeExport.Owned.%lu"'}
    header='#ifndef NATIVE_EXPORT_CONTRACT_H\n#define NATIVE_EXPORT_CONTRACT_H\n'
    header+=''.join('#define '+key+' '+value+'\n' for key,value in definitions.items())
    header+='int verify_sha256(const wchar_t *path, const char *expected);\nint verify_software_authorization(void);\n#endif\n'
    (job/'contract.h').write_text(header,encoding='ascii')
    build='@echo off\nsetlocal\ncd /d "%~dp0"\n'
    if args.vcvars:
        vc=Path(args.vcvars).resolve();ascii_path(vc);need(vc.is_file(),'vcvarsall.bat not found')
        build+='call "'+str(vc)+'" x86\nif errorlevel 1 exit /b 1\n'
    else:
        build+='if /I not "%VSCMD_ARG_TGT_ARCH%"=="x86" (echo Use an x86 MSVC developer prompt. & exit /b 1)\n'
    if args.sdk_root:
        sdk=Path(args.sdk_root).resolve();ascii_path(sdk);need(sdk.is_dir(),'SDK root missing')
        need(args.sdk_version is not None and re.fullmatch(r'[0-9]+(?:\.[0-9]+){3}',args.sdk_version),'Explicit numeric SDK version required')
        build+='set "SDKROOT='+str(sdk)+'"\nset "SDKVER='+args.sdk_version+'"\n'
        build+='set "INCLUDE=%SDKROOT%\\Include\\%SDKVER%\\ucrt;%SDKROOT%\\Include\\%SDKVER%\\shared;%SDKROOT%\\Include\\%SDKVER%\\um;%INCLUDE%"\n'
        build+='set "LIB=%SDKROOT%\\Lib\\%SDKVER%\\ucrt\\x86;%SDKROOT%\\Lib\\%SDKVER%\\um\\x86;%LIB%"\n'
    build+='''set CFLAGS=/nologo /c /O2 /MT /W4 /WX /utf-8 /D_CRT_SECURE_NO_WARNINGS /D_WIN32_WINNT=0x0601
cl %CFLAGS% direct_export.c native_runtime.c ui_dispatch.c ot_exception.c proofs.c
if errorlevel 1 exit /b 1
link /nologo /DLL /MACHINE:X86 /OUT:native-export.dll direct_export.obj native_runtime.obj ui_dispatch.obj ot_exception.obj proofs.obj user32.lib advapi32.lib
if errorlevel 1 exit /b 1
cl %CFLAGS% launch_owned.c
if errorlevel 1 exit /b 1
link /nologo /MACHINE:X86 /SUBSYSTEM:CONSOLE /OUT:launch-owned.exe launch_owned.obj proofs.obj user32.lib advapi32.lib
exit /b %errorlevel%
'''
    (job/'build.cmd').write_text(build,encoding='ascii')
    result={'schema':'prepared-native-H2-export-job/1','original_EXE':str(exe),'original_EXE_sha256':EXE_SHA,
            'corridor':str(corridor),'corridor_sha256':sha(raw),'course_event_counts':dict(zip(COURSES,counts)),
            'software_authorization':{'record_path':authorization['record_path'],
                                      'record_sha256':authorization['record_sha256'],
                                      'required_original_license':'full','expires_unix_seconds':authorization_expiry,
                                      'attestation_only':True,
                                      'vendor_verification_performed':False},
            'compiled':False,'native_application_executed':False,'native_export_verified':False,
            'execution':'Review generated sources, compile x86 with build.cmd, run launch-owned.exe --check, then --run-native-export only within authorized native work. Never attach to an existing process.',
            'licence':'Requires user full-license attestation; missing/changed/revoked record invalidates this job. Original versionAllowsSaving is still checked twice; false stops. No bypass.',
            'idle_boundary':'Original successful case resumed its native pump after about40s. Launcher timeout leaves child open; inspect PID/log/files before any retry.'}
    write(job/'job-preparation.json',result)
    return {'prepared':str(job),'native_application_executed':False,'course_event_counts':dict(zip(COURSES,counts))}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare-capture');p.add_argument('--root',required=True);p.add_argument('--project',required=True)
    p.add_argument('--donor',required=True);p.add_argument('--job-dir',required=True)
    p.set_defaults(action=prepare_capture)
    p=sub.add_parser('project-h2');p.add_argument('--root',required=True);p.add_argument('--project',required=True)
    p.add_argument('--recipe',required=True);p.add_argument('--collector',required=True);p.add_argument('--collector-sha256',required=True)
    p.add_argument('--donor',required=True);p.add_argument('--capture-output',required=True);p.add_argument('--job-dir',required=True)
    p.set_defaults(action=project_h2)
    p=sub.add_parser('prepare-export');p.add_argument('--root',required=True);p.add_argument('--exe',required=True)
    p.add_argument('--corridor',required=True);p.add_argument('--job-dir',required=True)
    p.add_argument('--vcvars');p.add_argument('--sdk-root');p.add_argument('--sdk-version')
    p.set_defaults(action=prepare_export)
    args=parser.parse_args(argv)
    try:
        print(json.dumps(args.action(args),ensure_ascii=True));return 0
    except Exception as exc:
        print(json.dumps({'passed':False,'error_type':type(exc).__name__,'error':str(exc),
                          'code':getattr(exc,'code',None),'native_application_executed':False},ensure_ascii=True));return 2

if __name__=='__main__':raise SystemExit(main())
