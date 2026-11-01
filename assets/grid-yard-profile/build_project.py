"""Generate and publish one nine-station junction grid. No native application calls."""
import copy
import json
from pathlib import Path
import grid_geometry as gg
from grid_geometry import w,pf,rf,ns,sb,g,cd,cats,sha,PORTS,SIDE,OPPOSITE,STATIONS,name
from opentrack_ai.current_archive.multi_document import operations as ops
from opentrack_ai.current_archive.zero_operations import vehicle_catalogs as vc,run_bundle as rb
from opentrack_ai.current_archive import course_factories as cf
from opentrack_ai.current_archive.zero_terminal.area_operations import arr_like,dictionary_like
from opentrack_ai.current_archive.windows_publish import publish_project
from opentrack_ai.current_archive.tools import ArchiveTools
from opentrack_ai.current_archive.prepare_contract import auxiliary as aux
from yard_profile import services


TARGET=Path('.')
CATALOGS={role:'OTData/grid.'+role for role in rb.CATALOG_KEYS}
DOC_PATHS={n:TARGET.as_posix()+'/OTDocuments/'+n+'.opentrack' for n in STATIONS}


def project(docs,dest=None):
    p=cd.Project(docs,document_paths=DOC_PATHS,expected_hashes={k:sha(v) for k,v in docs.items()},complete_document_set=True)
    if dest is not None:p.check_dest_catalog(dest)
    return p


def neighbor(dn,port):
    r,c=int(dn[1]),int(dn[2]);dr,dc={'W':(0,-1),'E':(0,1),'N':(-1,0),'S':(1,0)}[port]
    r,c=r+dr,c+dc
    return f'J{r}{c}' if 1<=r<=3 and 1<=c<=3 else None


def make_plans():
    plans=[]
    for axis in 'HV':
        for number in (1,2,3):
            for reverse in (False,True):
                incoming=('W' if not reverse else'E') if axis=='H' else('N' if not reverse else'S')
                order=([f'J{number}{i}' for i in (1,2,3)] if axis=='H' else[f'J{i}{number}' for i in (1,2,3)])
                if reverse:order.reverse()
                for lane in (1,2):
                    cid=f'{axis}{number}{OPPOSITE[incoming]}{lane}'
                    plans.append({'id':cid,'train':'T_'+cid,'itinerary':'I_'+cid,'lane':lane,
                        'documents':order,'in_ports':[incoming]*3,'out_ports':[OPPOSITE[incoming]]*3,
                        'start_s':32460+(0 if axis=='H' else 300)+(number-1)*120+int(reverse)*60+(lane-1)*30})
    for p in PORTS:
        for q in PORTS:
            if q in (p,OPPOSITE[p]):continue
            cid='TURN_'+p+q
            plans.append({'id':cid,'train':'T_'+cid,'itinerary':'I_'+cid,'lane':1,
                'documents':[neighbor('J22',p),'J22',neighbor('J22',q)],
                'in_ports':[p,p,OPPOSITE[q]],'out_ports':[OPPOSITE[p],q,q],
                'start_s':33600+len([x for x in plans if x['id'].startswith('TURN_')])*90})
    base=next(x for x in plans if x['id']=='H2E1')
    follow=copy.deepcopy(base);follow.update(id='H2E1_FOLLOW',train='T_H2E1_FOLLOW',start_s=base['start_s']+15)
    plans.append(follow)
    assert len(plans)==33 and len({p['itinerary'] for p in plans})==32
    for p in plans:
        p['visits']=[{'station':dn,'seconds':p['start_s']+i*300,'stop':i==2,'track':port+str(p['lane'])}
                     for i,(dn,port) in enumerate(zip(p['documents'],p['in_ports']))]
    return plans


