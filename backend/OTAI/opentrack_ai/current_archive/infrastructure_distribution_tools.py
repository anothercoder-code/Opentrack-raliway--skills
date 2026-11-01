"""Current named distribution/edge data operations; never execute simulations."""
from pathlib import Path
from typing import Annotated, Literal
from pydantic import Field, StrictInt, StrictFloat
from .tools import Input, PathText, sha
from .bundle_tools import Source
from .next_tools import NextFunctions, Save, Ordinal
from .operation_tools import Name, SignedI32
from ..errors import APIError
from ..json_safe import checked_json
from . import named_distributions as nd, edge_operations as edges, distribution_references as refs
Number=StrictInt|StrictFloat
Policy=Literal['native_setter','piecewise_linear_guard']
class InspectEdge(Input):
    source_path:PathText
    model_id:SignedI32
class EditEdge(Save):
    source:Source
    model_id:SignedI32
    changes:Annotated[dict[Literal['length_m','radius_m','gradient_per_mille'],Number],Field(min_length=1,max_length=3)]
class InspectDistributions(Input):
    source_path:PathText
class Interval(Input):
    lower_s:Number
    upper_s:Number
    percentage:Number
Rows=Annotated[list[Interval],Field(max_length=10000)]
class Replace(Input):
    action:Literal['replace_intervals']
    name:Name
    rows:Rows
class Edit(Input):
    action:Literal['edit_interval']
    name:Name
    index:Ordinal
    changes:Annotated[dict[Literal['lower_s','upper_s','percentage'],Number],Field(min_length=1,max_length=3)]
class Insert(Input):
    action:Literal['insert_interval']
    name:Name
    index:Ordinal
    interval:Interval
class Delete(Input):
    action:Literal['delete_interval']
    name:Name
    index:Ordinal
class New(Input):
    action:Literal['new']
    template_name:Name
    new_name:Name
    current_class:Literal['OTDistribution:1']
    intervals:Rows
class Copy(Input):
    action:Literal['copy']
    template_name:Name
    new_name:Name
    current_class:Literal['OTDistribution:1']
Action=Annotated[Replace|Edit|Insert|Delete|New|Copy,Field(discriminator='action')]
class EditDistributions(Save):
    source:Source
    policy:Policy
    operation:Action
class AuditReferences(Input):
    project_run:Source
    catalogs:Annotated[dict[Literal['courses','timetable'],Source],Field(min_length=1,max_length=2)]
    name:Name|None=None

