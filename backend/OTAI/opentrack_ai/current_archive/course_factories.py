"""Current-only Course11/Timetable9 template factories. No I/O or native runtime.
Caller owns SHA/path/atomic batch persistence. External references are exact names,
NOT a claim of route physical validity. Existing graph nodes remain shared/unmodified.
"""
import math
import re
from opentrack_ai.current_archive import writer as w, catalogs as c

TT=['i','@','@','i','i','@','@','@','@','@','i','f','@','@','@','iiii','@','f','@']
class FactoryError(ValueError): pass

def require(ok,message):
    if not ok: raise FactoryError(message)

def clone(obj):
    return w.GenericArchivedObject(obj.clazz,None,[w.TypedGroup(list(g.encodings),list(g.values)) for g in obj.contents])

def put(obj,i,value):obj.contents[i].values[0]=value

def name(value):
    require(type(value) is str and 0<len(value)<=200 and all(32<=ord(x)<127 for x in value) and '#' not in value,'Expected exact printable ASCII name (1..200, no #)')
    return value

def string(sample,value):
    require(type(value) is str and len(value)<=2000 and all(32<=ord(x)<127 for x in value),'Expected printable ASCII text <=2000')
    exemplar=next((o for o in w.objects(sample) if w.kind(o)=='NSString'),None)
    require(exemplar is not None,'Template needs NSString shape'); c.text(exemplar)
    return w.GenericArchivedObject(exemplar.clazz,None,[w.TypedValue(b'+',value.encode('ascii'))])

def settext(obj,i,value):put(obj,i,None if value is None else string(obj,value))

def integer(value,low,high):
    require(type(value) is int and low<=value<=high,f'Integer outside {low}..{high}')
    return value

def real(value,low,high):
    require(isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and low<=value<=high,f'Finite number outside {low}..{high}')
    return float(value)

def dictionary(root):
    require(w.kind(root) in ('NSDictionary','NSMutableDictionary') and root.clazz.version==0,'Current dictionary required');c.hierarchy(root)
    require(root.contents and root.contents[0].encodings==[b'i'],'Dictionary count encoding')
    count=root.contents[0].value;require(type(count)is int and count>=0 and len(root.contents)==1+2*count,'Dictionary count')
    result={}
    for i in range(1,len(root.contents),2):
        k,v=root.contents[i:i+2];require(k.encodings==v.encodings==[b'@'],'Dictionary pair encoding')
        key=c.text(k.value);require(key not in result,'Duplicate dictionary key');result[key]=v.value
    return result

def timetable(root):
    rows=dictionary(root)
    for key,row in rows.items():
        c.shape(row,'OTTimetable',9,TT)
        require(row.contents[0].value==17,'Timetable internal format must be 17')
        require(key==c.text(row.contents[1].value)+'#'+str(row.contents[3].value),'Timetable key/owner/index mismatch')
        c.array(row.contents[9].value)
    return rows

def itinerary_names(root):
    require(w.kind(root)=='OTDestInfoList' and root.clazz.version==0 and len(root.contents)==1 and root.contents[0].encodings==[b'@'],'Current OTDestInfoList required')
    chain=root.clazz.superclass
    for n,v in [('OTMutableArray',0),('NSObject',0)]:
        require(chain is not None and chain.name==n.encode() and chain.version==v,'Unsupported Dest inheritance');chain=chain.superclass
    require(chain is None,'Unexpected Dest superclass');seen=set()
    for item in c.array(root.contents[0].value):
        c.shape(item,'OTDestInfo',1,['i','@','@','i','@']);s=c.text(item.contents[1].value)
        require(s and s not in seen,'Ambiguous Itinerary');seen.add(s)
    return seen