def infrastructure(sources):
    roots,versions,models,proofs,rows={},{},{},{},[]
    local,cross={},{}
    for dn in STATIONS:
        blob,item,proof=gg.make_document(sources,dn)
        root,ver=w.load_next_compatible(blob);_,byid=rf.document(root)
        roots[dn],versions[dn],models[dn],proofs[dn]=root,ver,byid,proof
        rows.append((dn,item))
        ids,values=proof['ids'],proof['values']
        def add(sequence,key):
            ref=gg.local_route(root,byid,ids,values,sequence,'R_'+dn+'_'+'_'.join(map(str,key)))
            local[(dn,*key)]={'document':dn,**ref}
        for p in PORTS:
            add([name(p,'B3'),name(p,'HOME')],(p,'B3_HOME'))
            for lane in (1,2):
                for role in ('HOME_REF','REF_ENTRY'):add(proof['sequences'][(p,lane,role)],(p,lane,role))
            for q in PORTS:
                if p!=q:add(proof['sequences'][(p,q,'CORE')],(p,q,'CORE'))
            add([name(p,'O_A'),name(p,'B1')],(p,'OUT_B1'))
            add([name(p,'B1'),name(p,'B2')],(p,'B1_B2'))
        print('Prepared '+dn+' (8 platform tracks, 24 turnouts, 32 signals)',flush=True)
    connections=[]
    for dn in STATIONS:
        for p in PORTS:
            target=neighbor(dn,p)
            if target is None:continue
            q=OPPOSITE[p]
            
            sid=proofs[dn]['ids'][name(p,'OUT')][SIDE[p]]
            tid=proofs[target]['ids'][name(q,'IN')][SIDE[q]]
            for source,source_id,other,other_id in [(dn,sid,target,tid),(target,tid,dn,sid)]:
                end=models[source][source_id]
                assert all(end.contents[i].value is None for i in (9,10,11,12))
                end.clazz=w.Class(b'OTConnModel',1,end.clazz)
                end.contents +=[w.TypedValue(b'@',ns.string('')),w.TypedValue(b'@',ns.string(other)),w.TypedValue(b'i',other_id),w.TypedValue(b'i',0)]
            owner=models[dn][proofs[dn]['ids'][name(p,'B2')][1-SIDE[p]]]
            boundary=models[dn][proofs[dn]['ids'][name(p,'OUT')][1-SIDE[p]]]
            receiver=models[target][tid]
            finish=models[target][proofs[target]['ids'][name(q,'B3')][SIDE[q]]]
            label='R_LINK_'+dn+'_'+target
            aid=owner.contents[19].value+1
            primary=g.route(label,aid,owner.contents[0].value,[owner,boundary],2)
            fragment=g.route(label,aid,owner.contents[0].value,[finish],-1,True)
            assert not pf.mutable_array(owner.contents[15].value.contents[0].value)
            w.set_elements(owner.contents[15].value.contents[0].value,[primary]);owner.contents[19].value=aid
            w.set_elements(receiver.contents[15].value.contents[0].value,[fragment])
            cross[(dn,target)]={'document':dn,**cd.ref(primary)}
            connections.append({'from':dn,'port':p,'to':target,'target_port':q,'source_connector_id':sid,'target_connector_id':tid})
    assert len(connections)==24
    docs={n:w.dump_verified(roots[n],versions[n]) for n in STATIONS}
    return docs,w.dump_verified(sb.dictionary(rows),1000),proofs,local,cross,connections


