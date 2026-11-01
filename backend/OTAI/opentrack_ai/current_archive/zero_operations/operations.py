"""Fresh daily Course/Timetable catalogs; planned times only, no simulator.

Uses the audited current factories with an explicit in-memory type template.
Template rows are never emitted. Network station order is resolved from the
full persisted Path/Route occurrence lists, not deduplicated by station name.
"""
import copy
import hashlib
import math
from opentrack_ai.current_archive import writer as w, catalogs as c, course_factories as cf
from opentrack_ai.current_archive import path_functions as pf, route_factory as rf

class OperationsError(ValueError): pass

def need(x, msg):
    if not x: raise OperationsError(msg)

def name(x): return cf.name(x)
def sha(x): return hashlib.sha256(x).hexdigest()
def arr_like(src, values):
    out=cf.clone(src); w.set_elements(out,values); return out

def dictionary_like(src, pairs):
    cf.dictionary(src)
    out=cf.clone(src);out.contents=[w.TypedValue(b'i',len(pairs))]
    for key,value in pairs:
        out.contents += [w.TypedValue(b'@',cf.string(src,key)),w.TypedValue(b'@',value)]
    return out

def station_sequence(document_blob,dest_blob,itinerary,document_name,*,details=False,speed_index='0',maximum_vehicle_speed_kmh=None):
    """Single-document forward selected itinerary/station/speed reference checks; not full network validation."""
    name(itinerary);name(document_name)
    from .station_binding import read_document
    
    doc,_,_,_=read_document(document_blob,allow_stations=True);cat,_=w.load_next_compatible(dest_blob)
    rf.layout(doc,'OTDocument',4,['i','i','@','i','i','@','@','@','ffff','ffff','ffff','f','@','@','ffff','iii','ff','@','@','@','@'])
    need(doc.contents[0].value==17,'Current Document marker17 required')
    models=pf.mutable_array(doc.contents[2].value); mids={id(o) for o in models}
    for o in models:
        if w.kind(o)=='OTEndModel':rf.layout(o,'OTEndModel',7,rf.END,graphic=True)
        elif w.kind(o)=='OTEdgeModel':rf.layout(o,'OTEdgeModel',3,rf.EDGE,graphic=True)
        elif w.kind(o)=='OTStationModel':rf.layout(o,'OTStationModel',1,['i','f','f','f','i','i','@','@','ii','ii'],graphic=True)
    graphic_ids=[o.contents[0].value for o in models];need(len(set(graphic_ids))==len(graphic_ids),'Duplicate graphic ID')
    ends={o.contents[0].value:o for o in models if w.kind(o)=='OTEndModel'}
    need(len(ends)==sum(w.kind(o)=='OTEndModel' for o in models),'Duplicate End ID')
    rf.layout(doc.contents[5].value,'OTMutableArray',0,['@'])
    dests=pf.mutable_array(doc.contents[5].value.contents[0].value)
    targets=[d for d in dests if w.kind(d)=='OTDest' and pf.string(d.contents[1].value)==itinerary]
    need(len(targets)==1,'Itinerary must be uniquely owned by Document')
    dest=targets[0];pf.shape(dest,'OTDest');infos=pf.info(dest)['saved_references']
    cf.itinerary_names(cat)
    cis=[x for x in c.array(cat.contents[0].value) if c.text(x.contents[1].value)==itinerary]
    need(len(cis)==1,'Itinerary catalog identity absent/ambiguous')
    def extinfo(obj):
        return [(pf.string(x.contents[0].value),tuple(x.contents[1].values),pf.string(x.contents[2].value)) for x in c.array(obj.contents[4].value)]
    need(extinfo(dest)==extinfo(cis[0]),'Document/catalog itinerary references differ')
    sequence=[];persisted_paths=c.array(dest.contents[0].value)
    need(len(persisted_paths)==1,'Dest must persist exactly first Path')
    for occurrence,inf in enumerate(infos):
        need(inf['document']==document_name,'Cross-document Path unsupported')
        owner=ends.get(inf['start_id']);need(owner is not None,'Path owner absent')
        rf.wrapper(owner.contents[17].value,'OTPathList')
        ps=c.array(owner.contents[17].value.contents[0].value)
        found=[p for p in ps if pf.string(p.contents[1].value)==inf['name'] and p.contents[2].values==[inf['array_id'],inf['start_id']]]
        need(len(found)==1,'Path reference not in exact owner list');path=found[0];pf.shape(path,'OTPath')
        if occurrence==0:need(persisted_paths[0] is path,'Persisted first Path differs from full info list')
        route_infos=pf.info(path)['saved_references'];nodes=[];persisted_routes=c.array(path.contents[0].value)
        need(len(persisted_routes)==1,'Path must persist exactly first Route')
        for route_occurrence,ri in enumerate(route_infos):
            ro=ends.get(ri['start_id']);need(ro is not None,'Route owner absent')
            rf.wrapper(ro.contents[15].value,'OTRouteList')
            rs=c.array(ro.contents[15].value.contents[0].value)
            hits=[r for r in rs if pf.string(r.contents[1].value)==ri['name'] and r.contents[2].values==[ri['array_id'],ri['start_id']]]
            need(len(hits)==1,'Route reference not in exact owner list');route=hits[0];pf.shape(route,'OTRoute')
            if route_occurrence==0:need(persisted_routes[0] is route,'Persisted first Route differs from full info list')
            ns=c.array(route.contents[0].value);need(len(ns)>=2 and all(id(e) in mids and w.kind(e)=='OTEndModel' for e in ns),'Route End membership')
            need(ns[0] is ro,'Route first End differs from owner')
            for a,b in zip(ns,ns[1:]):
                related=ends.get(a.contents[8].value)
                need(related is not None and related.contents[8].value==a.contents[0].value,'Broken related pair')
                ee=[v for v in [related.contents[9].value,related.contents[10].value] if v is not None]
                matches=[e for e in ee if id(e) in mids and w.kind(e)=='OTEdgeModel' and ((e.contents[7].value is related and e.contents[8].value is b) or (e.contents[8].value is related and e.contents[7].value is b))]
                need(len(matches)==1 and matches[0] in (b.contents[9].value,b.contents[10].value),'Actual Edge/backreference missing')
            if nodes:need(nodes[-1] is ns[0],'Disconnected Routes')
            nodes += ns if not nodes else ns[1:]
        
        
        station_vertices={}
        for node in nodes:
            sm=node.contents[12].value
            if sm is not None:
                pair_key=tuple(sorted((node.contents[0].value,node.contents[8].value)))
                sign=c.text(sm.contents[7].value)
                need(sign not in station_vertices or station_vertices[sign]==pair_key,'Multiple distinct reference vertices for one station in a Path')
                station_vertices[sign]=pair_key
        need(nodes and nodes[0] is owner and len({id(x) for x in nodes})==len(nodes),'Invalid internally cyclic Path or wrong owner')
        if sequence:need(sequence[-1] is nodes[0],'Disconnected Path occurrences')
        sequence += nodes if not sequence else nodes[1:]
    need(sequence,'Empty Itinerary')
    station_models={id(o):o for o in models if w.kind(o)=='OTStationModel'}
    stations=[];trace=[];distance=0;minimum_time=0.;previous_end=None
    need(sequence[0].contents[12].value is not None and sequence[-1].contents[12].value is not None,'Pass-only profile requires station-bound first/last Ends')
    for e in sequence:
        if previous_end is not None:
            related=ends[previous_end.contents[8].value]
            edge=next(x for x in (related.contents[9].value,related.contents[10].value) if x is not None and ((x.contents[7].value is related and x.contents[8].value is e)or(x.contents[8].value is related and x.contents[7].value is e)))
            length=edge.contents[9].values[1];need(type(length)is int and length>0,'Positive native Edge length required')
            speeds=cf.dictionary(edge.contents[16].value);need(speed_index in speeds,'Course speed-type index absent on an itinerary Edge')
            speed=speeds[speed_index];c.shape(speed,'OTSpeed',0,['@','i','i','i'])
            limit=speed.contents[1 if edge.contents[7].value is related else 2].value;need(type(limit)is int and limit>0,'Positive direction-specific speed limit required')
            if maximum_vehicle_speed_kmh is not None:
                need(type(maximum_vehicle_speed_kmh) in (int,float) and math.isfinite(maximum_vehicle_speed_kmh) and maximum_vehicle_speed_kmh>0,'Positive finite vehicle speed cap required')
                limit=min(limit,maximum_vehicle_speed_kmh)
            distance+=length;minimum_time+=length/(limit/3.6)
        previous_end=e
        s=e.contents[12].value
        if e.contents[20].value==2:
            need(s is not None,'Recognized StationVertex lacks station association')
            need(id(s) in station_models,'End references external StationModel')
            stations.append(c.text(s.contents[7].value));trace.append({'station_sign':stations[-1],'distance_m':distance,'minimum_edge_time_s':minimum_time})
    need(len(stations)>=2,'Need at least two network station occurrences')
    return trace if details else stations

