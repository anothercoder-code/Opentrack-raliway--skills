"""Pure bytes two-document terminal infrastructure. No simulator execution.

Each station has one arrival stopping direction, not bidirectional stopping.
The opposite reference half carries a departure main signal. This explicit
saved-data extension is not covered by the older forward-only area runtime gate.
"""
from ..multi_document import core as cd
from opentrack_ai.current_archive import writer as w, catalogs as cats, path_functions as pf, route_factory as rf
from opentrack_ai.current_archive.zero_generation import topology as tp, native_signal_routes as ns
from opentrack_ai.current_archive.zero_operations import station_binding as sb, run_bundle as rb
from opentrack_ai.current_archive.zero_terminal import terminal_areas as ta
from opentrack_ai.current_archive.graphic_alignment import make_placement, make_signal_placement

def need(ok,msg):
    if not ok:raise ValueError(msg)
def vertex(key,x):return dict(key=key,x=x,y=30,orientation='horizontal',names=[key+'-left',key+'-right'],insulated_joint=[False,False],axle_counter=[False,False])
def edge(key,a,b,length):return dict(key=key,**{'from':[a,1],'to':[b,0]},length_m=length,radius_m=0.,gradient_per_mille=0.,track_type=1,loop_type=1,dlink_type=1,equal_speed=True,rack_rail=False,speeds=[dict(train_type='0',speed12_kmh=80,speed21_kmh=80)],remark='',track_name='1',line_name='A-B')
def placement(x,y):return make_placement(x,y)
def wrapped(kind,items):
    chain=[(kind,0)]+([]if kind=='OTMutableArray'else[('OTMutableArray',0)])+[('NSObject',0)]
    return ns.obj(chain,[('@',[ns.arr(items)])])
def inf(obj,doc=None):
    groups=[('@',[ns.string(cd.ident(obj)[0])]),('ii',list(cd.ident(obj)[1:]))]
    if doc is not None:groups.append(('@',[ns.string(doc)]))
    return ns.obj(([('OTArrayExtInfo',0)]if doc is not None else [])+[('OTArrayInfo',0),('NSObject',0)],groups)
def route(name,aid,start,nodes,continuation,fragment=False):
    groups=[('@',[ns.arr(nodes)]),('@',[ns.string(name)]),('ii',[aid,start]),('@',[ns.string('')]),('@',[None]),('iiiiii',[0,400,5,0,continuation,0]),('iff',[0,40.,0.]),('@',[ns.string('')]),('ff',[0.,0.]),('i',[-1]),('iii',[5000,0,0]),('i',[0]),('@@@',[ns.arr([]if fragment else[nodes[0]]),None,None])]
    r=ns.obj(pf.SHAPES['OTRoute'][0],groups);ind=ns.obj([('OTSigInd',0),('NSObject',0)],[('i',[0]),('@',[r])]);r.contents[4].value=wrapped('OTSigIndList',[]if fragment else[ind]);return r

def _empty(blob,role):
    root,v=w.load(blob)
    if role=='depot':cats.engine_items(root);w.set_elements(root,[])
    elif role=='courses':
        cats.course_items(root)
        for i in (1,2,3,4):w.set_elements(root.contents[i].value,[])
    elif role=='trains':
        cats.train_items(root)
        for i in (1,2,3):w.set_elements(root.contents[i].value,[])
    elif role=='timetable':
        need(w.kind(root)=='NSMutableDictionary','Current timetable required');root.contents=[w.TypedValue(b'i',0)]
    else:raise ValueError('Unknown catalog')
    return w.dump_verified(root,v)

def _signal(blob,eid,name):
    root,_=w.load(blob);models,byid=rf.document(root)
    return ns.build_main_signal(blob,end_id=eid,name=name,model_id=max(m.contents[0].value for m in models)+1,placement=make_signal_placement(byid[eid],100,20),sight_m=500,delay_s=0.,show_symbol=True,show_icon=True)

