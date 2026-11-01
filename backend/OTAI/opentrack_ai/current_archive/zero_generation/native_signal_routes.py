"""New objects from audited current schemas; no movement/template cloning.
Pure bytes transaction. Current local Document4, no simulation or GUI claims.
"""
import hashlib, math
from opentrack_ai.current_archive import writer as w, path_functions as f, route_factory as rf
from opentrack_ai.current_archive.graph_references import incoming
from opentrack_ai.current_archive.graphic_alignment import validate_placement, validate_signal_placement, validate_generated_signal_alignment
Unsupported=f.Unsupported
require=rf.require

def cls(chain):
    parent=None
    for name,version in reversed(chain): parent=w.Class(name.encode(),version,parent)
    return parent

def obj(chain, groups):
    return w.GenericArchivedObject(cls(chain),None,[w.TypedGroup(w.split_types(enc.encode()), values) for enc,values in groups])

def arr(items=()):
    a=obj([('NSMutableArray',0),('NSArray',0),('NSObject',0)],[]);w.set_elements(a,list(items));return a

def string(value):
    require(type(value)==str and '\0' not in value and len(value.encode('utf8'))<=65536,'Invalid string')
    return obj([('NSString',1),('NSObject',0)],[('+',[value.encode('utf8')])])

def wrapped(kind,items):
    return obj([(kind,0),('OTMutableArray',0),('NSObject',0)],[('@',[arr(items)])])

def integer(v,lo=0,hi=2147483647):
    require(type(v)==int and lo<=v<=hi,'Integer outside API guard');return v

def number(v,lo=-1e6,hi=1e6):
    require(type(v) in (int,float) and math.isfinite(v) and lo<=v<=hi,'Nonfinite/out of guard number');return float(v)

def document(data):
    root,version=w.load(data);models,byid=rf.document(root)
    require(incoming(root,root)==0 and incoming(root,root.contents[2].value)==1,'Shared document/model array unsupported')
    return root,version,models,byid

def validate_topology(root):
    models,byid=rf.document(root)
    for end in models:
        if w.kind(end)!='OTEndModel':continue
        rf.layout(end,'OTEndModel',7,rf.END,graphic=True)
        related=byid.get(end.contents[8].value)
        require(related is not end and related is not None and w.kind(related)=='OTEndModel','Missing/current related End required')
        rf.layout(related,'OTEndModel',7,rf.END,graphic=True)
        require(related.contents[8].value==end.contents[0].value,'Related End not reciprocal')
        elem=end.contents[7].value
        rf.layout(elem,'OTElement',0,['i','f','f','f','i','i','@','@'],graphic=True)
        require(elem in models and f.mutable_array(elem.contents[7].value).count(end)==1,'Safety membership mismatch')
        incident=[end.contents[i].value for i in (9,10) if end.contents[i].value is not None]
        require(len(set(map(id,incident)))==len(incident),'Duplicate incident Edge')
        for edge in incident:
            require(edge in models and w.kind(edge)=='OTEdgeModel','Edge outside document')
            require(end in [edge.contents[i].value for i in (7,8)],'Incident/Edge reverse mismatch')
    for edge in models:
        if w.kind(edge)!='OTEdgeModel':continue
        rf.layout(edge,'OTEdgeModel',3,rf.EDGE,graphic=True)
        ends=[edge.contents[i].value for i in (7,8)]
        require(ends[0] is not ends[1],'Edge self endpoint unsupported')
        require(all(e in models and w.kind(e)=='OTEndModel' and edge in [e.contents[i].value for i in (9,10)] for e in ends),'Edge/End reverse mismatch')
        require(type(edge.contents[9].values[1])==int and edge.contents[9].values[1]>0,'Positive Edge length required')
        require(ends[0].contents[7].value is ends[1].contents[7].value,'Edge endpoints must share native union Safety Element')
    for signal in models:
        if w.kind(signal)!='OTSignalModel':continue
        rf.layout(signal,'OTSignalModel',11,rf.SIGNAL,graphic=True)
        e=signal.contents[7].value
        require(e in models and w.kind(e)=='OTEndModel' and e.contents[11].value is signal,'Signal/End reverse mismatch')
        for indication in rf.wrapper(signal.contents[10].value,'OTSigIndList'):
            rf.layout(indication,'OTSigInd',0,['i','@'])
            require(indication.contents[1].value is e,'Signal indication owner must be End')
    for end in models:
        if w.kind(end)=='OTEndModel' and end.contents[11].value is not None:
            require(end.contents[11].value in models and w.kind(end.contents[11].value)=='OTSignalModel','End signal outside models')
            require(end.contents[11].value.contents[7].value is end,'End borrows another End signal')
    for elem in models:
        if w.kind(elem)!='OTElement':continue
        members=f.mutable_array(elem.contents[7].value)
        require(members and len(set(map(id,members)))==len(members),'Empty/duplicate Safety Element')
        require(all(e in models and w.kind(e)=='OTEndModel' and e.contents[7].value is elem for e in members),'Safety reverse mismatch')
    return models,byid

