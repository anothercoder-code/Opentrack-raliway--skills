"""Original proprietary timetable XML events and output; never run OpenTrack."""
import copy
from datetime import datetime
import math
from xml.parsers import expat

from pydantic import TypeAdapter,ValidationError

from .archive import APIError,w
from .connection_commands import native_wait_string
from .course_lifecycle import string_slot,write_slot
from .models import ArchiveText,NewCourseId,TimeText,TimetableStop
from .native_records import timetable_record
from .railml_values import f32,float_text,int_text
from .timetable_exchange import input_text,bind_import_courses,format_number

LEAVES={'courseID','stationID','trackID','arrivalTime','departureTime','waitTime','delayTime','delayDistributionName','deltaLoad','minTime','maxTime','referenceTime'}
CONTAINERS={'timetable','course','referenceCourse','timetableEntry','connection'}
def yes(value,short=False):return value.lower() in (['yes','y','1'] if short else ['yes','1'])
def checked_text(value,kind=ArchiveText):
    try:return TypeAdapter(kind).validate_python(value)
    except ValidationError as error:raise APIError('TIMETABLE_XML_VALUE','XML text is outside the current native field contract.',str(error)[:300]) from error
def day(value):
    value=int_text(value)
    if not -366<=value<=366:raise APIError('TIMETABLE_XML_DAY','XML dayOffset is outside the supported -366..366 range.',value)
    return value
def time_string(value):return value if value=='HH:MM:SS' else checked_text(value,TimeText)
def duration(value,format):
    if format==2:
        value=time_string(value)
        if value=='HH:MM:SS':return '-1'
        return str(sum(int(v)*n for v,n in zip(value.split(':'),[3600,60,1])))
    if format==6:return str(int_text(value))
    value=checked_text(value)
    try:f32(float(value or '0'))
    except (ValueError,APIError) as error:raise APIError('TIMETABLE_XML_NUMBER','An unmarked wait/delay must be finite numeric text. Use format=s or hh:mm:ss for original conversions.') from error
    return value