def daily_plan(train_names, itinerary, stations, *, hours=24, interval_s=3600, phase_s=300, visit_spacing_s=180, start_s=0, window_end_s=86400):
    need(type(train_names)is list and 1<=len(train_names)<=100,'Explicit Train names required')
    need(len(set(train_names))==len(train_names),'Duplicate Train names')
    for n in train_names:name(n)
    name(itinerary);need(type(stations)is list and 2<=len(stations)<=10000,'Bounded station sequence required')
    for s in stations:name(s)
    for k,v in [('hours',hours),('interval_s',interval_s),('phase_s',phase_s),('visit_spacing_s',visit_spacing_s),('start_s',start_s),('window_end_s',window_end_s)]:
        need(type(v)is int and v>=0,k+' must be nonnegative integer')
    need(1<=hours<=366*24 and interval_s>0 and visit_spacing_s>0,'Invalid daily window settings')
    need(hours*len(train_names)<=10000 and hours*len(train_names)*len(stations)<=100000,'Daily plan exceeds guarded record limit')
    need(hours==1 or (len(stations)-1)*visit_spacing_s<interval_s,'Repeated services of one Train definition overlap in this daily-plan profile')
    out=[]
    for h in range(hours):
        for i,t in enumerate(train_names):
            begin=start_s+h*interval_s+i*phase_s
            visits=[begin+j*visit_spacing_s for j in range(len(stations))]
            need(visits[-1]<=window_end_s,'Course exceeds explicit plan window')
            course='DAY_'+str(h).zfill(3)+'_'+str(i+1).zfill(2)
            out.append({'course_id':course,'train':t,'itinerary':itinerary,'visits':[{'station_sign':s,'absolute_seconds':sec} for s,sec in zip(stations,visits)]})
    return out

