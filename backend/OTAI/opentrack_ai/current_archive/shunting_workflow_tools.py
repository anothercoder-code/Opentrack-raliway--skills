"""Finite split/join timetable previews and fresh timetable publication."""
from typing import Any
from .tools import Input, ArchiveTools, sha
from .bundle_tools import Source
from .next_tools import Save
from .operating_candidate_publication import save_candidate
from ..errors import APIError
class ShuntingSources(Input):
    timetable: Source
    courses: Source
    trains: Source
    stations: Source
    connection_template: Source
    depot: Source
class PreviewShuntingConnections(Save):
    sources: ShuntingSources
    spec: dict[str, Any]
class ShuntingPreviewTools(ArchiveTools):
    def preview(self,args):
        from .shunting_workflow.core import plan_connections
        blobs={};paths={}
        for key in ShuntingSources.model_fields:
            binding=getattr(args.sources,key);path=self.path(binding.path);data=self.secure_bytes(path)
            if sha(data)!=binding.sha256:raise APIError('SOURCE_CHANGED','Source differs from explicit SHA binding',key)
            paths[key]=path;blobs[key]=data
        try:output,receipt=plan_connections(blobs,args.spec)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError)as exc:
            raise APIError('SHUNTING_PLAN_INVALID','Outside the finite split/join timetable-data contract',str(exc)[:500])from exc
        for key,path in paths.items():
            if self.secure_bytes(path)!=blobs[key]:raise APIError('SOURCE_CHANGED','Source changed during preview',key)
        if type(output)is not bytes or type(receipt)is not dict or receipt.get('output_sha256')!=sha(output) or receipt.get('source_sha256')!={k:sha(v)for k,v in blobs.items()}:
            raise APIError('PREVIEW_MANIFEST','Receipt differs from actual source/output bytes')
        result = {'tool':'opentrack_preview_shunting_connections','preview_only':args.preview_only,'saved':False,'publication_review_pending':args.preview_only,'native_runtime_ready':False,'source_bindings':args.sources.model_dump(),'output':{'sha256':sha(output),'bytes':len(output)},'receipt':receipt,'limitations':['Finite same-day Connection6 split/join planning only; not complete shunting or hump operation.','Initial Train/Course catalogs remain unchanged; resulting composition is a static receipt projection, not persisted runtime state.','Spatial compatibility, native coupling and dynamic composition have not been validated.','The output is limited to the timetable archive.']}
        dependencies = {path: blobs[key] for key, path in paths.items() if key != 'timetable'}
        return save_candidate(self, args, paths['timetable'], blobs['timetable'], output, result,
                              extension='.timetable', dependencies=dependencies)
def tool_definitions(root):
    service=ShuntingPreviewTools(root)
    return [('opentrack_preview_shunting_connections','Plan split/join timetable connections using six SHA-bound current archives. Preview or save reciprocal Connection6 records to a fresh .timetable copy. Static same-day stop and component checks; no native execution or spatial/dynamic validation.',PreviewShuntingConnections,service.preview,False,False)]
