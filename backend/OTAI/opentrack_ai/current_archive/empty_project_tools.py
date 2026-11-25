"""Expose empty current-format project creation with verified fresh publication."""

from typing import Annotated, Literal

from pydantic import Field, StrictInt, StrictStr

from ..errors import APIError
from ..models import DocumentName
from .bundle_tools import Source
from .next_tools import NextFunctions
from .project_candidate_publication import ProjectSave, project_target, publish_candidate
from .tools import Input, PathText, sha
from .zero_generation.empty_project import build_empty_project


DayOffset = Annotated[StrictInt, Field(ge=0, le=24854)]
Clock = Annotated[StrictStr, Field(pattern=r'^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$')]


class EmptyProjectWindow(Input):
    start_day: DayOffset
    start_time: Clock
    stop_day: DayOffset
    stop_time: Clock
    step: Annotated[StrictStr, Field(min_length=1, max_length=30)]


class InitializeEmptyCurrentProject(ProjectSave):
    header_document: Source
    shape_archive: Source
    document_names: Annotated[list[DocumentName], Field(min_length=1, max_length=100)]
    execution_root: PathText
    run_filename: Annotated[StrictStr, Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,59}\.run$')] = 'blank.run'
    train_types: Annotated[list[StrictStr], Field(min_length=1, max_length=100)]
    simulation: EmptyProjectWindow | None = None
    additional_outputs: Annotated[list[Literal['station_and_signal_positions']], Field(max_length=1)] = Field(default_factory=list)


class EmptyCurrentProjectTools(NextFunctions):
    def initialize(self, args):
        target = project_target(self, args, args.execution_root)
        header_path, header, _, _ = self.checked(args.header_document)
        shape_path, shapes, _, _ = self.checked(args.shape_archive)
        if header_path.suffix != '.opentrack':
            raise APIError('EMPTY_CURRENT_PROJECT', 'Select an original saved .opentrack worksheet for its header')

        def recheck():
            for path, data in ((header_path, header), (shape_path, shapes)):
                if self.secure_bytes(path) != data:
                    raise APIError('SOURCE_CHANGED', 'An empty-project donor changed during preview or publication',
                                   path.relative_to(self.root).as_posix())

        try:
            files, receipt = build_empty_project(
                header, shapes, document_names=args.document_names, execution_root=args.execution_root,
                run_filename=args.run_filename, train_types=args.train_types,
                simulation=None if args.simulation is None else args.simulation.model_dump(),
                additional_outputs=args.additional_outputs,
            )
        except (ValueError, TypeError, IndexError, KeyError, OverflowError) as exc:
            raise APIError('EMPTY_CURRENT_PROJECT', 'The source cannot build a verified empty current-format project',
                           str(exc)[:500]) from exc
        result = {
            'preview_only': args.preview_only, 'saved': False, 'publication_review_pending': True,
            'native_application_executed': False, 'native_runtime_ready': False,
            'source_bindings': {'header_document': args.header_document.model_dump(),
                                'shape_archive': args.shape_archive.model_dump()},
            'output_files': {name: {'sha256': sha(data), 'bytes': len(data)} for name, data in files.items()},
            'receipt': receipt,
        }
        recheck()
        if args.preview_only:
            return result
        return publish_candidate(self, target, files, result, recheck)


def tool_definitions(root):
    service = EmptyCurrentProjectTools(root)
    return [(
        'opentrack_initialize_empty_current_project',
        'Preview or atomically publish blank native worksheets, six empty current catalogue archives and one bound .run. '
        'Use a SHA-bound saved worksheet header and a compatible native shape archive. Optionally set the native '
        'simulation window and station/signal position output. The blank project is ready for '
        'typed geometry editing. It has no railway infrastructure or operating services. Never starts OpenTrack.',
        InitializeEmptyCurrentProject, service.initialize, False, False,
    )]
