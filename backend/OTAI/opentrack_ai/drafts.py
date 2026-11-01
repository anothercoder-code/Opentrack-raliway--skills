import copy
import json
import os
import re
from pathlib import Path
import uuid

from .archive import APIError,KINDS,Project,clock,digest,inside,parse_run,seconds,w
from native_text_schema import normalize_labels
from opentrack_course_schema import course_array


def text(template,value):
    value.encode('ascii')
    sample=next(o for o in w.objects(template) if w.kind(o)=='NSString')
    return w.ar.GenericArchivedObject(sample.clazz,None,[w.ar.TypedValue(b'+',value.encode('ascii'))])


def set_text(obj,index,value):obj.contents[index].values[0]=text(obj,value)


def atomic_write(path,blob):
    tmp=path.with_name(path.name+'.otai-'+uuid.uuid4().hex+'.tmp')
    tmp.write_bytes(blob)
    try:tmp.replace(path)
    finally:
        if tmp.exists():tmp.unlink()


class DraftManager:
    def __init__(self,service):self.service=service

    def folder(self,identifier):return inside(self.service.work/identifier,[self.service.work])

    def load_manifest(self,identifier):
        folder=self.folder(identifier);path=folder/'manifest.json'
        if not path.is_file():raise APIError('DRAFT_NOT_FOUND','Draft ID does not exist.',identifier)
        manifest=json.loads(path.read_text(encoding='utf8'))
        for relative,expected in manifest['draft_files'].items():
            p=inside(folder/'project'/relative,[folder/'project'])
            if not p.is_file() or digest(p.read_bytes())!=expected:raise APIError('DRAFT_CHANGED','A draft input changed after validation. Create a new draft to review the changed input.',relative)
        return manifest

    def stage(self,args):
        from .legacy_geometry_guard import reject
        reject()  
        self.service.check_build();p=self.service.project(args);changes=[]
        original_sources=dict(p.sources);original_digest=p.source_digest
        simulation=None;geometry_changed=False
        from .geometry import Geometry,KINDS as GEOMETRY_KINDS
        from .generation import OperationalData,KINDS as GENERATION_KINDS
        from .itinerary_controls import Itineraries,KINDS as ITINERARY_KINDS
        geometry=Geometry(p)
        operations=OperationalData(p)
        for change in args.changes:
            kind=change.kind
            if kind in GENERATION_KINDS:
                changes.append(operations.apply(change))
            elif kind in GEOMETRY_KINDS:
                changes.append(geometry.apply(change));geometry_changed=True
            elif kind in ['define_route','define_shunting','set_route_protection','define_path','define_itinerary']:
                from .operations import Definitions
                result=getattr(Definitions(p),kind)(change);changes.append(result)
                if result.get('security_arrays_upgraded'):operations.migrations['OTSecurityArray']=operations.migrations.get('OTSecurityArray',0)+result['security_arrays_upgraded']
            elif kind=='repair_itinerary_documents':
                from .operations import rebase_itinerary_documents
                changes.append({'kind':kind,'references':rebase_itinerary_documents(p,p.project)})
            elif kind=='delete_all_paths':
                from .path_lifecycle import delete_all_paths
                changes.append(delete_all_paths(p,change))
            elif kind=='edit_itinerary_margins':
                from .itinerary_margins import edit
                changes.append(edit(p,change))
            elif kind in ITINERARY_KINDS:
                changes.append(Itineraries(p).apply(change))
            elif kind=='edge_length':
                matches=[o for o in p.models.get(change.document,[]) if w.kind(o)=='OTEdgeModel' and o.contents[0].value==change.edge_id]
                if len(matches)!=1:raise APIError('EDGE_NOT_FOUND','Expected one matching Edge in the specified document.')
                edge=matches[0];before=edge.contents[9].values[1]
                edge.contents[9].values=list(edge.contents[9].values);edge.contents[9].values[1]=change.length_m
                changes.append({'kind':kind,'document':change.document,'edge_id':change.edge_id,'before_m':before,'after_m':change.length_m});geometry_changed=True
            elif kind=='normalize_labels':
                for name,obj in [*p.data.items(),*p.docs.items(),*p.corridors.items()]:
                    for row in normalize_labels(obj):changes.append({'kind':kind,'archive':name,**row})
            elif kind=='repair_catalog_layout':
                root=p.data['courses']
                if w.kind(root)=='OTCourseList' and root.clazz.version==3:
                    actual=w.elements(root.contents[4].value);wrong=w.elements(root.contents[1].value)
                    if not actual and wrong and all(w.kind(o)=='OTCourse' for o in wrong):
                        if w.elements(root.contents[2].value) or w.elements(root.contents[3].value):raise APIError('AMBIGUOUS_REPAIR','Auxiliary course arrays are nonempty; refusing to infer their meaning.')
                        w.set_elements(root.contents[4].value,wrong);w.set_elements(root.contents[1].value,[])
                        changes.append({'kind':kind,'archive':'courses','moved_course_count':len(wrong),'from_index':1,'to_index':4})
                if w.kind(p.data['stations']) in ['NSArray','NSMutableArray']:
                    stations=w.elements(p.data['stations'])
                    if not all(w.kind(o)=='OTStation' for o in stations):raise APIError('AMBIGUOUS_REPAIR','Station array contains non-station objects.')
                    from .operations import Definitions,clone
                    dictionary=clone(Definitions(p).template('NSMutableDictionary'))
                    dictionary.contents=[w.ar.TypedValue(b'i',len(stations))]
                    for station in stations:dictionary.contents.extend([w.ar.TypedValue(b'@',station.contents[1].value),w.ar.TypedValue(b'@',station)])
                    p.data['stations']=dictionary
                    changes.append({'kind':kind,'archive':'stations','root':'NSMutableDictionary'})
            elif kind=='reencode_native':
                changes.append({'kind':kind,'known_native_length_errors':dict(p.native_length_errors)})
            elif kind=='simulation':
                from .native_records import absolute_time
                begin=absolute_time(change.start,change.start_day_offset);end=absolute_time(change.stop,change.stop_day_offset)
                if begin>=end:raise APIError('SIMULATION_WINDOW','Stop day/time must be later than start day/time.')
                simulation=change.model_dump()
                p.parameters.update({'Start Time':[change.start],'Stop Time':[change.stop],'Start Day Offset':[str(change.start_day_offset)],'Stop Day Offset':[str(change.stop_day_offset)],'Step':[str(change.step_s)],'Time Ratio':[change.time_ratio]})
                p.scenario.update(begin_s=begin,end_s=end,simulation_step_s=change.step_s)
                for corridor in p.corridors.values():corridor.contents[7].values=[float(begin),float(end)]
                changes.append(change.model_dump())
            else:
                if kind in ['bind_course','clone_course','course_enabled']:operations.prepare_courses()
                courses={w.string(c.contents[0].value):c for c in p.courses()}
                cid=change.template_id if kind=='clone_course' else change.course_id
                if cid not in courses:raise APIError('COURSE_NOT_FOUND','Selected source course does not exist.',cid)
                course=courses[cid]
                if kind=='clone_course':
                    if change.new_id in courses:raise APIError('COURSE_EXISTS','New course ID already exists.',change.new_id)
                    operations.requested_courses+=1
                    if operations.requested_courses>1000:raise APIError('GENERATION_SIZE','Cloned and generated Course definitions share the per-draft limit of 1000.')
                    cloned=copy.deepcopy(course);set_text(cloned,0,change.new_id)
                    w.set_elements(course_array(p.data['courses']),p.courses()+[cloned]);course=cloned
                    table=p.data['timetable'];entries=[]
                    for key,entry in p.table().items():
                        if w.string(entry.contents[1].value)==cid:
                            row=copy.deepcopy(entry);set_text(row,1,change.new_id)
                            for connection in w.elements(row.contents[9].value):set_text(connection,0,change.new_id)
                            entries.extend([w.ar.TypedValue(b'@',text(row,change.new_id+'#'+str(row.contents[3].value))),w.ar.TypedValue(b'@',row)])
                    if not entries:raise APIError('TIMETABLE_MISSING','Template course has no timetable to clone.')
                    table.contents.extend(entries);table.contents[0].values[0]+=len(entries)//2
                    cid=change.new_id
                if kind in ['bind_course','clone_course']:
                    if change.train is not None:set_text(course,3,change.train)
                    if change.itinerary is not None:w.set_elements(course.contents[2].value,[text(course,change.itinerary)])
                if kind in ['shift_timetable','clone_course']:
                    from .native_records import absolute_time,split_time
                    for entry in p.table().values():
                        if w.string(entry.contents[1].value)==cid:
                            for index,day_index in [(6,0),(7,1)]:
                                old=w.string(entry.contents[index].value)
                                if old!='HH:MM:SS':
                                    day,updated=split_time(absolute_time(old,entry.contents[15].values[day_index])+change.seconds)
                                    set_text(entry,index,updated);entry.contents[15].values[day_index]=day
                if kind=='course_enabled':course.contents[5].values[0]=int(change.enabled)
                changes.append(change.model_dump())
        operations.finalize()
        if geometry_changed:
            p.scenario['mileage_changed_requires_review']=True
        identifier='draft-'+uuid.uuid4().hex[:16];folder=self.folder(identifier);destination=folder/'project'
        folder.mkdir(parents=True,exist_ok=False)
        files=self.write_project(p,destination,original_sources)
        revised=Project(self.service.root,str(destination),str(destination/'BJTU-demo.run'))
        validation=self.service.validate_project(revised,args.validation_scope)
        if geometry_changed:validation['warnings'].append({'code':'GEOMETRY_CHANGED','details':'Review station diagram mileage, timetable feasibility and native running times after changing Edge lengths. No automatic capacity/retiming claim is made.'})
        manifest={'draft_id':identifier,'label':args.label,'source_project':str(p.project),
            'source_run':str(p.run_file) if p.run_file else None,'source_digest':original_digest,
            'source_files':{path:digest(blob) for path,blob in original_sources.items()},
            'draft_files':{str(path.relative_to(destination)):digest(blob) for path,blob in files.items()},
            'changes':changes,'serialization_migrations':operations.migrations,'validation':validation,'validation_scope':args.validation_scope,'geometry_changed':geometry_changed,
            'applied':False,'native_simulation_verified':False}
        (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
        return {'draft_id':identifier,'source_digest':original_digest,'draft_project':str(destination),
            'run_file':str(destination/'BJTU-demo.run'),'changes':changes,'serialization_migrations':operations.migrations,'validation':validation,
            'source_files_unchanged':all(Path(path).is_file() and digest(Path(path).read_bytes())==sha for path,sha in manifest['source_files'].items()),
            'apply_enabled':self.service.allow_apply}

    def write_project(self,p,destination,original_sources):
        from .legacy_geometry_guard import reject
        reject()  
        from .operations import rebase_itinerary_documents
        rebase_itinerary_documents(p,destination)
        (destination/'OTData').mkdir(parents=True,exist_ok=False);(destination/'OTDocuments').mkdir()
        output=destination/'output';output.mkdir()
        files={}
        def encoded(obj,source):
            if str(source) not in original_sources:return w.dump_verified(obj,p.versions[str(source)])
            old=original_sources[str(source)]
            unchanged=w.fingerprint(w.load(old)[0])==w.fingerprint(obj)
            return old if unchanged and str(source) not in p.native_length_errors else w.dump_verified(obj,p.versions[str(source)])
        for kind,obj in p.data.items():files[destination/'OTData'/('empty.'+kind)]=encoded(obj,p.data_paths[kind])
        for name,obj in p.docs.items():files[destination/'OTDocuments'/(name+'.opentrack')]=encoded(obj,p.doc_paths[name])
        for name,obj in p.corridors.items():
            source=next(path for path in p.versions if Path(path).name==name)
            set_text(obj,2,str(destination/'OTDocuments'/name))
            files[destination/'OTDocuments'/name]=w.dump_verified(obj,p.versions[source])
        params=copy.deepcopy(p.parameters)
        params.update({key:[str(destination/'OTData'/('empty.'+kind)).replace('\\','/')] for key,kind in KINDS.items()})
        params['Infrastructure Document']=[str(destination/'OTDocuments'/(name+'.opentrack')).replace('\\','/') for name in p.docs]
        params['Train Diagram Document']=[str(destination/'OTDocuments'/name).replace('\\','/') for name in p.corridors]
        params['OutputPath']=[str(output).replace('\\','/')]
        if 'Document Set Document' in params:params['Document Set Document']=params['Infrastructure Document']
        for key,value in {'Start Time':'06:00:00','Stop Time':'23:59:59','Step':'0.2','Time Ratio':'30:1',
                'Keep Occupations':'0','Show Train':'1','Output Simulation Protocol':'1','Output Messages (Text)':'1'}.items():params.setdefault(key,[value])
        lines=['// OTAI draft; native simulation has not been executed.']+[key+'#'+value+'#' for key,values in params.items() for value in values]
        files[destination/'BJTU-demo.run']=('\r\n'.join(lines)+'\r\n').encode('ascii')
        if p.scenario:files[destination/'demo-scenario.json']=json.dumps(p.scenario,ensure_ascii=False,indent=2).encode('utf8')
        for path,blob in files.items():path.write_bytes(blob)
        return files

    def describe(self,args):
        manifest=self.load_manifest(args.draft_id)
        return manifest

    def publish(self,args):
        from .legacy_geometry_guard import reject
        reject()  
        self.service.check_build();manifest=self.load_manifest(args.draft_id)
        if not manifest['validation']['valid']:raise APIError('INVALID_DRAFT','Resolve draft errors before publishing.')
        if re.fullmatch(r'CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]',args.project_name,re.I):raise APIError('PROJECT_NAME','Reserved Windows project name.')
        target=inside(self.service.root/'OTProjects'/args.project_name,[self.service.root/'OTProjects'])
        if target.exists():raise APIError('PROJECT_EXISTS','Choose a new isolated project name; existing projects are never overwritten.',str(target))
        for path,expected in manifest['source_files'].items():
            source=inside(path,[self.service.root/'OTProjects',self.service.work,self.service.root/'OTData'])
            if not source.is_file() or digest(source.read_bytes())!=expected:raise APIError('SOURCE_CHANGED','Draft source changed before publication.',str(source))
        folder=self.folder(args.draft_id);draft=Project(self.service.root,str(folder/'project'),str(folder/'project/BJTU-demo.run'))
        validation_scope=manifest.get('validation_scope','preparation')
        current=self.service.validate_project(draft,validation_scope)
        if not current['valid']:raise APIError('INVALID_DRAFT','Current draft validation failed.',current['errors'])
        parent=self.service.work/('publish-'+uuid.uuid4().hex[:16]);staging=parent/'project'
        parent.mkdir(parents=True,exist_ok=False)
        draft.parameters['Document Set Name']=[args.project_name]
        self.write_project(draft,staging,dict(draft.sources))
        staged=Project(self.service.root,str(staging));validation=self.service.validate_project(staged,validation_scope)
        if not validation['valid']:raise APIError('PUBLICATION_VALIDATION','Isolated staging validation failed.',{'staging':str(staging),'errors':validation['errors']})
        from .operations import rebase_itinerary_documents
        rebase_itinerary_documents(staged,target)
        (staging/'OTData/empty.dest').write_bytes(w.dump_verified(staged.data['dest'],staged.versions[str(staged.data_paths['dest'])]))
        for name,document in staged.corridors.items():
            set_text(document,2,str(target/'OTDocuments'/name));path=staging/'OTDocuments'/name
            path.write_bytes(w.dump_verified(document,staged.versions[str(path)]))
        run=(staging/'BJTU-demo.run').read_bytes().replace(str(staging).replace('\\','/').encode('ascii'),str(target).replace('\\','/').encode('ascii'))
        run_name=args.project_name+'.run';(staging/run_name).write_bytes(run);(staging/'BJTU-demo.run').write_bytes(run)
        (staging/'opentrack-project.json').write_text(json.dumps({'default_run':run_name,'published_from_draft':args.draft_id},indent=2),encoding='utf8')
        scenario=staging/'demo-scenario.json'
        if scenario.is_file():
            settings=json.loads(scenario.read_text(encoding='utf8'));settings.update(database_bundle_dir=str(target/'OTData'),output_dir=str(target/'output'))
            scenario.write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf8')
        publication={'draft_id':args.draft_id,'source_project':manifest['source_project'],'source_digest':manifest['source_digest'],
            'serialization_migrations':manifest.get('serialization_migrations',{}),
            'project':str(target),'run_file':str(target/run_name),'isolated_publication':True,'validation_scope':validation_scope,'native_simulation_verified':False}
        (staging/'publication.json').write_text(json.dumps(publication,indent=2),encoding='utf8')
        purpose='原版格式信息生成版本，已通过数据结构、引用绑定和时刻顺序校验；仿真准备警告请查 publication.json。' if validation_scope=='generation' else '独立修复版本，已通过静态仿真准备检查。'
        (staging/'使用说明.md').write_text(purpose+'\n导入 '+str(target/run_name)+'，并打开 OTDocuments 中所需线路及走行图。\n原工程和运行中的原版程序未被修改；尚未做原生试跑，不能据此认定仿真成功或无冲突。\n',encoding='utf8')
        staging.rename(target);parent.rmdir()
        final=Project(self.service.root,str(target));validation=self.service.validate_project(final,validation_scope)
        if not validation['valid']:raise APIError('PUBLICATION_VALIDATION','Inspect the new isolated project; original remains untouched.',validation['errors'])
        return {**publication,'validation':validation,'source_files_unchanged':all(Path(path).is_file() and digest(Path(path).read_bytes())==sha for path,sha in manifest['source_files'].items())}

    def check_closed(self):
        from repair_hsr_persisted_defaults import require_application_closed
        try:require_application_closed()
        except RuntimeError as e:raise APIError('APPLICATION_RUNNING','Exit OpenTrack before applying a draft; in-memory saves can overwrite repaired data.') from e

    def apply(self,args):
        from .legacy_geometry_guard import reject
        reject()  
        if not self.service.allow_apply:raise APIError('APPLY_DISABLED','Applying to an existing project is disabled. Enable --allow-apply for user-authorized save updates; draft creation works without it.')
        self.service.check_build(require_binary=True);manifest=self.load_manifest(args.draft_id)
        if manifest['applied']:raise APIError('DRAFT_ALREADY_APPLIED','This draft has already been applied.',manifest.get('applied_run'))
        if args.expected_source_digest!=manifest['source_digest']:raise APIError('DIGEST_MISMATCH','Use the exact source digest returned by this draft.')
        if not manifest['validation']['valid']:raise APIError('INVALID_DRAFT','Resolve draft validation errors before applying.',manifest['validation']['errors'])
        self.service.work.mkdir(parents=True,exist_ok=True)
        lock=self.service.work/'.apply.lock'
        try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
        except FileExistsError as e:raise APIError('APPLY_BUSY','Another apply holds the project write lock. Inspect .apply.lock if a previous server terminated unexpectedly.') from e
        try:
            os.write(fd,str(os.getpid()).encode('ascii'));os.close(fd)
            self.check_closed()
            for path,expected in manifest['source_files'].items():
                path=inside(path,[self.service.root/'OTProjects',self.service.work,self.service.root/'OTData'])
                if not path.is_file() or digest(path.read_bytes())!=expected:raise APIError('SOURCE_CHANGED','Source input changed after the draft was prepared; create a new draft.',str(path))
            project=Project(self.service.root,manifest['source_project'],manifest['source_run'])
            if project.source_digest!=manifest['source_digest']:raise APIError('SOURCE_CHANGED','The selected source input set changed after staging.')
            folder=self.folder(args.draft_id);draft=Project(self.service.root,str(folder/'project'),str(folder/'project/BJTU-demo.run'))
            validation=self.service.validate_project(draft)
            if not validation['valid']:raise APIError('INVALID_DRAFT','Draft no longer passes validation.',validation['errors'])
            target=project.project;revision='ai-ready-'+uuid.uuid4().hex[:12]
            bundle=target/'OTData'/revision;bundle.mkdir(exist_ok=False)
            output=self.service.root/'OTOutput'/revision;output.mkdir(parents=True,exist_ok=False)
            plan={}
            from .operations import rebase_itinerary_documents
            rebase_itinerary_documents(draft,target)
            for kind in KINDS.values():
                blob=w.dump_verified(draft.data[kind],draft.versions[str(draft.data_paths[kind])]) if kind=='dest' else (folder/'project/OTData'/('empty.'+kind)).read_bytes()
                plan[target/'OTData'/('empty.'+kind)]=blob;plan[bundle/('AI.'+kind)]=blob
            for filename in [*(name+'.opentrack' for name in draft.docs),*draft.corridors]:
                path=inside(folder/'project/OTDocuments'/filename,[folder/'project'])
                blob=path.read_bytes()
                if path.suffix=='.otsimcor':
                    root,version=w.load_next_compatible(blob);set_text(root,2,str(target/'OTDocuments'/path.name));blob=w.dump_verified(root,version)
                plan[target/'OTDocuments'/path.name]=blob
            params=copy.deepcopy(draft.parameters)
            params.update({key:[str(bundle/('AI.'+kind)).replace('\\','/')] for key,kind in KINDS.items()})
            for key in ['Infrastructure Document','Document Set Document','Train Diagram Document']:
                if key in params:params[key]=[str(target/'OTDocuments'/Path(s).name).replace('\\','/') for s in params[key]]
            params['OutputPath']=[str(output).replace('\\','/')]
            run_blob=('// OTAI revision; native run pending.\r\n'+'\r\n'.join(key+'#'+v+'#' for key,values in params.items() for v in values)+'\r\n').encode('ascii')
            run=target/(revision+'.run');plan[run]=run_blob
            if project.run_file and project.run_file.is_relative_to(target):plan[project.run_file]=run_blob
            if draft.scenario:
                config=dict(draft.scenario);config['database_bundle_dir']=str(bundle);config['output_dir']=str(output)
                plan[target/'demo-scenario.json']=json.dumps(config,ensure_ascii=False,indent=2).encode('utf8')
            backup=self.service.root/'OTAI/backups'/revision;backup.mkdir(parents=True,exist_ok=False)
            before={path:path.read_bytes() if path.is_file() else None for path in plan}
            for path,blob in before.items():
                inside(path,[target])
                if blob is not None:
                    saved=backup/path.relative_to(target);saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(blob)
            (backup/'transaction.json').write_text(json.dumps({'target':str(target),'draft_id':args.draft_id,'files':[{ 'relative':str(p.relative_to(target)),'existed':blob is not None} for p,blob in before.items()]},indent=2),encoding='utf8')
            written=[]
            try:
                for path,blob in plan.items():
                    self.check_closed();path.parent.mkdir(parents=True,exist_ok=True);atomic_write(path,blob);written.append(path)
                loaded=Project(self.service.root,str(target),str(run))
                after_validation=self.service.validate_project(loaded)
                if not after_validation['valid']:raise APIError('POST_APPLY_VALIDATION','Applied files failed structural validation.',after_validation['errors'])
                updated_manifest=dict(manifest,applied=True,applied_run=str(run),backup=str(backup))
                atomic_write(folder/'manifest.json',json.dumps(updated_manifest,ensure_ascii=False,indent=2).encode('utf8'))
            except Exception:
                for path in reversed(written):
                    if before[path] is None:path.unlink(missing_ok=True)
                    else:atomic_write(path,before[path])
                raise
            return {'applied':True,'run_file':str(run),'database_bundle':str(bundle),'backup':str(backup),
                'validation':after_validation,'global_preferences_changed':False,'native_simulation_verified':False,
                'next_step':'Import the returned .run in OpenTrack. Global preferences, registry defaults and root OTTemp catalogs were deliberately not modified.'}
        finally:lock.unlink(missing_ok=True)
