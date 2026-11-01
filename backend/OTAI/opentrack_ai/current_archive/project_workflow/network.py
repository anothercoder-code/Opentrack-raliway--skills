"""Bounded declaration-to-native multi-document *chain*, pure bytes only.

One point station per document. This is not a 3x3 grid, stopping-area model,
traffic plan, native simulator, or publication operation.
"""
import re
from opentrack_ai.current_archive.multi_document import core as cd, generate as g, operations as ops
from opentrack_ai.current_archive import writer as w, catalogs as cats, path_functions as pf, route_factory as rf
from opentrack_ai.current_archive.zero_generation import topology as tp, native_signal_routes as ns
from opentrack_ai.current_archive.zero_operations import station_binding as sb, run_bundle as rb


def need(ok, message):
    if not ok: raise ValueError(message)


def _spec(s):
    need(type(s) is dict and set(s)=={'topology','stations','half_link_length_m','execution_root'},'Exact chain spec required')
    need(s['topology']=='chain','Only a linear chain is supported; grids, cycles and branch junctions are not implemented')
    need(type(s['stations']) is list and 2<=len(s['stations'])<=12,'2..12 ordered stations required')
    seen=set()
    for row in s['stations']:
        need(type(row) is dict and set(row)=={'id','name'},'Exact station id/name required')
        k=row['id'];need(type(k)is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,23}',k) is not None,'Safe station/document id required')
        need(k.casefold() not in seen,'Unique case-insensitive station ids required');seen.add(k.casefold())
        need(type(row['name'])is str and 1<=len(row['name'])<=100 and all(32<=ord(c)<127 for c in row['name']) and '#' not in row['name'],'Nonempty printable ASCII station name required')
    need(type(s['half_link_length_m'])is int and 1<=s['half_link_length_m']<=100000,'Integer 1..100000 metre half link required')
    need(rb.root_path(s['execution_root'],'windows')==s['execution_root'],'Canonical forward-slash Windows root required')


def _topology(length):
    vs=[g.vertex(k,30+i*100)for i,k in enumerate(('left','reference','right'))]
    es=[]
    for name,a,b in [('left','left','reference'),('right','reference','right')]:
        es.append(dict(key=name,**{'from':[a,1],'to':[b,0]},length_m=length,radius_m=0.,gradient_per_mille=0.,track_type=1,loop_type=1,dlink_type=1,equal_speed=True,rack_rail=False,speeds=[dict(train_type='0',speed12_kmh=80,speed21_kmh=80)],remark='',track_name='1',line_name='chain'))
    return {'vertices':vs,'edges':es}


