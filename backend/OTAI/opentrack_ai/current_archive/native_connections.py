"""Current Connection6 / Timetable9 saved-data commands. Pure bytes, no filesystem.
Caller atomically publishes output with all dependency hashes rechecked.
Not GUI, native runtime, circulation validation or a JSON-record conversion.
"""
from dataclasses import dataclass
import hashlib, math, struct
from opentrack_ai.current_archive import writer as w, catalogs as c
from opentrack_ai.current_archive.course_factories import timetable, clone, settext
from opentrack_ai.current_archive.stock_operations import CATEGORY_LAYOUT
from opentrack_ai.current_archive.graph_references import reference_inventory
from opentrack_ai.json_safe import checked_json

class ConnectionError(ValueError): pass

def need(ok,msg):
    if not ok: raise ConnectionError(msg)

@dataclass(frozen=True)
class Command:
    action: str
    course_id: str
    index: int
    target_course_id: str | None = None
    connection_index: int | None = None

LAYOUT=['@','@','@','@','i','@','@','i','f']
def text(obj,i):
    return None if obj.contents[i].value is None else c.text(obj.contents[i].value)

def connection(obj):
    c.shape(obj,'OTConnection',6,LAYOUT)
    for i in (0,1,2,3,5,6):
        if obj.contents[i].value is not None:c.text(obj.contents[i].value)
    
    need(type(obj.contents[4].value)is int and 0<=obj.contents[4].value<=11,'Noncanonical Connection flags')
    need(not (obj.contents[4].value&4 and obj.contents[4].value&8),'Conflicting connection locations')
    need(type(obj.contents[7].value)is int,'Connection time type must be int32')
    return obj

def wait(value):
    need(math.isfinite(value),'Nonfinite category default connection time')
    value=struct.unpack('<f',struct.pack('<f',value))[0]
    if value<0:return 'HH:MM:SS'
    seconds=math.trunc(struct.unpack('<f',struct.pack('<f',math.fmod(value,86400)))[0])%86400
    return f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}'

def record(obj):
    connection(obj)
    return {k:text(obj,i) for i,k in [(0,'course_id'),(1,'target_course_id'),(2,'station_sign'),(3,'minimum_wait'),(5,'maximum_wait'),(6,'target_station_sign')]} | {'flags':obj.contents[4].value,'time_reference_type':obj.contents[7].value,'dispatching_distance_km':obj.contents[8].value}

def atom(v):
    if isinstance(v,w.GenericArchivedObject):return ('ref',id(v))
    if isinstance(v,w.WireFloat):return ('float',v.encoding,v.byte_order,v.bits)
    if isinstance(v,float):return ('float64',struct.pack('<d',v))
    if isinstance(v,w.Array):return ('array',atom(v.elements))
    if isinstance(v,w.GenericStruct):return ('struct',v.name,atom(v.fields))
    if isinstance(v,w.CString):return ('cstring',v.token.data)
    if isinstance(v,(list,tuple)):return tuple(map(atom,v))
    return v

def state(obj):
    cl=obj.clazz;chain=[]
    while cl:chain.append((cl.name,cl.version));cl=cl.superclass
    return tuple(chain),tuple((tuple(g.encodings),atom(g.values)) for g in obj.contents)

