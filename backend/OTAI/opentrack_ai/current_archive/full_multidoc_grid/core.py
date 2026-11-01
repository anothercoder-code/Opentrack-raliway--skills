"""Fixed audited terminal grid repartition, pure bytes. New signal plan, not native execution."""
import copy,json
from opentrack_ai.current_archive import writer as w,path_functions as pf,route_factory as rf,catalogs as cats
from opentrack_ai.current_archive.multi_document import core as cd,generate as g
from opentrack_ai.current_archive.zero_generation import topology as tp,native_signal_routes as ns
from opentrack_ai.current_archive.zero_operations import run_bundle as rb
from opentrack_ai.current_archive.graphic_alignment import make_placement,make_signal_placement,copy_native_alignment

HASHES = {'terminal_document':'c801bea7067e8c5eadc884bdeedfc516daeb4d0c86fe925486a90fd01ff44458','request':'dab63674467c2ef5fd30893691747d72e50f9318781d3ed4e4668aa609788755','shapes':'8ee95dbc78c84211cfbea472bcd2c6bae55c68abf8a6f7ce721d541aeed53e07','depot':'59228ba5c8cbb24c0b6c9e408bc2375ea0d0515194dac3ca6780c1110941c872','trains':'bbd1e8b8fb5bc47987414012c588d452b5c971228b57efd947e394c484d318ea','courses':'1a353cd60c46b2710c90dff43452919d59b678d7f27b47cc978b675d410c4367','timetable':'59445579e338532bb4ca728bdb7853e01b4e8a01f79a2d4ba831991c63891ed5','stations':'989bc90b882f494ae2232c3583ec2349ff15c0fd54efb75f87ac17dadacb1f42'}
def need(x,m):
 if not x:raise ValueError(m)
def state(r):return (r['vertex'],r['side'])
def doc(v):
 if '.terminal.'in v:return ('W' if v[0]=='H'else'S')+v[1]
 if v[0]in'HV':
  a,b=v[1:].split('.');return 'X'+(b+'.'+a if v[0]=='H'else a+'.'+b)
 return v.split('.')[0]
def add(back,obj):w.set_elements(back,pf.mutable_array(back)+[obj])
class FiniteCircuitProject(cd.Project):
 """Only itinerary repetition admitted; finite saved Path references, no recursion.
 Routes/Paths retain the old acyclic guards. Does not weaken existing tools.
 """
 def dest_view(self,dest):
  dn=self.owners[id(dest)][0];refs=pf.info(dest)['saved_references'];need(1<=len(refs)<=1000,'Bounded explicit itinerary reference list required')
  persisted=pf.mutable_array(dest.contents[0].value);need(len(persisted)==1,'Only first Path persisted')
  at=(dn,refs[0]['start_id']);chain=[];paths=[]
  for i,r in enumerate(refs):
   need(r['document']in self.roots and r['document']==at[0],'Missing/disconnected ExtInfo document')
   path=self.owned(at,'OTPath',(r['name'],r['array_id'],r['start_id']))
   if i==0:need(path is persisted[0],'First Path pointer mismatch')
   nodes,_=self.path_view(path);need(nodes[0]==at,'Disconnected Path')
   chain+=nodes if i==0 else nodes[1:];paths.append((at[0],cd.ref(path)));at=nodes[-1]
   need(len(chain)<=10000,'Expanded itinerary too large')
  self.dest_views[id(dest)]=(chain,paths);return chain,paths

