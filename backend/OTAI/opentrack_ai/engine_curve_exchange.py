"""Original Z/V point text exchange, based on reviewed controller/model functions."""
import copy
import json
from pathlib import Path
import re
import uuid

from .errors import APIError

LIMIT=2000000
INT_MIN=-2147483648
INT_MAX=2147483647


def int_value(token,line):
    match=re.match(r'^[+-]?[0-9]+',token)
    value=int(match.group()) if match else 0
    if not INT_MIN<=value<=INT_MAX:raise APIError('ENGINE_CURVE_TEXT_INTEGER','Numeric text exceeds the audited signed-int32 domain.',{'line':line})
    return value


def parse_text(content):
    if not isinstance(content,str):raise APIError('ENGINE_CURVE_TEXT_VALUE','Content must be a string.')
    if len(content)>LIMIT:raise APIError('ENGINE_CURVE_TEXT_SIZE','Curve input exceeds 2 MB.')
    try:content.encode('ascii')
    except UnicodeEncodeError as error:raise APIError('ENGINE_CURVE_TEXT_ASCII','Original curve text requires ASCII data.') from error
    if '\0' in content:raise APIError('ENGINE_CURVE_TEXT_VALUE','Embedded NUL bytes are not accepted.')
    normalized=content.replace('\r\n','\n')
    if any(ord(c)<32 and c not in '\t\n' for c in normalized):raise APIError('ENGINE_CURVE_TEXT_VALUE','Only tab and LF/CRLF control characters are supported.')
    lines=normalized.split('\n') if normalized else []
    if normalized.endswith('\n'):lines.pop()
    name=lines[0].strip(' ') if lines else None;rows=[];previous=1;ignored=0;incomplete=0;truncated=0
    for number,line in enumerate(lines,1):
        if len(line)>1022:raise APIError('ENGINE_CURVE_TEXT_SIZE','A line exceeds the original 1024-byte text-mode import buffer.',number)
        
        start=line.lstrip(' ')
        if not start or start[0] not in '0123456789':
            if start and not start.startswith('//'):ignored+=1
            continue
        tokens=[part for part in line.replace(',','.').replace('\t',' ').split(' ') if part]
        if len(tokens)<2:incomplete+=1;continue
        speed=max(0,int_value(tokens[0],number));force=int_value(tokens[1],number)
        flag=2 if len(tokens)>2 and tokens[2]=='H' else 1
        rows.append((speed,force,previous));previous=flag
        if any(re.search(r'[.,eE]',token) for token in tokens[:2]):truncated+=1
        if len(rows)>100000:raise APIError('GENERATION_SIZE','At most 100000 source point rows are supported.')
    return rows,{'source_diagram_name':name,'parsed_points':len(rows),'ignored_noncomment_lines':ignored,'incomplete_numeric_lines':incomplete,'integer_converted_rows':truncated,
        'flag_semantics':'H on a text row applies to the next source row before sign splitting or sorting.'}


def input_text(project,args):
    from .archive import digest
    if args.content is not None:
        content=args.content;blob=content.encode('utf8');source='inline'
    else:
        path=project.resolve(args.file_path)
        if path.stat().st_size>LIMIT:raise APIError('ENGINE_CURVE_TEXT_SIZE','Curve input exceeds 2 MB.')
        blob=path.read_bytes()
        if blob!=path.read_bytes():raise APIError('ENGINE_CURVE_TEXT_CHANGED','Curve input changed during snapshot capture.')
        try:content=blob.decode('utf8')
        except UnicodeDecodeError as error:raise APIError('ENGINE_CURVE_TEXT_ASCII','Input is not an ASCII/UTF-8 file.') from error
        source=str(path)
    rows,details=parse_text(content)
    return rows,{'source':source,'bytes':len(blob),'sha256':digest(blob),'snapshot_semantics':'Input bytes are consumed once for this ordered operation; later file changes do not change the draft.',**details}


def assign_points(definitions,diagram,index,rows):
    objects=[]
    for row in rows:
        point=copy.deepcopy(definitions.template('OTDPoint'));point.contents[0].values=list(row);objects.append(point)
    diagram.contents[index].values[0]=definitions.array(objects)