class NativeXMLParser:
    """Reviewed callback rules; ambiguous native dictionary order stays explicit."""
    def __init__(self,connection_attribute_order='require_unambiguous'):
        self.stack=[];self.text='';self.ready=False;self.reference=False;self.connection=None;self.state={}
        self.rows={};self.course_rows=[];self.seen_courses=set();self.warnings=[];self.unknown=set();self.connections=0
        self.connection_attribute_order=connection_attribute_order;self.reset_course()

    def reset_course(self):
        actual={k:self.state.get(k,'HH:MM:SS') for k in ['actual_arrival','actual_departure']}
        self.state={'course_id':'0','interval_reference_course_id':'0','interval_offset_s':0.,**actual};self.reset_row()

    def reset_row(self):
        self.state.update(station_sign='',track_id='',arrival='HH:MM:SS',departure='HH:MM:SS',arrival_day_offset=0,departure_day_offset=0,
            actual_arrival_day_offset=0,actual_departure_day_offset=0,dwell='0',mean_delay='0',distribution_name='',delta_mass_t=0.,
            stop_at_station=False,timing_station=True,connections=[])
        self.actual_seen=set()

    def warning(self,code,**values):self.warnings.append({'code':code,**values})

    def start(self,name,attributes):
        parent=self.stack[-1] if self.stack else None
        if len(self.stack)>=64:raise APIError('TIMETABLE_XML_DEPTH','XML nesting exceeds 64 elements.')
        required={'timetable':None,'course':'timetable','timetableEntry':'course','connection':'timetableEntry'}
        if not self.stack and name!='timetable':raise APIError('TIMETABLE_XML_FORMAT','Expected original proprietary <timetable> XML; RailML is a separate format.')
        if name in required and parent!=required[name]:raise APIError('TIMETABLE_XML_STRUCTURE','Invalid native timetable container nesting.',name)
        self.stack.append(name);self.text='';self.format=0;self.time_type=0;self.valid=-1;self.actual_day_offset_supplied=False
        if name=='course':self.reset_course();self.course_rows=[]
        elif name=='referenceCourse':self.reference=True
        elif name=='timetableEntry':self.reset_row();self.ready=True
        elif name=='connection':
            self.connection={'course_id':self.state['course_id'],'target_course_id':'0','station_sign':self.state['station_sign'],
                'target_station_sign':self.state['station_sign'],'minimum_wait':'HH:MM:SS','maximum_wait':'HH:MM:SS',
                'join':False,'split':False,'location':0,'time_reference_type':0}
        elif name not in LEAVES|CONTAINERS and name not in self.unknown:
            self.unknown.add(name);self.warning('XML_UNKNOWN_ELEMENT_IGNORED',element=name)
        pairs=list(zip(attributes[::2],attributes[1::2]));attributes=dict(pairs)
        if name=='connection' and 'connectionTimeType' in attributes and attributes.get('connectionPlace','').lower() in ['home','station']:
            if self.connection_attribute_order=='require_unambiguous':raise APIError('TIMETABLE_XML_ATTRIBUTE_ORDER','Native dictionary enumeration can change this connection location. Select the intended reviewed callback order explicitly.',{'choices':['place_then_time_type','time_type_then_place']})
            keys=['connectionPlace','connectionTimeType'] if self.connection_attribute_order=='place_then_time_type' else ['connectionTimeType','connectionPlace']
            pairs=[(k,v) for k,v in pairs if k not in keys]+[(k,attributes[k]) for k in keys]
            self.warning('NATIVE_DICTIONARY_ORDER_NOT_REPRODUCED',selected_callback_order=self.connection_attribute_order)
        for key,value in pairs:self.attribute(name,key,value)

    def attribute(self,name,key,value):
        if not self.ready:
            if name=='referenceTime' and key=='format' and value.lower()=='hh:mm:ss':self.warning('NATIVE_REFERENCE_TIME_FORMAT_IGNORED_BEFORE_ENTRY')
            return
        if name=='timetableEntry' and key=='stopInformation':self.state['stop_at_station']=yes(value,True)
        elif name=='connection':
            c=self.connection
            if key=='connectionType':
                c['join']=value.lower() in ['join','meet'];c['split']=value.lower()=='split'
            elif key=='connectionPlace':c['location']={'home':4,'station':8,'exit':0}.get(value.lower(),0)
            elif key=='connectionTimeType':
                if c['location']:self.warning('NATIVE_CONNECTION_TIME_TYPE_RESETS_LOCATION',target_course_id=c['target_course_id'])
                c['location']=0;c['time_reference_type']=int(value.lower()=='departure')
        elif name in LEAVES:
            if key=='format':self.format={'hh:mm:ss':2,'s':6}.get(value.lower(),0)
            if name in ['arrivalTime','departureTime']:
                field='arrival' if name=='arrivalTime' else 'departure'
                if key=='type':self.time_type={'planned':1,'actual':2}.get(value.lower(),0)
                elif key=='valid':self.valid=1 if yes(value) else 0 if value.lower() in ['no','0'] else -1
                elif key=='dayOffset':self.state[field+'_day_offset']=day(value);self.actual_day_offset_supplied=True
                elif name=='departureTime' and key=='useDepartureTime':self.state['timing_station']=yes(value)

    def characters(self,text):self.text+=text

    def end(self,name):
        s=self.state;value=self.text
        if name=='course':
            cid=checked_text(s['course_id'],NewCourseId)
            if cid in self.seen_courses:raise APIError('TIMETABLE_XML_DUPLICATE','One XML batch cannot repeat a Course container.',cid)
            self.seen_courses.add(cid)
            for index,row in enumerate(self.course_rows):
                if row['course_id']!=cid:raise APIError('TIMETABLE_XML_STRUCTURE','Changing Course ID inside its timetable entries is unsupported.',cid)
                self.rows[(cid,index)]=row
        elif name=='timetableEntry':
            if len(self.rows)+len(self.course_rows)>=10000:raise APIError('GENERATION_SIZE','XML import supports at most 10000 timetable rows.')
            for field in ['actual_arrival','actual_departure']:
                if s[field]!='HH:MM:SS' and field not in self.actual_seen:self.warning('NATIVE_ACTUAL_STRING_CARRIED_TO_NEXT_ROW',field=field,course_id=s['course_id'],index=len(self.course_rows))
            self.course_rows.append(copy.deepcopy(s));self.ready=False
        elif name=='referenceCourse':self.reference=False
        elif name=='connection':
            s['connections'].append(self.connection);self.connection=None;self.connections+=1
            if self.connections>10000:raise APIError('GENERATION_SIZE','XML import supports at most 10000 connections.')
        elif name=='courseID':
            value=checked_text(value,NewCourseId) if value not in ['0','-1'] else value
            if self.connection is not None:self.connection['target_course_id']=value
            elif self.reference:s['interval_reference_course_id']=value
            else:s['course_id']=value
        elif name=='referenceTime':
            s['interval_offset_s']=float_text(duration(value,2) if self.format==2 else value)
        elif name=='stationID':
            value=checked_text(value)
            if not 1<=len(value)<=32:raise APIError('TIMETABLE_XML_STATION','stationID requires 1..32 characters.')
            if self.connection is not None:self.connection.update(station_sign=value,target_station_sign=value)
            else:s['station_sign']=value
        elif name=='trackID':s['track_id']=checked_text(value)
        elif name in ['arrivalTime','departureTime']:
            field='arrival' if name=='arrivalTime' else 'departure'
            if self.time_type==2:
                if self.valid==1:
                    s['actual_'+field]=native_wait_string(float_text(value)) if self.format==6 else time_string(value);self.actual_seen.add('actual_'+field)
                    self.warning('NATIVE_XML_ACTUAL_VALIDITY_NOT_PERSISTED',field=field)
                    if self.actual_day_offset_supplied:self.warning('NATIVE_ACTUAL_DAY_OFFSET_STORED_ON_PLANNED',field=field,day_offset=s[field+'_day_offset'])
            elif self.valid!=0:
                if self.format==6:
                    number=float_text(value);s[field]=native_wait_string(number)
                    if field=='departure':s[field+'_day_offset']=day(str(math.floor(number/86400)) if number>=0 else '0')
                else:s[field]=time_string(value)
        elif name in ['waitTime','delayTime']:s['dwell' if name=='waitTime' else 'mean_delay']=duration(value,self.format)
        elif name=='delayDistributionName':s['distribution_name']=checked_text(value)
        elif name=='deltaLoad':s['delta_mass_t']=float_text(value)
        elif name in ['minTime','maxTime'] and self.connection is not None:
            self.connection['minimum_wait' if name=='minTime' else 'maximum_wait']=native_wait_string(float_text(value)) if self.format==6 else time_string(value)
        self.stack.pop()

    def parse(self,content):
        if len(content.encode('utf8'))>2000000:raise APIError('TIMETABLE_EXCHANGE_SIZE','XML input exceeds 2 MB.')
        parser=expat.ParserCreate();parser.ordered_attributes=True
        parser.StartElementHandler=self.start;parser.EndElementHandler=self.end;parser.CharacterDataHandler=self.characters
        def entity(*args):raise APIError('TIMETABLE_XML_ENTITY','Entity declarations are outside the supported timetable XML input contract.')
        parser.EntityDeclHandler=entity;parser.ExternalEntityRefHandler=lambda *args:1
        parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
        try:parser.Parse(content,True)
        except expat.ExpatError as error:raise APIError('TIMETABLE_XML_PARSE','Malformed XML input.',{'line':error.lineno,'column':error.offset}) from error
        except APIError as error:
            if error.code=='ROLLING_STOCK_XML_NUMBER':raise APIError('TIMETABLE_XML_NUMBER',str(error)) from error
            raise
        return self.rows,self.warnings


