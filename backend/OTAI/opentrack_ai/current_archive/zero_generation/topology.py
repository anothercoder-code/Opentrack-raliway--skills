"""Current-format synthetic railway topology, generated from an explicit spec.

Pure bytes. The source document supplies only an unchanged opaque header; all
railway objects are newly built. This does not run OpenTrack or grant a licence.
"""
from __future__ import annotations
import hashlib
import math
import struct
from opentrack_ai.current_archive import writer as w
from opentrack_ai.current_archive import path_functions as pf, route_factory as rf
from opentrack_ai.current_archive import graph_references as gr
from opentrack_ai.current_archive.graphic_alignment import validate_alignment_pair

class TopologyError(ValueError): pass

def need(ok, msg):
    if not ok: raise TopologyError(msg)

def exact(value, lo, hi, name):
    need(type(value) is int and lo <= value <= hi, name + ': integer outside guarded range')
    return value

def flt(value, name):
    need(type(value) in (int, float) and math.isfinite(value), name + ': finite numeric value required')
    try: raw = struct.pack('<f', value)
    except (OverflowError, struct.error) as ex: raise TopologyError(name + ': float32 overflow') from ex
    result = w.WireFloat(raw, b'f', 'little')
    need(math.isfinite(result), name + ': float32 overflow')
    return result

def text(value, name):
    need(type(value) is str and '\x00' not in value and len(value.encode('utf8')) <= 4096, name + ': bounded NUL-free text required')
    return value

def signature(clazz):
    out=[]
    while clazz:
        out.append((clazz.name,clazz.version));clazz=clazz.superclass
    return tuple(out)

DOC_ENC=['i','i','@','i','i','@','@','@','ffff','ffff','ffff','f','@','@','ffff','iii','ff','@','@','@','@']
CLASS_SHAPES={
 'OTEndModel':(7,rf.END,True,False),
 'OTEdgeModel':(3,rf.EDGE,True,False),
 'OTElement':(0,['i','f','f','f','i','i','@','@'],True,False),
 'OTSpeed':(0,['@','i','i','i'],False,False),
 'OTRouteList':(0,['@'],False,True),
 'OTShuntingList':(0,['@'],False,True),
 'OTPathList':(0,['@'],False,True),
}

