"""Finite spatially referenced split plan. Pure immutable bytes, no execution."""
import copy, hashlib, math
from opentrack_ai.current_archive import writer as w, catalogs as c, course_factories as cf
from opentrack_ai.current_archive.multi_document import core as cd
from opentrack_ai.current_archive.multistation_timetable.api import generate_from_spec as base_generate
from opentrack_ai.current_archive.consist_workflow.core import generate_consist, load as load_consist, summary
from opentrack_ai.current_archive.shunting_workflow.core import plan_connections
from opentrack_ai.current_archive.zero_operations import run_bundle as rb

SOURCE_KEYS={'header_document','shapes','depot_template','trains_template','courses_template','timetable_template','connection_template'}
def need(ok,msg):
    if not ok: raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def clock(n):
    need(type(n)is int and 0<=n<86400,'Strict same-day integer seconds required')
    return f'{n//3600:02}:{n//60%60:02}:{n%60:02}'

def generate_from_spec(sources,spec):
    need(type(sources)is dict and set(sources)==SOURCE_KEYS and all(type(b)is bytes and b for b in sources.values()),'Seven immutable source donors required')
    need(type(spec)is dict and set(spec)=={'schema','base','split','accept_uncalibrated_inherited_model','accept_unverified_dynamic_execution'},'Exact spatial split spec required')
    need(spec['schema']=='split-spatial-chain/1','Unsupported schema')
    need(spec['accept_uncalibrated_inherited_model'] is True and spec['accept_unverified_dynamic_execution'] is True,'Explicit model and execution limitations acceptance required')
    base=spec['base'];need(type(base)is dict and base.get('schema')=='multi-station-timetable/1','Explicit base plan required')
    need(base.get('window_days')==1 and type(base.get('window_days'))is int and base.get('bind_connections') is False,'One same-day plan without prior connections required')
    network=base.get('network');need(type(network)is dict,'Network must be an object')
    stations=network.get('stations',[])
    need(type(stations)is list and len(stations)==3,'Exactly three actual chain stations required')
    need(all(type(row)is dict for row in stations),'Each station must be an object')
    ids=[s.get('id') for s in stations];need(all(type(x)is str for x in ids),'Station ids required')
    plans=base.get('plan');need(type(plans)is list and len(plans)==1,'Exactly one initial main Course required')
    main=plans[0];need(type(main)is dict,'Main plan must be an object');need(main.get('itinerary')=='I:chain:forward','Main must follow full forward chain')
    split=spec['split'];need(type(split)is dict and set(split)=={'child_course_id','main_train_name','visits','departure_order_policy'},'Exact split fields required')
    need(split['departure_order_policy']=='child_interval_then_main_unverified','Explicit unverified departure-order plan policy required')
    child_id=cf.name(split['child_course_id']);main_train=cf.name(split['main_train_name'])
    need(child_id!=main.get('course_id') and child_id!=base.get('course_template_id'),'Fresh child Course id required')
    vehicle=base.get('vehicle');need(type(vehicle)is dict and type(vehicle.get('train_names'))is list,'Vehicle object and train name list required')
    need(main_train not in vehicle['train_names'],'Fresh main formation name required')
    child_visits=split['visits'];need(type(child_visits)is list and len(child_visits)==2,'Child has exactly event station and destination')
    for i,v in enumerate(child_visits):
        need(type(v)is dict and set(v)=={'station_sign','arrival_s','departure_s','stop'},'Exact child visit fields')
        need(v['station_sign']==ids[i+1] and v['stop'] is True,'Child event and final visits must stop on actual B-C suffix')
        clock(v['arrival_s']);clock(v['departure_s']);need(v['arrival_s']==v['departure_s'],'No child origin/final dwell in this domain')
    files,base_receipt=base_generate(sources,base)
    
    
    trains0=files['OTData/chain.trains'];depot=files['OTData/chain.depot']
    _,_,_,trainmap,engines,_,_=load_consist(trains0,depot)
    need(len(trainmap)==len(engines)==1,'One Engine donor and child Train required')
    child_train=next(iter(trainmap));engine_name=next(iter(engines))
    trainbytes,formation_receipt=generate_consist(trains0,depot,{'mode':'clone','template_name':child_train,'output_name':main_train,'formation':[{'kind':'engine','name':engine_name},{'kind':'engine','name':engine_name}],'model_policy':'inherit_template','accept_uncalibrated_inherited_model':True})
    _,_,_,trainmap,engines,_,_=load_consist(trainbytes,depot)
    ms=summary(trainmap[main_train],engines);cs=summary(trainmap[child_train],engines)
    need(0<ms['length_m']<=500 and 0<cs['length_m']<ms['length_m'],'Whole initial main and child must geometrically fit the 500m approach')
    paths=base_receipt['topology']['document_paths'];docs={dn:files['OTDocuments/'+dn+'.opentrack']for dn in paths}
    project=cd.Project(docs,document_paths=paths,expected_hashes={k:sha(v)for k,v in docs.items()},complete_document_set=True)
    project.check_dest_catalog(files['OTData/chain.dest'])
    named={c.text(d.contents[1].value):d for d in project.dests}
    main_itin='I:chain:forward';child_itin='I:'+ids[1]+'-'+ids[2]
    need(main_itin in named and child_itin in named,'Actual main and suffix Itineraries required')
    main_nodes,_=project.dest_view(named[main_itin]);child_nodes,_=project.dest_view(named[child_itin])
    def visit_keys(nodes):
        result=[]
        for i,k in enumerate(nodes):
            e=project.model(k)
            if e.contents[20].value==2:
                need(e.contents[12].value is not None,'Unbound reference')
                result.append((c.text(e.contents[12].value.contents[7].value),k,i))
        return result
    mv=visit_keys(main_nodes);cv=visit_keys(child_nodes)
    need([x[0]for x in mv]==ids and [x[0]for x in cv]==ids[1:],'Actual spatial station sequence differs')
    event=mv[1][1];event_i=mv[1][2]
    need(child_nodes[0]==event and child_nodes==main_nodes[event_i:],'Child must be exact same-direction physical suffix from main event End')
    before=main_nodes[event_i-1];ee=project.model(before);xx=project.model(event)
    area_key=project.edge_between(before,event);area=project.model(area_key)
    need(ee.contents[20].value==1 and xx.contents[20].value==2 and ee.contents[12].value is xx.contents[12].value,'Shared actual approach station ownership required')
    need(area.contents[9].values[1]>=ms['length_m'] and xx.contents[11].value is not None,'Approach length/signal missing')
    main_edges=[project.edge_between(a,b)for a,b in zip(main_nodes[event_i:],main_nodes[event_i+1:])]
    child_edges=[project.edge_between(a,b)for a,b in zip(child_nodes,child_nodes[1:])]
    need(main_edges==child_edges,'Directed suffix Edge identity mismatch')
    
    length=0;lower=0.;speed=min(engines[engine_name].contents[7].value,10000)
    for a,b,ek in zip(child_nodes,child_nodes[1:],child_edges):
        edge=project.model(ek);half=project.model(project.actual_related(a));sp=cf.dictionary(edge.contents[16].value)['0'];v=sp.contents[1 if edge.contents[7].value is half else 2].value
        meters=edge.contents[9].values[1];need(type(v)is int and v>0 and type(meters)is int and meters>0,'Positive speed/length required');length+=meters;lower+=meters/(min(v,speed)/3.6)
    need(child_visits[1]['arrival_s']-child_visits[0]['departure_s']+1e-6>=lower,'Child travel below actual directional speed-only bound')
    
    courses,cver=w.load_next_compatible(files['OTData/chain.courses']);items=c.course_items(courses);need(len(items)==1,'One base course')
    cf.settext(items[0],3,main_train)
    trainroot=w.load_next_compatible(trainbytes)[0];destroot=w.load_next_compatible(files['OTData/chain.dest'])[0]
    fields=dict(speed_type='instructional',description='Synthetic spatial split plan',comment='Static same-direction suffix; actual placement unverified',train_number=child_id,course_type='',acceleration_percent=100,delayed_acceleration_percent=100,enabled=True,entering_speed_kmh=0,output_offset_m=0,spacing_mode='discrete',additional_reservation_time_s=0,additional_release_time_s=0)
    courses=cf.new_course(courses,trainroot,destroot,template_id=main['course_id'],course_id=child_id,train=child_train,itineraries=[child_itin],fields=fields)
    ttable,tver=w.load_next_compatible(files['OTData/chain.timetable']);stationroot=w.load_next_compatible(files['OTData/chain.stations'])[0]
    stops=[dict(template_key=main['course_id']+'#0',station_sign=v['station_sign'],arrival=clock(v['arrival_s']),departure=clock(v['departure_s']),arrival_day_offset=0,departure_day_offset=0,stop_at_station=True,timing_station=True,interval_reference_course_id=None,interval_offset_s=0,dwell_s=0,mean_delay_s=0,track_id='',distribution_name='',delta_mass_t=0)for v in child_visits]
    ttable=cf.new_timetable(ttable,courses,stationroot,course_id=child_id,stops=stops)
    coursebytes=w.dump_verified(courses,cver);ttbytes=w.dump_verified(ttable,tver)
    paired,connection_receipt=plan_connections({'courses':coursebytes,'trains':trainbytes,'depot':depot,'stations':files['OTData/chain.stations'],'timetable':ttbytes,'connection_template':sources['connection_template']},{'schema':'split-join-timetable-plan/1','operations':[{'kind':'split','main_course':main['course_id'],'other_course':child_id,'station_sign':ids[1]}],'accept_unverified_spatial_and_dynamic_execution':True})
    files=dict(files);files.update({'OTData/chain.courses':coursebytes,'OTData/chain.trains':trainbytes,'OTData/chain.timetable':paired})
    
    
    main_visits=main['visits'];need(main_visits[2]['arrival_s']>=main_visits[1]['departure_s'],'Main onward schedule')
    need(child_visits[1]['arrival_s']<=main_visits[1]['departure_s'],'Declared planned intervals require child arrival before main departure; physical feasibility is unverified')
    members={k:v for k,v in files.items()if k!='chain.run'}
    files['chain.run'],run_receipt=rb.build_run(members,catalog_paths={k:'OTData/chain.'+k for k in rb.CATALOG_KEYS},document_paths=['OTDocuments/'+k+'.opentrack'for k in paths],execution_root=network['execution_root'],path_style='windows',train_types=['instructional'],stop_day=1)
    fresh=cf.timetable(w.load_next_compatible(paired)[0]);need(len(fresh)==5,'Exactly five TT rows')
    outcourses=c.course_items(w.load_next_compatible(coursebytes)[0]);need(len(outcourses)==2,'Two Course refs')
    for co in outcourses:
        cid=c.text(co.contents[0].value);itins=[c.text(x)for x in c.array(co.contents[2].value)];need(itins==[main_itin if cid==main['course_id']else child_itin],'Saved itinerary mismatch')
    receipt={'schema':'split-spatial-chain-result/1','profile':'three-station-same-day-single-split-two-identical-engine-units','source_sha256':{k:sha(v)for k,v in sources.items()},'files':{k:{'sha256':sha(v),'bytes':len(v)}for k,v in files.items()},'courses':2,'timetable_rows':5,'connection_records':2,'initial_main':ms,'initial_child':cs,'formation':formation_receipt,'connections':connection_receipt,'spatial':{'main_itinerary':main_itin,'child_itinerary':child_itin,'station_order':ids,'main_nodes':[list(k)for k in main_nodes],'child_nodes':[list(k)for k in child_nodes],'event_end':list(event),'approach_entry':list(before),'approach_edge':list(area_key),'approach_length_m':area.contents[9].values[1],'same_direction_suffix_verified':True,'same_directed_edge_sequence_verified':True,'child_suffix_edge_keys':[list(k)for k in child_edges],'child_length_m':length,'child_speed_only_lower_bound_s':lower,'actual_stopping_position_verified':False,'same_track_runtime_reservation_verified':False},'schedule':{'main':copy.deepcopy(main),'child_visits':copy.deepcopy(child_visits),'shared_suffix_planned_intervals_disjoint':True,'departure_order_policy':split['departure_order_policy'],'child_can_pass_main_at_station_verified':False,'head_tail_placement_verified':False},'run':run_receipt,'topology':base_receipt['topology'],'initial_post_split_train_not_premutated':True,'actual_fields_written':False,'preview_only':True,'saved':False,'native_execution':False,'native_runtime_ready':False,'dynamic_split_verified':False,'shunting_route_generated':False,'scope':'Complete saved project with actual same-direction spatial suffix and finite split plan. Runtime head/tail placement, reservation, split removal/order, native operation and physical calibration remain unverified.'}
    return files,receipt
