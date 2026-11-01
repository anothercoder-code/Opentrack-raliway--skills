"""Guarded current-archive OTPath append extraction; bytes only, no native runtime.
Dependencies are frozen wave2 current_archive codec/schema (not copied or modified).
"""
import hashlib
from opentrack_ai.current_archive import writer as w, path_functions as f
Unsupported = f.Unsupported
MAX_ROUTES = 10000  
END_FIELDS = ['i','f','f','f','i','i','@','@','i','@','@','@','@','@','f','@','@','@','@','i','i','f','i','ii']


def identity(obj):
    return {'name': f.string(obj.contents[1].value),
            'array_id': obj.contents[2].values[0], 'start_id': obj.contents[2].values[1]}


def exact_ref(ref):
    if not isinstance(ref, dict) or set(ref) != {'name','array_id','start_id'}:
        raise Unsupported('Exact name/array_id/start_id required')
    if not isinstance(ref['name'], str) or not ref['name'] or any(type(ref[k]) != int or not 0 <= ref[k] <= 2147483647 for k in ('array_id','start_id')):
        raise Unsupported('Explicit nonempty name and nonnegative signed-int32 IDs required')
    return ref


def select(root, kind, ref):
    exact_ref(ref)
    return f.select(root, kind, ref['name'], ref['array_id'], ref['start_id'])


def document(root):
    f.hierarchy(root,[('OTDocument',4),('NSObject',0)])
    if len(root.contents)!=21 or root.contents[2].encodings!=[b'@']:
        raise Unsupported('Current OTDocument v4 required')
    models=f.mutable_array(root.contents[2].value)
    ids=[]
    for o in models:
        if not o.contents or o.contents[0].encodings!=[b'i'] or type(o.contents[0].value)!=int:
            raise Unsupported('Invalid model identity')
        ids.append(o.contents[0].value)
    if len(set(ids))!=len(ids):raise Unsupported('Duplicate model IDs')
    return models


def route_nodes(route, models):
    f.shape(route,'OTRoute'); exact_ref(identity(route))
    nodes=f.mutable_array(route.contents[0].value)
    if route.contents[5].values[4]!=-1:raise Unsupported('Cross-document Route continuation is outside guarded domain')
    if len(nodes)<2:raise Unsupported('Route requires at least two Ends')
    for node in nodes:
        f.hierarchy(node,[('OTEndModel',7),('OTGraphicModel',1),('NSObject',0)])
        if [''.join(e.decode() for e in g.encodings) for g in node.contents]!=END_FIELDS:
            raise Unsupported('Unsupported End layout')
        if node not in models:raise Unsupported('End not in current document collection')
    if identity(route)['start_id']!=nodes[0].contents[0].value:
        raise Unsupported('Route start ID differs from owning End')
    wrapper=nodes[0].contents[15].value
    f.hierarchy(wrapper,[('OTRouteList',0),('OTMutableArray',0),('NSObject',0)])
    if len(wrapper.contents)!=1 or wrapper.contents[0].encodings!=[b'@'] or route not in f.mutable_array(wrapper.contents[0].value):
        raise Unsupported('Route not in owning End RouteList')
    candidates=f.mutable_array(wrapper.contents[0].value)
    key=identity(route)
    for other in candidates:
        f.shape(other,'OTRoute')
        if other is not route and (other.contents[2].values==[key['array_id'],key['start_id']] or f.string(other.contents[1].value)==key['name']):
            raise Unsupported('Ambiguous owner RouteList ID or name lookup')
    return nodes


def check_chain(chain, models):
    if not 1<=len(chain)<=MAX_ROUTES:raise Unsupported('Interface route count guard 1..10000')
    ends=[]
    for route in chain:
        nodes=route_nodes(route,models)
        if ends and ends[-1] is not nodes[0]:raise Unsupported('Disconnected Route chain')
        ends.extend(nodes if not ends else nodes[1:])
    if len({id(x) for x in chain})!=len(chain) or len({id(x) for x in ends})!=len(ends):
        raise Unsupported('Repeated Route or cyclic/revisited End outside guarded domain')
    return ends


def resolve_path(root, path, models):
    info=f.info(path); exact_ref(identity(path))
    refs=info['saved_references']
    if not 1<=len(refs)<=MAX_ROUTES:raise Unsupported('Empty or oversized Path infos')
    chain=[select(root,'OTRoute',r) for r in refs]
    ends=check_chain(chain,models)
    persisted=f.mutable_array(path.contents[0].value)
    if len(persisted)!=1 or persisted[0] is not chain[0]:raise Unsupported('Saved first Route/info mismatch')
    if identity(path)['start_id']!=ends[0].contents[0].value:raise Unsupported('Path owner mismatch')
    wrapper=ends[0].contents[17].value
    f.hierarchy(wrapper,[('OTPathList',0),('OTMutableArray',0),('NSObject',0)])
    if len(wrapper.contents)!=1 or wrapper.contents[0].encodings!=[b'@'] or path not in f.mutable_array(wrapper.contents[0].value):
        raise Unsupported('Path not in owning End PathList')
    for e in models:
        if w.kind(e)=='OTEndModel' and e is not ends[0] and len(e.contents)>17 and e.contents[17].value is wrapper:
            raise Unsupported('Aliased PathList ownership')
    for obj in w.objects(root):
        if w.kind(obj)=='OTPathList' and obj is not wrapper and path in f.mutable_array(obj.contents[0].value):
            raise Unsupported('Path belongs to multiple PathLists')
    key=identity(path)
    for other in f.mutable_array(wrapper.contents[0].value):
        f.shape(other,'OTPath')
        if other is not path and (other.contents[2].values==[key['array_id'],key['start_id']] or f.string(other.contents[1].value)==key['name']):
            raise Unsupported('Ambiguous owner PathList ID or name lookup')
    return chain


