"""Pure operational input compiler using the production archive input contracts.

Produces actual JSON and timetable data, not archives or simulated run results.
All external identifiers are caller assertions, never native evidence.
"""
import csv
import hashlib
import io
import json
from pydantic import Field
from . import models as m
from .errors import APIError

ORDER = ('stations','engines','categories','formations','routes','paths','itineraries','courses','patterns','timetables')
KEYS = {'stations':'sign','engines':'name','categories':'name','formations':'name','routes':'name','paths':'name','itineraries':'name','courses':'course_id','timetables':'course_id'}

class ExternalCatalog(m.Input):
    engines: list[m.ArchiveName] = Field(default_factory=list,max_length=10000)
    categories: list[m.ArchiveName] = Field(default_factory=list,max_length=10000)
    formations: list[m.ArchiveName] = Field(default_factory=list,max_length=10000)
    stations: list[str] = Field(default_factory=list,max_length=10000)
    routes: list[m.RouteSelector] = Field(default_factory=list,max_length=10000)
    paths: list[m.ArchiveName] = Field(default_factory=list,max_length=10000)
    itineraries: list[m.ArchiveName] = Field(default_factory=list,max_length=10000)
    courses: list[m.CourseId] = Field(default_factory=list,max_length=10000)
    speed_types: list[m.ArchiveName] = Field(default_factory=list,max_length=1000)

class PrepareOperations(m.Input):
    operations: m.GenerateOperations
    external_catalog: ExternalCatalog = Field(default_factory=ExternalCatalog)
    previous_operations: m.GenerateOperations | None = None
    expected_previous_sha256: str | None = Field(default=None,pattern=r'^[a-f0-9]{64}$')
    include_csv: bool = False
    offset: int = Field(default=0,ge=0)
    limit: int = Field(default=50,ge=1,le=200)


def absolute(value, day):
    if value is None:return None
    h, minute, second=map(int,value.split(':'))
    return day*86400+h*3600+minute*60+second


def split(value):
    day, second=divmod(value,86400)
    if not -366 <= day <= 366:raise APIError('TIME_OUT_OF_RANGE','Expanded timetable exceeds supported day offsets [-366, 366].')
    return day,f'{second//3600:02}:{second//60%60:02}:{second%60:02}'


def expand_pattern(pattern):
    """Shared by native generation and pure preparation: identical CourseSpec data."""
    if pattern.stops[0].departure_offset_s!=0:raise APIError('PATTERN_ORIGIN','First stop departure_offset_s must be 0.')
    common={k:v for k,v in pattern.model_dump().items() if k in m.CourseSpec.model_fields and k not in {'course_id','stops'}}
    base=absolute(pattern.first_departure,pattern.first_departure_day_offset)
    for index in range(pattern.count):
        stops=[]
        for stop in pattern.stops:
            values=stop.model_dump(exclude={'arrival_offset_s','departure_offset_s'})
            for key in ('arrival','departure'):
                offset=getattr(stop,key+'_offset_s')
                values[key+'_day_offset'],values[key]=(0,None) if offset is None else split(base+index*pattern.interval_s+offset)
            if pattern.keep_interval_reference and index and values['interval_reference_course_id'] is None:
                values['interval_reference_course_id']=pattern.id_prefix+str(pattern.first_number)
                values['interval_offset_s']=index*pattern.interval_s
            stops.append(values)
        yield m.CourseSpec(**common,course_id=pattern.id_prefix+str(pattern.first_number+index*pattern.number_step),stops=stops)


def validate_timetable(table):
    """Pure parity checks from OperationalData.set_timetable; no archive access."""
    if table.stops[0].departure is None or table.stops[-1].arrival is None:
        raise APIError('TIMETABLE_ENDPOINT','First stop requires departure and last stop requires arrival.',table.course_id)
    previous=None
    for index,stop in enumerate(table.stops):
        owner={'course':table.course_id,'index':index}
        arrival=absolute(stop.arrival,stop.arrival_day_offset)
        departure=absolute(stop.departure,stop.departure_day_offset)
        if arrival is None and departure is None:raise APIError('TIMETABLE_TIME','Each generated stop needs at least one time.',owner)
        for stamp in (arrival,departure):
            if stamp is not None:
                if previous is not None and stamp<previous:raise APIError('TIMETABLE_ORDER','Arrival/departure times must be chronological; use explicit day offsets across midnight.',owner)
                previous=stamp
        if stop.stop_at_station and arrival is not None and departure is not None and departure-arrival<stop.dwell_s:
            raise APIError('TIMETABLE_DWELL','Scheduled dwell is shorter than dwell_s.',owner)


