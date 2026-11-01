"""Current local multi-Path OTDest composition; no GUI/runtime equivalence.
Derived from frozen wave7 itinerary_factory with explicitly reviewed sequence semantics.
"""
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

from opentrack_ai.current_archive.graph_references import incoming_counts

def exclusive_destination_owner(root):
 counts=incoming_counts(root);wrapper=root.contents[5].value;backing=wrapper.contents[0].value
 if counts.get(id(root),0)!=0 or counts.get(id(wrapper),0)!=1 or counts.get(id(backing),0)!=1:
  raise Unsupported('Aliased destination owner/container (including nested or cyclic incoming edges)')

def exclusive_catalog_owner(root):
 counts=incoming_counts(root)
 if counts.get(id(root),0)!=0 or counts.get(id(root.contents[0].value),0)!=1:
  raise Unsupported('Aliased catalog owner/container (including nested or cyclic incoming edges)')

def validate_fixed_pair_route_links(ends,models):
 """Bounded same-document edge membership audit, not interlocking validation.
 The selected current Route crosses current End.idOfRelated then an Edge to
 its next stored End. Connector models and unresolved relations fail closed.
 """
 by_id={o.contents[0].value:o for o in models}
 for first,last in zip(ends,ends[1:]):
  related=by_id.get(first.contents[8].value)
  if related is None or w.kind(related)!='OTEndModel':
   raise Unsupported('Route requires unresolved related End')
  check(related,[('OTEndModel',7),('OTGraphicModel',1),('NSObject',0)],['i','f','f','f','i','i','@','@','i','@','@','@','@','@','f','@','@','@','@','i','i','f','i','ii'])
  if related.contents[8].value!=first.contents[0].value:
   raise Unsupported('Route requires unresolved or nonreciprocal related End')
  candidates=[]
  for edge in models:
   if w.kind(edge)!='OTEdgeModel':continue
   chain,enc=p._COUNTER_ROLES['OTEdgeModel'];check(edge,chain,enc)
   a,b=edge.contents[7].value,edge.contents[8].value
   if (a is related and b is last) or (b is related and a is last):candidates.append(edge)
  if len(candidates)!=1:raise Unsupported('Route End sequence has missing or ambiguous connecting Edge')
  edge=candidates[0]
  if edge not in [related.contents[i].value for i in (9,10)] or edge not in [last.contents[i].value for i in (9,10)]:
   raise Unsupported('Route Edge is not linked from both incident Ends')

def validate_path_boundaries(occurrences):
 """Pure sequence rule supported by 0x489b10, not a track physics validator.
 Each occurrence is (Path object, first End object, last End object).
 Repeat identities at non-adjacent positions are preserved; no set de-duplication.
 """
 if not occurrences:raise Unsupported('Empty Itinerary')
 for previous,current in zip(occurrences,occurrences[1:]):
  if previous[0] is current[0]:raise Unsupported('Consecutive same Path unsupported by native continuation selection')
  if previous[2] is not current[1]:raise Unsupported('Disconnected Path chain; turnback domain not implemented')
 return {'closed_endpoint':occurrences[0][1] is occurrences[-1][2],
         'repeated_path':len({id(x[0]) for x in occurrences})<len(occurrences)}

