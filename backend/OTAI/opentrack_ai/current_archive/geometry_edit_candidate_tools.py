"""Publish a reviewed worksheet increment as a fresh complete no-service project."""

import json

from ..errors import APIError
from . import writer
from .bundle_tools import Source
from .itinerary_edit_tools import EditableItineraryProject
from .movement_application_tools import MovementApplicationTools, PrepareMovementApplication, unique_json_keys
from .multi_document.bundle import validate_no_service_bundle
from .multi_document.core import need
from .multi_document_tools import Inventory, MultiDocumentTools
from .project_candidate_publication import ProjectSave, project_target, publish_candidate
from .project_workflow.relocation import relocate_project
from .tools import PathText, sha
from .zero_generation.empty_project import worksheet_header_fingerprint


class PrepareGeometryEditCandidate(ProjectSave):
    source_project: Inventory
    bundle_manifest: Source
    target_directory: PathText


class GeometryEditCandidateTools(MultiDocumentTools):
    def prepare(self, args):
        target = project_target(self, args)
        state = self.load_project(args.source_project, minimum_documents=1)
        if state['root'] != state['base'].as_posix():
            raise APIError('GEOMETRY_CANDIDATE_INVALID', 'Use the no-service source run at its actual execution root')
        run = args.source_project.run_file
        original = state['files']
        try:
            validate_no_service_bundle(original, run_file=run, expected_hashes=args.source_project.files,
                                       complete_file_set=True)
            manifest = self.secure_bytes(self.path(args.bundle_manifest.path))
            if sha(manifest) != args.bundle_manifest.sha256:
                raise APIError('SOURCE_CHANGED', 'The geometry bundle differs from its reviewed SHA')
            fields = json.loads(manifest, object_pairs_hook=unique_json_keys)
            need(isinstance(fields, dict) and fields.get('format') == 'opentrack-saved-geometry-v1',
                 'Select a reviewed saved-geometry bundle')
            reviewed, _, changes, recheck_bundle, _ = MovementApplicationTools(self.root).review(
                PrepareMovementApplication(
                    project_run=Source(path=(state['base'] / run).relative_to(self.root).as_posix(),
                                       sha256=args.source_project.files[run]),
                    bundle_manifest=args.bundle_manifest, target_directory=args.target_directory,
                ),
            )
            replacements = {path.relative_to(state['base']).as_posix(): data for path, data in changes.items()}
            need(replacements and replacements.keys() <= set(state['document_members'].values()),
                 'A no-service edit candidate may replace only explicitly bound worksheets')
            for name, data in replacements.items():
                need(data != original[name], 'The reviewed bundle includes an unchanged worksheet')
                before, _ = writer.load_next_compatible(original[name])
                after, _ = writer.load_next_compatible(data)
                need(worksheet_header_fingerprint(before) == worksheet_header_fingerprint(after),
                     'Geometry candidate cannot change the protected or other non-collection worksheet header fields')
            proposed = {**original, **replacements}
            moved, relocation = relocate_project(
                proposed, source_root=state['root'], target_root=target.as_posix(), run_file=run,
                expected_hashes={name: sha(data) for name, data in proposed.items()},
                project_type=EditableItineraryProject,
            )
            unchanged_catalogs = {path: sha(original[path]) for role, path in state['roles'].items() if role != 'dest'}
            need(all(sha(moved[name]) == value for name, value in unchanged_catalogs.items()),
                 'The fresh geometry candidate changed an operating catalogue')
            final_hashes = {name: sha(data) for name, data in moved.items()}
            validation = validate_no_service_bundle(moved, run_file=run, expected_hashes=final_hashes, complete_file_set=True)
        except (ValueError, TypeError, IndexError, KeyError, OverflowError) as exc:
            raise APIError('GEOMETRY_CANDIDATE_INVALID', 'Could not validate the reviewed no-service geometry candidate',
                           str(exc)[:500]) from exc

        def recheck():
            self.recheck(state)
            recheck_bundle()

        result = {
            'preview_only': args.preview_only, 'saved': False, 'publication_review_pending': True,
            'source_project_modified': False, 'native_application_executed': False, 'native_runtime_ready': False,
            'source_project': self.source_receipt(args, state), 'source_bundle': args.bundle_manifest.model_dump(),
            'replacements': reviewed['replacements'], 'preserved_operating_catalogue_sha256': unchanged_catalogs,
            'run_member': run, 'member_sha256': final_hashes, 'relocation': relocation, 'validation': validation,
        }
        recheck()
        if args.preview_only:
            return result
        return publish_candidate(self, target, moved, result, recheck)


def tool_definitions(root):
    service = GeometryEditCandidateTools(root)
    return [(
        'opentrack_prepare_geometry_edit_candidate',
        'Preview or publish a fresh complete no-service project from a verified current worksheet geometry bundle. '
        'Requires exact source and replacement hashes, preserves operating catalogues and keeps the source untouched. '
        'The result is for further geometry work and never starts OpenTrack.',
        PrepareGeometryEditCandidate, service.prepare, False, False,
    )]
