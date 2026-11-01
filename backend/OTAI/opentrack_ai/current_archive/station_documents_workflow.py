"""Finite one-station-per-document final-stop project, immutable bytes only.

Reuses the audited chain connector/continuation, Path/Itinerary, stock and record
factories. No native process, filesystem publication or runtime cache is created.
"""
import copy
import math
from . import writer as w, catalogs as c, course_factories as cf
from .multi_document import core as cd, operations as ops
from .multistation_timetable import topology as nt
from .zero_operations import vehicle_catalogs as vc, run_bundle as rb
from .zero_terminal.area_operations import arr_like, dictionary_like
from .stock_operations import CATEGORY_LAYOUT
from .graphic_alignment import validate_generated_signal_alignment

SOURCE_KEYS={'header','shapes','depot_template','trains_template','courses_template','timetable_template'}
SPEC_KEYS={'schema','execution_root','document_paths','run_filename','output_directory',
           'stations','half_link_length_m','vehicles','course_template_id',
           'timetable_template_key','train_types','speed_type','plan','simulation',
           'path_name','itinerary_name'}
CATALOGS={role:'OTData/chain.'+role for role in rb.CATALOG_KEYS}


def need(ok,message):
    if not ok:raise ValueError(message)


def configuration(spec):
    """Validate the explicit finite domain before any donor read or publication."""
    need(type(spec)is dict and set(spec)==SPEC_KEYS,'Exact station-document specification required')
    need(spec['schema']=='station-documents-final-stop/1','Unknown station-document schema')
    network={'topology':'chain','stations':spec['stations'],
             'half_link_length_m':spec['half_link_length_m'],'execution_root':spec['execution_root']}
    nt._spec(network)
    names=[x['id']for x in spec['stations']]
    paths={name:spec['execution_root']+'/OTDocuments/'+name+'.opentrack'for name in names}
    need(type(spec['document_paths'])is dict and spec['document_paths']==paths,
         'Every document path must match its explicit execution root and station basename')
    run=rb.relative(spec['run_filename']);out=rb.relative(spec['output_directory'])
    need('/'not in run and run.endswith('.run'),'A simple native .run filename required')
    members=[*CATALOGS.values(),*('OTDocuments/'+n+'.opentrack'for n in names),run]
    folded=[x.casefold()for x in members]
    need(len(set(folded))==len(folded),'Case-insensitive candidate member collision')
    need(all(out.casefold()!=x and not out.casefold().startswith(x+'/') and not x.startswith(out.casefold()+'/')for x in folded),
         'Output directory overlaps a project member')
    sim=spec['simulation']
    need(type(sim)is dict and set(sim)=={'start_day','start_time','stop_day','stop_time','step'},'Exact simulation window required')
    need(type(sim['start_day'])is int and type(sim['stop_day'])is int and sim['start_day']==sim['stop_day']==0,
         'This one-journey profile is same-day only')
    need(type(spec['train_types'])is list and len(spec['train_types'])==1 and spec['train_types'][0]==spec['speed_type'],
         'One explicit Course speed type mapping to native Edge index0 required')
    for key in ('path_name','itinerary_name','speed_type','course_template_id'):
        cf.name(spec[key])
    need(type(spec['timetable_template_key'])is str and 1<=len(spec['timetable_template_key'])<=250 and all(32<=ord(x)<127 for x in spec['timetable_template_key']),'Explicit printable timetable template key required')
    plan=spec['plan'];need(type(plan)is list and len(plan)==1,'Exactly one forward journey required; no fleet or circulation inference')
    entry=plan[0]
    need(type(entry)is dict and set(entry)=={'course_id','train','itinerary','visits'},'Exact Course plan required')
    need(entry['itinerary']==spec['itinerary_name'],'Course must select the generated primary Itinerary')
    cf.name(entry['course_id']);cf.name(entry['train'])
    visits=entry['visits'];need(type(visits)is list and len(visits)==len(names),'One visit per ordered station required')
    prior=-1
    for i,(visit,name)in enumerate(zip(visits,names)):
        need(type(visit)is dict and set(visit)=={'station_sign','absolute_seconds','stop'},'Exact final-stop visit required')
        need(visit['station_sign']==name,'Forward station order differs from document chain')
        need(type(visit['stop'])is bool and visit['stop']==(i==len(names)-1),'Only the final visit stops')
        sec=visit['absolute_seconds'];need(type(sec)is int and prior<sec<86400,'Strictly increasing same-day integer times required');prior=sec
    need(type(spec['vehicles'])is dict and spec['vehicles'].get('train_names')==[entry['train']],
         'Exactly the selected single Train definition required')
    
    
    for key in ('engine_name','category_name'):
        cf.name(spec['vehicles'].get(key))
    return {'execution_root':spec['execution_root'],'document_paths':paths,
            'run_filename':run,'output_directory':out}


