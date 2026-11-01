"""Original Itinerary safety-margin rows, commands and two-column exchange."""
import copy
from decimal import Decimal,ROUND_HALF_UP,localcontext
import json
import math
from pathlib import Path
import re
import struct
import uuid

from .archive import APIError,digest,inside,page,w

MAX_ROWS=10000
MAX_INPUT=2000000


def f32(value):
    try:result=struct.unpack('<f',struct.pack('<f',float(value)))[0]
    except (OverflowError,ValueError,TypeError) as error:raise APIError('MARGIN_FLOAT32','Safety-margin values must fit finite float32.') from error
    if not math.isfinite(result):raise APIError('MARGIN_FLOAT32','Safety-margin values must fit finite float32.')
    return result


def rows(destination):
    if w.kind(destination)!='OTDest' or len(destination.contents)!=6:raise APIError('ITINERARY_MARGIN_SCHEMA','Expected original OTDest margin storage.')
    wrapper=destination.contents[5].value
    if w.kind(wrapper)!='OTSafetyMarginArray' or wrapper.clazz.version!=0 or len(wrapper.contents)!=1:raise APIError('ITINERARY_MARGIN_SCHEMA','Expected OTSafetyMarginArray v0.')
    if w.kind(wrapper.contents[0].value) not in ['NSArray','NSMutableArray']:raise APIError('ITINERARY_MARGIN_SCHEMA','Expected the original embedded margin array.')
    values=w.elements(wrapper.contents[0].value)
    if len(values)>MAX_ROWS:raise APIError('ITINERARY_MARGIN_SIZE','Select an Itinerary with at most 10000 margin rows.')
    result=[];identities={}
    for obj in values:
        if w.kind(obj)!='OTSafetyMargin' or obj.clazz.version!=0 or len(obj.contents)!=1 or obj.contents[0].encodings!=[b'f',b'f']:
            raise APIError('ITINERARY_MARGIN_SCHEMA','Expected original OTSafetyMargin v0 with one ff group.')
        position,margin=map(f32,obj.contents[0].values)
        if id(obj) not in identities:identities[id(obj)]={'position_m':position,'safety_margin_m':margin}
        result.append(identities[id(obj)])
    return result


def make_point(point):
    values=[f32(point['position_m']),f32(point['safety_margin_m'])]
    return w.ar.GenericArchivedObject(w.ar.Class(b'OTSafetyMargin',0,w.ar.Class(b'NSObject',0,None)),None,[w.ar.TypedGroup([b'f',b'f'],values)])


def assign(destination,values,builder,existing=None):
    objects=dict(existing or {});items=[]
    for value in values:
        if id(value) not in objects:objects[id(value)]=make_point(value)
        else:objects[id(value)].contents[0].values=[f32(value['position_m']),f32(value['safety_margin_m'])]
        items.append(objects[id(value)])
    array=destination.contents[5].value.contents[0].value
    if array is None:destination.contents[5].value.contents[0].values[0]=builder.array(items)
    else:w.set_elements(array,items)


def alias_groups(values):
    indices={}
    for index,value in enumerate(values):indices.setdefault(id(value),[]).append(index)
    return [group for group in indices.values() if len(group)>1]


def shared_profiles(project,destination):
    from .itinerary_controls import definitions
    wrapper=destination.contents[5].value;array=wrapper.contents[0].value;points={id(obj) for obj in w.elements(array)};result=[]
    for name,(document,other) in definitions(project).items():
        if other is destination:continue
        candidate=other.contents[5].value
        if candidate is None or not candidate.contents:continue
        embedded=candidate.contents[0].value
        if candidate is wrapper or embedded is array or w.kind(embedded) in ['NSArray','NSMutableArray'] and any(id(obj) in points for obj in w.elements(embedded)):
            result.append((name,document,other))
    return result


def native_sort(values):
    from .native_array_sort import sort_by_position
    for value in values:
        value['position_m']=f32(value['position_m']);value['safety_margin_m']=f32(value['safety_margin_m'])
    return sort_by_position(values)


