"""Current-only purebytes batch. No filesystem, Project, graph solver or migrations."""
import hashlib, math, struct
from types import MappingProxyType
from collections import defaultdict
from opentrack_ai.current_archive import writer as w, catalogs as c, course_factories as f
from opentrack_ai.current_archive.graph_references import reference_inventory

CATALOGS={'depot','trains','courses','dest','stations','timetable'}
class BatchError(ValueError): pass

def require(test,message):
    if not test:raise BatchError(message)

class Context:
    __slots__=('data','stock_update_targets')
    def __init__(self,data):self.data=MappingProxyType(data);self.stock_update_targets=0
    def courses(self):return c.course_items(self.data['courses'])
    def __getattr__(self,name):raise BatchError('Unexpected catalog-only context access: '+name)

def refs(data):
    engines=c.engine_items(data['depot']);trains=c.train_items(data['trains']);courses=c.course_items(data['courses'])
    names={c.text(o.contents[1].value) for o in engines};tn={c.text(o.contents[0].value) for o in trains};ids={c.text(o.contents[0].value) for o in courses}
    require(not ids&{'0','-1'},'Reserved Course identity')
    for t in trains:require(set(c.bound_engine_names(t))<=names,'Missing Engine binding')
    dest=f.itinerary_names(data['dest']);stations=c.station_items(data['stations']);table=f.timetable(data['timetable'])
    for o in courses:
        require(c.text(o.contents[3].value) in tn,'Missing Train binding')
        its=[c.text(s) for s in c.array(o.contents[2].value)]
        require(len(its)==len(set(its)) and set(its)<=dest,'Missing/duplicate Itinerary binding')
    groups=defaultdict(list);links=defaultdict(set)
    for key,r in table.items():
        owner=c.text(r.contents[1].value);station=c.text(r.contents[5].value)
        require(owner in ids and station in stations,'Missing timetable owner/station');groups[owner].append(r)
        ref=None if r.contents[2].value is None else c.text(r.contents[2].value)
        if ref not in (None,'','0','-1'):
            require(ref in ids and ref!=owner,'Missing/self interval Course');links[owner].add(ref)
            require(any(c.text(x.contents[1].value)==ref and c.text(x.contents[5].value)==station for x in table.values()),'Interval station reference missing')
        else:require(r.contents[11].value==0,'Noncanonical unbound interval offset')
        for conn in c.array(r.contents[9].value):
            c.shape(conn,'OTConnection',6,['@','@','@','@','i','@','@','i','f'])
            co=c.text(conn.contents[0].value);target=c.text(conn.contents[1].value)
            require(co==owner and c.text(conn.contents[2].value)==station,'Connection owner/station mismatch')
            require(target in ids,'Connection target missing/unbound')
            require(any(c.text(x.contents[1].value)==target and c.text(x.contents[5].value)==c.text(conn.contents[6].value) for x in table.values()),'Connection target station missing')
    for owner,rows in groups.items():
        rows.sort(key=lambda r:r.contents[3].value)
        require(all(r.contents[3].value==i and r.contents[4].value==len(rows)-1 for i,r in enumerate(rows)),'Noncontiguous timetable indices')
    def visit(n,active,done):
        require(n not in active,'Interval cycle')
        if n in done:return
        active.add(n)
        for child in links[n]:visit(child,active,done)
        active.remove(n);done.add(n)
    for n in list(links):visit(n,set(),set())
    return engines,courses,table

def targets(data,spec):
    kind=spec['kind']
    if kind=='update_engines':
        rows=c.engine_items(data['depot']);selected={n for n in spec['names']};return 'depot',[(o,{(2,5):'all'} if 'cw_value' in spec else {}) for o in rows if c.text(o.contents[1].value) in selected]
    if kind=='update_courses':
        slots={'acceleration_percent':(6,0),'delayed_acceleration_percent':(9,0),'comment':(11,0)}
        return 'courses',[(o,{slots[k]:'all' for k in slots if k in spec}) for o in c.course_items(data['courses']) if c.text(o.contents[0].value) in spec['course_ids']]
    if kind=='shift_timetable_rows':return 'timetable',[(o,{(6,0):'all',(7,0):'all',(15,0):'all',(15,1):'all'}) for o in f.timetable(data['timetable']).values() if c.text(o.contents[1].value) in spec['course_ids']]
    raise BatchError('Unsupported operation')

def masks(data,operations):
    result={k:{} for k in CATALOGS}
    for spec in operations:
        k,rows=targets(data,spec)
        for o,slots in rows:
            if spec['kind']=='update_engines' and 'understands_radio' in spec:slots[(11,0)]='bit4'
            result[k].setdefault(id(o),{}).update(slots)
    return result

def protected(root,mask):
    seen={}
    def walk(v):
        if isinstance(v,w.GenericArchivedObject):
            if id(v) in seen:return ('ref',seen[id(v)])
            n=len(seen);seen[id(v)]=n;chain=[];cl=v.clazz
            while cl:chain.append((cl.name,cl.version));cl=cl.superclass
            return ('obj',n,tuple(chain),tuple((tuple(g.encodings),tuple(('edited',) if mask.get(id(v),{}).get((i,j))=='all' else ('flags',x&~4) if mask.get(id(v),{}).get((i,j))=='bit4' else walk(x) for j,x in enumerate(g.values))) for i,g in enumerate(v.contents)))
        if isinstance(v,w.Array):return ('array',walk(v.elements))
        if isinstance(v,w.GenericStruct):return ('struct',v.name,walk(v.fields))
        if isinstance(v,(list,tuple)):return tuple(walk(x) for x in v)
        if isinstance(v,w.WireFloat):return ('floatbits',v.encoding,v.byte_order,v.bits)
        if isinstance(v,w.CString):return ('cstring',v.token.data)
        if isinstance(v,w.SharedString):return ('sharedstring',v.data)
        if type(v)is float:return ('float',v.hex())
        return v
    return walk(root)

