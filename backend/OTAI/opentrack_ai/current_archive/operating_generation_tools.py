"""Explicit new network and planned operating catalogs in one fresh-directory transaction."""
import math,os
from typing import Annotated, Literal
from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator
from .network_generation_tools import GenerateNetwork, Sources as NetworkSources, NetworkGeneration, Text, Number, EndRef
from .tools import Input, sha
from .bundle_tools import Source
from . import writer as w, catalogs as c
from .zero_operations import station_binding as stations, vehicle_catalogs as vehicles, operations, speed_preferences, run_bundle
from ..errors import APIError
from .terminal_generation_schema import TerminalProfile
from .graphic_alignment import GraphicPlacement as Placement

class Sources(NetworkSources):
    depot_template:Source
    trains_template:Source
    courses_template:Source
    timetable_template:Source
    run_template:Source
    connection_template:Source|None=None
class Station(Input):
    sign:Text
    name:Text
    ends:Annotated[list[EndRef],Field(min_length=1,max_length=1000)]
    placement:Placement
    station_type_raw:Annotated[StrictInt,Field(ge=2,le=2)]
    interlock_type_raw:Annotated[StrictInt,Field(ge=4,le=4)]
    icon_show_type_raw:Annotated[StrictInt,Field(ge=1,le=1)]
    timing_point:StrictBool
class TrainParameters(Input):
    maximum_acceleration_mps2:Annotated[Number,Field(gt=0,le=10)]
    braking_delay_s:Annotated[Number,Field(ge=0,le=60)]
    braking_release_speed_kmh:Annotated[Number,Field(ge=0,le=400)]
class Vehicles(Input):
    engine_template:Text
    train_template:Text
    category_template:Text
    engine_name:Text
    category_name:Text
    train_names:Annotated[list[Text],Field(min_length=1,max_length=1000)]
    use_template_physics:StrictBool
    inherit_conflict_definitions:StrictBool
    train_parameters:TrainParameters
class Assignment(Input):
    train:Text
    itinerary:Text
class Schedule(Input):
    assignments:Annotated[list[Assignment],Field(min_length=1,max_length=1000)]
    periods:Annotated[StrictInt,Field(ge=1,le=1000)]
    interval_s:Annotated[StrictInt,Field(ge=1,le=86400)]
    phase_s:Annotated[StrictInt,Field(ge=0,le=86400)]
    start_s:Annotated[StrictInt,Field(ge=0,le=366*86400)]
    window_end_s:Annotated[StrictInt,Field(ge=1,le=366*86400)]
    free_flow_multiplier:Annotated[Number,Field(ge=1,le=10)]
    leg_slack_s:Annotated[StrictInt,Field(ge=0,le=86400)]
    course_prefix:Annotated[StrictStr,Field(min_length=1,max_length=190,pattern=r'^[ -~]+$')]
class Visit(Input):
    station_sign:Text
    absolute_seconds:Annotated[StrictInt,Field(ge=0,le=366*86400)]
class CoursePlan(Input):
    course_id:Text
    train:Text
    itinerary:Text
    visits:Annotated[list[Visit],Field(min_length=2,max_length=10000)]
