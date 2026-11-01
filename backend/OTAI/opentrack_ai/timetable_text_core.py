"""Pure original timetable exchange grammar; extracted from timetable_exchange.py.
No archive decoder, project filesystem, or native runtime dependency.
"""
import json
import re
from pydantic import TypeAdapter, ValidationError
from .errors import APIError

HEADER17=['courseID','intervalCourseID','timeToIntervalReference','stationIndex','stationSign','trackName','arrTimeDayOffset','arrTime','depTimeDayOffset','depTime','useDepTime','dwell','stopAtStation','meanDelay','Distribution','deltaMass']


HEADER16=HEADER17[:5]+HEADER17[6:15]


CONNECTION17=['courseID','connCourseID','stationIndex','connStationSign','connTimeType','connChangeTime','connMaxChangeTime','connectionType']


CONNECTION16=CONNECTION17[:4]+CONNECTION17[5:]


def flag(value,line,column):
    if value not in ['0','1']:raise APIError('TIMETABLE_EXCHANGE_VALUE','Boolean exchange columns must be 0 or 1.',{'line':line,'column':column})
    return value=='1'


def wait_seconds(value):
    from .models import TimeText
    TypeAdapter(TimeText).validate_python(value)
    h,m,s=map(int,value.split(':')); return h*3600+m*60+s


def parse_text(content):
    from .models import NewCourseId,TimetableStop,ConnectionSpec
    try:content.removeprefix('\ufeff').encode('ascii')
    except UnicodeEncodeError as error:raise APIError('TIMETABLE_EXCHANGE_ASCII','Original text exchange requires ASCII field data.') from error
    if len(content.encode('utf8'))>2000000:raise APIError('TIMETABLE_EXCHANGE_SIZE','Exchange content exceeds 2 MB.')
    if any((ord(c)<32 and c not in '\t\r\n') or ord(c)==127 for c in content) or re.search(r'\r(?!\n)',content):
        raise APIError('TIMETABLE_EXCHANGE_SEPARATOR','Only tabs and LF/CRLF record separators are allowed; other ASCII controls are forbidden.')
    content=content.removeprefix('\ufeff');rows={};connections=[];in_connections=False;widths=set()
    for number,line in enumerate(content.replace('\r\n','\n').split('\n'),1):
        if len(line)>4095:raise APIError('TIMETABLE_EXCHANGE_SIZE','A line exceeds the original Windows import buffer.',number)
        if not line.strip():continue
        if line.lstrip().startswith('//'):
            if re.match(r'^//\s*Connections\b',line.lstrip(),re.I):in_connections=True
            continue
        if len(line)>4095:raise APIError('TIMETABLE_EXCHANGE_SIZE','A line exceeds the original Windows import buffer.',number)
        columns=line.split('\t')
        try:
            if in_connections:
                if len(columns) not in [7,8]:raise ValueError('Connection records need 7 legacy or 8 current columns.')
                names=CONNECTION17 if len(columns)==8 else CONNECTION16;data=dict(zip(names,columns));cid=TypeAdapter(NewCourseId).validate_python(data['courseID']);target=TypeAdapter(NewCourseId).validate_python(data['connCourseID'])
                index=int(data['stationIndex']);code=int(data['connectionType'])
                if index<0 or not 0<=code<=63 or code&16 and code&32:raise ValueError('Unsupported connection location/flags or negative index.')
                
                values=dict(target_course_id=target,target_station_sign=data['connStationSign'] or None,
                    minimum_wait_s=wait_seconds(data['connChangeTime']),maximum_wait_s=None if data['connMaxChangeTime'] in ['','HH:MM:SS'] else wait_seconds(data['connMaxChangeTime']),
                    entry_connection=bool(code&16),dispo_connection=bool(code&32),join=bool(code&1),split=bool(code&2))
                if 'connTimeType' in data:values['time_reference_type']=int(data['connTimeType'])
                spec=ConnectionSpec(**values)
                connections.append((cid,index,spec));continue
            if len(columns) not in [14,16]:raise ValueError('Timetable records need 14 legacy or 16 current columns; intermediate formats require a separate audit.')
            widths.add(len(columns));data=dict(zip(HEADER17 if len(columns)==16 else HEADER16,columns));cid=TypeAdapter(NewCourseId).validate_python(data['courseID']);index=int(data['stationIndex'])
            if index<0:raise ValueError('stationIndex must be nonnegative.')
            reference=data['intervalCourseID'];reference=None if reference in ['','0','-1'] else TypeAdapter(NewCourseId).validate_python(reference)
            stop=TimetableStop(station_sign=data['stationSign'],track_id=data.get('trackName',''),arrival=None if data['arrTime'] in ['','HH:MM:SS'] else data['arrTime'],departure=None if data['depTime'] in ['','HH:MM:SS'] else data['depTime'],
                arrival_day_offset=int(data['arrTimeDayOffset'] or '0'),departure_day_offset=int(data['depTimeDayOffset'] or '0'),timing_station=flag(data['useDepTime'],number,'useDepTime'),
                dwell_s=int(data['dwell'] or '0'),stop_at_station=flag(data['stopAtStation'],number,'stopAtStation'),mean_delay_s=float(data['meanDelay'] or '0'),distribution_name=data['Distribution'],
                delta_mass_t=float(data.get('deltaMass','0') or '0'),interval_reference_course_id=reference,interval_offset_s=float(data['timeToIntervalReference'] or '0'))
            if (cid,index) in rows:raise ValueError('Duplicate Course/stationIndex record.')
            rows[(cid,index)]=stop
        except (ValueError,ValidationError) as error:raise APIError('TIMETABLE_EXCHANGE_VALUE','Invalid native text exchange record.',{'line':number,'reason':str(error)[:400]}) from error
    if not rows:raise APIError('TIMETABLE_EXCHANGE_EMPTY','The input has no timetable records.')
    if len(rows)>10000 or len(connections)>10000:raise APIError('GENERATION_SIZE','One exchange supports at most 10000 timetable rows and 10000 connections.')
    if len(widths)>1:raise APIError('TIMETABLE_EXCHANGE_FORMAT','Do not mix 1.6 and 1.7 timetable row layouts in one input.')
    for cid,index,spec in connections:
        if (cid,index) not in rows:raise APIError('TIMETABLE_EXCHANGE_OWNER','Each imported connection needs an owner timetable row in the input.',{'course_id':cid,'index':index})
        rows[(cid,index)].connections.append(spec)
    return rows,connections,('opentrack_17' if widths=={16} else 'opentrack_16')