class InfrastructureDistributionFunctions(NextFunctions):
    @staticmethod
    def invoke(fn,*args,**kw):
        try:return fn(*args,**kw)
        except (ValueError,TypeError,IndexError,OverflowError) as exc:raise APIError('CURRENT_INFRASTRUCTURE_DISTRIBUTION',str(exc)[:500]) from exc
    def inspect_edge(self,args):
        _,blob,_,_=self.read(args.source_path)
        _,version,edge=self.invoke(edges.state,blob,args.model_id)
        values=edge.contents[9].values
        return checked_json({'source_path':args.source_path,'source_sha256':sha(blob),'model_id':args.model_id,'length_m':values[1],'radius_m':edges.float_report(values[2]),'gradient_per_mille':edges.float_report(values[3]),'native_application_started':False,'physical_validity_checked':False})
    def edit_edge(self,args):
        path,blob,_,_=self.checked(args.source)
        keys={'length_m':'length_m','radius_m':'radius_raw','gradient_per_mille':'gradient_raw'}
        output,report=self.invoke(edges.patch_edge_archive,blob,args.model_id,{keys[k]:v for k,v in args.changes.items()})
        report['typed_api_units']={'length_m':'metres','radius_m':'metres','gradient_per_mille':'per_mille'}
        report['unit_evidence']='current C getter/call chain and manual; nonzero gradient readonly corroboration'
        return self.finish(args,path,blob,output,report)
    def inspect_distributions(self,args):
        _,blob,root,_=self.read(args.source_path)
        return checked_json({'source_path':args.source_path,'source_sha256':sha(blob),'distributions':self.invoke(nd.details,root),'scope':'OTCourseList3 group3 OTDistribution1 only; unrelated records opaque, not whole-file current certification','named_business_function':'piecewise linear code1 only; names are not enum values','native_application_started':False})
    def edit_distributions(self,args):
        path,blob,_,_=self.checked(args.source)
        kw=args.operation.model_dump();action=kw.pop('action');kw['policy']=args.policy
        if action in ('insert_interval','delete_interval'):
            kw['action']='insert' if action=='insert_interval' else 'delete';action='change_interval_count'
        elif action in ('new','copy'):kw['mode']=action;action='create'
        output,report=self.invoke(nd.transform,blob,action,**kw)
        report['scope']='current named distribution schema only; unrelated CourseList records preserved opaque'
        report['rename_supported']=False;report['whole_distribution_delete_supported']=False
        return self.finish(args,path,blob,output,report)
    def audit_references(self,args):
        rp=self.path(args.project_run.path);rb=self.secure_bytes(rp)
        if sha(rb)!=args.project_run.sha256:raise APIError('SOURCE_CHANGED','Run differs from inspected SHA')
        project=self.root.joinpath(*self.project_scope(rp))
        if rp.parent!=project or rp.suffix!='.run':raise APIError('DISTRIBUTION_SCOPE','Run must be directly inside selected project')
        try:lines=rb.decode('ascii').splitlines()
        except UnicodeError as exc:raise APIError('DISTRIBUTION_SCOPE','ASCII run bindings required') from exc
        inputs={rp:rb};descriptors={}
        for role,spec in args.catalogs.items():
            path,blob,_,_=self.checked(spec);self.same_project([rp,path])
            key=refs.CATALOG_KEYS[role];matches=[line.split('#') for line in lines if line.split('#')[0]==key]
            if len(matches)!=1 or len(matches[0])!=3 or matches[0][2] or not matches[0][1]:raise APIError('DISTRIBUTION_SCOPE','Unique exact run binding required: '+key)
            raw=matches[0][1]
            if '%' in raw or '\\' in raw or '..' in Path(raw).parts:raise APIError('DISTRIBUTION_SCOPE','Ambiguous catalog path')
            candidate=Path(raw) if Path(raw).is_absolute() else project/raw
            try:relative=candidate.relative_to(self.root).as_posix()
            except ValueError as exc:raise APIError('DISTRIBUTION_SCOPE','Catalog outside root') from exc
            if self.path(relative)!=path:raise APIError('DISTRIBUTION_SCOPE','Supplied catalog differs from run binding')
            inputs[path]=blob;descriptors[role]={'run_path':raw,'bytes':blob,'sha256':spec.sha256}
        result=self.invoke(refs.inspect_references,run_bytes=rb,catalogs=descriptors,name=args.name)
        result['input_sources']=[{'path':str(p.relative_to(self.root)),'sha256':sha(b)} for p,b in inputs.items()]
        result['native_application_started']=False
        for p,b in inputs.items():
            if self.secure_bytes(p)!=b:raise APIError('SOURCE_CHANGED','Input changed during reference audit')
        return checked_json(result)

def tool_definitions(root):
    s=InfrastructureDistributionFunctions(root)
    return [
      ('opentrack_inspect_current_edge','Read selected current Edge3 signed length metres, float32 radius metres and gradient per mille; no geometry validity or simulation.',InspectEdge,s.inspect_edge),
      ('opentrack_edit_current_edge','Edit existing Edge3 scalar fields by global modelID, retaining End/Route references. Finite float32 and int32 API domains; preview/fresh copy only, no simulation.',EditEdge,s.edit_edge,False,False),
      ('opentrack_inspect_named_distributions','Read current named OTDistribution1 records in CourseList3 group3. Piecewise linear code1 business domain; names are not enum values; other records opaque.',InspectDistributions,s.inspect_distributions),
      ('opentrack_edit_named_distributions','Edit/replace/insert/delete interval rows or create/copy from explicit existing named template. Explicit validation policy, code1 only. No whole-distribution rename/delete, migration or sampling. Preview/fresh copy.',EditDistributions,s.edit_distributions,False,False),
      ('opentrack_audit_distribution_references','Read-only run/SHA-bound named Distribution reference audit for validated Timetable9 and Incident12 consumers. Unknown versions and missing scopes remain unresolved; never authorizes rename/delete.',AuditReferences,s.audit_references),
    ]