def _project(files,spec):
    names=list(configuration(spec)['document_paths'])
    docs={dn:files['OTDocuments/'+dn+'.opentrack']for dn in names}
    p=cd.Project(docs,document_paths=spec['document_paths'],
                 expected_hashes={dn:cd.sha(b)for dn,b in docs.items()},complete_document_set=True)
    p.check_dest_catalog(files[CATALOGS['dest']])
    return p


def _trace(p,spec,maximum_speed):
    dests=[d for d in p.dests if c.text(d.contents[1].value)==spec['itinerary_name']]
    need(len(dests)==1 and len(p.dests)==1,'Exactly the requested primary Itinerary required')
    nodes,_=p.dest_view(dests[0]);visits=[];edges=[];distance=lower=0.
    for i,key in enumerate(nodes):
        model=p.model(key)
        if i:
            ek=p.edge_between(nodes[i-1],key);edge=p.model(ek)
            half=p.model(p.actual_related(nodes[i-1]));metres=edge.contents[9].values[1]
            speeds=cf.dictionary(edge.contents[16].value);need('0'in speeds,'Native Edge speed index0 absent')
            sp=speeds['0'];c.shape(sp,'OTSpeed',0,['@','i','i','i'])
            speed=sp.contents[1 if edge.contents[7].value is half else 2].value
            need(type(speed)is int and 0<speed<=1000,'Positive bounded direction-specific speed required')
            distance+=metres;lower+=metres/(min(speed,maximum_speed)/3.6)
            edges.append({'document':ek[0],'edge_id':ek[1],'length_m':metres})
        if model.contents[20].value==2:
            station=model.contents[12].value;need(station is not None,'Reference StationVertex is unbound')
            visits.append({'station_sign':c.text(station.contents[7].value),'document':key[0],
                           'end_id':key[1],'previous_end_key':None if i==0 else list(nodes[i-1]),
                           'distance_m':distance,'minimum_edge_time_s':lower})
    names=[x['id']for x in spec['stations']]
    need([x['station_sign']for x in visits]==names,'Primary Itinerary station sequence differs')
    need(visits[0]['document']==nodes[0][0] and visits[0]['end_id']==nodes[0][1] and
         visits[-1]['document']==nodes[-1][0] and visits[-1]['end_id']==nodes[-1][1],
         'Primary Itinerary must start/end at its reference StationVertices')
    leg=2*(spec['half_link_length_m']+500)
    need([x['distance_m']for x in visits]==[i*leg for i in range(len(names))],
         'Actual split-chain station distances differ from declared geometry')
    return {'visits':visits,'nodes':[list(x)for x in nodes],'edges':edges,
            'distance_m':distance,'minimum_edge_time_s':lower,'adjacent_station_distance_m':leg}