def new_course(courses,trains,dest,*,template_id,course_id,train,itineraries,fields=None):
    """Return copy-on-write CourseList. Every unmentioned field inherits template."""
    items=c.course_items(courses);lookup={c.text(o.contents[0].value):o for o in items}
    name(course_id);require(course_id not in ('0','-1'),'Reserved unbound Course ID');require(course_id not in lookup,'Course already exists');require(template_id in lookup,'Explicit existing Course template required')
    require(train in {c.text(o.contents[0].value) for o in c.train_items(trains)},'Unknown exact Train')
    require(type(itineraries)is list and 1<=len(itineraries)<=1000 and all(type(s)is str for s in itineraries),'Explicit nonempty Itinerary list required')
    known=itinerary_names(dest);require(len(itineraries)==len(set(itineraries)) and set(itineraries)<=known,'Unknown/duplicate exact Itinerary')
    obj=clone(lookup[template_id]);settext(obj,0,course_id);settext(obj,3,train)
    arr=clone(obj.contents[2].value);c.array(arr);w.set_elements(arr,[string(obj,s) for s in itineraries]);put(obj,2,arr)
    fields={} if fields is None else fields
    texts={'speed_type':4,'description':10,'comment':11,'train_number':13,'course_type':14}
    scalars={'acceleration_percent':6,'delayed_acceleration_percent':9}
    require(not set(fields)-set(texts)-set(scalars)-{'enabled','entering_speed_kmh','output_offset_m','spacing_mode','additional_reservation_time_s','additional_release_time_s'},'Unsupported Course field')
    for k,v in fields.items():
        if k in texts:require(v is not None,'Course text must not be nil');settext(obj,texts[k],v)
        elif k in scalars:put(obj,scalars[k],integer(v,50,100))
        elif k=='enabled':require(type(v)is bool,'enabled must be bool');put(obj,5,int(v))
        elif k=='entering_speed_kmh':put(obj,1,real(v,0,1000)/3.6)
        elif k=='output_offset_m':obj.contents[7].values[0]=real(v,-1e6,1e6)
        elif k=='spacing_mode':require(v in ('discrete','moving','moving_cbtc'),'Unsupported spacing mode');put(obj,8,{'discrete':0,'moving':2,'moving_cbtc':3}[v])
        else:obj.contents[12].values[0 if k=='additional_reservation_time_s' else 1]=real(v,0,86400)
    out=clone(courses);arr=clone(c.course_array(courses));w.set_elements(arr,items+[obj]);put(out,4,arr);return out

def clock(value):
    if value is None:return None
    require(type(value)is str and re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]',value),'Time needs HH:MM:SS or None')
    h,m,s=map(int,value.split(':'));return h*3600+m*60+s

