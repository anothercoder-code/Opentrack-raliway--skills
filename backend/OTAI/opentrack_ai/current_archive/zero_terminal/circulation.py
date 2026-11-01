"""Fresh terminal stops + actual native turnround records, static only.
A pure-byte preflight/transaction; all inputs are explicit and SHA-bound.
No runtime transfer, braking, capacity, or fleet-count acceptance claim.
"""
import math, hashlib
from opentrack_ai.current_archive import writer as w, catalogs as c, course_factories as cf
from opentrack_ai.current_archive import native_connections as nc
from opentrack_ai.current_archive.stock_operations import CATEGORY_LAYOUT
from .terminal_areas import read_document, AreaError
from .area_operations import station_sequence

class CirculationError(ValueError):pass
def need(ok,msg):
    if not ok:raise CirculationError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def clock(row,slot):
    value=c.text(row.contents[slot].value)
    need(len(value)==8 and value.count(':')==2 and value!='HH:MM:SS','Defined planned HH:MM:SS required')
    h,m,s=map(int,value.split(':'));need(0<=h<24 and 0<=m<60 and 0<=s<60,'Clock range')
    day=row.contents[15].values[0 if slot==6 else 1];need(type(day)is int and day==0,'One-day profile does not day-wrap')
    return day*86400+h*3600+m*60+s