def _vehicle(files,spec):
    depot,_=w.load_next_compatible(files[CATALOGS['depot']]);trains,_=w.load_next_compatible(files[CATALOGS['trains']])
    es=c.engine_items(depot);ts=c.train_items(trains);cats=c.array(trains.contents[1].value)
    need(len(es)==len(ts)==len(cats)==1,'Exactly one Engine, Train and Category required')
    engine,train,category=es[0],ts[0],cats[0];c.shape(category,'OTTrainCategory',19,CATEGORY_LAYOUT)
    need(not(category.contents[0].values[1]&0x20),'stopAtEveryStation conflicts with final-only stop')
    refs=c.array(train.contents[2].values[1]);need(len(refs)==1 and refs[0].contents[1].value==1 and not c.array(train.contents[2].values[2]),'Single powered unit at posInTrain1, no trailers required')
    need(c.bound_engine_names(train)==[c.text(engine.contents[1].value)] and c.text(train.contents[3].value)==c.text(category.contents[1].value),'Vehicle catalog reference closure differs')
    need(c.text(train.contents[0].value)==spec['plan'][0]['train'],'Selected Train identity differs')
    length=float(engine.contents[2].values[2]);speed=engine.contents[7].value
    need(math.isfinite(length)and 0<length<=500 and type(speed)is int and 0<speed<=1000,'Vehicle must fit actual 500m stop area and have bounded speed')
    return trains,length,speed


def _services(sources,files,spec,p):
    trains,length,speed=_vehicle(files,spec);trace=_trace(p,spec,speed)
    ct,cv=w.load_next_compatible(sources['courses_template']);tt,tv=w.load_next_compatible(sources['timetable_template'])
    templates={c.text(x.contents[0].value):x for x in c.course_items(ct)};rows=cf.timetable(tt)
    cid0=spec['course_template_id'];key0=spec['timetable_template_key']
    need(ct.contents[0].value==17 and cid0 in templates and key0 in rows,'Exact current Course/Timetable donor identities absent')
    need(not c.array(rows[key0].contents[9].value),'Connection-bearing Timetable donor unsupported')
    outc=cf.clone(ct)
    for i in(1,2,3):outc.contents[i].value=arr_like(ct.contents[i].value,[])
    outc.contents[4].value=arr_like(ct.contents[4].value,[copy.deepcopy(templates[cid0])])
    outt=dictionary_like(tt,[(key0,copy.deepcopy(rows[key0]))])
    entry=spec['plan'][0];cid=entry['course_id'];need(cid!=cid0,'New Course cannot reuse template identity')
    fields={'speed_type':spec['speed_type'],'description':'Explicit final-stop single journey',
            'comment':'Planned only; no native simulation','train_number':cid,'course_type':'',
            'acceleration_percent':100,'delayed_acceleration_percent':100,'enabled':True,
            'entering_speed_kmh':0,'output_offset_m':0,'spacing_mode':'discrete',
            'additional_reservation_time_s':0,'additional_release_time_s':0}
    dest=w.load_next_compatible(files[CATALOGS['dest']])[0]
    outc=cf.new_course(outc,trains,dest,template_id=cid0,course_id=cid,train=entry['train'],itineraries=[entry['itinerary']],fields=fields)
    stops=[]
    for i,(visit,actual)in enumerate(zip(entry['visits'],trace['visits'])):
        if i:
            previous=entry['visits'][i-1];prior=trace['visits'][i-1]
            need(visit['absolute_seconds']-previous['absolute_seconds']+1e-6>=actual['minimum_edge_time_s']-prior['minimum_edge_time_s'],
                 'Planned interval below directional Edge/Engine speed necessary bound')
        sec=visit['absolute_seconds'];clock=f'{sec//3600:02}:{sec//60%60:02}:{sec%60:02}'
        stops.append(dict(template_key=key0,station_sign=visit['station_sign'],arrival=clock,departure=clock,
                          arrival_day_offset=0,departure_day_offset=0,stop_at_station=visit['stop'],timing_station=True,
                          interval_reference_course_id=None,interval_offset_s=0,dwell_s=0,mean_delay_s=0,
                          track_id='',distribution_name='',delta_mass_t=0))
    outt=cf.new_timetable(outt,outc,w.load_next_compatible(files[CATALOGS['stations']])[0],course_id=cid,stops=stops)
    outc.contents[4].value=arr_like(outc.contents[4].value,[x for x in c.course_items(outc)if c.text(x.contents[0].value)!=cid0])
    outt=dictionary_like(outt,[(k,v)for k,v in cf.timetable(outt).items()if k!=key0])
    return {'courses':w.dump_verified(outc,cv),'timetable':w.dump_verified(outt,tv)},trace,length


