"""Cross-document service composition. Pure bytes, static saved-data contract only.

No source application, subprocess, network, filesystem publication or runtime cache.
A single vehicle-type definition is deliberately not a proven physical fleet.
"""
import copy
import hashlib
import math
from .topology import cd, validate_terminal_project
from opentrack_ai.current_archive import writer as w, catalogs as c, course_factories as cf
from opentrack_ai.current_archive import native_connections as nc
from opentrack_ai.current_archive.stock_operations import CATEGORY_LAYOUT
from opentrack_ai.current_archive.zero_operations import vehicle_catalogs as vc, run_bundle as rb
from opentrack_ai.current_archive.zero_operations.speed_preferences import read_train_types,index_for_course
Project=cd.Project

class OperationsError(ValueError): pass
def need(ok,msg):
    if not ok: raise OperationsError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def arr_like(old,values):
    out=cf.clone(old);w.set_elements(out,values);return out
def dict_like(old,pairs):
    cf.dictionary(old);out=cf.clone(old);out.contents=[w.TypedValue(b'i',len(pairs))]
    for k,v in pairs:out.contents += [w.TypedValue(b'@',cf.string(old,k)),w.TypedValue(b'@',v)]
    return out

def clock(sec):
    need(type(sec)is int and 0<=sec<86400,'One-day profile requires integer seconds 0..86399; day wrapping rejected')
    return f'{sec//3600:02}:{sec//60%60:02}:{sec%60:02}'

def default_plan(*,train='AB_TRAIN',count=48,start_s=300,interval_s=1800,travel_s=300):
    for x in (count,start_s,interval_s,travel_s):need(type(x)is int,'Integer plan parameters required')
    need(2<=count<=1000 and interval_s>travel_s>0,'Bounded nonoverlapping plan required')
    out=[]
    for i in range(count):
        start=start_s+i*interval_s;finish=start+travel_s;clock(start);clock(finish)
        a,b=('A','B')if i%2==0 else('B','A')
        out.append({'course_id':f'AB_{i:03}','train':train,'itinerary':f'I:{a}-{b}','visits':[{'station_sign':a,'arrival_s':start,'departure_s':start,'stop':False},{'station_sign':b,'arrival_s':finish,'departure_s':finish,'stop':True}]})
    return out

def trace_project(documents,document_paths,dest_blob,stations_blob,*,speed_index,vehicle_speed):
    need(type(vehicle_speed)is int and 0<vehicle_speed<=1000,'Bounded Engine speed required')
    project=Project(documents,document_paths=document_paths,expected_hashes={k:sha(b)for k,b in documents.items()},complete_document_set=True)
    project.check_dest_catalog(dest_blob)
    stations=c.station_items(w.load_next_compatible(stations_blob)[0]);sign_owners={}
    for dn,models in project.models.items():
        sms=[m for m in models if w.kind(m)=='OTStationModel'];need(len(sms)==1,'Exactly one StationModel per document required')
        sm=sms[0];sign=c.text(sm.contents[7].value)
        need(sign not in sign_owners and sign in stations,'Station sign must be unique across all documents and present in catalog')
        c.text(stations[sign].contents[2].value) 
        sign_owners[sign]=dn
    need(set(sign_owners)==set(stations),'Station catalog exact closure required')
    traces={}
    for dest in project.dests:
        name=c.text(dest.contents[1].value);nodes,_=project.dest_view(dest);trace=[];dist=lower=0.;edges=[]
        for i,key in enumerate(nodes):
            end=project.model(key)
            if i:
                ek=project.edge_between(nodes[i-1],key);edge=project.model(ek);actual=project.actual_related(nodes[i-1]);half=project.model(actual)
                length=edge.contents[9].values[1];need(type(length)is int and length>0,'Positive native Edge length required')
                speeds=cf.dictionary(edge.contents[16].value);need(speed_index in speeds,'Speed-type index absent on selected Edge')
                sp=speeds[speed_index];c.shape(sp,'OTSpeed',0,['@','i','i','i'])
                speed=sp.contents[1 if edge.contents[7].value is half else 2].value
                need(type(speed)is int and 0<speed<=1000,'Positive bounded direction-specific speed required')
                dist+=length;lower+=length/(min(speed,vehicle_speed)/3.6);edges.append(list(ek))
            if end.contents[20].value==2:
                sm=end.contents[12].value;need(sm is not None and w.kind(sm)=='OTStationModel','StationVertex requires owned station')
                sign=c.text(sm.contents[7].value);need(sign_owners.get(sign)==key[0],'Station reference crosses document ownership')
                trace.append({'station_sign':sign,'end_key':list(key),'previous_end_key':None if i==0 else list(nodes[i-1]),'distance_m':dist,'minimum_edge_time_s':lower})
        need(len(trace)==2 and trace[0]['end_key']==list(nodes[0]) and trace[-1]['end_key']==list(nodes[-1]),'Exactly two endpoint station occurrences required')
        need(trace[0]['station_sign']!=trace[1]['station_sign'],'Distinct station endpoints required')
        traces[name]={'visits':trace,'nodes':[list(n)for n in nodes],'edges':edges,'distance_m':dist,'minimum_edge_time_s':lower}
    need(len(traces)==2,'Exactly reciprocal two-station itineraries required')
    a,b=list(traces.values());need(a['visits'][0]['station_sign']==b['visits'][-1]['station_sign'] and a['visits'][-1]['station_sign']==b['visits'][0]['station_sign'],'Two itineraries are not reciprocal')
    return project,traces

