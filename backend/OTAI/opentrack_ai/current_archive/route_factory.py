"""Fail-closed current archive Route template factory, not full native init/copy.

Requires opentrack_ai.current_archive from the published wave3 codec on PYTHONPATH.
Pure bytes in/out; does not open Project, execute binaries, or modify source files.
"""
import hashlib
from . import writer as w, path_functions as f

Unsupported = f.Unsupported
END = ['i','f','f','f','i','i','@','@','i','@','@','@','@','@','f','@','@','@','@','i','i','f','i','ii']
EDGE = ['i','f','f','f','i','i','@','@','@','iiffii','ff','i','@','@','@','@','@','@','@','@','@']
SIGNAL = ['i','f','f','f','i','i','@','@','iii','iiii','@','i','i','@','@','@','f']

def require(ok, message):
    if not ok: raise Unsupported(message)

def layout(obj, cls, version, enc, graphic=False, mutable=False):
    f.hierarchy(obj, [(cls,version)]+([('OTGraphicModel',1)] if graphic else [])+([('OTMutableArray',0)] if mutable else [])+[('NSObject',0)])
    require([''.join(e.decode('ascii') for e in g.encodings) for g in obj.contents]==enc, 'Unsupported '+cls+' layout')
    require(all(len(g.encodings)==len(g.values) for g in obj.contents), 'Malformed group')
    return obj

def wrapper(obj, cls):
    layout(obj,cls,0,['@'],mutable=True)
    return f.mutable_array(obj.contents[0].value)

def refs(root,target):
    from .graph_references import incoming
    return incoming(root,target)

def document(root):
    f.hierarchy(root,[('OTDocument',4),('NSObject',0)])
    require(len(root.contents)==21 and root.contents[2].encodings==[b'@'],'Current document layout required')
    models=f.mutable_array(root.contents[2].value); by_id={}
    for m in models:
        require(m.contents and m.contents[0].encodings==[b'i'] and type(m.contents[0].value)==int,'Malformed model identity')
        ident=m.contents[0].value
        require(ident not in by_id,'Duplicate model identity')
        by_id[ident]=m
    return models,by_id

def validate_chain(root, route, requested_ids):
    models,by_id=document(root)
    f.shape(route,'OTRoute');nodes=f.mutable_array(route.contents[0].value)
    require(route.contents[5].values[4]==-1,'Continuation unsupported; never serialize expanded runtime tail')
    require(isinstance(requested_ids,list) and all(type(i)==int for i in requested_ids),'Explicit integer End list required')
    require(len(nodes)>=2 and len(set(requested_ids))==len(requested_ids),'Simple chain required')
    require([e.contents[0].value for e in nodes]==requested_ids,'Only explicitly confirmed template geometry supported')
    signals=[]
    for e in nodes:
        layout(e,'OTEndModel',7,END,graphic=True)
        require(by_id.get(e.contents[0].value) is e,'End outside current document')
        layout(e.contents[7].value,'OTElement',0,['i','f','f','f','i','i','@','@'],graphic=True)
        require(e.contents[7].value in models,'Safety element outside document')
        signal=e.contents[11].value
        if signal is not None:
            layout(signal,'OTSignalModel',11,SIGNAL,graphic=True)
            require(signal in models and signal.contents[7].value is e,'Signal/End backreference not closed')
        signals.append(signal)
    is_main=lambda s: s is not None and s.contents[8].values[0] in {1,2,24,25,26}
    require(is_main(signals[0]) and is_main(signals[-1]),'Terminal main signals required')
    require(not any(is_main(s) for s in signals[1:-1]),'Intermediate main signal unsupported')
    require(signals[0].contents[9].values[0]==2 and signals[-1].contents[9].values[0]==2,'Only explicit show-type 2 terminal signals supported')
    edges=[]
    for a,b in zip(nodes,nodes[1:]):
        paired=by_id.get(a.contents[8].value)
        require(paired is not None and w.kind(paired)=='OTEndModel','Missing related End or connector unsupported')
        layout(paired,'OTEndModel',7,END,graphic=True)
        require(paired.contents[8].value==a.contents[0].value,'Related End pair not reciprocal')
        choices=[]
        for i in (9,10):
            edge=paired.contents[i].value
            if edge is None: continue
            layout(edge,'OTEdgeModel',3,EDGE,graphic=True)
            require(edge in models,'Edge outside current document')
            ends=[edge.contents[i].value for i in (7,8)]
            require(paired in ends and all(e in models for e in ends),'Edge endpoints not closed')
            if b in ends:
                require(edge in [b.contents[i].value for i in (9,10)],'Destination incident edge missing')
                require(type(edge.contents[9].values[1])==int and edge.contents[9].values[1]>0,'Positive persisted edge length required')
                if edge not in choices: choices.append(edge)
        require(len(choices)==1,'Disconnected or ambiguous directed edge chain')
        edges.append(choices[0])
    require(route.contents[12].values[1:]==[None,None] and f.string(route.contents[7].value)=='' and route.contents[9].value==-1,'Protection/overlap references unsupported')
    groups=f.mutable_array(route.contents[12].values[0])
    require(all(e in nodes for e in groups) and len(set(map(id,groups)))==len(groups),'Unknown groupStartElems reference')
    require(route.contents[5].values[5]==0 and route.contents[6].values[0]==0,'Dirty/occupied-entry/discrete flags unsupported')
    owner=nodes[0]
    require(route.contents[2].values[1]==owner.contents[0].value,'Template start ID mismatch')
    require(route in wrapper(owner.contents[15].value,'OTRouteList'),'Template absent from owner RouteList')
    inds=wrapper(route.contents[4].value,'OTSigIndList')
    require(len(inds)==1,'Only single explicit track-speed indication supported')
    for ind in inds:
        layout(ind,'OTSigInd',0,['i','@'])
        require(ind.contents[0].value==0 and ind.contents[1].value is route,'Indication code/backreference unsupported')
    return owner,nodes,edges,signals,inds