def _validate_structure(files,spec):
    p=_project(files,spec);_,length,speed=_vehicle(files,spec);trace=_trace(p,spec,speed)
    stations=c.station_items(w.load_next_compatible(files[CATALOGS['stations']])[0])
    need(set(stations)==set(spec['document_paths']),'Station catalog exact document closure differs')
    for row in spec['stations']:
        dn=row['id'];models=p.models[dn];sms=[m for m in models if w.kind(m)=='OTStationModel']
        need(len(sms)==1 and c.text(sms[0].contents[7].value)==dn,'Exactly one correctly named StationModel per document required')
        for model in models:
            if w.kind(model)=='OTStationModel':
                need(all(type(model.contents[i].value)is int for i in(4,5))and
                     (model.contents[4].value,model.contents[5].value)==(0,0),
                     'Generated StationModel native default graphic alignment must be (0,0)')
            elif w.kind(model)=='OTSignalModel':
                validate_generated_signal_alignment(model)
        need(c.text(stations[dn].contents[2].value)==row['name'] and stations[dn].contents[7].value==1,'Station catalog name/timing mismatch')
        refs=[e for e in p.ends(dn)if e.contents[20].value==2]
        need(len(refs)==2 and p.related(p.key(refs[0]))==p.key(refs[1]) and all(e.contents[12].value is sms[0]for e in refs),'Exactly one shared reference vertex pair per station required')
        edges=[m for m in models if w.kind(m)=='OTEdgeModel']
        need(len(edges)==4 and sorted(e.contents[9].values[1]for e in edges)==sorted([spec['half_link_length_m'],500,500,spec['half_link_length_m']]),'Declared four-edge local topology length mismatch')
        for end in refs:
            need(w.kind(end.contents[11].value)=='OTSignalModel','Both directional reference signals required')
        
        
        visit=next(v for v in trace['visits']if v['station_sign']==dn)
        if visit['previous_end_key']is not None:
            before=tuple(visit['previous_end_key']);after=(dn,visit['end_id'])
            ee=p.model(before);xx=p.model(after);edge=p.model(p.edge_between(before,after))
            need(before[0]==dn and ee.contents[20].value==1 and ee.contents[12].value is xx.contents[12].value is sms[0]and edge.contents[9].values[1]==500,'Actual station arrival area differs from explicit 500m approach')
    report=p.report();need(len(report['connectors'])==2*(len(spec['stations'])-1),'Exactly reciprocal neighbor connector pairs required')
    entry=spec['plan'][0];courses={c.text(x.contents[0].value):x for x in c.course_items(w.load_next_compatible(files[CATALOGS['courses']])[0])}
    need(set(courses)=={entry['course_id']},'Exactly the selected Course required')
    course=courses[entry['course_id']]
    need(c.text(course.contents[3].value)==entry['train']and[c.text(x)for x in c.array(course.contents[2].value)]==[entry['itinerary']]and c.text(course.contents[4].value)==spec['speed_type'],'Saved Course identity references or speed mapping differ')
    rows=cf.timetable(w.load_next_compatible(files[CATALOGS['timetable']])[0])
    need(set(rows)=={entry['course_id']+'#'+str(i)for i in range(len(entry['visits']))},'Exact timetable key set differs')
    for i,visit in enumerate(entry['visits']):
        row=rows[entry['course_id']+'#'+str(i)];sec=visit['absolute_seconds'];clock=f'{sec//3600:02}:{sec//60%60:02}:{sec%60:02}'
        need(c.text(row.contents[1].value)==entry['course_id']and row.contents[3].value==i and row.contents[4].value==len(rows)-1 and c.text(row.contents[5].value)==visit['station_sign'],'Saved timetable identity/order/station differs')
        need(c.text(row.contents[6].value)==c.text(row.contents[7].value)==clock and row.contents[15].values==[0,0,0,0],'Planned times or actual offsets differ')
        need(c.text(row.contents[13].value)==c.text(row.contents[14].value)=='HH:MM:SS' and not c.array(row.contents[9].value),'Actual results or connections unexpectedly retained')
        need(row.contents[10].value==2+int(visit['stop'])and float(c.text(row.contents[8].value))==0,'Final-stop/timing flags or zero dwell differ')
    return {'trace':trace,'reconstruction':report,'train_length_m':length,'one_station_per_document':True,
            'connector_pairs':len(spec['stations'])-1,'station_count':len(stations),'course_count':1,
            'timetable_rows':len(rows),'final_only_stop':True,'graphic_alignment_defaults_verified':True,
            'signal_alignment_matches_owner_verified':True}