def import_points(stock,values,args,rows,provenance):
    from .drafts import set_text
    from .engine_diagrams import AUTO_SYSTEM_ORDER,selection_index,point_rows,set_systems,systems
    if args.existing=='new':
        if len(values)>=64:raise APIError('ENGINE_DIAGRAM_COUNT','At most 64 diagrams are supported per Engine.')
        diagram=copy.deepcopy(stock.d.template('OTDDiagram'))
        diagram.contents[0].values=[250,400,150,125,80,1,1];diagram.contents[5].values[0]=-200
        
        from .models import CalibratedWhite
        from .native_colors import make_color
        diagram.contents[4].values[0]=make_color(stock.d,CalibratedWhite(white=0))
        wrapper=copy.deepcopy(stock.d.template('OTEfficiencyArray'));wrapper.contents[0].values[0]=stock.d.array();diagram.contents[7].values[0]=wrapper
        codes=args.power_system_codes
        if codes is None:
            used={code for value in values for code in systems(value)}
            code=next((code for code in AUTO_SYSTEM_ORDER if code not in used),None)
            if code is None:raise APIError('ENGINE_SYSTEM_EXHAUSTED','Supply explicit unused power codes or an empty unassigned list.')
            codes=[code]
        set_systems(stock.d,diagram,codes)
        name=args.description if args.description is not None else provenance['source_diagram_name']
        if name is None:name='Diagram '+str(len(values)+1)
        set_text(diagram,6,'' if name in ['', ' '] else name)
        values.append(diagram);at=len(values)-1
    else:at=args.index;diagram=selection_index(values,at)
    result={1:[] if args.existing in ['new','replace'] else point_rows(diagram,1),2:[] if args.existing in ['new','replace'] else point_rows(diagram,2)}
    speeds={index:{row[0] for row in points} for index,points in result.items()};duplicates=0
    for row in rows:
        index=2 if row[1]<0 else 1
        if row[0] in speeds[index]:duplicates+=1;continue
        result[index].append(row);speeds[index].add(row[0])
    for index,points in result.items():assign_points(stock.d,diagram,index,sorted(points,key=lambda row:row[0]))
    return {'index':at,'existing':args.existing,'source_points':len(rows),'duplicate_speeds_skipped':duplicates,'resulting_traction_points':len(result[1]),'resulting_braking_points':len(result[2]),
        'display_axes_policy':'New diagrams use audited constructor scales; existing scales are preserved. This data operation does not execute the native view auto-scale command.'}


def render_text(engine_name,index,record):
    name=record['description'];warnings=[]
    if not isinstance(name,str) or not isinstance(engine_name,str):raise APIError('ENGINE_CURVE_TEXT_HEADER','Captions must be strings.')
    if sum(len(record[key]) for key in ['points','braking_points'])>100000:raise APIError('GENERATION_SIZE','At most 100000 point rows are supported.')
    for key in ['points','braking_points']:
        for point in record[key]:
            if any(type(point[field]) is not int or not INT_MIN<=point[field]<=INT_MAX for field in ['speed_kmh','force_kn']):raise APIError('ENGINE_CURVE_TEXT_INTEGER','Point values must be signed-int32 integers, without coercion.')
            if type(point['flag']) is not int or point['flag'] not in [1,2]:raise APIError('ENGINE_CURVE_POINT_TYPE','Native text export supports reviewed point types 1 and 2 only.')
    for value in [name,engine_name]:
        if '\n' in value or '\r' in value or '\0' in value:raise APIError('ENGINE_CURVE_TEXT_HEADER','A native text caption contains an embedded line break or NUL.')
    lines=[name,'//','// Produced by OTAI: OpenTrack-compatible Z/V point text','// Engine: '+engine_name,'// Z/V-Diagram: '+name,'// -----------------------------------------------',
        '// Speed [km/h], Tractive Effort [kN], Type (opt.)','// -----------------------------------------------']
    for key in ['points','braking_points']:
        points=record[key]
        speeds=[point['speed_kmh'] for point in points]
        if any(speed<0 for speed in speeds):warnings.append({'kind':'negative_speed_rows_ignored_on_native_import','curve':key,'count':sum(speed<0 for speed in speeds)})
        if any(b<=a for a,b in zip(speeds,speeds[1:])):warnings.append({'kind':'native_import_sorts_curve','curve':key})
        duplicate=len(speeds)-len(set(speeds))
        if duplicate:warnings.append({'kind':'native_import_drops_duplicate_speeds','curve':key,'count':duplicate})
        wrong=sum(point['force_kn']<0 if key=='points' else point['force_kn']>0 for point in points)
        if wrong:warnings.append({'kind':'point_force_sign_reclassified_on_native_import','curve':key,'count':wrong})
        for at,point in enumerate(points):
            flag=points[at+1]['flag'] if at+1<len(points) else 1
            if flag not in [1,2]:raise APIError('ENGINE_CURVE_POINT_TYPE','Native text export supports reviewed point types 1 and 2 only.',{'index':index,'flag':flag})
            lines.append(str(point['speed_kmh'])+'\t'+str(point['force_kn'])+(' H' if flag==2 else ''))
        if points and points[0]['flag']!=1:warnings.append({'kind':'first_point_type_normalized','curve':key,'native_type':points[0]['flag']})
    caption_rows,_=parse_text(name)
    if caption_rows:warnings.append({'kind':'numeric_caption_is_parsed_as_point_on_native_import'})
    zeros=sum(point['force_kn']==0 for point in record['braking_points'])
    if zeros:warnings.append({'kind':'zero_braking_points_reclassified_as_traction_on_native_import','count':zeros})
    if name!=name.strip(' '):warnings.append({'kind':'new_import_trims_caption_spaces'})
    warnings.append({'kind':'text_omits_saved_fields','fields':['supply_assignments','color','adhesion','scales','visibility','loss_function']})
    content='\r\n'.join(lines)+'\r\n'
    parse_text(content) 
    return content,warnings