def movements(docs,proofs,local,cross,plans):
    
    
    
    base_project=project(docs)
    roots,versions=base_project.roots,base_project.versions
    done=set();catalog_rows=[];expected_nodes={}
    for plan in plans:
        if plan['itinerary'] in done:continue
        selected=[]
        for i,(source,target) in enumerate(zip(plan['documents'],plan['documents'][1:])):
            p,q=plan['in_ports'][i],plan['out_ports'][i]
            port=plan['in_ports'][i+1];lane=plan['lane']
            assert neighbor(source,q)==target and port==OPPOSITE[q]
            selected += [local[(source,p,lane,'REF_ENTRY')],local[(source,p,q,'CORE')],
                local[(source,q,'OUT_B1')],local[(source,q,'B1_B2')],cross[(source,target)],
                local[(target,port,'B3_HOME')],local[(target,port,lane,'HOME_REF')]]
        actual=[];all_nodes=[];at=None
        for ref in selected:
            key=(ref['document'],ref['start_id'])
            assert at is None or key==at
            route=base_project.owned(key,'OTRoute',(ref['name'],ref['array_id'],ref['start_id']))
            nodes=base_project.route_view(route)
            actual.append(route);all_nodes+=nodes if at is None else nodes[1:];at=nodes[-1]
        assert len(all_nodes)==len(set(all_nodes))
        dn,start=all_nodes[0];owner=base_project.model((dn,start));aid=owner.contents[19].value+1
        path=ns.obj(pf.SHAPES['OTPath'][0],[('@',[ns.arr(actual[:1])]),('@',[ns.string('P_'+plan['id'])]),
            ('ii',[aid,start]),('@',[ns.string('')]),('@',[ns.arr([g.inf(r) for r in actual])])])
        backing=owner.contents[17].value.contents[0].value
        w.set_elements(backing,pf.mutable_array(backing)+[path]);owner.contents[19].value=aid
        itinerary=ns.obj(pf.SHAPES['OTDest'][0],[('@',[ns.arr([path])]),('@',[ns.string(plan['itinerary'])]),
            ('ii',[-1,-1]),('@',[ns.string('')]),('@',[ns.arr([g.inf(path,dn)])]),('@',[g.wrapped('OTSafetyMarginArray',[])])])
        target=roots[dn].contents[5].value.contents[0].value
        w.set_elements(target,pf.mutable_array(target)+[itinerary])
        catalog_rows.append(ns.obj([('OTDestInfo',1),('NSObject',0)],[('i',[17]),('@',[ns.string(plan['itinerary'])]),
            ('@',[ns.string(DOC_PATHS[dn])]),('i',[start]),('@',[ns.arr([g.inf(path,dn)])])]))
        expected_nodes[plan['itinerary']]=all_nodes;done.add(plan['itinerary'])
    docs={dn:w.dump_verified(root,versions[dn]) for dn,root in roots.items()}
    dest=w.dump_verified(g.wrapped('OTDestInfoList',catalog_rows),1000)
    fresh=project(docs,dest)
    for d in fresh.dests:
        nodes,_=fresh.dest_view(d)
        assert nodes==expected_nodes[pf.string(d.contents[1].value)]
    print('Fresh native-byte reconstruction validated all32 cross-document itineraries',flush=True)
    return docs,dest


def trace(p,itin):
    item=next(d for d in p.dests if pf.string(d.contents[1].value)==itin)
    nodes,path_refs=p.dest_view(item);refs=[];distance=0;visits=[];resources=[]
    for dn,ref in path_refs:
        path=p.owned((dn,ref['start_id']),'OTPath',(ref['name'],ref['array_id'],ref['start_id']))
        _,path_routes=p.path_view(path);refs.extend(path_routes)
    for i,key in enumerate(nodes):
        end=p.model(key)
        if i:
            edge=p.model(p.edge_between(nodes[i-1],key));distance+=edge.contents[9].values[1]
        if end.contents[20].value==2:
            sm=end.contents[12].value
            if i:
                prev=p.model(nodes[i-1]);arrival=p.model(p.edge_between(nodes[i-1],key))
                assert prev.contents[12].value is sm and arrival.contents[9].values[1]==500
            visits.append({'station':pf.string(sm.contents[7].value),'distance_m':distance,'end_key':list(key)})
    for dn,ref in refs:
        route=p.owned((dn,ref['start_id']),'OTRoute',(ref['name'],ref['array_id'],ref['start_id']))
        expanded=p.route_view(route)
        assert route.contents[6].values[0]==0 and route.contents[11].value==0
        elems=sorted({(k[0],p.model(k).contents[7].value.contents[0].value) for k in expanded[1:]})
        resources.append({'route':ref['name'],'document':dn,'element_keys':[list(k) for k in elems]})
    return {'itinerary':itin,'distance_m':distance,'visits':visits,'route_count':len(refs),'nodes':[list(k) for k in nodes],'resources':resources}


