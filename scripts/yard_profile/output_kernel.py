"""Portable output kernel from the frozen actual native-cohort verifier.

No simulation, launch or GUI inspection. Body clearance is conditional on an
explicit coordinate-error envelope; native block exclusions are separate. The
0.5m single-step reconciliation is not a continuous global error bound.
"""
from __future__ import annotations
from pathlib import Path
import bisect,copy,json,math,re
from .output_io import ReviewError,need,clock,header_value,parse_vt

COURSES={f'GD{d}{i}01' for i in range(1,5) for d in ('D','U')}|{'GDD102'}
BOUNDARIES=[0,1250,2400,3750,4250,5000,6250,7400,8750,9250,10000]
BLOCKS=[(BOUNDARIES[i],BOUNDARIES[i+1]) for i in (0,1,2,3,5,6,7,8)]
POSITION_RECONCILIATION_M=.5
DISTANCE_EXPORT_HALF_UNIT_M=.05
TIME_EXPORT_HALF_UNIT_S=.005

def hms(n):
    n=int(n); return f'{n//3600:02}:{n//60%60:02}:{n%60:02}'



def native_end_time(clock_text,numeric_text,fine_time):
    """Check two stock quantizations against exported fine absolute seconds.

    secondToTimeString:0x68f324 uses x87 RC=11 (truncate toward zero), while
    CourseStatistics0x5f1688 writes the numeric seconds using printf %.0f.
    fine_time itself has %.2f quantization; do not turn a rounded Statistics
    integer into a high-resolution physical timestamp.
    """
    displayed=clock(clock_text);numeric=float(numeric_text)
    need(math.isfinite(fine_time) and math.isfinite(numeric) and numeric.is_integer(),
         'Nonfinite/nonintegral native end time')
    need(-TIME_EXPORT_HALF_UNIT_S-.00001<=fine_time-displayed<1+TIME_EXPORT_HALF_UNIT_S+.00001
         and abs(numeric-fine_time)<=.5+TIME_EXPORT_HALF_UNIT_S+.00001,
         'Course end clock/numeric/VT disagree')
    return fine_time



def terminal_log_position(position_m):
    need(math.isfinite(position_m) and
         10000-POSITION_RECONCILIATION_M-DISTANCE_EXPORT_HALF_UNIT_M<=position_m<=10000+DISTANCE_EXPORT_HALF_UNIT_M,
         'Actual terminal log position outside native numerical reconciliation band')
    return {'reference_m':10000,'actual_integrated_log_m':position_m,
            'reference_minus_log_m':10000-position_m,
            'native_position_reconciliation_m':POSITION_RECONCILIATION_M,
            'distance_export_half_unit_m':DISTANCE_EXPORT_HALF_UNIT_M,
            'exact_reference_position_inferred':False,
            'native_station_arrival_and_stop_evidence_required':True}



def semantic_graph(root,w):
    """Preserve object aliases/field types/order; ignore only wire token sharing.

    Objective-C class metadata identifies a class by its full name/version
    hierarchy. Repeated identical class descriptors/encoding tokens are wire
    representation details, not separate business object instances.
    """
    seen={}
    def chain(cl):
        out=[];visited=set()
        while cl is not None:
            need(id(cl) not in visited,'Cyclic class metadata');visited.add(id(cl))
            out.append((cl.name.hex(),cl.version));cl=cl.superclass
        return out
    def visit(v):
        if isinstance(v,w.GenericArchivedObject):
            if id(v) in seen:return {'ref':seen[id(v)]}
            idx=len(seen);seen[id(v)]=idx
            return {'id':idx,'class':chain(v.clazz),'groups':[[[e.hex() for e in g.encodings],[visit(x) for x in g.values]] for g in v.contents]}
        if isinstance(v,w.Class):return {'class_value':chain(v)}
        if isinstance(v,w.Array):return {'array':visit(v.elements)}
        if isinstance(v,w.GenericStruct):return {'struct_name':visit(v.name),'fields':[visit(x) for x in v.fields]}
        if isinstance(v,w.CString):return {'cstring':v.token.data.hex()}
        if isinstance(v,w.SharedString):return {'shared_string_value':v.data.hex()}
        if isinstance(v,bytes):return {'bytes':v.hex()}
        if isinstance(v,float):return {'float':float(v).hex()}
        if v is None or type(v) in (int,bool,str):return v
        if type(v) in (tuple,list):return [visit(x) for x in v]
        raise ReviewError('Unsupported graph value in exact semantic comparison: '+type(v).__name__)
    return visit(root)



