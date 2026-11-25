"""Bounded multistation timetable previews and publication."""
from typing import Annotated, Any
from pydantic import Field, StrictStr
from .tools import Input, ArchiveTools, sha
from .bundle_tools import Source
from .project_candidate_publication import ProjectSave, project_target, publish_candidate
from ..errors import APIError

class CorridorSources(Input):
    header_document: Source
    shapes: Source
    depot_template: Source
    trains_template: Source
    courses_template: Source
    timetable_template: Source


class SevenSources(CorridorSources):
    connection_template: Source


class PlatformSources(CorridorSources):
    connection_template: Source | None = None

class PreviewMultistationTimetable(ProjectSave):
    sources: SevenSources
    spec: dict[str, Any]


class PlatformEvidence(Input):
    source: Annotated[StrictStr, Field(min_length=1, max_length=800)]
    supports: Annotated[StrictStr, Field(min_length=1, max_length=1000)]


class BuildReferencePlatform(PreviewMultistationTimetable):
    sources: PlatformSources
    evidence: Annotated[list[PlatformEvidence], Field(min_length=1, max_length=20)]
    model_assumptions: Annotated[list[StrictStr], Field(min_length=1, max_length=20)]


class MultistationTimetableTools(ArchiveTools):
    def reference_platform(self, args):
        network = args.spec.get('network')
        if not isinstance(network, dict) or not isinstance(network.get('platform'), dict):
            raise APIError('REFERENCE_PLATFORM_REQUIRED', 'Declare the real station platform under spec.network.platform')
        return self.preview(args, reference={
            'sources': [entry.model_dump() for entry in args.evidence],
            'model_assumptions': args.model_assumptions,
        })

    def preview(self, args, *, reference=None):
        network = args.spec.get('network')
        execution_root = network.get('execution_root') if isinstance(network, dict) else None
        target = project_target(self, args, execution_root)
        from .multistation_timetable.api import generate_from_spec
        blobs = {}; paths = {}
        for key in type(args.sources).model_fields:
            binding = getattr(args.sources, key)
            if binding is None:
                continue
            path = self.path(binding.path)
            blob = self.secure_bytes(path)
            if sha(blob) != binding.sha256:
                raise APIError('SOURCE_CHANGED', 'Source SHA does not match the explicit binding', key)
            paths[key] = path; blobs[key] = blob
        try:
            files, result = generate_from_spec(blobs, args.spec)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('MULTISTATION_TIMETABLE_INVALID', 'Outside the finite multistation timetable data contract', str(exc)[:500]) from exc
        def recheck():
            for key, path in paths.items():
                if self.secure_bytes(path) != blobs[key]:
                    raise APIError('SOURCE_CHANGED', 'Source changed during preparation or publication', key)
        recheck()
        if set(result['files']) != set(files) or any(result['files'][n] != {'sha256':sha(b),'bytes':len(b)} for n,b in files.items()):
            raise APIError('PREVIEW_MANIFEST', 'Generated candidate manifest does not match in-memory bytes')
        result.update(tool='opentrack_preview_multistation_timetable', preview_only=args.preview_only, saved=False,
                      publication_review_pending=True, native_runtime_ready=False,
                      generation_profile='chain_multistation_single_engine_bounded_cross_day',
                      source_bindings=args.sources.model_dump(exclude_none=True),
                      limitations=['Linear chain only; not arbitrary network or three-by-three grid.',
                                   'Single EngineReference template; no mixed formation physics.',
                                   'Bounded planned cross-day times; dynamics, fleet availability and runtime turnround unproven.',
                                   'Static timing checks do not prove timetable capacity, deadlock freedom or actual movement.'])
        if reference is not None:
            result.update(tool='opentrack_build_reference_platform_corridor',
                          generation_profile='reference_platform_through_stop',
                          reference=reference)
        if args.preview_only:
            return result
        return publish_candidate(self,target,files,result,recheck)

def tool_definitions(root):
    service = MultistationTimetableTools(root)
    return [
        ('opentrack_preview_multistation_timetable',
         'Preview or publish a fresh multistation chain and planned timetable on Windows using seven SHA-bound sources. Bounded cross-day profile with optional reciprocal turnrounds; no native execution.',
         PreviewMultistationTimetable, service.preview, False, False),
        ('opentrack_build_reference_platform_corridor',
         'Build a fresh native corridor around one real through-platform. Bind its directional stopping Edge, track and physical length, schedule a positive dwell and onward departure, and record source evidence and model assumptions. Native execution is verified separately.',
         BuildReferencePlatform, service.reference_platform, False, False),
    ]