def canonical(operations):
    return operations.model_dump(mode='json')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def check_supported(operations):
    unsupported=[key for key in type(operations).model_fields if key not in {*ORDER,'project','run_file','label'} and getattr(operations,key)]
    if unsupported:raise APIError('PREPARATION_SCOPE','Pure preparation currently supports definition batches, service patterns and explicit timetables only. Ordered maintenance/import commands require native validation.',unsupported)
    if not any(getattr(operations,key) for key in ORDER):raise APIError('EMPTY_GENERATION','Supply at least one entity or pattern.')


def prepare(args):
    operations=args.operations;check_supported(operations)
    course_count=len(operations.courses)+sum(p.count for p in operations.patterns)
    row_count=sum(len(c.stops) for c in operations.courses)+sum(p.count*len(p.stops) for p in operations.patterns)+sum(len(t.stops) for t in operations.timetables)
    connection_count=sum(len(s.connections) for c in [*operations.courses,*operations.timetables] for s in c.stops)+sum(p.count*sum(len(s.connections) for s in p.stops) for p in operations.patterns)
    if course_count>1000 or row_count>10000 or connection_count>10000 or sum(len(getattr(operations,k)) for k in ORDER)>1000:
        raise APIError('GENERATION_SIZE','Batch supports at most 1000 definitions/Courses, 10000 rows and 10000 connections.')
    courses=[*operations.courses,*(c for pattern in operations.patterns for c in expand_pattern(pattern))]
    requested_tables=[*courses,*operations.timetables]
    
    tables_by_course={table.course_id:table for table in requested_tables}
    catalogs={k:set(getattr(args.external_catalog,k)) for k in KEYS if k not in {'routes','timetables'}}
    catalogs['speed_types']=set(args.external_catalog.speed_types)
    indices={}; changes=[]
    for group in KEYS:
        rows=courses if group=='courses' else getattr(operations,group)
        names=[getattr(row,KEYS[group]) for row in rows]
        if len(names)!=len(set(names)):raise APIError('DUPLICATE_IDENTIFIER','Duplicate identifier in generated batch.',{'group':group,'identifiers':names})
        indices[group]={name:row for name,row in zip(names,rows)}
        if group in catalogs:
            for name,row in zip(names,rows):
                exists=name in catalogs[group]
                if exists and not getattr(row,'replace_existing',False):raise APIError('ENTITY_EXISTS','External catalog already contains identifier; set replace_existing explicitly.',{'group':group,'name':name})
                changes.append({'group':group,'id':name,'action':'replace' if exists else 'create'})
            catalogs[group].update(names)
        else:
            changes.extend({'group':group,'id':name,'action':'set' if group=='timetables' else 'create'} for name in names)
    references=[]
    def require(group,name,owner):
        if name not in catalogs[group]:raise APIError('UNRESOLVED_REFERENCE','Reference absent from generated and caller-supplied external catalogs.',{'owner':owner,'catalog':group,'reference':name})
        references.append({'owner':owner,'catalog':group,'reference':name})
    for group in ('engines','categories','formations'):
        available=set(getattr(args.external_catalog,group))
        for entity in getattr(operations,group):
            if entity.template_name and entity.template_name not in available:
                raise APIError('TEMPLATE_ORDER','Template must exist before its dependent definition.',{'group':group,'entity':entity.name,'template':entity.template_name})
            available.add(entity.name)
    for formation in operations.formations:
        for unit in formation.engines:require('engines',unit.engine_name,'formation:'+formation.name)
        if formation.category:require('categories',formation.category,'formation:'+formation.name)
        count=sum(unit.count for unit in [*formation.engines,*formation.trailers])
        positions=[n for unit in [*formation.engines,*formation.trailers] for n in unit.positions or []]
        if sum(u.count for u in formation.engines)>64 or count>1024 or len(positions)!=len(set(positions)) or any(n>count for n in positions):
            raise APIError('FORMATION_POSITIONS','Powered/trailer counts or explicit positions are invalid.',formation.name)
    for station in operations.stations:
        if station.end_ids and not station.document:raise APIError('STATION_DOCUMENT_REQUIRED','Station End assignments require a document.',station.sign)
    route_keys={(r.document,r.start_id,r.route_id,r.name) for r in args.external_catalog.routes}
    for route in operations.routes:
        if route.name in {r.name for r in args.external_catalog.routes}:
            raise APIError('ENTITY_EXISTS','A Route name already exists in the caller-supplied catalog.',route.name)
        start=route.nodes[0];route_keys.add((start.document,start.end_id,None,route.name))
    for path in operations.paths:
        for route in path.routes:
            if (route.document,route.start_id,route.route_id,route.name) not in route_keys:
                raise APIError('UNRESOLVED_REFERENCE','Route selector must exactly match a generated start End or caller-supplied route.',{'path':path.name,'route':route.model_dump()})
    for itinerary in operations.itineraries:
        for path in itinerary.paths:require('paths',path,'itinerary:'+itinerary.name)
    available_courses=set(args.external_catalog.courses)
    for course in courses:
        if course.template_id and course.template_id not in available_courses:
            raise APIError('TEMPLATE_ORDER','Course template must exist before its dependent definition.',{'course':course.course_id,'template':course.template_id})
        available_courses.add(course.course_id)
        require('formations',course.train,'course:'+course.course_id)
        require('speed_types',course.speed_type,'course:'+course.course_id)
        for name in course.itineraries:require('itineraries',name,'course:'+course.course_id)
        if course.template_id:require('courses',course.template_id,'course-template:'+course.course_id)
    for table in requested_tables:validate_timetable(table)
    preview=[]
    for table in requested_tables:
        require('courses',table.course_id,'timetable:'+table.course_id)
        validate_timetable(table)
        for index,stop in enumerate(table.stops):
            owner=f'{table.course_id}:{index}';require('stations',stop.station_sign,owner)
            arrival=absolute(stop.arrival,stop.arrival_day_offset);departure=absolute(stop.departure,stop.departure_day_offset)
            if stop.interval_reference_course_id:require('courses',stop.interval_reference_course_id,owner)
            for connection in stop.connections:
                require('courses',connection.target_course_id,owner)
                if connection.target_station_sign:require('stations',connection.target_station_sign,owner)
                target=tables_by_course.get(connection.target_course_id)
                sign=connection.target_station_sign or stop.station_sign
                if target and sign not in {s.station_sign for s in target.stops}:raise APIError('CONNECTION_STATION','Target course has no stop at the connection station.',{'owner':owner,'target':connection.target_course_id,'station':sign})
            if tables_by_course[table.course_id] is not table:continue
            preview.append({'course_id':table.course_id,'index':index,'station_sign':stop.station_sign,'arrival':stop.arrival,'departure':stop.departure,'arrival_day_offset':stop.arrival_day_offset,'departure_day_offset':stop.departure_day_offset,'arrival_absolute_s':arrival,'departure_absolute_s':departure})
    normalized=canonical(operations); sha=digest(normalized)
    difference=None
    if args.expected_previous_sha256 and args.previous_operations is None:raise APIError('BASELINE_REQUIRED','expected_previous_sha256 requires previous_operations.')
    if args.previous_operations is not None:
        before=canonical(args.previous_operations);before_sha=digest(before)
        if args.expected_previous_sha256 and args.expected_previous_sha256!=before_sha:raise APIError('BASELINE_CHANGED','Previous operations hash differs from expected value.',{'actual':before_sha})
        difference={'previous_sha256':before_sha,'unchanged':before_sha==sha,'changed_sections':[k for k in normalized if normalized[k]!=before[k]]}
    csv_text=None
    if args.include_csv:
        stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=list(preview[0]) if preview else ['course_id','station_sign'])
        writer.writeheader();writer.writerows(preview);csv_text=stream.getvalue()
    return {'evidence_level':'schema_and_input_reference_validation','native_simulation_verified':False,'native_archive_created':False,
        'native_apply_performed':False,'prepared_sha256':sha,'operations':normalized,
        'dependency_order':[k for k in ORDER if getattr(operations,k)],'entity_changes':changes,'difference':difference,
        'counts':{'courses':course_count,'timetable_rows':row_count,'final_timetable_rows':len(preview),'connections':connection_count,'checked_references':len(references)},
        'timetable':{'items':preview[args.offset:args.offset+args.limit],'total_count':len(preview),'offset':args.offset,'has_more':args.offset+args.limit<len(preview)},
        'timetable_csv':csv_text,'warnings':['External catalog identifiers and speed types are caller assertions, not verified project evidence.',
            'Physical topology, route continuity, native templates, braking/traction adequacy and simulation acceptance require separate native validation.',
            'Preparation is pure and deterministic; it does not reserve identifiers or make native apply idempotent.'],
        'units':{'mass':'t','length':'m','speed':'km/h','force':'kN','power':'kW','time':'seconds plus explicit signed day offsets'}}


def tool_definitions():
    return [('opentrack_prepare_operations','Prepare real GenerateOperations JSON without archive dependencies: production defaults, bounded pattern expansion, cross-entity references, cross-midnight chronology, CSV preview and deterministic baseline diff. No archive writes or simulation; external catalog is caller-asserted.',PrepareOperations,prepare)]
