"""Pure-byte execution-root binding, not a runtime launcher or filesystem writer."""
import hashlib
import math
import re
from pathlib import PurePosixPath, PureWindowsPath
from opentrack_ai.current_archive import runfile_parameters as rp

class RunBundleError(ValueError): pass

def need(ok, message):
    if not ok: raise RunBundleError(message)

def sha(blob): return hashlib.sha256(blob).hexdigest()

CATALOG_KEYS={'dest':'DestInfoFile','depot':'DepotFile','trains':'TrainFile','courses':'CourseFile','stations':'StationFile','timetable':'TimetableFile'}
EXTENSIONS={r:'.'+r for r in CATALOG_KEYS}
PATH_KEYS=set(CATALOG_KEYS.values())|{'OutputPath','Infrastructure Document','Train Diagram Document','Document Set Document'}
TARGET_KEYS=PATH_KEYS|{'Document Set Name','TrainType'}|{x.decode() for x in rp.WRITABLE}
REJECT_KEYS={'Incident'}
RESERVED={'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}



FRESH_RUN_OPTIONS = (
    ('Time Ratio','Best'), ('Show Train','1'), ('Show Train ID','1'),
    ('Show Current Time','1'), ('Show Messages','1'), ('Show Instruments','1'),
    ('Output Timetable (Text)','1'), ('Output Distance/Time','1'),
    ('Output Speed/Time','1'), ('Output Route Occ.','1'),
    ('Output Messages (Text)','1'), ('Output Course & Station Statistics','1'),
    ('Output Timetable & Delay Statistics','1'), ('Output Simulation Protocol','1'),
)

def ascii_text(s):
    need(type(s)is str and s and all(32<=ord(c)<127 for c in s),'Nonempty printable ASCII required')
    need(s==s.strip() and not any(c in s for c in '#%$'),'Whitespace edges or native separator/macros unsupported')
    return s

def relative(path):
    ascii_text(path)
    need(not path.startswith('/') and '\\' not in path and not any(c in path for c in ':<>"|?*'),'Canonical portable relative POSIX member required')
    parts=path.split('/')
    need(all(p not in ('','.', '..') and not p.endswith((' ','.')) and p.split('.')[0].upper() not in RESERVED for p in parts),'Unsafe/ambiguous relative member component')
    return path

def root_path(root, style):
    ascii_text(root)
    need(style in ('windows','posix'),'Explicit target path style required')
    need(not any(c in root for c in '<>"|?*'),'Ambiguous absolute execution root')
    if style=='windows':
        root=root.replace('\\','/')
        need(bool(re.fullmatch(r'[A-Za-z]:/[^:]+',root)),'Only drive-absolute Windows roots, not UNC/drive-relative paths')
        prefix=root[:3];tail=root[3:]
    else:
        need(root.startswith('/') and not root.startswith('//') and '\\' not in root and ':' not in root,'POSIX absolute root required')
        prefix='/';tail=root[1:]
    need(tail and not tail.endswith('/'),'Non-root canonical execution directory without trailing separator required')
    relative(tail)
    return prefix+tail

def records(blob, allow_empty=False):
    need(type(blob)is bytes and len(blob)<=1048576,'Immutable bytes up to 1MiB required')
    need(blob or allow_empty,'Empty run not valid')
    need(not blob or blob.endswith(b'\n'),'Terminated native records required')
    need(all(c<128 and (c>=32 or c in (10,13)) for c in blob),'ASCII only, no NUL/control bytes')
    out=[];seen={}
    
    for chunk in blob.split(b'\n')[:-1]:
        line=chunk+b'\n'
        need(len(line)<=1023,'Record exceeds native fgets(1024) boundary')
        body=line[:-2] if line.endswith(b'\r\n') else line[:-1]
        need(b'\r' not in body,'Bare CR rejected')
        if not body or body.startswith(b'//'):
            out.append((None,None,line));continue
        pieces=body.split(b'#')
        need(len(pieces)==3 and pieces[2]==b'' and pieces[0] in rp.KNOWN,'Unknown/noncanonical run record')
        k,v=pieces[:2]
        for group in rp.NATIVE_GROUPS:
            hit=next((t for t in group if t in body),None)
            need(hit is None or hit==k,'Native whole-line strstr collision')
        key=k.decode();value=v.decode()
        need(key not in REJECT_KEYS,'Incident binding not in supported fresh-bundle profile')
        need(key not in seen or k in rp.REPEATED,'Duplicate singleton run key')
        seen[key]=value;out.append((key,value,line))
    return out

def _layout(files,catalog_paths,document_paths,diagram_paths,output_directory):
    need(type(files)is dict and 7<=len(files)<=1000,'Bounded nonempty project bytes mapping required')
    for p,b in files.items():
        relative(p);need(type(b)is bytes and b,'Nonempty immutable member bytes required')
    folded=[p.casefold() for p in files]
    need(len(set(folded))==len(folded),'Case-insensitive member alias')
    for p in folded:
        need(not any(q.startswith(p+'/') for q in folded if p!=q),'Member file/directory collision')
    need(type(catalog_paths)is dict and set(catalog_paths)==set(CATALOG_KEYS),'Exactly six explicit catalog roles required')
    need(type(document_paths)is list and 1<=len(document_paths)<=100 and type(diagram_paths)is list,'Explicit bounded document lists required')
    selected=list(catalog_paths.values())+document_paths+diagram_paths
    for p in selected:relative(p);need(p in files,'Referenced member is missing from byte bundle')
    need(len(set(p.casefold() for p in selected))==len(selected),'Duplicate or role-aliased referenced member')
    for role,p in catalog_paths.items():need(p.endswith(EXTENSIONS[role]),'Catalog role extension mismatch')
    need(all(p.endswith('.opentrack') for p in document_paths),'Infrastructure extension mismatch')
    need(all(p.endswith('.otsimcor') for p in diagram_paths),'Diagram extension mismatch')
    
    need(set(files)==set(selected),'Unbound extra input members rejected')
    relative(output_directory)
    of=output_directory.casefold()
    need(all(p!=of and not p.startswith(of+'/') and not of.startswith(p+'/') for p in folded),'Output directory aliases/overlaps an input file or its subtree')
    return selected

def build_run(files, *, catalog_paths, document_paths, execution_root, path_style,
              train_types, start_day=0, start_time='00:00:00', stop_day=1,
              stop_time='00:00:00', step='0.2', output_directory='output',
              diagram_paths=None, template=b''):
    """Bind immutable members to a user-selected execution root, not the cloud staging root."""
    diagram_paths=[] if diagram_paths is None else diagram_paths
    selected=_layout(files,catalog_paths,document_paths,diagram_paths,output_directory)
    root=root_path(execution_root,path_style)
    need(type(train_types)is list and 1<=len(train_types)<=100,'Explicit ordered speed-type names required')
    for t in train_types:
        ascii_text(t);need(len(t)<=200 and not any(k.decode().lower() in t.lower() for k in rp.KNOWN),'TrainType name collides with run keyword')
    need(len({t.upper() for t in train_types})==len(train_types),'Case-insensitive duplicate TrainType')
    for d in (start_day,stop_day):need(type(d)is int and 0<=d<=24854,'Bounded nonnegative explicit day offset required')
    for t in (start_time,stop_time,step):ascii_text(t)
    original=records(template,True)
    if not template:
        original=records(b''.join((key+'#'+value+'#\n').encode('ascii') for key,value in FRESH_RUN_OPTIONS))
    retained=b''.join(raw for k,v,raw in original if k not in TARGET_KEYS)
    newline=b'\r\n' if any(raw.endswith(b'\r\n') for k,v,raw in original) else b'\n'
    def line(key,value):return (key+'#'+str(value)+'#').encode('ascii')+newline
    absolute=lambda p:root+'/'+p
    emitted=[]
    for role,key in CATALOG_KEYS.items():emitted.append((key,absolute(catalog_paths[role])))
    emitted.append(('OutputPath',absolute(output_directory)))
    emitted += [('Infrastructure Document',absolute(p)) for p in document_paths]
    emitted += [('Train Diagram Document',absolute(p)) for p in diagram_paths]
    emitted += [('TrainType',t) for t in train_types]
    emitted += [('Start Day Offset',start_day),('Start Time',start_time),('Stop Day Offset',stop_day),('Stop Time',stop_time),('Step',step)]
    output=retained+b''.join(line(k,v) for k,v in emitted)
    rows=records(output)
    checked=rp.inspect_runfile(output)
    need(checked['editable'],'Run time/record validation failed: '+str(checked['issues']))
    need(b'%PROJECT%' not in output,'Unresolved macro')
    
    need(b''.join(raw for k,v,raw in rows if k not in TARGET_KEYS)==retained,'Non-target option bytes changed')
    expected=[(k,str(v)) for k,v in emitted]
    need([(k,v) for k,v,raw in rows if k in TARGET_KEYS]==expected,'Run binding order mismatch')
    receipt={'operation':'bind_execution_run','execution_root':root,'path_style':path_style,
             'runtime_root_exists_verified':False,'native_runtime_verified':False,
             'simulation_executed':False,'complete_runtime_configuration':False,
             'window':checked['numeric'],'duration_is_24h':checked['numeric']['stop_seconds']-checked['numeric']['start_seconds']==86400,
             'ordered_train_types':train_types.copy(),'bindings':[{'key':k,'value':str(v)} for k,v in emitted],
             'template_sha256':sha(template),'run_sha256':sha(output),
             'fresh_run_options_applied':not bool(template),
             'fresh_run_options':dict(FRESH_RUN_OPTIONS) if not template else {},
             'members':{p:{'sha256':sha(files[p]),'bytes':len(files[p]),'execution_path':absolute(p)} for p in sorted(selected)},
             'output_directory':absolute(output_directory),'retained_non_target_keys':[k for k,v,raw in original if k and k not in TARGET_KEYS],
             'removed_template_keys':sorted({k for k,v,raw in original if k in TARGET_KEYS}),
             'scope':'literal path/name/time binding only; other application defaults, loading and simulation unverified'}
    receipt['configuration']={'catalog_paths':dict(catalog_paths),'document_paths':list(document_paths),
        'execution_root':root,'path_style':path_style,'train_types':list(train_types),
        'start_day':start_day,'start_time':start_time,'stop_day':stop_day,'stop_time':stop_time,
        'step':step,'output_directory':output_directory,'diagram_paths':list(diagram_paths)}
    return output,receipt

def verify_run(run,files,**configuration):
    """Rebind expected metadata and compare exact target records; all member bytes rehashed."""
    
    need('template' not in configuration,'Verifier owns candidate template')
    regenerated,receipt=build_run(files,template=run,**configuration)
    need(regenerated==run,'Run contains stale, missing, reordered or undeclared target bindings')
    return receipt

def verify_archive_bindings(run,files,*,catalog_paths,document_paths):
    """Current-format static cross-file/type/time checks. Not route dynamics or full Project validation."""
    from opentrack_ai.current_archive import writer as w, catalogs as c, course_factories as cf, route_factory as rf, path_functions as pf
    parsed=records(run);values={k:v for k,v,_ in parsed if k}
    clock=rp.inspect_runfile(run);need(clock['editable'],'Invalid run time/record contract')
    names=[v for k,v,_ in parsed if k=='TrainType']
    need(names and len({n.upper()for n in names})==len(names),'Explicit unique TrainType mapping required')
    need(set(catalog_paths)==set(CATALOG_KEYS),'Exactly six catalog roles required')
    first=catalog_paths['dest'];relative(first)
    need(values.get('DestInfoFile','').endswith('/'+first),'Run/catalog basename mismatch')
    root=values['DestInfoFile'][:-len(first)-1]
    style='windows' if re.match(r'^[A-Za-z]:/',root) else 'posix'
    need(root_path(root,style)==root,'Noncanonical execution root')
    for role,key in CATALOG_KEYS.items():need(values.get(key)==root+'/'+catalog_paths[role],'Run/catalog path binding mismatch')
    need([v for k,v,_ in parsed if k=='Infrastructure Document']==[root+'/'+p for p in document_paths],'Run/document path binding mismatch')
    need(not any(k in ('Train Diagram Document','Document Set Document','Document Set Name') for k,v,_ in parsed),'Auxiliary diagram/document-set semantic profile unsupported')
    out=values.get('OutputPath','');need(out.startswith(root+'/'),'Output is outside explicit execution root')
    _layout(files,catalog_paths,document_paths,[],out[len(root)+1:])
    roots={k:w.load_next_compatible(files[p])[0] for k,p in catalog_paths.items()}
    engines={c.text(e.contents[1].value):e for e in c.engine_items(roots['depot'])}
    trains={c.text(t.contents[0].value):t for t in c.train_items(roots['trains'])}
    courses={c.text(x.contents[0].value):x for x in c.course_items(roots['courses'])}
    stations=c.station_items(roots['stations']);itineraries=cf.itinerary_names(roots['dest'])
    need(courses and trains and engines,'Nonempty operations catalogs required')
    from opentrack_ai.current_archive.stock_operations import CATEGORY_LAYOUT
    categories={}
    for x in c.array(roots['trains'].contents[1].value):
        c.shape(x,'OTTrainCategory',19,CATEGORY_LAYOUT);n=c.text(x.contents[1].value)
        need(n not in categories,'Duplicate Category');categories[n]=x
    for t in trains.values():
        need(c.text(t.contents[3].value) in categories,'Missing Train Category')
        need(c.bound_engine_names(t) and set(c.bound_engine_names(t))<=set(engines),'Missing Train Engine')
    indices={};course_map={}
    for n,x in courses.items():
        typ=c.text(x.contents[4].value);matches=[i for i,s in enumerate(names)if s.upper()==typ.upper()]
        need(len(matches)==1,'Course speed-type missing; refusing native fallback0')
        idx=str(matches[0]);indices[typ]=idx;course_map[n]=idx
        need(c.text(x.contents[3].value)in trains,'Missing Course Train')
        its=[c.text(t)for t in c.array(x.contents[2].value)]
        need(its and set(its)<=itineraries,'Missing Course Itinerary')
    docs={};edges=0
    for p in document_paths:
        d=w.load_next_compatible(files[p])[0]
        rf.layout(d,'OTDocument',4,['i','i','@','i','i','@','@','@','ffff','ffff','ffff','f','@','@','ffff','iii','ff','@','@','@','@'])
        need(d.contents[0].value==17,'Current Document marker required')
        docname=p.rsplit('/',1)[-1][:-len('.opentrack')]
        need(docname.casefold()not in {x.casefold()for x in docs},'Ambiguous Document basename')
        docs[docname]=d
        for e in c.array(d.contents[2].value):
            if w.kind(e)!='OTEdgeModel':continue
            rf.layout(e,'OTEdgeModel',3,rf.EDGE,graphic=True);edges+=1
            speeds=cf.dictionary(e.contents[16].value)
            for idx in set(indices.values()):
                need(idx in speeds,'Used Course speed index missing from an Edge')
                speed=speeds[idx];c.shape(speed,'OTSpeed',0,['@','i','i','i'])
                need(all(type(v)is int and v>0 for group in speed.contents[1:3] for v in group.values),'Nonpositive/malformed direction speed limit')
    need(edges>0,'No infrastructure Edge')
    
    for di in c.array(roots['dest'].contents[0].value):
        for ref in c.array(di.contents[4].value):
            pf.hierarchy(ref,[('OTArrayExtInfo',0),('OTArrayInfo',0),('NSObject',0)])
            need([g.encodings for g in ref.contents]==[[b'@'],[b'i',b'i'],[b'@']] and all(len(g.encodings)==len(g.values)for g in ref.contents),'Invalid ExtInfo groups')
            need(c.text(ref.contents[2].value)in docs,'DestInfo references a missing infrastructure document')
    table=cf.timetable(roots['timetable']);by_course={k:[] for k in courses}
    lo=clock['numeric']['start_seconds'];hi=clock['numeric']['stop_seconds'];latest=lo
    def time(s,day):
        need(type(day)is int and 0<=day<=24854 and bool(re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]',s)),'Explicit canonical planned time/day required')
        h,m,sec=map(int,s.split(':'));return day*86400+h*3600+m*60+sec
    for row in table.values():
        owner=c.text(row.contents[1].value);need(owner in by_course,'Timetable refers to unknown Course')
        need(c.text(row.contents[5].value)in stations,'Timetable refers to unknown Station')
        index=row.contents[3].value;need(type(index)is int and index>=0,'Invalid stationIndex')
        a=time(c.text(row.contents[6].value),row.contents[15].values[0]);b=time(c.text(row.contents[7].value),row.contents[15].values[1])
        need(lo<=a<=b<=hi,'Planned time outside explicit run window')
        need(c.text(row.contents[13].value)==c.text(row.contents[14].value)=='HH:MM:SS' and row.contents[15].values[2:]==[0,0],'Expected unset actual results')
        by_course[owner].append((index,row.contents[4].value,a,b));latest=max(latest,b)
    for visits in by_course.values():
        visits.sort();need(visits and [r[0]for r in visits]==list(range(len(visits))),'Incomplete or duplicate stationIndex sequence')
        need(all(r[1]==len(visits)-1 for r in visits),'Timetable maxIndex mismatch')
        need(all(a[3]<b[2]for a,b in zip(visits,visits[1:])),'Non-increasing planned visits')
    return {'archive_bindings_checked':True,'courses':len(courses),'trains':len(trains),'stations':len(stations),
            'timetable_rows':len(table),'infrastructure_documents':len(docs),'edges':edges,
            'course_speed_type_to_edge_key':indices,'latest_planned_seconds':latest,
            'actual_results_unset':True,'full_project_verified':False,'simulation_executed':False,
            'scope':'current schema, existing member references, speed name/index and planned-window checks; not route motion, fleet or runtime defaults'}


def verify_manifest(run,files,receipt):
    """Validate exact immutable artifacts against a previously produced receipt."""
    need(type(receipt)is dict and receipt.get('operation')=='bind_execution_run','Expected binding receipt')
    need(type(files)is dict and set(files)==set(receipt.get('members',{})),'Manifest member set mismatch')
    need(sha(run)==receipt.get('run_sha256'),'Run hash differs from manifest')
    for path,blob in files.items():
        expected=receipt['members'][path]
        need(type(blob)is bytes and len(blob)==expected.get('bytes') and sha(blob)==expected.get('sha256'),'Member bytes differ from manifest')
    fresh=verify_run(run,files,**receipt['configuration'])
    for key in ('bindings','members','execution_root','ordered_train_types','window','output_directory'):
        need(fresh[key]==receipt[key],'Manifest binding metadata mismatch: '+key)
    return {'manifest_verified':True,'run_sha256':fresh['run_sha256'],'member_count':len(files),
            'native_runtime_verified':False,'simulation_executed':False}