def render(rows,format):
    if format=='json':return json.dumps({'format':'OTAI saved timetable records','rows':rows},ensure_ascii=False,indent=2),[]
    if format=='opentrack_xml':
        from .timetable_xml import render_xml
        return render_xml(rows)
    if format not in ['opentrack_17','opentrack_16']:raise APIError('TIMETABLE_EXCHANGE_FORMAT','Unsupported timetable text format.',format)
    current=format=='opentrack_17';lines=['// OpenTrack timetable exchange; original '+('1.7' if current else '1.6')+' columns','// '+'\t'.join(HEADER17 if current else HEADER16)];warnings=[]
    def emit(values):
        if any(any(ord(c)<32 or ord(c)==127 for c in str(value)) for value in values):raise APIError('TIMETABLE_EXCHANGE_SEPARATOR','A native exchange field contains a separator or forbidden ASCII control.')
        return '\t'.join(str(value) for value in values)
    for row in rows:
        values=[row['course_id'],row['interval_reference_course_id'],format_number(row['interval_offset_s']),row['index'],row['station_sign']]
        if current:values.append(row['track_id'])
        values.extend([row['arrival_day_offset'],row['arrival'],row['departure_day_offset'],row['departure'],int(row['timing_station']),format_number(row['dwell_s']),int(row['stop_at_station']),format_number(row['mean_delay_s']),row['distribution_name']])
        if current:values.append(format_number(row['delta_mass_t']))
        lines.append(emit(values))
        if not current and (row['track_id'] or row['delta_mass_t']):warnings.append({'key':row['key'],'omitted':['track_id','delta_mass_t']})
        if row['actual_arrival']!='HH:MM:SS' or row['actual_departure']!='HH:MM:SS':warnings.append({'key':row['key'],'omitted':['actual_times']})
    lines.extend(['// Connections:','// '+'\t'.join(CONNECTION17 if current else CONNECTION16)])
    for row in rows:
        for c in row['connections']:
            info=int(c['join'])+2*int(c['split'])+16*int(c['entry_connection'])+32*int(c['dispo_connection'])
            values=[row['course_id'],c['target_course_id'],row['index'],c['target_station_sign']]
            if current:values.append(c['time_reference_type'])
            values.extend([c['minimum_wait'],c['maximum_wait'],info]);lines.append(emit(values))
            omitted=(['time_reference_type'] if not current and c['time_reference_type'] else [])+(['dispatching_distance_km'] if c['dispatching_distance_km'] else [])
            if c.get('maximum_wait_is_nil'):omitted.append('nil_maximum_wait_storage')
            if omitted:warnings.append({'key':row['key'],'connection_target':c['target_course_id'],'omitted':omitted})
    for line in lines:
        try:line.encode('ascii')
        except UnicodeEncodeError as error:raise APIError('TIMETABLE_EXCHANGE_ASCII','Native exchange contains a non-ASCII field.') from error
        if '\r' in line or '\n' in line:raise APIError('TIMETABLE_EXCHANGE_SEPARATOR','A native field contains an embedded newline.')
        if len(line)>4095:raise APIError('TIMETABLE_EXCHANGE_SIZE','A rendered line exceeds the original Windows import buffer.')
    return '\r\n'.join(lines)+'\r\n',warnings


def format_number(value):return str(int(value)) if int(value)==value else format(value,'.17g')