def first_difference(a,b,path='$'):
    if type(a)!=type(b):return (path,str(a)[:120],str(b)[:120])
    if isinstance(a,dict):
        if set(a)!=set(b):return (path,sorted(a),sorted(b))
        for k in a:
            d=first_difference(a[k],b[k],path+'.'+str(k))
            if d:return d
    elif isinstance(a,list):
        if len(a)!=len(b):return (path+'.length',len(a),len(b))
        for i,(x,y) in enumerate(zip(a,b)):
            d=first_difference(x,y,path+'['+str(i)+']')
            if d:return d
    elif a!=b:return (path,str(a)[:120],str(b)[:120])
    return None



def audit_native_timetable_actuals(before,after,plans,output,names,texts=None):
    """Bounded27-entry native exit writeback; plan and mutable aliases exact.

    Native NSCoder may reorder NSMutableDictionary and intern NSStrings. Only
    actualArr/Dep strings and their two day offsets may differ in each record.
    This recipe has no connections: all27 connection arrays must stay distinct
    and empty; no generic alias normalization of mutable business data occurs.
    """
    from opentrack_ai.current_archive import writer as w,catalogs as c
    def parse(raw):
        root,version=w.load_next_compatible(raw)
        need(w.kind(root)=='NSMutableDictionary' and root.clazz.version==0 and root.contents[0].encodings==[b'i'] and root.contents[0].value==27 and len(root.contents)==55,'Exact27-entry native Timetable dictionary required')
        rows={};arrays=[]
        for i in range(27):
            key=c.text(root.contents[1+2*i].value);row=root.contents[2+2*i].value
            c.shape(row,'OTTimetable',9,['i','@','@','i','i','@','@','@','@','@','i','f','@','@','@','iiii','@','f','@'])
            need(row.contents[0].value==17 and key==c.text(row.contents[1].value)+'#'+str(row.contents[3].value) and key not in rows,'Native Timetable key/identity differs')
            conn=row.contents[9].value;need(c.array(conn)==[],'This exact Timetable writeback requires no connection entries');arrays.append(id(conn));rows[key]=row
        need(len(set(arrays))==27 and len({id(x) for x in rows.values()})==27,'Native Timetable mutable record/connection aliases changed')
        return rows,version
    old,ov=parse(before);new,nv=parse(after);need(ov==nv and set(old)==set(new),'Timetable identities/version changed')
    expected={p['course_id']:p for p in plans};reviews=[]
    for key,row in new.items():
        prior=old[key];cid=c.text(row.contents[1].value);idx=row.contents[3].value
        need(cid in expected and idx in (0,1,2),'Unexpected native Timetable identity')
        plan=expected[cid];sign=plan['visits'][idx]['station_sign'];need(c.text(row.contents[5].value)==sign,'Timetable actual station changed')
        from .output_io import stable_file
        tt_name='OT_'+cid+'.tt';vt_name='OT_'+cid+'.vt'
        text=texts[tt_name] if texts is not None else stable_file(output/tt_name)[0].decode('utf-8-sig')
        part=text.split('Actual Timetable vs. Planned Timetable',1)[0]
        actual=[[s.strip() for s in line.split('\t')] for line in part.splitlines() if '\t' in line and not line.startswith('//')]
        need(len(actual)==3 and actual[idx][0]==names[sign] and actual[idx][1]==('Dep.','Pass','Arr.')[idx],'Actual native Timetable output identity differs')
        time_text=actual[idx][2];sec=clock(time_text);numeric=int(actual[idx][3]);need(numeric in (sec,sec+1),'Native actual Timetable clock/numeric quantization differs')
        arr=c.text(row.contents[13].value);dep=c.text(row.contents[14].value)
        need((arr,dep)==((time_text,'HH:MM:SS') if idx==2 else ('HH:MM:SS',time_text)),'Saved actual time is not the actual native output event')
        need(row.contents[15].values[2:]==[0,0],'Actual native Timetable day offset differs from same-day outputs')
        vt=parse_vt(texts[vt_name] if texts is not None else stable_file(output/vt_name)[0].decode('utf-8-sig'))
        close=[(t,v) for t,v in vt if sec-.205<=t<sec+1.205 and (idx!=2 or v==0)]
        need(close,'No actual physical VT neighborhood for saved Timetable event')
        a,b=copy.deepcopy(prior),copy.deepcopy(row)
        for g in (13,14):b.contents[g]=copy.deepcopy(a.contents[g])
        b.contents[15].values[2:]=a.contents[15].values[2:]
        
        for rec in (a,b):
            for g in rec.contents:
                for j,x in enumerate(g.values):
                    if isinstance(x,w.GenericArchivedObject) and w.kind(x)=='NSString':c.text(x);g.values[j]=copy.deepcopy(x)
        need(semantic_graph(a,w)==semantic_graph(b,w),'Timetable planned/business field or mutable alias changed: '+key)
        reviews.append({'key':key,'station':sign,'actual_arrival':arr,'actual_departure':dep,'actual_day_offsets':row.contents[15].values[2:],'output_time':time_text,'output_numeric_s':numeric,'VT_event_neighborhood_s':[close[0][0],close[-1][0]],'planned_fields_and_mutable_aliases_preserved':True})
    return {'passed':True,'records':reviews,'record_count':27,'allowed_fields':['actualArrTime','actualDepTime','actualArrTimeDayOffset','actualDepTimeDayOffset'],'dictionary_key_order_ignored':True,'only_immutable_NSString_sharing_ignored':True,'mutable_record_and_connection_arrays_distinct':True,'VT_exact_interpolated_station_timestamp_inferred':False}



