"""Current persisted graph functions; no runtime expansion or GUI equivalence.
Import with frozen typedstream_writer on PYTHONPATH (or inject compatible codec).
"""
import hashlib
from . import writer as w

class Unsupported(ValueError): pass
class ExpectedRspIDError(Unsupported):
    def __init__(self,highwater):
        self.highestGivenRspID=highwater;self.expected_fresh_id=highwater+1
        super().__init__('Explicit array_id must equal highestGivenRspID + 1 = '+str(self.expected_fresh_id)+'; historical ID reuse forbidden')


SHAPES = {
 'OTRoute': ([('OTRoute',0),('OTSecurityArray',6),('OTOrgArray',2),('OTMutableArray',0),('NSObject',0)], ['@','@','ii','@','@','iiiiii','iff','@','ff','i','iii','i','@@@']),
 'OTPath': ([('OTPath',0),('OTOrgArray',2),('OTMutableArray',0),('NSObject',0)], ['@','@','ii','@','@']),
 'OTDest': ([('OTDest',1),('OTOrgArray',2),('OTMutableArray',0),('NSObject',0)], ['@','@','ii','@','@','@']),
}

def hierarchy(obj,expected):
    c=getattr(obj,'clazz',None);actual=[]
    while c:
        actual.append((c.name.decode('ascii'),c.version));c=c.superclass
        if len(actual)>10:raise Unsupported('Invalid/cyclic class chain')
    if actual!=expected:raise Unsupported('Unsupported complete class hierarchy')

def mutable_array(obj):
    hierarchy(obj,[('NSMutableArray',0),('NSArray',0),('NSObject',0)])
    return w.elements(obj)

def shape(obj,kind):
    if kind not in SHAPES: raise Unsupported('Only current Route/Path/Itinerary supported')
    parents,groups=SHAPES[kind]; c=obj.clazz; actual=[]
    while c:
        actual.append((c.name.decode('ascii'),c.version));c=c.superclass
        if len(actual)>10:raise Unsupported('Invalid class chain')
    if actual!=parents or [''.join(e.decode('ascii') for e in g.encodings) for g in obj.contents]!=groups:
        raise Unsupported('Unsupported class version or field layout')
    if any(len(g.encodings)!=len(g.values) for g in obj.contents):raise Unsupported('Malformed group')
    return obj

def string(obj):
    hierarchy(obj,[('NSString',1),('NSObject',0)])
    if w.kind(obj)!='NSString' or obj.clazz.version!=1 or len(obj.contents)!=1 or obj.contents[0].encodings!=[b'+']:
        raise Unsupported('Expected current NSString v1')
    return w.string(obj)

def fresh_string(template,value):
    string(template)
    if not isinstance(value,str):raise Unsupported('Description must be a string; empty clears')
    try:raw=value.encode('utf-8')
    except UnicodeError as e:raise Unsupported('Invalid Unicode') from e
    if b'\0' in raw:raise Unsupported('Embedded NUL unsupported')
    
    if len(raw)>1048576:raise Unsupported('Interface text safety limit: 1 MiB UTF-8')
    return w.GenericArchivedObject(template.clazz,None,[w.TypedValue(b'+',raw)])

def select(root,kind,name,array_id=None,start_id=None):
    if kind not in SHAPES:raise Unsupported('Unknown kind')
    matches=[]
    for o in w.objects(root):
        if w.kind(o)!=kind:continue
        shape(o,kind)
        if string(o.contents[1].value)!=name:continue
        if array_id is not None and o.contents[2].values[0]!=array_id:continue
        if start_id is not None and o.contents[2].values[1]!=start_id:continue
        matches.append(o)
    if len(matches)!=1:raise Unsupported('Identity must resolve exactly once in this archive')
    return matches[0]

