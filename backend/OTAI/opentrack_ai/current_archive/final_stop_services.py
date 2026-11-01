"""Finite single-document final-stop service catalogs; no simulator or I/O.
New explicit domain using low-level record factories, not a pass-only flag patch.
"""
import copy,math
from . import writer as w,catalogs as c,course_factories as cf
from .zero_terminal.area_operations import need,name,sha,arr_like,dictionary_like,station_sequence

def generate_final_stop_services(inputs,*,area_specs,course_template_id,timetable_template_key,document_name,plan,speed_type='Reihe R'):
    required={'courses_template','timetable_template','trains','depot','stations','document','dest','run_template'}
    need(set(inputs)==required and all(type(x)is bytes for x in inputs.values()),'Eight immutable explicit byte sources required')
    need(type(plan)is list and 1<=len(plan)<=100,'Bounded nonempty Course plan required')
    from opentrack_ai.current_archive.zero_operations.speed_preferences import read_train_types,index_for_course
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
    from .zero_terminal.terminal_areas import read_document
    read_document(inputs['document'],area_specs)
    need(set(known_stations)=={a['sign']for a in area_specs},'Exact Station catalog/area identity closure required')
    for area in area_specs:
        station=known_stations[area['sign']]
        need(c.text(station.contents[2].value)==area['name'] and station.contents[7].value==1,'Station catalog name/timing differs from area spec')
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
        need(not(categories[category_name].contents[0].values[1]&0x20),'Category stopAtEveryStation conflicts with explicit final-only stop profile')
        engine_names=c.bound_engine_names(train_records[train]);need(len(engine_names)==1 and not c.array(train_records[train].contents[2].values[2]),'Initial speed-cap profile requires single Engine and no trailers')
        engine_refs=c.array(train_records[train].contents[2].values[1]);need(type(engine_refs[0].contents[1].value)is int and engine_refs[0].contents[1].value==1,'Area profile requires one Engine reference at integer posInTrain 1; position is not quantity')
        need(engine_names[0] in engine_records,'Train Engine binding missing')
        engine=engine_records[engine_names[0]];vehicle_speed=engine.contents[7].value;need(type(vehicle_speed)is int and 0<vehicle_speed<=1000,'Positive bounded Engine maximum speed required')
        cache_key=(itin,speed_index,vehicle_speed)
        if cache_key not in seq_cache:seq_cache[cache_key]=station_sequence(inputs['document'],inputs['dest'],itin,document_name,area_specs=area_specs,details=True,speed_index=speed_index,maximum_vehicle_speed_kmh=vehicle_speed)
        visits=entry['visits'];need(type(visits)is list and all(type(x)is dict and set(x)=={'station_sign','absolute_seconds','stop'} for x in visits),'Invalid visits')
        actual=seq_cache[cache_key];signs=[x['station_sign']for x in actual]
        need(2<=len(visits)<=100 and len(visits)==len(actual),'Two to 100 exact actual and planned station occurrences required')
        need(len(set(signs))==len(signs),'Single journey without repeated station occurrences required')
        terminal=next((s for s in area_specs if s['sign']==signs[-1]),None)
        need(terminal is not None and terminal['stop'] is not None,'Last station needs explicit stopping area')
        stop=terminal['stop']
        need(actual[-1]['end_id']==stop['exit_end_id'] and actual[-1]['previous_end_id']==stop['entry_end_id'],'Last station wrong direction or lacks actual entry-to-reference approach')
        length=float(engine.contents[2].values[2]);need(math.isfinite(length) and length>0 and math.ceil(length)<=stop['length_m'],'Actual whole consist must fit stopping area')
        total_rows+=len(visits);need(total_rows<=100000,'Total planned rows exceed 100000 guard')
        need([x['station_sign'] for x in visits]==[x['station_sign']for x in seq_cache[cache_key]],'Planned stations differ from actual itinerary occurrence order')
        need({x['station_sign']for x in seq_cache[cache_key]}<=set(known_stations),'Station catalog binding missing')
        fields={'speed_type':name(speed_type),'description':'Explicit final-stop single journey','comment':'Planned only; no native simulation','train_number':cid,'course_type':'','acceleration_percent':100,'delayed_acceleration_percent':100,'enabled':True,'entering_speed_kmh':0,'output_offset_m':0,'spacing_mode':'discrete','additional_reservation_time_s':0,'additional_release_time_s':0}
        temp_courses=cf.new_course(temp_courses,tr,dest,template_id=course_template_id,course_id=cid,train=train,itineraries=[itin],fields=fields)
        stops=[];prior=-1;previous_minimum=None
        for visit_index,(visit,trace) in enumerate(zip(visits,seq_cache[cache_key])):
            need(type(visit['stop'])is bool and visit['stop']==(visit_index==len(visits)-1),'Only final station stops; earlier visits must pass')
            sec=visit['absolute_seconds'];need(type(sec)is int and 0<=sec<=366*86400 and sec>prior,'Times must strictly increase within supported absolute day range')
            if previous_minimum is not None:need(sec-prior+1e-6>=trace['minimum_edge_time_s']-previous_minimum,'Planned interval below Edge speed-limit travel-time lower bound')
            prior=sec;previous_minimum=trace['minimum_edge_time_s']
            day,clock=divmod(sec,86400);h,clock=divmod(clock,3600);m,s=divmod(clock,60);clock=f'{h:02}:{m:02}:{s:02}'
            stops.append(dict(template_key=timetable_template_key,station_sign=visit['station_sign'],arrival=clock,departure=clock,arrival_day_offset=day,departure_day_offset=day,stop_at_station=visit['stop'],timing_station=True,interval_reference_course_id=None,interval_offset_s=0,dwell_s=0,mean_delay_s=0,track_id='',distribution_name='',delta_mass_t=0))
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
    courses={c.text(o.contents[0].value):o for o in c.course_items(fresh['courses'])}
    for entry in plan:
        cid=entry['course_id'];course=courses[cid]
        need(c.text(course.contents[3].value)==entry['train'] and [c.text(x)for x in c.array(course.contents[2].value)]==[entry['itinerary']],'Fresh exact Course references mismatch')
        for index,visit in enumerate(entry['visits']):
            row=rows[cid+'#'+str(index)];day,seconds=divmod(visit['absolute_seconds'],86400);h,rem=divmod(seconds,3600);m,s=divmod(rem,60);clock=f'{h:02}:{m:02}:{s:02}'
            need(c.text(row.contents[1].value)==cid and row.contents[3].value==index and row.contents[4].value==len(entry['visits'])-1 and c.text(row.contents[5].value)==visit['station_sign'],'Fresh Timetable identity/order/station mismatch')
            need(c.text(row.contents[6].value)==c.text(row.contents[7].value)==clock and row.contents[15].values[:2]==[day,day],'Fresh planned time/day mismatch')
            need(row.contents[10].value==(3 if visit['stop'] else 2) and float(c.text(row.contents[8].value))==0,'Fresh stop/timing flags or dwell mismatch')
    return out,{'operation':'fresh_final_stop_service_catalogs','courses':len(plan),'timetable_rows':len(rows),'train_definitions_used':len({e['train']for e in plan}),'source_sha256':{k:sha(v)for k,v in inputs.items()},'output_sha256':{k:sha(v)for k,v in out.items()},'template_course_emitted':False,'template_timetable_row_emitted':False,'network_station_order_checked':True,'native_station_vertex_predicate_checked':True,'recognized_planned_occurrences_not_native_events':True,'speed_type_name':speed_type,'ordered_run_train_types':speed_types,'edge_speed_index':speed_index,'run_file_used_for_mapping_only':True,'minimum_time_check':'sum edge length/min(direction-specific speed limit, Engine vmax); ignores acceleration/curvature/conflicts, only necessary bound','planned_times_only':True,'physical_fleet_circulation_proven':False,'explicit_terminal_stop_flags_supported':True,'stopping_platforms_supported':False,'final_stop_area_static_contract_checked':True,'intermediate_stops_supported':False,'dwell_supported':False,'connections_supported':False,'fresh_archive_reload_verified':True,'native_simulation_executed':False,'test_scope':'current archive closure and ordered planned visit times, not capacity or vehicle motion'}