def audit_native_saved_document(actual,reference):
    """Explicit reviewed projection of observed native Save drawing changes.

    This is not the default input binding. It is used only with a separate
    SHA-bound reviewed-input manifest. Operational objects/aliases stay exact.
    """
    from opentrack_ai.current_archive import writer as w,catalogs as c
    from . import text as y
    a,av=w.load_next_compatible(actual);r,rv=w.load_next_compatible(reference)
    need(av==rv and w.kind(a)==w.kind(r)=='OTDocument' and a.clazz.version==r.clazz.version==4,'Exact Document4 native save projection required')
    am={x.contents[0].value:x for x in c.array(a.contents[2].value)};rm={x.contents[0].value:x for x in c.array(r.contents[2].value)}
    need(set(am)==set(rm) and len(am)==len(c.array(a.contents[2].value)),'Saved model identities changed')
    frames={}
    for i in (8,9,10):
        need(a.contents[i].encodings==r.contents[i].encodings and len(a.contents[i].values)==4 and all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in a.contents[i].values),'Unknown native Document frame')
        if a.contents[i].values!=r.contents[i].values:frames[str(i)]={'candidate':list(r.contents[i].values),'saved':list(a.contents[i].values)}
        a.contents[i]=copy.deepcopy(r.contents[i])
    labels=[]
    for mid,x in am.items():
        z=rm[mid];need(w.kind(x)==w.kind(z),'Saved model class changed')
        if w.kind(x)!='OTLabelModel':continue
        raw=y._data(x.contents[7].value);old=y._data(z.contents[7].value)
        need(raw==old and raw.startswith(y.RTF_PREFIX) and raw.endswith(y.RTF_SUFFIX),'Saved label text/font changed')
        text=raw[len(y.RTF_PREFIX):-len(y.RTF_SUFFIX)].decode('ascii')
        before=list(map(float,z.contents[8].values));after=list(map(float,x.contents[8].values))
        need(after[:2]==before[:2],'Saved Label anchor moved')
        y._inspect(x,y._entry({'key':'native-save-'+str(mid),'text':text,'rect':after}),mid)
        y._inspect(z,y._entry({'key':'candidate-'+str(mid),'text':text,'rect':before}),mid)
        labels.append({'id':mid,'text':text,'candidate_rect':before,'saved_rect':after,'left_top_anchor_unchanged':True,'actual_center_derived_from_rect':True})
        for i in (2,3,8):x.contents[i]=copy.deepcopy(z.contents[i])
    need(len(labels)==15,'Exactly15 known standalone drawing labels required')
    
    
    
    normalized={}
    for label,root in [('saved',a),('candidate',r)]:
        counts={'empty_RSP_text_fields':0,'label_colour_fields':0}
        for o in list(w.objects(root)):
            kind=w.kind(o)
            slots=(3,7) if kind=='OTRoute' else (3,) if kind in ('OTPath','OTDest') else (24,) if kind=='OTConnModel' else (19,20) if kind=='OTDocument' else ()
            for i in slots:
                s=o.contents[i].value
                if s is not None and w.kind(s)=='NSString' and len(s.contents)==1 and s.contents[0].encodings==[b'+'] and s.contents[0].value==b'':
                    o.contents[i].value=copy.deepcopy(s);counts['empty_RSP_text_fields']+=1
            if kind=='OTLabelModel':
                for i,white in ((11,0),(12,1)):
                    y._color(o.contents[i].value,white);o.contents[i].value=copy.deepcopy(o.contents[i].value);counts['label_colour_fields']+=1
        normalized[label]=counts
    need(normalized['saved']==normalized['candidate'],'Known immutable drawing/text role inventory changed')
    difference=first_difference(semantic_graph(a,w),semantic_graph(r,w))
    need(difference is None,'Saved document changed non-drawing fields, operational object aliases, Label text/style or unreviewed fields: '+str(difference))
    return {'passed':True,'operational_graph_and_aliases_unchanged':True,'Document_frame_changes':frames,'labels':labels,'exact_known_immutable_role_normalization':normalized,'scope':'Only native saved frame/view groups8/9/10; anchored15Label fit with exact RTF/style; exact empty RSP description/no-overlap, Conn.dragFileName, Document.importFileName/importSource NSString sharing; Label black/white immutable colour sharing. Connector blockTopo/blockEnd and all railway field values/aliases remain exact.'}



