"""Incident12 Train-only archive construction/editing; no simulation or I/O.

Uses current_archive stdlib codec. Caller owns atomic publication and source SHA.
Not native init equivalence: explicit name/course/time + audited init defaults.
"""
import math
import re
import struct
from . import writer as w, catalogs as c

class IncidentError(ValueError): pass
SCHEMA = ['@']*5 + ['iii','ffff','i'] + ['@']*6 + ['f','ii','@','ffff','@','f','@','@','f','@','f']
SETTERS = {'name':'0x4e16a0','enabled':'0x4e229c','reduced_speed_kmh':'0x4e1d6c'}

def need(ok, message):
    if not ok: raise IncidentError(message)

def text(value, nonempty=False):
    need(type(value) is str and len(value)<=2000 and (not nonempty or bool(value)) and all(32<=ord(x)<127 for x in value), 'Printable ASCII string <=2000 required')
    return value

def string(value):
    return w.GenericArchivedObject(w.Class(b'NSString',1,w.Class(b'NSObject',0)),[w.TypedValue(b'+',text(value).encode())])

def time(value):
    need(type(value) is str and re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]',value), 'Explicit HH:MM:SS required')
    return value

def speed(value):
    need(type(value) in (int,float), 'Native finite float32 input required (not bool)')
    try: result=struct.unpack('<f',struct.pack('<f',value))[0]
    except (OverflowError,struct.error): raise IncidentError('Outside finite float32')
    need(math.isfinite(result),'Outside finite float32')
    return max(result,0.0) if result<0 else result

def incoming(root):
    from .graph_references import incoming_counts
    return incoming_counts(root)

def state(blob):
    need(type(blob)is bytes,'Immutable archive bytes required')
    root,version=w.load_next_compatible(blob);courses=c.course_items(root)
    need(root.contents[0].value==17,'CourseList marker17 required')
    arr=root.contents[1].value;need(w.kind(arr)=='NSMutableArray','Mutable incident container required')
    incidents=c.array(arr);counts=incoming(root)
    need(counts.get(id(root),0)==0 and counts.get(id(arr),0)==1,'Shared/cyclic incident owner refused')
    allinc=[o for o in w.objects(root) if w.kind(o)=='OTIncident']
    need({id(o) for o in allinc}=={id(o) for o in incidents},'Incident outside designated container')
    names=set();lookup={c.text(o.contents[0].value):o for o in courses}
    for incident in incidents:
        c.shape(incident,'OTIncident',12,SCHEMA)
        need(counts[id(incident)]==1,'Shared Incident refused')
        n=c.text(incident.contents[0].value);text(n,True)
        need(n not in names,'Duplicate Incident name');names.add(n)
        need(incident.contents[5].values==[-1,-1,1],'Only explicit Train type1 supported')
        course=c.text(incident.contents[1].value)
        need(course in lookup and lookup[course].contents[5].value==1,'Exact enabled Course reference required')
        need(c.text(incident.contents[2].value)=='0','No document reference for Train profile')
        for g in (3,4):time(c.text(incident.contents[g].value))
        need(incident.contents[15].values==[0,0],'Only same-day time window')
        need(c.text(incident.contents[3].value)<=c.text(incident.contents[4].value),'Reversed window')
        need(incident.contents[7].value in (0,1),'Only use flag supported')
        for g in (8,9,10,11,12,13,16,18,21,23):need(c.text(incident.contents[g].value)=='','Unsupported reference/comment/distribution')
        need(not c.array(incident.contents[20].value),'Unexpected group IDs')
        need(incident.contents[6].values[1:]==[1.,0.,0.] and incident.contents[14].value==0. and incident.contents[17].values==[0.]*4,'Nondefault unsupported parameters')
        need(incident.contents[19].value==incident.contents[22].value==100. and incident.contents[24].value==-1.,'Nondefault probability/power')
        need(math.isfinite(incident.contents[6].values[0]) and incident.contents[6].values[0]>=0,'Invalid reduced speed')
    return root,version,arr,incidents,lookup

def create_train_incident(blob, *, name, course_id, begin_time, end_time, enabled=False, reduced_speed_kmh=0.):
    """Append current Incident12, built from audited defaults, never from legacy bytes."""
    root,version,arr,incidents,courses=state(blob)
    text(name,True);text(course_id,True);time(begin_time);time(end_time)
    need(begin_time<=end_time,'Same-day ordered window required')
    need(type(enabled)is bool,'enabled must be bool')
    need(course_id in courses and courses[course_id].contents[5].value==1,'Exact enabled Course reference required')
    need(name not in {c.text(o.contents[0].value) for o in incidents},'Duplicate Incident name')
    groupids=w.GenericArchivedObject(arr.clazz,[]);w.set_elements(groupids,[])
    values=[[string(x)] for x in (name,course_id,'0',begin_time,end_time)]
    values += [[-1,-1,1],[speed(reduced_speed_kmh),1.,0.,0.],[int(enabled)]]
    values += [[string('')] for _ in range(6)]
    values += [[0.],[0,0],[string('')],[0.,0.,0.,0.],[string('')],[100.],[groupids],[string('')],[100.],[string('')],[-1.]]
    incident=w.GenericArchivedObject(w.Class(b'OTIncident',12,w.Class(b'NSObject',0)),[w.TypedGroup([x.encode() for x in enc],v) for enc,v in zip(SCHEMA,values)])
    w.set_elements(arr,incidents+[incident]);out=w.dump_verified(root,version);state(out)
    return out

def patch_train_incident(blob, *, name, changes):
    root,version,arr,incidents,courses=state(blob)
    text(name,True);need(type(changes)is dict and bool(changes) and not set(changes)-SETTERS.keys(),'Known nonempty changes required')
    selected=[o for o in incidents if c.text(o.contents[0].value)==name];need(len(selected)==1,'Exact Incident name required');obj=selected[0]
    for key,value in changes.items():
        if key=='name':
            text(value,True);need(value==name or value not in {c.text(o.contents[0].value) for o in incidents},'Duplicate Incident name');obj.contents[0].value=string(value)
        elif key=='enabled':need(type(value)is bool,'enabled must be bool');obj.contents[7].value=int(value)
        else:obj.contents[6].values[0]=speed(value)
    out=w.dump_verified(root,version);state(out);return out
