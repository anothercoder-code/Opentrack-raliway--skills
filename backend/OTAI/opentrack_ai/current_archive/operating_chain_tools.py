"""One preview of infrastructure, vehicle/service catalogs and run binding."""
from typing import Annotated,Literal
from pydantic import Field,model_validator
from .tools import Input,ArchiveTools,sha
from .bundle_tools import Source
from .infrastructure_chain_tools import PreviewInfrastructureChain
from .operating_generation_tools import Vehicles,CoursePlan,RunConfiguration,Text
from ..errors import APIError
class WindowsRunConfiguration(RunConfiguration):
    path_style:Literal['windows']
    @model_validator(mode='after')
    def nonoverlap(self):
        a=self.run_filename.casefold();b=self.output_directory.casefold()
        if a==b or a.startswith(b+'/') or b.startswith(a+'/'):raise ValueError('Output directory overlaps final run member')
        return self
class PreviewOperatingChain(Input):
    domain:Literal['single_document_pass_operating_chain']
    infrastructure:PreviewInfrastructureChain
    depot_template:Source
    trains_template:Source
    courses_template:Source
    timetable_template:Source
    vehicles:Vehicles
    course_template_id:Text
    timetable_template_key:Text
    train_types:Annotated[list[Text],Field(min_length=1,max_length=100)]
    speed_type:Text
    plan:Annotated[list[CoursePlan],Field(min_length=1,max_length=1000)]
    run_configuration:WindowsRunConfiguration
    preview_only:Literal[True]=True
class OperatingChainTools(ArchiveTools):
    def preview(self,args):
        from .operating_chain_workflow import compose_operating_chain
        specs={k:getattr(args,k)for k in('depot_template','trains_template','courses_template','timetable_template')};specs.update({k:getattr(args.infrastructure,k)for k in('header','shapes')})
        inputs={};sources={};total=0
        for key,source in specs.items():
            path=self.path(source.path);blob=self.secure_bytes(path);total+=len(blob)
            if sha(blob)!=source.sha256:raise APIError('SOURCE_CHANGED','Exact donor SHA mismatch',key)
            if total>256*1024*1024:raise APIError('OPERATING_CHAIN_SIZE','Donors exceed256MiB total')
            inputs[path]=blob;sources[key]=blob
        infra=args.infrastructure.model_dump(exclude={'domain','header','shapes','preview_only'});infra['network']=args.infrastructure.network.core_spec()
        try:members,report=compose_operating_chain(sources,expected_hashes={k:sha(v)for k,v in sources.items()},infrastructure=infra,vehicles=args.vehicles.model_dump(),course_template_id=args.course_template_id,timetable_template_key=args.timetable_template_key,train_types=args.train_types,speed_type=args.speed_type,plan=[p.model_dump()for p in args.plan],run_configuration=args.run_configuration.model_dump())
        except(ValueError,TypeError,KeyError,IndexError,OverflowError)as exc:raise APIError('OPERATING_CHAIN_INVALID','Outside single-document pass operating domain',str(exc)[:500])from exc
        for path,blob in inputs.items():
            if self.secure_bytes(path)!=blob:raise APIError('SOURCE_CHANGED','Donor changed during preview')
        return {'tool':'opentrack_preview_operating_chain','preview_only':True,'saved':False,'publication_review_pending':True,'report':report,'outputs':{k:{'sha256':sha(v),'bytes':len(v)}for k,v in members.items()},'limitations':['Eight static members, not an executed simulation.','Single-engine no-trailer inherited template physics; no calibrated vehicle or physical fleet circulation claim.','Pass-only point stations, arrival equals departure, zero dwell; no stop or turnround.','Explicit ordered speed types and absolute planned seconds; lower-bound checks are not conflict-free scheduling.','No files or output directory are created.']}
def tool_definitions(root):
    s=OperatingChainTools(root)
    return [('opentrack_preview_operating_chain','Compose one explicit single-document infrastructure chain with generated single-engine Train/Engine definitions, pass-only Courses/Timetables and six-catalog run bindings. Exact SHA/reference/day/time checks, eight in-memory members. No export, stops, circulation, runtime or simulation.',PreviewOperatingChain,s.preview)]