def normalize_trace(tr,base):
    need(tr['distance_m']==10000 and tr['ordered_route_count']==10 and tr['nodes']==base['nodes'],'Static actual topology/service trace must verify10km/10Routes')
    need([m['distance_m'] for m in tr['mains']]==BOUNDARIES,'Yard Home or block distance differs')
    routes=[]
    for i,r in enumerate(tr['native_route_resources']):
        need(r['name']==base['ordered_routes'][i]['name'],'Service/Topology Route reference differs')
        routes.append({**r,'route_name':r['name'],'start_m':BOUNDARIES[i],'end_m':BOUNDARIES[i+1]})
    segments=[];position=0.
    for edge in tr['edges']:
        length=edge['length_m'];need(type(length)is int and length>0,'Positive actual Edge length required')
        segments.append({**edge,'edge_key':(edge['document'],edge['id']),'start_m':position,'end_m':position+length});position+=length
    need(position==10000,'Actual Edge trace does not total10km')
    return {**tr,'route_count':10,'route_resources':routes,'segments':segments,
            'message_main_signals':[{'name':m['name'],'document':m['document'],'type':m['type']} for m in base['mains']]}



def pairs(text,kind,cid):
    need('// x-Legend: [s]' in text and '// y-Legend: [km]' in text,'Native distance output units differ')
    need(header_value(text,r'^// '+re.escape(kind)+r' of Course:\s*(.+)$','Course')==cid,'Native distance/reservation Course differs')
    out=[]
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('//'): continue
        row=line.split();need(len(row)==2,'Native time/distance row width differs')
        row=tuple(float(x) for x in row);need(all(math.isfinite(x) for x in row) and 32400<=row[0]<=33600 and -.00005<=row[1]<=10.00005,'Native time/distance range differs');out.append((row[0],row[1]*1000))
    need(out and all(a[0]<=b[0] and a[1]<=b[1]+.11 for a,b in zip(out,out[1:])),'Unordered native time/distance record')
    return out



