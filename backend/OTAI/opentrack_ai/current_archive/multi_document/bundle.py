"""Complete no-service project manifest validator. Bytes only; wrapper commits."""
from .core import *
from opentrack_ai.current_archive.zero_operations import run_bundle as rb
from opentrack_ai.current_archive import catalogs as c, runfile_parameters as rp

def validate_no_service_bundle(files,*,run_file,expected_hashes,complete_file_set):
    need(complete_file_set is True and type(files)is dict and 8<=len(files)<=1000,'Bounded complete file inventory attestation required')
    
    
    
    for path,blob in files.items():
        rb.relative(path);need(type(blob)is bytes and 0<len(blob)<=20*1024*1024,'Nonempty immutable member bytes up to 20 MiB required')
    rb.relative(run_file);need(run_file.endswith('.run'),'Explicit .run member required')
    folded=[p.casefold()for p in files]
    need(len(set(folded))==len(folded),'Case-insensitive project-member collision including run')
    need(not any(q.startswith(p+'/')for p in folded for q in folded if p!=q),'Project member file/directory collision including run')
    need({k:sha(v)for k,v in files.items()}==expected_hashes,'Complete file hash manifest mismatch')
    need(run_file in files,'Run file missing');rows=rb.records(files[run_file]);values={k:v for k,v,_ in rows if k}
    clock=rp.inspect_runfile(files[run_file]);need(clock['editable'],'Invalid/missing explicit run time contract: '+str(clock['issues']))
    names=[v for k,v,_ in rows if k=='TrainType']
    need(1<=len(names)<=100,'Explicit nonempty bounded TrainType mapping required')
    for name in names:
        rb.ascii_text(name)
        need(len(name)<=200 and not any(k.decode().lower()in name.lower()for k in rp.KNOWN),'TrainType native keyword collision/length refused')
    need(len({n.casefold()for n in names})==len(names),'Case-insensitive duplicate TrainType')
    
    
    
    fresh_options=dict(rb.FRESH_RUN_OPTIONS)
    allowed=set(rb.CATALOG_KEYS.values())|{'OutputPath','Infrastructure Document','TrainType'}|{k.decode()for k in rp.WRITABLE}|set(fresh_options)
    need(set(values)<=allowed,'Optional native run options outside strict no-service validation profile')
    for key,value in values.items():
        if key in fresh_options:
            need(value==fresh_options[key],'Non-default native presentation/output option outside strict no-service validation profile: '+key)
    docs=[v for k,v,_ in rows if k=='Infrastructure Document'];need(docs,'No infrastructure documents')
    need(not any(k in ('Train Diagram Document','Document Set Document','Document Set Name')for k,v,_ in rows),'Document-set/diagram profile not implemented')
    
    
    paths={};rolepaths={}
    for role,key in rb.CATALOG_KEYS.items():
        value=values.get(key);need(value,'Missing run catalog '+key)
        matches=[p for p in files if p!=run_file and value.endswith('/'+p)]
        need(len(matches)==1,'Missing/ambiguous run member '+key);rolepaths[role]=matches[0];paths[key]=value[:-len(matches[0])-1]
    need(len(set(paths.values()))==1,'Mixed execution roots');root=next(iter(paths.values()));need(rb.root_path(root,'windows')==root,'Noncanonical execution root')
    docpaths=[];docblobs={};absolute={}
    for full in docs:
        need(full.startswith(root+'/'),'Infrastructure path outside execution root');rel=full[len(root)+1:];need(rel in files,'Missing run infrastructure document')
        name=stem(rel);need(name not in docblobs,'Duplicate document basename');docblobs[name]=files[rel];absolute[name]=full;docpaths.append(rel)
    allrefs=set(rolepaths.values())|set(docpaths)|{run_file};need(allrefs==set(files),'Unreferenced/extra/missing project files')
    output=values.get('OutputPath','');need(output.startswith(root+'/'),'OutputPath must stay under the exact execution root')
    output_relative=output[len(root)+1:];rb.relative(output_relative);of=output_relative.casefold()
    need(all(p!=of and not p.startswith(of+'/')and not of.startswith(p+'/')for p in folded),'Output directory overlaps a project member including run')
    rb._layout({p:b for p,b in files.items()if p!=run_file},rolepaths,docpaths,[],output_relative)
    project=Project(docblobs,document_paths=absolute,expected_hashes={k:sha(v)for k,v in docblobs.items()},complete_document_set=True);project.check_dest_catalog(files[rolepaths['dest']])
    catalog_roots={k:w.load(files[p])[0]for k,p in rolepaths.items()}
    need(not c.engine_items(catalog_roots['depot']) and not c.train_items(catalog_roots['trains']) and not c.course_items(catalog_roots['courses']),'This complete bundle validator is explicitly no-service only')
    for role,slots in (('trains',(1,2,3)),('courses',(1,2,3,4))):
        catalog=catalog_roots[role]
        need(catalog.contents[0].value==17,'Current no-service catalog marker17 required')
        need(all(not c.array(catalog.contents[i].value)for i in slots),'Every no-service '+role+' catalog array must be empty, including auxiliary arrays')
    table=catalog_roots['timetable'];layout(table,[('NSMutableDictionary',0),('NSDictionary',0),('NSObject',0)],['i']);need(type(table.contents[0].value)is int and table.contents[0].value==0,'No-service timetable must be empty')
    stations=c.station_items(catalog_roots['stations']);model_signs=[]
    need(all(s.contents[0].value==17 for s in stations.values()),'Current Station record marker17 required')
    for dn,models in project.models.items():
        signs=[]
        for m in models:
            if w.kind(m)=='OTStationModel':
                rf.layout(m,'OTStationModel',1,['i','f','f','f','i','i','@','@','ii','ii'],graphic=True)
                need(m.contents[8].values==[2,4]and m.contents[9].values==[1,0],'Only generated point-station model profile 2/4/1 supported')
                need(any(e.contents[12].value is m for e in project.ends(dn)),'Unbound StationModel in no-service point profile')
                sign=f.string(m.contents[7].value);need(sign in stations,'Unresolved StationModel catalog sign');signs.append(sign)
        need(len(signs)==len(set(signs)),'Duplicate StationModel sign in document');model_signs+=signs
        for e in project.ends(dn):
            st=e.contents[12].value
            if st is not None:need(st in models and w.kind(st)=='OTStationModel','End station model outside document')
            pair=project.model(project.related(project.key(e)))
            need(e.contents[20].value in (1,2)and pair.contents[20].value==e.contents[20].value,'Point-station paired End type mismatch')
            need(pair.contents[12].value is st and (e.contents[20].value==2)==(st is not None),'Point-station pair association/type mismatch')
    need(set(model_signs)==set(stations),'Station catalog/model closure mismatch')
    return dict(member_count=len(files),all_member_hashes=expected_hashes,complete_run_inventory_checked=True,explicit_time_contract=clock['numeric'],train_types=names,strict_no_service_run_options=True,documents=list(docblobs),destination_count=len(project.dests),station_count=len(stations),cross_document_route_path_dest_refs_resolved=True,no_service_catalogs=True,native_execution_verified=False)
