"""Create a separate synthetic line from the audited three-station archive.

This uses existing native graphics and Route/Path schemas. It is intentionally
not an arbitrary graph editor and never overwrites an existing project.
"""
import copy
import csv
import io
import json
from pathlib import Path
import re
import uuid

from .archive import APIError,KINDS,Project,clock,digest,inside,w
from .drafts import set_text,text
from .planning import arrange,check_plan,profiles_for,summary
from opentrack_course_schema import course_array
from opentrack_train_schema import bound_engine_names,engine_items,train_items


OLD_SIGNS=['BJN','JNW','NJN']
OLD_DOCS=['BJTU1','BJTU2','BJTU3']
OLD_NAMES=['Beijing South','Jinan West','Nanjing South']


def rename_identifiers(project,stations):
    
    
    signs=dict(zip(OLD_SIGNS,[s.sign for s in stations]));docs=dict(zip(OLD_DOCS,[s.document for s in stations]))
    names=dict(zip(OLD_NAMES,[s.native_name for s in stations]));seen=set()
    for root in [*project.data.values(),*project.docs.values(),*project.corridors.values()]:
        for obj in w.objects(root):
            if w.kind(obj)!='NSString' or id(obj) in seen:continue
            seen.add(id(obj));value=w.string(obj)
            value=re.sub('|'.join(map(re.escape,OLD_NAMES)),lambda m:names[m[0]],value)
            value=re.sub(r'(?<![A-Za-z0-9])(BJN|JNW|NJN)(?![A-Za-z0-9])',lambda m:signs[m[0]],value)
            value=re.sub(r'BJTU[123]',lambda m:docs[m[0]],value)
            obj.contents[0].values[0]=value.encode('ascii')
    return signs,docs


def rename_label(label,name):
    data=label.contents[7].value
    if w.kind(data)!='NSMutableData' or len(data.contents)!=2:raise APIError('LABEL_SCHEMA','Unsupported native RTF label data.')
    old=bytes(data.contents[1].value.elements)
    pattern=rb'(\x08\x08)([^{}]*)(}\r?\n)$'
    if not re.search(pattern,old):raise APIError('LABEL_SCHEMA','The audited RTF visible-text marker is absent.')
    blob=re.sub(pattern,lambda m:m[1]+name.encode('ascii')+m[3],old)
    data.contents=[w.ar.TypedValue(b'i',len(blob)),w.ar.TypedValue(('['+str(len(blob))+'c]').encode('ascii'),w.ar.Array(blob))]
    
    label.contents[8].values=list(label.contents[8].values);label.contents[8].values[2]=240.0


