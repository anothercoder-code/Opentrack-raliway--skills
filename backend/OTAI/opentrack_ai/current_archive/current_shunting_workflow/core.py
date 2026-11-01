"""New 2026-10-29 bounded current-archive Shunting/Overlap data implementation.
No simulation, GUI operation, source writes or publication. See contract evidence.
"""
import hashlib, math, struct
from .. import writer as w, path_functions as f, route_factory as rf
from ..zero_generation import native_signal_routes as n
from ..graph_references import incoming, incoming_counts
need=rf.require
CHAIN=[('OTShunting',0),('OTSecurityArray',6),('OTOrgArray',2),('OTMutableArray',0),('NSObject',0)]
ENC=['@','@','ii','@','@','iiiiii','iff','@','ff','i','iii','f']

def sha(b):return hashlib.sha256(b).hexdigest()
def identity(o):return {'name':f.string(o.contents[1].value),'array_id':o.contents[2].values[0],'start_id':o.contents[2].values[1]}
def scalar(v,lo=0,hi=2147483647):return n.integer(v,lo,hi)
def text(v):need(type(v)is str and v and len(v.encode('utf8'))<=200 and '\0' not in v,'Bounded nonempty name required');return v

def movement(root,ids):
    models,byid=n.validate_topology(root)
    need(type(ids)is list and 2<=len(ids)<=1000 and all(type(i)is int for i in ids) and len(set(ids))==len(ids),'Simple explicit End sequence required')
    nodes=[byid.get(i)for i in ids];need(all(e is not None and w.kind(e)=='OTEndModel'for e in nodes),'Missing End')
    edges=[]
    for a,b in zip(nodes,nodes[1:]):
        related=byid[a.contents[8].value];matches=[]
        for slot in (9,10):
            edge=related.contents[slot].value
            if edge is not None and b in [edge.contents[j].value for j in (7,8)] and edge not in matches:matches.append(edge)
        need(len(matches)==1,'Disconnected/ambiguous directed movement');edges+=matches
    return nodes,edges

def shunting(root,path,owner):
    f.shape(path,'OTPath');need(path.contents[2].values[1]==owner.contents[0].value,'Wrong automatic Path owner')
    items=f.mutable_array(path.contents[0].value);need(len(items)==1,'Exactly one Shunting body required');body=items[0]
    f.hierarchy(body,CHAIN);need([b''.join(g.encodings).decode()for g in body.contents]==ENC,'Unsupported Shunting layout')
    need(all(len(g.encodings)==len(g.values)for g in body.contents),'Malformed Shunting groups')
    scalar(body.contents[5].values[2]);scalar(body.contents[5].values[3])
    name=f.string(path.contents[1].value);need(name==f.string(body.contents[1].value),'Path/body name mismatch')
    need(body.contents[2].values==[-1,-1],'Stored body IDs must remain -1/-1')
    infos=f.mutable_array(path.contents[4].value);need(len(infos)==1,'One automatic saved reference required')
    rf.layout(infos[0],'OTArrayInfo',0,['@','ii'])
    need(f.string(infos[0].contents[0].value)==name and infos[0].contents[1].values==[-1,-1],'Automatic body reference mismatch')
    ids=[e.contents[0].value for e in f.mutable_array(body.contents[0].value)];nodes,edges=movement(root,ids)
    need(nodes[0]is owner and f.mutable_array(body.contents[0].value)==nodes,'Wrong Shunting owner/geometry')
    need(body.contents[5].values[4:]==[-1,0] and body.contents[6].values[0]==0,'Continuation/dirty/occupied-entry flags outside supported domain')
    need(f.string(body.contents[7].value)=='' and body.contents[9].value==-1,'Recursive Overlap unsupported')
    inds=rf.wrapper(body.contents[4].value,'OTSigIndList');need(len(inds)==1,'One code-0 indication required')
    rf.layout(inds[0],'OTSigInd',0,['i','@']);need(inds[0].contents[0].value==0 and inds[0].contents[1].value is body,'Indication must point to Shunting body')
    speed=body.contents[11].value;need(isinstance(speed,(int,float))and not isinstance(speed,bool)and math.isfinite(speed)and 0<speed<=1000,'Speed outside finite API range')
    return body,nodes,edges

