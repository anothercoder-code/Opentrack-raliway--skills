"""New exact cross-document Paths and Itineraries; immutable bytes transaction.
No filesystem commit, renames, existing-Route edits, fallback repair or runtime.
"""
from .core import *
from .generate import inf,wrapped
from opentrack_ai.current_archive.zero_generation import native_signal_routes as ns
from opentrack_ai.current_archive.graph_references import incoming


def exact_reference(value):
    need(type(value)is dict and set(value)=={'document','name','array_id','start_id'},'Exact document/name/array_id/start_id reference required')
    need(type(value['document'])is str and value['document'] and type(value['name'])is str and value['name'],'Nonempty document/name required')
    need(all(type(value[k])is int and 0<=value[k]<=2147483647 for k in ('array_id','start_id')),'Exact nonnegative signed int32 ID required')
    return value['document'],(value['name'],value['array_id'],value['start_id'])

def exclusive(root,wrapper):
    need(incoming(root,wrapper)==1 and incoming(root,wrapper.contents[0].value)==1,'Shared owner wrapper/backing array refused')

def create_path(documents,catalog,*,document_paths,expected_hashes,complete_document_set,name,routes):
    need(type(name)is str and name and '\x00'not in name,'Explicit new Path name required')
    need(type(routes)is list and 1<=len(routes)<=1000,'Bounded nonempty exact Route sequence required')
    need(expected_hashes=={**{k:sha(v)for k,v in documents.items()},'$dest_catalog':sha(catalog)},'Complete input hash manifest mismatch')
    p=Project(documents,document_paths=document_paths,expected_hashes={k:expected_hashes[k]for k in documents},complete_document_set=complete_document_set);p.check_dest_catalog(catalog)
    selected=[];all_nodes=[];at=None
    for value in routes:
        dn,r=exact_reference(value);need(dn in p.roots,'Missing selected document')
        key=(dn,r[2]);need(at is None or key==at,'Explicit Route chain not contiguous after cross-document continuation')
        obj=p.owned(key,'OTRoute',r);nodes=p.route_view(obj)
        need(nodes[0]==key,'Cannot use continuation fragment as source Route')
        selected.append(obj);all_nodes+=nodes if at is None else nodes[1:];at=nodes[-1]
    need(len(set(all_nodes))==len(all_nodes),'Cyclic/repeated Path movement refused')
    owner_key=all_nodes[0];owner=p.model(owner_key);dn=owner_key[0];root=p.roots[dn];version=p.versions[dn]
    need(not any(ident(o)[0]==name for o in p.paths_objects),'Project Path name already exists')
    high=owner.contents[19].value;need(type(high)is int and -1<=high<2147483647,'Invalid/exhausted native RSP highwater');aid=high+1
    used=[]
    for slot,kind in ((15,'OTRouteList'),(16,'OTShuntingList'),(17,'OTPathList')):
        wr=owner.contents[slot].value;exclusive(root,wr)
        for o in rf.wrapper(wr,kind):
            i,s=o.contents[2].values;need(type(i)is int and 0<=i<=high and s==owner_key[1],'Stale or inconsistent owner RSP identity');used.append(i)
    need(len(set(used))==len(used),'Duplicate owner RSP identity')
    
    
    for r in list(p.roots.values())+[w.load(catalog)[0]]:
        for o in w.objects(r):
            if w.kind(o)=='OTArrayExtInfo':need(f.string(o.contents[0].value)!=name,'New name would capture saved ExtInfo')
    path=ns.obj(f.SHAPES['OTPath'][0],[('@',[ns.arr(selected[:1])]),('@',[ns.string(name)]),('ii',[aid,owner_key[1]]),('@',[ns.string('')]),('@',[ns.arr([inf(o)for o in selected])])])
    backing=owner.contents[17].value.contents[0].value;before_items=f.mutable_array(backing);before_groups=list(backing.contents);baseline=w.dump_verified(root,version)
    w.set_elements(backing,before_items+[path]);owner.contents[19].value=aid
    output=dict(documents);output[dn]=w.dump_verified(root,version)
    checked=Project(output,document_paths=document_paths,expected_hashes={k:sha(v)for k,v in output.items()},complete_document_set=True);checked.check_dest_catalog(catalog)
    saved=checked.owned(owner_key,'OTPath',(name,aid,owner_key[1]));need(checked.path_view(saved)[0]==all_nodes,'Fresh cross-document Path differs')
    backing.contents=before_groups;owner.contents[19].value=high
    need(w.dump_verified(root,version)==baseline,'Unexpected mutation outside new Path/highwater')
    return output,dict(operation='create_cross_document_path',created={'document':dn,**ref(path)},runtime_end_keys=all_nodes,ordered_routes=routes,persisted_route_objects=1,full_route_infos=len(selected),changed_documents=[dn],all_other_document_bytes_unchanged=True,original_graph_rollback_verified=True,input_sha256=expected_hashes,output_sha256={**{k:sha(v)for k,v in output.items()},'$dest_catalog':sha(catalog)},atomic_group_commit_required=True,native_simulation_executed=False)