def generate(sources,expected_hashes,spec):
 need(type(sources)is dict and set(sources)==set(HASHES),'Exact eight source roles required')
 need(all(type(v)is bytes and v for v in sources.values()),'Nonempty immutable bytes required')
 need(type(expected_hashes)is dict and expected_hashes=={k:cd.sha(v)for k,v in sources.items()}==HASHES,'Only exact audited terminal grid baseline supported')
 need(type(spec)is dict and set(spec)=={'execution_root','accept_new_signal_plan'},'Exact specification required')
 need(spec['accept_new_signal_plan']is True,'Explicit acceptance of NEW signal/section plan required')
 rootpath=spec['execution_root'];need(rb.root_path(rootpath,'windows')==rootpath,'Canonical Windows execution root required')
 req=json.loads(sources['request']);vs={v['key']:v for v in req['network']['vertices']};es={e['key']:e for e in req['network']['edges']}
 origins={v:doc(v)for v in vs};names=sorted(set(origins.values()));need(len(names)==25,'Exact25Doc partition')
 oldroot,_=w.load(sources['terminal_document']);oldmodels,oldids=rf.document(oldroot)
 oldends={pf.string(e.contents[18].value):e for e in oldmodels if w.kind(e)=='OTEndModel'}
 oldstate={(v,s):oldends[vs[v]['names'][s]]for v in vs for s in (0,1)}
 oldsignals={k:e.contents[11].value for k,e in oldstate.items()if e.contents[11].value is not None}
 orig_routes={r['name']:[state(e)for e in r['ends']]for r in req['routes']}
 signalstates=set(oldsignals)
 for seq in orig_routes.values():
  for a,b in zip(seq,seq[1:]):
   if origins[a[0]]!=origins[b[0]]:signalstates.add(b)
 segments={};route_segments={}
 for rn,seq in orig_routes.items():
  cuts=[i for i,x in enumerate(seq)if x in signalstates];need(cuts[0]==0 and cuts[-1]==len(seq)-1,'Signal boundary missing')
  route_segments[rn]=[]
  for a,b in zip(cuts,cuts[1:]):
   part=tuple(seq[a:b+1]);need(len(set(part))==len(part),'Simple Route segment required');need(sum(origins[x[0]]!=origins[y[0]]for x,y in zip(part,part[1:]))<=1,'Too many boundaries')
   if part not in segments:segments[part]='R:MD:'+str(len(segments)+1)
   route_segments[rn].append(part)
 topologies={dn:{'vertices':[copy.deepcopy(v)for k,v in vs.items()if origins[k]==dn],'edges':[]}for dn in names};edgeparts={};boundary={};vertexmaps={}
 for ek,e in es.items():
  a=state(e['from_end']);b=state(e['to_end']);da,db=origins[a[0]],origins[b[0]];base=copy.deepcopy(e);base.pop('from_end');base.pop('to_end')
  if da==db:
   base.update({'from':list(a),'to':list(b)});topologies[da]['edges'].append(base);edgeparts[ek]=[(da,ek,e['length_m'])]
  else:
   need(e['radius_m']==0 and e['length_m']>=2,'Only positive straight boundary splits')
   x=(vs[a[0]]['x']+vs[b[0]]['x'])/2;y=(vs[a[0]]['y']+vs[b[0]]['y'])/2;pair=[]
   for i,(dn,end)in enumerate(((da,a),(db,b))):
    key='boundary.'+ek+'.'+str(i);v=g.vertex(key,x);v['y']=y;v['names']=[key+':0',key+':1'];topologies[dn]['vertices'].append(v)
    ee=copy.deepcopy(base);ee['key']=ek+'.part'+str(i);ee['length_m']=e['length_m']//2 if i==0 else e['length_m']-e['length_m']//2
    
    ee.update({'from':list(end)if i==0 else[key,0],'to':[key,0]if i==0 else list(end)})
    topologies[dn]['edges'].append(ee);pair.append((dn,key,ee['key'],ee['length_m']))
   boundary[ek]=pair;edgeparts[ek]=[(dn,k,l)for dn,_,k,l in pair]
 movement={}
 for ek,e in es.items():
  a,b=state(e['from_end']),state(e['to_end'])
  for start,end in (((a[0],1-a[1]),b),((b[0],1-b[1]),a)):
   need((start,end)not in movement,'Ambiguous original Edge');movement[(start,end)]=ek
 docs={};ids={};roots={};versions={};models={};original_signals=[];new_signals=[]
 for dn in names:
  blob,rep=tp.generate_network(sources['terminal_document'],sources['shapes'],topologies[dn]);ids[dn]=rep['vertex_end_ids']
  for st in sorted(signalstates):
   if origins[st[0]]!=dn:continue
   eid=ids[dn][st[0]][st[1]];rr,_=w.load(blob);mm,byid=rf.document(rr);old=oldsignals.get(st)
   if old is not None:
    
    
    
    placement=make_signal_placement(byid[eid],float(old.contents[2].value),float(old.contents[3].value),angle=float(old.contents[1].value))
    blob,_=ns.build_main_signal(blob,end_id=eid,name=pf.string(old.contents[13].value),model_id=max(x.contents[0].value for x in mm)+1,placement=placement,sight_m=old.contents[9].values[1],delay_s=float(old.contents[16].value),show_symbol=bool(old.contents[9].values[2]&4),show_icon=not bool(old.contents[9].values[2]&8));original_signals.append([dn,eid,st])
   else:
    blob,_=ns.build_main_signal(blob,end_id=eid,name='MD:'+st[0]+':'+str(st[1]),model_id=max(x.contents[0].value for x in mm)+1,placement=g.signal_placement(byid[eid],vs[st[0]]['x'],vs[st[0]]['y']),sight_m=400,delay_s=0,show_symbol=False,show_icon=True);new_signals.append([dn,eid,st])
  r,v=w.load(blob);mm,byid=rf.document(r);stationmap={}
  for st,oe in oldstate.items():
   if origins[st[0]]!=dn:continue
   ne=byid[ids[dn][st[0]][st[1]]];sm=oe.contents[12].value
   if sm is not None:
    sign=pf.string(sm.contents[7].value)
    if sign not in stationmap:
     need(sm.contents[6].value is None,'Unknown Station observer');new=copy.deepcopy(sm);new.contents[0].value=max(x.contents[0].value for x in mm)+1;mm.append(new);stationmap[sign]=new
    ne.contents[12].value=stationmap[sign];ne.contents[20].value=oe.contents[20].value
   if st in oldsignals:
    old=oldsignals[st];new=ne.contents[11].value
    copy_native_alignment(old,new)
    for j in range(len(old.contents)):
     if j in (0,7,10):continue
     need(w.dump_verified(old.contents[j].value,1000)==w.dump_verified(new.contents[j].value,1000)if old.contents[j].encodings==[b'@']and old.contents[j].value is not None else old.contents[j].values==new.contents[j].values,'Original signal property mismatch '+str(j))
  need(len(stationmap)<=1,'One station per station document');w.set_elements(r.contents[2].value,mm);roots[dn]=r;versions[dn]=v;models[dn]=rf.document(r)[1]
 for ek,pair in boundary.items():
  for i,(dn,vkey,_,_)in enumerate(pair):
   tdn,tkey,_,_=pair[1-i];e=models[dn][ids[dn][vkey][1]];need(all(e.contents[j].value is None for j in(9,10,11,12)),'Nonempty Connector half')
   e.clazz=w.Class(b'OTConnModel',1,e.clazz);e.contents +=[w.TypedValue(b'@',ns.string('')),w.TypedValue(b'@',ns.string(tdn)),w.TypedValue(b'i',ids[tdn][tkey][1]),w.TypedValue(b'i',0)]
 paths={};routeproof=[]
 for part,rn in segments.items():
  dn=origins[part[0][0]];owner=models[dn][ids[dn][part[0][0]][part[0][1]]];start=owner.contents[0].value;aid=owner.contents[19].value+1
  expanded=[];source_nodes=[];remote_nodes=[];host=None
  for i,st in enumerate(part):
   sd=origins[st[0]];obj=models[sd][ids[sd][st[0]][st[1]]]
   if i and sd!=origins[part[i-1][0]]:
    ek=movement[(part[i-1],st)];pair=boundary[ek];src=next(x for x in pair if x[0]==dn);dst=next(x for x in pair if x[0]==sd)
    bnd=models[dn][ids[dn][src[1]][0]];source_nodes.append(bnd);expanded.append((dn,bnd.contents[0].value));host=models[sd][ids[sd][dst[1]][1]]
   (source_nodes if sd==dn else remote_nodes).append(obj);expanded.append((sd,obj.contents[0].value))
  r=g.route(rn,aid,start,source_nodes,len(source_nodes)if remote_nodes else -1)
  add(owner.contents[15].value.contents[0].value,r);owner.contents[19].value=aid
  if remote_nodes:add(host.contents[15].value.contents[0].value,g.route(rn,aid,start,remote_nodes,-1,True))
  aid+=1;p=ns.obj(pf.SHAPES['OTPath'][0],[('@',[ns.arr([r])]),('@',[ns.string('P:'+rn)]),('ii',[aid,start]),('@',[ns.string('')]),('@',[ns.arr([g.inf(r)])])]);add(owner.contents[17].value.contents[0].value,p);owner.contents[19].value=aid;paths[part]=(dn,p)
  routeproof.append({'name':rn,'original_states':[list(x)for x in part],'expanded_nodes':[list(x)for x in expanded]})
 oldpath={p['name']:p['routes']for p in req['paths']};destrows=[];expected={}
 for it in req['itineraries']:
  parts=[part for pn in it['paths']for rn in oldpath[pn]for part in route_segments[rn]];selected=[paths[p]for p in parts];dn=selected[0][0];first=selected[0][1];name=it['name']
  d=ns.obj(pf.SHAPES['OTDest'][0],[('@',[ns.arr([first])]),('@',[ns.string(name)]),('ii',[-1,-1]),('@',[ns.string(it['description'])]),('@',[ns.arr([g.inf(p,dn)for dn,p in selected])]),('@',[g.wrapped('OTSafetyMarginArray',[])])]);add(roots[dn].contents[5].value.contents[0].value,d)
  destrows.append(ns.obj([('OTDestInfo',1),('NSObject',0)],[('i',[17]),('@',[ns.string(name)]),('@',[ns.string(rootpath+'/OTDocuments/'+dn+'.opentrack')]),('i',[first.contents[2].values[1]]),('@',[ns.arr([g.inf(p,dn)for dn,p in selected])])]))
  states=[]
  for part in parts:states.extend(part if not states else part[1:])
  expected[name]=states
 docs={dn:w.dump_verified(r,versions[dn])for dn,r in roots.items()};docpaths={dn:rootpath+'/OTDocuments/'+dn+'.opentrack'for dn in docs};dest=w.dump_verified(g.wrapped('OTDestInfoList',destrows),1000)
 p=FiniteCircuitProject(docs,document_paths=docpaths,expected_hashes={k:cd.sha(v)for k,v in docs.items()},complete_document_set=True);p.check_dest_catalog(dest);traces={}
 reverse={(origins[v],ids[origins[v]][v][s]):(v,s)for v in vs for s in(0,1)}
 for d in p.dests:
  name=pf.string(d.contents[1].value);nodes,_=p.dest_view(d);states=[reverse[k]for k in nodes if k in reverse];need(states==expected[name],'Finite itinerary original state sequence differs')
  distance=sum(p.model(p.edge_between(a,b)).contents[9].values[1]for a,b in zip(nodes,nodes[1:]));origdist=sum(es[movement[(a,b)]]['length_m']for a,b in zip(states,states[1:]));need(distance==origdist,'Physical length changed')
  stations=[pf.string(p.model(k).contents[12].value.contents[7].value)for k in nodes if p.model(k).contents[20].value==2];oldstations=[pf.string(oldstate[st].contents[12].value.contents[7].value)for st in states if oldstate[st].contents[20].value==2];need(stations==oldstations,'Station occurrence trace changed')
  traces[name]={'distance_m':distance,'station_occurrences':stations,'original_states':[list(x)for x in states],'expanded_nodes':[list(x)for x in nodes]}
 files={'OTDocuments/'+dn+'.opentrack':b for dn,b in docs.items()};cp={r:'OTData/grid.'+r for r in rb.CATALOG_KEYS}
 for role,path in cp.items():files[path]=dest if role=='dest'else sources[role]
 run,run_report=rb.build_run(files,catalog_paths=cp,document_paths=list('OTDocuments/'+dn+'.opentrack'for dn in docs),execution_root=rootpath,path_style='windows',train_types=['instructional'],template=b'');rb.verify_run(run,files,catalog_paths=cp,document_paths=list('OTDocuments/'+dn+'.opentrack'for dn in docs),execution_root=rootpath,path_style='windows',train_types=['instructional']);files['grid.run']=run
 return files,{'operation':'rebuild_fixed_terminal_grid_multidocument','domain':'fixed_audited_terminal_grid_new_signal_plan','source_sha256':expected_hashes,'members':{k:{'sha256':cd.sha(v),'bytes':len(v)}for k,v in files.items()},'vertex_documents':origins,'original_vertex_ids':{v:{'document':origins[v],'ids':ids[origins[v]][v]}for v in vs},'edge_parts':edgeparts,'boundary_pairs':boundary,'route_segments':routeproof,'itineraries':traces,'counts':{'documents':25,'original_double_vertices':74,'original_edges':92,'rebuilt_edges':132,'connector_pairs':40,'station_documents':12,'infrastructure_documents':13,'original_signals':len(oldsignals),'added_signals':len(new_signals),'source_routes':len(segments),'itineraries':len(traces)},'original_signals_preserved':original_signals,'added_signals':new_signals,'run':run_report,'native_simulation_executed':False,'native_runtime_ready':False,'control_equivalence_proven':False,'original_physical_topology_and_metric_preserved':True,'service_catalogs_byte_preserved':{k:cd.sha(sources[k])for k in('depot','trains','courses','timetable','stations')},'scope':'Actual three-by-three grade-separated corridors and perimeter wyes, not nine station grid. Added directional signals split Routes at document boundaries; control/section/capacity semantics are NEW and unverified. Six finite two-lap itinerary station occurrences preserved; original planned service catalogs retained, not native execution proof.'}