def lookup(values,distance):
    distance=f32(distance);at=None
    for index,row in enumerate(values):
        if distance==row['position_m']:at=index;break
        if distance<row['position_m']:
            at=index-1 if index else None;break
    else:
        if values:at=len(values)-1
    return {'distance_m':distance,'row_index':at,'safety_margin_m':values[at]['safety_margin_m'] if at is not None else 0.0}


def selected(project,name):
    from .itinerary_controls import definitions
    records=definitions(project)
    if name not in records:raise APIError('ITINERARY_NOT_LOADED','A loaded Itinerary document definition is required.',name)
    return records[name]


def read(service,args):
    project=service.project(args);document,dest=selected(project,args.name);values=rows(dest)
    duplicates=len(values)-len({row['position_m'] for row in values})
    first={};items=[]
    for index,row in enumerate(values):first.setdefault(id(row),index);items.append({'index':index,'reference_index':first[id(row)],**row})
    shared=[name for name,_,_ in shared_profiles(project,dest)]
    return {'name':args.name,'document':document,**page(items,args.limit,args.offset),
        'queries':[lookup(values,distance) for distance in args.distances_m],
        'nondecreasing_positions':all(a['position_m']<=b['position_m'] for a,b in zip(values,values[1:])),
        'duplicate_position_rows':duplicates,'source_digest':project.source_digest,
        'shared_profile_count':len(shared),'shared_profiles_preview':shared[:20],'shared_profiles_truncated':len(shared)>20,
        'lookup_rule':'Native array order: first exact match; otherwise preceding row before the first greater position; no row means zero. No implicit sort.',
        'native_application_started':False,'native_train_control_verified':False}


def float_value(token):
    
    
    match=re.match(r'^[ \t]*([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)',token)
    return f32(float(match.group(1))) if match else 0.0


def parse_text(content):
    if len(content.encode('utf8'))>MAX_INPUT:raise APIError('MARGIN_TEXT_SIZE','Margin text exceeds 2 MB.')
    try:content.encode('ascii')
    except UnicodeEncodeError as error:raise APIError('MARGIN_TEXT_ASCII','Original safety-margin text requires ASCII data.') from error
    normalized=content.replace('\r\n','\n')
    if any(ord(char)<32 and char not in '\t\n' for char in normalized):raise APIError('MARGIN_TEXT_CONTROL','Only tab and LF/CRLF control characters are supported.')
    values=[];ignored=0;incomplete=0;extra=0
    for number,line in enumerate(normalized.split('\n'),1):
        if len(line)>1022:raise APIError('MARGIN_TEXT_SIZE','A line exceeds the original 1024-byte import buffer.',number)
        beginning=line.lstrip(' ')
        if not beginning or beginning[0] not in '0123456789':
            if beginning and not beginning.startswith('//'):ignored+=1
            continue
        columns=line.replace(',','.').split('\t')
        if len(columns)<2:incomplete+=1;continue
        values.append({'position_m':float_value(columns[0]),'safety_margin_m':float_value(columns[1])})
        if len(columns)>2:extra+=1
        if len(values)>MAX_ROWS:raise APIError('ITINERARY_MARGIN_SIZE','One Itinerary supports at most 10000 margin rows.')
    return native_sort(values),{'parsed_rows':len(values),'ignored_noncomment_lines':ignored,'incomplete_numeric_lines':incomplete,'extra_column_rows':extra,
        'replacement':'Original import clears the profile before reading and sorts the accepted rows.'}


def input_text(project,args):
    if args.content is not None:content=args.content;blob=content.encode('utf8');source='inline'
    else:
        path=project.resolve(args.file_path)
        try:
            if path.stat().st_size>MAX_INPUT:raise APIError('MARGIN_TEXT_SIZE','Margin input exceeds 2 MB.')
            blob=path.read_bytes()
            if blob!=path.read_bytes():raise APIError('MARGIN_TEXT_CHANGED','Margin input changed during snapshot capture.')
        except OSError as error:raise APIError('MARGIN_TEXT_UNREADABLE','Cannot read selected margin input.',str(path)) from error
        try:content=blob.decode('utf8')
        except UnicodeDecodeError as error:raise APIError('MARGIN_TEXT_ASCII','Input must be ASCII text.') from error
        source=str(path)
    values,details=parse_text(content)
    return values,{'source':source,'bytes':len(blob),'sha256':digest(blob),**details}