def import_xml(editor,args):
    content,provenance=input_text(editor.p,args);incoming,warnings=NativeXMLParser(args.connection_attribute_order).parse(content)
    if not incoming and not args.clear_existing_timetables:raise APIError('TIMETABLE_EXCHANGE_EMPTY','XML has no timetable entries; clearing requires clear_existing_timetables=true.')
    table,groups=editor.load();ids=list(dict.fromkeys(cid for cid,_ in incoming));known={r['sign'] for r in editor.p.catalog('stations')}
    if any(r['station_sign'] not in known for r in incoming.values()):raise APIError('TIMETABLE_STATION','XML timetable rows require exact existing station signs.')
    connections=sum(len(r['connections']) for r in incoming.values());cleared=sum(len(v) for cid,v in groups.items() if cid not in ids) if args.clear_existing_timetables else 0
    editor.budget(len(incoming)+cleared,connections)
    if not args.clear_existing_timetables and args.existing=='reject' and any(groups.get(cid) for cid in ids):raise APIError('TIMETABLE_EXCHANGE_EXISTS','XML Courses already have timetable data; explicitly select replace.',ids[:50])
    new_ids,unbound=bind_import_courses(editor,ids,args)
    before={(string_slot(row,1),row.contents[3].value):timetable_record(key,row) for key,row in table.items() if args.clear_existing_timetables or string_slot(row,1) in ids}
    removed=len(table) if args.clear_existing_timetables else 0
    if args.clear_existing_timetables:groups.clear()
    for cid in ids:groups[cid]=[]
    for (cid,index),data in incoming.items():
        row=editor.o.make_timetable_row(cid,index,1,TimetableStop(station_sign=data['station_sign'],stop_at_station=False))
        for slot,field in [(2,'interval_reference_course_id'),(5,'station_sign'),(6,'arrival'),(7,'departure'),(8,'dwell'),(12,'mean_delay'),(13,'actual_arrival'),(14,'actual_departure'),(16,'distribution_name'),(18,'track_id')]:write_slot(row,slot,data[field])
        row.contents[10].values[0]=int(data['stop_at_station'])+2*int(data['timing_station']);row.contents[11].values[0]=data['interval_offset_s'];row.contents[17].values[0]=data['delta_mass_t']
        row.contents[15].values=[data[field+'_day_offset'] for field in ['arrival','departure','actual_arrival','actual_departure']]
        values=[]
        for c in data['connections']:
            obj=copy.deepcopy(editor.d.template('OTConnection'))
            for slot,field in [(0,'course_id'),(1,'target_course_id'),(2,'station_sign'),(3,'minimum_wait'),(5,'maximum_wait'),(6,'target_station_sign')]:write_slot(obj,slot,c[field])
            obj.contents[4].values[0]=int(c['join'])+2*int(c['split'])+c['location'];obj.contents[7].values[0]=c['time_reference_type'];obj.contents[8].values[0]=0.;values.append(obj)
        row.contents[9].values[0]=editor.d.array(values);groups[cid].append(row)
    editor.write(groups);after=[r for cid in ids for r in groups[cid]]
    return {'input':provenance,'format':'opentrack_xml','existing':args.existing,'connection_attribute_order':args.connection_attribute_order,'courses_created':len(new_ids),'unbound_courses':unbound,
        'imported_rows':len(incoming),'imported_connections':connections,'cleared_timetable_rows':removed,'xml_warnings':warnings,'xml_warning_count':len(warnings),
        **editor.changes(before,after),'native_xml_scope':'Original proprietary saved-data event behavior; no native runtime validity, external DTD access or GUI execution.'}


