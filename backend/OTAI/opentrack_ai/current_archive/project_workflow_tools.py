from typing import Literal
"""Finite project relocation and line-chain generation, in-memory previews only."""
from typing import Any
from pydantic import StrictBool
from .tools import Input,PathText,sha
from .bundle_tools import Source
from .multi_document_tools import Inventory,MultiDocumentTools,Name
from ..errors import APIError

class RelocateProjectPreview(Input):
    source_project:Inventory
    target_execution_root:PathText
    preview_only: Literal[True] = True

class GenerateLineProjectPreview(Input):
    source_project:Inventory
    header_document:Name
    shape_archive:Source
    spec:dict[str,Any]
    preview_only: Literal[True] = True

class ProjectWorkflowTools(MultiDocumentTools):
    @staticmethod
    def readonly(args):
        if args.preview_only is not True:
            raise APIError('PREVIEW_ONLY','Only an in-memory data preview is available; no save or publication.')
    @staticmethod
    def output_manifest(members):
        if type(members) is not dict or not members:raise APIError('PREVIEW_MANIFEST','Nonempty output member map required')
        result={}
        for name,blob in members.items():
            MultiDocumentTools.member(name)
            if type(blob) is not bytes:raise APIError('PREVIEW_MANIFEST','Output member must be bytes')
            result[name]={'sha256':sha(blob),'bytes':len(blob)}
        return result
    def relocate(self,args):
        self.readonly(args)
        from .project_workflow.relocation import relocate_project
        state=self.load_project(args.source_project);self.project(state)
        selected={n:state['files'][n]for n in state['selected']}
        try:
            members,receipt=relocate_project(selected,source_root=state['root'],target_root=args.target_execution_root,run_file=args.source_project.run_file,expected_hashes={n:sha(b)for n,b in selected.items()})
        except (ValueError,TypeError,KeyError,IndexError,OverflowError)as exc:
            raise APIError('RELOCATION_INVALID','Outside the verified selected-run relocation domain',str(exc)[:500])from exc
        manifest=self.output_manifest(members)
        if type(receipt) is not dict or receipt.get('source_sha256')!={n:sha(b)for n,b in selected.items()} or receipt.get('output_sha256')!={n:row['sha256']for n,row in manifest.items()}:
            raise APIError('PREVIEW_MANIFEST','Relocation receipt does not match actual source and output bytes')
        self.recheck(state)
        return {'tool':'opentrack_preview_relocated_project','preview_only':True,'saved':False,'native_runtime_ready':False,'publication_review_pending':True,'source_bindings':args.source_project.model_dump(),'selected_source_members':sorted(selected),'unselected_source_members_not_migrated':sorted(set(state['files'])-set(selected)),'output_files':manifest,'receipt':receipt,'scope':'Selected run and its explicit dependency closure only, not every run or unrelated source-directory file. No native execution.'}
    def generate_line(self,args):
        self.readonly(args)
        from .project_workflow.network import generate_network
        state=self.load_project(args.source_project);self.project(state)
        if args.header_document not in state['documents']:raise APIError('HEADER_DOCUMENT','Selected header document absent')
        path=self.path(args.shape_archive.path);shapes=self.secure_bytes(path)
        if sha(shapes)!=args.shape_archive.sha256:raise APIError('SOURCE_CHANGED','Shape source differs from binding')
        templates={k:state['files'][state['roles'][k]]for k in ('depot','trains','courses','timetable')}
        try:members,receipt=generate_network(state['documents'][args.header_document],shapes,templates,args.spec)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError)as exc:
            raise APIError('NETWORK_INVALID','Outside the verified one-station-per-document line-chain domain',str(exc)[:500])from exc
        manifest=self.output_manifest(members)
        expected_sources={'header':sha(state['documents'][args.header_document]),'shapes':sha(shapes),**{k:sha(b)for k,b in templates.items()}}
        if type(receipt) is not dict or receipt.get('sources_sha256')!=expected_sources or receipt.get('members')!=manifest:
            raise APIError('PREVIEW_MANIFEST','Network receipt does not match actual source and output bytes')
        self.recheck(state)
        if self.secure_bytes(path)!=shapes:raise APIError('SOURCE_CHANGED','Shape source changed during preview')
        return {'tool':'opentrack_preview_multistation_line_project','preview_only':True,'saved':False,'native_runtime_ready':False,'publication_review_pending':True,'source_bindings':args.source_project.model_dump(),'shape_binding':args.shape_archive.model_dump(),'output_files':manifest,'receipt':receipt,'scope':'Line chain only; not a three-by-three grid, branching junction, stopping-area or operating-service implementation.'}

def tool_definitions(root):
    service=ProjectWorkflowTools(root)
    return [('opentrack_preview_relocated_project','Read-only selected-run project relocation preview with explicit source tree hashes; known run, diagram and archive path fields only. No save or native execution.',RelocateProjectPreview,service.relocate),('opentrack_preview_multistation_line_project','Read-only one-station-per-document line-chain generation preview from explicit SHA-bound donors. Rejects grids/branches; empty traffic catalogs, no stopping-region or native running claim.',GenerateLineProjectPreview,service.generate_line)]