def create_route_from_template(data, *, template, name, end_ids, description=''):
    """Allocate new Route on SAME verified movement as explicit current template.

    template={'name':str,'array_id':int,'start_id':int}; end_ids explicitly confirms
    the movement. ID is highestGivenRspID+1 per 0x4c7188, not number-of-routes+1.
    Template policy preserves stored parameters, NOT native init/copy equivalence.
    """
    require(isinstance(template,dict) and set(template)=={'name','array_id','start_id'},'Exact template identity required')
    require(type(template['array_id'])==int and type(template['start_id'])==int,'Integer template identity required')
    require(isinstance(name,str) and bool(name),'Explicit nonempty Route name required')
    root,version=w.load_next_compatible(data)
    require(refs(root,root)==0,'Aliased archive root unsupported')
    route=f.select(root,'OTRoute',**template)
    owner,nodes,edges,signals,inds=validate_chain(root,route,end_ids)
    new_name=f.fresh_string(route.contents[1].value,name)
    new_description=f.fresh_string(route.contents[3].value,description)
    
    f.guard_counter_references(root,owner)
    old_high=owner.contents[19].value
    require(type(old_high)==int and -1<=old_high<2147483647,'highestGivenRspID invalid or exhausted')
    ident=old_high+1
    used=[]
    for idx,cls in [(15,'OTRouteList'),(16,'OTShuntingList'),(17,'OTPathList')]:
        container=owner.contents[idx].value
        if container is None: continue
        items=wrapper(container,cls)
        require(refs(root,container)==1 and refs(root,container.contents[0].value)==1,'Aliased owner container unsupported')
        for item in items:
            if cls=='OTRouteList':f.shape(item,'OTRoute')
            elif cls=='OTPathList':f.shape(item,'OTPath')
            else:raise Unsupported('Nonempty ShuntingList unsupported until complete member schema is audited')
            require(len(item.contents)>2 and item.contents[2].encodings==[b'i',b'i'],'Unknown RSP identity layout')
            aid,sid=item.contents[2].values
            require(type(aid)==int and type(sid)==int and sid==owner.contents[0].value,'Invalid RSP owner identity')
            require(0<=aid<=old_high,'Stale highestGivenRspID; no silent repair')
            used.append(aid)
    require(len(set(used))==len(used),'Duplicate owner RSP identity')
    for obj in w.objects(root):
        if w.kind(obj)=='OTRoute':
            f.shape(obj,'OTRoute')
            require(f.string(obj.contents[1].value)!=name,'Route name already exists')
            require(obj.contents[2].values!=[ident,owner.contents[0].value],'Route identity already exists')
        if w.kind(obj) in ('OTArrayInfo','OTArrayExtInfo'):
            require(obj.contents[1].values!=[ident,owner.contents[0].value] and f.string(obj.contents[0].value)!=name,'Would capture an existing saved reference')
    new=f.clone(route)
    new.contents[0].value=f.array_like(route.contents[0].value,nodes)
    new.contents[1].value=new_name;new.contents[2].values=[ident,owner.contents[0].value]
    new.contents[3].value=new_description
    new.contents[7].value=f.fresh_string(route.contents[7].value,'')
    new.contents[12].values=[f.array_like(route.contents[12].values[0],f.mutable_array(route.contents[12].values[0])),None,None]
    copied=[]
    for ind in inds:
        item=f.clone(ind);item.contents[1].value=new;copied.append(item)
    sl=f.clone(route.contents[4].value)
    sl.contents[0].value=f.array_like(route.contents[4].value.contents[0].value,copied)
    new.contents[4].value=sl
    arr=owner.contents[15].value.contents[0].value
    w.set_elements(arr,f.mutable_array(arr)+[new]);owner.contents[19].value=ident
    output=w.dump_verified(root,version)
    check,_=w.load(output);added=f.select(check,'OTRoute',name,ident,end_ids[0])
    check_owner,*_=validate_chain(check,added,end_ids)
    
    check_array=check_owner.contents[15].value.contents[0].value
    w.set_elements(check_array,[x for x in f.mutable_array(check_array) if x is not added])
    check_owner.contents[19].value=old_high
    original,original_version=w.load(data)
    require(w.dump_verified(check,version)==w.dump_verified(original,original_version),'Unrelated graph mutation detected')
    return output,{'operation':'create_route_from_explicit_current_template','created':f.info(added),
       'highestGivenRspID_before':old_high,'highestGivenRspID_after':ident,
       'edge_ids':[e.contents[0].value for e in edges], 'terminal_signal_ids':[signals[i].contents[0].value for i in (0,-1)],
       'template':template,'input_sha256':hashlib.sha256(data).hexdigest(),'output_sha256':hashlib.sha256(output).hexdigest(),
       'native_init_or_copy_equivalent':False,'continuation':'absent; native strip/append no-op',
       'gui_or_simulation_verified':False,'project_wide_name_uniqueness':'caller precondition; only current document inspected'}