def xml_text(value):
    text=str(value)
    if any(ord(c)<32 and c not in '\t\r\n' or 0xd800<=ord(c)<=0xdfff or ord(c) in [0xfffe,0xffff] for c in text):raise APIError('TIMETABLE_XML_CHARACTER','A saved field contains a character forbidden in XML 1.0.')
    return ''.join('&#'+str(ord(c))+';' if c in '"&<>' or ord(c)>126 else c for c in text)


def render_xml(rows,saved_actual='omit'):
    warnings=[];lines=['<?xml version="1.0"?>','<?xml-stylesheet?>','<!DOCTYPE timetable SYSTEM "timetable-opentrack_xml.dtd">',
        '<timetable title="OpenTrack timetable" application="OpenTrack" date="'+datetime.now().astimezone().isoformat()+'">']
    by_course={}
    for row in rows:by_course.setdefault(row['course_id'],[]).append(row)
    def element(tag,value,attrs='',indent=3):lines.append('\t'*indent+'<'+tag+attrs+'>'+xml_text(value)+'</'+tag+'>')
    for cid,items in by_course.items():
        if any(r['index']!=i or r['last_index']!=len(items)-1 for i,r in enumerate(items)):raise APIError('TIMETABLE_XML_INDEX','XML export requires contiguous, consistent Course row indices.',cid)
        lines.append('\t<course>');element('courseID',cid,indent=2);first=items[0]
        if first['interval_reference_course_id'] not in ['','0','-1']:
            lines.append('\t\t<referenceCourse>');element('courseID',first['interval_reference_course_id']);element('referenceTime',format(f32(first['interval_offset_s']),'.1f'),' format="s"');lines.append('\t\t</referenceCourse>')
        for row in items:
            omitted=[]
            if (row['interval_reference_course_id'],row['interval_offset_s'])!=(first['interval_reference_course_id'],first['interval_offset_s']):omitted.append('per_row_interval_reference_or_offset')
            if f32(row['interval_offset_s'])!=float(format(f32(row['interval_offset_s']),'.1f')):omitted.append('interval_offset_precision')
            lines.append('\t\t<timetableEntry stopInformation="'+('yes' if row['stop_at_station'] else 'no')+'">');element('stationID',row['station_sign'])
            if row['track_id']:element('trackID',row['track_id'])
            for field,tag in [('arrival','arrivalTime'),('departure','departureTime')]:
                offset=row[field+'_day_offset'];attrs=' format="hh:mm:ss" type="planned"'+(' dayOffset="'+str(offset)+'"' if offset>0 else '')
                if offset<0:omitted.append(field+'_negative_day_offset')
                if field=='departure':attrs+=' useDepartureTime="'+('yes' if row['timing_station'] else 'no')+'"'
                element(tag,row[field],attrs+' valid="yes"')
                actual=row['actual_'+field]
                if actual!='HH:MM:SS' or saved_actual=='as_valid':
                    if saved_actual=='as_valid':
                        actual_day=row['actual_'+field+'_day_offset'];attrs=' format="hh:mm:ss" type="actual"'+(' dayOffset="'+str(actual_day)+'"' if actual_day>0 else '')+' valid="yes"'
                        element(tag,actual,attrs);omitted.append('native_actual_validity_unverified')
                        if actual_day<0:omitted.append('actual_'+field+'_negative_day_offset')
                    else:omitted.append('actual_'+field+'_validity_unavailable')
            element('waitTime',format_number(row['dwell_s']),' format="s"');element('delayTime',format_number(row['mean_delay_s']),' format="s"')
            if row['distribution_name']:element('delayDistributionName',row['distribution_name'])
            if row['delta_mass_t']:
                rounded=format(f32(row['delta_mass_t']),'.3f');element('deltaLoad',rounded)
                if float(rounded)!=f32(row['delta_mass_t']):omitted.append('delta_mass_precision')
            if omitted:warnings.append({'key':row['key'],'omitted':list(dict.fromkeys(omitted))})
            for c in row['connections']:
                kind='meet' if c['join'] and c['split'] else 'join' if c['join'] else 'split' if c['split'] else 'normal'
                place='home' if c['entry_connection'] else 'dispo' if c['dispo_connection'] else 'exit';time='departure' if c['time_reference_type'] else 'arrivalpass'
                lines.append('\t\t\t<connection connectionType="'+kind+'" connectionPlace="'+place+'" connectionTimeType="'+time+'">')
                element('courseID',c['target_course_id'],indent=4);element('stationID',c['station_sign'],indent=4)
                element('minTime',c['minimum_wait'],' format="hh:mm:ss"',4);element('maxTime',c['maximum_wait'],' format="hh:mm:ss"',4);lines.append('\t\t\t</connection>')
                lost=[]
                if c['target_station_sign']!=c['station_sign']:lost.append('target_station_sign')
                if c['entry_connection']:lost.append('native_import_connection_location_order')
                if c['dispo_connection']:lost.append('native_import_dispo_place_name')
                if c['join'] and c['split']:lost.append('native_import_meet_split_flag')
                if c['time_reference_type'] not in [0,1]:lost.append('time_reference_type_raw_code')
                if c['dispatching_distance_km']:lost.append('dispatching_distance_km')
                if c.get('maximum_wait_is_nil'):lost.append('nil_maximum_wait_storage')
                if lost:warnings.append({'key':row['key'],'connection_target':c['target_course_id'],'omitted':lost})
            lines.append('\t\t</timetableEntry>')
        lines.append('\t</course>')
    lines.append('</timetable>');return '\n'.join(lines)+'\n',warnings
