"""Current archive-only OTDest factory; explicitly not init/copy/runtime emulation."""
import hashlib
from opentrack_ai.current_archive import writer as w
from opentrack_ai.current_archive import path_functions as p
Unsupported=p.Unsupported

def sha(data): return hashlib.sha256(data).hexdigest()
def check(o, chain, enc):
 p.hierarchy(o,chain)
 if [b''.join(g.encodings).decode() for g in o.contents]!=enc or any(len(g.encodings)!=len(g.values) for g in o.contents):raise Unsupported('Unsupported field layout')
 return o

def wrapper(o,kind):
 check(o,[(kind,0)]+([] if kind=='OTMutableArray' else [('OTMutableArray',0)])+[('NSObject',0)],['@'])
 return p.mutable_array(o.contents[0].value)

def dest(o):
 check(o,[('OTDest',1),('OTOrgArray',2),('OTMutableArray',0),('NSObject',0)],['@','@','ii','@','@','@'])
 p.string(o.contents[1].value);p.string(o.contents[3].value)
 if o.contents[2].values!=[-1,-1]:raise Unsupported('Only current unnumbered Itinerary template supported')
 return refs(o.contents[4].value)

def refs(a):
 result=[]
 for x in p.mutable_array(a):
  check(x,[('OTArrayExtInfo',0),('OTArrayInfo',0),('NSObject',0)],['@','ii','@'])
  result.append((p.string(x.contents[2].value),p.string(x.contents[0].value),*x.contents[1].values))
 return result

from .graph_references import incoming_counts

def exclusive_destination_owner(root):
 counts=incoming_counts(root);wrapper=root.contents[5].value;backing=wrapper.contents[0].value
 if counts.get(id(root),0)!=0 or counts.get(id(wrapper),0)!=1 or counts.get(id(backing),0)!=1:
  raise Unsupported('Aliased destination owner/container (including nested or cyclic incoming edges)')

def exclusive_catalog_owner(root):
 counts=incoming_counts(root)
 if counts.get(id(root),0)!=0 or counts.get(id(root.contents[0].value),0)!=1:
  raise Unsupported('Aliased catalog owner/container (including nested or cyclic incoming edges)')

