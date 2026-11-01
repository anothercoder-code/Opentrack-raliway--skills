"""Bounded scalar edits of known local Shunting layouts; no migration or export."""
import math,struct
from .. import writer as w,path_functions as f,route_factory as rf
from ..graph_references import incoming
from . import core,inventory
need=rf.require
FIELDS={'speed_kmh','release_time_s','reservation_time_s'}

def select(root,ref):
    need(type(ref)is dict and set(ref)=={'name','array_id','start_id'},'Exact automatic Path name/array_id/start_id required')
    core.text(ref['name']);core.scalar(ref['array_id']);core.scalar(ref['start_id'])
    models=f.mutable_array(root.contents[2].value);found=[]
    for owner in models:
        if w.kind(owner)not in('OTEndModel','OTConnModel','OTStationEndModel'):continue
        if owner.contents[16].value is None:continue
        for path in rf.wrapper(owner.contents[16].value,'OTShuntingList'):
            if core.identity(path)==ref:found.append((owner,path,f.mutable_array(path.contents[0].value)[0]))
    need(len(found)==1,'Automatic Path identity must resolve exactly once')
    owner,path,body=found[0]
    need(owner.contents[0].value==ref['start_id'],'Automatic Path owner mismatch')
    need(core.identity(body)['name']==ref['name'],'Path/body name mismatch')
    refs=f.mutable_array(path.contents[4].value)
    need(len(refs)==1,'Exactly one saved body reference required')
    need(f.string(refs[0].contents[0].value)==ref['name']and refs[0].contents[1].values==body.contents[2].values,'Saved body reference mismatch')
    nodes=f.mutable_array(body.contents[0].value)
    need(len(nodes)>=2 and nodes[0]is owner and all(any(n is m for m in models)for n in nodes),'Only owned local Shunting supported')
    need(body.contents[5].values[4]==-1,'Cross-document Shunting unsupported')
    inds=rf.wrapper(body.contents[4].value,'OTSigIndList')
    need(len(inds)==1 and inds[0].contents[0].value==0 and w.kind(inds[0].contents[1].value)=='OTShunting','Known single code-0 indication required')
    
    
    expected=1+sum(ind.contents[1].value is body for ind in inds)
    need(incoming(root,path)==1 and incoming(root,body)==expected,'Aliased automatic Path/body outside parameter edit scope')
    return body

def update_parameters(data,spec):
    need(type(spec)is dict and set(spec)=={'shunting','changes'},'Exact shunting and changes required')
    changes=spec['changes'];need(type(changes)is dict and 1<=len(changes)<=3 and set(changes)<=FIELDS,'Only speed/release/reservation parameters supported')
    normalized={}
    for key,val in changes.items():
        if key=='speed_kmh':
            need(type(val)in(int,float)and math.isfinite(val)and 0<val<=1000,'Finite speed in (0,1000] API range required')
            normalized[key]=struct.unpack('<f',struct.pack('<f',val))[0]
            need(normalized[key]>0,'Speed underflows binary32')
        else:normalized[key]=core.scalar(val)
    before=inventory.inspect_inventory(data)
    root,version=w.load(data);body=select(root,spec['shunting']);si=11 if body.clazz.superclass.version==6 else 10
    old={'speed_kmh':body.contents[si].value,'release_time_s':body.contents[5].values[2],'reservation_time_s':body.contents[5].values[3]}
    def put(obj,values):
        index=11 if obj.clazz.superclass.version==6 else 10
        for key,val in values.items():
            if key=='speed_kmh':obj.contents[index].value=val
            else:obj.contents[5].values[2 if key=='release_time_s'else 3]=val
    put(body,normalized);out=w.dump_verified(root,version)
    check,cv=w.load(out);fresh=select(check,spec['shunting']);inventory.inspect_inventory(out)
    for key,val in normalized.items():
        actual=fresh.contents[si].value if key=='speed_kmh'else fresh.contents[5].values[2 if key=='release_time_s'else 3]
        need(actual==val,'Parameter fresh readback mismatch')
    put(fresh,old);original,ov=w.load(data)
    need(w.dump_verified(check,cv)==w.dump_verified(original,ov),'Unrelated graph mutation')
    result=core.receipt(data,out,'update_local_shunting_parameters',{'shunting':spec['shunting'],'before':old,'changes':normalized,'document_version':before['document_version'],'security_array_version':body.clazz.superclass.version,'ids_and_saved_references_preserved':True,'indication_pointer_preserved':True,'indication_points_to_edited_body':rf.wrapper(body.contents[4].value,'OTSigIndList')[0].contents[1].value is body,'existing_indication_semantics_certified':False,'inverse_graph_verified':True,'scope':'Only three scalar parameters; no rename, topology or operational feasibility changes'})
    return out,result