def info(obj):
    kind=w.kind(obj);shape(obj,kind)
    result={'class':kind,'version':obj.clazz.version,'name':string(obj.contents[1].value),
            'array_id':obj.contents[2].values[0],'start_id':obj.contents[2].values[1],
            'description':string(obj.contents[3].value),'persisted_object_count':len(w.elements(obj.contents[0].value))}
    if kind in ('OTPath','OTDest'):
        refs=[]
        for row in mutable_array(obj.contents[4].value):
            expected='OTArrayInfo' if kind=='OTPath' else 'OTArrayExtInfo'
            hierarchy(row,([('OTArrayExtInfo',0)] if kind=='OTDest' else [])+[('OTArrayInfo',0),('NSObject',0)])
            enc=['@','ii']+(['@'] if kind=='OTDest' else [])
            if w.kind(row)!=expected or row.clazz.version!=0 or [''.join(e.decode() for e in g.encodings) for g in row.contents]!=enc:raise Unsupported('Unsupported reference info shape')
            d={'name':string(row.contents[0].value),'array_id':row.contents[1].values[0],'start_id':row.contents[1].values[1]}
            if kind=='OTDest':d['document']=string(row.contents[2].value)
            refs.append(d)
        result['saved_references']=refs
        result['reference_resolution']='not expanded; cross-document references are inspection-only'
    return result

def inspect_archive(data,kind,name,array_id=None,start_id=None):
    root,_=w.load(data)
    return info(select(root,kind,name,array_id,start_id))

def set_description(data,kind,name,description,array_id=None,start_id=None):
    """Pure bytes transaction: errors return no replacement archive; caller commits.
    A new NSString prevents accidental edits to aliases of the old description.
    This operates on the fresh persisted graph and preserves its saved refs.
    """
    root,version=w.load(data);obj=select(root,kind,name,array_id,start_id)
    before=info(obj);new=fresh_string(obj.contents[3].value,description)
    obj.contents[3].value=new
    output=w.dump_verified(root,version)
    actual=inspect_archive(output,kind,name,array_id,start_id)
    if actual!={**before,'description':description}:raise Unsupported('Reload verification failed')
    return output,{'operation':'set_array_description','function':'0x52c2c8','before':before,'after':actual,
                   'input_sha256':hashlib.sha256(data).hexdigest(),'output_sha256':hashlib.sha256(output).hexdigest(),
                   'native_gui_or_simulation_verified':False}

def clone(obj):
    return w.GenericArchivedObject(obj.clazz,None,[w.TypedGroup(list(g.encodings),list(g.values)) for g in obj.contents])

def array_like(template,items):
    mutable_array(template)
    obj=clone(template);w.set_elements(obj,list(items));return obj


_COUNTER_ROLES={
 'OTSigInd':([('OTSigInd',0),('NSObject',0)],['i','@']),
 'OTElement':([('OTElement',0),('OTGraphicModel',1),('NSObject',0)],['i','f','f','f','i','i','@','@']),
 'OTEdgeModel':([('OTEdgeModel',3),('OTGraphicModel',1),('NSObject',0)],['i','f','f','f','i','i','@','@','@','iiffii','ff','i','@','@','@','@','@','@','@','@','@']),
 'OTSignalModel':([('OTSignalModel',11),('OTGraphicModel',1),('NSObject',0)],['i','f','f','f','i','i','@','@','iii','iiii','@','i','i','@','@','@','f']),
}
def guard_counter_references(root,owner):
    from .graph_references import reference_inventory
    objects,counts=reference_inventory(root)
    if counts[id(root)]:raise Unsupported('Shared document root counter ownership unsupported')
    def role_shape(obj):
        kind=w.kind(obj)
        if kind=='OTRoute':shape(obj,kind);return
        chain,enc=_COUNTER_ROLES[kind];hierarchy(obj,chain)
        if [b''.join(g.encodings).decode() for g in obj.contents]!=enc or any(len(g.values)!=len(g.encodings) for g in obj.contents):raise Unsupported('Unsupported current counter reference role layout')
    accepted=0
    for obj in objects:
        edges=[(i,j) for i,g in enumerate(obj.contents) for j,v in enumerate(g.values) if v is owner]
        if not edges:continue
        kind=w.kind(obj)
        if kind=='NSMutableArray':
            mutable_array(obj)
            parents=[(par,i,j) for par in objects for i,g in enumerate(par.contents) for j,v in enumerate(g.values) if v is obj]
            if len(parents)!=counts[id(obj)] or not parents:raise Unsupported('Unknown nested owner of End reference array')
            for par,i,j in parents:
                pk=w.kind(par)
                if par is root and (i,j)==(2,0):continue
                if (pk=='OTElement' and (i,j)==(7,0)) or (pk=='OTRoute' and (i,j) in ((0,0),(12,0))):role_shape(par)
                else:raise Unsupported('Unknown owner of End reference array')
        elif kind in ('OTSigInd','OTEdgeModel','OTSignalModel'):
            role_shape(obj)
            allowed={'OTSigInd':{(1,0)},'OTEdgeModel':{(7,0),(8,0)},'OTSignalModel':{(7,0)}}[kind]
            if not set(edges)<=allowed:raise Unsupported('Unknown direct End counter reference slot')
        else:raise Unsupported('Unknown incoming owner of End counter')
        accepted+=len(edges)
    if accepted!=counts[id(owner)]:raise Unsupported('Nested incoming End counter reference unsupported')