class Builder:
    def __init__(self, shapes):
        source, self.stream_version = w.load_next_compatible(shapes)
        need(w.kind(source)=='NSMutableArray','Shape container must be mutable array')
        self.protos={}
        for obj in pf.mutable_array(source):
            name=w.kind(obj)
            need(name not in self.protos, 'Duplicate shape name')
            self.protos[name]=obj
        for name,(ver,enc,g,m) in CLASS_SHAPES.items():
            need(name in self.protos,'Missing shape '+name)
            rf.layout(self.protos[name],name,ver,enc,graphic=g,mutable=m)
        for name,chain in [
            ('NSMutableArray',[('NSMutableArray',0),('NSArray',0),('NSObject',0)]),
            ('NSMutableDictionary',[('NSMutableDictionary',0),('NSDictionary',0),('NSObject',0)]),
            ('NSString',[('NSString',1),('NSObject',0)]),
        ]: pf.hierarchy(self.protos[name],chain)
        self.models=[];self.high=-1

    def obj(self,name,groups):
        return w.GenericArchivedObject(self.protos[name].clazz,contents=[w.TypedGroup([x.encode() for x in enc],vals) for enc,vals in groups])

    def string(self,value): return self.obj('NSString',[('+',[value.encode('utf8')])])
    def array(self,items=()): return self.obj('NSMutableArray',[('i',[len(items)])]+[('@',[x]) for x in items])
    def wrapper(self,name): return self.obj(name,[('@',[self.array()])])
    def graphic(self,name,tail,loc=(0.,0.,0,0)):
        self.high+=1
        need(self.high<2147483647,'Graphic ID exhausted')
        x,y,alignment_x,alignment_y=loc
        validate_alignment_pair(alignment_x,alignment_y)
        out=self.obj(name,[('i',[self.high]),('f',[flt(0.,'angle')]),('f',[flt(x,'x')]),('f',[flt(y,'y')]),('i',[alignment_x]),('i',[alignment_y]),('@',[None])]+tail)
        self.models.append(out)
        return out

    def vertex(self, spec):
        orient=spec['orientation']
        need(orient in ('horizontal','vertical'),'Explicit horizontal/vertical orientation required')
        codes=((1,0),(2,0)) if orient=='horizontal' else ((0,4),(0,3))
        ends=[]
        for side in (0,1):
            end=self.graphic('OTEndModel',[
                ('@',[None]),('i',[-1]),('@',[None]),('@',[None]),('@',[None]),('@',[None]),('@',[None]),
                ('f',[flt(-99999.,'locality')]),('@',[self.wrapper('OTRouteList')]),
                ('@',[self.wrapper('OTShuntingList')]),('@',[self.wrapper('OTPathList')]),
                ('@',[self.string(spec['names'][side])]),('i',[-1]),('i',[1]),('f',[flt(0.,'switchTime')]),('i',[0]),
                ('ii',[int(spec['insulated_joint'][side]),int(spec['axle_counter'][side])])
            ],(spec['x'],spec['y'],*codes[side]))
            ends.append(end)
        for side,end in enumerate(ends): end.contents[8].value=ends[1-side].contents[0].value
        
        for end in ends:
            elem=self.graphic('OTElement',[('@',[self.array([end])])])
            end.contents[7].value=elem
        return ends

    def union(self,left,right):
        target=left.contents[7].value;old=right.contents[7].value
        if target is old:return
        members=pf.mutable_array(target.contents[7].value)
        for end in pf.mutable_array(old.contents[7].value):
            need(end not in members,'Duplicate safety membership')
            end.contents[7].value=target;members.append(end)
        w.set_elements(target.contents[7].value,members)
        self.models.remove(old)

    def edge(self,spec,a,b):
        keys=[];dict_groups=[]
        for item in spec['speeds']:
            key=self.string(item['train_type']);keys.append(key)
            speed=self.obj('OTSpeed',[('@',[key]),('i',[item['speed12_kmh']]),('i',[item['speed21_kmh']]),('i',[0])])
            dict_groups.extend([('@',[key]),('@',[speed])])
        speed_dict=self.obj('NSMutableDictionary',[('i',[len(keys)])]+dict_groups)
        edge=self.graphic('OTEdgeModel',[
            ('@',[a]),('@',[b]),('iiffii',[spec['track_type'],spec['length_m'],flt(spec['radius_m'],'radius_m'),flt(spec['gradient_per_mille'],'gradient'),spec['loop_type'],spec['dlink_type']]),
            ('ff',[flt(100.,'wire cross-section'),flt(40.,'tunnel cross-section')]),
            ('i',[int(spec['equal_speed'])+2*int(spec['rack_rail'])]),('@',[self.string(spec['remark'])]),('@',[None]),('@',[None]),
            ('@',[self.array(keys)]),('@',[speed_dict]),('@',[None]),('@',[None]),('@',[self.string(spec['track_name'])]),('@',[self.string(spec['line_name'])])])
        for end,other in ((a,b),(b,a)):
            slot=9 if end.contents[9].value is None else 10
            need(end.contents[slot].value is None,'Third Edge at one half-vertex forbidden')
            end.contents[slot].value=edge
            self.union(end,other)
        return edge


def validate_spec(spec):
    need(type(spec) is dict and set(spec)=={'vertices','edges'},'Exact vertices/edges spec required')
    vs=spec['vertices'];es=spec['edges']
    need(type(vs) is list and 1<=len(vs)<=1000,'1..1000 vertices required')
    need(type(es) is list and len(es)<=2000,'At most 2000 edges')
    vkeys=set();ekeys=set();degrees={};pairs=set()
    for v in vs:
        need(type(v) is dict and set(v)=={'key','x','y','orientation','names','insulated_joint','axle_counter'},'Exact vertex fields required')
        key=text(v['key'],'vertex key');need(key and key not in vkeys,'Unique nonempty vertex key required');vkeys.add(key)
        flt(v['x'],'x');flt(v['y'],'y');need(v['orientation'] in ('horizontal','vertical'),'Unknown orientation')
        need(type(v['names']) is list and len(v['names'])==2,'Two End names required')
        for s in v['names']:text(s,'End name')
        for field in ('insulated_joint','axle_counter'):
            need(type(v[field]) is list and len(v[field])==2 and all(type(x) is bool for x in v[field]),'Two explicit boolean detector flags required')
            need(not any(v[field]),'Detector-enabled topology outside initial verified domain')
    for e in es:
        need(type(e) is dict and set(e)=={'key','from','to','length_m','radius_m','gradient_per_mille','track_type','loop_type','dlink_type','equal_speed','rack_rail','speeds','remark','track_name','line_name'},'Exact Edge fields required')
        key=text(e['key'],'edge key');need(key and key not in ekeys,'Unique nonempty Edge key required');ekeys.add(key)
        ends=[]
        for field in ('from','to'):
            ref=e[field];need(type(ref) is list and len(ref)==2 and type(ref[0]) is str and ref[0] in vkeys,'Unknown vertex reference')
            exact(ref[1],0,1,'half-vertex side');end=tuple(ref);ends.append(end)
            degrees[end]=degrees.get(end,0)+1;need(degrees[end]<=2,'Third Edge at one half-vertex forbidden')
        need(ends[0][0]!=ends[1][0],'Edge between halves of same vertex refused')
        pair=frozenset(ends);need(pair not in pairs,'Parallel duplicate endpoint pair refused');pairs.add(pair)
        exact(e['length_m'],1,2147483647,'length_m');flt(e['radius_m'],'radius');flt(e['gradient_per_mille'],'gradient')
        for field in ('track_type','loop_type','dlink_type'):
            exact(e[field],1,1,field)  
        for field in ('equal_speed','rack_rail'):need(type(e[field]) is bool,'Explicit Edge boolean required')
        for field in ('remark','track_name','line_name'):text(e[field],field)
        speeds=e['speeds'];need(type(speeds) is list and 1<=len(speeds)<=100,'1..100 explicit train-type speeds required')
        st=set()
        for s in speeds:
            need(type(s) is dict and set(s)=={'train_type','speed12_kmh','speed21_kmh'},'Exact speed fields required')
            key=text(s['train_type'],'train type')
            need(key.isascii() and key.isdigit() and str(int(key))==key and key not in st,'Unique canonical nonnegative train-type string required');st.add(key)
            exact(s['speed12_kmh'],1,1000,'speed12');exact(s['speed21_kmh'],1,1000,'speed21')
            need(not e['equal_speed'] or s['speed12_kmh']==s['speed21_kmh'],'equal_speed conflicts with directional table')


