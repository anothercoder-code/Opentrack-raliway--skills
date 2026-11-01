"""Explicit final-stop infrastructure and eight-member byte composition."""
import re
from . import writer as w,catalogs as cats,path_functions as pf,route_factory as rf
from .zero_generation import topology as tp,native_signal_routes as ns
from .zero_operations import station_binding as sb
from .zero_terminal import terminal_areas as ta
from .multi_document import core as cd,operations as ops,generate as g
from .graphic_alignment import reject_legacy_alignment

def need(ok,msg):
    if not ok:raise ValueError(msg)

def compose_final_stop_infrastructure(header,shapes,*,expected_hashes,spec):
    need(type(header)is bytes and type(shapes)is bytes,'Immutable donor bytes required')
    need(expected_hashes=={'header':cd.sha(header),'shapes':cd.sha(shapes)},'Exact donor SHA binding required')
    need(type(spec)is dict and set(spec)=={'document_name','document_path','network','stations','signals','routes','paths','itineraries'},'Exact single-document specification required')
    name=spec['document_name'];need(type(name)is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,39}',name),'Safe document name required')
    need(cd.stem(spec['document_path'])==name,'Authoritative document path basename must match')
    for field in('signals','routes','paths','itineraries'):
        rows=spec[field];need(type(rows)is list and 1<=len(rows)<=100,'Explicit bounded nonempty '+field+' required')
        names=[r['name']for r in rows];need(len(names)==len(set(names)),'Duplicate '+field+' name')
    need(type(spec['stations'])is list and len(spec['stations'])<=100,'Bounded point-station list required')
    tp.validate_spec(spec['network']);need(len(spec['network']['vertices'])<=400 and len(spec['network']['edges'])<=800,'Finite infrastructure size exceeded')
    blob,top=tp.generate_network(header,shapes,spec['network']);ids=top['vertex_end_ids'];vertices={v['key']:v for v in spec['network']['vertices']};stage=[]
    def end(ref):
        need(type(ref)is dict and set(ref)=={'vertex','side'} and ref['vertex']in ids and type(ref['side'])is int and ref['side']in(0,1),'Exact known vertex/side required')
        return ids[ref['vertex']][ref['side']]
    for signal in spec['signals']:
        reject_legacy_alignment(signal)
        need(set(signal)=={'name','end','angle','alignment_x','alignment_y','sight_m','delay_s','show_symbol','show_icon'},'Exact signal fields required')
        eid=end(signal['end']);v=vertices[signal['end']['vertex']];_,_,_,index=ns.document(blob)
        blob,r=ns.build_main_signal(blob,end_id=eid,name=signal['name'],model_id=max(index)+1,placement={'x':v['x'],'y':v['y'],**{k:signal[k]for k in('angle','alignment_x','alignment_y')}},**{k:signal[k]for k in('sight_m','delay_s','show_symbol','show_icon')});stage.append(r)
    routes={}
    for route in spec['routes']:
        need(set(route)=={'name','ends','description','release_groups','reserve_previous'},'Exact Route fields required')
        blob,r=ns.build_route(blob,end_ids=[end(x)for x in route['ends']],**{k:route[k]for k in('name','description','release_groups','reserve_previous')});routes[route['name']]={'document':name,**{k:r[k]for k in('name','array_id','start_id')}};stage.append(r)
    version=w.load(blob)[1];area_specs=[]
    for st in spec['stations']:
        need(set(st)=={'sign','name','reference_end','ordinary_ends','placement','timing_point','station_type_raw','interlock_type_raw','icon_show_type_raw','stop'},'Exact explicit AreaStation required')
        row={k:st[k]for k in('sign','name','placement','timing_point','station_type_raw','interlock_type_raw','icon_show_type_raw')}
        row.update(reference_end_id=end(st['reference_end']),ordinary_end_ids=[end(x)for x in st['ordinary_ends']],stop=None)
        if st['stop'] is not None:
            stop=st['stop'];need(set(stop)=={'entry','exit','area_edge','length_m','exit_signal_name','direction'},'Exact area stop fields required')
            need(stop['area_edge']in top['edge_ids'],'Unknown area Edge')
            row['stop']=dict(entry_end_id=end(stop['entry']),exit_end_id=end(stop['exit']),area_edge_id=top['edge_ids'][stop['area_edge']],length_m=stop['length_m'],exit_signal_name=stop['exit_signal_name'],direction=stop['direction'])
        area_specs.append(row)
    need(any(s['stop'] is not None for s in area_specs),'At least one explicitly designed stop area required')
    blob,station_blob,r,_=ta.bind_areas(blob,area_specs);stage.append(r)
    documents={name:blob};docpaths={name:spec['document_path']};catalog=w.dump_verified(g.wrapped('OTDestInfoList',[]),version);paths={}
    def hashes():return {**{k:cd.sha(v)for k,v in documents.items()},'$dest_catalog':cd.sha(catalog)}
    for path in spec['paths']:
        need(set(path)=={'name','routes'},'Exact Path name/routes required')
        need(type(path['routes'])is list and all(x in routes for x in path['routes']),'Unknown selected Route name')
        documents,r=ops.create_path(documents,catalog,document_paths=docpaths,expected_hashes=hashes(),complete_document_set=True,name=path['name'],routes=[routes[x]for x in path['routes']]);paths[path['name']]=r['created'];stage.append(r)
    for item in spec['itineraries']:
        need(set(item)=={'name','paths'},'Exact Itinerary name/paths required')
        need(type(item['paths'])is list and all(x in paths for x in item['paths']),'Unknown selected Path name')
        out,r=ops.create_itinerary(documents,catalog,document_paths=docpaths,expected_hashes=hashes(),complete_document_set=True,name=item['name'],paths=[paths[x]for x in item['paths']]);documents=out['documents'];catalog=out['catalog'];stage.append(r)
    project=cd.Project(documents,document_paths=docpaths,expected_hashes={k:cd.sha(v)for k,v in documents.items()},complete_document_set=True);project.check_dest_catalog(catalog)
    stations=cats.station_items(w.load(station_blob)[0]);station_models=[m for m in project.models[name]if w.kind(m)=='OTStationModel'];need(set(stations)=={pf.string(m.contents[7].value)for m in station_models},'Station catalog/model closure mismatch')
    ta.read_document(documents[name],area_specs)
    itinerary_nodes={pf.string(o.contents[1].value):[list(k)for k in project.dest_view(o)[0]]for o in project.dests}
    members={'OTDocuments/'+name+'.opentrack':documents[name],'OTData/infrastructure.stations':station_blob,'OTData/infrastructure.dest':catalog}
    return members,{'document_paths':docpaths,'vertex_end_ids':ids,'edge_ids':top['edge_ids'],'route_references':routes,'path_references':paths,'itinerary_end_keys':itinerary_nodes,'area_specs':area_specs,'counts':{'documents':1,'signals':len(spec['signals']),'routes':len(routes),'paths':len(paths),'itineraries':len(spec['itineraries']),'stations':len(stations),'stop_areas':sum(x['stop']is not None for x in area_specs)},'output_sha256':{k:cd.sha(v)for k,v in members.items()},'stage_receipts':stage,'fresh_archive_reload_verified':True,'operating_ready':False,'native_application_executed':False,'scope':'Explicit single-document forward single-Edge final-stop area configuration, not actual stopping observation'}