def course(plan,names,messages,texts,row,route_rows,tr):
    cid=plan['course_id'];tt=texts['OT_'+cid+'.tt'];vt=texts['OT_'+cid+'.vt'];order=[v['station_sign'] for v in plan['visits']]
    for text,pattern in [(tt,r'^// Timetable of Course:\s*(.+)$'),(vt,r'^// Speed/Time of Course\s*:\s*(.+)$')]:
        need(header_value(text,pattern,'Course')==cid,'Course header differs')
        need(header_value(text,r'^// Train:\s*(.+)$','Train')==plan['train'],'Course Train differs')
        need(header_value(text,r'^// Itineraries:\s*1:\s*(.+)$','Itinerary')==plan['itinerary'],'Course Itinerary differs')
    events=[]
    for i,sign in enumerate(order):
        marker=('(?:Departure at |Late Departure at )' if i==0 else '(?:Passed Station |Late Passing of Station )' if i==1 else '(?:Early |Late )?Arrival at ')+re.escape(sign)
        pattern=re.compile(r'^(?:NORMAL|WARNING)\s+\t?(\d{2}:\d{2}:\d{2})\s+'+re.escape(cid)+r'\s+Course '+re.escape(cid)+r': '+marker+r'(?=\s|$).*\('+re.escape(sign)+r'\)\s*$')
        hits=[(line,pattern.fullmatch(line)) for line in messages.splitlines()];hits=[(s,m) for s,m in hits if m]
        need(len(hits)==1,'Exactly one native station/document event required: '+cid+'/'+sign)
        line,hit=hits[0];events.append({'time':hit[1],'station':sign,'document':sign,'raw':line})
    need(clock(events[0]['time'])>=plan['visits'][0]['absolute_seconds'] and all(clock(a['time'])<clock(b['time']) for a,b in zip(events,events[1:])),'Actual station times/order differ')
    need('Actual Timetable vs. Planned Timetable' in tt,'Actual/planned Timetable missing')
    first,second=tt.split('Actual Timetable vs. Planned Timetable',1)
    actual=[[s.strip() for s in line.split('\t')] for line in first.splitlines() if '\t' in line and not line.startswith('//')]
    comparison=[[s.strip() for s in line.split('\t')] for line in second.splitlines() if '\t' in line and line.split('\t',1)[0].strip() in names.values()]
    need(len(actual)==len(comparison)==3,'Native Timetable needs three stations in both sections')
    for i,(sign,event,visit) in enumerate(zip(order,events,plan['visits'])):
        need(actual[i][0]==names[sign] and actual[i][1]==('Dep.','Pass','Arr.')[i] and actual[i][2]==event['time'],'Actual TT/Message event differs')
        rr=comparison[i];need(len(rr)>=6 and rr[0]==names[sign] and rr[1]==('Dep.','Pass','Arr.')[i] and rr[2]==hms(visit['absolute_seconds']) and int(rr[3])==visit['absolute_seconds'] and rr[4]==event['time'],'Planned TT differs from this exact Course plan')
    samples=parse_vt(vt);need(max(v for _,v in samples)<=80.01,'Actual speed exceeds the explicit80km/h line profile')
    end=native_end_time(row[11],row[12],samples[-1][0]);need(plan['visits'][-1]['absolute_seconds']-.005<=end<=33600,'Native Course ends before plan or after window')
    need(row[3]==plan['train'] and row[4]=='Reihe R' and row[7]==events[0]['time'] and row[9]==events[-1]['time'],'Statistics/Train/station events differ')
    need(math.isclose(float(row[21]),10.,abs_tol=1e-7) and int(row[23])==1 and all(int(x)>=0 for x in row[24:26]),'Actual distance/terminal stop/counter profile differs')
    need(clock(events[-1]['time'])<=end+.51,'Actual terminal arrival after Course end')
    route_rows=sorted(route_rows,key=lambda r:int(r[1]));expected=[r['route_name'] for r in tr['route_resources']]
    need(len(route_rows)==10 and [r[5] for r in route_rows]==expected,'Actual10Route usage sequence differs')
    st=pairs(texts['OT_'+cid+'.st1'],'Distance/Time',cid)
    need(abs(st[0][1])<=.1 and abs(st[-1][0]-end)<=.011,'Actual head-distance endpoint differs')
    terminal_position=terminal_log_position(st[-1][1])
    need([t for t,_ in st]==[t for t,_ in samples],'Native VT and distance records do not share the same actual absolute time samples')
    need(st[0][0]>=32400 and samples[0][0]>=32400,'Actual trajectory before run')
    reserve=pairs(texts['OT_'+cid+'.step1'],'Route Reservation',cid)
    release=pairs(texts['OT_'+cid+'.step2'],'Route Release',cid)
    def crossing(series,target):return next((t for t,d in series if d>=target-.051),None)
    blocks=[{'start_m':a,'end_m':b,'reserved_at_s':crossing(reserve,b),'released_at_s':crossing(release,b)} for a,b in BLOCKS]
    need(all(x['reserved_at_s'] is not None and x['released_at_s'] is not None and x['reserved_at_s']<=x['released_at_s'] for x in blocks),'Missing/invalid actual reservation/release of a station-to-station block')
    return {'course':cid,'train':plan['train'],'itinerary':plan['itinerary'],'lane':plan['lane'],'events':events,'distance_km':float(row[21]),'end_s':end,'course_end':row[11],'course_end_rounded_numeric_s':int(row[12]),'terminal_log_position':terminal_position,'terminal_stops':int(row[23]),'route_brakings':int(row[24]),'signal_stops':int(row[25]),'route_names':expected,'route_statistics':route_rows,'vt_samples':len(samples),'maximum_speed_kmh':max(v for _,v in samples),'last_two_zero_speed_samples':samples[-2:],'native_block_reservation_release':blocks,'last_station_area_release_recorded':crossing(release,10000),'departure_delay_s':clock(events[0]['time'])-plan['visits'][0]['absolute_seconds']},st,samples



def clean_curve(rows):
    out=[]
    for t,d in rows:
        if out and t==out[-1][0]:
            need(abs(d-out[-1][1])<=.11,'Conflicting st1 positions at one exported time')
            out[-1]=(t,d)
        else:out.append((t,d))
    need(len(out)>1,'At least two distinct physical trajectory times required')
    return out



def ranges(trace):
    edges={};elements={}
    for edge in trace['segments']:
        interval=(edge['start_m'],edge['end_m'])
        edges[tuple(edge['edge_key'])]=[interval]
        elements.setdefault(tuple(edge['safety_element_key']),[]).append(interval)
    return edges,elements



def first_covered(series,target):
    return next((t for t,d in series if d>=target-.051),None)



def lease_disjoint(a,b,tolerance=.011):
    if any(v is None for v in (*a,*b)):return False
    need(all(type(v) in (float,int) and math.isfinite(v) for v in (*a,*b)) and a[0]<=a[1] and b[0]<=b[1], 'Invalid/nonfinite native reserve/release interval')
    return a[1]<=b[0]+tolerance or b[1]<=a[0]+tolerance



def bodies_on_ranges(lo,hi,intervals,length=209.,margin=POSITION_RECONCILIATION_M+DISTANCE_EXPORT_HALF_UNIT_M+2*(80/3.6)*TIME_EXPORT_HALF_UNIT_S):
    possible=any(hi+margin>a and lo-length-margin<b for a,b in intervals)
    definite=any(lo-margin>a and hi-length+margin<b for a,b in intervals)
    return possible,definite