def validate_stops(project,traces,stop_specs,length_m):
    """Structural stopping domain: reference2 + ordinary1 + actual area approach.
    Reverse-course departure starts at related reference half; runtime turnround unproven.
    """
    need(type(stop_specs)is dict and len(stop_specs)==2,'Two explicit destination stopping areas required')
    for trace in traces.values():
        visit=trace['visits'][-1];sign=visit['station_sign'];need(sign in stop_specs,'Missing terminal stop')
        s=stop_specs[sign];required={'document','entry_end_id','exit_end_id','length_m','area_edge_id','departure_end_id'}
        need(type(s)is dict and set(s)==required,'Exact terminal stop contract required')
        dn=s['document'];need(type(dn)is str,'Document key required')
        for k in required-{'document'}:need(type(s[k])is int and s[k]>=0,'Integer stop identity/length required')
        entry=(dn,s['entry_end_id']);exit=(dn,s['exit_end_id']);edgekey=(dn,s['area_edge_id']);dep=(dn,s['departure_end_id'])
        need(visit['end_key']==list(exit) and visit['previous_end_key']==list(entry),'Terminal must be reached on actual entry-to-reference direction')
        need(project.edge_between(entry,exit)==edgekey,'Wrong stopping Edge')
        e=project.model(edgekey);need(s['length_m']==e.contents[9].values[1] and math.ceil(length_m)<=s['length_m'],'Train does not fit exact saved stopping Edge')
        ee=project.model(entry);xx=project.model(exit);dd=project.model(dep)
        need(w.kind(ee)==w.kind(xx)==w.kind(dd)=='OTEndModel','Connectors cannot be stop references')
        need(ee.contents[20].value==1 and xx.contents[20].value==2,'Ordinary entry and StationVertex exit required')
        sm=xx.contents[12].value;need(sm is not None and ee.contents[12].value is sm,'Stopping area requires same owned StationModel')
        need(project.related(exit)==dep and project.related(dep)==exit and dd.contents[12].value is sm and dd.contents[20].value==2,'Departure must use reciprocal StationVertex half')
        for key in (entry,exit):
            other=project.model(project.related(key));orig=project.model(key)
            need(other.contents[12].value is sm and other.contents[20].value==orig.contents[20].value,'Asymmetric station pair')
        for end in (xx,dd):
            sig=end.contents[11].value;need(sig is not None and w.kind(sig)=='OTSignalModel','Arrival exit and reverse departure require actual signals')
        start=next((x['visits'][0]for x in traces.values()if x['visits'][0]['station_sign']==sign),None)
        need(start is not None and start['end_key']==list(dep),'Opposite itinerary starts at wrong half')

