"""Publish a bounded, spatially bound split plan with its original run configuration."""
from typing import Any
from .tools import ArchiveTools, sha
from .multistation_timetable_tools import SevenSources
from .project_candidate_publication import ProjectSave, project_target, publish_candidate
from ..errors import APIError

class PreviewSpatialShunting(ProjectSave):
    sources: SevenSources
    spec: dict[str, Any]

class SpatialShuntingTools(ArchiveTools):
    def preview(self, args):
        from .shunting_spatial_workflow.core import generate_from_spec
        blobs, paths = {}, {}
        for key in SevenSources.model_fields:
            binding = getattr(args.sources, key)
            path = self.path(binding.path)
            blob = self.secure_bytes(path)
            if sha(blob) != binding.sha256:
                raise APIError('SOURCE_CHANGED', 'Source differs from explicit SHA binding', key)
            paths[key], blobs[key] = path, blob
        try:
            target = project_target(self, args, args.spec['base']['network']['execution_root'])
            files, receipt = generate_from_spec(blobs, args.spec)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('SPATIAL_SHUNTING_INVALID', 'Outside the finite spatial split data contract', str(exc)[:500]) from exc
        def recheck():
            for key, path in paths.items():
                if self.secure_bytes(path) != blobs[key]:
                    raise APIError('SOURCE_CHANGED', 'Source changed during operation', key)

        recheck()
        if (type(files) is not dict or type(receipt) is not dict or
            receipt.get('source_sha256') != {k: sha(v) for k, v in blobs.items()} or
            receipt.get('files') != {n: {'sha256': sha(b), 'bytes': len(b)} for n, b in files.items()}):
            raise APIError('PREVIEW_MANIFEST', 'Receipt differs from actual source/output bytes')
        receipt.update(tool='opentrack_preview_spatial_shunting', preview_only=args.preview_only,
                       saved=False, publication_review_pending=args.preview_only,
                       source_bindings=args.sources.model_dump())
        if args.preview_only:
            return receipt
        return publish_candidate(self, target, files, receipt, recheck)

def tool_definitions(root):
    service = SpatialShuntingTools(root)
    return [('opentrack_preview_spatial_shunting',
             'Preview or publish a fresh three-station same-direction split project from seven SHA-bound donors. Checks the common physical suffix and uses the exact final run bindings. Native dynamic execution is not verified.',
             PreviewSpatialShunting, service.preview, False, False)]
