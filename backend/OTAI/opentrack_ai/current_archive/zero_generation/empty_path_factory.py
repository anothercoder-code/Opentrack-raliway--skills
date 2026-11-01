"""Explicit empty-PathList type-template extension of frozen current Path core.
No placeholders. Keeps existing movement/counter/owner/cycle guards.
"""
import hashlib
from opentrack_ai.current_archive import writer as w
from opentrack_ai.current_archive.path_functions import (Unsupported,hierarchy,mutable_array,select,shape,info,guard_counter_references,ExpectedRspIDError,clone,array_like,fresh_string,string,inspect_archive)
def create_local_path(data,name,array_id,routes,description='',*,template_data=None,template_name=None,template_array_id=None,template_start_id=None,expected_template_sha256=None):
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
    chain=[];nodes=[];visited_ends=set()
    for ref in routes:
        if not isinstance(ref,dict) or set(ref)!={'name','array_id','start_id'} or type(ref['array_id'])!=int or type(ref['start_id'])!=int:raise Unsupported('Exact Route name/ID/start required')
        route=select(root,'OTRoute',ref['name'],ref['array_id'],ref['start_id'])
        es=mutable_array(route.contents[0].value)
        if route.contents[5].values[4]!=-1 or len(es)<2 or any(w.kind(e)!='OTEndModel' or e.clazz.version!=7 for e in es):raise Unsupported('Cross-document/continuation/empty Route unsupported')
        if any(e not in local_models for e in es):raise Unsupported('Route references an End outside this document model collection')
        for e in es:hierarchy(e,[('OTEndModel',7),('OTGraphicModel',1),('NSObject',0)])
        end_enc=['i','f','f','f','i','i','@','@','i','@','@','@','@','@','f','@','@','@','@','i','i','f','i','ii']
        if any([''.join(x.decode() for x in g.encodings) for g in e.contents]!=end_enc for e in es):raise Unsupported('Unsupported current End field layout')
        from .loop_itinerary import validate_fixed_pair_route_links
        validate_fixed_pair_route_links(es,local_models)
        for endpoint in (es if not chain else es[1:]):
            if id(endpoint) in visited_ends:raise Unsupported('Repeated End/cyclic Path unsupported')
            visited_ends.add(id(endpoint))
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
    from opentrack_ai.current_archive.graph_references import incoming_counts
    counts=incoming_counts(root)
    if counts[id(plist)]!=1:raise Unsupported('Aliased PathList wrapper unsupported')
    aliases=counts[id(target_array)]
    if aliases!=1:raise Unsupported('Aliased PathList backing array unsupported')
    existing=mutable_array(target_array)
    external_objects=set()
    if existing:
        if template_data is not None:raise Unsupported('External template is only for genuinely empty PathList')
        template=shape(existing[0],'OTPath');info(template)
    else:
        if not isinstance(template_data,bytes) or hashlib.sha256(template_data).hexdigest()!=expected_template_sha256:raise Unsupported('Explicit current external Path template bytes/SHA required')
        template_root,_=w.load(template_data)
        hierarchy(template_root,[('OTDocument',4),('NSObject',0)])
        from .loop_itinerary import check
        check(template_root,[('OTDocument',4),('NSObject',0)],['i','i','@','i','i','@','@','@','ffff','ffff','ffff','f','@','@','ffff','iii','ff','@','@','@','@'])
        template=select(template_root,'OTPath',template_name,template_array_id,template_start_id);info(template)
        candidates=[o for o in mutable_array(template_root.contents[2].value) if w.kind(o)=='OTEndModel' and o.contents[0].value==template.contents[2].values[1]]
        if len(candidates)!=1 or template not in w.elements(candidates[0].contents[17].value.contents[0].value):raise Unsupported('External Path template not in its native owner PathList')
        external_objects={id(x) for x in w.objects(template_root)}
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
    
    baseline=w.dump_verified(root,version)
    owner.contents[19].value=fresh_id
    
    backing=plist.contents[0].value;backing.contents[0].value+=1;backing.contents.append(w.TypedValue(b'@',new))
    if external_objects & {id(x) for x in w.objects(root)}:raise Unsupported('External template retained source object dependencies')
    output=w.dump_verified(root,version);actual=inspect_archive(output,'OTPath',name,array_id,owner.contents[0].value)
    verify,vv=w.load(output);new_verify=select(verify,'OTPath',name,array_id,owner.contents[0].value)
    verify_owner=next(o for o in w.objects(verify) if w.kind(o)=='OTEndModel' and o.contents[0].value==owner.contents[0].value)
    arr=verify_owner.contents[17].value.contents[0].value;arr.contents=[arr.contents[0]]+[g for g in arr.contents[1:] if g.value is not new_verify];arr.contents[0].value-=1;verify_owner.contents[19].value=highwater
    if w.dump_verified(verify,vv)!=baseline:raise Unsupported('Existing graph changed outside new Path/counter')
    expected=[{'name':string(r.contents[1].value),'array_id':r.contents[2].values[0],'start_id':r.contents[2].values[1]} for r in chain]
    if actual['persisted_object_count']!=1 or actual['saved_references']!=expected:raise Unsupported('Saved first-object/full-info verification failed')
    return output,{'operation':'create_local_path','functions':['0x559398','0x55a050','0x4c4770','0x55a600','0x4c7188'],
                   'allocator':{'function':'0x4c7188','owner_end_id':owner.contents[0].value,'field':'highestGivenRspID','group':19,'encoding':'i','before':highwater,'after':fresh_id,'allocated_id':fresh_id},
                   'created':actual,'document_scope':'single archive; project-wide uniqueness is caller precondition',
                   'native_gui_or_simulation_verified':False,'explicit_external_template_sha256':expected_template_sha256 if template_data is not None else None,'external_template_object_dependencies_retained':False,'template_policy':'shape only; all Path movement/identity/name/description/info fields replaced'}
