"""Native IncidentSet data previews and fresh Course catalog publication."""
from typing import Any
from .tools import ArchiveTools, sha
from .next_tools import Save
from .operating_candidate_publication import save_candidate
from ..errors import APIError

class PreviewIncidentSets(Save):
    source_path: str
    source_sha256: str
    spec: dict[str, Any]

class IncidentSetTools(ArchiveTools):
    def preview(self,args):
        if len(args.source_sha256)!=64 or any(c not in '0123456789abcdef' for c in args.source_sha256):
            raise APIError('SOURCE_HASH','A lowercase SHA256 binding is required')
        path=self.path(args.source_path)
        blob=self.secure_bytes(path)
        if sha(blob)!=args.source_sha256:
            raise APIError('SOURCE_CHANGED','Source SHA does not match the explicit binding')
        from .incident_set_workflow.core import plan
        try:
            output,receipt=plan(blob,args.spec)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError) as exc:
            raise APIError('INCIDENT_SET_INVALID','Outside the finite IncidentSet storage contract',str(exc)[:500]) from exc
        if self.secure_bytes(path)!=blob:
            raise APIError('SOURCE_CHANGED','Source changed during preview')
        if receipt.get('source_sha256') != sha(blob) or receipt.get('output_sha256') != sha(output):
            raise APIError('PREVIEW_MANIFEST', 'Incident set receipt differs from source/output bytes')
        result = dict(tool='opentrack_preview_incident_sets',preview_only=args.preview_only,saved=False,
                    source_sha256=sha(blob),output={'sha256':sha(output),'bytes':len(output)},
                    incident_sets=receipt,native_runtime_ready=False,publication_review_pending=args.preview_only,
                    limitations=['Finite current Train type1 Incident12 members only; not all event types.',
                                 'Named native sets contain shared incident object references, not independent incident copies.',
                                 'Use clears global flags before enabling the selected sets union; Unuse disables selected members only.',
                                 'No random sampling, native triggering or runtime execution.'])
        return save_candidate(self, args, path, blob, output, result, extension='.courses')

def tool_definitions(root):
    service=IncidentSetTools(root)
    return [('opentrack_preview_incident_sets','Preview or save SHA-bound native IncidentSet lifecycle and member Use flags to a fresh .courses archive. No sampling or native execution.',PreviewIncidentSets,service.preview,False,False)]