def create_local_path(data,name,array_id,routes,description=''):
    """Compose native init/add/rebuild/save data behavior in ONE current document.
    Caller confirms fresh ID = highestGivenRspID + 1; native high-water mark advances.
    Existing PathList required. Cross-document routes and existing identity reject.
    routes=[{'name':str,'array_id':int,'start_id':int},...].
    """
    root,version=w.load(data)
    if w.kind(root)!='OTDocument' or root.clazz.version!=4 or len(root.contents)!=21 or root.contents[2].encodings!=[b'@']:raise Unsupported('Requires one current OTDocument v4 archive')
    hierarchy(root,[('OTDocument',4),('NSObject',0)])
    local_models=mutable_array(root.contents[2].value)
    ids=[]
    for model in local_models:
        if not model.contents or model.contents[0].encodings!=[b'i'] or type(model.contents[0].value)!=int:raise Unsupported('Invalid document model identity')
        ids.append(model.contents[0].value)
    if len(set(ids))!=len(ids):raise Unsupported('Duplicate model identity in document')
    if not isinstance(name,str) or not name:raise Unsupported('Nonempty explicit Path name required')
    if type(array_id)!=int or not 0<=array_id<=2147483647:raise Unsupported('Path ID requires nonnegative signed int32')
    if not isinstance(routes,list) or not 1<=len(routes)<=10000:raise Unsupported('Interface route count range 1..10000')
    chain=[];nodes=[]
    for ref in routes:
        if not isinstance(ref,dict) or set(ref)!={'name','array_id','start_id'} or type(ref['array_id'])!=int or type(ref['start_id'])!=int:raise Unsupported('Exact Route name/ID/start required')
        route=select(root,'OTRoute',ref['name'],ref['array_id'],ref['start_id'])
        es=mutable_array(route.contents[0].value)
        if route.contents[5].values[4]!=-1 or len(es)<2 or any(w.kind(e)!='OTEndModel' or e.clazz.version!=7 for e in es):raise Unsupported('Cross-document/continuation/empty Route unsupported')
        if any(e not in local_models for e in es):raise Unsupported('Route references an End outside this document model collection')
        for e in es:hierarchy(e,[('OTEndModel',7),('OTGraphicModel',1),('NSObject',0)])
        end_enc=['i','f','f','f','i','i','@','@','i','@','@','@','@','@','f','@','@','@','@','i','i','f','i','ii']
        if any([''.join(x.decode() for x in g.encodings) for g in e.contents]!=end_enc for e in es):raise Unsupported('Unsupported current End field layout')
        if es[0].contents[0].value!=ref['start_id']:raise Unsupported('Route start identity mismatch')
        if route not in w.elements(es[0].contents[15].value.contents[0].value):raise Unsupported('Route not in owning End list')
        if chain and nodes[-1][-1] is not es[0]:raise Unsupported('Disconnected Route chain')
        if route in chain:raise Unsupported('Repeated Route unsupported')
        chain.append(route);nodes.append(es)
    owner=nodes[0][0]
    if any(e is owner for es in nodes for e in es[1:]):raise Unsupported('Cyclic Path unsupported')
    plist=owner.contents[17].value
    if w.kind(plist)!='OTPathList' or plist.clazz.version!=0 or len(plist.contents)!=1 or plist.contents[0].encodings!=[b'@']:raise Unsupported('Existing current PathList required')
    if any(e is not owner and w.kind(e)=='OTEndModel' and e.contents[17].value is plist for e in local_models):raise Unsupported('Aliased PathList ownership unsupported')
    hierarchy(plist,[('OTPathList',0),('OTMutableArray',0),('NSObject',0)])
    target_array=plist.contents[0].value
    from .graph_references import incoming_counts
    counts=incoming_counts(root)
    if counts[id(plist)]!=1:raise Unsupported('Aliased PathList wrapper unsupported')
    aliases=counts[id(target_array)]
    if aliases!=1:raise Unsupported('Aliased PathList backing array unsupported')
    existing=mutable_array(target_array)
    if not existing:raise Unsupported('Existing nonempty PathList required for verified class template')
    template=shape(existing[0],'OTPath');info(template)
    guard_counter_references(root,owner)
    highwater=owner.contents[19].value
    if type(highwater) is not int or not 0<=highwater<2147483647:raise Unsupported('highestGivenRspID must be nonnegative int32 below maximum; overflow refused')
    fresh_id=highwater+1
    allocated=[]
    for idx in (15,16,17):
        wrapper=owner.contents[idx].value
        if wrapper:
            for o in w.elements(wrapper.contents[0].value):
                ident=o.contents[2].values[0]
                if type(ident) is not int or not 0<=ident<=2147483647:raise Unsupported('Invalid existing allocated R/S/P ID')
                allocated.append(ident)
    if len(allocated)!=len(set(allocated)):raise Unsupported('Conflicting allocated R/S/P IDs at owner')
    if allocated and max(allocated)>highwater:raise Unsupported('highestGivenRspID is below an already allocated R/S/P ID')
    if fresh_id in allocated:raise Unsupported('Fresh R/S/P ID conflicts with an existing object')
    if array_id!=fresh_id:raise ExpectedRspIDError(highwater)
    for o in w.objects(root):
        if w.kind(o)=='OTPath' and string(o.contents[1].value)==name:raise Unsupported('Path name already exists in document')
        if w.kind(o)=='OTArrayExtInfo' and (string(o.contents[0].value)==name or o.contents[1].values==[array_id,owner.contents[0].value]):raise Unsupported('Existing saved Path reference would be captured')
    refs=w.elements(template.contents[4].value)
    if not refs:raise Unsupported('Existing current OTArrayInfo template required')
    new=clone(template);new.contents[0].value=array_like(template.contents[0].value,chain[:1])
    new.contents[1].value=fresh_string(template.contents[1].value,name)
    new.contents[2].values=[array_id,owner.contents[0].value]
    new.contents[3].value=fresh_string(template.contents[3].value,description)
    infos=[]
    for route in chain:
        item=clone(refs[0]);item.contents[0].value=route.contents[1].value
        item.contents[1].values=list(route.contents[2].values);infos.append(item)
    new.contents[4].value=array_like(template.contents[4].value,infos)
    
    owner.contents[19].value=fresh_id
    
    w.set_elements(plist.contents[0].value,existing+[new])
    output=w.dump_verified(root,version);actual=inspect_archive(output,'OTPath',name,array_id,owner.contents[0].value)
    expected=[{'name':string(r.contents[1].value),'array_id':r.contents[2].values[0],'start_id':r.contents[2].values[1]} for r in chain]
    if actual['persisted_object_count']!=1 or actual['saved_references']!=expected:raise Unsupported('Saved first-object/full-info verification failed')
    return output,{'operation':'create_local_path','functions':['0x559398','0x55a050','0x4c4770','0x55a600','0x4c7188'],
                   'allocator':{'function':'0x4c7188','owner_end_id':owner.contents[0].value,'field':'highestGivenRspID','group':19,'encoding':'i','before':highwater,'after':fresh_id,'allocated_id':fresh_id},
                   'created':actual,'document_scope':'single archive; project-wide uniqueness is caller precondition',
                   'native_gui_or_simulation_verified':False}
