"""Fresh native-byte checks for the nine-station project; no simulated acceptance."""
import collections
import grid_geometry as gg
from grid_geometry import w,pf,rf,cd,cats,sha,STATIONS,PORTS,SIDE,OPPOSITE,name
from opentrack_ai.current_archive import course_factories as cf
from opentrack_ai.current_archive.zero_operations import run_bundle as rb
from opentrack_ai.current_archive.prepare_contract import auxiliary as aux


def intersects_platform_bay(a,b):
    low,high=0.,1.
    for start,finish,left,right in ((a.contents[2].value,b.contents[2].value,420.,980.),
                                   (a.contents[3].value,b.contents[3].value,660.,1200.)):
        delta=finish-start
        if abs(delta)<1e-9:
            if not left<start<right:return False
        else:
            x,y=sorted(((left-start)/delta,(right-start)/delta))
            low,high=max(low,x),min(high,y)
            if low>=high-1e-9:return False
    return max(low,0.)<min(high,1.)-1e-9


def validate(files,plans,proofs,cached_traces):
    from build_project import TARGET,CATALOGS,DOC_PATHS
    legs={plan.get('leg_distance_m',5000) for plan in plans}
    assert len(legs)==1 and next(iter(legs)) in (5000,6000)
    leg=next(iter(legs));outside=leg==6000
    unified=all(plan.get('unified_platform_bay',False) for plan in plans)
    planned_intervals={b['seconds']-a['seconds'] for plan in plans for a,b in zip(plan['visits'],plan['visits'][1:])}
    assert planned_intervals==({420} if outside else {300})
    expected={'OTDocuments/'+n+'.opentrack' for n in STATIONS}|set(CATALOGS.values())|{'grid.run'}
    assert set(files)==expected and len(files)==16
    assert all(isinstance(b,bytes) and b for b in files.values())
    docs={n:files['OTDocuments/'+n+'.opentrack'] for n in STATIONS}
    p=cd.Project(docs,document_paths=DOC_PATHS,expected_hashes={n:sha(b) for n,b in docs.items()},complete_document_set=True)
    p.check_dest_catalog(files[CATALOGS['dest']])
    counts={};adj=collections.defaultdict(set);connector_count=core_checks=turn_checks=0
    for dn in STATIONS:
        models,byid=p.models[dn],p.byid[dn]
        kinds=collections.Counter(w.kind(m) for m in models)
        assert sum(kinds[k] for k in ('OTEndModel','OTConnModel'))==144
        assert kinds['OTEdgeModel']==80 and kinds['OTSignalModel']==32
        assert kinds['OTStationModel']==1 and kinds['OTRectModel']==4 and kinds['OTLabelModel']==(15 if unified else 14 if outside else 13)
        ends=[m for m in models if w.kind(m) in ('OTEndModel','OTConnModel')]
        assert len([m for m in ends if m.contents[9].value is not None and m.contents[10].value is not None])==24
        assert len([m for m in ends if m.contents[20].value==2])==16
        station=next(m for m in models if w.kind(m)=='OTStationModel')
        assert pf.string(station.contents[7].value)==dn
        if unified:
            rects=[m for m in models if w.kind(m)=='OTRectModel']
            assert {m.contents[2].value for m in rects}=={450.}
            assert {m.contents[9].values[0]-5 for m in rects}=={500.}
            assert len({m.contents[3].value for m in rects})==4
            track_y=[]
            for port in PORTS:
                for lane in (1,2):
                    group=[byid[proofs[dn]['ids'][name(port,f'P{lane}_{r}')][SIDE[port]]] for r in ('START','REF','END')]
                    assert len({m.contents[3].value for m in group})==1
                    assert all(m.contents[5].value==0 and m.contents[4].value in (1,2) for m in group)
                    assert max(m.contents[2].value for m in group)<=1080 and min(m.contents[2].value for m in group)>=320
                    track_y.append(group[0].contents[3].value)
                for role in ('I_A','I_B','O_A','O_B'):
                    assert all(byid[eid].contents[2].value>=1600 for eid in proofs[dn]['ids'][name(port,role)])
            assert len(set(track_y))==8 and max(track_y)-min(track_y)==540
            platform_names={port+str(lane) for port in PORTS for lane in (1,2)}
            for edge in (m for m in models if w.kind(m)=='OTEdgeModel'):
                if pf.string(edge.contents[19].value) not in platform_names:
                    assert not intersects_platform_bay(edge.contents[7].value,edge.contents[8].value), 'Non-platform track crosses the common platform bay'
        for m in models:
            k=w.kind(m)
            if k=='OTSignalModel':
                end=m.contents[7].value
                assert end.contents[11].value is m
                assert [m.contents[i].value for i in (4,5)]==[end.contents[i].value for i in (4,5)]
                assert (m.contents[4].value,m.contents[5].value)!=(0,0)
                assert all(32<=ord(c)<127 for c in pf.string(m.contents[13].value))
                assert not m.contents[9].values[2]&8
            elif k=='OTConnModel':
                remote=pf.string(m.contents[25].value);rid=m.contents[26].value
                other=p.byid[remote][rid]
                assert w.kind(other)=='OTConnModel' and pf.string(other.contents[25].value)==dn
                assert other.contents[26].value==m.contents[0].value
                connector_count+=1;adj[dn].add(remote)
            elif k=='OTEdgeModel':
                a,b=m.contents[7].value,m.contents[8].value
                assert a.contents[7].value is b.contents[7].value
                speed=cf.dictionary(m.contents[16].value)['0']
                assert speed.contents[1].value in (40,80) and speed.contents[2].value==speed.contents[1].value
        for arm in PORTS:
            ids=proofs[dn]['ids']
            for role in ('I_A','I_B','O_A','O_B'):
                assert all(byid[eid].contents[12].value is None and byid[eid].contents[20].value==1
                           for eid in ids[name(arm,role)]),'Junction must be outside native station-associated vertices'
            if outside:
                start=(dn,ids[name(arm,'P1_REF')][SIDE[arm]])
                entry=(dn,ids[name(arm,'I_A')][SIDE[arm]])
                outgoing=next(r for r in pf.mutable_array(byid[start[1]].contents[15].value.contents[0].value)
                              if pf.string(r.contents[1].value).endswith('REF_ENTRY'))
                sequence=p.route_view(outgoing)
                length=sum(p.model(p.edge_between(a,b)).contents[9].values[1] for a,b in zip(sequence,sequence[1:]))
                assert sequence[-1]==entry and length==1300
                assert length-100>=1000 and length-209>100,'An entire waiting proxy train must clear the platform end'
            eid=proofs[dn]['ids'][name(arm,'I_A')][SIDE[arm]]
            routes=pf.mutable_array(byid[eid].contents[15].value.contents[0].value)
            assert len(routes)==3
            for route in routes:
                nodes=p.route_view(route)
                resources={(x[0],p.model(x).contents[7].value.contents[0].value) for x in nodes[1:]}
                assert (dn,proofs[dn]['core_element_id']) in resources
                distance=sum(p.model(p.edge_between(a,b)).contents[9].values[1] for a,b in zip(nodes,nodes[1:]))
                assert distance==400
                assert not any(p.model(x).contents[11].value is not None for x in nodes[1:-1])
                label=pf.string(route.contents[1].value)
                out=label.split('_')[-2]
                assert out!=arm
                core_checks+=1
                if out!=OPPOSITE[arm]:turn_checks+=1
        counts[dn]={'models':len(models),'paired_vertices':72,'station_tracks':8,'turnouts':24,'signals':32,
                    'platform_drawings':4,'central_routes':12,'turn_routes':8}
    assert connector_count==48 and core_checks==108 and turn_checks==72
    for start in STATIONS:
        seen={start};stack=[start]
        while stack:
            at=stack.pop()
            for nxt in adj[at]-seen:seen.add(nxt);stack.append(nxt)
        assert seen==set(STATIONS),'The actual document connector graph must connect all nine stations'

    dests={pf.string(d.contents[1].value):d for d in p.dests}
    assert len(dests)==32 and set(dests)=={x['itinerary'] for x in plans}
    fresh_traces={};reference_usage=set()
    for key,dest in dests.items():
        nodes,path_refs=p.dest_view(dest);refs=[];distance=0;minimum=0.;visits=[]
        for dn,ref in path_refs:
            path=p.owned((dn,ref['start_id']),'OTPath',(ref['name'],ref['array_id'],ref['start_id']))
            _,path_routes=p.path_view(path);refs.extend(path_routes)
        for i,node in enumerate(nodes):
            end=p.model(node)
            if i:
                edge=p.model(p.edge_between(nodes[i-1],node));length=edge.contents[9].values[1]
                half=p.model(p.actual_related(nodes[i-1]));speed=cf.dictionary(edge.contents[16].value)['0']
                limit=speed.contents[1 if edge.contents[7].value is half else 2].value
                assert length>0 and limit>0
                distance+=length;minimum+=length/(limit/3.6)
            if end.contents[20].value==2:
                reference_usage.add(node)
                visits.append((pf.string(end.contents[12].value.contents[7].value),distance,minimum))
                if i:
                    prev=p.model(nodes[i-1]);edge=p.model(p.edge_between(nodes[i-1],node))
                    assert prev.contents[12].value is end.contents[12].value and prev.contents[20].value==1
                    assert edge.contents[9].values[1]==500
        assert distance==2*leg and len(refs)==14 and [v[1] for v in visits]==[0,leg,2*leg]
        for a,b in zip(visits,visits[1:]):assert b[2]-a[2]<next(iter(planned_intervals))
        fresh_traces[key]={'stations':[v[0] for v in visits],'nodes':[list(k) for k in nodes]}
    assert len(reference_usage)==72,'All eight platform tracks at all nine stations must be used by planned journeys'
    cr=w.load_next_compatible(files[CATALOGS['courses']])[0];tt=w.load_next_compatible(files[CATALOGS['timetable']])[0]
    courses={cats.text(c.contents[0].value):c for c in cats.course_items(cr)};rows=cf.timetable(tt)
    trains=w.load_next_compatible(files[CATALOGS['trains']])[0]
    assert len(cats.train_items(trains))==33 and len(courses)==33 and len(rows)==99
    assert set(rows)=={plan['id']+'#'+str(i) for plan in plans for i in range(3)}
    for plan in plans:
        course=courses[plan['id']];tr=fresh_traces[plan['itinerary']]
        assert cats.text(course.contents[3].value)==plan['train']
        assert [cats.text(x) for x in cats.array(course.contents[2].value)]==[plan['itinerary']]
        assert cats.text(course.contents[4].value)=='Reihe R' and course.contents[5].value==1
        assert course.contents[1].value==0 and course.contents[12].values==[0,0]
        assert tr['stations']==plan['documents'] and tr['nodes']==cached_traces[plan['id']]['nodes']
        for i,v in enumerate(plan['visits']):
            row=rows[plan['id']+'#'+str(i)];sec=v['seconds'];clock=f'{sec//3600:02}:{sec//60%60:02}:{sec%60:02}'
            assert cats.text(row.contents[1].value)==plan['id'] and row.contents[3].value==i
            assert cats.text(row.contents[5].value)==v['station']
            assert cats.text(row.contents[6].value)==cats.text(row.contents[7].value)==clock
            assert row.contents[10].value==2+int(i==2) and row.contents[15].values==[0,0,0,0]
            assert cats.text(row.contents[13].value)==cats.text(row.contents[14].value)=='HH:MM:SS'
            assert cats.text(row.contents[18].value)==v['track'] and not cats.array(row.contents[9].value)
    assert cached_traces['H2E1']['nodes']==cached_traces['H2E1_FOLLOW']['nodes']
    archives={n:b for n,b in files.items() if n!='grid.run'}
    docs_list=['OTDocuments/'+n+'.opentrack' for n in STATIONS]
    values=aux.records(files['grid.run']);core=aux.core_bytes(values)
    rr=rb.verify_run(core,archives,catalog_paths=CATALOGS,document_paths=docs_list,execution_root=TARGET.as_posix(),
        path_style='windows',output_directory='output',train_types=['Reihe R'],
        start_day=0,start_time='09:00:00',stop_day=0,stop_time='10:30:00',step='0.2')
    rb.verify_archive_bindings(core,archives,catalog_paths=CATALOGS,document_paths=docs_list)
    assert [v for k,v,_ in values if k=='Break Time']==['00:00:00']
    return {'schema':'nine-junction-grid-static-validation/1','passed':True,'input_files':16,'stations':9,
        'station_documents':counts,'connector_pairs':24,'all_nine_stations_connected':True,
        'local_core_routes_checked':108,'local_turn_routes_checked':72,'shared_junction_core_resources':9,
        'itineraries':32,'courses':33,'timetable_rows':99,'all_72_platform_references_used':True,
        'journey_distance_m':2*leg,'per_leg_distance_m':leg,'terminal_stops_planned':33,
        'junctions_outside_station_associations_checked':True,
        'one_common_horizontal_platform_bay_per_station':unified,
        'all_non_platform_tracks_avoid_common_platform_bay':unified,
        'reference_to_junction_entry_m':1300 if outside else 300,
        'platform_end_to_junction_entry_m':1200 if outside else 200,
        'following_pair':['H2E1','H2E1_FOLLOW'],'following_planned_offset_s':15,
        'run_bindings_verified':True,'native_Signal_alignment_and_icon_flags_checked':True,
        'train_physics_calibrated':False,'junction_capacity_optimized':False,
        'native_application_executed':False,'native_runtime_safety_verified':False}