def create_itinerary(documents,catalog,*,document_paths,expected_hashes,complete_document_set,name,paths):
    need(type(name)is str and name and '\x00'not in name,'Explicit new itinerary name required')
    need(type(paths)is list and 1<=len(paths)<=1000,'Bounded nonempty exact Path sequence required')
    need(expected_hashes=={**{k:sha(v)for k,v in documents.items()},'$dest_catalog':sha(catalog)},'Complete input hash manifest mismatch')
    p=Project(documents,document_paths=document_paths,expected_hashes={k:expected_hashes[k]for k in documents},complete_document_set=complete_document_set);p.check_dest_catalog(catalog)
    selected=[];all_nodes=[];at=None
    for value in paths:
        dn,r=exact_reference(value);need(dn in p.roots,'Missing selected Path document')
        key=(dn,r[2]);need(at is None or key==at,'Path sequence not contiguous after native reconstruction')
        obj=p.owned(key,'OTPath',r);nodes,_=p.path_view(obj);selected.append((dn,obj));all_nodes+=nodes if at is None else nodes[1:];at=nodes[-1]
    need(len(set(all_nodes))==len(all_nodes),'Cyclic/repeated itinerary movement refused')
    need(not any(f.string(o.contents[1].value)==name for o in p.dests),'Project itinerary name already exists')
    dn=all_nodes[0][0];root=p.roots[dn];version=p.versions[dn];wrapper=root.contents[5].value;exclusive(root,wrapper)
    cr,cv=w.load(catalog);need(incoming(cr,cr)==0 and incoming(cr,cr.contents[0].value)==1,'Shared catalog root/backing refused')
    di=ns.arr([inf(o,d)for d,o in selected])
    dest=ns.obj(f.SHAPES['OTDest'][0],[('@',[ns.arr([selected[0][1]])]),('@',[ns.string(name)]),('ii',[-1,-1]),('@',[ns.string('')]),('@',[di]),('@',[wrapped('OTSafetyMarginArray',[])])])
    
    row=ns.obj([('OTDestInfo',1),('NSObject',0)],[('i',[17]),('@',[ns.string(name)]),('@',[ns.string(document_paths[dn])]),('i',[all_nodes[0][1]]),('@',[ns.arr([inf(o,d)for d,o in selected])])])
    target=wrapper.contents[0].value;old=f.mutable_array(target);oldgroups=list(target.contents);cback=cr.contents[0].value;cold=f.mutable_array(cback);coldgroups=list(cback.contents);baseline=w.dump_verified(root,version);cbaseline=w.dump_verified(cr,cv)
    w.set_elements(target,old+[dest]);w.set_elements(cback,cold+[row])
    output=dict(documents);output[dn]=w.dump_verified(root,version);outcat=w.dump_verified(cr,cv)
    checked=Project(output,document_paths=document_paths,expected_hashes={k:sha(v)for k,v in output.items()},complete_document_set=True);checked.check_dest_catalog(outcat)
    saved=next(o for o in checked.dests if f.string(o.contents[1].value)==name);need(checked.dest_view(saved)[0]==all_nodes,'Fresh cross-document itinerary differs')
    target.contents=oldgroups;cback.contents=coldgroups
    need(w.dump_verified(root,version)==baseline and w.dump_verified(cr,cv)==cbaseline,'Unexpected mutation outside new itinerary/catalog membership')
    return {'documents':output,'catalog':outcat},dict(operation='create_cross_document_itinerary',name=name,owner_document=dn,ordered_paths=paths,runtime_end_keys=all_nodes,persisted_path_objects=1,full_external_path_infos=len(paths),changed_dependencies=[dn,'$dest_catalog'],all_other_document_bytes_unchanged=True,original_graph_rollback_verified=True,input_sha256=expected_hashes,output_sha256={**{k:sha(v)for k,v in output.items()},'$dest_catalog':sha(outcat)},atomic_group_commit_required=True,native_simulation_executed=False)