def bind_turnrounds(blobs,*,expected_hashes,area_specs,chains,document_name):
    required={'document','dest','depot','trains','courses','timetable','stations','connection_template','run_template'}
    need(type(blobs)is dict and set(blobs)==required and all(type(b)is bytes for b in blobs.values()),'Exact immutable archive dependency set')
    need(type(expected_hashes)is dict and set(expected_hashes)==required and all(expected_hashes[k]==sha(b) for k,b in blobs.items()),'Source dependency hash mismatch')
    need(type(chains)is list and 1<=len(chains)<=6,'Explicit 1..6 independent line chains required')
    doc,dv,models,byid=read_document(blobs['document'],area_specs)
    roots={k:w.load_next_compatible(v)[0]for k,v in blobs.items()if k not in ('document','run_template')}
    station_catalog=c.station_items(roots['stations']);need(set(station_catalog)=={s['sign']for s in area_specs},'Station catalog exact closure')
    courses={c.text(o.contents[0].value):o for o in c.course_items(roots['courses'])}
    trains={c.text(o.contents[0].value):o for o in c.train_items(roots['trains'])}
    engines={c.text(o.contents[1].value):o for o in c.engine_items(roots['depot'])}
    categories={}
    for cat in c.array(roots['trains'].contents[1].value):
        c.shape(cat,'OTTrainCategory',19,CATEGORY_LAYOUT);key=c.text(cat.contents[1].value)
        need(key not in categories,'Duplicate Category');categories[key]=cat
    rows=cf.timetable(roots['timetable'])
    need(len(rows)==5*len(courses),'Exactly five rows for every Course required')
    
    for row in rows.values():
        need(not c.array(row.contents[9].value),'Fresh-only: existing Connection, duplicate or contradictory reapplication refused')
        need(c.text(row.contents[13].value)==c.text(row.contents[14].value)=='HH:MM:SS' and row.contents[15].values[2:]==[0,0],'Actual simulation times must be unset')
    claimed=set();line_ids=set();used_trains=set();used_itins=set();commands=[];receipts=[];trace_cache={}
    station_map={s['sign']:s for s in area_specs}
    for chain in chains:
        need(type(chain)is dict and set(chain)=={'line_id','train','itinerary','station_sign','course_ids'},'Unknown/missing chain fields')
        line,train,itin,sign=(chain[k]for k in ('line_id','train','itinerary','station_sign'))
        need(all(type(x)is str and x for x in (line,train,itin,sign)),'Named line/Train/Itinerary/Station required')
        
        need(line in ('H1','H2','H3','V1','V2','V3') and itin=='I:terminal:'+line,'Cross-line itinerary rejected')
        number=('H1','H2','H3','V1','V2','V3').index(line)+1
        need(train==f'TRAIN_{number:02}' and sign==f'S{number}_IN','Cross-line Train/Station rejected')
        need(line not in line_ids and train not in used_trains and itin not in used_itins,'Line/Train/Itinerary may have exactly one chain')
        line_ids.add(line);used_trains.add(train);used_itins.add(itin)
        ids=chain['course_ids'];need(type(ids)is list and 2<=len(ids)<=24 and all(type(x)is str for x in ids),'Bounded 2..24 chronological Courses per chain')
        need(len(set(ids))==len(ids) and not claimed.intersection(ids),'Duplicate Course/fork/merge rejected');claimed.update(ids)
        need(train in trains and sign in station_map and station_map[sign]['stop'] is not None,'Missing Train/terminal area')
        tr=trains[train];refs=c.array(tr.contents[2].values[1])
        need(len(refs)==1 and not c.array(tr.contents[2].values[2]) and type(refs[0].contents[1].value)is int and refs[0].contents[1].value==1,'Single Engine reference at integer posInTrain 1/no trailer profile only')
        ename=c.text(refs[0].contents[0].value);need(ename in engines,'Missing Engine')
        engine=engines[ename];length=float(engine.contents[2].values[2]);need(math.isfinite(length) and 0<length<100000,'Finite actual consist length required')
        catname=c.text(tr.contents[3].value);need(catname in categories,'Actual Category absent')
        minimum=float(categories[catname].contents[20].value);need(math.isfinite(minimum) and minimum>=0,'Finite nonnegative minimum turnround required')
        need(not(categories[catname].contents[0].values[1]&0x20),'stopAtEveryStation conflicts with selected occurrence stops')
        stop=station_map[sign]['stop'];need(math.ceil(length)<=stop['length_m'],'Area shorter than actual conservative consist length')
        from opentrack_ai.current_archive.zero_operations.speed_preferences import index_for_course,read_train_types
        need(all(cid in courses for cid in ids),'Missing Course')
        speed_types={c.text(courses[cid].contents[4].value)for cid in ids}
        need(len(speed_types)==1,'Chain Course speed types differ')
        speed_type=next(iter(speed_types));speed_index=str(index_for_course(blobs['run_template'],speed_type))
        trace=station_sequence(blobs['document'],blobs['dest'],itin,document_name,area_specs=area_specs,details=True,speed_index=speed_index,maximum_vehicle_speed_kmh=engine.contents[7].value)
        need([x['station_sign']for x in trace]==[sign,f'S{number}_OUT',sign,f'S{number}_OUT',sign],'Exact actual A-B-A-B-A visit sequence required')
        need(trace[0]['end_id']==trace[-1]['end_id']==stop['exit_end_id'] and trace[-1]['previous_end_id']==stop['entry_end_id'],'Wrong final approach/shared successor endpoint/direction')
        
        for cid in ids:
            need(cid in courses,'Missing Course');course=courses[cid]
            need(c.text(course.contents[3].value)==train and [c.text(x)for x in c.array(course.contents[2].value)]==[itin],'Actual different Train/Itinerary or crossed line')
            rr=[rows.get(cid+'#'+str(i))for i in range(5)];need(all(r is not None for r in rr),'Missing occurrence row')
            previous=-1
            for i,r in enumerate(rr):
                need(c.text(r.contents[1].value)==cid and type(r.contents[3].value)is int and r.contents[3].value==i and r.contents[4].value==4,'Wrong visit/maxIndex')
                need(c.text(r.contents[5].value)==trace[i]['station_sign'],'Wrong occurrence station')
                need(type(r.contents[10].value)is int and r.contents[10].value==(3 if i==4 else 2),'Only terminal index4 stop; earlier A/B pass/timing required')
                arrival,departure=clock(r,6),clock(r,7)
                need(arrival==departure and arrival>previous,'Exact monotone zero-dwell planned timestamps required')
                if i:need(arrival-previous+1e-6>=trace[i]['minimum_edge_time_s']-trace[i-1]['minimum_edge_time_s'],'Timetable leg below actual Edge/vehicle speed lower bound')
                previous=departure
            need(course.contents[5].value==1,'Disabled Course cannot enter circulation chain')
        gaps=[]
        for pred,succ in zip(ids,ids[1:]):
            gap=clock(rows[succ+'#0'],7)-clock(rows[pred+'#4'],6)
            need(gap>=minimum,'Planned connection gap below category minimum; no finite maximum invented')
            gaps.append(gap);commands.append(nc.Command('turnround_to',pred,4,succ))
        receipts.append({'line_id':line,'train':train,'itinerary':itin,'station_sign':sign,'course_ids':ids,'actual_train_length_m':length,'engine_reference_count':1,'engine_positions':[1],'position_is_quantity':False,'minimum_turnround_s':minimum,'minimum_planned_layover_s':min(gaps),'area_length_m':stop['length_m'],'entry_end_id':stop['entry_end_id'],'exit_end_id':stop['exit_end_id'],'visits':trace,'course_speed_type':speed_type,'edge_speed_index':speed_index,'run_train_types':read_train_types(blobs['run_template'])})
    need(claimed==set(courses),'Every Course must belong to exactly one complete supplied chain')
    output,native=nc.apply({k:blobs[k]for k in ('courses','trains','stations','connection_template','timetable')},commands)
    final,version=w.load_next_compatible(output);saved=cf.timetable(final);actual=[]
    for key,row in saved.items():
        for record in c.array(row.contents[9].value):actual.append((key,nc.record(record)))
    expected=[]
    for cmd in commands:
        a,b=cmd.course_id,cmd.target_course_id
        expected.extend([(a+'#4',a,b,2,'HH:MM:SS'),(b+'#0',b,a,0,None)])
    need(len(actual)==len(expected),'Decoded native Connection count mismatch')
    for key,owner,target,flags,maximum in expected:
        found=[rec for k,rec in actual if k==key and rec['course_id']==owner and rec['target_course_id']==target]
        need(len(found)==1,'Reciprocal link absent/duplicate');rec=found[0]
        row=saved[key];cat=next(r for r in receipts if owner in r['course_ids'])
        need(rec['flags']==flags and rec['maximum_wait']==maximum and rec['minimum_wait']==nc.wait(cat['minimum_turnround_s']),'Native flags/minimum/maximum representation mismatch')
        need(rec['station_sign']==rec['target_station_sign']==c.text(row.contents[5].value),'Connection Station binding mismatch')
        need(rec['time_reference_type']==0 and rec['dispatching_distance_km']==0,'Unexpected native Connection defaults')
    
    for row in saved.values():w.set_elements(row.contents[9].value,[])
    original,ov=w.load_next_compatible(blobs['timetable'])
    need(w.dump_verified(final,version)==w.dump_verified(original,ov),'Unselected TT graph changed')
    incoming={cid:[]for cid in claimed};outgoing={cid:[]for cid in claimed};decoded_pairs=[]
    for key,rec in actual:
        if rec['flags']==2:
            a,b=rec['course_id'],rec['target_course_id'];outgoing[a].append(b);incoming[b].append(a);decoded_pairs.append([a,b])
    need(all(len(incoming[cid])<=1 and len(outgoing[cid])<=1 for cid in claimed),'Decoded fork/merge')
    root_ids=sorted(cid for cid in claimed if not incoming[cid] and outgoing[cid]);tail_ids=sorted(cid for cid in claimed if incoming[cid] and not outgoing[cid]);internal_ids=sorted(cid for cid in claimed if incoming[cid] and outgoing[cid])
    need(len(root_ids)==len(tail_ids)==len(chains) and set(root_ids+tail_ids+internal_ids)==claimed,'Decoded chain endpoint domain mismatch')
    count=len(chains);course_count=len(claimed);pairs=len(decoded_pairs)
    return output,{'profile':'fresh-only explicit-terminal-grid-circulation-static-v1','source_sha256':expected_hashes,'timetable_sha256':sha(output),'courses':course_count,'chains':count,'pairs':pairs,'connection_records':len(actual),'roots':len(root_ids),'tails':len(tail_ids),'internal_courses':len(internal_ids),'root_course_ids':root_ids,'tail_course_ids':tail_ids,'internal_course_ids':internal_ids,'decoded_pairs':decoded_pairs,'chains_detail':receipts,'native_connection_receipt':native,'unselected_timetable_graph_restored':True,'tail_policy':'intentional final parking; no day-wrap; no deadlock inference','native_simulation_executed':False,'physical_vehicle_turnround_proven':False}