def generate_terminal_project(header_document,shapes,catalog_templates,*,execution_root):
    need(type(header_document)is bytes and type(shapes)is bytes,'Immutable source bytes required')
    need(set(catalog_templates)=={'depot','trains','courses','timetable'},'Four explicit catalog donors required')
    rb.root_path(execution_root,'windows');docs={};stations=[];stops={};steps={};ids={};baselines={}
    for dn in ('A','B'):
        order=['tail','reference','entry','connector']if dn=='A'else['connector','entry','reference','tail']
        spec={'vertices':[vertex(k,30+i*100)for i,k in enumerate(order)],'edges':[edge('tail','tail','reference',500),edge('area','reference','entry',500),edge('line','entry','connector',1000)]if dn=='A'else[edge('line','connector','entry',1000),edge('area','entry','reference',500),edge('tail','reference','tail',500)]}
        blob,network=tp.generate_network(header_document,shapes,spec);vs=network['vertex_end_ids'];ids[dn]=vs
        arrive=vs['reference'][1 if dn=='A'else 0];depart=vs['reference'][0 if dn=='A'else 1];entry=vs['entry'][1 if dn=='A'else 0]
        blob,sig=_signal(blob,arrive,'EXIT:'+dn)
        area={'sign':dn,'name':'Station '+dn,'reference_end_id':arrive,'ordinary_end_ids':[entry],'placement':placement(130,60),'station_type_raw':2,'interlock_type_raw':4,'icon_show_type_raw':1,'timing_point':True,'stop':{'entry_end_id':entry,'exit_end_id':arrive,'area_edge_id':network['edge_ids']['area'],'length_m':500,'exit_signal_name':'EXIT:'+dn,'direction':'forward_only'}}
        blob,station,ar,_=ta.bind_areas(blob,[area]);baselines[dn]=blob
        blob,departure_signal=_signal(blob,depart,'DEPART:'+dn)
        docs[dn]=blob;stations.append((dn,cats.station_items(w.load(station)[0])[dn]))
        stops[dn]={'document':dn,**area['stop'],'departure_end_id':depart,'reference_end_id':arrive,'ordinary_end_ids':[entry]}
        steps[dn]={'network':network,'arrival_signal':sig,'area_binding':ar,'departure_signal':departure_signal,'area_spec':area}
    roots={};versions={};byid={}
    for dn,b in docs.items():roots[dn],versions[dn]=w.load(b);_,byid[dn]=rf.document(roots[dn])
    conn={'A':ids['A']['connector'][1],'B':ids['B']['connector'][0]}
    for dn,target in [('A','B'),('B','A')]:
        e=byid[dn][conn[dn]];need(all(e.contents[i].value is None for i in (9,10,11,12)),'Connector must remain free/nonstation');e.clazz=w.Class(b'OTConnModel',1,e.clazz);e.contents +=[w.TypedValue(b'@',ns.string('')),w.TypedValue(b'@',ns.string(target)),w.TypedValue(b'i',conn[target]),w.TypedValue(b'i',0)]
    paths={dn:execution_root+'/OTDocuments/'+dn+'.opentrack'for dn in docs};destrows=[]
    for dn,target in [('A','B'),('B','A')]:
        side=0 if dn=='A'else 1
        local=[ids[dn][v][side]for v in ('reference','entry','connector')];remote=[ids[target][v][side]for v in ('entry','reference')]
        owner=byid[dn][local[0]];name='R:'+dn+'-'+target
        r=route(name,0,local[0],[byid[dn][i]for i in local],len(local));fr=route(name,0,local[0],[byid[target][i]for i in remote],-1,True)
        w.set_elements(owner.contents[15].value.contents[0].value,[r]);w.set_elements(byid[target][conn[target]].contents[15].value.contents[0].value,[fr])
        path=ns.obj(pf.SHAPES['OTPath'][0],[('@',[ns.arr([r])]),('@',[ns.string('P:'+dn+'-'+target)]),('ii',[1,local[0]]),('@',[ns.string('')]),('@',[ns.arr([inf(r)])])]);w.set_elements(owner.contents[17].value.contents[0].value,[path]);owner.contents[19].value=1
        dest=ns.obj(pf.SHAPES['OTDest'][0],[('@',[ns.arr([path])]),('@',[ns.string('I:'+dn+'-'+target)]),('ii',[-1,-1]),('@',[ns.string('')]),('@',[ns.arr([inf(path,dn)])]),('@',[wrapped('OTSafetyMarginArray',[])])]);w.set_elements(roots[dn].contents[5].value.contents[0].value,[dest])
        destrows.append(ns.obj([('OTDestInfo',1),('NSObject',0)],[('i',[17]),('@',[ns.string('I:'+dn+'-'+target)]),('@',[ns.string(paths[dn])]),('i',[local[0]]),('@',[ns.arr([inf(path,dn)])])]))
    docs={dn:w.dump_verified(r,versions[dn])for dn,r in roots.items()};dest=w.dump_verified(wrapped('OTDestInfoList',destrows),versions['A']);station_blob=w.dump_verified(sb.dictionary(stations),1000)
    files={'OTDocuments/'+dn+'.opentrack':b for dn,b in docs.items()};catalog_paths={r:'OTData/example.'+r for r in rb.CATALOG_KEYS}
    for role in rb.CATALOG_KEYS:files[catalog_paths[role]]=dest if role=='dest'else station_blob if role=='stations'else _empty(catalog_templates[role],role)
    run,run_report=rb.build_run(files,catalog_paths=catalog_paths,document_paths=list('OTDocuments/'+dn+'.opentrack'for dn in docs),execution_root=execution_root,path_style='windows',train_types=['instructional'],template=b'')
    files['cross-document.run']=run
    report=validate_terminal_project(files,document_paths=paths,stops=stops)
    report.update(steps=steps,run=run_report,source_sha256={'header':cd.sha(header_document),'shapes':cd.sha(shapes),**{k:cd.sha(v)for k,v in catalog_templates.items()}},native_simulation_executed=False,physical_circulation_proven=False,reverse_turnround_supported=False,service_catalogs_empty=True,scope='Saved-data two terminal arrival directions, opposite-half departure main signals; not native stopping or reversal acceptance')
    return files,report

