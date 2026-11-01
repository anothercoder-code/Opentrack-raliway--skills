"""One-station-per-document project preview and Windows atomic publication.

Construction stays in the pure-byte workflow. This adapter owns exact source
bindings and final-target validation, and uses only the reviewed native Windows
publisher for disk delivery. It neither launches nor controls OpenTrack.
"""
import os
from typing import Annotated,Any

from pydantic import Field,StrictBool,model_validator

from .tools import ArchiveTools,Input,PathText,sha
from .project_initialization_tools import InitializationSources
from .zero_operations import run_bundle as rb
from ..errors import APIError
from ..json_safe import checked_json


class InitializeStationDocuments(Input):
    sources:InitializationSources
    spec:Annotated[dict[str,Any],Field(min_length=1,max_length=32)]
    preview_only:StrictBool=True
    target_directory:PathText|None=None

    @model_validator(mode='after')
    def explicit_save_target(self):
        if not self.preview_only and self.target_directory is None:
            raise ValueError('Saving requires an explicit fresh target_directory')
        return self


class StationDocumentsTools(ArchiveTools):
    def target(self,args,configuration):
        """Check every document's final binding before source reads or writes."""
        if args.target_directory is None:
            return None
        target=self.path(args.target_directory)
        if os.name=='nt':
            from .windows_io import validate_scoped_path
            validate_scoped_path(self.root,target)
        try:
            expected=rb.root_path(target.as_posix(),'windows')
            selected=rb.root_path(configuration['execution_root'],'windows')
        except (ValueError,TypeError,KeyError) as exc:
            raise APIError('PROJECT_TARGET_BINDING','Publication requires a canonical Windows target and execution root',str(exc)[:300]) from exc
        if selected.casefold()!=expected.casefold():
            raise APIError('PROJECT_TARGET_BINDING','Run execution_root must equal the actual fresh publication target',{'expected_execution_root':expected})
        paths=configuration['document_paths']
        if type(paths)is not dict or not 2<=len(paths)<=12:
            raise APIError('PROJECT_TARGET_BINDING','Explicit bounded document paths are required')
        for name,value in paths.items():
            wanted=expected+'/OTDocuments/'+name+'.opentrack'
            if type(value)is not str or value.replace('\\','/').casefold()!=wanted.casefold():
                raise APIError('PROJECT_TARGET_BINDING','Every document_path must name this project\'s actual document member',{'document':name,'expected_document_path':wanted})
        return target

    def initialize(self,args):
        from . import station_documents_workflow as workflow
        try:
            configuration=workflow.configuration(args.spec)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
            raise APIError('STATION_DOCUMENTS_INVALID','Outside bounded one-station-per-document initialization contract',str(exc)[:700]) from exc
        target=self.target(args,configuration)
        if not args.preview_only and os.name!='nt':
            raise APIError('UNSUPPORTED_SECURE_FILESYSTEM','Station-document project publication is implemented for Windows x64 local NTFS only')
        sources={};inputs={};total=0
        for role in type(args.sources).model_fields:
            binding=getattr(args.sources,role);path=self.path(binding.path)
            blob=self.secure_bytes(path);total+=len(blob)
            if sha(blob)!=binding.sha256:
                raise APIError('SOURCE_CHANGED','Exact station-document donor SHA mismatch',role)
            if total>256*1024*1024:
                raise APIError('INITIALIZATION_SIZE','Six donors exceed 256 MiB total')
            if path in inputs and inputs[path]!=blob:
                raise APIError('SOURCE_CHANGED','Repeated resolved donor changed between resource-role reads',role)
            inputs[path]=blob;sources[role]=blob

        def recheck():
            for path,blob in inputs.items():
                if self.secure_bytes(path)!=blob:
                    raise APIError('SOURCE_CHANGED','A station-document donor changed during publication',str(path.relative_to(self.root)))

        try:
            members,receipt=workflow.initialize(sources,args.spec)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
            raise APIError('STATION_DOCUMENTS_INVALID','Outside bounded one-station-per-document initialization contract',str(exc)[:700]) from exc

        def validate_bundle(actual):
            try:
                validation=workflow.validate(actual,args.spec,receipt)
            except (ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
                raise APIError('STATION_DOCUMENTS_VERIFY','Actual station-document members fail independent readback validation',str(exc)[:700]) from exc
            return checked_json(validation)

        validation=validate_bundle(members)
        recheck()
        if type(members)is not dict or not all(type(k)is str and type(v)is bytes for k,v in members.items()):
            raise APIError('INITIALIZATION_RECEIPT','Immutable named project candidates required')
        manifest={name:{'sha256':sha(blob),'bytes':len(blob)}for name,blob in members.items()}
        if len(members)!=len(configuration['document_paths'])+7:
            raise APIError('INITIALIZATION_RECEIPT','Expected N station documents, six catalogs and one run member')
        if type(receipt)is not dict or any(receipt.get(key)is not False for key in ('saved','native_application_executed','native_runtime_ready')):
            raise APIError('INITIALIZATION_RECEIPT','Candidate receipt must explicitly remain unsaved and unexecuted')
        if receipt.get('members')!=manifest or receipt.get('source_sha256')!={role:sha(blob)for role,blob in sources.items()}:
            raise APIError('INITIALIZATION_RECEIPT','Candidate receipt must bind actual source and generated member hashes')
        result=checked_json({'tool':'opentrack_initialize_station_documents_project',
            'profile':'one_station_per_document_forward_final_stop',
            'preview_only':args.preview_only,'saved':False,'project_files_delivered':False,
            'native_application_executed':False,'native_runtime_verified':False,
            'source_bindings':args.sources.model_dump(),'candidate_receipt':receipt,
            'outputs':manifest,'candidate_validation':validation,'publication':None,
            'limitations':['Bounded explicit linear station chain, one station per topology document; six authorized native format and vehicle templates remain required.',
                'Forward journey with final terminal stop only; no arbitrary network, intermediate dwell, reverse journey or fleet circulation.',
                'Unsaved candidate validation and a separate saved publication receipt are distinct evidence layers.',
                'Publication and fresh-byte validation do not execute OpenTrack or establish native simulation success.']})
        if args.preview_only:
            return result

        from .windows_publish import publish_project
        publication=publish_project(self.root,target,members,recheck=recheck,
            validate_bundle=validate_bundle,empty_directories=(configuration['output_directory'],))
        return {**result,'saved':True,'project_files_delivered':True,
            'target_directory':str(target.relative_to(self.root)),
            'run_path':str((target/configuration['run_filename']).relative_to(self.root)),
            'publication':publication,
            'persisted_content_validation':{'all_members_reloaded':True,
                'member_count':len(members),'document_count':len(configuration['document_paths']),
                'one_station_per_document_verified':True,'member_hashes_match_candidates':True,
                'connectors_cross_document_paths_and_catalog_bindings_verified':True,
                'native_runtime_verified':False}}


def tool_definitions(root):
    service=StationDocumentsTools(root)
    return [('opentrack_initialize_station_documents_project',
        'Initialize a bounded forward final-stop station chain from six exact SHA-bound native format/vehicle resources, with one station per .opentrack document, reciprocal connectors and cross-document Route/Path/Itinerary bindings. Preview or atomically publish N+7 project members to an explicit fresh Windows x64 local NTFS target, rereading every member and validating all references. Existing targets are preserved. Never launches OpenTrack or claims native simulation.',
        InitializeStationDocuments,service.initialize,False,False)]
