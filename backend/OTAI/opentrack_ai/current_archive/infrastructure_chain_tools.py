"""One in-memory topology-to-itinerary transaction; never exports files."""
from typing import Annotated,Literal
from pydantic import Field
from .tools import Input,ArchiveTools,PathText,sha
from .bundle_tools import Source
from .network_generation_tools import Network,MainSignal,Route,Text
from .finite_topology_tools import PointStation
from ..errors import APIError
class PathPlan(Input):
    name:Text
    routes:Annotated[list[Text],Field(min_length=1,max_length=100)]
class ItineraryPlan(Input):
    name:Text
    paths:Annotated[list[Text],Field(min_length=1,max_length=100)]
class PreviewInfrastructureChain(Input):
    domain:Literal['single_document_infrastructure_chain']
    header:Source
    shapes:Source
    document_name:Annotated[str,Field(strict=True,pattern=r'^[A-Za-z][A-Za-z0-9_]{0,39}$')]
    document_path:PathText
    network:Network
    stations:Annotated[list[PointStation],Field(max_length=100)]
    signals:Annotated[list[MainSignal],Field(min_length=1,max_length=100)]
    routes:Annotated[list[Route],Field(min_length=1,max_length=100)]
    paths:Annotated[list[PathPlan],Field(min_length=1,max_length=100)]
    itineraries:Annotated[list[ItineraryPlan],Field(min_length=1,max_length=100)]
    preview_only:Literal[True]=True
class InfrastructureChainTools(ArchiveTools):
    def preview(self,args):
        from .infrastructure_chain_workflow import compose_infrastructure
        inputs={};data={}
        for key in('header','shapes'):
            source=getattr(args,key);path=self.path(source.path);blob=self.secure_bytes(path)
            if sha(blob)!=source.sha256:raise APIError('SOURCE_CHANGED','Exact donor SHA mismatch',key)
            if len(blob)>128*1024*1024:raise APIError('INFRASTRUCTURE_SIZE','Donor exceeds128MiB')
            inputs[path]=blob;data[key]=blob
        spec=args.model_dump(exclude={'domain','header','shapes','preview_only'});spec['network']=args.network.core_spec()
        try:members,report=compose_infrastructure(data['header'],data['shapes'],expected_hashes={k:sha(v)for k,v in data.items()},spec=spec)
        except(ValueError,TypeError,KeyError,IndexError,OverflowError)as exc:raise APIError('INFRASTRUCTURE_CHAIN_INVALID','Outside single-document explicit infrastructure domain',str(exc)[:500])from exc
        for path,blob in inputs.items():
            if self.secure_bytes(path)!=blob:raise APIError('SOURCE_CHANGED','Donor changed during preview')
        return {'tool':'opentrack_preview_infrastructure_chain','preview_only':True,'saved':False,'publication_review_pending':True,'report':report,'outputs':{k:{'sha256':sha(v),'bytes':len(v)}for k,v in members.items()},'limitations':['One document only, no Connector or repeated/cyclic Route/Path/Itinerary.','Explicit routes, not automatic route search or engineered railway alignment.','Point stations are not stopping areas; no vehicles, timetable, run or operational readiness.','Files are generated only in memory, never exported.']}
def tool_definitions(root):
    s=InfrastructureChainTools(root)
    return [('opentrack_preview_infrastructure_chain','Pure-memory single-document explicit topology → main signals → Routes → point stations → Paths → Itineraries and matching DestInfo. Exact references and fresh reload. No connector, route search, operating service, export or native execution.',PreviewInfrastructureChain,s.preview)]