def check_indices(indices,count):
    if len(indices)!=len(set(indices)):raise APIError('MARGIN_INDEX','Selected row indices must be unique.')
    if any(not 0<=index<count for index in indices):raise APIError('MARGIN_INDEX','Selected row does not exist.',{'indices':indices[:20],'row_count':count})


def edit(project,args):
    from .operations import Definitions
    document,dest=selected(project,args.name);before=rows(dest);values=copy.deepcopy(before);original_values=list(values);commands=[];imports=[]
    original=w.elements(dest.contents[5].value.contents[0].value);existing={id(value):obj for value,obj in zip(values,original)}
    shared=shared_profiles(project,dest);shared_before={}
    for name,owner,other in shared:
        previous=rows(other);shared_before[name]=(owner,previous,alias_groups(previous))
    requested=getattr(project,'_margin_edit_budget',0)+len(args.edits)
    if requested>10000:raise APIError('MARGIN_EDIT_BUDGET','A draft supports at most 10000 margin edit commands.')
    project._margin_edit_budget=requested
    for command in args.edits:
        action=command.action;change={'action':action}
        if action=='add':
            check_indices(command.selected_indices,len(values));at=max(command.selected_indices)+1 if command.selected_indices else len(values)
            source=at-1 if at else None;value=copy.deepcopy(values[source]) if source is not None else {'position_m':0.0,'safety_margin_m':0.0}
            values.insert(at,value);change.update(index=at,inherited_index=source)
        elif action=='insert':
            at=command.index
            if not values or at>len(values):raise APIError('MARGIN_INSERT_INDEX','Original insert requires an existing reference row and an index within [0,count].')
            source=at-1 if at else 0;values.insert(at,copy.deepcopy(values[source]));change.update(index=at,inherited_index=source)
        elif action=='update':
            check_indices([command.index],len(values));target=values[command.index]
            
            
            if command.safety_margin_m is not None:target['safety_margin_m']=f32(command.safety_margin_m)
            if command.position_m is not None:target['position_m']=f32(command.position_m);values=native_sort(values)
            resulting=[i for i,row in enumerate(values) if row is target]
            change.update(selected_index=command.index,resulting_index=resulting[0],resulting_indices=resulting,position_sort=command.position_m is not None)
        elif action=='delete':
            check_indices(command.indices,len(values))
            for at in sorted(command.indices,reverse=True):values.pop(at)
            change['indices']=sorted(command.indices,reverse=True)
        elif action=='clear':values=[]
        elif action=='sort':values=native_sort(values)
        elif action=='import_text':
            values,info=input_text(project,command);imports.append(info);change['import_index']=len(imports)-1
        else:raise APIError('MARGIN_COMMAND','Unknown safety-margin command.',action)
        if len(values)>MAX_ROWS:raise APIError('ITINERARY_MARGIN_SIZE','One Itinerary supports at most 10000 margin rows.')
        change['row_count']=len(values);commands.append(change)
    
    
    
    for value in original_values:existing[id(value)].contents[0].values=[f32(value['position_m']),f32(value['safety_margin_m'])]
    assign(dest,values,Definitions(project),existing);shared_changes=[]
    for name,owner,other in shared:
        previous=shared_before[name];after=rows(other)
        if previous[1]!=after or previous[2]!=alias_groups(after):shared_changes.append({'name':name,'document':owner,'before_margins':previous[1],'after_margins':after,
            'before_margin_aliases':previous[2],'after_margin_aliases':alias_groups(after)})
    return {'kind':args.kind,'name':args.name,'document':document,'before_margins':before,'after_margins':values,
        'before_margin_aliases':alias_groups(before),'after_margin_aliases':alias_groups(values),'shared_profile_changes':shared_changes,
        'shared_profiles_before':[name for name,_,_ in shared],'shared_profiles_after':[name for name,_,_ in shared_profiles(project,dest)],
        'margin_commands':commands,'imports':imports,'row_count':len(values),'course_references_preserved':True,
        'itinerary_paths_and_description_preserved':True,'native_application_started':False,'native_train_control_verified':False,
        'evidence':['itinerary-margins-contract','itinerary-margins-functions']}


