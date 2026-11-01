from typing import Literal
"""Read-only native IncidentSet data preview, never saves or starts a process."""
from typing import Any
from pydantic import StrictBool
from .tools import Input, ArchiveTools, sha
from ..errors import APIError

class PreviewIncidentSets(Input):
    source_path: str
    source_sha256: str
    spec: dict[str, Any]
    preview_only: Literal[True] = True

class IncidentSetTools(ArchiveTools):
    def preview(self,args):
        if args.preview_only is not True:
            raise APIError('PREVIEW_ONLY','This candidate is preview-only; saving, publication and native execution are unavailable.')
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
        return dict(tool='opentrack_preview_incident_sets',preview_only=True,saved=False,
                    source_sha256=sha(blob),output={'sha256':sha(output),'bytes':len(output)},
                    incident_sets=receipt,native_runtime_ready=False,publication_review_pending=True,
                    limitations=['Finite current Train type1 Incident12 members only; not all event types.',
                                 'Named native sets contain shared incident object references, not independent incident copies.',
                                 'Use clears global flags before enabling the selected sets union; Unuse disables selected members only.',
                                 'No random sampling, native triggering, new save, publication or runtime execution.'])

def tool_definitions(root):
    service=IncidentSetTools(root)
    return [('opentrack_preview_incident_sets','Read-only SHA-bound native IncidentSet data preview. Plan set lifecycle and member Use flags in memory; returns hashes only. No save, sampling or native execution.',PreviewIncidentSets,service.preview)]
