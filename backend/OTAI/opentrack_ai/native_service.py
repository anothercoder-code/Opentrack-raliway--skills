import hashlib
import importlib.metadata
import json
import math
import re
from pathlib import Path

from .archive import APIError,LOCK,KINDS,LEGACY,Project,digest,inside,page,parse_run,ref,seconds,w,END_KINDS
from .catalog import EXPECTED_EXE_SHA256,TARGET_BASELINE,SCHEMAS,EVIDENCE
from . import __version__
from .native_records import absolute_time,trailer_record
from native_text_schema import native_strings
from opentrack_train_schema import bound_engine_names,engine_items,train_items
from opentrack_station_schema import station_items
from hsr_capacity_graph import initial_tail_resources


class Service:
    def __init__(self,root,allow_apply=False,allow_runtime=False):
        self.root=Path(root).resolve();self.allow_apply=allow_apply;self.allow_runtime=allow_runtime
        if not (self.root/'OpenTrack.app/OpenTrack.exe').is_file():
            from .resources import templates
            templates(self.root)
        self.work=self.root/'OTAI/workspaces'

    def project(self,args):return Project(self.root,args.project,args.run_file)

    def check_build(self,require_binary=False):
        path=self.root/'OpenTrack.app/OpenTrack.exe'
        if not path.is_file():
            if require_binary:raise APIError('BINARY_MISSING','This operation requires the audited OpenTrack executable.')
            from .resources import templates
            templates(self.root);return None
        actual=digest(path.read_bytes())
        if actual!=EXPECTED_EXE_SHA256:raise APIError('UNVERIFIED_BUILD','Archive edits/runtime offsets are pinned to the audited executable. Verify schemas for this new build first.',{'expected':EXPECTED_EXE_SHA256,'actual':actual})
        return actual

    def capabilities(self,args):
        path=self.root/'OpenTrack.app/OpenTrack.exe';actual=digest(path.read_bytes()) if path.is_file() else None
        descriptor=Path(__file__).resolve().parents[1]/'resources/function-bank.json'
        bank=json.loads(descriptor.read_text(encoding='utf8')) if descriptor.is_file() else None
        return {'version':__version__,'root':str(self.root),'source':'Existing OTUndo decompilation/disassembly and schema helpers',
            'offline_helper_directory':str(LEGACY),
            'target_baseline':{**TARGET_BASELINE,'selected_executable':str(path),'stock_file_verified':actual==EXPECTED_EXE_SHA256 if actual else False,
                'english_resource_directory_present':(path.parent/'Resources/English.lproj').is_dir(),
                'app_directory_framework_overrides':[name for name in ['AppKit.dll','Foundation.dll'] if (path.parent/name).is_file()],
                'stock_runtime_acceptance':False},
            'executable_sha256':actual,'audited_build_matches':actual==EXPECTED_EXE_SHA256 if actual else None,
            'offline_archive_editing_requires_original_executable':False,
            'rolling_stock_maintenance':['update_engines','update_formations','update_categories','rename_engines','rename_formations','rename_categories','delete_engines','delete_formations','delete_categories','edit_engine_diagrams','migrate_rolling_stock'],
            'engine_diagram_data':['multiple_supply_systems','linear_and_hyperbolic_segments','signed_electrical_braking','speed_band_fixed_and_fractional_losses','ordered_diagram_add_duplicate_delete','partial_fields','native_limit_recomputation','native_curve_point_text_import_export','calibrated_rgb_white_color','point_add_selected_update_drag_model_delete','native_scale_commands','paged_diagram_data'],
            'railml_timetable_readonly_analysis':True,'railml_timetable_export':True,'railml_timetable_import':False,'mcp_sdk_version':importlib.metadata.version('mcp'),'draft_editing':True,'apply_enabled':self.allow_apply,
            'runtime_read_enabled':self.allow_runtime,'runtime_memory_writes':False,'gui_operations':False,
            'new_synthetic_project_creation':True,'generated_demo_plan_checks':True,
            'function_pseudocode_reading':bank is not None,'function_bank':{key:bank[key] for key in ['bank_id','functions','pseudocode_files','failed_entries','metadata_methods','native_classes','native_categories','full_entry_export_gate_passed']} if bank else None,'function_pseudocode_is_complete_source_recovery':False,'native_category_metadata':True,'native_method_disassembly':True,'function_coverage_lookup':True,'native_method_invocation':False,
            'independent_directional_search':True,'native_definition_drafts':['route','path','itinerary','shunting','overlap_binding','release_groups','local_slow_speed_zone'],'full_replica_complete':False,
            'native_geometry_drafts':True,'persistent_editor_undo_redo':True,
            'operational_data_generation':['engine','train_category','powered_and_trailer_formation','braking_table','station','route','path','itinerary','course','course_controls','bulk_course_updates','itinerary_preference_order','course_rename','course_delete','reset_unavailable_itineraries','multiday_timetable','service_pattern','timetable_skeleton_from_first_itinerary','category_timetable_defaults','station_timing_flag','timetable_connections','interval_references','sequential_interval_course_copy','interval_connection_renumbering','interval_connection_property_propagation','partial_timetable_rows','row_insert_delete','interval_family_updates','connection_edits','saved_actual_time_commands','native_timetable_text_exchange'],
            'rolling_stock_xml_exchange':{'version':'2.2','export_formats':['railml_2_2','railml_1_00','railml_1_03'],'export_tool':'opentrack_export_rolling_stock','import_field':'rolling_stock_imports','native_execution':False,'legacy_1_00_1_03':True,'legacy_import_implemented':False,'full_standard_xsd_validation':False},
            'rolling_stock_migration':{'operation':'migrate_rolling_stock','engines':[0,1,2],'diagrams':[0,1,2,3],'formations':list(range(17)),'trailers':[0,1,2,3],'read_only_decoded_views':True,'stock_writes_upgrade_in_draft':True},
            'category_saved_controls':['dispatch_priority','delay_and_performance_tables','stop_and_timing_defaults','foreground_background_color','signed_dwell_variation_and_units','delay_add_type','connection_default','departure_process_and_start_mode','track_name_policy','early_delayed_offsets'],
            'development_focus':'Original-function Skill/MCP and operational data generation; no replacement GUI or physics/simulation engine is required.',
            'source_evidence_entries':len(EVIDENCE),'schema_contracts':list(SCHEMAS),
            'validation_boundary':'Archive/schema validation does not establish successful native simulation or maximum capacity.'}

    def inspect(self,args):
        p=self.project(args);counts={};catalogs={};errors=[]
        for owner,items in p.models.items():
            kinds={w.kind(o) for o in items};counts[owner]={kind:sum(w.kind(o)==kind for o in items) for kind in sorted(kinds)}
        for kind in ['services','trains','engines','stations','timetable']:
            try:catalogs[kind]=len(p.catalog(kind))
            except (AssertionError,IndexError,ValueError,APIError) as e:catalogs[kind]=None;errors.append({'catalog':kind,'error':str(e) or 'Native schema mismatch'})
        return {'project':str(p.project),'selected_run':str(p.run_file) if p.run_file else None,'source_digest':p.source_digest,
            'catalog_paths':{k:str(v) for k,v in p.data_paths.items()},'model_counts':counts,'catalog_counts':catalogs,
            'scenario':p.scenario,'run_parameters':p.parameters,'native_length_errors':p.native_length_errors,'schema_errors':errors,
            'canonical_catalogs_differing_from_selected_run':p.canonical_differences,
            'evidence_level':'offline archive snapshot','native_simulation_verified':False}

    def objects(self,args):
        p=self.project(args);rows=[]
        for owner,items in p.models.items():
            if args.document and owner!=args.document:continue
            for obj in items:
                kind=w.kind(obj);ident=obj.contents[0].value
                if args.object_id is not None and ident!=args.object_id:continue
                if args.class_name and kind!=args.class_name:continue
                row={'document':owner,'class':kind,'id':ident,'x':obj.contents[2].value,'y':obj.contents[3].value}
                if kind=='OTEdgeModel':row.update(length_m=obj.contents[9].values[1],ends=[obj.contents[i].value.contents[0].value for i in [7,8]])
                if kind in END_KINDS:
                    sig=obj.contents[11].value
                    row.update(related_id=obj.contents[8].value,signal_id=sig.contents[0].value if sig else None,station_sign=ref(obj.contents[12].value))
                if args.query and args.query.casefold() not in json.dumps(row,ensure_ascii=False).casefold():continue
                if args.object_id is not None:row['archive_fields']=[{'index':i,'encodings':[e.decode('ascii','replace') for e in g.encodings],'values':[ref(v) for v in g.values]} for i,g in enumerate(obj.contents)]
                rows.append(row)
        return page(rows,args.limit,args.offset)

    def native_class(self,args):
        from .native import resolve
        path,_,result=resolve(self.root,args)
        methods=[dict(m,method_kind='instance') for m in result.pop('methods')]+[dict(m,method_kind='class') for m in result.pop('class_methods')]
        methods=[m for m in methods if args.method_filter.casefold() in m['name'].casefold()]
        result.update(binary=str(path),binary_sha256=digest(path.read_bytes()),methods=page(methods,args.limit,args.offset),
            evidence_level='read-only PE metadata; no native methods invoked',note='Runtime ivar byte offsets and archive contents indices are different namespaces.')
        return result

    def disassemble_method(self,args):
        from .native import disassemble
        return disassemble(self.root,args)

    def function_coverage(self,args):
        from .coverage import read_coverage
        return read_coverage(self.root,args)

    def inspect_topology(self,args):
        from .topology import Topology
        return Topology(self.project(args)).inspect(args)

    def search_network(self,args):
        from .topology import Topology
        return Topology(self.project(args)).search(args)

    def list_routes(self,args):
        from .topology import Topology
        p=self.project(args);rows=Topology(p).route_records()
        rows=[{key:value for key,value in row.items() if not key.startswith('_')} for row in rows
            if (not args.document or row['document']==args.document) and (args.start_id is None or row['start_id']==args.start_id)]
        return {**page(rows,args.limit,args.offset),'source_digest':p.source_digest,'native_simulation_verified':False}

    def replica_status(self,args):
        
        
        path=Path(__file__).resolve().parents[1]/'replica/requirements.json'
        if not path.is_file():raise APIError('REQUIREMENTS_UNAVAILABLE','Full replication requirements have not been generated.')
        data=json.loads(path.read_text(encoding='utf8'));rows=data['requirements']
        if args.query:rows=[row for row in rows if args.query.casefold() in json.dumps(row,ensure_ascii=False).casefold()]
        return {**{key:value for key,value in data.items() if key!='requirements'},**page(rows,args.limit,args.offset)}

    def schemas(self,args):
        if args.name is None:return {'contracts':SCHEMAS,'audited_executable_sha256':EXPECTED_EXE_SHA256}
        if args.name not in SCHEMAS:raise APIError('SCHEMA_NOT_FOUND','Choose one of the exposed audited contracts.',list(SCHEMAS))
        return {'name':args.name,**SCHEMAS[args.name]}

    def catalog(self,args):
        p=self.project(args)
        if args.kind=='itineraries':
            from .itinerary_controls import catalog_rows
            return page(catalog_rows(p,args),args.limit,args.offset)
        rows=p.catalog(args.kind,args.include_curves)
        if args.query:rows=[r for r in rows if args.query.casefold() in json.dumps(r,ensure_ascii=False).casefold()]
        return page(rows,args.limit,args.offset)

    def get_service(self,args):
        p=self.project(args)
        rows=[c for c in p.courses() if w.string(c.contents[0].value)==args.course_id]
        if len(rows)!=1:raise APIError('COURSE_NOT_FOUND','Expected exactly one matching course.',args.course_id)
        course=p.service(rows[0]);trains={r['name']:r for r in p.catalog('trains')};engines={r['name']:r for r in p.catalog('engines',args.include_curves)}
        vehicle=trains.get(course['train']);course['vehicle']=vehicle
        course['engine_details']=[engines.get(name) for name in vehicle['engines']] if vehicle else []
        categories={r['name']:r for r in p.catalog('categories')}
        course['category_details']=categories.get(vehicle['category']) if vehicle else None
        course['vehicle_length']=self.vehicle_lengths(p).get(course['train'])
        course['timetable']=sorted([r for r in p.catalog('timetable') if r['course_id']==args.course_id],key=lambda r:r['index'])
        return course

    def vehicle_lengths(self,p):
        from .native_records import engine_reference_names
        engines={w.string(e.contents[1].value):e for e in engine_items(p.data['depot'])};result={}
        for vehicle in train_items(p.data['trains']):
            name=w.string(vehicle.contents[0].value);references=engine_reference_names(vehicle)
            trailers=w.elements(vehicle.contents[2].values[2]) if vehicle.contents[2].values[2] else []
            supported=all(ref in engines for ref in references) and all(w.kind(obj)=='OTTrailer' for obj in trailers)
            decoded=[trailer_record(obj) for obj in trailers] if supported else []
            result[name]={'length_m':sum(engines[ref].contents[2].values[2] for ref in references)+sum(obj['length_m'] for obj in decoded) if supported else None,
                'supported':supported,'note':'Sum of explicit Engine and Trailer record lengths; positions and number_of_items do not multiply mass/length.'}
        return result

    def paths(self,args):
        p=self.project(args);_,_,paths=p.graph()
        from .operations import Definitions
        definitions=Definitions(p).paths()
        return page([{'name':name,'description':w.string(definitions[name][2].contents[3].value),'distance_m':row['distance_m'],'route_count':len(row['routes']),
            'start':row['routes'][0]['start'],'end':row['routes'][-1]['end']} for name,row in sorted(paths.items())],args.limit,args.offset)

    def trace(self,args):
        p=self.project(args);_,models,paths=p.graph()
        if args.path_name not in paths:raise APIError('PATH_NOT_FOUND','Path name must match a defined native Path.',args.path_name)
        path=paths[args.path_name]
        bodies={}
        for name,vehicle in self.vehicle_lengths(p).items():
            if not vehicle['supported']:bodies[name]=vehicle;continue
            try:bodies[name]={'supported':True,**initial_tail_resources(path,models,vehicle['length_m'])}
            except AssertionError as e:bodies[name]={'supported':False,'reason':str(e)}
        return {'name':args.path_name,**path,'initial_body_by_vehicle':bodies,'evidence_level':'offline directional route/resource graph'}

    def validate(self,args):return self.validate_project(self.project(args),getattr(args,'validation_scope','preparation'))

    def check_demo_plan(self,args):
        from .planning import check_plan
        return check_plan(self.project(args))

    def create_demo_line(self,args):
        from .demo import DemoBuilder
        return DemoBuilder(self).create(args)

    def validate_project(self,p,validation_scope='preparation'):
        errors=[];warnings=[];checks=0;destinations={}
        def check(condition,code,details):
            nonlocal checks
            checks+=1
            if not condition:errors.append({'code':code,'details':details})
        def preparation_check(condition,code,details):
            if validation_scope=='generation':
                if not condition:warnings.append({'code':code,'details':details,'scope':'simulation preparation; not a native data-integrity failure'})
            else:check(condition,code,details)
        for path,error in p.native_length_errors.items():check(False,'NATIVE_LENGTH',{'file':path,'error':error})
        for kind,obj in [*p.data.items(),*p.docs.items(),*p.corridors.items()]:
            for text in native_strings(obj):
                check(w.string(text).isascii(),'NATIVE_CSTRING',{'archive':kind,'text':w.string(text)[:160]})
        try:
            courses=p.courses();trains=train_items(p.data['trains']);engines=engine_items(p.data['depot']);stations=station_items(p.data['stations']);table=p.table()
            cids=[w.string(c.contents[0].value) for c in courses];tids=[w.string(t.contents[0].value) for t in trains];eids=[w.string(e.contents[1].value) for e in engines]
            for cid in cids:check(bool(cid) and cid not in ['0','-1'],'COURSE_RESERVED_ID',cid)
            for key,obj in table.items():check(w.string(obj.contents[1].value) in cids,'TIMETABLE_ORPHAN',key)
            categories=[w.string(c.contents[1].value) for c in w.elements(p.data['trains'].contents[1].value)]
            for label,ids in [('courses',cids),('trains',tids),('engines',eids),('categories',categories)]:check(len(ids)==len(set(ids)),'DUPLICATE_NAME',label)
            destinations={w.string(d.contents[1].value):d for d in w.elements(p.data['dest'].contents[0].value)}
            from .operations import Definitions,itinerary_owners
            path_definitions=Definitions(p).paths();owners=itinerary_owners(p)
            for name,info in destinations.items():
                reference=Path(w.string(info.contents[2].value))
                if not reference.is_absolute():reference=p.project/reference
                check(reference.is_file(),'ITINERARY_DOCUMENT_MISSING',{'itinerary':name,'path':str(reference)})
                check(name in owners,'ITINERARY_DEFINITION_MISSING',name)
                for extended in w.elements(info.contents[4].value):
                    path_name=w.string(extended.contents[0].value)
                    if path_name in path_definitions:
                        owner,_,defined=path_definitions[path_name]
                        check(extended.contents[1].values==defined.contents[2].values and w.string(extended.contents[2].value)==owner,
                            'ITINERARY_PATH_REFERENCE',{'itinerary':name,'path':path_name})
                if name in owners and reference.resolve()!=p.doc_paths[owners[name]].resolve():
                    warnings.append({'code':'EXTERNAL_ITINERARY_DOCUMENT','details':{'itinerary':name,'path':str(reference),'selected_document':str(p.doc_paths[owners[name]])}})
            for train in trains:
                from .rolling_stock import formation_record
                saved=formation_record(train)
                check(saved['category'] in categories,'CATEGORY_BINDING',saved['name'])
                for name in saved['engines']:check(name in eids,'ENGINE_BINDING',{'train':saved['name'],'engine':name})
                if not saved['engines']:warnings.append({'code':'FORMATION_UNPOWERED_DEFINITION','details':saved['name'],'scope':'Saved definition is readable; powered movement/coupling is not established.'})
            for course in courses:
                row=p.service(course);cid=row['course_id'];check(row['train'] in tids,'VEHICLE_BINDING',row)
                check(bool(row['itineraries']),'EMPTY_ITINERARY',cid)
                for itinerary in row['itineraries']:check(itinerary in destinations,'ITINERARY_BINDING',{'course':cid,'itinerary':itinerary})
                entries=sorted([p.timetable_row(k,o) for k,o in table.items() if w.string(o.contents[1].value)==cid],key=lambda r:r['index'])
                check(len(entries)>=2,'TIMETABLE_MISSING',cid)
                undefined=[entry['index'] for entry in entries if entry['arrival']=='HH:MM:SS' and entry['departure']=='HH:MM:SS']
                endpoints_undefined=bool(entries) and (entries[0]['departure']=='HH:MM:SS' or entries[-1]['arrival']=='HH:MM:SS')
                preparation_check(not undefined and not endpoints_undefined,'TIMETABLE_PLANNED_TIMES_UNDEFINED',{'course_id':cid,'row_indices':undefined[:100],'row_count':len(entries)})
                previous=float('-inf')
                for i,entry in enumerate(entries):
                    check(entry['index']==i and entry['last_index']==len(entries)-1,'TIMETABLE_INDEX',entry)
                    check(entry['key']==cid+'#'+str(i),'TIMETABLE_KEY',entry)
                    check(entry['station_sign'] in stations,'TIMETABLE_STATION',entry)
                    for field in ['arrival','departure']:
                        text=entry[field]
                        if text=='HH:MM:SS':continue
                        value=absolute_time(text,entry[field+'_day_offset']);check(value>=previous,'TIMETABLE_ORDER',entry);previous=value
                    if entry['stop_at_station'] and entry['arrival']!='HH:MM:SS' and entry['departure']!='HH:MM:SS':
                        check(absolute_time(entry['departure'],entry['departure_day_offset'])-absolute_time(entry['arrival'],entry['arrival_day_offset'])>=entry['dwell_s'],'TIMETABLE_DWELL',entry)
                    reference=entry['interval_reference_course_id']
                    if reference not in ['','0','-1']:check(reference in cids,'INTERVAL_REFERENCE',{'course':cid,'reference':reference})
                    for connection in entry['connections']:
                        check(connection['course_id']==cid and connection['station_sign']==entry['station_sign'],'CONNECTION_OWNER',connection)
                        check(connection['target_course_id'] in cids,'CONNECTION_COURSE',connection)
                        target_rows=[obj for obj in table.values() if w.string(obj.contents[1].value)==connection['target_course_id'] and w.string(obj.contents[5].value)==connection['target_station_sign']]
                        check(bool(target_rows),'CONNECTION_STATION',connection)
                if entries and p.parameters.get('Start Time') and p.parameters.get('Stop Time'):
                    departure=entries[0]['departure']
                    if row['enabled'] and departure!='HH:MM:SS':
                        begin=absolute_time(p.parameters['Start Time'][0],int(p.parameters.get('Start Day Offset',['0'])[0]))
                        end=absolute_time(p.parameters['Stop Time'][0],int(p.parameters.get('Stop Day Offset',['0'])[0]))
                        preparation_check(begin<=absolute_time(departure,entries[0]['departure_day_offset'])<end,'DEPARTURE_OUTSIDE_WINDOW',cid)
            for key,entry in table.items():check(w.string(entry.contents[1].value) in cids,'ORPHAN_TIMETABLE',key)
        except (AssertionError,IndexError,ValueError,APIError) as e:check(False,'CATALOG_SCHEMA',str(e) or 'Native catalog schema mismatch')
        try:
            models=p.models;graph_error_start=len(errors)
            shortest=math.inf
            for owner,items in models.items():
                ids=[o.contents[0].value for o in items];check(len(ids)==len(set(ids)),'DUPLICATE_GRAPHIC_ID',owner)
                present={id(o) for o in items}
                for obj in w.objects(p.docs[owner]):
                    if w.kind(obj) in END_KINDS|{'OTEdgeModel','OTSignalModel','OTElement'}:
                        check(id(obj) in present,'DANGLING_GRAPHIC_REFERENCE',{'document':owner,'class':w.kind(obj),'id':obj.contents[0].value})
                ends={o.contents[0].value:o for o in items if w.kind(o) in END_KINDS}
                for ident,end in ends.items():
                    other=ends.get(end.contents[8].value);check(other is not None and other.contents[8].value==ident,'HALF_VERTEX_PAIR',{'document':owner,'id':ident})
                    element=end.contents[7].value
                    check(element is not None and id(element) in present and w.kind(element)=='OTElement','ELEMENT_REFERENCE',{'document':owner,'end':ident})
                    if element and w.kind(element)=='OTElement':
                        members=element.contents[7].value
                        if members is not None and w.kind(members) in ['NSArray','NSMutableArray']:
                            check(any(member is end for member in w.elements(members)),'ELEMENT_MEMBERSHIP',{'document':owner,'end':ident})
                        else:check(False,'ELEMENT_MEMBERSHIP',{'document':owner,'end':ident})
                    signal=end.contents[11].value
                    if signal:check(id(signal) in present and w.kind(signal)=='OTSignalModel' and signal.contents[7].value is end,'SIGNAL_BACKREFERENCE',{'document':owner,'end':ident})
                    for index in [9,10]:
                        edge=end.contents[index].value
                        if edge:check(id(edge) in present and w.kind(edge)=='OTEdgeModel','END_EDGE_REFERENCE',{'document':owner,'end':ident})
                for obj in items:
                    if w.kind(obj)=='OTEdgeModel':
                        length=obj.contents[9].values[1];check(math.isfinite(length) and length>0,'EDGE_LENGTH',{'document':owner,'id':obj.contents[0].value});shortest=min(shortest,length)
                        for i in [7,8]:
                            end=obj.contents[i].value
                            if end is None or w.kind(end) not in END_KINDS:
                                check(False,'EDGE_ENDPOINT',{'document':owner,'edge':obj.contents[0].value});continue
                            check(ends.get(end.contents[0].value) is end,'EDGE_ENDPOINT',{'document':owner,'edge':obj.contents[0].value})
                            check(any(end.contents[j].value is obj for j in [9,10]),'EDGE_BACKREFERENCE',{'document':owner,'edge':obj.contents[0].value})
                        for index,reverse in [(13,14),(14,13)]:
                            linked=obj.contents[index].value
                            if linked:check(id(linked) in present and w.kind(linked)=='OTEdgeModel' and linked.contents[reverse].value is obj,
                                'EXCLUSION_BACKREFERENCE',{'document':owner,'edge':obj.contents[0].value})
            if len(errors)!=graph_error_start:raise APIError('GEOMETRY_INVALID','Directional tracing was skipped after structural reference failures.')
            _,_,paths=p.graph()
            from .network_records import protection_errors
            for issue in protection_errors(p):check(False,issue['code'],issue['details'])
            for dest in w.elements(p.data['dest'].contents[0].value):
                for ext in w.elements(dest.contents[4].value):check(w.string(ext.contents[0].value) in paths,'ITINERARY_PATH',w.string(dest.contents[1].value))
            try:
                lengths=self.vehicle_lengths(p)
                for course in p.courses():
                    row=p.service(course);vehicle=lengths.get(row['train'])
                    if not vehicle or not vehicle['supported']:
                        warnings.append({'code':'VEHICLE_LENGTH_UNMODELED','details':row['train']});continue
                    for name in row['itineraries']:
                        if name not in destinations:continue
                        parts=w.elements(destinations[name].contents[4].value)
                        if not parts:continue
                        first_path=paths.get(w.string(parts[0].contents[0].value))
                        if first_path:
                            try:initial_tail_resources(first_path,models,vehicle['length_m']);check(True,'INITIAL_BODY',row['course_id'])
                            except AssertionError as e:preparation_check(False,'INITIAL_BODY_UNSUPPORTED',{'course':row['course_id'],'reason':str(e),'note':'This checker supports one approach Edge; it never silently truncates a body spanning additional Edges.'})
            except (AssertionError,IndexError,ValueError,APIError) as e:check(False,'VEHICLE_LENGTH_SCHEMA',str(e))
            if p.parameters.get('Step'):
                step=float(p.parameters['Step'][0]);preparation_check(.1<=step<=10,'SIMULATION_STEP',step)
                vmax=max((e.contents[7].value for e in engine_items(p.data['depot'])),default=350)
                if step*vmax/3.6>=shortest:warnings.append({'code':'LARGE_STEP_DISPLACEMENT','details':'At the catalog maximum speed a step spans at least the shortest Edge. This is coarse screening, not an accuracy proof.'})
        except (AssertionError,IndexError,KeyError,ValueError,APIError) as e:check(False,'ROUTE_GRAPH',str(e) or 'Directional graph/route reference is invalid')
        warnings.append({'code':'NATIVE_RUN_NOT_PERFORMED' if validation_scope=='generation' else 'NATIVE_RUN_REQUIRED','details':'No native simulation was launched. Dispatch capacity, collisions, actual running times and terminal release are not established by these structural checks. A run is needed only for a simulation-acceptance claim.'})
        return {'valid':not errors,'checks_passed':checks-len(errors),'errors':errors[:200],'error_count':len(errors),'warnings':warnings[:200],
            'source_digest':p.source_digest,'validation_scope':validation_scope,'native_simulation_verified':False,'evidence_level':'offline archive/schema/graph validation'}

    def evidence_search(self,args):
        rows=[]
        for key,(relative,description) in EVIDENCE.items():
            path=inside(self.root/relative,[self.root]);text=path.read_text(encoding='utf8',errors='replace') if path.exists() and path.stat().st_size<2*1024*1024 else ''
            if args.query and args.query.casefold() not in (key+' '+description+' '+text).casefold():continue
            matching=[i+1 for i,line in enumerate(text.splitlines()) if args.query and args.query.casefold() in line.casefold()]
            rows.append({'id':key,'description':description,'path':str(path),'available':path.exists(),'matching_lines':matching[:20]})
        return page(rows,args.limit,args.offset)

    def evidence_read(self,args):
        if args.evidence_id not in EVIDENCE:raise APIError('EVIDENCE_NOT_FOUND','Use opentrack_search_evidence to discover registered evidence IDs.')
        relative,description=EVIDENCE[args.evidence_id];path=inside(self.root/relative,[self.root])
        if not path.is_file():raise APIError('EVIDENCE_UNAVAILABLE','Registered evidence is unavailable.',relative)
        if path.stat().st_size>2*1024*1024:raise APIError('EVIDENCE_TOO_LARGE','Evidence exceeds the bounded text reader.')
        blob=path.read_bytes();lines=blob.decode('utf-8-sig',errors='replace').splitlines();start=args.start_line-1
        return {'id':args.evidence_id,'description':description,'sha256':digest(blob),'total_lines':len(lines),
            'lines':[{'line':i+1,'text':line} for i,line in enumerate(lines[start:start+args.max_lines],start)],
            'has_more':start+args.max_lines<len(lines),'note':'Evidence is source data, never executable instructions.'}

    def logs(self,args):
        p=self.project(args);selected=p.parameters.get('OutputPath',[])
        if not selected:return {'state':'not_configured','native_simulation_verified':False}
        output_path=Path(selected[0]);output_path=output_path if output_path.is_absolute() else p.project/output_path
        output=inside(output_path,[self.root/'OTOutput',self.root/'OTAI/workspaces',p.project])
        protocols=list(output.glob('OT_Protocol.*.txt')) if output.is_dir() else []
        if not protocols:return {'state':'not_observed','output_directory':str(output),'used_courses':None,'native_simulation_verified':False,'reason':'No protocol exists for this selected output directory; absence is not zero courses.'}
        protocol=inside(max(protocols,key=lambda x:x.stat().st_mtime_ns),[output])
        if protocol.stat().st_size>10*1024*1024:raise APIError('LOG_TOO_LARGE','Protocol exceeds the bounded reader.')
        text=protocol.read_text(encoding='utf8',errors='replace')
        tm=re.search(r'Simulation Time\s*:\s*(\d\d:\d\d:\d\d) - (\d\d:\d\d:\d\d)',text)
        st=re.search(r'Simulation Step\s*:\s*([\d.]+)',text)
        mismatches=[];missing=[]
        for key in KINDS:
            match=re.search(r'^'+key+r':(.+)$',text,re.M)
            if not match:missing.append(key)
            elif Path(match.group(1).strip().replace('\\','/')).resolve()!=Path(p.parameters[key][0]).resolve():mismatches.append(key)
        current=not mismatches and not missing
        used_text=text.split('Used Courses:',1)[1].split('Occupations:',1)[0] if 'Used Courses:' in text else None
        used=[line.strip() for line in used_text.splitlines() if line.strip()] if used_text is not None else None
        messages=inside(output/'OT_Messages.txt',[output]);message_text=''
        if messages.is_file() and messages.stat().st_size<=10*1024*1024:message_text=messages.read_text(encoding='utf8',errors='replace')
        window_matches=bool(tm and tm.groups()==(p.parameters.get('Start Time',[None])[0],p.parameters.get('Stop Time',[None])[0]))
        configured_days=[int(p.parameters.get(key,['0'])[0]) for key in ['Start Day Offset','Stop Day Offset']]
        day_offsets_supported=not any(configured_days)
        step_matches=bool(st and math.isclose(float(st.group(1)),float(p.parameters.get('Step',['nan'])[0]),abs_tol=1e-6,rel_tol=1e-6))
        expected=sum(bool(c.contents[5].value) for c in p.courses())
        completed=bool(current and window_matches and day_offsets_supported and step_matches and used is not None and len(used)==expected and 'End of Simulation' in message_text and 'Cancel Simulation' not in message_text)
        return {'state':'protocol_completed' if completed else ('observed' if current else 'stale_or_incomplete'),
            'protocol':str(protocol),'protocol_matches_catalog_paths':current,'mismatched_catalog_keys':mismatches,'missing_catalog_keys':missing,
            'actual_window':list(tm.groups()) if tm else None,'actual_step_s':float(st.group(1)) if st else None,
            'configured_day_offsets':configured_days,'multiday_protocol_matching_supported':False,'configured_days_supported':day_offsets_supported,
            'window_matches':window_matches,'step_matches':step_matches,'used_courses':len(used) if used is not None and current else None,
            'expected_enabled_courses':expected,'message_tail':message_text.splitlines()[-args.message_lines:] if args.message_lines else [],
            'protocol_run_completed':completed,'all_courses_completed':None,
            'native_simulation_verified':False,'evidence_level':'native protocol files matched to selected input',
            'limitation':'Used Courses plus End of Simulation establishes a matching single-day protocol end, not every train reaching its terminal or absence of collisions. Matching nonzero day offsets and per-train completion acceptance are not implemented.'}

    def read_runtime(self,args):
        if not self.allow_runtime:raise APIError('RUNTIME_DISABLED','Restart this server with --runtime-read only when the user authorized this read-only inspection.')
        self.check_build(require_binary=True)
        import ctypes as c
        from ctypes import wintypes as wt
        api=c.WinDLL('kernel32',use_last_error=True);api.OpenProcess.argtypes=[wt.DWORD,wt.BOOL,wt.DWORD];api.OpenProcess.restype=wt.HANDLE
        api.QueryFullProcessImageNameW.argtypes=[wt.HANDLE,wt.DWORD,wt.LPWSTR,c.POINTER(wt.DWORD)];api.CloseHandle.argtypes=[wt.HANDLE]
        handle=api.OpenProcess(0x1000,False,args.pid)
        if not handle:raise APIError('PROCESS_UNREADABLE','Cannot query this process.')
        try:
            name=c.create_unicode_buffer(32768);size=wt.DWORD(len(name))
            if not api.QueryFullProcessImageNameW(handle,0,name,c.byref(size)):raise APIError('PROCESS_UNREADABLE','Cannot query executable path.')
            if Path(name.value).resolve()!=(self.root/'OpenTrack.app/OpenTrack.exe').resolve():raise APIError('PROCESS_OUTSIDE_SCOPE','PID must be the audited OpenTrack executable.')
        finally:api.CloseHandle(handle)
        from inspect_hsr_engine_runtime import Reader
        from inspect_hsr_collision_runtime import inspect
        reader=Reader(args.pid)
        try:return inspect(reader,args.pid,tuple(args.courses))
        finally:reader.close()