def generate_network_project(sources, *, expected_hashes, spec):
    """Six immutable shape donors -> N+7 native project members and receipt.

    sources: header, shapes, depot, trains, courses, timetable.
    The four service catalogs are intentionally empty in the new network.
    A station id is the native document basename and station sign.
    """
    need(type(sources)is dict and set(sources)=={'header','shapes','depot','trains','courses','timetable'},'Exact six shape donor sources required')
    need(all(type(b)is bytes and b for b in sources.values()),'Nonempty immutable bytes required')
    need(type(expected_hashes)is dict and expected_hashes=={k:cd.sha(v)for k,v in sources.items()},'Exact source SHA256 binding required')
    _spec(spec)
    names=[r['id']for r in spec['stations']];root_path=spec['execution_root'];length=spec['half_link_length_m']
    docs={};roots={};versions={};ids={};models={};station_rows=[];base_reports={}
    paths={dn:root_path+'/OTDocuments/'+dn+'.opentrack'for dn in names}
    for row in spec['stations']:
        dn=row['id'];blob,base=tp.generate_network(sources['header'],sources['shapes'],_topology(length));ids[dn]=base['vertex_end_ids'];base_reports[dn]=base
        for eid in ids[dn]['reference']:
            rr,_=w.load(blob);mm,byid=rf.document(rr)
            blob,_=ns.build_main_signal(blob,end_id=eid,name='S:'+dn+':'+str(eid),model_id=max(m.contents[0].value for m in mm)+1,placement=g.signal_placement(byid[eid],130,20),sight_m=500,delay_s=0.,show_symbol=True,show_icon=True)
        blob,station,_=sb.bind_stations(blob,[dict(sign=dn,name=row['name'],end_ids=[ids[dn]['reference'][0]],placement=g.placement(130,50),station_type_raw=2,interlock_type_raw=4,icon_show_type_raw=1,timing_point=True)])
        station_rows.append((dn,cats.station_items(w.load(station)[0])[dn]));roots[dn],versions[dn]=w.load(blob);_,models[dn]=rf.document(roots[dn])
    for ix,dn in enumerate(names):
        for neighbor,vertex,side,target_vertex,target_side in [(ix-1,'left',0,'right',1),(ix+1,'right',1,'left',0)]:
            if not 0<=neighbor<len(names):continue
            target=names[neighbor];e=models[dn][ids[dn][vertex][side]]
            need(w.kind(e)=='OTEndModel' and all(e.contents[i].value is None for i in (9,10,11,12)),'Connector must be an unused, nonstation outward half')
            e.clazz=w.Class(b'OTConnModel',1,e.clazz);e.contents +=[w.TypedValue(b'@',ns.string('')),w.TypedValue(b'@',ns.string(target)),w.TypedValue(b'i',ids[target][target_vertex][target_side]),w.TypedValue(b'i',0)]
    dest_rows=[];route_refs={};path_refs={}
    for ix in range(len(names)-1):
        for source,target,side,boundary,remote_boundary in [(names[ix],names[ix+1],0,'right','left'),(names[ix+1],names[ix],1,'left','right')]:
            start=ids[source]['reference'][side];owner=models[source][start];local_end=ids[source][boundary][side];remote_end=ids[target]['reference'][side];host=ids[target][remote_boundary][side]
            r=g.route('R:'+source+'-'+target,0,start,[owner,models[source][local_end]],2)
            fragment=g.route('R:'+source+'-'+target,0,start,[models[target][remote_end]],-1,True)
            need(not pf.mutable_array(owner.contents[15].value.contents[0].value),'Duplicate source route owner')
            w.set_elements(owner.contents[15].value.contents[0].value,[r]);w.set_elements(models[target][host].contents[15].value.contents[0].value,[fragment])
            p=ns.obj(pf.SHAPES['OTPath'][0],[('@',[ns.arr([r])]),('@',[ns.string('P:'+source+'-'+target)]),('ii',[1,start]),('@',[ns.string('')]),('@',[ns.arr([g.inf(r)])])])
            w.set_elements(owner.contents[17].value.contents[0].value,[p]);owner.contents[19].value=1
            d=ns.obj(pf.SHAPES['OTDest'][0],[('@',[ns.arr([p])]),('@',[ns.string('I:'+source+'-'+target)]),('ii',[-1,-1]),('@',[ns.string('')]),('@',[ns.arr([g.inf(p,source)])]),('@',[g.wrapped('OTSafetyMarginArray',[])])])
            back=roots[source].contents[5].value.contents[0].value;w.set_elements(back,pf.mutable_array(back)+[d])
            dest_rows.append(ns.obj([('OTDestInfo',1),('NSObject',0)],[('i',[17]),('@',[ns.string('I:'+source+'-'+target)]),('@',[ns.string(paths[source])]),('i',[start]),('@',[ns.arr([g.inf(p,source)])])]))
            route_refs[(source,target)]={'document':source,**cd.ref(r)};path_refs[(source,target)]={'document':source,**cd.ref(p)}
    docs={dn:w.dump_verified(roots[dn],versions[dn])for dn in names};dest=w.dump_verified(g.wrapped('OTDestInfoList',dest_rows),versions[names[0]])
    
    
    for order,label in [(names,'forward'),(list(reversed(names)),'reverse')]:
        route_seq=[route_refs[(a,b)]for a,b in zip(order,order[1:])]
        docs,pr=ops.create_path(docs,dest,document_paths=paths,expected_hashes={**{k:cd.sha(v)for k,v in docs.items()},'$dest_catalog':cd.sha(dest)},complete_document_set=True,name='P:chain:'+label,routes=route_seq)
        payload,ir=ops.create_itinerary(docs,dest,document_paths=paths,expected_hashes={**{k:cd.sha(v)for k,v in docs.items()},'$dest_catalog':cd.sha(dest)},complete_document_set=True,name='I:chain:'+label,paths=[pr['created']])
        docs=payload['documents'];dest=payload['catalog']
    project=cd.Project(docs,document_paths=paths,expected_hashes={k:cd.sha(v)for k,v in docs.items()},complete_document_set=True);project.check_dest_catalog(dest)
    traces={}
    for d in project.dests:
        name=pf.string(d.contents[1].value);nodes,_=project.dest_view(d);dist=0;station_trace=[]
        for i,key in enumerate(nodes):
            if i: dist+=project.model(project.edge_between(nodes[i-1],key)).contents[9].values[1]
            e=project.model(key)
            if e.contents[20].value==2:station_trace.append(cats.text(e.contents[12].value.contents[7].value))
        traces[name]={'station_order':station_trace,'distance_m':dist,'nodes':[list(k)for k in nodes]}
    need(traces['I:chain:forward']['station_order']==names and traces['I:chain:reverse']['station_order']==list(reversed(names)),'Full-chain station order differs')
    need(all(traces['I:chain:'+x]['distance_m']==2*length*(len(names)-1)for x in ('forward','reverse')),'Full-chain physical Edge distance differs')
    files={'OTDocuments/'+k+'.opentrack':v for k,v in docs.items()};catalog_paths={r:'OTData/chain.'+r for r in rb.CATALOG_KEYS}
    for role,path in catalog_paths.items():files[path]=dest if role=='dest'else w.dump_verified(sb.dictionary(station_rows),1000)if role=='stations'else g.empty_catalog(sources[role],role)
    doc_members=['OTDocuments/'+dn+'.opentrack'for dn in names]
    run,run_receipt=rb.build_run(files,catalog_paths=catalog_paths,document_paths=doc_members,execution_root=root_path,path_style='windows',train_types=['instructional'],template=b'')
    rb.verify_run(run,files,catalog_paths=catalog_paths,document_paths=doc_members,execution_root=root_path,path_style='windows',train_types=['instructional']);files['chain.run']=run
    return files,{'operation':'generate_linear_multidocument_network','topology':'chain','domain':'line_chain_not_grid','station_count':len(names),'one_station_per_document':True,'sources_sha256':dict(expected_hashes),'members':{k:{'sha256':cd.sha(v),'bytes':len(v)}for k,v in files.items()},'document_paths':paths,'itineraries':traces,'reconstruction':project.report(),'run':run_receipt,'service_catalogs_empty':True,'station_stopping_regions_supported':False,'grid_supported':False,'junctions_supported':False,'native_runtime_ready':False,'native_simulation_executed':False,'scope':'2..12 point-station linear chain, saved-schema synthesis and complete no-service run references only'}


def generate_network(header_document, shapes, templates, spec):
    """Convenience composition API; caller binds external source project hashes.

    templates must be the explicit four catalog byte donors. The lower-level
    generate_network_project API additionally accepts an exact SHA map.
    """
    need(type(templates)is dict and set(templates)=={'depot','trains','courses','timetable'},'Exact four catalog donors required')
    sources={'header':header_document,'shapes':shapes,**templates}
    need(all(type(v)is bytes and v for v in sources.values()),'Immutable nonempty bytes required')
    return generate_network_project(sources,expected_hashes={k:cd.sha(v)for k,v in sources.items()},spec=spec)