class DemoBuilder:
    def __init__(self,service):self.service=service

    def create(self,args):
        from .legacy_geometry_guard import reject
        reject()  
        s=self.service;s.check_build()
        for attribute in ['sign','document','native_name']:
            values=[getattr(station,attribute) for station in args.stations]
            if len(set(values))!=3:raise APIError('DEMO_STATIONS','Three distinct '+attribute+' values are required.')
        if args.station_speed_kmh>args.maximum_speed_kmh:raise APIError('DEMO_SPEED','Station speed exceeds maximum speed.')
        if re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]',args.project_name,re.I):raise APIError('PROJECT_NAME','Reserved Windows directory name.')
        target=inside(s.root/'OTProjects'/args.project_name,[s.root/'OTProjects'])
        if target.exists():raise APIError('PROJECT_EXISTS','An existing project is never overwritten. Choose a new project_name.',str(target))
        p=s.project(args);source_digest=p.source_digest;source_files=p.source_hashes
        station_rows=p.catalog('stations')
        if list(p.docs)!=OLD_DOCS or len(station_rows)!=3 or {row['sign'] for row in station_rows}!=set(OLD_SIGNS):
            raise APIError('DEMO_TEMPLATE','Use the audited three-station BJTU template in document order BJTU1/BJTU2/BJTU3.')
        initial_validation=s.validate_project(p)
        if not initial_validation['valid']:raise APIError('INVALID_TEMPLATE','Repair the source template before generating a new line.',initial_validation['errors'])
        doc_versions={args.stations[i].document:p.versions[str(p.doc_paths[name])] for i,name in enumerate(OLD_DOCS)}
        native_versions={kind:p.versions[str(path)] for kind,path in p.data_paths.items()}
        _,models,paths=p.graph();edges={(name,o.contents[0].value):o for name,items in models.items() for o in items if w.kind(o)=='OTEdgeModel'}
        rail_identity={name:{(w.kind(o),o.contents[0].value,tuple(o.contents[i].value for i in [2,3])) for o in items if w.kind(o)!='OTLabelModel'} for name,items in models.items()}
        changed=[];mainline=set()
        for first,second,distance in [(OLD_SIGNS[0],OLD_SIGNS[1],args.section_distances_m[0]),(OLD_SIGNS[1],OLD_SIGNS[2],args.section_distances_m[1])]:
            for a,b in [(first,second),(second,first)]:
                route=paths[f'P:{a}-{b}_1'];records=[e for r in route['routes'] for e in r['edges']]
                candidate=max(records,key=lambda e:e['end_m']-e['start_m']);key=(candidate['owner'],candidate['edge_id'])
                if key in mainline:raise APIError('DEMO_TEMPLATE','Sections unexpectedly share their principal Edge.')
                edge=edges[key];old=edge.contents[9].values[1];new=old+distance-route['distance_m']
                if new<10000:raise APIError('DEMO_DISTANCE','Requested section is too short for the preserved station geometry.')
                edge.contents[9].values=list(edge.contents[9].values);edge.contents[9].values[1]=new;mainline.add(key)
                changed.append({'document':key[0],'edge_id':key[1],'before_m':old,'after_m':new})
        for key,edge in edges.items():
            speed=args.maximum_speed_kmh if key in mainline else args.station_speed_kmh
            
            edge.contents[16].values[0]=copy.deepcopy(edge.contents[16].value)
            for item in w.objects(edge.contents[16].value):
                if w.kind(item)=='OTSpeed':
                    if item.contents[1].encodings!=[b'i'] or item.contents[2].encodings!=[b'i']:raise APIError('SPEED_SCHEMA','Expected audited integer OTSpeed fields.')
                    item.contents[1].values[0]=item.contents[2].values[0]=speed
        train_name='DEMO_EMU_'+str(args.maximum_speed_kmh)
        if train_name in {r['name'] for r in p.catalog('trains')}|{r['name'] for r in p.catalog('engines')}:
            raise APIError('DEMO_VEHICLE_EXISTS','The demo vehicle name already exists in the source.')
        original_train=next((t for t in train_items(p.data['trains']) if w.string(t.contents[0].value)==args.source_train),None)
        if original_train is None:raise APIError('DEMO_TEMPLATE','Selected source vehicle is missing.')
        refs=bound_engine_names(original_train)
        if len(refs)!=1 or w.elements(original_train.contents[2].values[2]):raise APIError('DEMO_TEMPLATE','Expected a single powered unit without trailers.')
        original_engine=next(e for e in engine_items(p.data['depot']) if w.string(e.contents[1].value)==refs[0])
        engine=copy.deepcopy(original_engine);train=copy.deepcopy(original_train)
        set_text(engine,1,train_name);engine.contents[6].values[0]=args.maximum_force_kn;engine.contents[7].values[0]=args.maximum_speed_kmh
        diagram,=w.elements(engine.contents[16].value);diagram.contents[0].values=list(diagram.contents[0].values);diagram.contents[0].values[0]=args.maximum_speed_kmh
        point=w.elements(diagram.contents[1].value)[0];points=[]
        for v in sorted({0,args.maximum_speed_kmh,*range(0,args.maximum_speed_kmh+1,50)}):
            item=copy.deepcopy(point);item.contents[0].values=[v,min(args.maximum_force_kn,round(args.nominal_power_kw*3.6/max(v,1))),1];points.append(item)
        w.set_elements(diagram.contents[1].value,points)
        set_text(diagram,6,f'SYNTHETIC {args.nominal_power_kw}kW / {args.maximum_force_kn}kN / {args.maximum_speed_kmh}kmh; not manufacturer data')
        set_text(train,0,train_name)
        reference,=w.elements(train.contents[2].values[1]);set_text(reference,0,train_name)
        brakes=train.contents[2].values[0].contents[0].value;sample=w.elements(brakes)[0];items=[]
        for v in sorted({0,min(200,args.maximum_speed_kmh),args.maximum_speed_kmh}):
            item=copy.deepcopy(sample);value=-.7 if v==args.maximum_speed_kmh else -.8;item.contents[0].values=[v,value,value];items.append(item)
        w.set_elements(brakes,items)
        w.set_elements(p.data['depot'],engine_items(p.data['depot'])+[engine])
        w.set_elements(p.data['trains'].contents[3].value,train_items(p.data['trains'])+[train])
        signs,docnames=rename_identifiers(p,args.stations)
        for old,station in zip(OLD_DOCS,args.stations):
            label,=[o for o in p.models[old] if w.kind(o)=='OTLabelModel'];rename_label(label,station.native_name)
        p.docs={docnames[name]:doc for name,doc in p.docs.items()};p.models={docnames[name]:items for name,items in p.models.items()};p._graph=None
        for old,identity in rail_identity.items():
            after={(w.kind(o),o.contents[0].value,tuple(o.contents[i].value for i in [2,3])) for o in p.models[docnames[old]] if w.kind(o)!='OTLabelModel'}
            if after!=identity:raise APIError('GRAPH_IDENTITY','Rail graphics or coordinates changed unexpectedly.')
        p.scenario={'model_type':'three_station_synthetic_demo','mode':'demo','station_signs':[x.sign for x in args.stations],
            'stations':[x.model_dump() for x in args.stations],'section_distances_m':args.section_distances_m,
            'station_reference_mileage_m':[0,args.section_distances_m[0],sum(args.section_distances_m)],
            'maximum_speed_kmh':args.maximum_speed_kmh,'station_speed_kmh':args.station_speed_kmh,
            'demo_train':train_name,'nominal_power_kw':args.nominal_power_kw,'maximum_force_kn':args.maximum_force_kn,
            'dwell_s':args.dwell_s,'departures_each_direction':args.departures_each_direction,'departure_interval_s':args.departure_interval_s,
            'simulation_step_s':.1,'source_project':str(p.project),'source_digest':source_digest,
            'mileage_basis':'Synthetic demonstration distances; not surveyed chainage or a real timetable',
            'traction_model':'Uncalibrated powered-unit engineering proxy; not a production CR400 specification',
            'native_simulation_verified':False}
        profiles=profiles_for(p);schedule=arrange(profiles,args)
        self.write_courses(p,schedule,args,train_name)
        start=min(c['departure_s'] for c in schedule);stop=max(c['arrival_s'] for c in schedule)+1800
        p.scenario.update(begin_s=start,end_s=stop)
        old_corridors=list(p.corridors.items());p.corridors={};corridor_versions={}
        for oldname,corridor in old_corridors:
            members=w.elements(corridor.contents[15].value);corridor_signs=[w.string(o.contents[0].value) for o in members]
            name='DEMO-'+'-'.join(corridor_signs);filename=name+'.otsimcor'
            mileage=0
            for i,station in enumerate(members):
                previous=0
                if i:
                    a=p.scenario['station_signs'].index(corridor_signs[i-1]);b=p.scenario['station_signs'].index(corridor_signs[i]);previous=sum(args.section_distances_m[min(a,b):max(a,b)]);mileage+=previous
                station.contents[1].values=list(station.contents[1].values);station.contents[1].values[:3]=[i,mileage,previous]
            corridor.contents[7].values=[float(start),float(stop)];set_text(corridor,3,name)
            set_text(corridor,16,'Synthetic timetable; native simulation pending');set_text(corridor,18,name+' '+str(args.maximum_speed_kmh)+'kmh')
            for index in [19,20,25]:w.set_elements(corridor.contents[index].value,[])
            for group in corridor.contents[0].value.contents:group.value.contents=[w.ar.TypedValue(b'i',0)]
            topo=corridor.contents[1].value;w.set_elements(topo.contents[0].value,[])
            for i in [1,2]:topo.contents[i].value.contents=[w.ar.TypedValue(b'i',0)]
            p.corridors[filename]=corridor
            corridor_versions[filename]=next(version for path,version in p.versions.items() if Path(path).name==oldname)
        parent=s.work/('create-'+uuid.uuid4().hex[:16]);staging=parent/'project';(staging/'OTDocuments').mkdir(parents=True)
        bundle_name='ready-'+uuid.uuid4().hex[:12];bundle=staging/'OTData'/bundle_name;bundle.mkdir(parents=True);(staging/'output').mkdir()
        run_name=args.project_name+'.run'
        from .operations import rebase_itinerary_documents
        rebase_itinerary_documents(p,staging)
        for kind,obj in p.data.items():
            blob=w.dump_verified(obj,native_versions[kind]);(bundle/('DEMO.'+kind)).write_bytes(blob);(staging/'OTData'/('empty.'+kind)).write_bytes(blob)
        for name,doc in p.docs.items():(staging/'OTDocuments'/(name+'.opentrack')).write_bytes(w.dump_verified(doc,doc_versions[name]))
        for name,doc in p.corridors.items():
            set_text(doc,2,str(staging/'OTDocuments'/name));(staging/'OTDocuments'/name).write_bytes(w.dump_verified(doc,corridor_versions[name]))
        params=copy.deepcopy(p.parameters)
        params.update({key:[str(bundle/('DEMO.'+kind)).replace('\\','/')] for key,kind in KINDS.items()})
        params.update({'Infrastructure Document':[str(staging/'OTDocuments'/(name+'.opentrack')).replace('\\','/') for name in p.docs],
            'Document Set Document':[str(staging/'OTDocuments'/(name+'.opentrack')).replace('\\','/') for name in p.docs],
            'Document Set Name':[args.project_name],
            'Train Diagram Document':[str(staging/'OTDocuments'/name).replace('\\','/') for name in p.corridors],
            'OutputPath':[str(staging/'output').replace('\\','/')],'Start Time':[clock(start)],'Stop Time':[clock(stop)],'Step':['0.1'],
            'Time Ratio':['30:1'],'Keep Occupations':['0'],'Show Train':['1'],'Show Train ID':['1'],'Multithreaded':['0']})
        run_blob=('// Synthetic demonstration; native run pending.\r\n'+'\r\n'.join(k+'#'+v+'#' for k,values in params.items() for v in values)+'\r\n').encode('ascii')
        (staging/run_name).write_bytes(run_blob)
        (staging/'opentrack-project.json').write_text(json.dumps({'default_run':run_name,'model_type':p.scenario['model_type']},indent=2),encoding='utf8')
        (staging/'demo-scenario.json').write_text(json.dumps(p.scenario,ensure_ascii=False,indent=2),encoding='utf8')
        checked=Project(s.root,str(staging));validation=s.validate_project(checked);plan=check_plan(checked)
        if not validation['valid'] or not plan['valid']:raise APIError('DEMO_VALIDATION','Generated staging project failed validation; source untouched.',{'staging':str(staging),'archive':validation,'plan':plan})
        if not all(Path(path).is_file() and digest(Path(path).read_bytes())==sha for path,sha in source_files.items()):raise APIError('SOURCE_CHANGED','Source changed during creation; generated project was not published.')
        
        
        final_run=run_blob.replace(str(staging).replace('\\','/').encode('ascii'),str(target).replace('\\','/').encode('ascii'))
        (staging/run_name).write_bytes(final_run)
        rebase_itinerary_documents(p,target)
        destination_blob=w.dump_verified(p.data['dest'],native_versions['dest'])
        (bundle/'DEMO.dest').write_bytes(destination_blob);(staging/'OTData/empty.dest').write_bytes(destination_blob)
        for name,doc in p.corridors.items():
            set_text(doc,2,str(target/'OTDocuments'/name));(staging/'OTDocuments'/name).write_bytes(w.dump_verified(doc,corridor_versions[name]))
        (staging/'timetable.csv').write_bytes(self.timetable_csv(schedule,args))
        for direction,profile in profiles.items():
            data=io.StringIO(newline='');writer=csv.DictWriter(data,fieldnames=['distance_m','planning_time_s','kinematic_speed_kmh']);writer.writeheader();writer.writerows(profile['samples'])
            (staging/('speed-profile-'+direction+'.csv')).write_bytes(data.getvalue().encode('utf-8-sig'))
        self.write_instructions(staging,target,run_name,schedule,args,plan)
        staging.rename(target);parent.rmdir()
        final=Project(s.root,str(target));validation=s.validate_project(final);plan=check_plan(final)
        report={'project':str(target),'run_file':str(target/run_name),'source_project':str(p.project),'source_digest':source_digest,
            'source_files_unchanged':all(Path(path).is_file() and digest(Path(path).read_bytes())==sha for path,sha in source_files.items()),
            'configuration':p.scenario,'schedule':schedule,'length_changes':changed,'rail_graphics_and_coordinates_preserved':True,
            'archive_validation':validation,'operating_plan':plan,'native_simulation_verified':False}
        (target/'demo-plan.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        if not validation['valid'] or not plan['valid']:raise APIError('DEMO_POST_PUBLICATION','Inspect the new project report; source remains untouched.',str(target/'demo-plan.json'))
        return {'project':str(target),'run_file':str(target/run_name),'instructions':str(target/'使用说明.md'),'report':str(target/'demo-plan.json'),
            'source_files_unchanged':report['source_files_unchanged'],'source_digest':source_digest,'source_digest_new_project':final.source_digest,
            'stations':[x.model_dump() for x in args.stations],'distance_m':sum(args.section_distances_m),'maximum_speed_kmh':args.maximum_speed_kmh,
            'course_count':len(schedule),'simulation_start':clock(start),'simulation_stop':clock(stop),'step_s':.1,
            'validation':validation,'operating_plan':plan,'native_simulation_verified':False}

    def write_courses(self,p,schedule,args,train_name):
        sample=copy.deepcopy(p.courses()[0]);row_sample=copy.deepcopy(next(iter(p.table().values())));courses=[];table=[]
        for record in schedule:
            cid=record['course_id'];course=copy.deepcopy(sample);set_text(course,0,cid);set_text(course,3,train_name)
            stations=args.stations if record['direction']=='down' else list(reversed(args.stations))
            itinerary=f'I:{stations[0].sign}-{stations[-1].sign}_1'
            w.set_elements(course.contents[2].value,[text(course,itinerary)]);course.contents[5].values[0]=1
            set_text(course,10,f'SYNTHETIC {stations[0].native_name} - {stations[-1].native_name}')
            set_text(course,11,f'Demo {args.maximum_speed_kmh}kmh; padded synthetic timetable; native run pending');set_text(course,13,'G')
            courses.append(course)
            for i,station in enumerate(stations):
                row=copy.deepcopy(row_sample);set_text(row,1,cid);set_text(row,2,'-1');row.contents[3].values[0]=i;row.contents[4].values[0]=2;set_text(row,5,station.sign)
                arrival=None if i==0 else record['middle_arrival_s'] if i==1 else record['arrival_s']
                departure=record['departure_s'] if i==0 else record['middle_departure_s'] if i==1 else None
                set_text(row,6,clock(arrival) if arrival is not None else 'HH:MM:SS');set_text(row,7,clock(departure) if departure is not None else 'HH:MM:SS')
                set_text(row,8,str(args.dwell_s if i==1 else 0));w.set_elements(row.contents[9].value,[])
                for index in [13,14]:set_text(row,index,'HH:MM:SS')
                table.extend([w.ar.TypedValue(b'@',text(row,cid+'#'+str(i))),w.ar.TypedValue(b'@',row)])
        for i in [1,2,3]:
            if w.elements(p.data['courses'].contents[i].value):raise APIError('DEMO_TEMPLATE','Auxiliary Course arrays must be empty.')
        w.set_elements(course_array(p.data['courses']),courses);p.data['timetable'].contents=[w.ar.TypedValue(b'i',len(table)//2)]+table

    def timetable_csv(self,schedule,args):
        output=io.StringIO(newline='');writer=csv.writer(output);writer.writerow(['车次','方向','始发站','始发时间',args.stations[1].display_name+'到达',args.stations[1].display_name+'出发','终到站','终到时间','编组','性质'])
        for row in schedule:
            stations=args.stations if row['direction']=='down' else list(reversed(args.stations))
            writer.writerow([row['course_id'],'下行' if row['direction']=='down' else '上行',stations[0].display_name,clock(row['departure_s']),clock(row['middle_arrival_s']),clock(row['middle_departure_s']),stations[-1].display_name,clock(row['arrival_s']),'DEMO_EMU_'+str(args.maximum_speed_kmh),'模拟'])
        return output.getvalue().encode('utf-8-sig')

    def write_instructions(self,base,target,run_name,schedule,args,plan):
        route='—'.join(s.display_name for s in args.stations);rows=[]
        for row in schedule:
            stations=args.stations if row['direction']=='down' else list(reversed(args.stations))
            rows.append(f"| {row['course_id']} | {stations[0].display_name} | {clock(row['departure_s'])} | {clock(row['middle_arrival_s'])} / {clock(row['middle_departure_s'])} | {stations[-1].display_name} | {clock(row['arrival_s'])} |")
        instructions=f'''# {route}：{args.maximum_speed_kmh} km/h 演示工程

这是独立的新工程。距离 {sum(args.section_distances_m)/1000:g} km、时刻表、{args.nominal_power_kw} kW 牵引曲线均为演示设定，不是真实运行图或实测车辆性能。

## 加载

1. 在 OpenTrack 的 Info → Preferences → Import 导入 `{target/run_name}`。
2. 打开 `OTDocuments` 中的三份 .opentrack 文件：{', '.join(s.document for s in args.stations)}；也可使用导入的 Document Set。
3. 三份 .otsimcor 走行图分别对应两区间和全线，均已写入导入配置。
4. Tools → Courses/Services 应有 {len(schedule)} 个 G 字头车次，全部绑定 `DEMO_EMU_{args.maximum_speed_kmh}` 和对应行程。
5. Simulation 的保存配置为 Step **0.1 s**、Time Ratio **30:1**、起点 **{clock(min(r['departure_s'] for r in schedule))}**、终点 **{clock(max(r['arrival_s'] for r in schedule)+1800)}**。启动前确认实际控件值与保存值一致，尤其不能仍为 500。

全线正线限速 {args.maximum_speed_kmh} km/h，站内/咽喉限速 {args.station_speed_kmh} km/h；列车从零加速、到站制动，速度并非全程恒定。数值积分步长与播放倍率是两个参数。

## 排班

双向各 {args.departures_each_direction} 列，{args.stations[1].display_name}停站 {args.dwell_s} 秒。目标同向间隔 {args.departure_interval_s//60} 分钟；资源检查需要时会自动推迟发车。计划计入信号机后方完整车体、提前预留和释放余量。

| 车次 | 始发 | 发车 | 中间站到 / 发 | 终到 | 到达 |
|---|---|---|---|---|---|
'''+ '\n'.join(rows)+f'''

## 验证范围

- 原生归档往返、六库引用、站名/连接器/行程重命名、十二条 Path 里程、三份走行图时间/里程均已静态检查。
- 离线资源模型冲突数：**{plan['conflict_count']}**。它采用 25 m 空间积分、已有 Strahl 估算、0.7 m/s² 制动及 15% 走行余量，不能替代原生仿真验收。
- `speed-profile-down.csv` / `speed-profile-up.csv` 提供离线运动学速度与含余量的计划时间，不能作为实际仿真速度输出。
- 本次只写入独立工程；未启动或操作 OpenTrack，未改注册表/全局首选项，也未覆盖 BJTU。
- 完整检查和调整记录见 `demo-plan.json`，可读时刻表见 `timetable.csv`。
'''
        (base/'使用说明.md').write_text(instructions,encoding='utf8')