def reject_dependents(roots, target):
    """Fail closed including name-fallback references and unmapped document refs.
    Conservative ID/name matching may reject unrelated same-ID Paths; never misses
    an OTDest reference because an external document label cannot be resolved.
    """
    key=identity(target)
    for root in roots.values():
        for obj in w.objects(root):
            if w.kind(obj)=='OTDest':
                info=f.info(obj)
                if any(x is target for x in f.mutable_array(obj.contents[0].value)):
                    raise Unsupported('Target Path is referenced by an Itinerary')
                for ref in info['saved_references']:
                    if ref['name']==key['name'] or (ref['array_id'],ref['start_id'])==(key['array_id'],key['start_id']):
                        raise Unsupported('Target Path is referenced or potentially referenced by an Itinerary')
            elif w.kind(obj)=='OTArrayExtInfo':
                
                f.hierarchy(obj,[('OTArrayExtInfo',0),('OTArrayInfo',0),('NSObject',0)])
                if len(obj.contents)!=3 or [g.encodings for g in obj.contents]!=[[b'@'],[b'i',b'i'],[b'@']]:raise Unsupported('Unknown external reference shape')
                if f.string(obj.contents[0].value)==key['name'] or obj.contents[1].values==[key['array_id'],key['start_id']]:
                    raise Unsupported('Target Path has a saved external dependency')


def occurrences(root,target):
    from .graph_references import incoming
    return incoming(root,target)


def append_existing(documents, target_document, target_ref, source_kind, source_ref,
                    source_document=None, *, complete_document_set=False):
    """Return ({doc_key: bytes}, report); inputs never mutate; no disk writes.
    documents is the complete caller-selected archive set with explicit doc keys.
    Only target bytes change. Existing unreferenced local Path + connected local
    Route, or flattened local Path. All mapped docs scanned for dependencies.
    No claim of integrity for documents outside the provided collection.
    """
    if complete_document_set is not True:
        raise Unsupported('Caller must explicitly attest the supplied document collection is complete')
    if not isinstance(documents,dict) or not documents or any(not isinstance(k,str) or not k or not isinstance(v,bytes) for k,v in documents.items()):
        raise Unsupported('Nonempty explicit document-to-bytes mapping required')
    if target_document not in documents:raise Unsupported('Missing target document mapping')
    source_document=target_document if source_document is None else source_document
    if source_document not in documents:raise Unsupported('Missing source document mapping')
    if source_document!=target_document:raise Unsupported('Cross-document append not implemented; no mapping guesses')
    if source_kind not in ('OTRoute','OTPath'):raise Unsupported('Source must be Route or Path')
    loaded={k:w.load(v) for k,v in documents.items()}
    roots={k:v[0] for k,v in loaded.items()}
    for root in roots.values():document(root)
    root,version=loaded[target_document];models=document(root)
    target=select(root,'OTPath',target_ref);source=select(root,source_kind,source_ref)
    if source is target:raise Unsupported('Self append is outside guarded domain')
    chain=resolve_path(root,target,models)
    extra=resolve_path(root,source,models) if source_kind=='OTPath' else [source]
    check_chain(chain+extra,models)
    reject_dependents(roots,target)
    
    
    infos=target.contents[4].value
    if occurrences(root,infos)!=1:
        raise Unsupported('Aliased routeInfoArray')
    template=f.mutable_array(infos)[0];rebuilt=[]
    for route in chain+extra:
        item=f.clone(template);item.contents[0].value=route.contents[1].value
        item.contents[1].values=list(route.contents[2].values);rebuilt.append(item)
    old_infos=target.contents[4].value
    target.contents[4].value=f.array_like(infos,rebuilt)
    
    output=w.dump_verified(root,version)
    after,_=w.load(output)
    actual=resolve_path(after,select(after,'OTPath',target_ref),document(after))
    if [identity(r) for r in actual]!=[identity(r) for r in chain+extra]:raise Unsupported('Fresh reload chain mismatch')
    
    
    target.contents[4].value=old_infos
    baseline=w.dump_verified(root,version)
    before,sv=w.load(documents[target_document])
    if baseline!=w.dump_verified(before,sv):raise Unsupported('Unexpected non-target graph mutation')
    result=dict(documents);result[target_document]=output
    return result,{'operation':'append_existing_path_routes','source_kind':source_kind,
        'functions':['0x55971c' if source_kind=='OTRoute' else '0x5595fc','0x55a050','0x55a600'],
        'runtime_routes_before':len(chain),'runtime_routes_after':len(chain+extra),
        'persisted_route_count':1,'saved_references':[identity(r) for r in chain+extra],
        'input_sha256':hashlib.sha256(documents[target_document]).hexdigest(),
        'output_sha256':hashlib.sha256(output).hexdigest(),
        'all_other_document_bytes_unchanged':True,'native_gui_or_simulation_verified':False}
