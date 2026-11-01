"""Strict selected-run relocation; immutable bytes only, never a writer/launcher.

Document renaming is excluded. Relative native ExtInfo/Connector names remain
unchanged and cross-document Project validates their exact identity closure.
"""
import re
from opentrack_ai.current_archive import writer as w, path_functions as f, route_factory as rf, catalogs as c, course_factories as cf, runfile_parameters as rp
from opentrack_ai.current_archive.zero_operations import run_bundle as rb
from ..multi_document.core import Project

class RelocationError(ValueError): pass
def need(ok,msg):
    if not ok: raise RelocationError(msg)
def sha(b):return rb.sha(b)
def norm(s):return s.replace('\\','/')
DIAGRAM=['@','@','@','@','@','@','i','ff','@','ffff','iii','ff','@','i','ffff','@','@','i','@','@','@','i','i','@','ii','@']
def _absolute(s):return bool(re.match(r'^[A-Za-z]:[/\\]',s)) or s.startswith(('/', '\\\\'))
def _layout(o,kind,version,groups):
    f.hierarchy(o,[(kind,version),('NSObject',0)])
    need(all(len(g.encodings)==len(g.values)for g in o.contents),'Malformed group cardinality')
    need([''.join(e.decode() for e in g.encodings)for g in o.contents]==groups,'Unsupported '+kind+' exact layout')
def _patch_archive(blob, fields):
    root,version=w.load(blob); allowed={}; changes=[]
    for owner,index,old,new in fields(root):
        obj=owner.contents[index].value
        need(w.kind(obj)=='NSString','Path field must use immutable NSString')
        current=w.string(obj);need(norm(current)==old,'Archive authoritative path mismatch')
        need(id(obj)not in allowed or allowed[id(obj)][1]==new,'Conflicting shared path string')
        allowed[id(obj)]=(obj,new);changes.append((owner,index,current,new))
    
    
    slots={(id(o),i)for o,i,_,_ in changes}
    for o in w.objects(root):
        if w.kind(o)in ('NSString','NSMutableString'):
            s=w.string(o)
            need(not _absolute(s) or id(o)in allowed,'Unrecognized absolute archive path')
        for i,g in enumerate(o.contents):
            for val in g.values:
                if id(val)in allowed:need((id(o),i)in slots and g.encodings==[b'@'],'Path string aliased outside typed allowlist')
    before=w.dump(root,version)
    originals={k:obj.contents[0].value for k,(obj,new)in allowed.items()}
    for obj,new in allowed.values():obj.contents[0].value=new.encode('utf-8')
    output=w.dump_verified(root,version)
    for k,(obj,new)in allowed.items():obj.contents[0].value=originals[k]
    need(w.dump(root,version)==before,'Non-target archive graph altered')
    return output,len(changes)

