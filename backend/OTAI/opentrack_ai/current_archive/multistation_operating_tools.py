"""Bounded two-station operating-plan previews and publication."""
from typing import Any
from .tools import Input, ArchiveTools, sha
from .bundle_tools import Source
from .project_candidate_publication import ProjectSave, project_target, publish_candidate
from ..errors import APIError

class SevenSources(Input):
    header_document: Source
    shapes: Source
    depot_template: Source
    trains_template: Source
    courses_template: Source
    timetable_template: Source
    connection_template: Source

class PreviewOperatingPlan(ProjectSave):
    sources: SevenSources
    spec: dict[str, Any]

class OperatingPreviewTools(ArchiveTools):
    def preview(self, args):
        target = project_target(self, args, args.spec.get('execution_root'))
        from .multistation_operations.api import generate_from_spec
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
            raise APIError('OPERATING_PLAN_INVALID', 'Outside the finite two-station operating-data contract', str(exc)[:500]) from exc
        def recheck():
            for key, path in paths.items():
                if self.secure_bytes(path) != blobs[key]:
                    raise APIError('SOURCE_CHANGED', 'Source changed during preparation or publication', key)
        recheck()
        if set(result['files']) != set(files) or any(result['files'][n] != {'sha256':sha(b),'bytes':len(b)} for n,b in files.items()):
            raise APIError('PREVIEW_MANIFEST', 'Generated candidate manifest does not match in-memory bytes')
        result.update(tool='opentrack_preview_multistation_operating_plan', preview_only=args.preview_only, saved=False,
                      publication_review_pending=True, native_runtime_ready=False,
                      generation_profile='two_station_single_engine_same_day',
                      source_bindings=args.sources.model_dump(),
                      limitations=['Fixed A/B, one station per document; not arbitrary network or three-by-three grid.',
                                   'Single EngineReference; no multi-unit or trailer composition.',
                                   'Same-day plan only; physical fleet availability, dynamics and runtime turnround are not proven.',
                                   'Five-minute sample runtime is a planned time, not a native simulation result.'])
        if args.preview_only:
            return result
        return publish_candidate(self,target,files,result,recheck)

def tool_definitions(root):
    service = OperatingPreviewTools(root)
    return [('opentrack_preview_multistation_operating_plan',
             'Preview or publish a fresh A/B operating plan on Windows from seven SHA-bound resources: two terminal areas, one EngineReference Train, reciprocal Itineraries, Courses, times and optional turnround connections. Bounded same-day plan; no native execution.',
             PreviewOperatingPlan, service.preview, False, False)]
