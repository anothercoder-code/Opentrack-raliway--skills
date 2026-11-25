"""Save native Route aspects and category-specific signal settings."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, model_validator

from ..errors import APIError
from .bundle_tools import CourseBundles, Source
from .itinerary_edit_tools import bound_dest_catalog, run_infrastructure_paths
from .next_tools import NextFunctions, Ordinal
from .operation_tools import Name
from .project_candidate_publication import ProjectSave
from .route_fetch_tools import ReviewedName, RouteEnd
from .signal_operating_fields import append_route_aspects, edit_category_signals
from .tools import Input, sha


class BoundSignalRequest(ProjectSave):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    dest_catalog: Source


class MetricSignalAspects(Input):
    start_end: RouteEnd
    speeds_kmh: Annotated[list[Annotated[StrictInt, Field(ge=10, le=300)]], Field(min_length=1, max_length=30)]


class RouteAspectRequest(BoundSignalRequest):
    start_ends: Annotated[list[RouteEnd], Field(min_length=1, max_length=1000)] | None = None
    metric_signal_aspects: Annotated[list[MetricSignalAspects], Field(max_length=1000)] = Field(default_factory=list)


Coordinate = Annotated[StrictFloat | StrictInt, Field(allow_inf_nan=False)]
Delay = Annotated[StrictFloat | StrictInt, Field(ge=0, le=86400, allow_inf_nan=False)]
Performance = Annotated[StrictFloat | StrictInt, Field(gt=0, le=200, allow_inf_nan=False)]
Speed = Annotated[StrictInt, Field(ge=1, le=1000)]


class PerformanceRow(Input):
    category: Name
    delay_s: Delay
    performance_percent: Performance


class CoastingRow(Input):
    category: Name
    enabled: StrictBool


class SignalOperation(Input):
    action: Literal['insert', 'edit']
    document: Name
    end_id: Ordinal
    signal_id: Ordinal | None = None
    name: ReviewedName | None = None
    x: Coordinate | None = None
    y: Coordinate | None = None

    @model_validator(mode='after')
    def matching_signal_identity(self):
        has_placement = self.name is not None and self.x is not None and self.y is not None
        if self.action == 'insert' and (not has_placement or self.signal_id is not None):
            raise ValueError('Insertion requires explicit name and drawing x/y, with no existing Signal ID')
        if self.action == 'edit' and (self.signal_id is None or any(value is not None for value in (self.name, self.x, self.y))):
            raise ValueError('Editing requires the existing Signal ID and preserves its name and drawing placement')
        return self


class PerformanceOperation(SignalOperation):
    kind: Literal['performance_category']
    rows: Annotated[list[PerformanceRow], Field(min_length=1, max_length=999)]


class CoastingOperation(SignalOperation):
    kind: Literal['coasting']
    rows: Annotated[list[CoastingRow], Field(max_length=999)] = Field(default_factory=list)
    lower_speed_kmh: Speed | None = None
    upper_speed_kmh: Speed | None = None

    @model_validator(mode='after')
    def paired_speed_thresholds(self):
        lower, upper = self.lower_speed_kmh, self.upper_speed_kmh
        if (lower is None) != (upper is None) or (lower is not None and lower >= upper):
            raise ValueError('Supply both thresholds in increasing order, or omit both during an edit')
        if (self.action == 'insert' or not self.rows) and lower is None:
            raise ValueError('A new coasting signal or an empty category edit needs both thresholds')
        return self


class CategorySignalRequest(BoundSignalRequest):
    trains: Source
    operations: Annotated[list[Annotated[PerformanceOperation | CoastingOperation, Field(discriminator='kind')]],
                          Field(min_length=1, max_length=100)]


class SignalOperatingTools(NextFunctions, CourseBundles):
    def _train_binding(self, args, run_path, run):
        matches = [line.split('#') for line in run.decode('ascii').splitlines() if line.startswith('TrainFile#')]
        if len(matches) != 1 or len(matches[0]) != 3 or matches[0][2]:
            raise APIError('SIGNAL_TRAIN_CATALOG_SCOPE', 'One run-bound TrainFile is required')
        raw = matches[0][1]
        path = Path(raw)
        if not raw or any(char in raw for char in '\\%$') or '..' in path.parts or path.suffix != '.trains':
            raise APIError('SIGNAL_TRAIN_CATALOG_SCOPE', 'Use an explicit portable .trains path')
        wanted = path if path.is_absolute() else run_path.parent / path
        target, archive, _, _ = self.checked(args.trains)
        if not wanted.is_relative_to(run_path.parent) or target != self.path(wanted.relative_to(self.root).as_posix()):
            raise APIError('SIGNAL_TRAIN_CATALOG_SCOPE', 'TrainList must match the selected run TrainFile')
        return target, archive

    def _edit(self, args, *, train_categories):
        inputs = {name: self.checked(source) for name, source in args.documents.items()}
        run_path, run, scope_check, scope = self.checked_document_list(args, inputs)
        catalog_path, catalog, _, _ = self.checked(args.dest_catalog)
        bound_dest_catalog(self, run_path, run, catalog_path)
        dependencies = {run_path: run, catalog_path: catalog, **{row[0]: row[1] for row in inputs.values()}}
        if args.target_directory is not None and self.path(args.target_directory).is_relative_to(run_path.parent):
            raise APIError('SIGNAL_OPERATIONS_SCOPE', 'Publish replacement archives outside the selected source project')
        documents = {name: row[1] for name, row in inputs.items()}
        paths = run_infrastructure_paths(run)
        try:
            if train_categories:
                trains_path, trains = self._train_binding(args, run_path, run)
                dependencies[trains_path] = trains
                output, report = edit_category_signals(documents, paths, catalog, trains,
                                                       [item.model_dump() for item in args.operations])
                format_name = 'opentrack-category-signal-v1'
            else:
                output, report = append_route_aspects(documents, paths, catalog, args.start_ends,
                                                      [item.model_dump() for item in args.metric_signal_aspects])
                format_name = 'opentrack-route-aspects-v1'
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('CURRENT_SIGNAL_OPERATIONS', str(exc)[:500]) from exc
        result = {'preview_only': args.preview_only, 'saved': False, 'change_report': report,
                  'fresh_archive_reload_verified': True, 'native_application_started': False}
        if not output:
            scope_check()
            if any(self.secure_bytes(file) != blob for file, blob in dependencies.items()):
                raise APIError('SOURCE_CHANGED', 'A bound signal input changed during verification')
            return {**result, 'no_change': True}
        members = {inputs[name][0].name: data for name, data in output.items()}
        manifest = {'format': format_name,
                    'files': {name: {'sha256': sha(data), 'bytes': len(data)} for name, data in members.items()},
                    'replacement_for': {inputs[name][0].name: inputs[name][0].relative_to(self.root).as_posix()
                                        for name in output},
                    'sources': {path.relative_to(self.root).as_posix(): sha(blob) for path, blob in dependencies.items()},
                    'document_scope': scope, 'complete_relocated_project': False}
        return self.publish_bundle(inputs=dependencies, members=members, manifest=manifest,
                                   result={**result, 'manifest': manifest},
                                   target_directory=args.target_directory, scope_check=scope_check)

    def route_aspects(self, args):
        return self._edit(args, train_categories=False)

    def category_signals(self, args):
        return self._edit(args, train_categories=True)


def tool_definitions(root):
    service = SignalOperatingTools(root)
    return [
        ('opentrack_append_all_route_signal_aspects',
         'Append missing saved start-signal aspects to every Route at selected primary Ends, preserving existing '
         'aspect order and route identities. Optionally append explicit numeric speed aspects to show-type 2 signals. '
         'Save native replacement files for the selected scope.',
         RouteAspectRequest, service.route_aspects, False, False),
        ('opentrack_edit_train_category_signals',
         'Insert or edit current native Performance Category and Coasting signals with exact names from the '
         'run-bound TrainList order. Preserve other settings and save the changed .opentrack worksheets.',
         CategorySignalRequest, service.category_signals, False, False),
    ]