def operating(sources,docs,dest,station_catalog,plans):
    spec={'engine_template':'CR400AF_8_PROXY_350','train_template':'CR400AF_8_PROXY_350','category_template':'Category 1',
        'engine_name':'GRID_ENGINE','category_name':'GRID_CATEGORY','train_names':[p['train'] for p in plans],
        'use_template_physics':True,'inherit_conflict_definitions':True,'train_parameters':services.VEHICLE_PARAMETERS}
    vehicles,vr=vc.generate_vehicle_catalogs(sources['depot_template'],sources['trains_template'],spec)
    trains=w.load_next_compatible(vehicles['trains'])[0]
    ct,cv=w.load_next_compatible(sources['courses_template']);tt,tv=w.load_next_compatible(sources['timetable_template'])
    templates={cats.text(x.contents[0].value):x for x in cats.course_items(ct)};rows=cf.timetable(tt)
    cid0,key0='G1046','G1046#0';courses=cf.clone(ct)
    for index in (1,2,3):courses.contents[index].value=arr_like(ct.contents[index].value,[])
    courses.contents[4].value=arr_like(ct.contents[4].value,[copy.deepcopy(templates[cid0])])
    table=dictionary_like(tt,[(key0,copy.deepcopy(rows[key0]))])
    dest_root=w.load_next_compatible(dest)[0];stations=w.load_next_compatible(station_catalog)[0]
    p=project(docs,dest);traces={}
    for plan in plans:
        tr=trace(p,plan['itinerary']);traces[plan['id']]=tr
        assert tr['distance_m']==12000 and [v['distance_m'] for v in tr['visits']]==[0,6000,12000]
        assert [v['station'] for v in tr['visits']]==plan['documents'] and tr['route_count']==14
        fields={'speed_type':'Reihe R','description':'Three by three junction-grid journey',
            'comment':'Planned teaching proxy; native runtime acceptance pending','train_number':plan['id'],'course_type':'',
            'acceleration_percent':100,'delayed_acceleration_percent':100,'enabled':True,'entering_speed_kmh':0,
            'output_offset_m':0,'spacing_mode':'discrete','additional_reservation_time_s':0,'additional_release_time_s':0}
        courses=cf.new_course(courses,trains,dest_root,template_id=cid0,course_id=plan['id'],train=plan['train'],
            itineraries=[plan['itinerary']],fields=fields)
        stops=[]
        for visit in plan['visits']:
            clock=services._clock(visit['seconds'])
            stops.append(dict(template_key=key0,station_sign=visit['station'],arrival=clock,departure=clock,
                arrival_day_offset=0,departure_day_offset=0,stop_at_station=visit['stop'],timing_station=True,
                interval_reference_course_id=None,interval_offset_s=0,dwell_s=0,mean_delay_s=0,track_id=visit['track'],distribution_name='',delta_mass_t=0))
        table=cf.new_timetable(table,courses,stations,course_id=plan['id'],stops=stops)
    courses.contents[4].value=arr_like(courses.contents[4].value,[x for x in cats.course_items(courses) if cats.text(x.contents[0].value)!=cid0])
    table=dictionary_like(table,[(key,row) for key,row in cf.timetable(table).items() if key!=key0])
    files={'OTDocuments/'+n+'.opentrack':b for n,b in docs.items()}
    for role,blob in {**vehicles,'courses':w.dump_verified(courses,cv),'timetable':w.dump_verified(table,tv),
                      'stations':station_catalog,'dest':dest}.items():files[CATALOGS[role]]=blob
    run,rr=rb.build_run(files,catalog_paths=CATALOGS,document_paths=['OTDocuments/'+n+'.opentrack' for n in STATIONS],
        execution_root=TARGET.as_posix(),path_style='windows',output_directory='output',train_types=['Reihe R'],
        start_day=0,start_time='09:00:00',stop_day=0,stop_time='10:30:00',step='0.2')
    from yard_profile.composition import with_break
    files['grid.run'],br=with_break(run,'00:00:00')
    return files,traces,{'vehicle':vr,'run':rr,'break':br}

