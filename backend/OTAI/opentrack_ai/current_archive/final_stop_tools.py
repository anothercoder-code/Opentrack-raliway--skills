"""Explicit final-stop preview. Separate domain from frozen pass-only behavior."""
from typing import Annotated,Literal
from pydantic import Field,StrictBool
from .infrastructure_chain_tools import PreviewInfrastructureChain
from .operating_chain_tools import PreviewOperatingChain
from .terminal_generation_schema import AreaStation
from .network_generation_tools import Text
from .tools import Input,ArchiveTools,sha
from ..errors import APIError
class FinalStopInfrastructure(PreviewInfrastructureChain):
    domain:Literal['single_document_final_stop_infrastructure']
    stations:Annotated[list[AreaStation],Field(min_length=2,max_length=100)]
class StopVisit(Input):
    station_sign:Text
    absolute_seconds:Annotated[int,Field(strict=True,ge=0,le=366*86400)]
    stop:StrictBool
class StopPlan(Input):
    course_id:Text
    train:Text
    itinerary:Text
    visits:Annotated[list[StopVisit],Field(min_length=2,max_length=100)]
class PreviewFinalStopChain(PreviewOperatingChain):
    domain:Literal['single_document_final_stop_chain']
    infrastructure:FinalStopInfrastructure
    plan:Annotated[list[StopPlan],Field(min_length=1,max_length=100)]
class FinalStopTools(ArchiveTools):
    def preview(self,args):
        from .final_stop_workflow import compose_final_stop_chain
        specs={k:getattr(args,k)for k in('depot_template','trains_template','courses_template','timetable_template')};specs.update({k:getattr(args.infrastructure,k)for k in('header','shapes')});inputs={};sources={};total=0
        for key,source in specs.items():
            path=self.path(source.path);blob=self.secure_bytes(path);total+=len(blob)
            if sha(blob)!=source.sha256:raise APIError('SOURCE_CHANGED','Exact donor SHA mismatch',key)
            if total>256*1024*1024:raise APIError('FINAL_STOP_SIZE','Donors exceed256MiB')
            inputs[path]=blob;sources[key]=blob
        infrastructure=args.infrastructure.model_dump(exclude={'domain','header','shapes','preview_only'});infrastructure['network']=args.infrastructure.network.core_spec()
        try:members,report=compose_final_stop_chain(sources,expected_hashes={k:sha(v)for k,v in sources.items()},infrastructure=infrastructure,vehicles=args.vehicles.model_dump(),course_template_id=args.course_template_id,timetable_template_key=args.timetable_template_key,train_types=args.train_types,speed_type=args.speed_type,plan=[p.model_dump()for p in args.plan],run_configuration=args.run_configuration.model_dump())
        except(ValueError,TypeError,KeyError,IndexError,OverflowError)as exc:raise APIError('FINAL_STOP_INVALID','Outside explicit final-stop area domain',str(exc)[:500])from exc
        for path,blob in inputs.items():
            if self.secure_bytes(path)!=blob:raise APIError('SOURCE_CHANGED','Donor changed during preview')
        return {'tool':'opentrack_preview_final_stop_chain','preview_only':True,'saved':False,'publication_review_pending':True,'report':report,'outputs':{k:{'bytes':len(v),'sha256':sha(v)}for k,v in members.items()},'limitations':['Static final-only forward stop in explicit single-Edge area, not observed stopping.','No dwell, intermediate stops, reverse stop, turnround, connection or fleet-circulation claim.','All area endpoints, lengths, signals and follow-on topology are user-specified, never auto-added.','Eight members in memory only; no export/output directory/native execution.']}
def tool_definitions(root):
    s=FinalStopTools(root)
    return [('opentrack_preview_final_stop_chain','Compose explicit single-document topology and forward terminal stop area with actual length/signal/Station references, final-only zero-dwell service data and six-catalog run binding. Eight-member static preview; no intermediate stop, turnround, export or native execution.',PreviewFinalStopChain,s.preview)]
