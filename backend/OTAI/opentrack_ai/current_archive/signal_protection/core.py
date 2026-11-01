"""Finite single-document Route protection-data configuration and resource report.
No original executable, dispatch simulation or safety certification.
"""
import hashlib,itertools,math,struct
from opentrack_ai.current_archive import writer as w,path_functions as f,route_factory as rf
from opentrack_ai.current_archive.zero_generation import native_signal_routes as n

Unsupported=f.Unsupported
require=rf.require
MAX_ROUTES=256

def guard_route_capacity(current_count):
    require(type(current_count)==int and 0<=current_count<MAX_ROUTES,'API supports at most 256 Routes per archive; not a native limit')

KEYS={'route','array_id','start_id','release_distance_m','announce_distance_m','release_time_s','reserve_time_s','reservation_distance_m','use_reservation_distance','use_release_distance','approach_length_m','approach_speed_kmh','release_groups','reserve_previous'}

def intval(x):
    require(type(x)==int and 0<=x<=2147483647,'Nonnegative int32 required');return x

def real(x):
    require(type(x) in (int,float) and math.isfinite(x) and 0<=x<=1e7,'Finite nonnegative float32 API range required')
    y=struct.unpack('<f',struct.pack('<f',x))[0]
    require(math.isfinite(y) and (x==0 or y>0),'Float32 overflow/underflow');return y

def boolean(x):
    require(type(x)==bool,'Explicit boolean required');return x

def load(data):
    require(type(data)==bytes and 0<len(data)<=64*1024*1024,'Bounded archive bytes required')
    root,v,models,byid=n.document(data);n.validate_topology(root)
    require(not any(w.kind(o)=='OTConnModel' for o in w.objects(root)),'Cross-document protection not implemented')
    routes=[]
    for o in w.objects(root):
        if w.kind(o)=='OTRoute':
            guard_route_capacity(len(routes))
            f.shape(o,'OTRoute');ids=[e.contents[0].value for e in f.mutable_array(o.contents[0].value)]
            rf.validate_chain(root,o,ids)
            require(len(ids)>=2 and len(set(ids))==len(ids),'Simple nonrepeated End route required')
            require(o.contents[11].value in (0,1),'Unknown reservationWithPrevious')
            require(all(type(x)==int and x>=0 for x in o.contents[5].values[:4]),'Invalid security distances/times')
            require(type(o.contents[10].values[0])==int and o.contents[10].values[0]>=0 and all(type(x)==int and x in (0,1) for x in o.contents[10].values[1:]),'Invalid security flags')
            require(all(isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x) and x>=0 for x in o.contents[8].values),'Invalid approach parameters')
            groups=[e.contents[0].value for e in f.mutable_array(o.contents[12].values[0])]
            require(groups and groups[0]==ids[0] and groups[-1]==ids[-1] and [ids.index(i) for i in groups]==sorted(ids.index(i) for i in groups),'Release grouping must be ordered and cover endpoints')
            routes.append(o)
    require(routes,'No supported Route found')
    identities=[(r.contents[2].values[1],r.contents[2].values[0]) for r in routes]
    require(len(identities)==len(set(identities)),'Duplicate route identity')
    return root,v,models,byid,routes

def detail(root,r):
    ids=[e.contents[0].value for e in f.mutable_array(r.contents[0].value)]
    _,nodes,edges,signals,_=rf.validate_chain(root,r,ids)
    return {'name':f.string(r.contents[1].value),'array_id':r.contents[2].values[0],'start_id':r.contents[2].values[1],
        'end_ids':ids,'edge_ids':[e.contents[0].value for e in edges],
        'safety_element_ids':sorted({e.contents[7].value.contents[0].value for e in nodes}),
        'release_distance_m':r.contents[5].values[0],'announce_distance_m':r.contents[5].values[1],
        'release_time_s':r.contents[5].values[2],'reserve_time_s':r.contents[5].values[3],
        'reservation_distance_m':r.contents[10].values[0],'use_reservation_distance':bool(r.contents[10].values[1]),'use_release_distance':bool(r.contents[10].values[2]),
        'approach_length_m':r.contents[8].values[0],'approach_speed_kmh':r.contents[8].values[1],
        'release_group_start_end_ids':[e.contents[0].value for e in f.mutable_array(r.contents[12].values[0])],
        'reserve_previous':bool(r.contents[11].value)}