def fixed(value):
    
    
    with localcontext() as context:
        context.prec=80
        number=Decimal.from_float(f32(value))
        
        
        if number:number=number.quantize(Decimal(1).scaleb(number.adjusted()-16),rounding=ROUND_HALF_UP)
        return format(number.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP),'f')


def render(name,values):
    lines=['//','// Produced by OTAI: original OpenTrack safety-margin text','// Itinerary: '+name+' ','//',
        '// -----------------------------------------------','// Position [m/], Safety Margin[ m]','// -----------------------------------------------']
    losses=0
    for row in values:
        first,second=fixed(row['position_m']),fixed(row['safety_margin_m']);lines.append(first+'\t'+second)
        if f32(float(first))!=row['position_m'] or f32(float(second))!=row['safety_margin_m']:losses+=1
    warnings=[]
    if losses:warnings.append({'kind':'two_decimal_rounding','rows':losses})
    negative=sum(row['position_m']<0 or math.copysign(1,row['position_m'])<0 for row in values)
    if negative:warnings.append({'kind':'signed_position_rows_ignored_on_native_import','rows':negative})
    if native_sort(values)!=values:warnings.append({'kind':'native_import_reorders_rows'})
    if alias_groups(values):warnings.append({'kind':'shared_row_identity_lost_on_native_import'})
    return '\n'.join(lines)+'\n',warnings


class MarginExporter:
    def __init__(self,service):self.service=service

    def read(self,args):return read(self.service,args)

    def export(self,args):
        project=self.service.project(args);profiles=[];warnings=[];blobs=[];references={};shared_by_name={}
        def ref(obj):
            if id(obj) not in references:references[id(obj)]=len(references)
            return references[id(obj)]
        for name in args.names:
            document,dest=selected(project,name);values=rows(dest);wrapper=dest.contents[5].value;array=wrapper.contents[0].value
            shared_by_name[name]=[other for other,_,_ in shared_profiles(project,dest)]
            profiles.append({'name':name,'document':document,'rows':values,'profile_reference_id':ref(wrapper),'array_reference_id':ref(array),
                'row_reference_ids':[ref(obj) for obj in w.elements(array)],'outside_selection_shared_profiles':[other for other in shared_by_name[name] if other not in args.names]})
        if sum(len(profile['rows']) for profile in profiles)>100000:raise APIError('MARGIN_EXPORT_SIZE','One export supports at most 100000 rows.')
        if args.format=='json':blobs.append(('itinerary-margins.json',json.dumps({'format':'OTAI mapped saved safety-margin data','profiles':profiles},ensure_ascii=False,indent=2).encode('utf8')))
        else:
            for number,profile in enumerate(profiles,1):
                content,issues=render(profile['name'],profile['rows']);blobs.append(('margins-'+str(number).zfill(4)+'.txt',content.encode('ascii')))
                warnings.extend({'name':profile['name'],**issue} for issue in issues)
                
                
                
                if shared_by_name[profile['name']]:warnings.append({'name':profile['name'],
                    'kind':'cross_itinerary_shared_references_not_represented',
                    'shared_profiles':shared_by_name[profile['name']]})
        folder=inside(self.service.work/('export-'+uuid.uuid4().hex[:16]),[self.service.work]);folder.mkdir(parents=True,exist_ok=False);files=[]
        for name,blob in blobs:
            path=folder/name;path.write_bytes(blob);files.append({'file':str(path),'sha256':digest(blob),'bytes':len(blob)})
        report={'format':args.format,'source_project':str(project.project),'source_digest':project.source_digest,'profile_count':len(profiles),
            'row_count':sum(len(profile['rows']) for profile in profiles),'file_count':len(files),'files':files[:20],'files_truncated':len(files)>20,
            'warnings':warnings[:20],'warning_count':len(warnings),'source_files_unchanged':all(digest(Path(name).read_bytes())==digest(blob) for name,blob in project.sources.items()),
            'native_application_started':False,'native_train_control_verified':False}
        manifest=folder/'manifest.json';manifest.write_text(json.dumps({**report,'files':files,'warnings':warnings,
            'ownership':[{'name':profile['name'],'document':profile['document'],'row_count':len(profile['rows'])} for profile in profiles]},ensure_ascii=False,indent=2),encoding='utf8')
        report['manifest']=str(manifest);return report
