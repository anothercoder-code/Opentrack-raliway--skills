"""Finite three-station + infrastructure-only wye project, pure bytes.

Not a grid, stopping-area model, arbitrary network or simulation.
"""
from opentrack_ai.current_archive.multi_document import core as cd, generate as g, operations as ops, bundle as cb
from opentrack_ai.current_archive import writer as w, catalogs as cats, path_functions as pf, route_factory as rf
from opentrack_ai.current_archive.zero_generation import topology as tp, native_signal_routes as ns
from opentrack_ai.current_archive.zero_operations import station_binding as sb, run_bundle as rb

def need(x,m):
 if not x: raise ValueError(m)
def edge(k,a,b,length):
 return dict(key=k,**{'from':list(a),'to':list(b)},length_m=length,radius_m=0.,gradient_per_mille=0.,track_type=1,loop_type=1,dlink_type=1,equal_speed=True,rack_rail=False,speeds=[dict(train_type='0',speed12_kmh=80,speed21_kmh=80)],remark='Synthetic branch data; geometry not physical alignment certification',track_name=k,line_name='branch')
def validate_spec(s):
 need(type(s)is dict and set(s)=={'topology','arm_length_m','junction_edge_length_m','execution_root'},'Exact branch spec required')
 need(s['topology']=='three_arm_wye','Only three_arm_wye, not grid or arbitrary crossing, is supported')
 for k in ('arm_length_m','junction_edge_length_m'):need(type(s[k])is int and 1<=s[k]<=100000,'Integer 1..100000 metres required: '+k)
 need(rb.root_path(s['execution_root'],'windows')==s['execution_root'],'Canonical Windows execution root required')