def new_timetable(table,courses,stations,*,course_id,stops):
    """Add rows only: existing course timetable replacement deliberately unsupported.
    Each row explicitly selects template_key. Non-time optional fields inherit.
    Actual times explicitly reset using native reset semantics, never copy results.
    Connection-bearing templates rejected (owner rebinding not implemented).
    """
    rows=timetable(table);ids={c.text(o.contents[0].value) for o in c.course_items(courses)}
    require(course_id in ids,'Unknown Course');require(not any(c.text(o.contents[1].value)==course_id for o in rows.values()),'Timetable already exists')
    require(type(stops)is list and 1<=len(stops)<=10000,'Expected 1..10000 stops')
    known=c.station_items(stations);created=[];previous=-math.inf
    allowed={'template_key','station_sign','arrival','departure','arrival_day_offset','departure_day_offset','stop_at_station','timing_station','interval_reference_course_id','interval_offset_s','dwell_s','mean_delay_s','track_id','distribution_name','delta_mass_t'}
    required={'template_key','station_sign','arrival','departure','arrival_day_offset','departure_day_offset'}
    for index,spec in enumerate(stops):
        require(type(spec)is dict and required<=set(spec) and not set(spec)-allowed,'Missing/unknown timetable fields')
        require(spec['template_key'] in rows,'Explicit existing row template required');template=rows[spec['template_key']]
        require(not c.array(template.contents[9].value),'Connection-bearing template unsupported')
        require(spec['station_sign'] in known,'Unknown exact station sign');row=clone(template)
        put(row,9,clone(template.contents[9].value))
        settext(row,1,course_id);settext(row,5,spec['station_sign']);put(row,3,index);put(row,4,len(stops)-1)
        abs_times=[]
        for i,field in enumerate(('arrival','departure')):
            sec=clock(spec[field]);day=integer(spec[field+'_day_offset'],-366,366)
            require(sec is not None or day==0,'Undefined time requires zero day offset')
            if sec is not None:
                absolute=sec+day*86400;require(absolute>=previous,'Nonchronological timetable');previous=absolute;abs_times.append(absolute)
            settext(row,6+i,'HH:MM:SS' if sec is None else spec[field]);row.contents[15].values[i]=day
        require(abs_times,'At least one scheduled time required')
        settext(row,13,'HH:MM:SS');settext(row,14,'HH:MM:SS');row.contents[15].values[2:]=[0,0]
        flags=integer(row.contents[10].value,0,3)
        for field,bit in [('stop_at_station',1),('timing_station',2)]:
            if field in spec:require(type(spec[field])is bool,'Flags require bool');flags=flags|bit if spec[field] else flags&~bit
        put(row,10,flags)
        for field,slot in [('dwell_s',8),('mean_delay_s',12)]:
            if field in spec:settext(row,slot,format(real(spec[field],0,86400),'.9g'))
        dwell=float(c.text(row.contents[8].value));require(math.isfinite(dwell) and dwell>=0,'Invalid inherited dwell')
        require(not(flags&1 and len(abs_times)==2 and abs_times[1]-abs_times[0]<dwell),'Dwell exceeds planned stop')
        for field,slot in [('track_id',18),('distribution_name',16)]:
            if field in spec:require(spec[field] is not None,'Text must not be nil');settext(row,slot,spec[field])
        if 'delta_mass_t' in spec:put(row,17,real(spec['delta_mass_t'],-1e6,1e6))
        if 'interval_reference_course_id' in spec:settext(row,2,spec['interval_reference_course_id'])
        ref=None if row.contents[2].value is None else c.text(row.contents[2].value)
        offset=real(spec['interval_offset_s'], -31622400,31622400) if 'interval_offset_s' in spec else (0.0 if ref in (None,'','0','-1') else real(row.contents[11].value,-31622400,31622400))
        if ref in (None,'','0','-1'):
            require('interval_offset_s' not in spec or offset==0,'Unset interval reference requires zero offset');offset=0.0
        else:
            require(ref in ids and ref!=course_id,'Unknown/self interval reference')
            require(any(c.text(o.contents[1].value)==ref and c.text(o.contents[5].value)==spec['station_sign'] for o in rows.values()),'Reference has no station row')
        put(row,11,offset);created.append((course_id+'#'+str(index),row))
    out=clone(table);out.contents[0].values[0]=len(rows)+len(created)
    for key,row in created:out.contents.extend([w.TypedValue(b'@',string(row,key)),w.TypedValue(b'@',row)])
    return out

def generate(blobs,*,template_id,course_id,train,itineraries,stops,fields=None):
    """Required blobs: courses,trains,dest,stations,timetable. Returns changed bytes only."""
    require(set(blobs)=={'courses','trains','dest','stations','timetable'},'Five explicit catalogs required')
    decoded={k:w.load_next_compatible(v) for k,v in blobs.items()};roots={k:v[0] for k,v in decoded.items()}
    course=new_course(roots['courses'],roots['trains'],roots['dest'],template_id=template_id,course_id=course_id,train=train,itineraries=itineraries,fields=fields)
    table=new_timetable(roots['timetable'],course,roots['stations'],course_id=course_id,stops=stops)
    return {k:w.dump_verified(v,decoded[k][1]) for k,v in [('courses',course),('timetable',table)]}
