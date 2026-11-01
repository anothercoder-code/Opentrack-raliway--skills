"""Original tab-separated 1.7/1.6 timetable exchange; no native program runs."""
import copy
import json
from pathlib import Path
import re
import uuid

from .timetable_text_core import HEADER17, HEADER16, CONNECTION17, CONNECTION16, flag, wait_seconds, parse_text, render, format_number

from .archive import APIError,digest,inside,w
from .course_lifecycle import set_pairs,string_slot,write_slot
from .native_records import timetable_record,connection_record
from opentrack_course_schema import course_array









def input_text(project,args):
    if args.content is not None:
        raw=args.content.encode('utf8');return args.content,{'source':'inline','sha256':digest(raw)}
    path=project.resolve(args.file_path)
    if path.stat().st_size>2000000:raise APIError('TIMETABLE_EXCHANGE_SIZE','Exchange input exceeds 2 MB.')
    raw=path.read_bytes()
    if raw!=path.read_bytes():raise APIError('TIMETABLE_EXCHANGE_CHANGED','Exchange input changed while it was being snapshotted.')
    try:content=raw.decode('utf-8-sig')
    except UnicodeDecodeError as error:raise APIError('TIMETABLE_EXCHANGE_ASCII','Exchange input is not an ASCII/UTF-8 text file.') from error
    return content,{'source':str(path),'sha256':digest(raw),'snapshot_semantics':'Input bytes are materialized in this draft; later text-file edits do not change the reviewed draft.'}


def bind_import_courses(editor,ids,args):
    p=editor.p
    courses=p.courses();lookup={w.string(obj.contents[0].value):obj for obj in courses}
    if len(lookup)!=len(courses):raise APIError('DUPLICATE_COURSE_ID','Imported Course bindings are ambiguous.')
    new_ids=[cid for cid in ids if cid not in lookup];templates={item.course_id:item.template_id for item in args.templates}
    missing_templates=[templates.get(cid,args.default_template_id) for cid in new_ids if templates.get(cid,args.default_template_id) is not None and templates.get(cid,args.default_template_id) not in lookup]
    if missing_templates:raise APIError('GENERATION_TEMPLATE_NOT_FOUND','An imported Course template does not exist.',missing_templates[:50])
    unbound=[cid for cid in new_ids if templates.get(cid,args.default_template_id) is None]
    if unbound and not args.create_unbound_courses:raise APIError('TIMETABLE_EXCHANGE_COURSE','Missing Course definitions need explicit templates or create_unbound_courses=true.',unbound[:50])
    if len(new_ids)>1000:raise APIError('GENERATION_SIZE','One timetable import supports at most 1000 new Course definitions.')
    editor.o.requested_courses+=len(new_ids)
    if editor.o.requested_courses>1000:raise APIError('GENERATION_SIZE','Imported and generated Course definitions share the per-draft limit of 1000.')
    if new_ids:editor.o.prepare_courses()
    for cid in new_ids:
        template=templates.get(cid,args.default_template_id)
        obj=copy.deepcopy(lookup[template] if template is not None else editor.d.template('OTCourse'));write_slot(obj,0,cid)
        if template is None:
            for index in [3,4,10,11,13,14]:write_slot(obj,index,'')
            obj.contents[2].values[0]=editor.d.array();obj.contents[1].values[0]=0.;obj.contents[5].values[0]=1;obj.contents[6].values[0]=100;obj.contents[7].values=[0.,0.];obj.contents[8].values[0]=0;obj.contents[9].values[0]=100;obj.contents[12].values=[0.,0.]
        courses.append(obj)
    w.set_elements(course_array(p.data['courses']),courses)
    return new_ids,unbound


