"""Build a native linear chain with direction-specific arrival areas."""

import math
import re
from opentrack_ai.current_archive.multi_document import core as cd, generate as g, operations as ops
from opentrack_ai.current_archive import writer as w, catalogs as cats, path_functions as pf, route_factory as rf
from opentrack_ai.current_archive.reference_platform_geometry import add_platform_rectangle
from opentrack_ai.current_archive.zero_generation import topology as tp, native_signal_routes as ns
from opentrack_ai.current_archive.zero_operations import station_binding as sb, run_bundle as rb


DEFAULT_ARRIVAL_LENGTH_M = 500
ARRIVAL_AREAS = (('forward', 0, 'left_entry', 'left_area'), ('reverse', 1, 'right_entry', 'right_area'))


def need(ok, message):
    if not ok: raise ValueError(message)


def _spec(s):
    fields = {'topology','stations','half_link_length_m','execution_root'}
    need(type(s) is dict and fields <= s.keys() <= fields | {'platform'},'Exact chain spec required')
    need(s['topology']=='chain','Only a linear chain is supported; grids, cycles and branch junctions are not implemented')
    need(type(s['stations']) is list and 2<=len(s['stations'])<=12,'2..12 ordered stations required')
    seen=set()
    for row in s['stations']:
        need(type(row) is dict and set(row)=={'id','name'},'Exact station id/name required')
        k=row['id'];need(type(k)is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,23}',k) is not None,'Safe station/document id required')
        need(k.casefold() not in seen,'Unique case-insensitive station ids required');seen.add(k.casefold())
        need(type(row['name'])is str and 1<=len(row['name'])<=100 and all(32<=ord(c)<127 for c in row['name']) and '#' not in row['name'],'Nonempty printable ASCII station name required')
    need(type(s['half_link_length_m'])is int and 1<=s['half_link_length_m']<=100000,'Integer 1..100000 metre half link required')
    need(rb.root_path(s['execution_root'],'windows')==s['execution_root'],'Canonical forward-slash Windows root required')
    if 'platform' in s:
        _validate_platform(s['platform'], {row['id'] for row in s['stations']})


def _validate_platform(platform, station_ids):
    fields = {'station_id', 'platform_id', 'track_name', 'direction', 'length_m'}
    need(type(platform) is dict and fields <= platform.keys() <= fields | {'drawing_side', 'width_m'},
         'Use one exact platform declaration with station, platform, track, direction and physical length')
    need(type(platform['station_id']) is str and platform['station_id'] in station_ids,
         'Platform station_id must match an existing station in the chain')
    for field in ('platform_id', 'track_name'):
        value = platform[field]
        need(type(value) is str and 1 <= len(value) <= 80 and value == value.strip()
             and all(32 <= ord(char) < 127 and char != '#' for char in value),
             f'Platform {field} requires printable ASCII without #')
    need(platform['direction'] in ('forward', 'reverse'), 'Platform direction must be forward or reverse')
    need(type(platform['length_m']) is int and 1 <= platform['length_m'] <= 100000,
         'Platform length_m must be a positive integer within the native Edge profile')
    if 'drawing_side' in platform:
        need(platform['drawing_side'] in ('above', 'below'), 'Drawing side must be above or below')
    if 'width_m' in platform:
        value = platform['width_m']
        need('drawing_side' in platform and type(value) in (int, float) and math.isfinite(value) and value > 0,
             'Platform drawing width requires a side and a finite positive width_m')


def _topology(length, platform=None):
    vs=[g.vertex(k,30+i*100)for i,k in enumerate(('left','left_entry','reference','right_entry','right'))]
    es=[]
    for name,a,b in [('left','left','left_entry'),('left_area','left_entry','reference'),('right_area','reference','right_entry'),('right','right_entry','right')]:
        edge_length = DEFAULT_ARRIVAL_LENGTH_M if name.endswith('_area') else length
        edge = dict(key=name, **{'from':[a,1], 'to':[b,0]}, length_m=edge_length,
                    radius_m=0., gradient_per_mille=0., track_type=1, loop_type=1, dlink_type=1,
                    equal_speed=True, rack_rail=False,
                    speeds=[dict(train_type='0', speed12_kmh=80, speed21_kmh=80)],
                    remark='', track_name='1', line_name='chain')
        if platform is not None and name == ('left_area' if platform['direction'] == 'forward' else 'right_area'):
            edge.update(length_m=platform['length_m'], remark='Platform '+platform['platform_id'],
                        track_name=platform['track_name'])
        es.append(edge)
    return {'vertices':vs,'edges':es}