class CurveExporter:
    def __init__(self,service):self.service=service

    def export(self,args):
        from .archive import digest,inside
        project=self.service.project(args);engines=project.catalog('engines',include_curves=True);names=[row['name'] for row in engines]
        if len(names)!=len(set(names)):raise APIError('ENGINE_AMBIGUOUS','Engine names are not unique; export cannot identify their ownership unambiguously.')
        missing=set(args.engine_names)-set(names)
        if missing:raise APIError('ENGINE_NOT_FOUND','Selected Engine names do not exist.',sorted(missing))
        selected=[row for row in engines if not args.engine_names or row['name'] in set(args.engine_names)];records=[]
        for engine in selected:
            diagrams=engine.get('tractive_effort_diagrams',[]);indices=range(len(diagrams)) if args.diagram_indices is None else args.diagram_indices
            for index in indices:
                if not 0<=index<len(diagrams):raise APIError('ENGINE_DIAGRAM_INDEX','An export index is outside a selected Engine.',{'engine':engine['name'],'index':index})
                records.append({'engine_name':engine['name'],'diagram_index':index,'diagram':diagrams[index]})
        if len(records)>1000 or sum(len(r['diagram']['points'])+len(r['diagram']['braking_points']) for r in records)>100000:raise APIError('GENERATION_SIZE','One export supports 1000 diagrams and 100000 points; select a smaller batch.')
        blobs=[];warnings=[]
        if args.format=='json':blobs.append(('engine-curves.json',json.dumps({'format':'OTAI mapped saved Engine diagrams','diagrams':records},ensure_ascii=False,indent=2).encode('utf8')))
        else:
            for number,row in enumerate(records):
                content,issues=render_text(row['engine_name'],row['diagram_index'],row['diagram']);blobs.append(('curve-'+str(number+1).zfill(4)+'.txt',content.encode('ascii')))
                warnings.extend({'engine_name':row['engine_name'],'diagram_index':row['diagram_index'],**issue} for issue in issues)
        identifier='export-'+uuid.uuid4().hex[:16];folder=inside(self.service.work/identifier,[self.service.work]);folder.mkdir(parents=True,exist_ok=False);files=[]
        for name,blob in blobs:
            path=folder/name;path.write_bytes(blob);files.append({'file':str(path),'sha256':digest(blob),'bytes':len(blob)})
        report={'export_id':identifier,'format':args.format,'source_project':str(project.project),'source_digest':project.source_digest,'engines':len(selected),'diagrams':len(records),'file_count':len(files),
            'files':files[:20],'files_truncated':len(files)>20,'representability_warnings':warnings[:20],'warning_count':len(warnings),'source_files_unchanged':all(Path(name).is_file() and digest(Path(name).read_bytes())==digest(raw) for name,raw in project.sources.items()),'native_application_started':False}
        manifest=folder/'manifest.json';manifest.write_text(json.dumps({**report,'files':files,'representability_warnings':warnings,'diagram_ownership':[{'engine_name':row['engine_name'],'diagram_index':row['diagram_index']} for row in records]},ensure_ascii=False,indent=2),encoding='utf8');report['manifest']=str(manifest)
        return report
