"""Typed current Station/Route/Train-Incident archive operations; no simulation."""
from typing import Annotated
from pathlib import Path
from pydantic import Field,StrictStr,StrictInt,StrictBool,model_validator
from .tools import Input,PathText,sha
from .bundle_tools import Source
from .next_tools import NextFunctions,Save
from .operation_tools import Name,SignedI32,RouteSelector
from .following_tools import Finite,Changes
from . import writer as w,catalogs as c
from ..errors import APIError
from ..json_safe import checked_json

AsciiName=Annotated[StrictStr,Field(min_length=1,max_length=2000,pattern=r'^[ -~]+$')]
Clock=Annotated[StrictStr,Field(pattern=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$')]
Char=Annotated[StrictInt,Field(ge=-128,le=127)]
class StationChanges(Input):
    display_name:Annotated[StrictStr,Field(max_length=1048576)]|None=None
    altitude_raw:SignedI32|None=None
    coord_x_raw:SignedI32|None=None
    coord_y_raw:SignedI32|None=None
    timing_point:StrictBool|Char|None=None
    @model_validator(mode='after')
    def supplied(self):
        if not self.model_fields_set:raise ValueError('Nonempty changes required')
        if any(getattr(self,k) is None for k in self.model_fields_set if k!='display_name'):raise ValueError('Only display_name accepts native nil')
        return self
class InspectStation(Input):
    source_path:PathText
    station_sign:Name
class EditStation(Save):
    source:Source
    station_sign:Name
    changes:StationChanges
class CreateRoute(Save):
    project_run:Source
    documents:Annotated[dict[Name,Source],Field(min_length=1,max_length=100)]
    target_document:Name
    template:RouteSelector
    name:Name
    end_ids:Annotated[list[SignedI32],Field(min_length=2,max_length=10000)]
    description:StrictStr=''
class InspectIncidents(Input):
    source_path:PathText
class IncidentSources(Save):
    project_run:Source
    source:Source
    trains:Source
class CreateIncident(IncidentSources):
    name:AsciiName
    course_id:AsciiName
    begin_time:Clock
    end_time:Clock
    enabled:StrictBool=False
    reduced_speed_kmh:Finite=0.0
class IncidentChanges(Changes):
    name:AsciiName|None=None
    enabled:StrictBool|None=None
    reduced_speed_kmh:Finite|None=None
class EditIncident(IncidentSources):
    name:AsciiName
    changes:IncidentChanges

class UpcomingFunctions(NextFunctions):
    def inspect_station(self,args):
        from . import station_operations as s
        _,blob,_,_=self.read(args.source_path)
        try:
            _,_,station=s._state(blob,args.station_sign)
            values={k:station.contents[g].values[slot] for k,(g,slot,_) in s.FIELDS.items()}
            values['display_name']=None if values['display_name'] is None else c.text(values['display_name'])
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_STATION_OPERATION',str(e)[:500]) from e
        return checked_json({'source_path':args.source_path,'source_sha256':sha(blob),'station_sign':args.station_sign,'values':values,'coordinate_and_altitude_units':'raw_native_integers_unverified_units','native_application_started':False})
    def station(self,args):
        from . import station_operations as s
        path,blob,_,_=self.checked(args.source)
        try:output,report=s.patch_station_archive(blob,args.station_sign,args.changes.model_dump(exclude_unset=True))
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_STATION_OPERATION',str(e)[:500]) from e
        return self.finish(args,path,blob,output,report)
    def route(self,args):
        from . import route_factory as f,path_functions as pf
        inputs={key:self.checked(spec) for key,spec in args.documents.items()}
        if args.target_document not in inputs:raise APIError('DOCUMENT_SCOPE','Target document missing')
        if len({x[0] for x in inputs.values()})!=len(inputs):raise APIError('DOCUMENT_SCOPE','Distinct document files required')
        runpath,runblob,scope_check,evidence=self.checked_document_list(args,inputs)
        path,blob,_,_=inputs[args.target_document]
        try:
            from .graph_references import reference_inventory
            for key,(_,_,root,_) in inputs.items():
                f.document(root)  
                expected=['i','i','@','i','i','@','@','@','ffff','ffff','ffff','f','@','@','ffff','iii','ff','@','@','@','@']
                if [g.encodings for g in root.contents]!=[[bytes([x]) for x in e.encode()] for e in expected]:raise ValueError('Unsupported current document field-group layout')
                objects,_=reference_inventory(root)
                for obj in objects:
                    kind=w.kind(obj)
                    if kind=='OTEndModel':
                        f.layout(obj,'OTEndModel',7,f.END,graphic=True)
                        for index,container_kind,member_kind in [(15,'OTRouteList','OTRoute'),(16,'OTShuntingList',None),(17,'OTPathList','OTPath')]:
                            container=obj.contents[index].value
                            if container is None:continue
                            members=f.wrapper(container,container_kind)
                            if member_kind is None and members:raise ValueError('Nonempty ShuntingList outside reviewed project dependency domain')
                            for member in members:
                                if w.kind(member)!=member_kind:raise ValueError('Unknown RSP member in dependency owner list')
                                pf.info(member)
                    if kind in ('OTRoute','OTPath','OTDest'):pf.info(obj)
                    if kind in ('OTArrayInfo','OTArrayExtInfo'):
                        pf.hierarchy(obj,([('OTArrayExtInfo',0)] if kind=='OTArrayExtInfo' else [])+[('OTArrayInfo',0),('NSObject',0)])
                        shape=[[b'@'],[b'i',b'i']]+([[b'@']] if kind=='OTArrayExtInfo' else [])
                        if [g.encodings for g in obj.contents]!=shape or any(len(g.values)!=len(g.encodings) for g in obj.contents):raise ValueError('Unsupported saved reference layout')
                        if any(type(v) is not int or not -2147483648<=v<=2147483647 for v in obj.contents[1].values):raise ValueError('Invalid saved reference identity')
                        pf.string(obj.contents[0].value)
                        if kind=='OTArrayExtInfo':pf.string(obj.contents[2].value)
                    if w.kind(obj)=='OTRoute' and c.text(obj.contents[1].value)==args.name:raise ValueError('Route name already exists in supplied project documents')
                    if w.kind(obj) in ('OTArrayInfo','OTArrayExtInfo') and c.text(obj.contents[0].value)==args.name:raise ValueError('New Route name would capture an existing saved reference')
            output,report=f.create_route_from_template(blob,template=args.template.model_dump(),name=args.name,end_ids=args.end_ids,description=args.description)
            created=report['created']
            for key,(_,_,root,_) in inputs.items():
                if key==args.target_document:continue
                for obj in w.objects(root):
                    if w.kind(obj)=='OTArrayExtInfo' and c.text(obj.contents[2].value)==args.target_document and obj.contents[1].values==[created['array_id'],created['start_id']]:
                        raise ValueError('New Route identity would capture an external saved reference')
            report['document_scope']=evidence
            report['project_wide_name_uniqueness']='verified within actual run-matched project archive inventory'
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_ROUTE_FACTORY',str(e)[:500]) from e
        return self.finish(args,path,blob,output,report,{runpath:runblob,**{v[0]:v[1] for k,v in inputs.items() if k!=args.target_document}},scope_check)
    def incident_scope(self,args,course_id):
        path,blob,root,_=self.checked(args.source);tp,tb,tr,_=self.checked(args.trains)
        rp=self.path(args.project_run.path);rb=self.secure_bytes(rp)
        if sha(rb)!=args.project_run.sha256:raise APIError('SOURCE_CHANGED','Run differs from inspected SHA')
        self.same_project([path,tp,rp]);project=self.root.joinpath(*self.project_scope(rp))
        if rp.parent!=project or rp.suffix!='.run':raise APIError('INCIDENT_SCOPE','Run must be directly inside the selected project')
        try:lines=rb.decode('ascii').splitlines()
        except UnicodeDecodeError as e:raise APIError('INCIDENT_SCOPE','ASCII run key#value# subset required') from e
        bindings={}
        for line in lines:
            if not line.strip() or line.startswith('//'):continue
            parts=line.split('#')
            if len(parts)!=3 or parts[2]!='':raise APIError('INCIDENT_SCOPE','Malformed run record')
            if parts[0] not in ('CourseFile','TrainFile'):continue
            key,raw=parts[:2]
            if key in bindings or not raw or '%' in raw or '\\' in raw or '..' in Path(raw).parts:raise APIError('INCIDENT_SCOPE','Unique explicit catalog binding required')
            candidate=Path(raw) if Path(raw).is_absolute() else project/raw
            try:relative=candidate.relative_to(self.root).as_posix()
            except ValueError as e:raise APIError('INCIDENT_SCOPE','Catalog outside authorized root') from e
            bindings[key]=self.path(relative)
        if bindings!={'CourseFile':path,'TrainFile':tp} or path==tp:raise APIError('INCIDENT_SCOPE','Supplied Course/Train must match run bindings exactly')
        try:
            courses={c.text(x.contents[0].value):x for x in c.course_items(root)}
            trains={c.text(x.contents[0].value):x for x in c.train_items(tr)}
            if course_id not in courses or courses[course_id].contents[5].value!=1:raise ValueError('Enabled selected Course required')
            train=c.text(courses[course_id].contents[3].value)
            if train not in trains:raise ValueError('Selected Course must resolve to actual current Train')
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('INCIDENT_SCOPE',str(e)[:500]) from e
        return path,blob,{rp:rb,tp:tb},{'course_id':course_id,'train_name':train,'run_catalog_bindings_matched':True,'scope':'Current Train-type Incident archive only; not runtime or full Project dependency closure'}
    @staticmethod
    def incident_rows(blob):
        from . import incident_operations as i
        _,_,_,incidents,_=i.state(blob)
        return [{'name':c.text(o.contents[0].value),'course_id':c.text(o.contents[1].value),'begin_time':c.text(o.contents[3].value),'end_time':c.text(o.contents[4].value),'enabled':bool(o.contents[7].value),'reduced_speed_kmh':o.contents[6].values[0],'incident_type':1,'class_version':12} for o in incidents]
    def inspect_incidents(self,args):
        _,blob,_,_=self.read(args.source_path)
        try:rows=self.incident_rows(blob)
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_INCIDENT_OPERATION',str(e)[:500]) from e
        return checked_json({'source_path':args.source_path,'source_sha256':sha(blob),'incidents':rows,'supported_profile':'current12 Train type1 only','native_application_started':False})
    def incident_create(self,args):
        from . import incident_operations as i
        path,blob,dependencies,scope=self.incident_scope(args,args.course_id)
        try:output=i.create_train_incident(blob,**{k:getattr(args,k) for k in ('name','course_id','begin_time','end_time','enabled','reduced_speed_kmh')})
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_INCIDENT_OPERATION',str(e)[:500]) from e
        report={'operation':'create_train_incident','scope':scope,'created':self.incident_rows(output)[-1],'native_init_equivalent':False,'simulation_verified':False}
        return self.finish(args,path,blob,output,report,dependencies)
    def incident_edit(self,args):
        from . import incident_operations as i
        _,blob,_,_=self.checked(args.source)
        try:
            selected=[r for r in self.incident_rows(blob) if r['name']==args.name]
            if len(selected)!=1:raise ValueError('Exact Incident name required')
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_INCIDENT_OPERATION',str(e)[:500]) from e
        path,blob,dependencies,scope=self.incident_scope(args,selected[0]['course_id'])
        try:output=i.patch_train_incident(blob,name=args.name,changes=args.changes.model_dump(exclude_unset=True))
        except (ValueError,TypeError,IndexError,OverflowError) as e:raise APIError('CURRENT_INCIDENT_OPERATION',str(e)[:500]) from e
        final_name=args.changes.name if 'name' in args.changes.model_fields_set else args.name
        report={'operation':'edit_train_incident','scope':scope,'before':selected[0],'after':next(r for r in self.incident_rows(output) if r['name']==final_name),'simulation_verified':False}
        return self.finish(args,path,blob,output,report,dependencies)

def tool_definitions(root):
    service=UpcomingFunctions(root)
    return [
      ('opentrack_inspect_current_station','Read selected Station3 saved display name, raw int32 altitude/XY and timing flag; source SHA. No physical unit inference.',InspectStation,service.inspect_station),
      ('opentrack_edit_current_station','Station3 existing-record setters only; name string/nil isolated copy, raw int32 altitude/XY and signed-char timing normalization. No catalog identity rename. Preview/fresh copy only.',EditStation,service.station,False,False),
      ('opentrack_create_current_route','Create distinct Route over same explicit existing movement/template, native highestGivenRspID+1 and fresh indications/backrefs. Verify run/document inventory; no new geometry or native init/copy equivalence.',CreateRoute,service.route,False,False),
      ('opentrack_inspect_current_train_incidents','Inspect current Incident12 Train type1 archive profile only; rejects legacy/other event profiles. No runtime execution.',InspectIncidents,service.inspect_incidents),
      ('opentrack_create_current_train_incident','Construct current Incident12 Train event with enabled same-run Course and actual Train; canonical same-day times, finite float32 reduced speed. Defaults disabled. Archive only, preview/fresh copy.',CreateIncident,service.incident_create,False,False),
      ('opentrack_edit_current_train_incident','Edit current Train Incident name/use/reduced speed only; verify run Course/Train bindings. No other event type or simulation. Preview/fresh copy.',EditIncident,service.incident_edit,False,False),
    ]