from .zero_operations import vehicle_catalogs as vc,run_bundle as rb,speed_preferences as sp
from .operating_chain_workflow import SOURCE_KEYS

def compose_final_stop_chain(sources,*,expected_hashes,infrastructure,vehicles,course_template_id,timetable_template_key,train_types,speed_type,plan,run_configuration):
    from .final_stop_services import generate_final_stop_services
    need(type(sources)is dict and set(sources)==SOURCE_KEYS and all(type(b)is bytes for b in sources.values()),'Six immutable donor roles required')
    need(expected_hashes=={k:cd.sha(v)for k,v in sources.items()},'Complete donor SHA mismatch')
    cfg=dict(run_configuration);run_name=cfg.pop('run_filename');rb.relative(run_name)
    need('/'not in run_name and run_name.endswith('.run'),'Simple run filename required')
    need(set(cfg)=={'execution_root','path_style','output_directory','start_day','start_time','stop_day','stop_time','step'},'Exact run configuration required')
    need(cfg['path_style']=='windows','Only explicit Windows domain supported')
    rb.relative(cfg['output_directory']);a=run_name.casefold();b=cfg['output_directory'].casefold();need(a!=b and not a.startswith(b+'/') and not b.startswith(a+'/'),'Output directory overlaps final run member')
    root=rb.root_path(cfg['execution_root'],'windows');doc_member='OTDocuments/'+infrastructure['document_name']+'.opentrack'
    need(infrastructure['document_path']==root+'/'+doc_member,'Infrastructure document_path must match exact run execution-root/member')
    preference,_=sp.replace_train_types(b'',train_types);sp.index_for_course(preference,speed_type)
    files,ir=compose_final_stop_infrastructure(sources['header'],sources['shapes'],expected_hashes={k:expected_hashes[k]for k in('header','shapes')},spec=infrastructure)
    vehicle,vr=vc.generate_vehicle_catalogs(sources['depot_template'],sources['trains_template'],vehicles)
    service_inputs={'courses_template':sources['courses_template'],'timetable_template':sources['timetable_template'],'document':files[doc_member],'dest':files['OTData/infrastructure.dest'],'stations':files['OTData/infrastructure.stations'],'trains':vehicle['trains'],'depot':vehicle['depot'],'run_template':preference}
    services,sr=generate_final_stop_services(service_inputs,area_specs=ir['area_specs'],course_template_id=course_template_id,timetable_template_key=timetable_template_key,document_name=infrastructure['document_name'],plan=plan,speed_type=speed_type)
    members=dict(files);members.update({'OTData/infrastructure.'+role:blob for role,blob in {**vehicle,**services}.items()});catalogs={role:'OTData/infrastructure.'+role for role in rb.CATALOG_KEYS}
    need(set(members)=={doc_member,*catalogs.values()},'Exactly seven data members required')
    run,rr=rb.build_run(members,catalog_paths=catalogs,document_paths=[doc_member],train_types=train_types,**cfg)
    checked=rb.verify_archive_bindings(run,members,catalog_paths=catalogs,document_paths=[doc_member]);rb.verify_manifest(run,members,rr)
    ta.read_document(members[doc_member],ir['area_specs']);project=cd.Project({infrastructure['document_name']:members[doc_member]},document_paths={infrastructure['document_name']:infrastructure['document_path']},expected_hashes={infrastructure['document_name']:cd.sha(members[doc_member])},complete_document_set=True);project.check_dest_catalog(members[catalogs['dest']])
    members[run_name]=run
    return members,{'schema':'single-document-final-stop-chain/1','counts':{'members':len(members),'documents':1,'catalogs':6,'courses':len(plan),'timetable_rows':sum(len(p['visits'])for p in plan),'final_stops':len(plan)},'infrastructure':ir,'vehicles':vr,'services':sr,'run':rr,'cross_file_bindings':checked,'source_sha256':expected_hashes,'output_sha256':{k:cd.sha(v)for k,v in members.items()},'saved':False,'fresh_archive_reload_verified':True,'native_runtime_ready':False,'actual_stops_observed':False,'native_application_executed':False,'scope':'Explicit static final-only stopping configuration, no dwell/turnround/connections, not actual simulated stopping'}