def relocate_project(files, *, source_root, target_root, run_file, expected_hashes, output_directory='output'):
    """Return (selected closure bytes, receipt). No filename rename or extra files."""
    need(type(files)is dict and 8<=len(files)<=1000,'Bounded exact selected project files required')
    source=rb.root_path(source_root,'windows');target=rb.root_path(target_root,'windows')
    need(source==source_root and target==target_root and source.casefold()!=target.casefold(),'Distinct canonical roots required')
    rb.relative(run_file);rb.relative(output_directory)
    need(run_file.endswith('.run') and run_file in files,'Explicit selected run member required')
    for p,b in files.items():rb.relative(p);need(type(b)is bytes and 0<len(b)<=20*1024*1024,'Bounded immutable source bytes required')
    need({p:sha(b)for p,b in files.items()}==expected_hashes,'Exact complete source hash manifest mismatch')
    folded=[p.casefold()for p in files];need(len(set(folded))==len(folded),'Case-insensitive member alias')
    need(not any(q.startswith(p+'/')for p in folded for q in folded if p!=q),'File/directory member collision')
    from ..prepare_contract import auxiliary as aux
    rows=aux.records(files[run_file]); vals={k:v for k,v,_ in rows if k}
    clock=rp.inspect_runfile(aux.core_bytes(rows));need(clock['editable'],'Invalid explicit run time contract')
    types=[v for k,v,_ in rows if k=='TrainType'];need(types and len({v.casefold()for v in types})==len(types),'Unique explicit TrainType map required')
    for name in types:rb.ascii_text(name);need(len(name)<=200,'TrainType name too long')
    def member(value):
        value=norm(value);need(value.startswith(source+'/'),'Input path outside exact source root')
        rel=value[len(source)+1:];rb.relative(rel);need(rel in files,'Referenced member missing');return rel
    roles={role:member(vals.get(key,''))for role,key in rb.CATALOG_KEYS.items()}
    docs=[member(v)for k,v,_ in rows if k=='Infrastructure Document']
    diagrams=[member(v)for k,v,_ in rows if k=='Train Diagram Document']
    docsets=[member(v)for k,v,_ in rows if k=='Document Set Document']
    aux.set_bindings(rows,[v for k,v,_ in rows if k in ('Infrastructure Document','Train Diagram Document')])
    need(len({p.casefold() for p in docs})==len(docs),'Duplicate infrastructure declaration')
    roots={role:w.load(files[p])[0]for role,p in roles.items()}
    c.engine_items(roots['depot']);c.train_items(roots['trains']);c.course_items(roots['courses']);c.station_items(roots['stations']);cf.timetable(roots['timetable'])
    aux.incident_bindings(files[roles['courses']],[v for k,v,_ in rows if k=='Incident'])
    selected=list(roles.values())+docs+diagrams
    need(set(selected)|{run_file}==set(files),'Supplied files must be exact selected-run dependency closure')
    rb._layout({p:files[p]for p in selected},roles,docs,diagrams,output_directory)
    need(output_directory.casefold()!=run_file.casefold() and not run_file.casefold().startswith(output_directory.casefold()+'/') and not output_directory.casefold().startswith(run_file.casefold()+'/'),'Output overlaps run file')
    need('OutputPath'in vals and bool(vals['OutputPath']),'Explicit source OutputPath required')
    rb.root_path(norm(vals['OutputPath']),'windows') 
    need('Document Set Name'not in vals or docsets,'Orphan Document Set Name')
    docbytes={p.rsplit('/',1)[-1][:-10]:files[p]for p in docs}
    need(len(docbytes)==len(docs),'Ambiguous document basenames')
    paths={p.rsplit('/',1)[-1][:-10]:source+'/'+p for p in docs}
    project=Project(docbytes,document_paths=paths,expected_hashes={k:sha(v)for k,v in docbytes.items()},complete_document_set=True)
    project.check_dest_catalog(files[roles['dest']])
    out=dict(files); counts={}
    def dest_fields(root):
        for row in rf.wrapper(root,'OTDestInfoList'):
            _layout(row,'OTDestInfo',1,['i','@','@','i','@'])
            old=norm(f.string(row.contents[2].value));rel=member(old);need(rel in docs,'Dest owner not infrastructure')
            yield row,2,old,target+'/'+rel
    out[roles['dest']],counts['dest_owner_paths']=_patch_archive(files[roles['dest']],dest_fields)
    for p in diagrams:
        def diagram_fields(root,p=p):
            _layout(root,'OTCorridorDocument',13,DIAGRAM)
            yield root,2,source+'/'+p,target+'/'+p
        out[p],n=_patch_archive(files[p],diagram_fields);counts[p]=n
    
    for p in selected:
        if p==roles['dest']or p in diagrams:continue
        root,_=w.load(files[p])
        need(not any(_absolute(w.string(o))for o in w.objects(root)if w.kind(o)in ('NSString','NSMutableString')),'Unknown absolute reference in unchanged archive '+p)
    emitted=[]
    for k,v,raw in rows:
        if k in rb.PATH_KEYS:
            new=target+'/'+output_directory if k=='OutputPath' else target+'/'+member(v)
            newline=b'\r\n'if raw.endswith(b'\r\n')else b'\n'
            emitted.append((k+'#'+new+'#').encode('ascii')+newline)
        else:emitted.append(raw)
    out[run_file]=b''.join(emitted);aux.records(out[run_file])
    newpaths={dn:target+p[len(source):]for dn,p in paths.items()}
    Project(docbytes,document_paths=newpaths,expected_hashes={k:sha(v)for k,v in docbytes.items()},complete_document_set=True).check_dest_catalog(out[roles['dest']])
    need(b''.join(raw for k,v,raw in rows if k not in rb.PATH_KEYS)==b''.join(raw for k,v,raw in aux.records(out[run_file])if k not in rb.PATH_KEYS),'Non-path run records changed')
    return out,{'operation':'relocate_selected_run_closure','source_root':source,'execution_root':target,'run_file':run_file,'output_directory':target+'/'+output_directory,'member_count':len(out),'documents':docs,'diagrams':diagrams,'catalog_paths':roles,'path_changes':counts,'source_sha256':expected_hashes,'output_sha256':{p:sha(b)for p,b in out.items()},'unchanged_members':[p for p in files if files[p]==out[p]],'document_names_and_extinfo_basenames_preserved':True,'selected_run_dependency_closure_only':True,'simulation_executed':False,'native_runtime_ready':False,'saved':False}
