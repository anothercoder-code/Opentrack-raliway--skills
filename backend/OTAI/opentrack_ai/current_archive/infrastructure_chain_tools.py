"""Single-document topology-to-itinerary preview and native publication."""
import os
from typing import Annotated,Literal
from pydantic import Field
from .tools import Input,ArchiveTools,PathText,sha
from .bundle_tools import Source
from .network_generation_tools import Network,MainSignal,Route,Text
from .finite_topology_tools import PointStation
from .project_candidate_publication import ProjectSave
from ..errors import APIError
from ..json_safe import checked_json
class PathPlan(Input):
    name:Text
    routes:Annotated[list[Text],Field(min_length=1,max_length=100)]
class ItineraryPlan(Input):
    name:Text
    paths:Annotated[list[Text],Field(min_length=1,max_length=100)]
class PreviewInfrastructureChain(ProjectSave):
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
class InfrastructureChainTools(ArchiveTools):
    def preview(self,args):
        from .infrastructure_chain_workflow import compose_infrastructure
        target = None
        if not args.preview_only:
            if os.name != 'nt':
                raise APIError('UNSUPPORTED_SECURE_FILESYSTEM','Nested project publication requires Windows x64 local NTFS')
            target = self.path(args.target_directory)
            expected = f'{target.as_posix()}/OTDocuments/{args.document_name}.opentrack'
            if args.document_path != expected:
                raise APIError('PROJECT_TARGET_BINDING','document_path must equal its actual fresh target member',{'expected_document_path':expected})
        inputs={};data={}
        for key in('header','shapes'):
            source=getattr(args,key);path=self.path(source.path);blob=self.secure_bytes(path)
            if sha(blob)!=source.sha256:raise APIError('SOURCE_CHANGED','Exact donor SHA mismatch',key)
            if len(blob)>128*1024*1024:raise APIError('INFRASTRUCTURE_SIZE','Donor exceeds128MiB')
            inputs[path]=blob;data[key]=blob
        spec=args.model_dump(exclude={'domain','header','shapes','preview_only','target_directory'});spec['network']=args.network.core_spec()
        try:members,report=compose_infrastructure(data['header'],data['shapes'],expected_hashes={k:sha(v)for k,v in data.items()},spec=spec)
        except(ValueError,TypeError,KeyError,IndexError,OverflowError)as exc:raise APIError('INFRASTRUCTURE_CHAIN_INVALID','Outside single-document explicit infrastructure domain',str(exc)[:500])from exc
        def recheck():
            for path,blob in inputs.items():
                if self.secure_bytes(path)!=blob:
                    raise APIError('SOURCE_CHANGED','A donor changed during infrastructure generation or publication')
        recheck()
        result = {'tool':'opentrack_preview_infrastructure_chain','preview_only':args.preview_only,'saved':False,'publication_review_pending':args.preview_only,'report':report,'outputs':{k:{'sha256':sha(v),'bytes':len(v)}for k,v in members.items()},'limitations':['One document with simple explicit routes and no connectors.','Point stations, infrastructure and destination index only. Vehicle, timetable and .run configuration are outside this operation.']}
        if args.preview_only:
            return result

        from . import catalogs, writer
        from .graphic_alignment import validate_generated_signal_alignment
        from .multi_document.core import Project
        from .windows_publish import publish_project
        doc_member = 'OTDocuments/'+args.document_name+'.opentrack'

        def validate_bundle(actual):
            if actual != members or report['output_sha256'] != {name:sha(blob)for name,blob in actual.items()}:
                raise APIError('CURRENT_ARCHIVE_VERIFY','Infrastructure bundle differs from the verified candidates')
            docs = {args.document_name:actual[doc_member]}
            project = Project(docs,document_paths=report['document_paths'],
                              expected_hashes={name:sha(blob)for name,blob in docs.items()},complete_document_set=True)
            project.check_dest_catalog(actual['OTData/infrastructure.dest'])
            catalogs.station_items(writer.load_next_compatible(actual['OTData/infrastructure.stations'])[0])
            for model in project.models[args.document_name]:
                if writer.kind(model)=='OTSignalModel':
                    validate_generated_signal_alignment(model)

        result = checked_json(result)
        publication = publish_project(self.root,target,members,recheck=recheck,
                                      validate_bundle=validate_bundle,empty_directories=())
        return {**result,**publication}
def tool_definitions(root):
    s=InfrastructureChainTools(root)
    return [('opentrack_preview_infrastructure_chain','Preview or publish a fresh Windows directory containing a single document, point-station catalog and destination index. Requires explicit topology and movements and the actual target document path. No native execution.',PreviewInfrastructureChain,s.preview,False,False)]
