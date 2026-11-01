from typing import Literal
"""Read-only preview adapter. No archive save or publisher is reachable here."""
from typing import Any
from pydantic import StrictBool
from .tools import Input, ArchiveTools, sha
from .bundle_tools import Source
from ..errors import APIError

class SevenSources(Input):
    header_document: Source
    shapes: Source
    depot_template: Source
    trains_template: Source
    courses_template: Source
    timetable_template: Source
    connection_template: Source

class PreviewMultistationTimetable(Input):
    sources: SevenSources
    spec: dict[str, Any]
    preview_only: Literal[True] = True

class MultistationTimetableTools(ArchiveTools):
    def preview(self, args):
        
        if args.preview_only is not True:
            raise APIError('PREVIEW_ONLY', 'This candidate supports preview only. Saving and publication are unavailable pending independent transaction review.')
        from .multistation_timetable.api import generate_from_spec
        blobs = {}; paths = {}
        for key in SevenSources.model_fields:
            binding = getattr(args.sources, key)
            path = self.path(binding.path)
            blob = self.secure_bytes(path)
            if sha(blob) != binding.sha256:
                raise APIError('SOURCE_CHANGED', 'Source SHA does not match the explicit binding', key)
            paths[key] = path; blobs[key] = blob
        try:
            files, result = generate_from_spec(blobs, args.spec)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('MULTISTATION_TIMETABLE_INVALID', 'Outside the finite multistation timetable data contract', str(exc)[:500]) from exc
        
        
        for key, path in paths.items():
            if self.secure_bytes(path) != blobs[key]:
                raise APIError('SOURCE_CHANGED', 'Source changed during preview', key)
        if set(result['files']) != set(files) or any(result['files'][n] != {'sha256':sha(b),'bytes':len(b)} for n,b in files.items()):
            raise APIError('PREVIEW_MANIFEST', 'Generated candidate manifest does not match in-memory bytes')
        result.update(tool='opentrack_preview_multistation_timetable', preview_only=True, saved=False,
                      publication_review_pending=True, native_runtime_ready=False,
                      generation_profile='chain_multistation_single_engine_bounded_cross_day',
                      source_bindings=args.sources.model_dump(),
                      limitations=['Linear chain only; not arbitrary network or three-by-three grid.',
                                   'Single EngineReference template; no mixed formation physics.',
                                   'Bounded planned cross-day times; dynamics, fleet availability and runtime turnround unproven.',
                                   'Static timing checks do not prove timetable capacity, deadlock freedom or actual movement.',
                                   'No save, publication or native execution through this tool.'])
        return result

def tool_definitions(root):
    service = MultistationTimetableTools(root)
    return [('opentrack_preview_multistation_timetable',
             'Read-only multistation chain timetable preview from seven SHA-bound source archives and explicit specification. Generates native project bytes in memory with planned station times and optional reciprocal turnround records; returns hashes and checks only. Bounded cross-day profile, no save or native execution.',
             PreviewMultistationTimetable, service.preview)]