def generate_network_project(sources, *, expected_hashes, spec):
    """Six immutable shape donors -> N+7 native project members and receipt.

    sources: header, shapes, depot, trains, courses, timetable.
    The four service catalogs are intentionally empty in the new network.
    A station id is the native document basename and station sign.
    """
    need(type(sources)is dict and set(sources)=={'header','shapes','depot','trains','courses','timetable'},'Exact six shape donor sources required')
    need(all(type(b)is bytes and b for b in sources.values()),'Nonempty immutable bytes required')
    need(type(expected_hashes)is dict and expected_hashes=={k:cd.sha(v)for k,v in sources.items()},'Exact source SHA256 binding required')
    _spec(spec)
    platform = spec.get('platform')
    names=[r['id']for r in spec['stations']];root_path=spec['execution_root'];length=spec['half_link_length_m']
    docs={};roots={};versions={};ids={};models={};station_rows=[];base_reports={};stops={}
    paths={dn:root_path+'/OTDocuments/'+dn+'.opentrack'for dn in names}
    for row in spec['stations']:
        dn = row['id']
        station_platform = platform if platform is not None and dn == platform['station_id'] else None
        blob,base=tp.generate_network(sources['header'],sources['shapes'],_topology(length, station_platform));ids[dn]=base['vertex_end_ids'];base_reports[dn]=base
        for eid in ids[dn]['reference']:
            rr,_=w.load(blob);mm,byid=rf.document(rr)
            signal_x = float(byid[eid].contents[2].value) if station_platform else 130
            blob,_=ns.build_main_signal(blob,end_id=eid,name='S:'+dn+':'+str(eid),model_id=max(m.contents[0].value for m in mm)+1,placement=g.signal_placement(byid[eid],signal_x,20),sight_m=500,delay_s=0.,show_symbol=True,show_icon=True)
        station_x = 130
        if station_platform is not None:
            entry = 'left_entry' if station_platform['direction'] == 'forward' else 'right_entry'
            station_x = (float(byid[ids[dn][entry][0]].contents[2].value) + signal_x) / 2
        blob,station,_=sb.bind_stations(blob,[dict(sign=dn,name=row['name'],end_ids=[ids[dn]['reference'][0]],placement=g.placement(station_x,50),station_type_raw=2,interlock_type_raw=4,icon_show_type_raw=1,timing_point=True)])
        station_rows.append((dn,cats.station_items(w.load(station)[0])[dn]));roots[dn],versions[dn]=w.load(blob);_,models[dn]=rf.document(roots[dn])
        sm=models[dn][ids[dn]['reference'][0]].contents[12].value
        for vertex in ('left_entry','right_entry'):
            for eid in ids[dn][vertex]:
                e=models[dn][eid];need(e.contents[20].value==1 and e.contents[12].value is None,'Fresh ordinary area member required')
                e.contents[12].value=sm
        stops[dn]={}
        for direction,side,entry,edge in ARRIVAL_AREAS:
            area={'document':dn,'entry_end_id':ids[dn][entry][side],'exit_end_id':ids[dn]['reference'][side],
                  'departure_end_id':ids[dn]['reference'][1-side],'area_edge_id':base['edge_ids'][edge],
                  'length_m':DEFAULT_ARRIVAL_LENGTH_M}
            if station_platform is not None and direction == station_platform['direction']:
                area.update({key: station_platform[key] for key in ('platform_id','track_name','length_m')})
            stops[dn][direction] = area

    for ix,dn in enumerate(names):
        for neighbor,vertex,side,target_vertex,target_side in [(ix-1,'left',0,'right',1),(ix+1,'right',1,'left',0)]:
            if not 0<=neighbor<len(names):continue
            target=names[neighbor];e=models[dn][ids[dn][vertex][side]]
            need(w.kind(e)=='OTEndModel' and all(e.contents[i].value is None for i in (9,10,11,12)),'Connector must be an unused, nonstation outward half')
            e.clazz=w.Class(b'OTConnModel',1,e.clazz);e.contents +=[w.TypedValue(b'@',ns.string('')),w.TypedValue(b'@',ns.string(target)),w.TypedValue(b'i',ids[target][target_vertex][target_side]),w.TypedValue(b'i',0)]
    dest_rows=[];route_refs={};path_refs={}
    for ix in range(len(names)-1):
        for source,target,side,boundary,remote_boundary in [(names[ix],names[ix+1],0,'right','left'),(names[ix+1],names[ix],1,'left','right')]:
            start=ids[source]['reference'][side];owner=models[source][start];local_end=ids[source][boundary][side];remote_end=ids[target]['reference'][side];host=ids[target][remote_boundary][side]
            r=g.route('R:'+source+'-'+target,0,start,[owner,models[source][ids[source][boundary+'_entry'][side]],models[source][local_end]],3)
            fragment=g.route('R:'+source+'-'+target,0,start,[models[target][ids[target][remote_boundary+'_entry'][side]],models[target][remote_end]],-1,True)
            need(not pf.mutable_array(owner.contents[15].value.contents[0].value),'Duplicate source route owner')
            w.set_elements(owner.contents[15].value.contents[0].value,[r]);w.set_elements(models[target][host].contents[15].value.contents[0].value,[fragment])
            p=ns.obj(pf.SHAPES['OTPath'][0],[('@',[ns.arr([r])]),('@',[ns.string('P:'+source+'-'+target)]),('ii',[1,start]),('@',[ns.string('')]),('@',[ns.arr([g.inf(r)])])])
            w.set_elements(owner.contents[17].value.contents[0].value,[p]);owner.contents[19].value=1
            d=ns.obj(pf.SHAPES['OTDest'][0],[('@',[ns.arr([p])]),('@',[ns.string('I:'+source+'-'+target)]),('ii',[-1,-1]),('@',[ns.string('')]),('@',[ns.arr([g.inf(p,source)])]),('@',[g.wrapped('OTSafetyMarginArray',[])])])
            back=roots[source].contents[5].value.contents[0].value;w.set_elements(back,pf.mutable_array(back)+[d])
            dest_rows.append(ns.obj([('OTDestInfo',1),('NSObject',0)],[('i',[17]),('@',[ns.string('I:'+source+'-'+target)]),('@',[ns.string(paths[source])]),('i',[start]),('@',[ns.arr([g.inf(p,source)])])]))
            route_refs[(source,target)]={'document':source,**cd.ref(r)};path_refs[(source,target)]={'document':source,**cd.ref(p)}
    docs={dn:w.dump_verified(roots[dn],versions[dn])for dn in names};dest=w.dump_verified(g.wrapped('OTDestInfoList',dest_rows),versions[names[0]])
    # Full-chain movement is composed from adjacent Routes, never a fabricated
    # Route that skips several native document continuation boundaries.
    for order,label in [(names,'forward'),(list(reversed(names)),'reverse')]:
        route_seq=[route_refs[(a,b)]for a,b in zip(order,order[1:])]
        docs,pr=ops.create_path(docs,dest,document_paths=paths,expected_hashes={**{k:cd.sha(v)for k,v in docs.items()},'$dest_catalog':cd.sha(dest)},complete_document_set=True,name='P:chain:'+label,routes=route_seq)
        payload,ir=ops.create_itinerary(docs,dest,document_paths=paths,expected_hashes={**{k:cd.sha(v)for k,v in docs.items()},'$dest_catalog':cd.sha(dest)},complete_document_set=True,name='I:chain:'+label,paths=[pr['created']])
        docs=payload['documents'];dest=payload['catalog']
    platform_report = None
    if platform is not None:
        dn = platform['station_id']
        area = stops[dn][platform['direction']]
        platform_report = {**area, 'station_id': dn, 'direction': platform['direction']}
        if 'drawing_side' in platform:
            docs[dn], platform_report['graphics'] = add_platform_rectangle(
                docs[dn], area, platform['drawing_side'], platform.get('width_m'))
    project=cd.Project(docs,document_paths=paths,expected_hashes={k:cd.sha(v)for k,v in docs.items()},complete_document_set=True);project.check_dest_catalog(dest)
    # Independent structural checks on both directional areas, including origin
    # stations that have no incoming leg in a particular Itinerary.
    for dn,areas in stops.items():
        for area in areas.values():
            entry=(dn,area['entry_end_id']);exit=(dn,area['exit_end_id'])
            need(project.edge_between(entry,exit)==(dn,area['area_edge_id']),'Wrong area Edge identity')
            edge=project.model((dn,area['area_edge_id']));need(edge.contents[9].values[1]==area['length_m'],'Area actual length differs')
            if 'platform_id' in area:
                need(w.string(edge.contents[19].value)==area['track_name'],'Native platform track name differs')
                need(w.string(edge.contents[12].value)=='Platform '+area['platform_id'],'Native platform identifier differs')
            ee=project.model(entry);xx=project.model(exit)
            need(ee.contents[20].value==1 and xx.contents[20].value==2,'Ordinary area entry and StationVertex exit required')
            need(ee.contents[12].value is xx.contents[12].value and xx.contents[12].value is not None,'Area StationModel ownership mismatch')
            for key in (entry,exit):
                e=project.model(key);other=project.model(project.related(key))
                need(e.contents[12].value is other.contents[12].value and e.contents[20].value==other.contents[20].value,'Asymmetric station pair')
            need(project.related(exit)==(dn,area['departure_end_id']),'Opposite departure reference mismatch')
            signal = xx.contents[11].value
            need(w.kind(signal)=='OTSignalModel' and signal.contents[7].value is xx
                 and signal.contents[8].values[:2]==[1,4],'Reference must carry direction-facing main exit signal')
    traces={}
    for d in project.dests:
        name=pf.string(d.contents[1].value);nodes,_=project.dest_view(d);dist=0;station_trace=[];visits=[]
        for i,key in enumerate(nodes):
            if i: dist+=project.model(project.edge_between(nodes[i-1],key)).contents[9].values[1]
            e=project.model(key)
            if e.contents[20].value==2:
                sign=cats.text(e.contents[12].value.contents[7].value);station_trace.append(sign)
                visits.append({'station_sign':sign,'end_key':list(key),'previous_end_key':list(nodes[i-1])if i else None,'distance_m':dist})
                if i:
                    matching=[v for v in stops[sign].values()if v['exit_end_id']==key[1]]
                    need(len(matching)==1,'Unique directional stopping area required');ss=matching[0]
                    need(nodes[i-1]==(key[0],ss['entry_end_id']) and project.edge_between(nodes[i-1],key)==(key[0],ss['area_edge_id']),'Actual approach must use the declared directional station area')
                    a=project.model(nodes[i-1]);need(a.contents[20].value==1 and a.contents[12].value is e.contents[12].value,'Area ownership/type mismatch')
        traces[name]={'station_order':station_trace,'visits':visits,'distance_m':dist,'nodes':[list(k)for k in nodes]}
    need(traces['I:chain:forward']['station_order']==names and traces['I:chain:reverse']['station_order']==list(reversed(names)),'Full-chain station order differs')
    expected_distance = sum(2*length + stops[left]['reverse']['length_m'] + stops[right]['forward']['length_m']
                            for left,right in zip(names,names[1:]))
    need(all(traces['I:chain:'+x]['distance_m']==expected_distance for x in ('forward','reverse')),'Full-chain physical Edge distance differs')
    files={'OTDocuments/'+k+'.opentrack':v for k,v in docs.items()};catalog_paths={r:'OTData/chain.'+r for r in rb.CATALOG_KEYS}
    for role,path in catalog_paths.items():files[path]=dest if role=='dest'else w.dump_verified(sb.dictionary(station_rows),1000)if role=='stations'else g.empty_catalog(sources[role],role)
    doc_members=['OTDocuments/'+dn+'.opentrack'for dn in names]
    run,run_receipt=rb.build_run(files,catalog_paths=catalog_paths,document_paths=doc_members,execution_root=root_path,path_style='windows',train_types=['instructional'],template=b'')
    rb.verify_run(run,files,catalog_paths=catalog_paths,document_paths=doc_members,execution_root=root_path,path_style='windows',train_types=['instructional']);files['chain.run']=run
    report={'operation':'generate_linear_multidocument_network','topology':'chain','domain':'line_chain_not_grid','station_count':len(names),'one_station_per_document':True,'sources_sha256':dict(expected_hashes),'members':{k:{'sha256':cd.sha(v),'bytes':len(v)}for k,v in files.items()},'document_paths':paths,'stops':stops,'itineraries':traces,'reconstruction':project.report(),'run':run_receipt,'service_catalogs_empty':True,'station_stopping_regions_supported':True,'station_area_length_m':DEFAULT_ARRIVAL_LENGTH_M if platform is None else None,'station_area_runtime_verified':False,'grid_supported':False,'junctions_supported':False,'native_runtime_ready':False,'native_simulation_executed':False,'scope':'2..12 stations with two directional arrival areas each, static geometry and no-service references; no native stop validation'}
    if platform_report is not None:
        report['platform']=platform_report
    return files,report


def generate_network(header_document, shapes, templates, spec):
    """Convenience composition API; caller binds external source project hashes.

    templates must be the explicit four catalog byte donors. The lower-level
    generate_network_project API additionally accepts an exact SHA map.
    """
    need(type(templates)is dict and set(templates)=={'depot','trains','courses','timetable'},'Exact four catalog donors required')
    sources={'header':header_document,'shapes':shapes,**templates}
    need(all(type(v)is bytes and v for v in sources.values()),'Immutable nonempty bytes required')
    return generate_network_project(sources,expected_hashes={k:cd.sha(v)for k,v in sources.items()},spec=spec)