def initialize(sources,spec):
    config=configuration(spec);original=copy.deepcopy(spec)
    need(type(sources)is dict and set(sources)==SOURCE_KEYS and all(type(b)is bytes and b for b in sources.values()),'Six exact immutable donor roles required')
    hashes={k:cd.sha(b)for k,b in sources.items()}
    donors={'header':sources['header'],'shapes':sources['shapes'],**{k:sources[k+'_template']for k in('depot','trains','courses','timetable')}}
    files,top=nt.generate_network_project(donors,expected_hashes={k:cd.sha(b)for k,b in donors.items()},
            spec={'topology':'chain','stations':spec['stations'],'half_link_length_m':spec['half_link_length_m'],'execution_root':spec['execution_root']})
    p=_project(files,spec);names=list(config['document_paths']);selected=[]
    for a,b in zip(names,names[1:]):
        candidates=[r for r in p.routes if c.text(r.contents[1].value)=='R:'+a+'-'+b and p.owners[id(r)][0]==a]
        need(len(candidates)==1,'Unique adjacent forward source Route required')
        selected.append({'document':a,**cd.ref(candidates[0])})
    docs={dn:files['OTDocuments/'+dn+'.opentrack']for dn in names};dest=files[CATALOGS['dest']]
    docs,pr=ops.create_path(docs,dest,document_paths=config['document_paths'],expected_hashes={**{k:cd.sha(b)for k,b in docs.items()},'$dest_catalog':cd.sha(dest)},complete_document_set=True,name=spec['path_name'],routes=selected)
    payload,ir=ops.create_itinerary(docs,dest,document_paths=config['document_paths'],expected_hashes={**{k:cd.sha(b)for k,b in docs.items()},'$dest_catalog':cd.sha(dest)},complete_document_set=True,name=spec['itinerary_name'],paths=[pr['created']])
    
    
    for dn,blob in payload['documents'].items():
        root,version=w.load_next_compatible(blob);back=root.contents[5].value.contents[0].value
        w.set_elements(back,[d for d in c.array(back)if c.text(d.contents[1].value)==spec['itinerary_name']])
        files['OTDocuments/'+dn+'.opentrack']=w.dump_verified(root,version)
    cat,version=w.load_next_compatible(payload['catalog']);back=cat.contents[0].value
    w.set_elements(back,[d for d in c.array(back)if c.text(d.contents[1].value)==spec['itinerary_name']]);files[CATALOGS['dest']]=w.dump_verified(cat,version)
    vehicle,vr=vc.generate_vehicle_catalogs(sources['depot_template'],sources['trains_template'],spec['vehicles'])
    for role,blob in vehicle.items():files[CATALOGS[role]]=blob
    services,trace,length=_services(sources,files,spec,_project(files,spec))
    for role,blob in services.items():files[CATALOGS[role]]=blob
    files.pop('chain.run')
    run,rr=rb.build_run(files,catalog_paths=CATALOGS,document_paths=['OTDocuments/'+dn+'.opentrack'for dn in names],
                         execution_root=config['execution_root'],path_style='windows',output_directory=config['output_directory'],
                         train_types=spec['train_types'],template=b'',**spec['simulation'])
    files[config['run_filename']]=run
    detail=_validate_structure(files,spec)
    receipt={'schema':'station-documents-initialization/1','source_sha256':hashes,
             'specification_sha256':_spec_hash(spec),'members':_manifest(files),
             'configuration':config,'counts':{'documents':len(names),'stations':len(names),'members':len(files),'catalogs':6,'courses':1,'timetable_rows':len(names)},
             'topology':top,'primary_path':pr,'primary_itinerary':ir,'vehicles':vr,'run':rr,
             'validation':detail,'fresh_archive_reload_verified':True,'one_station_per_document':True,'from_empty_graph':True,
             'layout_change':{'mode':'explicit regenerated station-document chain, not bytewise archive splitting',
                  'between_reference_vertices_m':[trace['adjacent_station_distance_m']]*(len(names)-1),
                  'journey_distance_m':trace['distance_m'],'ordinary_arrival_area_m':500,
                  'terminal_follow_on_track_m':500+spec['half_link_length_m'],
                  'origin_and_middle_stop_flags':False,'station_reference_count_per_document':1,
                  'segment_layout':'each station: half-link / 500m left area / reference / 500m right area / half-link',
                  'new_geometry_requires_native_acceptance':True},
             'provenance':{'connector_reconstruction':'multi_document/core.py Project.block_end/actual_related/route_view; exact OTConnModel1 + OTEndModel7 saved contract',
                 'continuation_and_local_ids':'multistation_timetable/topology.py generate_network_project; existing current-format native shape synthesis',
                 'new_path_itinerary':'multi_document/operations.py; strict native saved-reference composition with rollback proof',
                 'service_factories':'course_factories.py new_course/new_timetable; original current Course/Timetable layouts',
                 'source_evidence':'existing artifacts/rebuild/multidocument-interface-notes.md and packaged function metadata; finite static reconstruction, native run separately required'},
             'saved':False,'publication_review_pending':True,'native_application_executed':False,
             'native_runtime_ready':False,'physical_calibration_verified':False,
             'scope':'2..12 linear one-station-per-document chain; one forward same-day powered-unit journey, final-only stop; no branch, dwell, turnround or fleet proof'}
    validate(files,spec,receipt)
    need(spec==original and hashes=={k:cd.sha(b)for k,b in sources.items()},'Caller specification or source bytes changed')
    return files,receipt