def import_text(editor,args):
    content,provenance=input_text(editor.p,args);incoming,connections,version=parse_text(content);table,groups=editor.load();p=editor.p
    editor.budget(len(incoming),len(connections));ids=list(dict.fromkeys(cid for cid,_ in incoming));known_stations={row['sign'] for row in p.catalog('stations')}
    if any(stop.station_sign not in known_stations for stop in incoming.values()):raise APIError('TIMETABLE_STATION','Imported timetable rows require exact existing station signs.')
    if args.existing=='reject' and any(groups.get(cid) for cid in ids):raise APIError('TIMETABLE_EXCHANGE_EXISTS','Imported Courses already have saved timetable data; explicitly select replace or merge.',[cid for cid in ids if groups.get(cid)][:50])
    new_ids,unbound=bind_import_courses(editor,ids,args)
    before={identity(row):timetable_record(key,row) for key,row in table.items() if identity(row)[0] in ids}
    if args.existing=='replace':
        for cid in ids:groups[cid]=[]
    for (cid,index),stop in incoming.items():
        existing=next((row for row in groups.get(cid,[]) if row.contents[3].value==index),None)
        if existing is not None and args.existing=='merge':
            new=editor.o.make_timetable_row(cid,index,1,stop)
            new.contents[10].values[0]=(existing.contents[10].value&~3)|(new.contents[10].value&3)
            for slot in [1,2,3,5,6,7,8,10,11,12,16]+([17,18] if version=='opentrack_17' else []):existing.contents[slot]=new.contents[slot]
            existing.contents[15].values[:2]=new.contents[15].values[:2]
            old_connections=w.elements(existing.contents[9].value)
            for connection,spec in zip(w.elements(new.contents[9].value),stop.connections):
                key=(string_slot(connection,1),string_slot(connection,6));matches=[i for i,obj in enumerate(old_connections) if (string_slot(obj,1),string_slot(obj,6))==key]
                if len(matches)>1:raise APIError('CONNECTION_AMBIGUOUS','Native connection merge identity is ambiguous.',key)
                if matches:
                    old=old_connections[matches[0]];connection.contents[4].values[0]=(old.contents[4].value&~15)|(connection.contents[4].value&15);connection.contents[8].values[0]=old.contents[8].value
                    if 'time_reference_type' not in spec.model_fields_set:connection.contents[7].values[0]=old.contents[7].value
                    old_connections[matches[0]]=connection
                else:old_connections.append(connection)
            for connection in old_connections:write_slot(connection,2,stop.station_sign)
            w.set_elements(existing.contents[9].value,old_connections)
        else:groups.setdefault(cid,[]).append(editor.o.make_timetable_row(cid,index,1,stop))
    for cid in ids:
        groups[cid].sort(key=lambda row:row.contents[3].value)
        if [row.contents[3].value for row in groups[cid]]!=list(range(len(groups[cid]))):raise APIError('TIMETABLE_EXCHANGE_INDEX','Resulting imported Course indices must be contiguous from zero.',cid)
    editor.write(groups);after=[row for cid in ids for row in groups[cid]]
    return {'input':provenance,'format':version,'existing':args.existing,'courses_created':len(new_ids),'unbound_courses':unbound,'imported_rows':len(incoming),'imported_connections':len(connections),**editor.changes(before,after)}


def identity(row):return string_slot(row,1),row.contents[3].value






class TimetableExporter:
    def __init__(self,service):self.service=service

    def export(self,args):
        p=self.service.project(args);rows=p.catalog('timetable')
        if len(args.course_ids)!=len(set(args.course_ids)):raise APIError('DUPLICATE_COURSE_ID','Export selections must not repeat Course IDs.')
        if args.course_ids:
            available={row['course_id'] for row in rows};missing=set(args.course_ids)-available
            if missing:raise APIError('TIMETABLE_ROW_NOT_FOUND','Selected Courses have no saved timetable rows.',sorted(missing))
            rows=[row for row in rows if row['course_id'] in set(args.course_ids)]
        rows.sort(key=lambda row:(row['course_id'],row['index']))
        extra={}
        if args.format=='railml_2_2':
            from .timetable_railml_export import render_railml
            try:content,warnings,extra=render_railml(p,rows,args)
            except APIError as error:
                if error.code.startswith('ROLLING_STOCK_XML_'):raise APIError('TIMETABLE_RAILML_VALUE',str(error)) from error
                raise
        elif args.format=='opentrack_xml':
            from .timetable_xml import render_xml
            content,warnings=render_xml(rows,args.saved_actual)
        else:content,warnings=render(rows,args.format)
        blob=content.encode('utf8' if args.format in ['json','opentrack_xml'] else 'ascii')
        identifier='export-'+uuid.uuid4().hex[:16];folder=inside(self.service.work/identifier,[self.service.work]);folder.mkdir(parents=True,exist_ok=False)
        path=folder/('timetable.json' if args.format=='json' else 'timetable-'+args.format+('.xml' if args.format in ['opentrack_xml','railml_2_2'] else '.txt'));path.write_bytes(blob)
        report={'export_id':identifier,'format':args.format,'file':str(path),'sha256':digest(blob),'source_project':str(p.project),'source_digest':p.source_digest,'rows':len(rows),'courses':len({row['course_id'] for row in rows}),
            'connections':sum(len(row['connections']) for row in rows),'representability_warnings':warnings[:20],'warning_count':len(warnings),'source_files_unchanged':all(Path(name).is_file() and digest(Path(name).read_bytes())==digest(raw) for name,raw in p.sources.items()),'native_application_started':False}
        if args.format=='opentrack_xml':report.update(saved_actual=args.saved_actual,native_actual_validity_verified=False,external_resources_resolved=False,dtd_validation_performed=False)
        report.update(extra);report['manifest']=str(folder/'manifest.json')
        if 'skipped_courses' in report:report.update(skipped_course_count=len(report['skipped_courses']),skipped_course_preview_truncated=len(report['skipped_courses'])>50)
        (folder/'manifest.json').write_text(json.dumps({**report,'representability_warnings':warnings},ensure_ascii=False,indent=2),encoding='utf8')
        if 'skipped_courses' in report:report['skipped_courses']=report['skipped_courses'][:50]
        return report