class RunConfiguration(Input):
    execution_root:Annotated[StrictStr,Field(min_length=1,max_length=1000)]
    path_style:Literal['windows','posix']
    run_filename:Annotated[StrictStr,Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\.run$')]
    output_directory:Annotated[StrictStr,Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')]
    start_day:Annotated[StrictInt,Field(ge=0,le=24854)]
    start_time:Annotated[StrictStr,Field(pattern=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$')]
    stop_day:Annotated[StrictInt,Field(ge=0,le=24854)]
    stop_time:Annotated[StrictStr,Field(pattern=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$')]
    step:Annotated[StrictStr,Field(min_length=1,max_length=30)]
class GenerateOperatingNetwork(GenerateNetwork):
    sources:Sources
    station_profile:Literal['point_only','terminal_area']='point_only'
    terminal_profile:TerminalProfile|None=None
    stations:Annotated[list[Station],Field(min_length=1,max_length=1000)]|None=None
    vehicles:Vehicles
    course_template_id:Text
    timetable_template_key:Text
    speed_type:Text
    operating_prefix:Annotated[StrictStr,Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')]
    run_configuration:RunConfiguration|None=None
    schedule:Schedule|None=None
    plan:Annotated[list[CoursePlan],Field(min_length=1,max_length=10000)]|None=None
    @model_validator(mode='after')
    def operating_contract(self):
        if self.station_profile=='point_only':
            if self.terminal_profile is not None or self.sources.connection_template is not None:raise ValueError('Point-only profile refuses terminal areas/stops/chains/Connection source')
            if not self.stations:raise ValueError('Point-only stations required')
            if (self.schedule is None)==(self.plan is None):raise ValueError('Exactly one explicit schedule or plan required')
            names=[x.sign for x in self.stations]
            if len(names)!=len(set(names)):raise ValueError('Duplicate station sign')
            if not all(s.timing_point for s in self.stations):raise ValueError('This profile supports explicit paired type2 StationVertex pass references only')
        else:
            if self.terminal_profile is None or self.sources.connection_template is None:raise ValueError('Terminal profile and SHA-bound native Connection template required')
            if self.stations is not None or self.plan is not None or self.schedule is not None:raise ValueError('Terminal profile refuses point-only stations/plan/schedule; use its explicit areas, five-visit plans and chains')
        if len(set(self.vehicles.train_names))!=len(self.vehicles.train_names):raise ValueError('Duplicate Train definition')
        if self.schedule and self.schedule.periods*len(self.schedule.assignments)>10000:raise ValueError('Schedule exceeds 10000 courses')
        filenames=[self.document_name+'.opentrack',self.catalog_filename]+[self.operating_prefix+'.'+x for x in ('depot','trains','stations','courses','timetable')]
        if self.run_configuration:filenames += [self.run_configuration.run_filename,self.run_configuration.output_directory]
        if len(set(x.casefold() for x in filenames))!=len(filenames):raise ValueError('Case-insensitive output filename collision')
        return self

class OperatingGeneration(NetworkGeneration):
    def generate(self,args):
        inputs={};blobs={};sources={}
        for key in Sources.model_fields:
            spec=getattr(args.sources,key)
            if spec is None:continue
            if key=='run_template':path=self.path(spec.path);blob=self.secure_bytes(path)
            else:path,blob,_,_=self.read(spec.path)
            if sha(blob)!=spec.sha256:raise APIError('SOURCE_CHANGED','Explicit source SHA mismatch',key)
            if path in inputs and inputs[path]!=blob:raise APIError('SOURCE_CHANGED','Shared source changed during reads',key)
            inputs[path]=blob;blobs[key]=blob;sources[key]={'path':spec.path,'sha256':spec.sha256}
        
        
        
        if not args.preview_only:
            with self.parent_fd(self.path(args.target_directory)) as (parent,name):
                try:os.stat(name,dir_fd=parent,follow_symlinks=False)
                except FileNotFoundError:pass
                else:raise APIError('TARGET_EXISTS','Bundle target exists; nothing overwritten')
        try:members,report=self.compose_operating(args,blobs)
        except (ValueError,TypeError,IndexError,KeyError,OverflowError) as exc:raise APIError('CURRENT_OPERATING_GENERATION',str(exc)[:500]) from exc
        manifest={'format':'opentrack-current-network-operating-archives-v1','station_profile':args.station_profile,'sources':sources,'files':{n:{'sha256':sha(b),'bytes':len(b)}for n,b in members.items()},
            'scope':'new single-document network and six catalogs, paired type2 pass StationVertices, planned services; no runtime configuration or execution',
            'complete_relocated_project':False,'native_simulation_executed':False,'report':report}
        result={'preview_only':args.preview_only,'saved':False,'bundle_type':'new network plus six operating catalogs; no complete runtime Project',
            'manifest':manifest,'report':report,'fresh_archive_reload_verified':True,'native_application_started':False,'native_simulation_executed':False}
        if args.station_profile=='terminal_area':
            manifest['scope']='explicit terminal-area graph, final-occurrence stop flags and native reciprocal Connection records; static configuration only'
            result['bundle_type']='generated terminal-area operating archives; physical stops/circulation unverified'
        validators={};directories=[]
        if args.run_configuration:
            cfg=args.run_configuration;archives={n:b for n,b in members.items() if n!=cfg.run_filename}
            validators[cfg.run_filename]=lambda blob:run_bundle.verify_manifest(blob,archives,report['run_binding'])
            directories=[cfg.output_directory]
            manifest['scope']='network, six operating catalogs and explicit execution-root run bindings; native runtime/defaults not verified'
            result['bundle_type']='generated network, planned operating data and bound run; native execution unverified'
        return self.publish_bundle(inputs=inputs,members=members,manifest=manifest,result=result,target_directory=args.target_directory,member_validators=validators,empty_directories=directories)

    @staticmethod
    def compose_operating(args,blobs):
        if args.station_profile=='terminal_area':
            from .terminal_generation_compose import compose_terminal
            return compose_terminal(args,blobs)
        members,network=NetworkGeneration.compose(args,blobs)
        filename=args.document_name+'.opentrack';ids=network['topology']['vertex_end_ids']
        specs=[]
        for station in args.stations:
            spec=station.model_dump();spec['end_ids']=[]
            for ref in spec.pop('ends'):
                if ref['vertex'] not in ids:raise ValueError('Unknown station vertex')
                spec['end_ids'].append(ids[ref['vertex']][ref['side']])
            specs.append(spec)
        doc,station_blob,station_report=stations.bind_stations(members[filename],specs)
        vehicle,vehicle_report=vehicles.generate_vehicle_catalogs(blobs['depot_template'],blobs['trains_template'],args.vehicles.model_dump())
        dest=members[args.catalog_filename]
        speed_index=str(speed_preferences.index_for_course(blobs['run_template'],args.speed_type))
        depot,_=w.load_next_compatible(vehicle['depot']);cap=c.engine_items(depot)[0].contents[7].value
        assignments=[]
        if args.schedule:
            s=args.schedule
            names=[a.train for a in s.assignments]
            if len(names)!=len(set(names)) or set(names)!=set(args.vehicles.train_names):raise ValueError('Each new Train definition needs exactly one schedule assignment')
            plan=[]
            for index,a in enumerate(s.assignments):
                trace=operations.station_sequence(doc,dest,a.itinerary,args.document_name,details=True,speed_index=speed_index,maximum_vehicle_speed_kmh=cap)
                if len(trace)<2:raise ValueError('Service needs at least two ordered station occurrences')
                offsets=[0]
                for previous,current in zip(trace,trace[1:]):
                    duration=math.ceil((current['minimum_edge_time_s']-previous['minimum_edge_time_s'])*s.free_flow_multiplier)+s.leg_slack_s
                    if duration<=0:raise ValueError('Every planned visit interval must be positive')
                    offsets.append(offsets[-1]+duration)
                if s.periods>1 and offsets[-1]>=s.interval_s:raise ValueError('Repeated services of same Train definition overlap schedule period')
                for period in range(s.periods):
                    start=s.start_s+period*s.interval_s+index*s.phase_s
                    if start+offsets[-1]>s.window_end_s:raise ValueError('Service exceeds explicit operating window')
                    plan.append({'course_id':f'{s.course_prefix}_{period:03}_{index+1:02}','train':a.train,'itinerary':a.itinerary,'visits':[{'station_sign':t['station_sign'],'absolute_seconds':start+offset}for t,offset in zip(trace,offsets)]})
                assignments.append({'train':a.train,'itinerary':a.itinerary,'station_sequence':[t['station_sign']for t in trace],'visit_offset_seconds':offsets,'minimum_free_flow_seconds':trace[-1]['minimum_edge_time_s']-trace[0]['minimum_edge_time_s']})
        else:plan=[x.model_dump()for x in args.plan]
        services,service_report=operations.generate_service_catalogs({'courses_template':blobs['courses_template'],'timetable_template':blobs['timetable_template'],'trains':vehicle['trains'],'depot':vehicle['depot'],'stations':station_blob,'document':doc,'dest':dest,'run_template':blobs['run_template']},
            course_template_id=args.course_template_id,timetable_template_key=args.timetable_template_key,document_name=args.document_name,plan=plan,speed_type=args.speed_type)
        members[filename]=doc
        members.update({args.operating_prefix+'.'+key:value for key,value in {**vehicle,**services,'stations':station_blob}.items()})
        report={'network':network,'station_binding':station_report,'vehicle_types':vehicle_report,'services':service_report,'schedule':args.schedule.model_dump()if args.schedule else None,'assignments':assignments,
            'planned_window_seconds':[min(v['absolute_seconds']for p in plan for v in p['visits']),max(v['absolute_seconds']for p in plan for v in p['visits'])],
            'counts':{**network['counts'],'stations':len(args.stations),'train_definitions':len(args.vehicles.train_names),'courses':len(plan),'timetable_rows':sum(len(p['visits'])for p in plan)},
            'run_file_generated':False,'run_train_types_required':speed_preferences.read_train_types(blobs['run_template']),
            'physical_fleet_circulation_proven':False,'platform_stops_supported':False,'calibrated_vehicle_dynamics':False,'native_simulation_executed':False,'complete_project_validated':False}
        if args.run_configuration:
            cfg=args.run_configuration
            catalog_paths={key:args.operating_prefix+'.'+key for key in ('depot','trains','stations','courses','timetable')}
            catalog_paths['dest']=args.catalog_filename
            configuration=cfg.model_dump(exclude={'run_filename'})
            run,run_report=run_bundle.build_run(members,catalog_paths=catalog_paths,document_paths=[filename],train_types=speed_preferences.read_train_types(blobs['run_template']),**configuration)
            static=run_bundle.verify_archive_bindings(run,members,catalog_paths=catalog_paths,document_paths=[filename])
            run_bundle.verify_manifest(run,members,run_report)
            members[cfg.run_filename]=run
            report.update(run_file_generated=True,run_binding=run_report,run_archive_bindings=static,output_directory_created_on_save=cfg.output_directory,execution_root_verified=False,complete_runtime_configuration=False)
        return members,report

def tool_definitions(root):
    service=OperatingGeneration(root)
    return [('opentrack_generate_current_operating_archives','Generate from an explicit network spec new infrastructure and six operating catalogs in one fresh-directory transaction: paired type2 StationVertex pass references, new vehicle definitions from explicitly accepted physical type templates, Courses and planned Timetables. Uses exact run-scoped speed-type names and Edge/vehicle speed lower bounds. Preview by default. Optionally bind a minimal run file to an explicit execution root and atomically create its empty output directory. Default point_only remains unchanged. Explicit terminal_area selects separate ordinary area members/type2 references, final-only stops and fresh native reciprocal chains with a SHA-bound Connection source; static configuration only. Runtime defaults, general platforms, physical-fleet circulation and native simulation remain unverified.',GenerateOperatingNetwork,service.generate,False,False)]