def build_main_signal(data, *, end_id, name, model_id, placement, sight_m, delay_s, show_symbol, show_icon):
    """Bounded explicit main/exit profile: signalType1, mainType4, location2,
    showType2, dispatch7; track-speed code0. Not all native Inspector defaults.
    All physical/placement options are explicit; nil performance/coasting avoided.
    """
    root,version,models,byid=document(data);validate_topology(root)
    integer(end_id);integer(model_id)
    require(model_id==max(byid,default=-1)+1,'Fresh model ID must equal observed maximum + 1; not native runtime allocator claim')
    placement=validate_placement(placement)
    require(type(show_symbol)==bool and type(show_icon)==bool,'Boolean display inputs required')
    end=byid.get(end_id);require(end is not None and w.kind(end)=='OTEndModel','Current End required')
    placement=validate_signal_placement(placement,end)
    require(end.contents[11].value is None,'Existing End signal cannot be replaced')
    f.guard_counter_references(root,end) 
    require(name and not any(w.kind(o)=='OTSignalModel' and f.string(o.contents[13].value)==name for o in w.objects(root)),'Duplicate/empty signal name')
    flags=0x80|0x200|(4 if show_symbol else 0)|(0 if show_icon else 8)
    ind=obj([('OTSigInd',0),('NSObject',0)],[('i',[0]),('@',[end])])
    groups=[('i',[model_id]),('f',[number(placement['angle'])]),('f',[number(placement['x'])]),('f',[number(placement['y'])]),('i',[placement['alignment_x']]),('i',[placement['alignment_y']]),('@',[None]),('@',[end]),('iii',[1,4,2]),('iiii',[2,integer(sight_m,1,100000),flags,0]),('@',[wrapped('OTSigIndList',[ind])]),('i',[0]),('i',[7]),('@',[string(name)]),('@',[arr()]),('@',[arr()]),('f',[number(delay_s,0,86400)])]
    signal=obj([('OTSignalModel',11),('OTGraphicModel',1),('NSObject',0)],groups)
    end.contents[11].value=signal;w.set_elements(root.contents[2].value,models+[signal])
    output=w.dump_verified(root,version)
    check,cv,cm,ci=document(output);validate_topology(check)
    saved=ci[model_id];rf.layout(saved,'OTSignalModel',11,rf.SIGNAL,graphic=True)
    validate_generated_signal_alignment(saved)
    require((saved.contents[4].value,saved.contents[5].value)==(placement['alignment_x'],placement['alignment_y']),'Signal native alignment readback mismatch')
    validate_signal_placement(placement,ci[end_id])
    require((saved.contents[4].value,saved.contents[5].value)==
            (ci[end_id].contents[4].value,ci[end_id].contents[5].value),'Signal/End directional alignment readback mismatch')
    require(saved.contents[7].value is ci[end_id] and ci[end_id].contents[11].value is saved,'Signal/End readback mismatch')
    require(rf.wrapper(saved.contents[10].value,'OTSigIndList')[0].contents[1].value is ci[end_id],'Signal indication must point to End')
    ci[end_id].contents[11].value=None;w.set_elements(check.contents[2].value,[m for m in cm if m is not saved])
    original,ov=w.load(data);require(w.dump_verified(check,cv)==w.dump_verified(original,ov),'Unrelated graph change')
    return output,receipt(data,output,'build_new_main_signal',{'model_id':model_id,'end_id':end_id,'name':name,'alignment_x':placement['alignment_x'],'alignment_y':placement['alignment_y'],'profile':'type1-main4-location2-show2-dispatch7','indication_owner':'End','allocator':'observed-max-plus-one, not native allocator parity'})

def validate_movement(root,ids):
    models,byid=validate_topology(root)
    require(type(ids)==list and 2<=len(ids)<=1000 and all(type(i)==int for i in ids) and len(set(ids))==len(ids),'Finite simple directed End sequence required')
    nodes=[byid.get(i) for i in ids]
    require(all(e is not None and w.kind(e)=='OTEndModel' for e in nodes),'End missing')
    edges=[]
    for a,b in zip(nodes,nodes[1:]):
        related=byid[a.contents[8].value]
        choices=[]
        for i in (9,10):
            edge=related.contents[i].value
            if edge is not None and b in [edge.contents[j].value for j in (7,8)] and edge not in choices:choices.append(edge)
        require(len(choices)==1,'Disconnected or ambiguous movement; names/coordinates do not establish connectivity')
        edges.append(choices[0])
    for i,end in enumerate(nodes):
        s=end.contents[11].value
        main=s is not None and s.contents[8].values[0] in (1,2,24,25,26)
        if i in (0,len(nodes)-1):
            require(main and s in models and s.contents[7].value is end and s.contents[9].values[0]==2,'Terminal show-type2 main signals required')
            require(type(s.contents[9].values[2])==int and 0<=s.contents[9].values[2]<=1023 and not s.contents[9].values[2]&2,'Virtual/unknown terminal signal flags outside guarded domain')
            inds=rf.wrapper(s.contents[10].value,'OTSigIndList')
            require(len(inds)==1 and inds[0].contents[0].value==0 and inds[0].contents[1].value is end,'Terminal track-speed indication/End closure required')
        else:require(not main,'Intermediate main signal splits Route')
    return nodes,edges

