"""Rebuilt data-only adapter for the recovered spatial split core.

New implementation, 2026-10-29. No native execution or publisher access.
"""
from typing import Any, Literal
from .tools import Input, ArchiveTools, sha
from .multistation_timetable_tools import SevenSources
from ..errors import APIError

class PreviewSpatialShunting(Input):
    sources: SevenSources
    spec: dict[str, Any]
    preview_only: Literal[True] = True

class SpatialShuntingTools(ArchiveTools):
    def preview(self, args):
        if args.preview_only is not True:
            raise APIError('PREVIEW_ONLY', 'Spatial split generation is preview-only; no saving or publication.')
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
            files, receipt = generate_from_spec(blobs, args.spec)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('SPATIAL_SHUNTING_INVALID', 'Outside the finite spatial split data contract', str(exc)[:500]) from exc
        for key, path in paths.items():
            if self.secure_bytes(path) != blobs[key]:
                raise APIError('SOURCE_CHANGED', 'Source changed during preview', key)
        if (type(files) is not dict or type(receipt) is not dict or
            receipt.get('source_sha256') != {k: sha(v) for k, v in blobs.items()} or
            receipt.get('files') != {n: {'sha256': sha(b), 'bytes': len(b)} for n, b in files.items()}):
            raise APIError('PREVIEW_MANIFEST', 'Receipt differs from actual source/output bytes')
        receipt.update(tool='opentrack_preview_spatial_shunting', preview_only=True,
                       saved=False, publication_review_pending=True,
                       source_bindings=args.sources.model_dump())
        return receipt

def tool_definitions(root):
    service = SpatialShuntingTools(root)
    return [('opentrack_preview_spatial_shunting',
             'Preview a three-station same-direction split plan from seven explicit SHA-bound donors. Generates native data in memory and checks the common physical suffix; returns hashes and static checks only. OpenTrack owns dynamic execution. No save or publication.',
             PreviewSpatialShunting, service.preview)]
