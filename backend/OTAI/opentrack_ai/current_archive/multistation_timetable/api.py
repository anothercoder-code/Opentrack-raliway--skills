"""Finite multi-station, up-to-seven-day chain plans. Pure immutable bytes only."""
import copy, hashlib, math
from .topology import generate_network_project
from opentrack_ai.current_archive import writer as w, catalogs as c, course_factories as cf, native_connections as nc
from opentrack_ai.current_archive.multi_document import core as cd
from opentrack_ai.current_archive.stock_operations import CATEGORY_LAYOUT
from opentrack_ai.current_archive.zero_operations import vehicle_catalogs as vc, run_bundle as rb
SOURCE_KEYS={'header_document','shapes','depot_template','trains_template','courses_template','timetable_template','connection_template'}
SPEC_KEYS={'schema','network','vehicle','course_template_id','timetable_template_key','plan','bind_connections','window_days'}
def need(ok,msg):
    if not ok: raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def arr(old,vals):
    o=cf.clone(old);w.set_elements(o,vals);return o
def dictionary(old,pairs):
    cf.dictionary(old);o=cf.clone(old);o.contents=[w.TypedValue(b'i',len(pairs))]
    for k,v in pairs:o.contents += [w.TypedValue(b'@',cf.string(old,k)),w.TypedValue(b'@',v)]
    return o
def clock(n):
    need(type(n)is int and 0<=n<7*86400,'Integer absolute time in days0..6 required')
    n%=86400;return f'{n//3600:02}:{n//60%60:02}:{n%60:02}'