def load(data):
    root,v,models,byid=n.document(data);n.validate_topology(root);rows=[];counts=incoming_counts(root)
    for end in models:
        if w.kind(end)!='OTEndModel':continue
        container=end.contents[16].value;items=rf.wrapper(container,'OTShuntingList')
        need(counts[id(container)]==1 and counts[id(container.contents[0].value)]==1,'Aliased Shunting container unsupported')
        high=scalar(end.contents[19].value,-1);allocated=[]
        for slot,kind in ((15,'OTRouteList'),(16,'OTShuntingList'),(17,'OTPathList')):
            for p in rf.wrapper(end.contents[slot].value,kind):
                f.shape(p,'OTRoute'if slot==15 else'OTPath');aid,sid=p.contents[2].values
                need(type(aid)is int and 0<=aid<=high and sid==end.contents[0].value,'Invalid/stale RSP identity');allocated.append(aid)
        need(len(allocated)==len(set(allocated)),'Duplicate RSP id')
        for path in items:
            body,nodes,edges=shunting(root,path,end);rows.append((path,body,nodes,edges))
    return root,v,byid,rows

def detail(row):
    p,b,ns,es=row
    return {**identity(p),'description':f.string(p.contents[3].value),'end_ids':[e.contents[0].value for e in ns],'edge_ids':[e.contents[0].value for e in es],'speed_kmh':b.contents[11].value,'release_time_s':b.contents[5].values[2],'reservation_time_s':b.contents[5].values[3]}

def select(rows,ref):
    need(type(ref)is dict and set(ref)=={'name','array_id','start_id'},'Exact name/ID/start reference required')
    text(ref['name']);scalar(ref['array_id']);scalar(ref['start_id'])
    found=[r for r in rows if identity(r[0])==ref];need(len(found)==1,'Shunting identity must resolve exactly once');return found[0]

def receipt(data,out,action,details):
    return {'operation':action,'input_sha256':sha(data),'output_sha256':sha(out),'output_bytes':len(out),'archive_roundtrip_passed':True,'details':details,'saved':False,'preview_only':True,'native_execution':False,'complete_project_validated':False}

def inspect(data):
    root,v,byid,rows=load(data)
    return {'input_sha256':sha(data),'shuntings':[detail(r)for r in rows],'native_execution':False,'scope':'single current Document4; local Shunting0/SecurityArray6'}

def create(data,spec):
    need(type(spec)is dict and set(spec)=={'name','description','end_ids','speed_kmh','release_time_s','reservation_time_s'},'Exact creation specification required')
    text(spec['name']);need(type(spec['description'])is str,'Description string required');scalar(spec['release_time_s']);scalar(spec['reservation_time_s'])
    speed=n.number(spec['speed_kmh'],0.0001,1000);speed=struct.unpack('<f',struct.pack('<f',speed))[0]
    root,v,byid,rows=load(data);nodes,edges=movement(root,spec['end_ids']);owner=nodes[0];oldhigh=scalar(owner.contents[19].value,-1,2147483646);aid=oldhigh+1
    for obj in w.objects(root):
        if w.kind(obj)in('OTPath','OTRoute','OTShunting'):need(f.string(obj.contents[1].value)!=spec['name'],'Movement name already exists')
        if w.kind(obj)in('OTArrayInfo','OTArrayExtInfo'):need(f.string(obj.contents[0].value)!=spec['name'],'Would capture existing reference')
    body=n.obj(CHAIN,[('@',[n.arr(nodes)]),('@',[n.string(spec['name'])]),('ii',[-1,-1]),('@',[n.string(spec['description'])]),('@',[None]),('iiiiii',[0,0,spec['release_time_s'],spec['reservation_time_s'],-1,0]),('iff',[0,40.,0.]),('@',[n.string('')]),('ff',[0.,0.]),('i',[-1]),('iii',[5000,0,0]),('f',[speed])])
    ind=n.obj([('OTSigInd',0),('NSObject',0)],[('i',[0]),('@',[body])]);body.contents[4].value=n.wrapped('OTSigIndList',[ind])
    info=n.obj([('OTArrayInfo',0),('NSObject',0)],[('@',[n.string(spec['name'])]),('ii',[-1,-1])])
    path=n.obj(f.SHAPES['OTPath'][0],[('@',[n.arr([body])]),('@',[n.string(spec['name'])]),('ii',[aid,owner.contents[0].value]),('@',[n.string(spec['description'])]),('@',[n.arr([info])])])
    arr=owner.contents[16].value.contents[0].value;w.set_elements(arr,f.mutable_array(arr)+[path]);owner.contents[19].value=aid
    out=w.dump_verified(root,v);check,cv,ci,rr=load(out);added=select(rr,identity(path));details=detail(added)
    ar=ci[owner.contents[0].value].contents[16].value.contents[0].value;w.set_elements(ar,[p for p in f.mutable_array(ar)if p is not added[0]]);ci[owner.contents[0].value].contents[19].value=oldhigh
    original,ov=w.load(data);need(w.dump_verified(check,cv)==w.dump_verified(original,ov),'Unrelated graph mutation')
    return out,receipt(data,out,'create_local_shunting',details)

