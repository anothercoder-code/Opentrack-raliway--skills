"""Original RailML 2.2 timetable writer from saved data; no native execution."""
from collections import Counter,defaultdict
from datetime import datetime
import math
import re

from .archive import APIError,w
from .course_lifecycle import string_slot
from .models import RailMLTimetableOptions
from .railml_export import NAMESPACE,native_id,xml_text
from .railml_values import REAL,checked_int,f32,int_text,native_truncate
from opentrack_station_schema import station_items

MAX_ROWS=10000
MAX_BYTES=2000000


def wait_seconds(value):
    """Reviewed timeStringToSecond:/isTimeString:, including the 60-second quirk."""
    if value is None or value=='HH:MM:SS':return -1
    parts=value.split(':')
    if len(parts) not in [2,3] or any(len(part)!=2 for part in parts):return -1
    numbers=[int_text(part) for part in parts]+([0] if len(parts)==2 else [])
    if not (0<=numbers[0]<24 and 0<=numbers[1]<60 and 0<=numbers[2]<=60):return -1
    return numbers[0]*3600+numbers[1]*60+numbers[2]%60


def filtered_station(value,options):
    if options is None:return value
    if options.uppercase:
        if not value.isascii():raise APIError('TIMETABLE_RAILML_FILTER_ENCODING','Uppercase station filtering is audited for ASCII station signs only.')
        value=value.upper()
    if len(value)>=options.replace_first:value=options.first_string+value[options.replace_first:]
    if len(value)>=options.replace_last:value=value[:len(value)-options.replace_last]+options.last_string
    while len(value)>1 and value.endswith(' '):value=value[:-1]
    return value


def double_prefix(value):
    if re.match(r'^\s*[+-]?(?:nan|inf)',value,re.I):return math.nan
    match=REAL.match(value);return float(match.group(1)) if match else 0.


def formation_metrics(train,engines,warnings):
    totals=[]
    for field in ['length_m','mass_t']:
        powered=0;trailers=0
        for name in train['engines']:
            if name not in engines:
                if field=='length_m':warnings.append({'kind':'NATIVE_MISSING_ENGINE_CONTRIBUTES_ZERO','formation':train['name'],'engine':name})
                continue
            value=engines[name][field]
            if not isinstance(value,int):raise APIError('TIMETABLE_RAILML_METRICS','Original vehicle dimensions require integer archive fields.',name)
            powered=checked_int(powered+value)
        for trailer in train['trailers']:
            value=trailer[field]
            if not isinstance(value,int):raise APIError('TIMETABLE_RAILML_METRICS','Original Trailer dimensions require integer archive fields.',train['name'])
            trailers=checked_int(trailers+value)
        if field=='mass_t':trailers=max(0,trailers)
        if abs(powered)+abs(trailers)>16777215:raise APIError('TIMETABLE_RAILML_METRICS_PRECISION','Summary export is bounded to exact float32 integer dimensions until wide native return/conversion behavior is recovered.',train['name'])
        value=native_truncate(f32(f32(powered)+f32(trailers)))
        totals.append(value)
    return totals


