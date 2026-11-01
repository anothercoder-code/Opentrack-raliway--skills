"""Typed finite topology generation preview, no filesystem publication."""
from typing import Annotated,Literal
from pydantic import Field,StrictBool
from .tools import Input,ArchiveTools,sha
from .bundle_tools import Source
from .network_generation_tools import Network,Text,EndRef,Number
from ..errors import APIError
from .graphic_alignment import GraphicPlacement as Placement
class PointStation(EndRef):
    sign:Text
    name:Text
    placement:Placement
    timing_point:StrictBool
class Document(Input):
    name:Annotated[str,Field(strict=True,pattern=r'^[A-Za-z][A-Za-z0-9_]{0,39}$')]
    network:Network
    stations:Annotated[list[PointStation],Field(max_length=400)]
class ConnectorEnd(EndRef):
    document:Text
class Connector(Input):
    a:ConnectorEnd
    b:ConnectorEnd
class PreviewFiniteTopology(Input):
    domain:Literal['finite_explicit_topology']
    header:Source
    shapes:Source
    documents:Annotated[list[Document],Field(min_length=1,max_length=16)]
    connectors:Annotated[list[Connector],Field(max_length=400)]
    preview_only:Literal[True]=True
class FiniteTopologyTools(ArchiveTools):
    def preview(self,args):
        from .finite_topology_workflow import generate_finite_topology
        inputs={};data={}
        for role in('header','shapes'):
            source=getattr(args,role);path=self.path(source.path);blob=self.secure_bytes(path)
            if sha(blob)!=source.sha256:raise APIError('SOURCE_CHANGED','Exact donor SHA differs',role)
            if len(blob)>128*1024*1024:raise APIError('FINITE_TOPOLOGY_SIZE','Donor exceeds128MiB')
            inputs[path]=blob;data[role]=blob
        docs=[]
        for doc in args.documents:
            spec=doc.model_dump();spec['network']=doc.network.core_spec();docs.append(spec)
        try:
            members,report=generate_finite_topology(data['header'],data['shapes'],expected_hashes={k:sha(v)for k,v in data.items()},documents=docs,connectors=[x.model_dump()for x in args.connectors])
        except(ValueError,TypeError,KeyError,IndexError,OverflowError)as exc:
            raise APIError('FINITE_TOPOLOGY_INVALID','Outside explicit finite topology domain',str(exc)[:500])from exc
        for path,blob in inputs.items():
            if self.secure_bytes(path)!=blob:raise APIError('SOURCE_CHANGED','Donor changed during preview')
        return {'tool':'opentrack_preview_finite_explicit_topology','preview_only':True,'saved':False,'report':report,'outputs':{k:{'bytes':len(v),'sha256':sha(v)}for k,v in members.items()},'native_runtime_ready':False,'publication_review_pending':True,'limitations':['Tool bounds are not original software bounds.','Point stations only; no stopping areas or automatic routes/paths/traffic.','Geometric crossings do not imply connectivity.','No files exported; topology validation is not operational or native-runtime validation.']}
def tool_definitions(root):
    service=FiniteTopologyTools(root)
    return [('opentrack_preview_finite_explicit_topology','Generate explicit finite multi-document double-vertex/edge topology, point stations and reciprocal free-half-end connectors. Fresh decode/reference checks. No routes, traffic, native execution, saving or export.',PreviewFiniteTopology,service.preview)]