def bind_overlap(data,route_ref,shunting_ref,selection_policy="route_terminal"):
    need(selection_policy in ("route_terminal","same_document_explicit"),"Unknown Overlap selection policy")
    root,v,byid,rows=load(data)
    need(type(route_ref)is dict and set(route_ref)=={'name','array_id','start_id'},'Exact Route identity required')
    text(route_ref['name']);scalar(route_ref['array_id']);scalar(route_ref['start_id'])
    route=f.select(root,'OTRoute',**route_ref);nodes=f.mutable_array(route.contents[0].value)
    need(route.contents[5].values[4]==-1 and len(nodes)>=2,'Local complete Route required')
    
    prior_name,prior_start=route.contents[7].value,route.contents[9].value
    route.contents[7].value=n.string('');route.contents[9].value=-1
    rf.validate_chain(root,route,[e.contents[0].value for e in nodes])
    if shunting_ref is None:newname,newstart='',-1
    else:
        p,b,snodes,edges=select(rows,shunting_ref)
        if selection_policy=='route_terminal':
            need(snodes[0]is nodes[-1],'Overlap must begin at Route terminal End')
        else:
            need(all(byid.get(e.contents[0].value)is e for e in snodes+nodes),'Same-document local references required')
            need(snodes[0]not in nodes[:-1],'Explicit Overlap start re-enters prior Route')
        need(not any(e in nodes[:-1]for e in snodes[1:]),'Overlap re-enters prior Route')
        newname,newstart=f.string(p.contents[1].value),snodes[0].contents[0].value
    route.contents[7].value=n.string(newname);route.contents[9].value=newstart
    out=w.dump_verified(root,v);check,cv,ci,rr=load(out);r=f.select(check,'OTRoute',**route_ref)
    need(f.string(r.contents[7].value)==newname and r.contents[9].value==newstart,'Overlap readback mismatch')
    
    route.contents[7].value=prior_name;route.contents[9].value=prior_start
    original,ov=w.load(data);need(w.dump_verified(root,v)==w.dump_verified(original,ov),'Unrelated graph mutation')
    return out,receipt(data,out,'bind_route_overlap'if shunting_ref else'unbind_route_overlap',{'route':route_ref,'overlap':shunting_ref,'selection_policy':selection_policy,'constraints':['current local Shunting domain','no prior-Route reentry','no recursive Overlap']})

def delete(data,ref):
    root,v,byid,rows=load(data);path,body,nodes,edges=select(rows,ref)
    for obj in w.objects(root):
        if obj in (path,body):continue
        if w.kind(obj)in('OTRoute','OTShunting')and f.string(obj.contents[7].value)==ref['name']:
            need(False,'Dependent Overlap reference must be removed first')
        if w.kind(obj)in('OTArrayInfo','OTArrayExtInfo')and obj not in f.mutable_array(path.contents[4].value):
            need(not(f.string(obj.contents[0].value)==ref['name'] or obj.contents[1].values==[ref['array_id'],ref['start_id']]),'Dependent saved Path reference')
    need(incoming(root,path)==1 and incoming(root,body)==2,'Shared automatic Path/body cannot be deleted')
    arr=nodes[0].contents[16].value.contents[0].value;old=list(f.mutable_array(arr));w.set_elements(arr,[p for p in old if p is not path])
    out=w.dump_verified(root,v);check,cv,ci,rr=load(out);need(not any(identity(r[0])==ref for r in rr),'Delete readback failed')
    
    need(ci[ref['start_id']].contents[19].value==nodes[0].contents[19].value,'Allocator changed on deletion')
    w.set_elements(arr,old);original,ov=w.load(data);need(w.dump_verified(root,v)==w.dump_verified(original,ov),'Unrelated mutation')
    return out,receipt(data,out,'delete_local_shunting',{'deleted':ref,'highestGivenRspID':nodes[0].contents[19].value})