def render_railml(project,rows,args):
    options=args.railml or RailMLTimetableOptions();warnings=[];identifiers=[];references=[];declarations=defaultdict(set);lines=[]
    def warning(kind,**details):warnings.append({'kind':kind,**details})
    def caption(value):
        if any(c in value for c in '\t\r\n'):warning('NATIVE_XML_ATTRIBUTE_WHITESPACE_NORMALIZATION',text=value[:80])
        return xml_text(value)
    def identifier(prefix,value,declare=False):
        result=native_id(prefix+value)
        if declare:
            identifiers.append(result)
            kind={'ocp-':'station','fo-':'formation','tr-':'train','tp-':'train_part','tg-':'train_group'}.get(prefix,'section')
            declarations[kind].add(result)
        return result
    def reference(kind,value):references.append((kind,value));return value
    def emit(indent,text):lines.append('\t'*indent+text)
    if len(rows)>MAX_ROWS or sum(len(r['connections']) for r in rows)>MAX_ROWS:raise APIError('TIMETABLE_RAILML_SIZE','One timetable export supports at most 10000 rows and connections.')
    stations=station_items(project.data['stations']);stock=project.catalog('trains');engine_records=project.catalog('engines');course_records=project.catalog('services')
    if len(stations)>MAX_ROWS or len(stock)>MAX_ROWS:raise APIError('TIMETABLE_RAILML_SIZE','One export supports at most 10000 Stations and formations.')
    courses={};engines={}
    for record in course_records:courses.setdefault(record['course_id'],record)
    for record in engine_records:engines.setdefault(record['name'],record)
    for field,records in [('course_id',course_records),('name',engine_records)]:
        for name,count in Counter(r[field] for r in records).items():
            if count>1:warning('NATIVE_FIRST_CATALOG_MATCH',field=field,name=name,definitions=count)
    all_rows=sorted(project.catalog('timetable'),key=lambda row:(row['course_id'],row['index']));raw=project.table();groups=defaultdict(list)
    for row in rows:groups[row['course_id']].append(row)
    selected={};skipped=[]
    for cid,items in groups.items():
        if any(row['index']!=index or row['last_index']!=len(items)-1 for index,row in enumerate(items)):raise APIError('TIMETABLE_RAILML_INDEX','Export requires contiguous Course rows and consistent last indices.',cid)
        if options.only_active and not courses.get(cid,{}).get('enabled',False):skipped.append({'course_id':cid,'reason':'inactive_or_missing_definition'});continue
        filtered=[row for row in items if not options.existing_stations_only or row['station_sign'] in stations]
        if not filtered:skipped.append({'course_id':cid,'reason':'no_existing_station'});continue
        selected[cid]=filtered
        if len(filtered)!=len(items):warning('NATIVE_EXISTING_STATION_FILTER_REMOVED_ROWS',course_id=cid,removed=len(items)-len(filtered))
    dataset=options.dataset_name if options.dataset_name is not None else project.project.name
    if options.dataset_name is None:warning('DATASET_NAME_FROM_PROJECT',project_name=dataset)
    emit(0,'<?xml version="1.0" encoding="ISO-8859-1"?>')
    emit(0,'<railml version="2.2" xmlns="'+NAMESPACE+'" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="'+NAMESPACE+' http://schemas.railml.org/2013/railML-2.2/railML.xsd">')
    emit(1,'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">');emit(2,'<dc:source>OpenTrack (http://www.opentrack.ch)</dc:source>')
    emit(2,'<dc:date>'+caption(options.metadata_date if options.metadata_date is not None else datetime.now().strftime('%a %b %d %H:%M:%S %Y'))+'</dc:date>');emit(1,'</metadata>')
    emit(1,'<infrastructure id="'+identifier('infrastructure-',dataset,True)+'" version="2.2">');emit(2,'<operationControlPoints>')
    for sign,obj in stations.items():
        if string_slot(obj,1)!=sign:raise APIError('TIMETABLE_RAILML_STATION','Station dictionary key and saved stationSign disagree.',sign)
        transformed=filtered_station(sign,options.station_filter);value=caption(transformed)
        if not transformed.strip():warning('EMPTY_FILTERED_STATION_SIGN',station=sign)
        attrs=' id="'+identifier('ocp-',transformed,True)+'" abbrevation="'+value+'" code="'+value+'" name="'+value+'" description="'+caption(string_slot(obj,2))+'"'
        if obj.clazz.version!=3 or len(obj.contents)!=10:raise APIError('TIMETABLE_RAILML_STATION_VERSION','Station geographic export requires the current v3 record.',sign)
        longitude=string_slot(obj,8);latitude=string_slot(obj,9);geo=bool(longitude and latitude) and -180<=double_prefix(longitude)<=180 and -90<=double_prefix(latitude)<=90
        if geo:
            emit(3,'<ocp'+attrs+'>');emit(4,'<geoCoord coord="'+caption(latitude)+' '+caption(longitude)+'"/>');emit(3,'</ocp>')
            if not REAL.match(latitude) or not REAL.match(longitude):warning('NATIVE_NONNUMERIC_COORDINATE_TEXT_PRESERVED',station=sign)
        else:emit(3,'<ocp'+attrs+'/>')
    emit(2,'</operationControlPoints>');emit(1,'</infrastructure>')
    emit(1,'<rollingstock id="'+identifier('rollingstock-',dataset,True)+'" version="2.2">');emit(2,'<formations>')
    for train in stock:
        length,weight=formation_metrics(train,engines,warnings)
        emit(3,'<formation id="'+identifier('fo-',train['name'],True)+'" name="'+caption(train['name'])+'" length="'+str(length)+'" weight="'+str(weight)+'"/>')
    emit(2,'</formations>');emit(1,'</rollingstock>')
    emit(1,'<timetable id="'+identifier('timetable-',dataset,True)+'" version="2.2">');emit(2,'<trainParts>')
    emitted_rows=connections=times=0
    planned=options.planned or not (options.published or options.calculated)
    def time_block(row,scope,actual=False):
        attrs=' scope="'+scope+'"'
        for field,label in [('arrival','arrival'),('departure','departure')]:
            key=('actual_' if actual else '')+field;offset=row[key+'_day_offset'];value=row[key]
            if offset>0:attrs+=' '+label+'Day="'+str(offset)+'"'
            elif offset<0:warning('NATIVE_NEGATIVE_DAY_OMITTED',key=row['key'],field=key,day=offset)
            if value!='HH:MM:SS':attrs+=' '+label+'="'+caption(value)+'.0"'
        emit(6,'<times'+attrs+'/>')
    for cid,items in selected.items():
        course=courses.get(cid,{});additional=course.get('train_number') or cid;description=course.get('description','')
        attrs=' id="'+identifier('tp-',cid,True)+'" trainNumber="'+caption(cid)+'"'
        if additional:attrs+=' additionalTrainNumber="'+caption(additional)+'"'
        if description:attrs+=' description="'+caption(description)+'"'
        emit(3,'<trainPart'+attrs+' processStatus="planned">')
        if course.get('train'):emit(4,'<formationTT formationRef="'+reference('formation',identifier('fo-',course['train']))+'"/>')
        emit(4,'<ocpsTT>')
        for row in items:
            emitted_rows+=1;station=filtered_station(row['station_sign'],options.station_filter)
            attrs=' ocpRef="'+reference('station',identifier('ocp-',station))+'"'
            if row['track_id']:attrs+=' trackInfo="'+caption(row['track_id'])+'"'
            emit(5,'<ocpTT'+attrs+' ocpType="'+('stop' if row['stop_at_station'] else 'pass')+'">')
            if planned:time_block(row,'scheduled');times+=1
            if options.published:time_block(row,'published');times+=1
            if options.calculated:
                if args.saved_actual=='as_valid':time_block(row,'calculated',True);times+=1
                else:warning('NATIVE_ACTUAL_VALIDITY_UNAVAILABLE',key=row['key'])
            if row['connections']:
                emit(6,'<connections>')
                for connection in row['connections']:
                    target=connection['target_course_id']
                    if options.only_active and not courses.get(target,{}).get('enabled',False):warning('NATIVE_INACTIVE_CONNECTION_OMITTED',key=row['key'],target=target);continue
                    attrs=' trainRef="'+reference('train',identifier('tr-',target))+'" trainPartRef="'+reference('train_part',identifier('tp-',target))+'"'
                    effective_station=connection['target_station_sign'] or connection['station_sign']
                    if effective_station and effective_station!=row['station_sign']:
                        broken=identifier('tp-',target);attrs+=' ocpRef="'+reference('station',broken)+'"';warning('NATIVE_CONNECTION_OCPREF_USES_COURSE_PART_ID',key=row['key'],target=target,ocp_ref=broken)
                    attrs+=' minConnTime="PT'+str(max(0,wait_seconds(connection['minimum_wait'])))+'S"'
                    maximum=wait_seconds(connection['maximum_wait'])
                    if maximum>0:attrs+=' maxConnTime="PT'+str(maximum)+'S"'
                    if connection.get('maximum_wait_is_nil'):warning('NATIVE_NIL_MAXIMUM_OMITTED',key=row['key'],target=target)
                    kind='meet' if connection['join'] and connection['split'] else 'join' if connection['join'] else 'split' if connection['split'] else 'none'
                    emit(7,'<connection'+attrs+' connOperation="'+kind+'"/>');connections+=1
                emit(6,'</connections>')
            dwell=string_slot(raw[row['key']],8)
            if dwell!='0':
                emit(6,'<stopDescription>');emit(7,'<stopTimes minimalTime="PT'+caption(dwell)+'S"/>');emit(6,'</stopDescription>')
            emit(5,'</ocpTT>')
        emit(4,'</ocpsTT>');emit(3,'</trainPart>')
    emit(2,'</trainParts>');emit(2,'<trains>')
    for cid in selected:
        attrs=' id="'+identifier('tr-',cid,True)+'" type="operational" trainNumber="'+caption(cid)+'" additionalTrainNumber="'+caption(cid)+'"'
        if courses.get(cid,{}).get('description'):attrs+=' description="'+caption(courses[cid]['description'])+'"'
        emit(3,'<train'+attrs+'>');emit(4,'<trainPartSequence sequence="1">');emit(5,'<trainPartRef ref="'+reference('train_part',identifier('tp-',cid))+'"/>');emit(4,'</trainPartSequence>');emit(3,'</train>')
    emit(2,'</trains>');interval_members=defaultdict(list)
    for row in all_rows:
        if row['index']==0 and row['interval_reference_course_id'] not in ['','0','-1']:interval_members[row['interval_reference_course_id']].append(row['course_id'])
    group_count=0
    for cid in selected:
        if not interval_members.get(cid):continue
        if not group_count:emit(2,'<trainGroups>')
        group_count+=1;attrs=' id="'+identifier('tg-',cid,True)+'"'
        if courses.get(cid,{}).get('description'):attrs+=' description="'+caption(courses[cid]['description'])+'"'
        emit(3,'<trainGroup'+attrs+'>');members=[cid]+[child for child in interval_members[cid] if child in selected]
        for index,member in enumerate(members,1):emit(4,'<trainRef sequence="'+str(index)+'" ref="'+reference('train',identifier('tr-',member))+'"/>')
        emit(3,'</trainGroup>')
    if group_count:emit(2,'</trainGroups>')
    emit(1,'</timetable>');emit(0,'</railml>')
    for value,count in Counter(identifiers).items():
        if count>1:warning('NATIVE_ID_COLLISION',id=value,count=count)
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9._-]*',value):warning('NATIVE_ID_NOT_NCNAME',id=value)
    for kind,value in sorted(set(references)):
        if value not in declarations[kind]:warning('UNRESOLVED_EXPORTED_REFERENCE',reference_kind=kind,target=value)
    warning('ORIGINAL_TIMETABLE_RAILML_OMISSIONS',fields=['Course itinerary/speed/spacing/acceleration/comment/kind','train vehicle curves/Category/braking/resistance; formations are summaries','row timing flag/delay/distribution/delta load and interval offsets','connection location/time-reference/dispatching distance','native actual validity and prepared Train state'])
    if options.calculated and args.saved_actual=='as_valid':warning('SAVED_ACTUAL_STRINGS_ASSUMED_VALID')
    content='\r\n'.join(lines)+'\r\n'
    try:size=len(content.encode('ascii'))
    except UnicodeEncodeError as error:raise APIError('TIMETABLE_RAILML_ENCODING','A saved caption cannot be represented by the audited escaped-ASCII writer.') from error
    if size>MAX_BYTES:raise APIError('TIMETABLE_RAILML_SIZE','RailML export exceeds 2 MB; select fewer Courses.')
    return content,warnings,{'rows':emitted_rows,'courses':len(selected),'connections':connections,'time_blocks':times,'train_groups':group_count,'stations':len(stations),'formations':len(stock),
        'skipped_courses':skipped,'railml_options':options.model_dump(),'saved_actual':args.saved_actual,'native_actual_validity_verified':False,'native_prepared_stock_state_verified':False,
        'xsd_validation_performed':False,'external_resources_resolved':False,'formation_metric_scope':'Saved unprepared Train dimensions with zero transient delta mass; exact integer magnitudes below 2^24. Wide native precision remains unverified.','catalog_order_note':'Course/index ordering is applied to a copy; station/formation order follows saved catalog enumeration, not certified native dictionary order.'}