def _spec_hash(spec):
    import json
    return cd.sha(json.dumps(spec,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))


def _manifest(files):
    return {name:{'sha256':cd.sha(blob),'bytes':len(blob)}for name,blob in files.items()}


def validate(members,spec,receipt):
    """Independently decode actual supplied members and prove saved bindings."""
    config=configuration(spec);names=list(config['document_paths']);run_name=config['run_filename']
    expected={*CATALOGS.values(),*('OTDocuments/'+dn+'.opentrack'for dn in names),run_name}
    need(type(members)is dict and set(members)==expected and all(type(b)is bytes and b for b in members.values()),'Exact immutable N+7 member set required')
    need(type(receipt)is dict and receipt.get('schema')=='station-documents-initialization/1'and receipt.get('saved')is False,'Unsaved typed candidate receipt required')
    need(receipt.get('native_application_executed')is False and receipt.get('native_runtime_ready')is False,'Native execution claims are outside candidate validation')
    need(receipt.get('specification_sha256')==_spec_hash(spec) and receipt.get('configuration')==config,'Candidate receipt specification binding mismatch')
    need(receipt.get('members')==_manifest(members),'Actual member byte hashes differ from candidate receipt')
    need(receipt.get('counts')=={'documents':len(names),'stations':len(names),'members':len(names)+7,'catalogs':6,'courses':1,'timetable_rows':len(names)},'Candidate receipt counts mismatch')
    archives={name:blob for name,blob in members.items()if name!=run_name};docs=['OTDocuments/'+dn+'.opentrack'for dn in names]
    fresh=rb.verify_run(members[run_name],archives,catalog_paths=CATALOGS,document_paths=docs,
                       execution_root=config['execution_root'],path_style='windows',output_directory=config['output_directory'],
                       train_types=spec['train_types'],**spec['simulation'])
    bindings=rb.verify_archive_bindings(members[run_name],archives,catalog_paths=CATALOGS,document_paths=docs)
    rb.verify_manifest(members[run_name],archives,receipt['run'])
    structure=_validate_structure(members,spec)
    need(structure==receipt.get('validation'),'Fresh actual cross-document structure differs from candidate')
    return {'all_members_reloaded':True,'total_member_count':len(members),'archive_member_count':len(archives),
            'run_member':run_name,'one_station_per_document':True,'bindings':bindings,
            'structure':structure,'run_window':fresh['window'],'saved':False,'native_runtime_verified':False}