def validate_terminal_project(files,*,document_paths,stops):
    docs={dn:files['OTDocuments/'+dn+'.opentrack']for dn in ('A','B')};p=cd.Project(docs,document_paths=document_paths,expected_hashes={k:cd.sha(v)for k,v in docs.items()},complete_document_set=True);p.check_dest_catalog(files['OTData/example.dest'])
    need(set(stops)=={'A','B'},'Exact two stop domains required')
    station_catalog=cats.station_items(w.load(files['OTData/example.stations'])[0])
    need(set(station_catalog)=={'A','B'},'Exact two-station catalog required')
    for sign,station in station_catalog.items():
        need(station.contents[0].value==17 and cats.text(station.contents[1].value)==sign and cats.text(station.contents[2].value)=='Station '+sign and station.contents[7].value==1,'Station catalog identity/timing mismatch')
    for dn,s in stops.items():
        need(s['document']==dn and s['length_m']==500,'Exact terminal domain required');root,v=w.load(docs[dn]);models,byid=rf.document(root)
        ref,entry,dep=[byid[s[k]]for k in ('exit_end_id','entry_end_id','departure_end_id')]
        need(ref.contents[8].value==dep.contents[0].value and dep.contents[8].value==ref.contents[0].value,'Departure must be opposite half of arrival reference')
        need(ref.contents[20].value==dep.contents[20].value==2 and ref.contents[12].value is dep.contents[12].value,'StationVertex pair must share station')
        need(entry.contents[20].value==byid[entry.contents[8].value].contents[20].value==1,'Area entry is ordinary type1')
        need(all(byid[eid].contents[12].value is ref.contents[12].value for eid in (s['entry_end_id'],entry.contents[8].value)),'Ordinary area must share station')
        
        
        
        departure_signal=dep.contents[11].value
        need(departure_signal is not None and departure_signal.contents[7].value is dep and departure_signal.contents[8].values==[1,4,2] and departure_signal.contents[9].values[0]==2 and cats.text(departure_signal.contents[13].value)=='DEPART:'+dn,'Explicit directional departure main signal absent')
        dep.contents[11].value=None;w.set_elements(root.contents[2].value,[m for m in models if m is not departure_signal])
        for e in [m for m in models if w.kind(m)in ('OTEndModel','OTConnModel')]:
            if w.kind(e)=='OTConnModel':e.clazz=e.clazz.superclass;e.contents=e.contents[:24]
            for slot in (15,17):w.set_elements(e.contents[slot].value.contents[0].value,[])
            e.contents[19].value=-1
        w.set_elements(root.contents[5].value.contents[0].value,[])
        area={'sign':dn,'name':'Station '+dn,'reference_end_id':s['exit_end_id'],'ordinary_end_ids':[s['entry_end_id']],'placement':placement(130,60),'station_type_raw':2,'interlock_type_raw':4,'icon_show_type_raw':1,'timing_point':True,'stop':{k:s[k]for k in ('entry_end_id','exit_end_id','area_edge_id','length_m','exit_signal_name','direction')}}
        ta.read_document(w.dump_verified(root,v),[area])
    itineraries={}
    for d in p.dests:
        name=pf.string(d.contents[1].value);nodes,_=p.dest_view(d);trace=[];distance=0;edge_trace=[]
        for ix,key in enumerate(nodes):
            e=p.model(key)
            if ix:
                ek=p.edge_between(nodes[ix-1],key);edge_obj=p.model(ek);distance+=edge_obj.contents[9].values[1];edge_trace.append({'document':ek[0],'edge_id':ek[1],'length_m':edge_obj.contents[9].values[1]})
            if e.contents[20].value==2:
                need(e.contents[12].value is not None,'Station reference must bind station');trace.append({'station_sign':cats.text(e.contents[12].value.contents[7].value),'document':key[0],'end_id':key[1],'distance_m':distance})
        need(len(trace)==2 and trace[0]['station_sign']!=trace[1]['station_sign'],'Exactly two reference occurrences required')
        final=stops[trace[-1]['station_sign']];need(nodes[-1]==(final['document'],final['exit_end_id'])and nodes[-2]==(final['document'],final['entry_end_id']),'Final approach does not match stopping domain')
        need(nodes[0]==(trace[0]['document'],stops[trace[0]['station_sign']]['departure_end_id']),'Wrong departure half')
        need(distance==3000,'Expected actual 3000m directional route')
        itineraries[name]={'station_signs':[t['station_sign']for t in trace],'start':list(nodes[0]),'end':list(nodes[-1]),'nodes':[list(x)for x in nodes],'trace':trace,'edges':edge_trace,'distance_m':distance}
    need(set(itineraries)=={'I:A-B','I:B-A'},'Exact bidirectional itineraries required')
    return {'document_paths':document_paths,'stops':stops,'itineraries':itineraries,'reconstruction':p.report(),'members':{k:{'sha256':cd.sha(v),'bytes':len(v)}for k,v in files.items()},'one_station_per_document':True,'arrival_stop_directions':2,'opposite_half_departure_signals':2,'old_forward_only_area_projection_checked':True,'native_simulation_executed':False}