def inspect_protection(data):
    root,v,models,byid,routes=load(data)
    rows=[detail(root,r) for r in routes];pairs=[]
    for a,b in itertools.combinations(rows,2):
        es=sorted(set(a['edge_ids'])&set(b['edge_ids']));ss=sorted(set(a['safety_element_ids'])&set(b['safety_element_ids']))
        pairs.append({'a':[a['start_id'],a['array_id']],'b':[b['start_id'],b['array_id']], 'shared_edge_ids':es,'shared_safety_element_ids':ss,'potential_shared_resource':bool(es or ss)})
    signals=[]
    for s in models:
        if w.kind(s)!='OTSignalModel':continue
        e=s.contents[7].value;typ=s.contents[8].values[0]
        signals.append({'model_id':s.contents[0].value,'end_id':e.contents[0].value,'related_end_id':e.contents[8].value,
            'signal_type_code':typ,'main_signal_type_code':s.contents[8].values[1],'location_code':s.contents[8].values[2],
            'show_type_code':s.contents[9].values[0],'native_main_predicate':typ in (1,2,24,25,26),
            'direction_encoding':'attached directional End, not graphic rotation'})
    return {'domain':'single_document_simple_routes','routes':rows,'signals':signals,'resource_pairs':pairs,
        'input_sha256':hashlib.sha256(data).hexdigest(),'runtime_safety_verified':False,'deadlock_free_verified':False,
        'limitations':['Shared resources are conservative static candidates, not dispatch conflicts.','No overlap/protection-zone construction, moving-block runtime or cross-document security.']}

def configure_route(data,spec):
    require(type(spec)==dict and set(spec)==KEYS,'Exact complete configuration keys required')
    require(type(spec['route'])==str and spec['route'] and '\0' not in spec['route'],'Explicit route name required')
    intval(spec['array_id']);intval(spec['start_id'])
    for key in ('release_distance_m','announce_distance_m','release_time_s','reserve_time_s','reservation_distance_m'):intval(spec[key])
    for key in ('use_reservation_distance','use_release_distance','reserve_previous'):boolean(spec[key])
    length=real(spec['approach_length_m']);speed=real(spec['approach_speed_kmh'])
    require((length==0 and speed==0) or (length>0 and speed>0),'Approach disabled requires both zero; enabled requires positive length/speed')
    require(spec['release_groups'] in ('global','each_end'),'Only audited native group/ungroup modes')
    root,v,*_=load(data);r=f.select(root,'OTRoute',spec['route'],spec['array_id'],spec['start_id']);before=detail(root,r)
    old={i:r.contents[i] for i in (5,8,10,11,12)}
    for i in old:r.contents[i]=w.TypedGroup(list(old[i].encodings),list(old[i].values))
    r.contents[5].values[:4]=[spec[k] for k in ('release_distance_m','announce_distance_m','release_time_s','reserve_time_s')]
    r.contents[8].values[:]=[length,speed]
    r.contents[10].values[:]=[spec['reservation_distance_m'],int(spec['use_reservation_distance']),int(spec['use_release_distance'])]
    r.contents[11].value=int(spec['reserve_previous'])
    nodes=f.mutable_array(r.contents[0].value)
    r.contents[12].values[0]=f.array_like(old[12].values[0],[nodes[0],nodes[-1]] if spec['release_groups']=='global' else nodes)
    output=w.dump_verified(root,v);rr,vv,*_=load(output);after=detail(rr,f.select(rr,'OTRoute',spec['route'],spec['array_id'],spec['start_id']))
    
    for i,g in old.items():r.contents[i]=g
    orig,ov=w.load(data)
    require(w.dump_verified(root,v)==w.dump_verified(orig,ov),'Non-target graph mutation')
    return output,{'operation':'configure_route_protection_data','input_sha256':hashlib.sha256(data).hexdigest(),'before':before,'after':after,'output_sha256':hashlib.sha256(output).hexdigest(), 'inspection':inspect_protection(output),'native_runtime_verified':False}