def doc_layout(root):
    pf.hierarchy(root,[('OTDocument',4),('NSObject',0)])
    need([''.join(x.decode() for x in g.encodings) for g in root.contents]==DOC_ENC,'Current Document4 layout required')
    need(type(root.contents[0].value) is int and root.contents[0].value==17,'Current internal document version17 required')
    exact(root.contents[1].value,0,15,'current document flags')
    need(gr.reference_inventory(root)[1][id(root)]==0,'Aliased document root refused')
    pf.mutable_array(root.contents[2].value)
    rf.layout(root.contents[5].value,'OTMutableArray',0,['@'])
    pf.mutable_array(root.contents[5].value.contents[0].value)
    rf.wrapper(root.contents[12].value,'OTOccInfoList')
    need(root.contents[13].value is None,'Unexpected archived print-info reference')
    for i in (17,18,19,20):text(w.string(root.contents[i].value),'Document string')


def blank_container(blob,builder):
    root,version=w.load_next_compatible(blob);doc_layout(root)
    old_models=pf.mutable_array(root.contents[2].value)
    removed_count=len(old_models)
    
    root.contents[2].value=builder.array()
    for i,name in ((5,'OTMutableArray'),(12,'OTOccInfoList')):
        old=root.contents[i].value
        root.contents[i].value=w.GenericArchivedObject(old.clazz,contents=[w.TypedValue(b'@',builder.array())])
    allowed={'OTDocument','OTMutableArray','OTOccInfoList','NSMutableArray','NSString','NSColor','NSMutableData','NSData'}
    objs,counts=gr.reference_inventory(root)
    need(all(w.kind(o) in allowed for o in objs),'Unknown or old-graph reference outside cleared containers')
    need(not any(o in old_models for o in objs),'Old model still reachable from header')
    need(counts[id(root)]==0,'Header cycles back to root')
    
    seen={}
    for o in objs+list(builder.protos.values()):
        k=o.clazz.name;sig=signature(o.clazz)
        need(k not in seen or seen[k]==sig,'Class namespace collision')
        seen[k]=sig
    return root,version,removed_count


