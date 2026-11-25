"""Three-station/infrastructure-junction project generation."""
from .project_workflow_tools import GenerateLineProjectPreview,ProjectWorkflowTools
from .project_candidate_publication import project_target,publish_candidate,require_external_target
from .tools import sha
from ..errors import APIError

class BranchNetworkTools(ProjectWorkflowTools):
    def preview(self,args):
        target=project_target(self,args,args.spec.get('execution_root'))
        require_external_target(target,self.path(args.source_project.project_directory))
        from .signal_protection.branch_network import generate_network
        state=self.load_project(args.source_project);self.project(state)
        if args.header_document not in state['documents']:raise APIError('HEADER_DOCUMENT','Selected header document absent')
        path=self.path(args.shape_archive.path);shapes=self.secure_bytes(path)
        if sha(shapes)!=args.shape_archive.sha256:raise APIError('SOURCE_CHANGED','Shape source differs from binding')
        templates={k:state['files'][state['roles'][k]]for k in ('depot','trains','courses','timetable')}
        try:members,receipt=generate_network(state['documents'][args.header_document],shapes,templates,args.spec)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError)as exc:
            raise APIError('BRANCH_INVALID','Outside the finite three-arm junction project domain',str(exc)[:500])from exc
        manifest=self.output_manifest(members)
        expected={'header':sha(state['documents'][args.header_document]),'shapes':sha(shapes),**{k:sha(b)for k,b in templates.items()}}
        if type(receipt)is not dict or receipt.get('source_sha256')!=expected or receipt.get('members')!=manifest:raise APIError('PREVIEW_MANIFEST','Branch receipt does not match actual source/output bytes')
        def recheck():
            self.recheck(state)
            if self.secure_bytes(path)!=shapes:
                raise APIError('SOURCE_CHANGED','Shape source changed during preparation or publication')
        recheck()
        result={'tool':'opentrack_preview_three_station_branch_project','preview_only':args.preview_only,'saved':False,'native_runtime_ready':False,'publication_review_pending':True,'source_bindings':args.source_project.model_dump(),'shape_binding':args.shape_archive.model_dump(),'output_files':manifest,'receipt':receipt,'limitations':['Three station documents plus one infrastructure-only junction document, not a three-by-three grid or arbitrary junction.','Point stations and empty traffic catalogs; no stopping-region or operating-service claim.','Geometry is a schematic, not engineered physical alignment or runtime protection certification.']}
        if args.preview_only:
            return result
        return publish_candidate(self,target,members,result,recheck)

def tool_definitions(root):
    service=BranchNetworkTools(root)
    return [('opentrack_preview_three_station_branch_project','Preview or publish a fresh bounded three-arm triangle junction on Windows: three station documents, one infrastructure-only junction, reciprocal connectors and six directed itineraries. Empty traffic; no native execution.',GenerateLineProjectPreview,service.preview,False,False)]
