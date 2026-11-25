"""Save native topology descriptions from a SHA-bound worksheet or movement graph."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictStr, model_validator

from ..errors import APIError
from . import native_topology_description as desc
from .bundle_tools import Source
from .itinerary_edit_tools import EditableItineraryProject, bound_dest_catalog, run_infrastructure_paths
from .next_tools import NextFunctions
from .operation_tools import Name
from .prepare_contract.auxiliary import records
from .project_candidate_publication import ProjectSave, project_target
from .station_exchange import read_catalog
from .tools import sha
from .zero_operations.speed_preferences import read_train_types


Basename = Annotated[StrictStr, Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')]
Section = Literal['itineraries', 'paths', 'routes']


class WorksheetDescription(ProjectSave):
    worksheet: Source
    basename: Basename = 'Worksheet'


class MovementDescriptions(ProjectSave):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    dest_catalog: Source | None = None
    station_catalog: Source | None = None
    sections: Annotated[list[Section], Field(min_length=1, max_length=3)] = Field(
        default_factory=lambda: list(desc.SECTION_NAMES))
    detailed_routes: StrictBool = False
    detailed_itinerary_profiles: StrictBool = False
    basename: Basename = 'Network'

    @model_validator(mode='after')
    def options(self):
        if len(set(self.sections)) != len(self.sections):
            raise ValueError('Select each description section once')
        if self.detailed_itinerary_profiles and 'itineraries' not in self.sections:
            raise ValueError('Select Itineraries to include their track profiles')
        return self


class NativeDescriptions(NextFunctions):
    def finish_description(self, args, inputs, filename, output, report, scope_check=None):
        target = project_target(self, args)
        expected = {filename: output}

        def recheck():
            if scope_check is not None:
                scope_check()
            for path, raw in inputs.items():
                if self.secure_bytes(path) != raw:
                    raise APIError('SOURCE_CHANGED', 'A topology description input changed', str(path))

        def validate_bundle(found):
            if found != expected:
                raise APIError('NATIVE_TOPOLOGY_DESCRIPTION', 'Description differs from the reviewed output')

        result = {'saved': False, 'preview_only': args.preview_only, 'encoding': 'UTF-8',
                  'file_name': filename, 'file_sha256': sha(output), 'file_bytes': len(output),
                  'input_sources': {str(path.relative_to(self.root)): sha(raw) for path, raw in inputs.items()},
                  'native_execution': False, **report}
        recheck()
        if args.preview_only:
            return result
        from .windows_publish import publish_project

        return {**result, **publish_project(self.root, target, expected, recheck=recheck,
                                           validate_bundle=validate_bundle, empty_directories=())}

    def export_worksheet(self, args):
        path, raw, root, _ = self.checked(args.worksheet)
        if path.suffix != '.opentrack':
            raise APIError('NATIVE_TOPOLOGY_DESCRIPTION', 'Select a native .opentrack worksheet')
        filename = f'{args.basename}.desc'
        try:
            output, report = desc.worksheet(root, path.stem, filename)
        except (ValueError, IndexError, TypeError, AttributeError) as exc:
            raise APIError('NATIVE_TOPOLOGY_DESCRIPTION', str(exc)[:500]) from exc
        return self.finish_description(args, {path: raw}, filename, output, report)

    def export_movements(self, args):
        bound = {name: self.checked(spec) for name, spec in args.documents.items()}
        run_path, run, scope_check, scope = self.checked_document_list(args, bound)
        inputs = {run_path: run, **{part[0]: part[1] for part in bound.values()}}
        documents = {name: part[1] for name, part in bound.items()}
        suffix = ''.join(letter for part, letter in desc.SUFFIXES.items() if part in args.sections)
        filename = f'{args.basename}.{suffix}.desc'
        try:
            project = EditableItineraryProject(
                documents, document_paths=run_infrastructure_paths(run),
                expected_hashes={name: sha(raw) for name, raw in documents.items()},
                complete_document_set=True,
            )
            if args.dest_catalog is not None:
                path, raw, _, _ = self.checked(args.dest_catalog)
                bound_dest_catalog(self, run_path, run, path)
                project.check_dest_catalog(raw, allow_external=True)
                inputs[path] = raw
            stations = {}
            if args.station_catalog is not None:
                path, raw, _, _ = self.checked(args.station_catalog)
                bindings = [value for key, value, _ in records(run) if key == 'StationFile']
                if len(bindings) != 1 or path.suffix != '.stations':
                    raise ValueError('Select the .stations catalog bound by the supplied run')
                binding = run_path.parent / Path(bindings[0])
                if self.path(binding.relative_to(self.root).as_posix()) != path:
                    raise ValueError('Station catalog path differs from the run StationFile binding')
                stations = {sign: fields['name'] for sign, fields in read_catalog(raw)[3].items()}
                inputs[path] = raw
            speed_count = len(read_train_types(run)) if args.detailed_itinerary_profiles else None
            output, report = desc.movements(project, args.sections, filename, detailed_routes=args.detailed_routes,
                                            profile_speed_count=speed_count, stations=stations)
        except (ValueError, IndexError, KeyError, TypeError, AttributeError) as exc:
            raise APIError('NATIVE_TOPOLOGY_DESCRIPTION', str(exc)[:500]) from exc
        return self.finish_description(args, inputs, filename, output, {**report, 'document_scope': scope}, scope_check)


def tool_definitions(root):
    service = NativeDescriptions(root)
    return [
        ('opentrack_export_native_worksheet_description',
         'Write the native .desc worksheet object listing with safety membership and connector references.',
         WorksheetDescription, service.export_worksheet, False, False),
        ('opentrack_export_native_movement_descriptions',
         'Write original Itinerary, Path and Route description sections with optional directional track profiles.',
         MovementDescriptions, service.export_movements, False, False),
    ]