def validate_network(root):
    doc_layout(root);models,byid=rf.document(root)
    need(all(w.kind(o) in {'OTEndModel','OTElement','OTEdgeModel'} for o in models),'Unexpected network object')
    ends=[o for o in models if w.kind(o)=='OTEndModel'];edges=[o for o in models if w.kind(o)=='OTEdgeModel'];elems=[o for o in models if w.kind(o)=='OTElement']
    for ident in byid:exact(ident,0,2147483646,'model ID')
    for end in ends:
        rf.layout(end,'OTEndModel',7,rf.END,graphic=True)
        other=byid.get(end.contents[8].value)
        need(other is not end and other in ends and other.contents[8].value==end.contents[0].value,'Nonreciprocal related End')
        need(end.contents[2].value==other.contents[2].value and end.contents[3].value==other.contents[3].value,'Related End coordinate mismatch')
        need(end.contents[7].value in elems,'Missing safety element')
        for i in (9,10):
            edge=end.contents[i].value
            need(edge is None or (edge in edges and end in (edge.contents[7].value,edge.contents[8].value)),'End/Edge backreference mismatch')
        need(end.contents[9].value is not None or end.contents[10].value is None,'Second Edge without first')
        need(end.contents[9].value is None or end.contents[9].value is not end.contents[10].value,'Duplicate Edge slot')
        for i,kind in ((15,'OTRouteList'),(16,'OTShuntingList'),(17,'OTPathList')):need(rf.wrapper(end.contents[i].value,kind)==[],'New End has stale RSP')
        need(end.contents[19].value==-1,'New End RSP highwater must be -1')
    membership=[]
    for elem in elems:
        rf.layout(elem,'OTElement',0,['i','f','f','f','i','i','@','@'],graphic=True)
        members=pf.mutable_array(elem.contents[7].value)
        need(members and len(set(map(id,members)))==len(members),'Empty/duplicate Safety members')
        for end in members:need(end in ends and end.contents[7].value is elem,'Safety/End backreference mismatch')
        membership+=members
    need(len(membership)==len(ends) and set(map(id,membership))==set(map(id,ends)),'Safety membership is not partition')
    for edge in edges:
        rf.layout(edge,'OTEdgeModel',3,rf.EDGE,graphic=True)
        a,b=[edge.contents[i].value for i in (7,8)]
        need(a in ends and b in ends and a is not b,'Edge endpoint absent')
        need(edge in [a.contents[i].value for i in (9,10)] and edge in [b.contents[i].value for i in (9,10)],'Edge/End reciprocity mismatch')
        need(a.contents[7].value is b.contents[7].value,'Connected End safety elements not united')
    
    adjacency={e.contents[0].value:set() for e in ends}
    for end in ends:adjacency[end.contents[0].value].add(end.contents[8].value)
    for edge in edges:
        a,b=[edge.contents[i].value.contents[0].value for i in (7,8)]
        adjacency[a].add(b);adjacency[b].add(a)
    seen=set();components=0
    for start in adjacency:
        if start in seen:continue
        components+=1;stack=[start]
        while stack:
            node=stack.pop()
            if node in seen:continue
            seen.add(node);stack+=list(adjacency[node]-seen)
    
    cycle_rank=len(edges)-len(ends)//2+components
    return {'vertices':len(ends)//2,'half_vertices':len(ends),'edges':len(edges),'safety_elements':len(elems),'components':components,'cycle_rank':cycle_rank,'max_model_id':max(byid,default=-1)}


def generate_network(document_source: bytes, shape_source: bytes, spec: dict):
    need(type(document_source) is bytes and type(shape_source) is bytes,'Immutable source bytes required')
    validate_spec(spec);b=Builder(shape_source)
    root,version,removed=blank_container(document_source,b)
    need(version==b.stream_version,'Mixed stream versions refused')
    blank=w.dump_verified(root,version);blank_fp=w.fingerprint(root)
    vertices={v['key']:b.vertex(v) for v in spec['vertices']};edge_ids={}
    for e in spec['edges']:
        a=vertices[e['from'][0]][e['from'][1]];c=vertices[e['to'][0]][e['to'][1]]
        edge=b.edge(e,a,c);edge_ids[e['key']]=edge.contents[0].value
    w.set_elements(root.contents[2].value,b.models)
    topology=validate_network(root)
    out=w.dump_verified(root,version)
    fresh,_=w.load_next_compatible(out);need(validate_network(fresh)==topology,'Fresh graph validation mismatch')
    
    
    w.set_elements(fresh.contents[2].value,[])
    need(w.fingerprint(fresh)==blank_fp,'Non-graph header changed')
    return out,{'operation':'generate_network_from_spec','source_sha256':hashlib.sha256(document_source).hexdigest(),'shapes_sha256':hashlib.sha256(shape_source).hexdigest(),'output_sha256':hashlib.sha256(out).hexdigest(),'derived_empty_shell_sha256':hashlib.sha256(blank).hexdigest(),'source_models_removed_in_new_copy':removed,'opaque_header_unchanged':True,'licence_granted_or_modified':False,'native_simulation_executed':False,'native_application_tested':False,'topology':topology,'vertex_end_ids':{k:[e.contents[0].value for e in pair] for k,pair in vertices.items()},'edge_ids':edge_ids,'allocation_highwater':b.high,'scope':'synthetic instructional topology; no signals, routes, stations, trains or operating safety certification'}
