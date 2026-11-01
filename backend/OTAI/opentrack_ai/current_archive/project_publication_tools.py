"""Explicit eight-member new-project publication, separate from preview receipts.

The pure initializer still returns immutable candidates and an unsaved receipt.
This adapter binds their absolute execution paths to the actual fresh target,
then asks the Windows handle publisher to save and independently reload them.
"""
import os
from pydantic import StrictBool,model_validator
from .tools import ArchiveTools,PathText,sha
from .project_initialization_tools import InitializeProject,validate_initialization_receipt
from .project_initialization_workflow import initialize_project,validate_candidate
from .zero_operations import run_bundle as rb
from ..errors import APIError
from ..json_safe import checked_json


class PublishInitializeProject(InitializeProject):
    preview_only:StrictBool=True
    target_directory:PathText|None=None

    @model_validator(mode='after')
    def explicit_target(self):
        if not self.preview_only and self.target_directory is None:
            raise ValueError('Saving requires an explicit fresh target_directory')
        return self


class ProjectPublicationTools(ArchiveTools):
    def target(self,args):
        """Validate final path bindings before reading donors or staging bytes."""
        if args.target_directory is None:
            return None
        target=self.path(args.target_directory)
        if os.name=='nt':
            from .windows_io import validate_scoped_path
            validate_scoped_path(self.root,target)
        cfg=args.project.run_configuration
        try:
            expected=rb.root_path(target.as_posix(),'windows')
            selected=rb.root_path(cfg.execution_root,cfg.path_style)
        except ValueError as exc:
            raise APIError('PROJECT_TARGET_BINDING','Publication requires a canonical Windows target and execution root',str(exc)[:300]) from exc
        if selected.casefold()!=expected.casefold():
            raise APIError('PROJECT_TARGET_BINDING','Run execution_root must equal the actual fresh publication target',{'expected_execution_root':expected})
        actual_doc=args.project.infrastructure.document_path.replace('\\','/')
        expected_doc=expected+'/OTDocuments/'+args.project.infrastructure.document_name+'.opentrack'
        if actual_doc.casefold()!=expected_doc.casefold():
            raise APIError('PROJECT_TARGET_BINDING','Infrastructure document_path must name this project\'s actual document member',{'expected_document_path':expected_doc})
        return target

    def initialize(self,args):
        target=self.target(args)
        if not args.preview_only and os.name!='nt':
            raise APIError('UNSUPPORTED_SECURE_FILESYSTEM','This new nested project publisher is implemented for Windows x64 local NTFS only')
        inputs={};sources={};total=0
        for key in type(args.sources).model_fields:
            spec=getattr(args.sources,key);path=self.path(spec.path)
            blob=self.secure_bytes(path);total+=len(blob)
            if sha(blob)!=spec.sha256:
                raise APIError('SOURCE_CHANGED','Exact initialization donor SHA mismatch',key)
            if total>256*1024*1024:
                raise APIError('INITIALIZATION_SIZE','Six donors exceed 256 MiB total')
            if path in inputs and inputs[path]!=blob:
                raise APIError('SOURCE_CHANGED','Repeated donor path changed between resource-role reads',key)
            inputs[path]=blob;sources[key]=blob

        def recheck():
            for path,blob in inputs.items():
                if self.secure_bytes(path)!=blob:
                    raise APIError('SOURCE_CHANGED','An initialization donor changed during publication',str(path.relative_to(self.root)))

        project=args.project.model_dump()
        project['infrastructure']['network']=args.project.infrastructure.network.core_spec()
        try:
            members,receipt=initialize_project(sources,
                expected_hashes={k:getattr(args.sources,k).sha256 for k in sources},
                profile=args.profile,project=project)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
            raise APIError('PROJECT_INITIALIZATION_INVALID','Outside bounded project initialization profile',str(exc)[:700]) from exc
        manifest=validate_initialization_receipt(members,receipt,sources,profile=args.profile,project=project)
        recheck()
        result=checked_json({'tool':'opentrack_initialize_project','profile':args.profile,
            'preview_only':args.preview_only,'saved':False,'project_files_delivered':False,
            'native_application_executed':False,'native_runtime_verified':False,
            'source_bindings':args.sources.model_dump(),'candidate_receipt':receipt,
            'outputs':manifest,'publication':None,
            'limitations':['Explicit single-document bounded topology; native format and vehicle templates remain required.',
                'Pass or final-only forward stop profile; no arbitrary intermediate dwell, turnround or fleet circulation.',
                'The candidate receipt describes in-memory generation; only the separate publication receipt can prove saved files.',
                'Saving and fresh-load validation do not execute OpenTrack or prove simulation success.']})
        if args.preview_only:
            return result

        def validate_bundle(actual):
            
            
            validate_initialization_receipt(actual,receipt,sources,profile=args.profile,project=project)
            return validate_candidate(actual,project=project,chain_receipt=receipt['chain_receipt'])

        from .windows_publish import publish_project
        publication=publish_project(self.root,target,members,recheck=recheck,
            validate_bundle=validate_bundle,
            empty_directories=(project['run_configuration']['output_directory'],))
        return {**result,'saved':True,'project_files_delivered':True,
            'target_directory':str(target.relative_to(self.root)),
            'run_path':str((target/project['run_configuration']['run_filename']).relative_to(self.root)),
            'publication':publication,
            'persisted_content_validation':{'all_eight_members_reloaded':True,
                'member_hashes_match_candidates':True,'run_document_catalog_bindings_verified':True,
                'native_runtime_verified':False}}


def tool_definitions(root):
    service=ProjectPublicationTools(root)
    return [('opentrack_initialize_project',
        'Initialize from an empty topology using six exact SHA-bound native format/vehicle resources. Preview or publish the complete eight-member single-document project into an explicit fresh Windows local NTFS target, including nested OTDocuments/OTData and output directory. Run/document execution paths must equal that target. Atomic no-overwrite commit and actual saved-byte reload/reference checks; never launches OpenTrack or claims native simulation.',
        PublishInitializeProject,service.initialize,False,False)]