def create_itinerary(documents,catalog,*,expected_hashes,document_paths,owner_document,name,path_refs,template_name,description='',template_document=None,template_catalog=None,expected_template_hashes=None):
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
 if not isinstance(path_refs,list) or not 1<=len(path_refs)<=10000:raise Unsupported('Interface Path count range 1..10000')
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
 external_objects=set();external_template=template_document is not None or template_catalog is not None
 if external_template:
  if definitions or entries:raise Unsupported('External type template currently requires empty destination document set/catalog')
  if not isinstance(template_document,bytes) or not isinstance(template_catalog,bytes) or expected_template_hashes!={'document':sha(template_document),'catalog':sha(template_catalog)}:raise Unsupported('Explicit external Dest template bytes/hash pair required')
  tr,_=w.load(template_document);tc,_=w.load(template_catalog)
  check(tr,[('OTDocument',4),('NSObject',0)],['i','i','@','i','i','@','@','@','ffff','ffff','ffff','f','@','@','ffff','iii','ff','@','@','@','@'])
  matches=[o for o in wrapper(tr.contents[5].value,'OTMutableArray') if p.string(o.contents[1].value)==template_name]
  if len(matches)!=1:raise Unsupported('External Dest template identity must resolve once')
  template=matches[0];template_refs=dest(template)
  template_entries=wrapper(tc,'OTDestInfoList');matches=[o for o in template_entries if p.string(o.contents[1].value)==template_name]
  if len(matches)!=1:raise Unsupported('External catalog template identity must resolve once')
  ct=matches[0];check(ct,[('OTDestInfo',1),('NSObject',0)],['i','@','@','i','@'])
  if ct.contents[0].value!=17 or not template_refs or refs(ct.contents[4].value)!=template_refs or ct.contents[3].value!=template_refs[0][3]:raise Unsupported('External template catalog/document mismatch')
  external_objects={id(x) for rr in (tr,tc) for x in w.objects(rr)}
 else:
  if template_name not in definitions or definitions[template_name][0]!=owner_document:raise Unsupported('Explicit current owner template required')
  template=definitions[template_name][1];ct=next(x for x in entries if p.string(x.contents[1].value)==template_name)
 if wrapper(template.contents[5].value,'OTSafetyMarginArray'):raise Unsupported('Only explicitly empty-margin current template supported; nonempty copy not implemented')
 selected=[];start=None;finish=None;path_boundaries=[]
 
 
 previous_path=None
 for ref in path_refs:
  if not isinstance(ref,dict) or set(ref)!={'name','array_id','start_id'} or type(ref['array_id'])!=int or type(ref['start_id'])!=int:raise Unsupported('Exact Path reference required')
  key=(owner_document,ref['name'],ref['array_id'],ref['start_id'])
  if key not in paths:raise Unsupported('Missing Path')
  path=paths[key]
  if path is previous_path:raise Unsupported('Consecutive same Path unsupported by native continuation selection')
  previous=None;visited_ends=set();routes=[]
  for route_ref in p.info(path)['saved_references']:
   route=p.select(roots[owner_document],'OTRoute',**{'name':route_ref['name'],'array_id':route_ref['array_id'],'start_id':route_ref['start_id']})
   es=p.mutable_array(route.contents[0].value)
   if route.contents[5].values[4]!=-1 or len(es)<2 or any(w.kind(e)!='OTEndModel' or e not in models[owner_document] for e in es):raise Unsupported('Nonlocal/invalid Route')
   for e in es:check(e,[('OTEndModel',7),('OTGraphicModel',1),('NSObject',0)],['i','f','f','f','i','i','@','@','i','@','@','@','@','@','f','@','@','@','@','i','i','f','i','ii'])
   validate_fixed_pair_route_links(es,models[owner_document])
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
  path_boundaries.append((path,first,finish));selected.append(path);previous_path=path
 validate_path_boundaries(path_boundaries)
 exclusive_destination_owner(roots[owner_document]);exclusive_catalog_owner(cr)
 baseline_doc=w.dump_verified(roots[owner_document],versions[owner_document]);baseline_cat=w.dump_verified(cr,cv)
 new=p.clone(template);new.contents[2].values=[-1,-1];new.contents[0].value=p.array_like(template.contents[0].value,selected[:1])
 new.contents[1].value=p.fresh_string(template.contents[1].value,name);new.contents[3].value=p.fresh_string(template.contents[3].value,description)
 infos=[];it=p.mutable_array(template.contents[4].value)[0]
 for path in selected:
  row=p.clone(it);row.contents[0].value=path.contents[1].value;row.contents[1].values=list(path.contents[2].values);row.contents[2].value=p.fresh_string(it.contents[2].value,owner_document);infos.append(row)
 new.contents[4].value=p.array_like(template.contents[4].value,infos)
 margin=p.clone(template.contents[5].value);margin.contents[0].value=p.array_like(margin.contents[0].value,[]);new.contents[5].value=margin
 target=roots[owner_document].contents[5].value.contents[0].value

 p.mutable_array(target)
 target.contents[0].value+=1;target.contents.append(w.TypedValue(b'@',new))
 ci=p.clone(ct);ci.contents[0].value=17;ci.contents[2].value=p.fresh_string(ct.contents[2].value,document_paths[owner_document])
 ci.contents[1].value=p.fresh_string(ct.contents[1].value,name);ci.contents[3].value=start.contents[0].value
 ci.contents[4].value=p.array_like(ct.contents[4].value,infos)

 cr.contents[0].value.contents[0].value+=1;cr.contents[0].value.contents.append(w.TypedValue(b'@',ci))
 if external_objects & {id(x) for rr in [*roots.values(),cr] for x in w.objects(rr)}:raise Unsupported('External template retained source object dependencies')
 output=dict(documents);output[owner_document]=w.dump_verified(roots[owner_document],versions[owner_document]);outcat=w.dump_verified(cr,cv)
 
 
 verify_doc,vv=w.load(output[owner_document]);backing=verify_doc.contents[5].value.contents[0].value
 objects=p.mutable_array(backing);created=[o for o in objects if p.string(o.contents[1].value)==name]
 if len(created)!=1 or refs(created[0].contents[4].value)!=refs(new.contents[4].value):raise Unsupported('Saved Itinerary reference readback mismatch')
 backing.contents=[backing.contents[0]]+[g for g in backing.contents[1:] if g.value is not created[0]];backing.contents[0].value-=1
 if w.dump_verified(verify_doc,vv)!=baseline_doc:raise Unsupported('Existing document graph changed')
 verify_cat,vv=w.load(outcat);backing=verify_cat.contents[0].value
 rows=p.mutable_array(backing);created=[o for o in rows if p.string(o.contents[1].value)==name]
 if len(created)!=1 or refs(created[0].contents[4].value)!=refs(new.contents[4].value):raise Unsupported('Saved catalog reference readback mismatch')
 backing.contents=[backing.contents[0]]+[g for g in backing.contents[1:] if g.value is not created[0]];backing.contents[0].value-=1
 if w.dump_verified(verify_cat,vv)!=baseline_cat:raise Unsupported('Existing catalog graph changed')
 receipt={'operation':'create_current_local_multi_path_itinerary','external_template_hashes':expected_template_hashes if external_template else None,'external_template_object_dependencies_retained':False,'input_sha256':actual,'output_sha256':{**{k:sha(v) for k,v in output.items()},'$catalog':sha(outcat)},'document_paths':dict(document_paths),'owner':owner_document,'name':name,'array_identity':[-1,-1],'first_end':start.contents[0].value,'last_end':finish.contents[0].value,'ordered_paths':refs(new.contents[4].value),'template':template_name,'margin_policy':'explicit empty current template; independent new array','changed_dependencies':[owner_document,'$catalog'],'atomic_bundle_commit_required':True,'native_init_copy_gui_simulation_equivalence':False,'closed_endpoint':start is finish,'nonconsecutive_path_reuse':len({id(x) for x in selected})<len(selected),'path_count':len(selected),'original_graph_canonical_roundtrip_unchanged':True,'continuation_domain':'same End object, different adjacent Path; no turnbacks or cross-document Paths','route_validation':'fixed reciprocal End pairs and actual Edge incidence; not signal/interlocking/simulation proof','c_evidence':['0x489b10','0x488ff4','0x477944','0x478058','0x4754f4','0x4c2190','0x4c751c']}
 return {'documents':output,'catalog':outcat},receipt