def generate_service_catalogs(inputs,*,course_template_id,timetable_template_key,document_name,plan,speed_type='Reihe R'):
    required={'courses_template','timetable_template','trains','depot','stations','document','dest','run_template'}
    need(set(inputs)==required and all(type(x)is bytes for x in inputs.values()),'Eight immutable explicit byte sources required')
    need(type(plan)is list and 1<=len(plan)<=10000,'Bounded nonempty Course plan required')
    from .speed_preferences import read_train_types,index_for_course
    speed_types=read_train_types(inputs['run_template']);speed_index=str(index_for_course(inputs['run_template'],speed_type))
    roots={k:w.load_next_compatible(v) for k,v in inputs.items() if k!='run_template'}
    ct,cv=roots['courses_template'];tt,tv=roots['timetable_template'];tr=roots['trains'][0];st=roots['stations'][0];dest=roots['dest'][0]
    need(ct.contents[0].value==17,'Current CourseList marker17 required')
    candidates={c.text(o.contents[0].value):o for o in c.course_items(ct)}
    need(course_template_id in candidates,'Explicit current Course type-template absent')
    templ=candidates[course_template_id]; cf.name(course_template_id)
    trows=cf.timetable(tt);need(timetable_template_key in trows,'Explicit current Timetable type-template absent')
    row=trows[timetable_template_key];need(not c.array(row.contents[9].value),'Connection-bearing row template unsupported')
    train_records={c.text(o.contents[0].value):o for o in c.train_items(tr)};known_trains=set(train_records);known_stations=c.station_items(st)
    from opentrack_ai.current_archive.stock_operations import CATEGORY_LAYOUT
    engine_records={c.text(e.contents[1].value):e for e in c.engine_items(roots['depot'][0])}
    categories={}
    for category in c.array(tr.contents[1].value):
        c.shape(category,'OTTrainCategory',19,CATEGORY_LAYOUT);key=c.text(category.contents[1].value)
        need(key not in categories,'Duplicate Category name');categories[key]=category
    
    temp_courses=cf.clone(ct)
    for i in (1,2,3):temp_courses.contents[i].value=arr_like(ct.contents[i].value,[])
    temp_courses.contents[4].value=arr_like(ct.contents[4].value,[copy.deepcopy(templ)])
    temp_table=dictionary_like(tt,[(timetable_template_key,copy.deepcopy(row))])
    names=set();seq_cache={};expected=[];total_rows=0
    for entry in plan:
        need(type(entry)is dict and set(entry)=={'course_id','train','itinerary','visits'},'Unknown/missing Course plan fields')
        cid=name(entry['course_id']);train=name(entry['train']);itin=name(entry['itinerary'])
        need(cid not in names and cid!=course_template_id,'Duplicate/template Course identity');names.add(cid)
        need(train in known_trains,'Unknown exact Train')
        category_name=c.text(train_records[train].contents[3].value)
        need(category_name in categories,'Train Category binding missing')
        need(not(categories[category_name].contents[0].values[1]&0x20),'Category stopAtEveryStation conflicts with ordinary pass-only profile')
        engine_names=c.bound_engine_names(train_records[train]);need(len(engine_names)==1 and not c.array(train_records[train].contents[2].values[2]),'Initial speed-cap profile requires single Engine and no trailers')
        need(engine_names[0] in engine_records,'Train Engine binding missing')
        engine=engine_records[engine_names[0]];vehicle_speed=engine.contents[7].value;need(type(vehicle_speed)is int and 0<vehicle_speed<=1000,'Positive bounded Engine maximum speed required')
        cache_key=(itin,speed_index,vehicle_speed)
        if cache_key not in seq_cache:seq_cache[cache_key]=station_sequence(inputs['document'],inputs['dest'],itin,document_name,details=True,speed_index=speed_index,maximum_vehicle_speed_kmh=vehicle_speed)
        visits=entry['visits'];need(type(visits)is list and all(type(x)is dict and set(x)=={'station_sign','absolute_seconds'} for x in visits),'Invalid visits')
        total_rows+=len(visits);need(total_rows<=100000,'Total planned rows exceed 100000 guard')
        need([x['station_sign'] for x in visits]==[x['station_sign']for x in seq_cache[cache_key]],'Planned stations differ from actual itinerary occurrence order')
        need({x['station_sign']for x in seq_cache[cache_key]}<=set(known_stations),'Station catalog binding missing')
        fields={'speed_type':name(speed_type),'description':'Synthetic daily plan','comment':'Planned only; no native simulation','train_number':cid,'course_type':'','acceleration_percent':100,'delayed_acceleration_percent':100,'enabled':True,'entering_speed_kmh':0,'output_offset_m':0,'spacing_mode':'discrete','additional_reservation_time_s':0,'additional_release_time_s':0}
        temp_courses=cf.new_course(temp_courses,tr,dest,template_id=course_template_id,course_id=cid,train=train,itineraries=[itin],fields=fields)
        stops=[];prior=-1;previous_minimum=None
        for visit,trace in zip(visits,seq_cache[cache_key]):
            sec=visit['absolute_seconds'];need(type(sec)is int and 0<=sec<=366*86400 and sec>prior,'Times must strictly increase within supported absolute day range')
            if previous_minimum is not None:need(sec-prior+1e-6>=trace['minimum_edge_time_s']-previous_minimum,'Planned interval below Edge speed-limit travel-time lower bound')
            prior=sec;previous_minimum=trace['minimum_edge_time_s']
            day,clock=divmod(sec,86400);h,clock=divmod(clock,3600);m,s=divmod(clock,60);clock=f'{h:02}:{m:02}:{s:02}'
            stops.append(dict(template_key=timetable_template_key,station_sign=visit['station_sign'],arrival=clock,departure=clock,arrival_day_offset=day,departure_day_offset=day,stop_at_station=False,timing_station=True,interval_reference_course_id=None,interval_offset_s=0,dwell_s=0,mean_delay_s=0,track_id='',distribution_name='',delta_mass_t=0))
        temp_table=cf.new_timetable(temp_table,temp_courses,st,course_id=cid,stops=stops)
        expected.append((cid,train,itin,len(stops)))
    final_courses=cf.clone(temp_courses);final_courses.contents[4].value=arr_like(temp_courses.contents[4].value,[o for o in c.course_items(temp_courses) if c.text(o.contents[0].value)!=course_template_id])
    final_table=dictionary_like(temp_table,[(k,v)for k,v in cf.timetable(temp_table).items() if k!=timetable_template_key])
    out={'courses':w.dump_verified(final_courses,cv),'timetable':w.dump_verified(final_table,tv)}
    fresh={k:w.load_next_compatible(b)[0]for k,b in out.items()}
    need({c.text(o.contents[0].value)for o in c.course_items(fresh['courses'])}==names,'Fresh Course identity mismatch')
    rows=cf.timetable(fresh['timetable']);need(len(rows)==sum(x[3] for x in expected),'Fresh timetable row count mismatch')
    for row in rows.values():
        need(c.text(row.contents[1].value) in names,'Old Course retained')
        need(c.text(row.contents[13].value)==c.text(row.contents[14].value)=='HH:MM:SS' and row.contents[15].values[2:]==[0,0],'Actual results not reset')
        need(not c.array(row.contents[9].value),'Unexpected Connection retained')
    return out,{'operation':'fresh_daily_service_catalogs','courses':len(plan),'timetable_rows':len(rows),'train_definitions_used':len({e['train']for e in plan}),'source_sha256':{k:sha(v)for k,v in inputs.items()},'output_sha256':{k:sha(v)for k,v in out.items()},'template_course_emitted':False,'template_timetable_row_emitted':False,'network_station_order_checked':True,'native_station_vertex_predicate_checked':True,'recognized_planned_occurrences_not_native_events':True,'speed_type_name':speed_type,'ordered_run_train_types':speed_types,'edge_speed_index':speed_index,'run_file_used_for_mapping_only':True,'minimum_time_check':'sum edge length/min(direction-specific speed limit, Engine vmax); ignores acceleration/curvature/conflicts, only necessary bound','planned_times_only':True,'physical_fleet_circulation_proven':False,'stopping_platforms_supported':False,'native_simulation_executed':False,'test_scope':'current archive closure and ordered planned visit times, not capacity or vehicle motion'}