def pair_review(a,b,ta,tb,one,two,steps_a,steps_b):
    need(a['lane'][0]==b['lane'][0],'Motion comparison is only for one running-main direction')
    ea,sa=ranges(ta);eb,sb=ranges(tb);shared_e=set(ea)&set(eb);shared_s=set(sa)&set(sb)
    need(shared_e and shared_s,'Same-direction actual Edge/Element sharing absent')
    need(all(ea[k]==eb[k] for k in shared_e),'Shared physical Edge has different journey-coordinate offsets; cannot compare these st1 coordinates')
    blocks=[]
    for i in (0,1,2,3,5,6,7,8):
        ra=ta['route_resources'][i];rb=tb['route_resources'][i]
        common={tuple(k) for k in ra['element_keys']}&{tuple(k) for k in rb['element_keys']}
        need(common,'Same numbered station-to-station block lacks a real shared Element')
        x=a['native_block_reservation_release'][len(blocks)];y=b['native_block_reservation_release'][len(blocks)]
        need(lease_disjoint((x['reserved_at_s'],x['released_at_s']),(y['reserved_at_s'],y['released_at_s'])),
             'Native reservation/release overlap on shared block '+a['course']+'/'+b['course']+'/'+str(i))
        blocks.append({'route_index':i,'start_m':BOUNDARIES[i],'end_m':BOUNDARIES[i+1],
            'actual_shared_element_keys':[list(k) for k in sorted(common)],
            'a_reserve_release_s':[x['reserved_at_s'],x['released_at_s']],
            'b_reserve_release_s':[y['reserved_at_s'],y['released_at_s']],
            'first_reserved_course':a['course'] if x['reserved_at_s']<=y['reserved_at_s'] else b['course']})
    if {a['course'],b['course']}=={'GDD101','GDD102'}:
        lead=a if a['course']=='GDD101' else b;follow=b if a['course']=='GDD101' else a
        need(follow['native_block_reservation_release'][0]['reserved_at_s']>=lead['native_block_reservation_release'][0]['released_at_s']-.011,
             'The designated D1 follower passed its leader in the initial shared block')
    
    
    leases={}
    for k in shared_s:
        end_a=max(v[1] for v in sa[k]);end_b=max(v[1] for v in sb[k])
        la=(first_covered(steps_a[0],end_a),first_covered(steps_a[1],end_a))
        lb=(first_covered(steps_b[0],end_b),first_covered(steps_b[1],end_b))
        leases[k]={'element_key':list(k),'a_extent_m':sa[k],'b_extent_m':sb[k],
            'a_prefix_reserve_release_s':la,'b_prefix_reserve_release_s':lb,
            'prefix_windows_disjoint':lease_disjoint(la,lb),
            'direct_native_element_id_log':False}
    one,two=clean_curve(one),clean_curve(two);times_a=[t for t,_ in one];times_b=[t for t,_ in two]
    start=max(clock(a['events'][0]['time']),clock(b['events'][0]['time']),one[0][0],two[0][0]);end=min(a['end_s'],b['end_s'],one[-1][0],two[-1][0])
    checks=0;ambiguous=[];definite=[];rear=[];resolved=0
    if start<end:
        knots=sorted({start,end,*[t for t in times_a if start<t<end],*[t for t in times_b if start<t<end]})
        def bracket(rows,times,left,right):
            return rows[max(0,bisect.bisect_right(times,left)-1)][1],rows[min(len(rows)-1,bisect.bisect_left(times,right))][1]
        for left,right in zip(knots,knots[1:]):
            alo,ahi=bracket(one,times_a,left,right);blo,bhi=bracket(two,times_b,left,right);checks+=1
            for k in shared_s:
                ap,ad=bodies_on_ranges(alo,ahi,sa[k]);bp,bd=bodies_on_ranges(blo,bhi,sb[k])
                if ad and bd:
                    if len(definite)<20:definite.append({'interval_s':[left,right],'element_key':list(k),'a_head_bounds_m':[alo,ahi],'b_head_bounds_m':[blo,bhi]})
                elif ap and bp:
                    if leases[k]['prefix_windows_disjoint']:resolved+=1
                    elif len(ambiguous)<20:ambiguous.append({'interval_s':[left,right],'element_key':list(k),'a_head_bounds_m':[alo,ahi],'b_head_bounds_m':[blo,bhi]})
            for k in shared_e:
                if bodies_on_ranges(alo,ahi,ea[k])[0] and bodies_on_ranges(blo,bhi,eb[k])[0]:
                    bound=max(alo-209.-bhi,blo-209.-ahi)-2*(POSITION_RECONCILIATION_M+DISTANCE_EXPORT_HALF_UNIT_M+(80/3.6)*TIME_EXPORT_HALF_UNIT_S)
                    rear.append((bound,left,right,list(k)))
    need(not definite,'Native trajectory bounds place both bodies in a shared actual SafetyElement: '+json.dumps(definite[:2]))
    need(not ambiguous,'Export resolution/prefix records cannot exclude shared Element occupancy: '+json.dumps(ambiguous[:2]))
    need(not rear or min(x[0] for x in rear)>=0,'Shared actual Edge rear-clearance envelope is negative; need finer native evidence')
    
    throats=[]
    for i in (4,9):
        common={tuple(k) for k in ta['route_resources'][i]['element_keys']}&{tuple(k) for k in tb['route_resources'][i]['element_keys']}
        throats.append({'route_index':i,'actual_shared_elements':[leases[k] for k in sorted(common)],
            'whole_a_route_release_s':first_covered(steps_a[1],BOUNDARIES[i+1]),
            'whole_b_route_release_s':first_covered(steps_b[1],BOUNDARIES[i+1]),
            'release_was_not_inferred_from_CourseEnd':True})
    return {'course_a':a['course'],'course_b':b['course'],'same_direction':True,
        'eight_native_shared_blocks_mutually_exclusive':True,'blocks':blocks,
        'shared_edge_keys':[list(k) for k in sorted(shared_e)],'shared_element_count':len(shared_s),
        'absolute_time_comparison_interval_s':[start,end] if start<end else None,
        'absolute_time_bracketing_checks':checks,'prefix_resolved_boundary_checks':resolved,
        'minimum_shared_edge_rear_clearance_bound_m':min(rear) if rear else None,
        'unresolved_possible_shared_element_intervals':ambiguous,'definite_shared_element_body_conflicts':definite,
        'station_throat_evidence':throats,
        'maximum_native_sample_gap_s':{'a':max(y[0]-x[0] for x,y in zip(one,one[1:])),'b':max(y[0]-x[0] for x,y in zip(two,two[1:]))},
        'linear_interpolation_used':False,'native_direct_element_lease_log_available':False,
        'global_continuous_position_error_bound_proven':False,
        'bounds_assumptions':['Cumulative distance stays nondecreasing between exported samples on these directed journeys.','Comparison covers simultaneous presence from actual departures through the earlier Course end; no post-end physical clearance is inferred.','Each train assumes a0.5m position/log coordinate-error allowance based on stock per-step reconciliation and the observed terminal offset, plus0.05m distance export rounding and0.005s time export rounding at80km/h. A per-step threshold alone does not prove a global continuous error bound; reported clearance is conditional on this envelope. Rear clearance subtracts both trains margins. Private platform Edges sharing a coordinate are excluded.'],
        'continuous_physics_or_safety_certified':False}