def apply(blobs,commands):
    """blobs: timetable,courses,trains,stations,connection_template (stock Connection6).
    1..1000 typed Command values; all execute sequentially in ONE decoded graph.
    insert uses explicit valid named target; the GUI unbound '0' draft is excluded.
    """
    need(type(blobs)is dict and set(blobs)=={'timetable','courses','trains','stations','connection_template'},'Five explicit byte dependencies required')
    need(all(type(v)is bytes for v in blobs.values()),'Immutable bytes required')
    need(type(commands)is list and 1<=len(commands)<=1000,'1..1000 commands required')
    for cmd in commands:
        need(type(cmd)is Command,'Typed Command required')
        need(cmd.action in ('insert','delete','turnround_to','turnround_from'),'Unknown action')
        need(type(cmd.course_id)is str and bool(cmd.course_id) and type(cmd.index)is int and cmd.index>=0,'Exact row identity required')
        if cmd.action=='delete':need(cmd.target_course_id is None and type(cmd.connection_index)is int and cmd.connection_index>=0,'Delete needs nonnegative index only')
        else:need(type(cmd.target_course_id)is str and cmd.target_course_id not in ('','0','-1') and cmd.connection_index is None,'Exact bound target required')
    loaded={k:w.load_next_compatible(v) for k,v in blobs.items()};roots={k:v[0] for k,v in loaded.items()}
    root=roots['timetable'];rows=timetable(root);template=connection(roots['connection_template'])
    courses={text(o,0):o for o in c.course_items(roots['courses'])}
    trains={text(o,0):o for o in c.train_items(roots['trains'])}
    cats={}
    for cat in c.array(roots['trains'].contents[1].value):
        c.shape(cat,'OTTrainCategory',19,CATEGORY_LAYOUT);key=text(cat,1)
        need(key and key not in cats,'Ambiguous category identity');cats[key]=cat
    stations=c.station_items(roots['stations']);groups={}
    objects,counts=reference_inventory(root);old={id(o):(o,state(o)) for o in objects};allowed={};array_ids=set()
    for key,row in rows.items():
        groups.setdefault(text(row,1),[]).append(row)
        need(text(row,2) not in (None,'','0','-1') or row.contents[11].value==0,'Noncanonical unbound interval offset')
        for obj in c.array(row.contents[9].value):connection(obj)
    for group in groups.values():
        group.sort(key=lambda o:o.contents[3].value)
        need([o.contents[3].value for o in group]==list(range(len(group))) and all(o.contents[4].value==len(group)-1 for o in group),'Incomplete timetable index domain')
    touched={};actions=[];created=deleted=0
    def touch(row):
        key=text(row,1)+'#'+str(row.contents[3].value);arr=row.contents[9].value
        need(counts[id(row)]==1 and counts[id(arr)]==1,'Shared row/connectionArray requires separately authorized explicit repair; no implicit COW')
        for obj in c.array(arr):need(counts[id(obj)]<=1,'Shared Connection object unsupported')
        if key not in touched:touched[key]=[record(o) for o in c.array(arr)]
        array_ids.add(id(arr));return arr
    def modify(obj,i,value):
        allowed.setdefault(id(obj),set()).add(i)
        if i in (0,1,2,3,5,6):settext(obj,i,value)
        else:obj.contents[i].value=value
    def find(row,target):
        return next(((o,i) for i,o in enumerate(c.array(row.contents[9].value)) if text(o,1)==target),(None,None))
    def default(cid):
        train=trains.get(text(courses[cid],3));cat=cats.get(text(train,3)) if train is not None else None
        return ('00:07:00',{'source':'native_no_category_fallback','seconds':420}) if cat is None else (wait(cat.contents[20].value),{'source':'category','name':text(cat,1),'seconds':cat.contents[20].value})
    def shell(row):
        nonlocal created
        arr=touch(row);obj=clone(template)
        for i,val in [(0,'0'),(1,'0'),(2,None),(3,None),(5,None),(6,'')]:settext(obj,i,val)
        for i,val in [(4,0),(7,0),(8,0.)]:obj.contents[i].value=val
        items=c.array(arr);idx=len(items);w.set_elements(arr,items+[obj]);created+=1
        return obj,idx
    def finish(obj,row,target,nil=False):
        minimum,provenance=default(text(row,1))
        for i,val in [(0,text(row,1)),(1,target),(2,text(row,5)),(3,minimum),(5,None if nil else 'HH:MM:SS'),(6,text(row,5))]:modify(obj,i,val)
        return provenance
    def helper(row,target,style):
        touch(row);obj,idx=find(row,target);new=obj is None;prov=None
        if new:obj,idx=shell(row);prov=finish(obj,row,target,style=='start')
        if style=='join':modify(obj,4,obj.contents[4].value|1)
        elif style=='split':modify(obj,4,obj.contents[4].value|2)
        return obj,idx,new,prov
    for cmd in commands:
        key=cmd.course_id+'#'+str(cmd.index);need(key in rows,'Missing selected timetable row');row=rows[key]
        if cmd.action!='delete':
            need(cmd.course_id in courses and cmd.course_id not in ('0','-1'),'Missing/reserved owner Course')
            need(cmd.target_course_id in courses,'Missing target Course')
            if cmd.action=='turnround_to':row=groups[cmd.course_id][-1]
            elif cmd.action=='turnround_from':row=groups[cmd.course_id][0]
            sign=text(row,5);need(sign in stations,'Missing effective Station')
            target_rows=groups.get(cmd.target_course_id,[])
            matches=[r for r in target_rows if text(r,5)==sign]
            need(matches,'Target has no timetable visit at effective station (strict API guard)')
        arr=touch(row);entry={'action':cmd.action,'selected_row':key,'effective_row':text(row,1)+'#'+str(row.contents[3].value)}
        if cmd.action=='delete':
            items=c.array(arr);need(cmd.connection_index<len(items),'Delete index out of range');items.pop(cmd.connection_index);w.set_elements(arr,items);deleted+=1
        elif cmd.action=='insert':
            _,idx,new,prov=helper(row,cmd.target_course_id,'plain');entry.update(connection_index=idx,created=new,default=prov)
        else:
            
            obj,idx=find(row,cmd.target_course_id);new=obj is None
            if new:obj,idx=shell(row)
            for i in (2,6):modify(obj,i,sign)
            modify(obj,4,obj.contents[4].value&~12)
            if cmd.action=='turnround_to':
                first=text(target_rows[0],5)==sign;counter=target_rows[0] if first else matches[0];style='start' if first else 'join';flags=2 if first else 1
            else:
                last=text(target_rows[-1],5)==sign;counter=target_rows[-1] if last else matches[0];style='split';flags=0
            _,other_idx,other_new,other_prov=helper(counter,cmd.course_id,style)
            modify(obj,4,(obj.contents[4].value&~3)|flags)
            prov=finish(obj,row,cmd.target_course_id) if new else None
            entry.update(connection_index=idx,created=new,default=prov,counterpart={'row':text(counter,1)+'#'+str(counter.contents[3].value),'connection_index':other_idx,'created':other_new,'default':other_prov,'style':style})
        actions.append(entry)
    
    
    for oid,(obj,before) in old.items():
        after=state(obj)
        need(before[0]==after[0],'Class chain changed')
        if oid in array_ids:continue 
        need(len(before[1])==len(after[1]),'Original object groups changed')
        for i,(a,b) in enumerate(zip(before[1],after[1])):
            if i not in allowed.get(oid,()):need(a==b,'Protected original graph changed')
    output=w.dump_verified(root,loaded['timetable'][1]);fresh,_=w.load_next_compatible(output)
    need(w.fingerprint(fresh)==w.fingerprint(root),'Fresh full graph mismatch')
    report={'dependency_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in blobs.items()},'output_sha256':hashlib.sha256(output).hexdigest(),'commands':actions,'created':created,'deleted':deleted,'rows':{k:{'before':v,'after':[record(o) for o in c.array(rows[k].contents[9].value)]} for k,v in touched.items()},'protected_original_graph_verified':True,'fresh_full_graph_verified':True,'native_application_tested':False,'independent_official_reader_tested_by_caller':False,'scope':'current archive saved-data only; no simulation/GUI; unknown fields retained, unsupported versions rejected'}
    return output,checked_json(report)