def build_route(data, *, name, end_ids, description, release_groups, reserve_previous):
    root,version,models,byid=document(data);nodes,edges=validate_movement(root,end_ids)
    require(type(name)==str and name,'Name required');require(type(reserve_previous)==bool,'Explicit reservation flag required')
    require(release_groups in ('global','each_end'),'Audited group/ungroup mode required')
    owner=nodes[0];f.guard_counter_references(root,owner)
    high=integer(owner.contents[19].value,-1,2147483646);aid=high+1
    used=[]
    for index,kind in ((15,'OTRouteList'),(16,'OTShuntingList'),(17,'OTPathList')):
        container=owner.contents[index].value
        require(container is not None,'Existing initialized RSP containers required')
        items=rf.wrapper(container,kind)
        require(incoming(root,container)==1 and incoming(root,container.contents[0].value)==1,'Shared RSP owner container')
        require(kind!='OTShuntingList' or not items,'Nonempty ShuntingList outside first release')
        for item in items:
            f.shape(item,'OTRoute' if kind=='OTRouteList' else 'OTPath')
            oldid,start=item.contents[2].values
            require(type(oldid)==int and 0<=oldid<=high and start==end_ids[0],'Stale or mismatched RSP identity')
            used.append(oldid)
    require(len(used)==len(set(used)),'Duplicate owner RSP id')
    for o in w.objects(root):
        if w.kind(o)=='OTRoute':
            f.shape(o,'OTRoute');require(f.string(o.contents[1].value)!=name,'Route name exists')
        if w.kind(o) in ('OTArrayInfo','OTArrayExtInfo'):
            require(o.contents[1].values!=[aid,end_ids[0]] and f.string(o.contents[0].value)!=name,'Would capture saved reference')
    
    
    groups=[('@',[arr(nodes)]),('@',[string(name)]),('ii',[aid,end_ids[0]]),('@',[string(description)]),('@',[None]),('iiiiii',[0,400,5,0,-1,0]),('iff',[0,40.0,0.0]),('@',[string('')]),('ff',[0.0,0.0]),('i',[-1]),('iii',[5000,0,0]),('i',[int(reserve_previous)]),('@@@',[arr([nodes[0],nodes[-1]] if release_groups=='global' else nodes),None,None])]
    route=obj(f.SHAPES['OTRoute'][0],groups)
    ind=obj([('OTSigInd',0),('NSObject',0)],[('i',[0]),('@',[route])])
    route.contents[4].value=wrapped('OTSigIndList',[ind])
    target=owner.contents[15].value.contents[0].value
    w.set_elements(target,f.mutable_array(target)+[route]);owner.contents[19].value=aid
    rf.validate_chain(root,route,end_ids)
    output=w.dump_verified(root,version)
    check,cv=w.load(output);saved=f.select(check,'OTRoute',name,aid,end_ids[0]);co,*_=rf.validate_chain(check,saved,end_ids)
    require([e.contents[0].value for e in f.mutable_array(saved.contents[12].values[0])]==([end_ids[0],end_ids[-1]] if release_groups=='global' else end_ids),'Release group order changed')
    ca=co.contents[15].value.contents[0].value;w.set_elements(ca,[r for r in f.mutable_array(ca) if r is not saved]);co.contents[19].value=high
    original,ov=w.load(data);require(w.dump_verified(check,cv)==w.dump_verified(original,ov),'Unrelated graph change')
    return output,receipt(data,output,'build_new_movement_route',{'name':name,'array_id':aid,'start_id':end_ids[0],'end_ids':end_ids,'edge_ids':[e.contents[0].value for e in edges],'release_groups':release_groups,'reserve_previous':reserve_previous,'native_allocator':'highestGivenRspID+1','movement_cloned':False})

def receipt(before,after,operation,detail):
    return {'operation':operation,**detail,'input_sha256':hashlib.sha256(before).hexdigest(),'output_sha256':hashlib.sha256(after).hexdigest(),'archive_roundtrip_passed':True,'native_simulation_executed':False,'complete_project_validated':False}
