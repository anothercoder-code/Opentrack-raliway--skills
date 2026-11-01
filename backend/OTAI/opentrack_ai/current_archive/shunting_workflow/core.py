"""Bounded split/join timetable plans. Pure bytes; never edits running formations."""
import collections, copy, hashlib, math
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive import native_connections as nc
from opentrack_ai.current_archive.course_factories import timetable, clock
from opentrack_ai.current_archive.consist_workflow import core as consist
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
        out.append((position(o),'engine',key,{'kind':'engine','name':key}))
    for o in trs:
        
        
        x=copy.deepcopy(o);x.contents[3].values[1]=0
        sig=sha(w.dump_verified(x))
        out.append((position(o),'trailer',sig,{'kind':'trailer','name':text(o,1),'signature_sha256':sig,'length_m':o.contents[2].values[2],'mass_t':o.contents[2].values[1]}))
    out.sort(key=lambda x:x[0]);need([x[0] for x in out]==list(range(1,len(out)+1)),'Formation positions must be continuous')
    need(any(x[1]=='engine' for x in out),'At least one Engine per initial Course')
    return out

def plan_connections(blobs,spec):
    keys={'timetable','courses','trains','stations','connection_template','depot'}
    need(type(blobs)is dict and set(blobs)==keys and all(type(v)is bytes for v in blobs.values()),'Six exact immutable sources required')
    need(type(spec)is dict and set(spec)=={'schema','operations','accept_unverified_spatial_and_dynamic_execution'},'Exact plan keys required')
    need(spec['schema']=='split-join-timetable-plan/1' and spec['accept_unverified_spatial_and_dynamic_execution'] is True,'Explicit finite static-plan acceptance required')
    ops=spec['operations'];need(type(ops)is list and 1<=len(ops)<=64,'1..64 disjoint operations required')
    roots={k:w.load_next_compatible(v)[0] for k,v in blobs.items()}
    _,_,_,trains,engines,cats,_=consist.load(blobs['trains'],blobs['depot'])
    courses=unique(c.course_items(roots['courses']),0,'Course')
    stations=c.station_items(roots['stations']);rows=timetable(roots['timetable']);groups={}
    for row in rows.values(): groups.setdefault(text(row,1),[]).append(row)
    for cid,group in groups.items():
        need(cid in courses,'Timetable owner missing Course');group.sort(key=lambda r:r.contents[3].value)
        need([r.contents[3].value for r in group]==list(range(len(group))) and all(r.contents[4].value==len(group)-1 for r in group),'Incomplete TT indices')
    nc.connection(roots['connection_template']);used=set();commands=[];events=[]
    def schedule(group):
        previous=-1;times={}
        for row in group:
            need(row.contents[10].value in (0,1,2,3),'Invalid TT flags')
            need(row.contents[15].values==[0,0,0,0],'Only same-day planned events supported')
            need(text(row,13)=='HH:MM:SS' and text(row,14)=='HH:MM:SS','Actual results must not be supplied')
            a=clock(text(row,6));d=clock(text(row,7));need(a is not None and d is not None and previous<=a<=d,'Complete chronological planned times required')
            previous=d;times[id(row)]=(a,d)
        return times
    def default(cid):
        train=trains[text(courses[cid],3)];cat=cats[text(train,3)];v=cat.contents[20].value
        need(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) and v==int(v) and 0<=v<86400,'Finite integral same-day category connection time required')
        return int(v)
    for op in ops:
        need(type(op)is dict and set(op)=={'kind','main_course','other_course','station_sign'},'Exact event fields required')
        kind=op['kind'];main=op['main_course'];other=op['other_course'];sign=op['station_sign']
        need(kind in ('split','join'),'Only split/join supported')
        need(all(type(v)is str and v and v not in ('0','-1') for v in (main,other,sign)),'Exact named identities required')
        need(main!=other and not {main,other}&used,'Each Course participates in only one event in this finite API')
        used.update((main,other));need(main in courses and other in courses and main in groups and other in groups,'Missing Course or TT')
        need(sign in stations,'Unknown Station')
        mg=groups[main];og=groups[other]
        mvis=[r for r in mg if text(r,5)==sign];ovis=[r for r in og if text(r,5)==sign]
        need(len(mvis)==len(ovis)==1,'Exactly one event-station visit per Course required')
        mr=mvis[0];orr=ovis[0];need(mr is not mg[0] and mr is not mg[-1],'Main Course must continue through interior stop')
        need(orr is (og[0] if kind=='split' else og[-1]),'Other Course must start after split or finish before join')
        need(len(og)>=2,'Other Course needs a real onward/prior visit')
        need(mr.contents[10].value&1 and orr.contents[10].value&1,'Both event rows must stop')
        need(not any(c.array(r.contents[9].value) for r in mg+og),'Event Courses must have no pre-existing connections')
        need(all(text(r,2) in (None,'','0','-1') and r.contents[11].value==0 for r in mg+og),'Interval timetables unsupported')
        mt=schedule(mg);ot=schedule(og);ma,md=mt[id(mr)];oa,od=ot[id(orr)]
        wait=max(default(main),default(other))
        if kind=='split':
            need(oa==od and od>=ma+wait and md>=od,'Split child creation must follow main arrival/minimum wait, before main departure')
            command=nc.Command('turnround_from',other,0,main)
        else:
            need(oa==od and md>=max(ma,oa)+wait,'Join source finishes before receiver departure/minimum wait')
            command=nc.Command('turnround_to',other,len(og)-1,main)
        need(text(courses[main],3) in trains and text(courses[other],3) in trains,'Missing Train')
        mtrain=trains[text(courses[main],3)];otrain=trains[text(courses[other],3)]
        mv=vehicles(mtrain,engines);ov=vehicles(otrain,engines)
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
            
            
            result=list(mv)
            for r in ov:
                idx=next(i for i in range(len(result)-1,-1,-1) if result[i][1:3]==r[1:3]);result.pop(idx)
            need(any(r[1]=='engine' for r in result),'Residual main must retain Engine in this API')
        else: result=mv+ov
        need(len(result)<=256,'Projected formation exceeds audited 256-record domain')
        ms=consist.summary(mtrain,engines);os=consist.summary(otrain,engines)
        length=ms['length_m']+(-1 if kind=='split' else 1)*os['length_m'];mass=ms['cold_mass_t']+(-1 if kind=='split' else 1)*os['cold_mass_t']
        need(0<length<=2**24 and 0<=mass<=2**24,'Projected accounting outside exact integer domain')
        events.append({'kind':kind,'main_course':main,'other_course':other,'station_sign':sign,'main_row':main+'#'+str(mr.contents[3].value),'other_row':other+'#'+str(orr.contents[3].value),'minimum_wait_s':wait,'main_arrival_s':ma,'main_departure_s':md,'other_event_s':oa,'initial_main':ms,'initial_other':os,'projected_main_formation':[dict(r[3],accounting_index=i+1) for i,r in enumerate(result)],'projected_main_length_m':length,'projected_main_cold_mass_t':mass,'projection_written_to_Train':False,'native_order_and_positions_verified':False})
        commands.append(command)
    data={k:v for k,v in blobs.items() if k!='depot'}
    output,native_receipt=nc.apply(data,commands)
    fresh=timetable(w.load_next_compatible(output)[0])
    for ev in events:
        expected=(2,0) if ev['kind']=='split' else (1,1)
        for key,flag,target in [(ev['main_row'],expected[0],ev['other_course']),(ev['other_row'],expected[1],ev['main_course'])]:
            cs=c.array(fresh[key].contents[9].value);need(len(cs)==1,'Exactly one new counterpart required');r=nc.record(cs[0])
            need(r['flags']==flag and r['target_course_id']==target and r['station_sign']==ev['station_sign'] and r['target_station_sign']==ev['station_sign'],'Fresh counterpart mismatch')
            need(r['maximum_wait'] in (None,'HH:MM:SS') and r['time_reference_type']==0 and r['dispatching_distance_km']==0,'Unexpected new connection state')
    return output,{'source_sha256':{k:sha(v) for k,v in blobs.items()},'output_sha256':sha(output),'events':events,'new_connection_records':2*len(events),'native_command_receipt':native_receipt,'stock_and_course_catalogs_modified':False,'spatial_compatibility_verified':False,'dynamic_composition_verified':False,'native_runtime_ready':False,'published':False,'scope':'Finite same-day split/join timetable plan with exact static component accounting; not a spatial shunting or running train execution.'}
