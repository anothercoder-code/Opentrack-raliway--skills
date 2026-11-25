"""Rebuilt fixed-grid preview and publication.

This is new interface code over the recovered fixed audited generator, not an
assertion that the old wrapper was recovered or that native execution succeeded.
"""
from pydantic import StrictBool
from .tools import Input, PathText, ArchiveTools, sha
from .bundle_tools import Source
from .project_candidate_publication import ProjectSave, project_target, publish_candidate
from .zero_operations import run_bundle as rb
from ..errors import APIError

class FullGridSources(Input):
    terminal_document: Source
    request: Source
    shapes: Source
    depot: Source
    trains: Source
    courses: Source
    timetable: Source
    stations: Source

class FullGridSpecification(Input):
    execution_root: PathText
    accept_new_signal_plan: StrictBool

class PreviewFullMultidocGrid(ProjectSave):
    sources: FullGridSources
    spec: FullGridSpecification
class FullMultidocGridTools(ArchiveTools):
    def preview(self, args):
        target = project_target(self, args, args.spec.execution_root)
        from .full_multidoc_grid import core
        inputs = {}; data = {}; hashes = {}
        for role in type(args.sources).model_fields:
            source = getattr(args.sources, role)
            path = self.path(source.path)
            blob = self.secure_bytes(path)
            if sha(blob) != source.sha256:
                raise APIError('SOURCE_CHANGED', 'Grid input differs from explicit SHA binding', role)
            inputs[path] = blob; data[role] = blob; hashes[role] = source.sha256
        if len(inputs) != 8:
            raise APIError('GRID_SOURCE_ROLES', 'Eight distinct role-bound source files required')
        try:
            members, receipt = core.generate(data, hashes, args.spec.model_dump())
            if type(members) is not dict or not members:
                raise ValueError('Nonempty generated member map required')
            for name, blob in members.items():
                rb.relative(name)
                if type(blob) is not bytes or not blob or len(blob) > 20*1024*1024:
                    raise ValueError('Bounded nonempty immutable output members required')
            manifest = {n: {'sha256': sha(b), 'bytes': len(b)} for n,b in members.items()}
            if receipt.get('members') != manifest or receipt.get('source_sha256') != hashes:
                raise ValueError('Generated receipt does not match actual input/output bytes')
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('FULL_GRID_INVALID', 'Outside the fixed audited terminal-grid domain', str(exc)[:500]) from exc
        def recheck():
            for path, original in inputs.items():
                if self.secure_bytes(path) != original:
                    raise APIError('SOURCE_CHANGED', 'Grid input changed during preparation or publication')
        recheck()
        result = {
            'tool': 'opentrack_preview_full_multidocument_grid',
            'preview_only': args.preview_only, 'saved': False, 'publication_review_pending': True,
            'native_runtime_ready': False, 'native_simulation_executed': False,
            'source_bindings': args.sources.model_dump(), 'output_files': manifest,
            'fresh_archive_reload_verified': True, 'receipt': receipt,
            'limitations': [
                'Only the eight exact audited baseline source hashes are supported.',
                '25 documents: 12 station, 4 corner, 9 grade-separated crossing documents; crossings do not permit turning between corridors.',
                '40 additional directional boundary signals form a new section/control plan; original runtime capacity equivalence is not established.',
            ],
        }
        if args.preview_only:
            return result
        return publish_candidate(self,target,members,result,recheck)

def tool_definitions(root):
    service = FullMultidocGridTools(root)
    return [('opentrack_preview_full_multidocument_grid',
             'Preview or publish a fresh Windows copy of the audited 25-document terminal grid with reciprocal connectors and six finite circuits. Eight exact SHA-bound inputs and explicit acceptance of a new boundary signal plan. Grade-separated crossings; no native execution.',
             PreviewFullMultidocGrid, service.preview, False, False)]