def ownership(data,operations):
    inventories={k:reference_inventory(v)[1] for k,v in data.items()}
    for spec in operations:
        key,selected=targets(data,spec);counts=inventories[key]
        require(counts[id(data[key])]==0,'Shared catalog root')
        for o,_ in selected:require(counts[id(o)]==1,'Shared selected entity')
        if key=='courses':require(counts[id(c.course_array(data[key]))]==1,'Shared mutable Course array')

def schedule_checks(data,operations):
    from .timetable_batch import time_value
    selected={cid for s in operations if s['kind']=='shift_timetable_rows' for cid in s['course_ids']}
    groups=defaultdict(list)
    for row in f.timetable(data['timetable']).values():
        if c.text(row.contents[1].value) in selected:groups[c.text(row.contents[1].value)].append(row)
    for rows in groups.values():
        previous=-math.inf
        for row in sorted(rows,key=lambda r:r.contents[3].value):
            arrival=time_value(row,'arrival');departure=time_value(row,'departure')
            for value in (arrival,departure):
                if value is not None:require(value>=previous,'Nonchronological planned schedule');previous=value
            dwell=float(c.text(row.contents[8].value))
            require(math.isfinite(dwell) and dwell>=0,'Invalid saved dwell')
            if arrival is not None and departure is not None and row.contents[10].value&1:require(departure-arrival>=dwell,'Planned stop shorter than saved dwell')

def apply_batch(blobs,operations):
    """Return (all six immutable output blobs, report), only after all checks succeed."""
    require(type(blobs)is dict and set(blobs)==CATALOGS and all(type(x)is bytes for x in blobs.values()),'Exactly six immutable current catalog blobs required')
    require(type(operations)is list and 1<=len(operations)<=100,'Expected 1..100 operations')
    from . import engine_batch,course_batch,timetable_batch
    modules={'update_engines':engine_batch,'update_courses':course_batch,'shift_timetable_rows':timetable_batch}
    for spec in operations:
        require(type(spec)is dict and spec.get('kind') in modules,'Unknown batch operation')
        modules[spec['kind']].validate_spec(spec)
    decoded={k:w.load_next_compatible(v) for k,v in blobs.items()};data={k:v[0] for k,v in decoded.items()};context=Context(data)
    refs(data);schedule_checks(data,operations)
    for spec in operations:
        k,chosen=targets(data,spec)
        expected=spec.get('names',spec.get('course_ids'))
        if k!='timetable':require(len(chosen)==len(expected),'Selected exact identity missing')
        else:
            require(bool(chosen),'No timetable rows selected')
            require(set(expected)<={c.text(o.contents[0].value) for o in c.course_items(data['courses'])},'Unknown selected Course')
    require(sum(len(targets(data,s)[1]) for s in operations)<=10000,'Batch target budget exceeds 10000');ownership(data,operations);before_mask=masks(data,operations);before={k:protected(v,before_mask[k]) for k,v in data.items()}
    reports=[]
    for spec in operations:reports.append(modules[spec['kind']].apply(context,spec))
    refs(data);schedule_checks(data,operations);after_mask=masks(data,operations)
    for k in data:require(protected(data[k],after_mask[k])==before[k],'Out-of-scope graph/reference modification: '+k)
    changed={targets(data,s)[0] for s in operations};output={k:w.dump_verified(data[k],decoded[k][1]) if k in changed else blobs[k] for k in data}
    fresh={k:w.load_next_compatible(v)[0] for k,v in output.items()};refs(fresh);fm=masks(fresh,operations)
    for spec in operations:
        _,old=targets(data,spec);_,new=targets(fresh,spec)
        require(len(old)==len(new),'Fresh selection count mismatch')
        for (a,slots),(b,_) in zip(old,new):
            if spec['kind']=='update_engines' and 'understands_radio' in spec:slots[(11,0)]='bit4'
            for i,j in slots:
                x=a.contents[i].values[j];y=b.contents[i].values[j]
                if isinstance(x,w.GenericArchivedObject):x=c.text(x);y=c.text(y)
                elif a.contents[i].encodings[j]==b'f':x=struct.unpack('>f',struct.pack('>f',x))[0]
                require(x==y,'Fresh selected field mismatch')
    for k in fresh:require(protected(fresh[k],fm[k])==before[k],'Fresh-reload protected graph mismatch: '+k)
    return output,{'validation_scope':'current_catalog_references','validated_catalogs':sorted(CATALOGS),'operations':reports,'changed_files':sorted(k for k in output if output[k]!=blobs[k]),'protected_graph_and_aliases_verified':True,'protected_graph_sha256':{k:hashlib.sha256(repr(before[k]).encode()).hexdigest() for k in sorted(before)},'checks_performed':['strict current shapes','real catalog name references','contiguous row indices','interval cycles','connection owners/targets/stations','complete incoming-edge inventory','selected entity and mutable array ownership','planned chronology and dwell for shifted courses','masked full-graph and alias preservation before and fresh reload','selected field fresh readback','unchanged catalog bytes'],'source_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in blobs.items()},'output_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in output.items()},'unvalidated_domains':['infrastructure_topology','routing','simulation','run_window'],'native_application_started':False,'complete_project_validated':False}