def create_itinerary(documents,catalog,*,expected_hashes,document_paths,owner_document,name,path_refs,template_name,description=''):
 """Return ({'documents': name->bytes, 'catalog': bytes}, receipt).
 documents MUST be complete project OTDocument set, declared by exact hash manifest.
 document_paths maps document names to exact authoritative catalog filenames, not inferred.
 path_refs exact name/array_id/start_id dicts, all owned in owner_document.
 IDs intentionally [-1,-1], as observed current native document/catalog representation.
 """
 if not isinstance(documents,dict) or not documents or set(document_paths)!=set(documents):raise Unsupported('Explicit complete document mapping required')
 actual={k:sha(v) for k,v in documents.items()};actual['$catalog']=sha(catalog)
 if actual!=expected_hashes:raise Unsupported('Complete dependency hash manifest mismatch')
 if len(set(document_paths.values()))!=len(documents):raise Unsupported('Ambiguous catalog document mapping')
 if owner_document not in documents or not isinstance(name,str) or not name:raise Unsupported('Explicit owner/name required')
 if not isinstance(path_refs,list) or len(path_refs)!=1:raise Unsupported('This verified factory requires exactly one Path')
 roots={};versions={};definitions={};paths={};models={}
 for dn,data in documents.items():
  r,v=w.load(data);check(r,[('OTDocument',4),('NSObject',0)],['i','i','@','i','i','@','@','@','ffff','ffff','ffff','f','@','@','ffff','iii','ff','@','@','@','@'])
  roots[dn]=r;versions[dn]=v;models[dn]=p.mutable_array(r.contents[2].value)
  ids=[m.contents[0].value for m in models[dn]]
  if len(set(ids))!=len(ids):raise Unsupported('Duplicate model ID')
  for o in w.objects(r):
   if w.kind(o)=='OTPath':
    inf=p.info(o);key=(dn,inf['name'],inf['array_id'],inf['start_id'])
    if key in paths:raise Unsupported('Duplicate Path identity')
    paths[key]=o
  for o in wrapper(r.contents[5].value,'OTMutableArray'):
   rr=dest(o);nm=p.string(o.contents[1].value)
   if nm in definitions:raise Unsupported('Duplicate Itinerary name')
   definitions[nm]=(dn,o,rr)
 cr,cv=w.load(catalog);entries=wrapper(cr,'OTDestInfoList');catalog_names=set()
 for row in entries:
  check(row,[('OTDestInfo',1),('NSObject',0)],['i','@','@','i','@'])
  nm=p.string(row.contents[1].value)
  if row.contents[0].value!=17 or nm in catalog_names or nm not in definitions:raise Unsupported('Catalog mismatch/duplicate')
  catalog_names.add(nm);dn,o,rr=definitions[nm]
  if p.string(row.contents[2].value)!=document_paths[dn] or refs(row.contents[4].value)!=rr or not rr or row.contents[3].value!=rr[0][3]:raise Unsupported('Catalog/document pairing mismatch')
  for key in rr:
   if key not in paths:raise Unsupported('Unresolved project Path reference')
  persisted=p.mutable_array(o.contents[0].value)
  if len(persisted)!=1 or rr[0][0]!=dn or persisted[0] is not paths[rr[0]]:raise Unsupported('Invalid persisted first Path identity')
 if catalog_names!=set(definitions):raise Unsupported('Incomplete global catalog')
 if name in definitions:raise Unsupported('Itinerary name already exists')
 if template_name not in definitions or definitions[template_name][0]!=owner_document:raise Unsupported('Explicit current owner template required')
 template=definitions[template_name][1]
 if wrapper(template.contents[5].value,'OTSafetyMarginArray'):raise Unsupported('Only explicitly empty-margin current template supported; nonempty copy not implemented')
 selected=[];previous=None;start=None;finish=None;visited_ends=set()
 for ref in path_refs:
  if not isinstance(ref,dict) or set(ref)!={'name','array_id','start_id'} or type(ref['array_id'])!=int or type(ref['start_id'])!=int:raise Unsupported('Exact Path reference required')
  key=(owner_document,ref['name'],ref['array_id'],ref['start_id'])
  if key not in paths or paths[key] in selected:raise Unsupported('Missing/repeated Path')
  path=paths[key];routes=[]
  for route_ref in p.info(path)['saved_references']:
   route=p.select(roots[owner_document],'OTRoute',**{'name':route_ref['name'],'array_id':route_ref['array_id'],'start_id':route_ref['start_id']})
   es=p.mutable_array(route.contents[0].value)
   if route.contents[5].values[4]!=-1 or len(es)<2 or any(w.kind(e)!='OTEndModel' or e not in models[owner_document] for e in es):raise Unsupported('Nonlocal/invalid Route')
   for e in es:check(e,[('OTEndModel',7),('OTGraphicModel',1),('NSObject',0)],['i','f','f','f','i','i','@','@','i','@','@','@','@','@','f','@','@','@','@','i','i','f','i','ii'])
   if es[0].contents[0].value!=route_ref['start_id'] or route not in wrapper(es[0].contents[15].value,'OTRouteList'):raise Unsupported('Route owner mismatch')
   if previous is not None and previous is not es[0]:raise Unsupported('Disconnected Path/Route chain')
   new_ends=es if previous is None else es[1:]
   for endpoint in new_ends:
    if id(endpoint) in visited_ends:raise Unsupported('Repeated End/cyclic Route chain unsupported')
    visited_ends.add(id(endpoint))
   if start is None:start=es[0]
   previous=es[-1];finish=previous;routes.append(route)
  if not routes or p.mutable_array(path.contents[0].value)!=routes[:1]:raise Unsupported('Path first Route mismatch')
  first=p.mutable_array(routes[0].contents[0].value)[0]
  if first.contents[0].value!=ref['start_id'] or path not in wrapper(first.contents[17].value,'OTPathList'):raise Unsupported('Path owner mismatch')
  selected.append(path)
 if start is finish:raise Unsupported('Cyclic Itinerary unsupported')
 exclusive_destination_owner(roots[owner_document]);exclusive_catalog_owner(cr)
 new=p.clone(template);new.contents[0].value=p.array_like(template.contents[0].value,selected[:1])
 new.contents[1].value=p.fresh_string(template.contents[1].value,name);new.contents[3].value=p.fresh_string(template.contents[3].value,description)
 infos=[];it=p.mutable_array(template.contents[4].value)[0]
 for path in selected:
  row=p.clone(it);row.contents[0].value=path.contents[1].value;row.contents[1].values=list(path.contents[2].values);row.contents[2].value=p.fresh_string(it.contents[2].value,owner_document);infos.append(row)
 new.contents[4].value=p.array_like(template.contents[4].value,infos)
 margin=p.clone(template.contents[5].value);margin.contents[0].value=p.array_like(margin.contents[0].value,[]);new.contents[5].value=margin
 target=roots[owner_document].contents[5].value.contents[0].value

 w.set_elements(target,p.mutable_array(target)+[new])
 ct=next(x for x in entries if p.string(x.contents[1].value)==template_name);ci=p.clone(ct)
 ci.contents[1].value=p.fresh_string(ct.contents[1].value,name);ci.contents[3].value=start.contents[0].value
 ci.contents[4].value=p.array_like(ct.contents[4].value,infos)

 w.set_elements(cr.contents[0].value,entries+[ci])
 output=dict(documents);output[owner_document]=w.dump_verified(roots[owner_document],versions[owner_document]);outcat=w.dump_verified(cr,cv)
 receipt={'operation':'create_current_local_itinerary','input_sha256':actual,'output_sha256':{**{k:sha(v) for k,v in output.items()},'$catalog':sha(outcat)},'document_paths':dict(document_paths),'owner':owner_document,'name':name,'array_identity':[-1,-1],'first_end':start.contents[0].value,'last_end':finish.contents[0].value,'ordered_paths':refs(new.contents[4].value),'template':template_name,'margin_policy':'explicit empty current template; independent new array','changed_dependencies':[owner_document,'$catalog'],'atomic_bundle_commit_required':True,'native_init_copy_gui_simulation_equivalence':False}
 return {'documents':output,'catalog':outcat},receipt
