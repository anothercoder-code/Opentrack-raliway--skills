"""Typed finite topology generation and publication."""
from typing import Annotated,Literal
from pydantic import Field,StrictBool
from .tools import Input,ArchiveTools,sha
from .project_candidate_publication import ProjectSave,project_target,publish_candidate
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
class PreviewFiniteTopology(ProjectSave):
    domain:Literal['finite_explicit_topology']
    header:Source
    shapes:Source
    documents:Annotated[list[Document],Field(min_length=1,max_length=16)]
    connectors:Annotated[list[Connector],Field(max_length=400)]
class FiniteTopologyTools(ArchiveTools):
    def preview(self,args):
        target=project_target(self,args)
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
        def recheck():
            for path,blob in inputs.items():
                if self.secure_bytes(path)!=blob:
                    raise APIError('SOURCE_CHANGED','Donor changed during preparation or publication')
        recheck()
        result={'tool':'opentrack_preview_finite_explicit_topology','preview_only':args.preview_only,'saved':False,'report':report,'outputs':{k:{'bytes':len(v),'sha256':sha(v)}for k,v in members.items()},'native_runtime_ready':False,'publication_review_pending':True,'limitations':['Tool bounds are not original software bounds.','Point stations only; no stopping areas or automatic routes/paths/traffic.','Geometric crossings do not imply connectivity.','Topology validation is not operational or native-runtime validation.']}
        if args.preview_only:
            return result
        return publish_candidate(self,target,members,result,recheck,require_run=False)
def tool_definitions(root):
    service=FiniteTopologyTools(root)
    return [('opentrack_preview_finite_explicit_topology','Preview or publish a fresh Windows archive set with explicit finite multi-document double-vertex/edge topology, point stations and reciprocal connectors. No run file, routes, traffic or native execution.',PreviewFiniteTopology,service.preview,False,False)]