def all_pairs(reports,topology,trajectories,texts):
    same=[];opposite=[];ids=sorted(reports)
    for i,aid in enumerate(ids):
        for bid in ids[i+1:]:
            a,b=reports[aid],reports[bid];ta,tb=topology['traces'][aid],topology['traces'][bid]
            ea,sa=ranges(ta);eb,sb=ranges(tb)
            if a['lane'][0]!=b['lane'][0]:
                need(not(set(ea)&set(eb)) and not(set(sa)&set(sb)),'Opposite mains unexpectedly share actual Edge/Element resources')
                opposite.append({'course_a':aid,'course_b':bid,'actual_resources_disjoint':True,'same_coordinate_collision_test_applied':False});continue
            def step(cid):return (pairs(texts['OT_'+cid+'.step1'],'Route Reservation',cid),pairs(texts['OT_'+cid+'.step2'],'Route Release',cid))
            same.append(pair_review(a,b,ta,tb,trajectories[aid],trajectories[bid],step(aid),step(bid)))
    need(len(same)==16 and len(opposite)==20,'Expected16 same-direction and20 opposite-direction pairs')
    return {'same_direction_pairs':same,'opposite_direction_pairs':opposite,'same_direction_count':16,'opposite_direction_count':20,
        'all128_shared_block_pair_checks_passed':True,'direct_native_ElementID_log_available':False,
        'terminal_whole_Route_release_may_remain_unrecorded':True,'continuous_safety_certified':False}



def fault_barrier(reports,trajectories):
    down=[cid for cid,report in reports.items() if report['lane'].startswith('D')]
    need(len(down)==5,'Five actual Down Courses required for the shared fault')
    sampled_heads={};not_departed=[]
    for cid in down:
        prior=[(t,s) for t,s in trajectories[cid] if t<32760-.011]
        need(not prior or max(s for _,s in prior)<=2400.1,'Down trajectory sample passed failed B2 before incident ended')
        if not prior:
            need(clock(reports[cid]['events'][0]['time'])>=32760,'No pre-recovery samples or delayed departure coverage for '+cid);not_departed.append(cid)
        sampled_heads[cid]=max((s for _,s in prior),default=None)
        need(reports[cid]['native_block_reservation_release'][2]['reserved_at_s']>=32760-.011,
             'A Down Course reserved the Route starting at failed B2 before09:06: '+cid)
    return down,sampled_heads,not_departed



