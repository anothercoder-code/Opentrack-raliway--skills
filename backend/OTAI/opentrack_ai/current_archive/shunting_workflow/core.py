"""Bounded split/join timetable plans. Pure bytes; never edits running formations."""
import collections, copy, hashlib, math
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive import native_connections as nc
from opentrack_ai.current_archive.course_factories import clock as timetable_clock, timetable
from opentrack_ai.current_archive.consist_workflow import core as consist
from opentrack_ai.current_archive.operating_plan_edit import timetable_time
from opentrack_ai.current_archive.train_factory import validate_template
from opentrack_ai.current_archive.formation_operations import position

class ShuntingError(ValueError): pass
def need(ok, msg):
    if not ok: raise ShuntingError(msg)
def sha(b): return hashlib.sha256(b).hexdigest()
def text(o,i): return None if o.contents[i].value is None else c.text(o.contents[i].value)
def unique(items,slot,label):
    out={}
    for o in items:
        k=text(o,slot);need(k and k not in out,'Missing/duplicate '+label);out[k]=o
    return out

def vehicles(t,engines):
    refs,trs=validate_template(t);out=[]
    need([position(x) for x in refs]==sorted(position(x) for x in refs) and [position(x) for x in trs]==sorted(position(x) for x in trs),'Each vehicle class array must follow increasing position in this API')
    for o in refs:
        key=text(o,0);need(key in engines,'Unresolved Engine')
        engine=engines[key]
        out.append((position(o),'engine',key,{'kind':'engine','name':key,
                    'length_m':engine.contents[2].values[2],'mass_t':engine.contents[2].values[1],
                    'maximum_speed_kmh':engine.contents[7].value}))
    for o in trs:
        # Compare the complete persistent Trailer except position. Native matching
        # can be broader (load/length); this API deliberately refuses that domain.
        x=copy.deepcopy(o);x.contents[3].values[1]=0
        sig=sha(w.dump_verified(x))
        out.append((position(o),'trailer',sig,{'kind':'trailer','name':text(o,1),'signature_sha256':sig,
                    'length_m':o.contents[2].values[2],'mass_t':o.contents[2].values[1],
                    'maximum_speed_kmh':o.contents[4].value}))
    out.sort(key=lambda x:x[0]);need([x[0] for x in out]==list(range(1,len(out)+1)),'Formation positions must be continuous')
    need(any(x[1]=='engine' for x in out),'At least one Engine per initial Course')
    return out

def projected_summary(before, result, length, mass):
    formation = [dict(row[3], position=index) for index, row in enumerate(result, 1)]
    engines = [row['name'] for row in formation if row['kind'] == 'engine']
    need(sum(row['length_m'] for row in formation) == length and sum(row['mass_t'] for row in formation) == mass,
         'Cumulative formation accounting differs from the component records')
    return {**before, 'formation': formation, 'length_m': length, 'cold_mass_t': mass,
            'maximum_speed_kmh': min(row['maximum_speed_kmh'] for row in formation),
            'engine_array_order': engines, 'engine_reference_count': len(engines),
            'trailer_record_count': len(formation) - len(engines), 'projected_prior_composition': True}


def scheduled_times(group, *, allow_day_offsets):
    previous = -1
    times = {}
    for row in group:
        need(row.contents[10].value in (0, 1, 2, 3), 'Invalid TT flags')
        days = row.contents[15].values
        need(days[2:] == [0, 0] and text(row, 13) == text(row, 14) == 'HH:MM:SS',
             'Actual results must not be supplied')
        need(all(type(day) is int and 0 <= day <= 366 for day in days[:2])
             and (allow_day_offsets or days[:2] == [0, 0]),
             'Use nonnegative day offsets in a directed composition plan; standalone timetable-only plans require day 0')
        arrival = timetable_time(row, 'arrival')
        departure = timetable_time(row, 'departure')
        need(arrival is not None and departure is not None and previous <= arrival <= departure,
             'Complete chronological planned times required')
        previous = departure
        times[id(row)] = arrival, departure
    return times


def _saved_event_connection(row, target, flags, station):
    records = [nc.record(item) for item in c.array(row.contents[9].value)]
    matches = [item for item in records if item['target_course_id'] == target]
    need(len(matches) == 1, 'Expected one existing reciprocal formation connection on each reviewed row')
    record, = matches
    need(record['course_id'] == text(row, 1) and record['flags'] == flags
         and record['station_sign'] == record['target_station_sign'] == station
         and record['time_reference_type'] == 0 and record['dispatching_distance_km'] == 0,
         'Saved formation connection does not match the reviewed station, role and location')
    return record