def generate_network_project(sources,*,expected_hashes,spec):
 need(type(sources)is dict and set(sources)=={'header','shapes','depot','trains','courses','timetable'},'Exact six sources required')
 need(all(type(v)is bytes and v for v in sources.values()),'Immutable nonempty bytes required')
 need(type(expected_hashes)is dict and expected_hashes=={k:cd.sha(v)for k,v in sources.items()},'Exact source hashes required')
 validate_spec(spec);names=['A','B','C'];docs={};ids={};station_rows=[];length=spec['arm_length_m'];junction_length=spec['junction_edge_length_m']
 for dn in names+['J']:
  if dn!='J': topo={'vertices':[g.vertex('station',20),g.vertex('boundary',220)],'edges':[edge('arm',('station',1),('boundary',0),length)]}
  else:
   vs=[];es=[]
   for i,n in enumerate(names):
    vs += [g.vertex('boundary_'+n,20+100*i),g.vertex('wye_'+n,70+100*i)]
    es.append(edge('arm_'+n,('boundary_'+n,1),('wye_'+n,0),length))
   for a,b in [('A','B'),('B','C'),('C','A')]:es.append(edge('link_'+a+b,('wye_'+a,1),('wye_'+b,1),junction_length))
   topo={'vertices':vs,'edges':es}
  blob,rep=tp.generate_network(sources['header'],sources['shapes'],topo);ids[dn]=rep['vertex_end_ids']
  signalids=ids[dn]['station'] if dn!='J' else sum([ids[dn]['wye_'+n]for n in names],[])
  for eid in signalids:
   rr,_=w.load(blob);mm,byid=rf.document(rr)
   blob,_=ns.build_main_signal(blob,end_id=eid,name='S:'+dn+':'+str(eid),model_id=max(x.contents[0].value for x in mm)+1,placement=g.signal_placement(byid[eid],50,20),sight_m=500,delay_s=0.,show_symbol=True,show_icon=True)
  if dn!='J':
   blob,st,_=sb.bind_stations(blob,[dict(sign=dn,name='Station '+dn,end_ids=[ids[dn]['station'][0]],placement=g.placement(20,50),station_type_raw=2,interlock_type_raw=4,icon_show_type_raw=1,timing_point=True)])
   station_rows.append((dn,cats.station_items(w.load(st)[0])[dn]))
  else:
   
   
   for a in names:
    for b in names:
     if a==b:continue
     blob,_=ns.build_route(blob,name='R:J:'+a+'-'+b,end_ids=[ids['J']['wye_'+a][0],ids['J']['wye_'+b][1]],description='',release_groups='global',reserve_previous=False)
  docs[dn]=blob
 roots={};versions={};models={}
 for dn,blob in docs.items():roots[dn],versions[dn]=w.load(blob);_,models[dn]=rf.document(roots[dn])
 for dn in names:
  for source,eid,target,tid in [(dn,ids[dn]['boundary'][1],'J',ids['J']['boundary_'+dn][0]),('J',ids['J']['boundary_'+dn][0],dn,ids[dn]['boundary'][1])]:
   e=models[source][eid];need(w.kind(e)=='OTEndModel'and all(e.contents[i].value is None for i in (9,10,11,12)),'Unused nonstation Connector end required')
   e.clazz=w.Class(b'OTConnModel',1,e.clazz);e.contents +=[w.TypedValue(b'@',ns.string('')),w.TypedValue(b'@',ns.string(target)),w.TypedValue(b'i',tid),w.TypedValue(b'i',0)]
 
 refs={}
 for dn in names:
  for src,dst,start,boundary,finish,host,label in [(dn,'J',ids[dn]['station'][0],ids[dn]['boundary'][0],ids['J']['wye_'+dn][0],ids['J']['boundary_'+dn][0],'in'),('J',dn,ids['J']['wye_'+dn][1],ids['J']['boundary_'+dn][1],ids[dn]['station'][1],ids[dn]['boundary'][1],'out')]:
   owner=models[src][start];aid=owner.contents[19].value+1;name='R:'+dn+':'+label
   r=g.route(name,aid,start,[owner,models[src][boundary]],2);frag=g.route(name,aid,start,[models[dst][finish]],-1,True)
   target=owner.contents[15].value.contents[0].value;w.set_elements(target,pf.mutable_array(target)+[r]);owner.contents[19].value=aid
   remote=models[dst][host].contents[15].value.contents[0].value;w.set_elements(remote,pf.mutable_array(remote)+[frag]);refs[(dn,label)]={'document':src,**cd.ref(r)}
 docs={dn:w.dump_verified(roots[dn],versions[dn])for dn in roots};paths={dn:spec['execution_root']+'/OTDocuments/'+dn+'.opentrack'for dn in docs}
 dest=w.dump_verified(g.wrapped('OTDestInfoList',[]),1000)
 
 for a in names:
  for b in names:
   if a==b:continue
   root,_=w.load(docs['J']);routes=[o for o in w.objects(root)if w.kind(o)=='OTRoute'and pf.string(o.contents[1].value)=='R:J:'+a+'-'+b];need(len(routes)==1,'Unique local route required')
   seq=[refs[(a,'in')],{'document':'J',**cd.ref(routes[0])},refs[(b,'out')]]
   docs,p=ops.create_path(docs,dest,document_paths=paths,expected_hashes={**{k:cd.sha(v)for k,v in docs.items()},'$dest_catalog':cd.sha(dest)},complete_document_set=True,name='P:'+a+'-'+b,routes=seq)
   result,_=ops.create_itinerary(docs,dest,document_paths=paths,expected_hashes={**{k:cd.sha(v)for k,v in docs.items()},'$dest_catalog':cd.sha(dest)},complete_document_set=True,name='I:'+a+'-'+b,paths=[p['created']]);docs=result['documents'];dest=result['catalog']
 project=cd.Project(docs,document_paths=paths,expected_hashes={k:cd.sha(v)for k,v in docs.items()},complete_document_set=True);project.check_dest_catalog(dest);traces={}
 for d in project.dests:
  label=pf.string(d.contents[1].value);nodes,_=project.dest_view(d);dist=0;stations=[];edgekeys=[]
  for i,key in enumerate(nodes):
   if i:
    ek=project.edge_between(nodes[i-1],key);dist+=project.model(ek).contents[9].values[1];edgekeys.append(list(ek))
   e=project.model(key)
   if e.contents[20].value==2:stations.append(cats.text(e.contents[12].value.contents[7].value))
  a,b=label[2:].split('-');need(stations==[a,b],'Unexpected station event trace');need(dist==4*length+junction_length,'Unexpected actual physical length')
  traces[label]={'station_order':stations,'distance_m':dist,'nodes':[list(k)for k in nodes],'edges':edgekeys}
 files={'OTDocuments/'+dn+'.opentrack':b for dn,b in docs.items()};cp={r:'OTData/branch.'+r for r in rb.CATALOG_KEYS}
 for role,path in cp.items():files[path]=dest if role=='dest'else w.dump_verified(sb.dictionary(station_rows),1000)if role=='stations'else g.empty_catalog(sources[role],role)
 members=['OTDocuments/'+dn+'.opentrack'for dn in docs];run,rr=rb.build_run(files,catalog_paths=cp,document_paths=members,execution_root=spec['execution_root'],path_style='windows',train_types=['instructional'],template=b'');rb.verify_run(run,files,catalog_paths=cp,document_paths=members,execution_root=spec['execution_root'],path_style='windows',train_types=['instructional']);files['branch.run']=run
 bundle_report=cb.validate_no_service_bundle(files,run_file='branch.run',expected_hashes={k:cd.sha(v)for k,v in files.items()},complete_file_set=True)
 return files,{'operation':'generate_three_station_branch_network','domain':'three_arm_wye_not_grid','source_sha256':expected_hashes,'members':{k:{'sha256':cd.sha(v),'bytes':len(v)}for k,v in files.items()},'document_paths':paths,'station_documents':names,'infrastructure_only_documents':['J'],'one_station_per_station_document':True,'itineraries':traces,'reconstruction':project.report(),'bundle_validation':bundle_report,'catalog_policy':'Shape donors only: all existing donor service entries and auxiliary arrays are intentionally omitted from the new no-service project; source bytes unchanged','run':rr,'service_catalogs_empty':True,'station_stopping_regions_supported':False,'grid_supported':False,'flat_crossing_supported':False,'native_runtime_ready':False,'native_simulation_executed':False,'physical_alignment_certified':False,'scope':'Finite triangle wye with three reciprocal external links, six directed station movements, point stations only; diagram coordinates and zero radius are not an engineered alignment'}

def generate_network(header_document,shapes,templates,spec):
 need(type(templates)is dict and set(templates)=={'depot','trains','courses','timetable'},'Four catalog donors required')
 sources={'header':header_document,'shapes':shapes,**templates}
 return generate_network_project(sources,expected_hashes={k:cd.sha(v)for k,v in sources.items()},spec=spec)