def compose_services(files,*,document_paths,stop_specs,vehicle_sources,vehicle_spec,course_template,timetable_template,connection_template,course_template_id,timetable_template_key,plan,speed_type='instructional',bind_connections=False):
    """Generate full Course/TT catalogs and optionally saved reciprocal connections.
    No broad archive migration. Template physics must be explicitly accepted.
    """
    need(type(files)is dict and all(type(k)is str and type(v)is bytes for k,v in files.items()),'Immutable project members required')
    required={'OTDocuments/A.opentrack','OTDocuments/B.opentrack','OTData/example.dest','OTData/example.stations','OTData/example.depot','OTData/example.trains','OTData/example.courses','OTData/example.timetable','cross-document.run'}
    need(set(files)==required,'Exact generated two-document project required')
    need(type(document_paths)is dict and set(document_paths)=={'A','B'},'Exact document paths required')
    suffix='/OTDocuments/A.opentrack';need(document_paths['A'].endswith(suffix),'Explicit A execution path required')
    execution_root=document_paths['A'][:-len(suffix)]
    need(document_paths['B']==execution_root+'/OTDocuments/B.opentrack','Document execution roots differ')
    members={k:b for k,b in files.items()if k!='cross-document.run'}
    catalogs={k:'OTData/example.'+k for k in rb.CATALOG_KEYS}
    expected_run,run_receipt=rb.build_run(members,catalog_paths=catalogs,document_paths=['OTDocuments/A.opentrack','OTDocuments/B.opentrack'],execution_root=execution_root,path_style='windows',train_types=['instructional'])
    need(files['cross-document.run']==expected_run,'Exact one-day generated run paths/window/options required')
    
    need(not c.engine_items(w.load_next_compatible(files['OTData/example.depot'])[0]),'Fresh empty Depot required')
    emptytr=w.load_next_compatible(files['OTData/example.trains'])[0]
    c.train_items(emptytr);need(all(not c.array(emptytr.contents[i].value)for i in (1,2,3)),'Fresh empty Train/Category/Conflict lists required')
    emptyc=w.load_next_compatible(files['OTData/example.courses'])[0]
    c.course_items(emptyc);need(all(not c.array(emptyc.contents[i].value)for i in (1,2,3,4)),'Fresh empty Course auxiliary lists required')
    need(not cf.timetable(w.load_next_compatible(files['OTData/example.timetable'])[0]),'Fresh empty Timetable required')
    need(type(bind_connections)is bool,'Explicit Connection generation flag required')
    need(type(plan)is list and 2<=len(plan)<=1000,'Explicit bounded nonempty one-chain plan required')
    need(set(vehicle_sources)=={'depot','trains'} and all(type(b)is bytes for b in vehicle_sources.values()),'Two immutable vehicle donors required')
    vehicle,vr=vc.generate_vehicle_catalogs(vehicle_sources['depot'],vehicle_sources['trains'],vehicle_spec)
    tr,tv=w.load_next_compatible(vehicle['trains']);dep,dv=w.load_next_compatible(vehicle['depot'])
    trains=c.train_items(tr);engines=c.engine_items(dep)
    need(len(trains)==len(engines)==1,'One Train type and one Engine template in this operational domain')
    train=trains[0];engine=engines[0];train_name=c.text(train.contents[0].value)
    refs=c.array(train.contents[2].values[1]);need(len(refs)==1 and refs[0].contents[1].value==1 and type(refs[0].contents[1].value)is int and not c.array(train.contents[2].values[2]),'Exactly one EngineRef position1/no trailer; position is not quantity')
    length=float(engine.contents[2].values[2]);need(math.isfinite(length) and length>0,'Finite actual Engine length required')
    categories=c.array(tr.contents[1].value);need(len(categories)==1,'Exactly one inherited Category')
    cat=categories[0];c.shape(cat,'OTTrainCategory',19,CATEGORY_LAYOUT)
    need(not(cat.contents[0].values[1]&0x20),'stopAtEveryStation outside explicit endpoint profile')
    minimum=float(cat.contents[20].value);need(math.isfinite(minimum) and minimum>=0 and minimum<86400,'Finite Category turnround within one day required')
    run=files['cross-document.run'];index=str(index_for_course(run,speed_type))
    docs={dn:files['OTDocuments/'+dn+'.opentrack']for dn in ('A','B')}
    project,traces=trace_project(docs,document_paths,files['OTData/example.dest'],files['OTData/example.stations'],speed_index=index,vehicle_speed=engine.contents[7].value)
    validate_stops(project,traces,stop_specs,length)
    full_stops={sign:{**spec,'exit_signal_name':'EXIT:'+sign,'direction':'forward_only','reference_end_id':spec['exit_end_id'],'ordinary_end_ids':[spec['entry_end_id']]}for sign,spec in stop_specs.items()}
    validate_terminal_project(files,document_paths=document_paths,stops=full_stops)
    ct,cv=w.load_next_compatible(course_template);tt,ttv=w.load_next_compatible(timetable_template)
    sts=w.load_next_compatible(files['OTData/example.stations'])[0];dest=w.load_next_compatible(files['OTData/example.dest'])[0]
    need(ct.contents[0].value==17,'Current CourseList marker17 required')
    candidates={c.text(x.contents[0].value):x for x in c.course_items(ct)};need(course_template_id in candidates,'Course donor absent')
    rows=cf.timetable(tt);need(timetable_template_key in rows and not c.array(rows[timetable_template_key].contents[9].value),'Clean Timetable donor required')
    outc=cf.clone(ct)
    for i in (1,2,3):outc.contents[i].value=arr_like(ct.contents[i].value,[])
    outc.contents[4].value=arr_like(ct.contents[4].value,[copy.deepcopy(candidates[course_template_id])])
    outt=dict_like(tt,[(timetable_template_key,copy.deepcopy(rows[timetable_template_key]))]);seen=set();previous=None;commands=[];gaps=[]
    for entry in plan:
        need(type(entry)is dict and set(entry)=={'course_id','train','itinerary','visits'},'Exact Course entry fields required')
        cid=cf.name(entry['course_id']);need(cid not in seen and cid!=course_template_id,'Duplicate/template Course');seen.add(cid)
        need(entry['train']==train_name and entry['itinerary']in traces,'Unknown exact Train/Itinerary')
        trace=traces[entry['itinerary']];visits=entry['visits']
        need(type(visits)is list and len(visits)==2,'Two visits required')
        stops=[]
        for i,(v,actual)in enumerate(zip(visits,trace['visits'])):
            need(type(v)is dict and set(v)=={'station_sign','arrival_s','departure_s','stop'},'Exact arrival/departure visit required')
            need(v['station_sign']==actual['station_sign'],'Visit order differs from reconstructed cross-document path')
            need(type(v['stop'])is bool and v['stop']==(i==1),'Only final terminal visit is stopping in this domain')
            a,d=v['arrival_s'],v['departure_s'];ac,dc=clock(a),clock(d);need(a==d,'Zero dwell per Course endpoint; layover represented between Courses')
            if i:need(a-visits[i-1]['departure_s']+1e-6>=actual['minimum_edge_time_s']-trace['visits'][i-1]['minimum_edge_time_s'],'Travel interval below saved directional speed/length necessary bound')
            stops.append(dict(template_key=timetable_template_key,station_sign=v['station_sign'],arrival=ac,departure=dc,arrival_day_offset=0,departure_day_offset=0,stop_at_station=v['stop'],timing_station=True,interval_reference_course_id=None,interval_offset_s=0,dwell_s=0,mean_delay_s=0,track_id='',distribution_name='',delta_mass_t=0))
        if previous:
            pe,pt=previous;need(pe['visits'][-1]['station_sign']==visits[0]['station_sign'],'Chain station continuity broken')
            need(project.related(tuple(pt['visits'][-1]['end_key']))==tuple(trace['visits'][0]['end_key']),'Reverse departure must use previous endpoint related half')
            gap=visits[0]['departure_s']-pe['visits'][-1]['arrival_s'];need(gap>=minimum,'Overlapping services or layover below actual Category minimum');gaps.append(gap)
            commands.append(nc.Command('turnround_to',pe['course_id'],1,cid))
        fields=dict(speed_type=speed_type,description='Synthetic two-station daily service',comment='Static planned data; native execution unverified',train_number=cid,course_type='',acceleration_percent=100,delayed_acceleration_percent=100,enabled=True,entering_speed_kmh=0,output_offset_m=0,spacing_mode='discrete',additional_reservation_time_s=0,additional_release_time_s=0)
        outc=cf.new_course(outc,tr,dest,template_id=course_template_id,course_id=cid,train=train_name,itineraries=[entry['itinerary']],fields=fields)
        outt=cf.new_timetable(outt,outc,sts,course_id=cid,stops=stops);previous=entry,trace
    outc.contents[4].value=arr_like(outc.contents[4].value,[x for x in c.course_items(outc)if c.text(x.contents[0].value)!=course_template_id])
    outt=dict_like(outt,[(k,v)for k,v in cf.timetable(outt).items()if k!=timetable_template_key])
    services={'courses':w.dump_verified(outc,cv),'timetable':w.dump_verified(outt,ttv)};native=None
    if bind_connections:
        services['timetable'],native=nc.apply({'courses':services['courses'],'timetable':services['timetable'],'trains':vehicle['trains'],'stations':files['OTData/example.stations'],'connection_template':connection_template},commands)
    fresh=cf.timetable(w.load_next_compatible(services['timetable'])[0]);need(len(fresh)==2*len(plan),'Actual emitted TT cardinality mismatch')
    nconnections=0
    for row in fresh.values():
        need(c.text(row.contents[13].value)==c.text(row.contents[14].value)=='HH:MM:SS' and row.contents[15].values[2:]==[0,0],'Actual times were not cleared')
        nconnections+=len(c.array(row.contents[9].value))
    need(nconnections==(2*(len(plan)-1)if bind_connections else 0),'Actual Connection record count mismatch')
    output=dict(files)
    for k,b in {**vehicle,**services}.items():output['OTData/example.'+k]=b
    validate_saved_services(output, plan=plan, minimum_turnround_s=minimum, bind_connections=bind_connections)
    report={'profile':'two-document-single-chain-planned-data-v1','courses':len(plan),'timetable_rows':len(fresh),'connection_records':nconnections,'connection_pairs':len(plan)-1 if bind_connections else 0,'minimum_turnround_s':minimum,'minimum_planned_layover_s':min(gaps),'train_length_m':length,'engine_reference_count':1,'engine_positions':[1],'vehicle_report':vr,'traces':traces,'stop_specs':stop_specs,'plan':copy.deepcopy(plan),'native_connection_receipt':native,'source_sha256':{k:sha(b)for k,b in files.items()},'template_sha256':{'course':sha(course_template),'timetable':sha(timetable_template),'connection':sha(connection_template),**{k:sha(b)for k,b in vehicle_sources.items()}},'output_sha256':{k:sha(b)for k,b in output.items()},'speed_type':speed_type,'ordered_run_train_types':read_train_types(run),'edge_speed_index':index,'window':[0,86400],'native_execution':False,'physical_fleet_circulation_proven':False,'reverse_turnround_runtime_proven':False,'capacity_or_deadlock_proven':False,'actual_stops_observed':False,'native_runtime_ready':False,'physical_calibration':False,'template_physics_accepted':True,'connections_are_saved_configuration_only':True}
    return output,report