def fault_incident_events(messages,first_station):
    out=[]
    for second,verb in ((32400,'started'),(32760,'stopped')):
        
        
        pattern=re.compile(r'^NORMAL\s*\t'+re.escape(hms(second))+r'\t\tIncident '+verb+r': Signal '+re.escape('S_'+first_station+'_D_B2')+r'\t\('+re.escape(first_station)+r'\)\s*$')
        hits=[line for line in messages.splitlines() if pattern.fullmatch(line)]
        need(len(hits)==1,'One exact native target-signal Incident '+verb+' event required at '+hms(second));out+=hits
    return out



def classify_native_messages(messages,plans,rows,topology):
    """Retain native severities; only five source-proven operational warnings.

    No unknown WARNING, ERROR, input/reference diagnostic, or incorrect counter
    is hidden. Distant-yellow messages are NORMAL and do not certify main green.
    """
    lookup={p['course_id']:p for p in plans};warnings=[];counts={cid:{'stop':0,'braking':0} for cid in lookup};distant=[]
    for line in messages.splitlines():
        parts=[s.strip() for s in line.split('\t')]
        if not parts or parts[0] not in {'NORMAL','WARNING','ERROR','FATAL'}:continue
        if parts[0] in {'ERROR','FATAL'}:raise ReviewError('Native '+parts[0]+' retained: '+line)
        special=len(parts)>=4 and 'Passed closed Distant Signal ' in parts[3]
        if parts[0]!='WARNING' and not special:continue
        need(len(parts)==5 and parts[2] in lookup,'Malformed/unbound native warning or distant message: '+line)
        severity,stamp,cid,body,doc=parts;need(doc.startswith('(') and doc.endswith(')'),'Native message document suffix required')
        doc=doc[1:-1];need(body.startswith('Course '+cid+': '),'Native message Course identity differs')
        body=body[len('Course '+cid+': '):];plan=lookup[cid];tr=topology['traces'][cid]
        known=[m for m in tr['message_main_signals'] if m['document']==doc]
        def signal_match(value,require_distant=False):
            
            
            matches=[m for m in known if value==m['name'] or value.startswith(m['name']+'_')]
            need(len(matches)==1 and (not require_distant or matches[0]['type'] in (2,25,26)),
                 'Message signal is not a selected main/distant in this actual document: '+line)
        entry={'severity':severity,'time':stamp,'course':cid,'document':doc,'raw':line}
        if special:
            need(severity=='NORMAL','Native distant-yellow message severity changed')
            signal_match(body.removeprefix('Passed closed Distant Signal '),True)
            entry.update(category='passed_yellow_distant',native_spec=0x36,native_type=1,does_not_prove_main_green_or_low_speed=True);distant.append(entry);continue
        late=re.fullmatch(r'Late (Departure at |Passing of Station |Arrival at )(\S+) \(Delay: (\d+)s\)',body)
        if late:
            index={'Departure at ':0,'Passing of Station ':1,'Arrival at ':2}[late[1]]
            need(plan['visits'][index]['station_sign']==late[2]==doc and clock(stamp)-plan['visits'][index]['absolute_seconds']==int(late[3])>0,
                 'Late warning disagrees with actual station, plan or numeric delay: '+line)
            entry.update(category=('late_departure','late_passing','late_arrival')[index],native_spec=(0x12,0x35,0x14)[index],native_type=2,delay_s=int(late[3]))
        else:
            stop=re.fullmatch(r'Stop at Signal (\S+)(?: at (\S+))?',body)
            brake=re.fullmatch(r'Braking for Route (\S+)',body)
            need(stop is not None or brake is not None,'Unclassified native WARNING retained: '+line)
            if stop:
                signal_match(stop[1]);need(stop[2] is None or stop[2]==doc,'Stop message station/document mismatch');counts[cid]['stop']+=1
                entry.update(category='signal_stop',native_spec=2,native_type=2)
            else:
                signal_match(brake[1]);counts[cid]['braking']+=1;entry.update(category='route_braking',native_spec=4,native_type=2)
        warnings.append(entry)
    for cid,counter in counts.items():
        need(counter['braking']==int(rows[cid][24]) and counter['stop']==int(rows[cid][25]),'Native warning counters disagree with Statistics: '+cid)
    return {'warning_count':len(warnings),'error_fatal_count':0,'native_WARNING_lines_preserved':warnings,
        'categories':{name:sum(e['category']==name for e in warnings) for name in ('signal_stop','route_braking','late_departure','late_passing','late_arrival')},
        'normal_yellow_distant_count':len(distant),'normal_yellow_distant_lines':distant,
        'unknown_or_input_warnings':[],'zero_warnings_claimed':False,
        'source_policy':'Only source-proven five business warning classes accepted with exact Course/station/delay/counter checks. Native severities unchanged.'}