def extend_into_new_itinerary(documents,catalog,*,existing_name,additional_path_refs,**kwargs):
 """Append an explicit sequence into a NEW named Itinerary, preserving the old one.
 This is a composite data operation, NOT original in-place append/copy emulation.
 The caller must provide current complete dependency hashes, mapping and template.
 """
 if not isinstance(additional_path_refs,list) or not additional_path_refs:
  raise Unsupported('Nonempty explicit additional Path references required')
 owner=kwargs.get('owner_document')
 if owner not in documents:raise Unsupported('Owner document missing')
 root,_=w.load(documents[owner]);matches=[o for o in wrapper(root.contents[5].value,'OTMutableArray') if p.string(o.contents[1].value)==existing_name]
 if len(matches)!=1:raise Unsupported('Existing Itinerary identity must resolve once in owner')
 existing=dest(matches[0])
 if any(row[0]!=owner for row in existing):raise Unsupported('Existing nonlocal Itinerary unsupported')
 combined=[{'name':row[1],'array_id':row[2],'start_id':row[3]} for row in existing]+additional_path_refs
 out,receipt=create_itinerary(documents,catalog,path_refs=combined,**kwargs)
 receipt['operation']='extend_into_new_current_local_itinerary'
 receipt['source_itinerary']=existing_name
 receipt['existing_itinerary_preserved']=True
 return out,receipt