def validate_saved_services(files,*,plan,minimum_turnround_s,bind_connections):
    """Read actual output records, require exact own/foreign identities and reciprocity.
    Caller must separately validate original topology and template provenance.
    """
    courses={c.text(x.contents[0].value):x for x in c.course_items(w.load_next_compatible(files['OTData/example.courses'])[0])}
    rows=cf.timetable(w.load_next_compatible(files['OTData/example.timetable'])[0]);expected_ids={e['course_id']for e in plan}
    need(len(expected_ids)==len(plan) and set(courses)==expected_ids,'Exact Course identities required')
    need(set(rows)=={cid+'#'+str(i)for cid in expected_ids for i in range(2)},'Exact TT row keys required')
    expected_connections={k:[]for k in rows}
    if bind_connections:
        for prev,nxt in zip(plan,plan[1:]):
            a,b=prev['course_id'],nxt['course_id'];sign=prev['visits'][-1]['station_sign']
            need(sign==nxt['visits'][0]['station_sign'],'Connection station mismatch')
            for key,owner,target,flags,maximum in ((a+'#1',a,b,2,'HH:MM:SS'),(b+'#0',b,a,0,None)):
                expected_connections[key].append({'course_id':owner,'target_course_id':target,'station_sign':sign,'minimum_wait':nc.wait(minimum_turnround_s),'maximum_wait':maximum,'target_station_sign':sign,'flags':flags,'time_reference_type':0,'dispatching_distance_km':0.})
    for entry in plan:
        cid=entry['course_id'];course=courses[cid]
        need(c.text(course.contents[3].value)==entry['train'] and [c.text(x)for x in c.array(course.contents[2].value)]==[entry['itinerary']],'Saved Course foreign reference mismatch')
        need(course.contents[5].value==1 and course.contents[1].value==0,'Course must be enabled and zero entering speed')
        for i,visit in enumerate(entry['visits']):
            key=cid+'#'+str(i);row=rows[key]
            need(row.contents[3].value==i and row.contents[4].value==1 and c.text(row.contents[1].value)==cid and c.text(row.contents[5].value)==visit['station_sign'],'Saved TT identity/index/station mismatch')
            need(row.contents[10].value==(3 if i else 2),'Saved TT stop/timing flags mismatch')
            need(c.text(row.contents[6].value)==clock(visit['arrival_s']) and c.text(row.contents[7].value)==clock(visit['departure_s']),'Saved planned timestamps mismatch')
            need(row.contents[15].values==[0,0,0,0] and c.text(row.contents[13].value)==c.text(row.contents[14].value)=='HH:MM:SS','Saved day/actual results mismatch')
            need(row.contents[2].value is None and row.contents[11].value==0 and row.contents[17].value==0,'Unexpected interval/mass change')
            need(c.text(row.contents[8].value)==c.text(row.contents[12].value)=='0' and c.text(row.contents[16].value)==c.text(row.contents[18].value)=='','Unexpected dwell/delay/distribution/track')
            need([nc.record(o)for o in c.array(row.contents[9].value)]==expected_connections[key],'Missing/extra/incorrect reciprocal Connection')
    return {'courses':len(courses),'timetable_rows':len(rows),'connection_records':sum(len(x)for x in expected_connections.values()),'exact_records_verified':True}