def generate_from_spec(sources,spec):
    need(type(sources)is dict and set(sources)==SOURCE_KEYS and all(type(b)is bytes and b for b in sources.values()),'Seven exact immutable donors required')
    need(type(spec)is dict and set(spec)==SPEC_KEYS and spec['schema']=='multi-station-timetable/1','Exact versioned specification required')
    days=spec['window_days'];need(type(days)is int and 1<=days<=7,'Window1..7 days required')
    need(type(spec['bind_connections'])is bool,'Explicit connection flag required')
    plan=spec['plan'];need(type(plan)is list and 1<=len(plan)<=1000,'Bounded one-chain plan required')
    donors={'header':sources['header_document'],'shapes':sources['shapes'],**{k:sources[k+'_template']for k in ('depot','trains','courses','timetable')}}
    files,top=generate_network_project(donors,expected_hashes={k:sha(v)for k,v in donors.items()},spec=spec['network'])
    paths=top['document_paths'];docs={k:files['OTDocuments/'+k+'.opentrack']for k in paths}
    project=cd.Project(docs,document_paths=paths,expected_hashes={k:sha(v)for k,v in docs.items()},complete_document_set=True)
    project.check_dest_catalog(files['OTData/chain.dest'])
    vehicle,vr=vc.generate_vehicle_catalogs(donors['depot'],donors['trains'],spec['vehicle'])
    tr,_=w.load_next_compatible(vehicle['trains']);dep,_=w.load_next_compatible(vehicle['depot'])
    trains=c.train_items(tr);engines=c.engine_items(dep);need(len(trains)==len(engines)==1,'One Engine type/Train definition only')
    train=trains[0];engine=engines[0];train_name=c.text(train.contents[0].value)
    refs=c.array(train.contents[2].values[1]);need(len(refs)==1 and refs[0].contents[1].value==1 and not c.array(train.contents[2].values[2]),'Single EngineRef position1, no Trailer')
    length=float(engine.contents[2].values[2]);speed=engine.contents[7].value
    need(math.isfinite(length) and 0<length<=500 and type(speed)is int and 0<speed<=1000,'Positive vehicle length<=500 and bounded speed required')
    cats=c.array(tr.contents[1].value);need(len(cats)==1,'One Category required');cat=cats[0];c.shape(cat,'OTTrainCategory',19,CATEGORY_LAYOUT)
    need(not(cat.contents[0].values[1]&0x20),'Implicit stop-at-all-stations unsupported')
    minimum=float(cat.contents[20].value);need(math.isfinite(minimum) and 0<=minimum<86400,'Bounded Category layover required')
    stations=w.load_next_compatible(files['OTData/chain.stations'])[0];station_items=c.station_items(stations)
    signs={}
    for dn,models in project.models.items():
        sms=[m for m in models if w.kind(m)=='OTStationModel'];need(len(sms)==1,'One StationModel per Doc')
        sign=c.text(sms[0].contents[7].value);need(sign not in signs and sign in station_items,'Unique globally bound station sign');signs[sign]=dn
    need(set(signs)==set(station_items),'Exact station closure')
    traces={}
    for dest in project.dests:
        name=c.text(dest.contents[1].value);nodes,_=project.dest_view(dest);visits=[];dist=lower=0.;edge_keys=[]
        for i,key in enumerate(nodes):
            e=project.model(key)
            if i:
                ek=project.edge_between(nodes[i-1],key);edge=project.model(ek);half=project.model(project.actual_related(nodes[i-1]));meters=edge.contents[9].values[1]
                need(type(meters)is int and meters>0,'Positive Edge length')
                sp=cf.dictionary(edge.contents[16].value)['0'];c.shape(sp,'OTSpeed',0,['@','i','i','i'])
                v=sp.contents[1 if edge.contents[7].value is half else 2].value;need(type(v)is int and 0<v<=1000,'Positive directional speed')
                dist+=meters;lower+=meters/(min(v,speed)/3.6);edge_keys.append(list(ek))
            if e.contents[20].value==2:
                sm=e.contents[12].value;need(sm is not None,'Unbound station reference');sign=c.text(sm.contents[7].value)
                need(signs.get(sign)==key[0],'Cross-owned station')
                visits.append({'station_sign':sign,'end_key':list(key),'previous_end_key':None if i==0 else list(nodes[i-1]),'distance_m':dist,'minimum_edge_time_s':lower})
        need(2<=len(visits)<=12 and visits[0]['end_key']==list(nodes[0]) and visits[-1]['end_key']==list(nodes[-1]),'Endpoint station references required')
        traces[name]={'visits':visits,'nodes':[list(k)for k in nodes],'edges':edge_keys,'length_m':dist,'minimum_edge_time_s':lower}
    ct,cv=w.load_next_compatible(sources['courses_template']);tt,tv=w.load_next_compatible(sources['timetable_template'])
    need(ct.contents[0].value==17,'Current CourseList required')
    cid0=spec['course_template_id'];key0=spec['timetable_template_key'];templates={c.text(x.contents[0].value):x for x in c.course_items(ct)};rows0=cf.timetable(tt)
    need(cid0 in templates and key0 in rows0 and not c.array(rows0[key0].contents[9].value),'Clean exact donors required')
    outc=cf.clone(ct)
    for i in (1,2,3):outc.contents[i].value=arr(ct.contents[i].value,[])
    outc.contents[4].value=arr(ct.contents[4].value,[copy.deepcopy(templates[cid0])]);outt=dictionary(tt,[(key0,copy.deepcopy(rows0[key0]))])
    destroot=w.load_next_compatible(files['OTData/chain.dest'])[0];seen=set();previous=None;commands=[];links=[]
    for entry in plan:
        need(type(entry)is dict and set(entry)=={'course_id','train','itinerary','visits'},'Exact Course plan keys')
        cid=cf.name(entry['course_id']);need(cid!=cid0 and cid not in seen,'Duplicate/template Course');seen.add(cid)
        need(entry['train']==train_name and entry['itinerary']in traces,'Unknown Train/Itinerary')
        trace=traces[entry['itinerary']];visits=entry['visits'];need(type(visits)is list and len(visits)==len(trace['visits']),'Visit occurrence count differs from actual path')
        stop_specs=[]
        for i,(v,actual)in enumerate(zip(visits,trace['visits'])):
            need(type(v)is dict and set(v)=={'station_sign','arrival_s','departure_s','stop'},'Exact visit keys')
            need(v['station_sign']==actual['station_sign'],'Station occurrence order differs from actual path')
            a,d=v['arrival_s'],v['departure_s'];ac,dc=clock(a),clock(d);need(a<=d<days*86400,'Invalid/window-exceeding absolute times')
            need(type(v['stop'])is bool,'Strict boolean stop')
            if i==0:need(a==d and not v['stop'],'First arrival equals departure, no origin dwell')
            if i==len(visits)-1:need(v['stop'] and a==d,'Final stopping endpoint, no postarrival dwell')
            if not v['stop']:need(a==d,'Pass-through cannot dwell')
            if i:
                need(a-visits[i-1]['departure_s']+1e-6>=actual['minimum_edge_time_s']-trace['visits'][i-1]['minimum_edge_time_s'],'Travel below actual Edge necessary bound')
            if v['stop']:
                end=tuple(actual['end_key']);before=tuple(actual['previous_end_key']);ee=project.model(before);xx=project.model(end);edge=project.model(project.edge_between(before,end))
                need(w.kind(ee)==w.kind(xx)=='OTEndModel' and ee.contents[20].value==1 and xx.contents[20].value==2,'Stop requires actual ordinary-to-reference approach')
                need(ee.contents[12].value is xx.contents[12].value and edge.contents[9].values[1]>=math.ceil(length),'Station area identity/length mismatch')
                need(xx.contents[11].value is not None,'Stop reference requires signal')
            stop_specs.append(dict(template_key=key0,station_sign=v['station_sign'],arrival=ac,departure=dc,arrival_day_offset=a//86400,departure_day_offset=d//86400,stop_at_station=v['stop'],timing_station=True,interval_reference_course_id=None,interval_offset_s=0,dwell_s=d-a,mean_delay_s=0,track_id='',distribution_name='',delta_mass_t=0))
        if previous:
            pe,pt=previous;gap=visits[0]['arrival_s']-pe['visits'][-1]['arrival_s']
            need(gap>=minimum,'Overlap or Category layover violation')
            need(pe['visits'][-1]['station_sign']==visits[0]['station_sign'],'Chain station discontinuity')
            need(project.related(tuple(pt['visits'][-1]['end_key']))==tuple(trace['visits'][0]['end_key']),'Turnround endpoint is not related departure half')
            commands.append(nc.Command('turnround_to',pe['course_id'],len(pe['visits'])-1,cid));links.append({'from':pe['course_id'],'to':cid,'gap_s':gap,'station_sign':visits[0]['station_sign']})
        fields=dict(speed_type='instructional',description='Synthetic multistation planned service',comment='Static data; native execution unverified',train_number=cid,course_type='',acceleration_percent=100,delayed_acceleration_percent=100,enabled=True,entering_speed_kmh=0,output_offset_m=0,spacing_mode='discrete',additional_reservation_time_s=0,additional_release_time_s=0)
        outc=cf.new_course(outc,tr,destroot,template_id=cid0,course_id=cid,train=train_name,itineraries=[entry['itinerary']],fields=fields)
        outt=cf.new_timetable(outt,outc,stations,course_id=cid,stops=stop_specs);previous=(entry,trace)
    outc.contents[4].value=arr(outc.contents[4].value,[x for x in c.course_items(outc)if c.text(x.contents[0].value)!=cid0]);outt=dictionary(outt,[(k,v)for k,v in cf.timetable(outt).items()if k!=key0])
    services={'courses':w.dump_verified(outc,cv),'timetable':w.dump_verified(outt,tv)}
    if spec['bind_connections'] and commands:
        services['timetable'],_=nc.apply({'courses':services['courses'],'timetable':services['timetable'],'trains':vehicle['trains'],'stations':files['OTData/chain.stations'],'connection_template':sources['connection_template']},commands)
    output=dict(files)
    for k,b in {**vehicle,**services}.items():output['OTData/chain.'+k]=b
    fresh=cf.timetable(w.load_next_compatible(services['timetable'])[0]);need(len(fresh)==sum(len(p['visits'])for p in plan),'TT count mismatch')
    expected={k:[]for k in fresh}
    if spec['bind_connections']:
        for pe,ne in zip(plan,plan[1:]):
            a,b=pe['course_id'],ne['course_id'];sign=pe['visits'][-1]['station_sign']
            for key,owner,target,flags,maximum in ((a+'#'+str(len(pe['visits'])-1),a,b,2,'HH:MM:SS'),(b+'#0',b,a,0,None)):
                expected[key].append({'course_id':owner,'target_course_id':target,'station_sign':sign,'minimum_wait':nc.wait(minimum),'maximum_wait':maximum,'target_station_sign':sign,'flags':flags,'time_reference_type':0,'dispatching_distance_km':0.})
    saved_courses={c.text(x.contents[0].value):x for x in c.course_items(w.load_next_compatible(services['courses'])[0])}
    need(set(saved_courses)==seen,'Exact Course set mismatch')
    total=0
    for e in plan:
        co=saved_courses[e['course_id']]
        need(c.text(co.contents[3].value)==e['train'] and [c.text(x)for x in c.array(co.contents[2].value)]==[e['itinerary']],'Saved Course refs mismatch')
        for i,v in enumerate(e['visits']):
            row=fresh[e['course_id']+'#'+str(i)]
            need(c.text(row.contents[1].value)==e['course_id'] and c.text(row.contents[5].value)==v['station_sign'] and row.contents[3].value==i,'Saved identity/order mismatch')
            need(c.text(row.contents[6].value)==clock(v['arrival_s']) and c.text(row.contents[7].value)==clock(v['departure_s']),'Saved clocks mismatch')
            need(row.contents[15].values==[v['arrival_s']//86400,v['departure_s']//86400,0,0],'Day/actual offsets mismatch')
            need(c.text(row.contents[13].value)==c.text(row.contents[14].value)=='HH:MM:SS','Actual times not empty')
            need([nc.record(x)for x in c.array(row.contents[9].value)]==expected[e['course_id']+'#'+str(i)],'Exact reciprocal connections mismatch')
            need(float(c.text(row.contents[8].value))==v['departure_s']-v['arrival_s'],'Saved minimum dwell differs from explicit plan')
            need(row.contents[10].value==2+int(v['stop']),'Stop flags mismatch');total+=len(c.array(row.contents[9].value))
    need(total==(2*len(links)if spec['bind_connections']else 0),'Connection count mismatch')
    members={k:v for k,v in output.items()if k!='chain.run'}
    output['chain.run'],rr=rb.build_run(members,catalog_paths={k:'OTData/chain.'+k for k in rb.CATALOG_KEYS},document_paths=['OTDocuments/'+k+'.opentrack'for k in paths],execution_root=spec['network']['execution_root'],path_style='windows',train_types=['instructional'],stop_day=days)
    receipt={'schema':'multistation-timetable-result/1','profile':'2..12-chain-stations-single-engine-up-to-seven-days','courses':len(plan),'timetable_rows':len(fresh),'connection_pairs':len(links)if spec['bind_connections']else 0,'connection_records':total,'plan':copy.deepcopy(plan),'traces':traces,'turnround_links':links,'minimum_turnround_s':minimum,'train_length_m':length,'topology':top,'vehicle':vr,'run':rr,'source_sha256':{k:sha(v)for k,v in sources.items()},'files':{k:{'sha256':sha(v),'bytes':len(v)}for k,v in output.items()},'preview_only':True,'saved':False,'native_runtime_ready':False,'native_execution':False,'capacity_or_deadlock_proven':False,'physical_calibration':False,'scope':'Ordered one-chain plans; adjacent intervals conservatively serial; branch/merge circulations, cyclic timetables and repeated spatial station visits are not implemented'}
    return output,receipt