def plan_connections(blobs,spec,*,child_before_main=True,sequential_main=False,verify_existing=False):
    keys={'timetable','courses','trains','stations','depot'}
    if not verify_existing:
        keys.add('connection_template')
    need(type(blobs)is dict and set(blobs)==keys and all(type(v)is bytes for v in blobs.values()),'Six exact immutable sources required')
    need(type(spec)is dict and set(spec)=={'schema','operations','accept_unverified_spatial_and_dynamic_execution'},'Exact plan keys required')
    need(spec['schema']=='split-join-timetable-plan/1' and spec['accept_unverified_spatial_and_dynamic_execution'] is True,'Explicit finite static-plan acceptance required')
    ops=spec['operations'];need(type(ops)is list and 1<=len(ops)<=64,'1..64 composition operations required')
    for op in ops:
        required={'kind','main_course','other_course','station_sign'}
        need(type(op)is dict and required<=set(op)<=required|({'main_visit_index'} if sequential_main else set()),
             'Exact event fields required')
        need(op['kind'] in ('split','join'),'Only split/join supported')
        need(all(type(op[k]) is str and op[k] and op[k] not in ('0','-1')
                 for k in ('main_course','other_course','station_sign')),'Exact named identities required')
        if 'main_visit_index' in op:
            need(type(op['main_visit_index']) is int and op['main_visit_index']>=0,
                 'main_visit_index must be a nonnegative timetable row index')
    if sequential_main:
        mains = {op['main_course'] for op in ops}
        partners = collections.defaultdict(list)
        for op in ops:
            partners[op['other_course']].append(op['kind'])
        need(mains.isdisjoint(partners) and all(kinds in (['split'], ['join'], ['split', 'join'])
                                              for kinds in partners.values()),
             'An event partner outside the main Courses can start at one split and finish at one later join')
    roots={k:w.load_next_compatible(v)[0] for k,v in blobs.items()}
    _,_,_,trains,engines,cats,_=consist.load(blobs['trains'],blobs['depot'])
    courses=unique(c.course_items(roots['courses']),0,'Course')
    stations=c.station_items(roots['stations']);rows=timetable(roots['timetable']);groups={}
    for row in rows.values(): groups.setdefault(text(row,1),[]).append(row)
    for cid,group in groups.items():
        need(cid in courses,'Timetable owner missing Course');group.sort(key=lambda r:r.contents[3].value)
        need([r.contents[3].value for r in group]==list(range(len(group))) and all(r.contents[4].value==len(group)-1 for r in group),'Incomplete TT indices')
    if not verify_existing:
        nc.connection(roots['connection_template'])
    used=set();commands=[];events=[];states={}
    def default(cid):
        train=trains[text(courses[cid],3)];cat=cats[text(train,3)];v=cat.contents[20].value
        need(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v==int(v) and 0<=v<86400,'Finite integral same-day category connection time required')
        return int(v)
    for op in ops:
        kind=op['kind'];main=op['main_course'];other=op['other_course'];sign=op['station_sign']
        need(main!=other and (sequential_main or not {main,other}&used),
             'Each Course participates in only one event in the timetable-only API')
        used.update((main,other));need(main in courses and other in courses and main in groups and other in groups,'Missing Course or TT')
        need(sign in stations,'Unknown Station')
        mg=groups[main];og=groups[other]
        mvis=[r for r in mg if text(r,5)==sign];ovis=[r for r in og if text(r,5)==sign]
        explicit=op.get('main_visit_index')
        if explicit is None:
            need(len(mvis)==1,'Select main_visit_index when an event station has repeated main Course visits')
            mr=mvis[0]
        else:
            need(explicit<len(mg) and text(mg[explicit],5)==sign,
                 'main_visit_index does not match the requested event station')
            mr=mg[explicit]
        need(len(ovis)==1,'Exactly one event-station visit per supplying or detached Course required')
        orr=ovis[0];main_index=mr.contents[3].value
        need(0<main_index<len(mg)-1,'Main Course must continue through interior stop')
        need(orr is (og[0] if kind=='split' else og[-1]),'Other Course must start after split or finish before join')
        need(len(og)>=2,'Other Course needs a real onward/prior visit')
        need(mr.contents[10].value&1 and orr.contents[10].value&1,'Both event rows must stop')
        if not verify_existing:
            need(not any(c.array(r.contents[9].value) for r in mg+og),'Event Courses must have no pre-existing connections')
        need(all(text(r,2) in (None,'','0','-1') and r.contents[11].value==0 for r in mg+og),'Interval timetables unsupported')
        mt = scheduled_times(mg, allow_day_offsets=sequential_main)
        ot = scheduled_times(og, allow_day_offsets=sequential_main)
        ma, md = mt[id(mr)]
        oa, od = ot[id(orr)]
        previous=states.get(main)
        if previous is not None:
            need(previous['index'] < mr.contents[3].value and previous['departure'] < ma,
                 'Repeated main events must be supplied in itinerary order at distinct stops')
        expected_flags = (2, 0) if kind == 'split' else (1, 1)
        if verify_existing:
            records = [_saved_event_connection(row, target, flag, sign)
                       for row, target, flag in ((mr, other, expected_flags[0]),
                                                 (orr, main, expected_flags[1]))]
            wait = max(timetable_clock(record['minimum_wait']) for record in records)
        else:
            wait = max(default(main), default(other))
        if kind=='split':
            need(oa==od and min(od,md)>=ma+wait,'Both planned departures must follow main arrival and the minimum wait')
            need(not child_before_main or md>=od,'This legacy schedule profile requires the child departure before the main departure')
            command=nc.Command('turnround_from',other,0,main,target_visit_index=explicit)
        else:
            need(oa==od and md>=max(ma,oa)+wait,'Join source finishes before receiver departure/minimum wait')
            command=nc.Command('turnround_to',other,len(og)-1,main,target_visit_index=explicit)
        need(text(courses[main],3) in trains and text(courses[other],3) in trains,'Missing Train')
        mtrain=trains[text(courses[main],3)];otrain=trains[text(courses[other],3)]
        mv=vehicles(mtrain,engines) if previous is None else previous['formation']
        ov=vehicles(otrain,engines)
        if kind=='split':
            for child in ov:
                if child[1]=='trailer':
                    for candidate in mv:
                        if candidate[1]=='trailer' and (candidate[3]['length_m'],candidate[3]['mass_t'])==(child[3]['length_m'],child[3]['mass_t']):
                            need(candidate[2]==child[2],'Ambiguous native Trailer length/mass match with different persistent fields')
            cnt=collections.Counter((r[1],r[2]) for r in mv)
            for r in ov:
                key=(r[1],r[2]);need(cnt[key]>0,'Child is not an exact component submultiset');cnt[key]-=1
            need(sum(cnt.values())>0,'Split cannot remove the complete main formation')
            # Native removal chooses the last matching Engine; strict trailers
            # are full equal signatures, so same direction positions are deterministic.
            result=list(mv)
            for r in ov:
                idx=next(i for i in range(len(result)-1,-1,-1) if result[i][1:3]==r[1:3]);result.pop(idx)
            need(any(r[1]=='engine' for r in result),'Residual main must retain Engine in this API')
        else: result=mv+ov
        need(len(result)<=256,'Projected formation exceeds audited 256-record domain')
        ms=consist.summary(mtrain,engines) if previous is None else previous['summary']
        os=consist.summary(otrain,engines)
        length=ms['length_m']+(-1 if kind=='split' else 1)*os['length_m'];mass=ms['cold_mass_t']+(-1 if kind=='split' else 1)*os['cold_mass_t']
        need(0<length<=2**24 and 0<=mass<=2**24,'Projected accounting outside exact integer domain')
        events.append({'kind':kind,'main_course':main,'other_course':other,'station_sign':sign,
                       'main_row':main+'#'+str(main_index),'other_row':other+'#'+str(orr.contents[3].value),
                       'main_visit_index':main_index,
                       'main_previous_station_visits':sum(text(row,5)==sign for row in mg[:main_index]),
                       'minimum_wait_s':wait,'main_arrival_s':ma,'main_departure_s':md,'other_event_s':oa,'initial_main':ms,'initial_other':os,'projected_main_formation':[dict(r[3],accounting_index=i+1) for i,r in enumerate(result)],'projected_main_length_m':length,'projected_main_cold_mass_t':mass,'projection_written_to_Train':False,'native_order_and_positions_verified':False})
        if sequential_main:
            states[main] = {'index': mr.contents[3].value, 'departure': md, 'formation': result,
                            'summary': projected_summary(ms, result, length, mass)}
        commands.append(command)
    if verify_existing:
        return blobs['timetable'], {
            'source_sha256': {k: sha(v) for k, v in blobs.items()},
            'output_sha256': sha(blobs['timetable']), 'events': events,
            'new_connection_records': 0, 'existing_connections_verified': True,
            'sequential_main_events': sequential_main,
        }
    data={k:v for k,v in blobs.items() if k!='depot'}
    output,native_receipt=nc.apply(data,commands)
    fresh=timetable(w.load_next_compatible(output)[0])
    for ev in events:
        expected=(2,0) if ev['kind']=='split' else (1,1)
        for key,flag,target in [(ev['main_row'],expected[0],ev['other_course']),(ev['other_row'],expected[1],ev['main_course'])]:
            cs=c.array(fresh[key].contents[9].value);need(len(cs)==1,'Exactly one new counterpart required');r=nc.record(cs[0])
            need(r['flags']==flag and r['target_course_id']==target and r['station_sign']==ev['station_sign'] and r['target_station_sign']==ev['station_sign'],'Fresh counterpart mismatch')
            need(r['maximum_wait'] in (None,'HH:MM:SS') and r['time_reference_type']==0 and r['dispatching_distance_km']==0,'Unexpected new connection state')
    return output,{'source_sha256':{k:sha(v) for k,v in blobs.items()},'output_sha256':sha(output),'events':events,'new_connection_records':2*len(events),'native_command_receipt':native_receipt,'stock_and_course_catalogs_modified':False,'spatial_compatibility_verified':False,'dynamic_composition_verified':False,'native_runtime_ready':False,'published':False,'sequential_main_events':sequential_main,'scope':'Finite split/join timetable plan with exact absolute clocks and static component accounting; native execution is verified separately.'}
