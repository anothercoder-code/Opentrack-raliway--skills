"""Typed editors for existing native Route and Path records."""

from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

from ..errors import APIError
from .bundle_tools import Source
from .multi_document_tools import Ref as DocumentRouteSelector
from .next_tools import NextFunctions, Save
from .operation_tools import Changes, I32, Name, RouteSelector
from .tools import Input, sha


Description = Annotated[StrictStr, Field(max_length=1048576)]
ProtectionValue = Annotated[StrictFloat | StrictInt, Field(ge=0, le=10000000, allow_inf_nan=False)]


class RouteChanges(Changes):
    description: Description | None = None
    release_distance_m: I32 | None = None
    announce_distance_m: I32 | None = None
    release_time_s: I32 | None = None
    reserve_time_s: I32 | None = None
    approach_length_m: ProtectionValue | None = None
    approach_speed_kmh: ProtectionValue | None = None
    reservation_distance_m: I32 | None = None
    use_reservation_distance: StrictBool | None = None
    use_release_distance: StrictBool | None = None
    reserve_previous: StrictBool | None = None
    release_groups: Literal['global', 'each_end'] | None = None


class EditRoute(Save):
    source: Source
    route: RouteSelector
    changes: RouteChanges


class ApproachChanges(Changes):
    approach_length_m: ProtectionValue | None = None
    approach_speed_kmh: ProtectionValue | None = None


class EditRouteApproachBatch(Save):
    source: Source
    routes: Annotated[list[RouteSelector], Field(min_length=1, max_length=256)]
    changes: ApproachChanges | None = None
    sort_by: Literal['selection', 'description', 'number_of_signal_aspects'] = 'selection'

    @model_validator(mode='after')
    def mutation_required_for_save(self):
        if not self.preview_only and self.changes is None:
            raise ValueError('Provide approach field changes when saving')
        return self


class EditPathDescription(Input):
    action: Literal['set_description']
    source: Source
    description: Description


class EditPathRoutes(Input):
    action: Literal['replace_routes']
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    target_document: Name
    dest_catalog: Source
    routes: Annotated[list[RouteSelector | DocumentRouteSelector], Field(min_length=1, max_length=10000)]
    description: Description | None = None


class EditPath(Save):
    path: RouteSelector
    operation: Annotated[EditPathDescription | EditPathRoutes, Field(discriminator='action')]


class MovementEdits(NextFunctions):
    def _require_archive_target(self, args):
        if not args.preview_only and self.path(args.target_path).suffix != '.opentrack':
            raise APIError('DOCUMENT_SCOPE', 'A new .opentrack target is required')

    def _document(self, binding):
        path, data, _, _ = self.checked(binding)
        if path.suffix != '.opentrack':
            raise APIError('DOCUMENT_SCOPE', 'A current .opentrack document is required')
        return path, data

    def route(self, args):
        from .movement_edits import edit_route

        self._require_archive_target(args)
        source, data = self._document(args.source)
        try:
            output, report = edit_route(data, args.route.model_dump(), args.changes.model_dump(exclude_unset=True))
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('CURRENT_ROUTE_EDIT', str(exc)[:500]) from exc
        return self.finish(args, source, data, output, report)

    def route_approach_batch(self, args):
        from .movement_edits import approach_batch

        self._require_archive_target(args)
        source, data = self._document(args.source)
        fields = {} if args.changes is None else args.changes.model_dump(exclude_unset=True)
        try:
            output, report = approach_batch(data, [ref.model_dump() for ref in args.routes], fields, args.sort_by)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('CURRENT_ROUTE_APPROACH_BATCH', str(exc)[:500]) from exc
        return self.finish(args, source, data, output, report)

    def edit_path(self, args):
        from .movement_edits import edit_path_description, edit_path_routes

        self._require_archive_target(args)
        operation = args.operation
        ref = args.path.model_dump()
        if operation.action == 'set_description':
            source, data = self._document(operation.source)
            try:
                output, report = edit_path_description(data, ref, operation.description)
            except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
                raise APIError('CURRENT_PATH_EDIT', str(exc)[:500]) from exc
            return self.finish(args, source, data, output, report)

        from .itinerary_edit_tools import bound_dest_catalog, run_infrastructure_paths

        inputs = {name: self.checked(spec) for name, spec in operation.documents.items()}
        if operation.target_document not in inputs or len({item[0] for item in inputs.values()}) != len(inputs):
            raise APIError('DOCUMENT_SCOPE', 'Supply distinct project documents including the target')
        run_path, run_data, scope_check, scope = self.checked_document_list(operation, inputs)
        catalog_path, catalog_data, _, _ = self.checked(operation.dest_catalog)
        bound_dest_catalog(self, run_path, run_data, catalog_path)
        source, data, _, _ = inputs[operation.target_document]
        try:
            documents = {name: item[1] for name, item in inputs.items()}
            output, report = edit_path_routes(documents, operation.target_document, catalog_data, ref,
                                              [route.model_dump() for route in operation.routes], operation.description,
                                              document_paths=run_infrastructure_paths(run_data))
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('CURRENT_PATH_EDIT', str(exc)[:500]) from exc
        report['document_scope'] = {**scope, 'run_source_sha256': sha(run_data), 'dest_catalog_sha256': sha(catalog_data)}
        dependencies = {run_path: run_data, catalog_path: catalog_data,
                        **{item[0]: item[1] for name, item in inputs.items() if name != operation.target_document}}
        return self.finish(args, source, data, output, report, dependencies, scope_check)


def tool_definitions(root):
    service = MovementEdits(root)
    return [
        ('opentrack_edit_current_route',
         'Edit saved Route description, reservation/release/approach fields, or supported release groups. '
         'Exact owner identity, preview or atomic new .opentrack copy, preservation of native references. '
         'No geometry replacement or native simulation.', EditRoute, service.route, False, False),
        ('opentrack_edit_current_route_approach_batch',
         'Inspect selected native Routes or atomically apply approach length and/or speed to all selected Routes '
         'in one worksheet. Sort reports by saved description or descending number of signal aspects. '
         'Preview or save a fresh .opentrack copy.', EditRouteApproachBatch, service.route_approach_batch, False, False),
        ('opentrack_edit_current_path',
         'Edit saved Path description or replace a connected Route sequence, including existing cross-document '
         'continuations. Structural edits verify run-bound documents and the DestInfo catalog, preserve the owning '
         'End, and validate affected Itinerary endpoints, Station order and distance-based safety margins. '
         'Preview or atomically save a new .opentrack copy.', EditPath, service.edit_path, False, False),
    ]
