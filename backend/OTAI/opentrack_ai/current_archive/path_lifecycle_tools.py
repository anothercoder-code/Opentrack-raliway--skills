"""Atomic, reference-checked lifecycle operations on saved ordinary Paths."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictStr, model_validator

from ..errors import APIError
from . import catalogs, path_functions, route_factory, writer
from .bundle_tools import Source
from .graph_references import incoming_counts
from .itinerary_edit_tools import (
    ItineraryEditTools, _ordered_paths, _station_references,
    bound_dest_catalog, run_infrastructure_paths,
)
from .movement_edits import _expanded_route_chain, _linked_itineraries, _movement_project
from .multi_document.core import ident, layout, ref
from .multi_document.generate import inf
from .multi_document.operations import exact_reference, exclusive
from .multi_document_tools import Ref
from .operation_tools import Name
from .tools import Input, PathText, sha
from .zero_generation.native_signal_routes import arr, obj, string


NewName = Annotated[StrictStr, Field(min_length=1, max_length=200, pattern=r'^[^\x00-\x1f\x7f]+$')]
Description = Annotated[StrictStr, Field(max_length=4096, pattern=r'^[^\x00]*$')]
Sequence = Annotated[list[Ref], Field(min_length=1, max_length=1000)]


class CreatePath(Input):
    action: Literal['create']
    name: NewName
    routes: Sequence
    description: Description = ''


class RenamePath(Input):
    action: Literal['rename']
    path: Ref
    new_name: NewName


class MovedPath(Input):
    use_moved_path: Literal[True]


class RepairItinerary(Input):
    name: Name
    paths: Annotated[list[Ref | MovedPath], Field(min_length=1, max_length=1000)]


class RemovePath(Input):
    path: Ref
    courses: Source
    repairs: Annotated[list[RepairItinerary], Field(max_length=1000)] = Field(default_factory=list)


class DeletePath(RemovePath):
    action: Literal['delete']


class MovePath(RemovePath):
    action: Literal['move']
    routes: Sequence


class EditPathLifecycle(Input):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    dest_catalog: Source
    edit: Annotated[CreatePath | RenamePath | DeletePath | MovePath, Field(discriminator='action')]
    preview_only: StrictBool = True
    target_directory: PathText | None = None

    @model_validator(mode='after')
    def require_target(self):
        if not self.preview_only and self.target_directory is None:
            raise ValueError('Saving requires a fresh target_directory')
        return self


require = route_factory.require


def _get_path(project, reference):
    document, identity = exact_reference(reference)
    return project.owned((document, identity[2]), 'OTPath', identity)


def _name_available(project, catalog, name, except_path=None, except_identity=None):
    folded = name.casefold()
    for root in (*project.roots.values(), catalog):
        for item in writer.objects(root):
            if writer.kind(item) == 'OTPath' and item is not except_path:
                require(path_functions.string(item.contents[1].value).casefold() != folded,
                        'The Path name already exists in the selected project')
            if writer.kind(item) == 'OTArrayExtInfo':
                if except_identity is not None and any(_references([item], except_identity)):
                    continue
                require(path_functions.string(item.contents[0].value).casefold() != folded,
                        'The Path name would capture an existing external reference')


def _allocated_path(project, name, description, selected, movement):
    document, start_id = owner_key = movement[0]
    owner = project.model(owner_key)
    root = project.roots[document]
    path_functions.guard_counter_references(root, owner, allow_local_shunting=True)
    holder = owner.contents[17].value
    exclusive(root, holder)
    highwater = owner.contents[19].value
    require(type(highwater) is int and -1 <= highwater < 2147483647, 'Native Path ID counter is invalid or exhausted')
    path = obj(path_functions.SHAPES['OTPath'][0], [
        ('@', [arr([selected[0][1]])]), ('@', [string(name)]), ('ii', [highwater + 1, start_id]),
        ('@', [string(description)]), ('@', [arr([inf(route) for _, route in selected])]),
    ])
    return owner, holder.contents[0].value, path


class Changes:
    def __init__(self):
        self.undo = []
        self.touched = set()

    def _record(self, root, item, restore):
        self.touched.add(id(root))
        self.undo.append((item, restore))

    def contents(self, root, item, values):
        self._record(root, item, list(item.contents))
        writer.set_elements(item, values)

    def group(self, root, item, values):
        self._record(root, item, list(item.values))
        item.values[:] = values

    def restore(self):
        for item, value in reversed(self.undo):
            if isinstance(item, writer.TypedGroup):
                item.values[:] = value
            else:
                item.contents[:] = value


def _references(items, identity):
    for item in items:
        name = path_functions.string(item.contents[0].value)
        document = path_functions.string(item.contents[2].value)
        array_id, start_id = item.contents[1].values
        if {'name': name, 'document': document, 'array_id': array_id, 'start_id': start_id} == identity:
            yield item


def _guard_fresh_identity(project, catalog, identity):
    for root in (*project.roots.values(), catalog):
        for item in writer.objects(root):
            if writer.kind(item) != 'OTArrayExtInfo':
                continue
            layout(item, [('OTArrayExtInfo', 0), ('OTArrayInfo', 0), ('NSObject', 0)], ['@', 'ii', '@'])
            label = path_functions.string(item.contents[2].value)
            require(label.casefold() != identity['document'].casefold()
                    or item.contents[1].values != [identity['array_id'], identity['start_id']],
                    'New Path ID would capture an existing external reference')


def _saved_movements(project):
    return {path_functions.info(item)['name']: project.dest_view(item)[0] for item in project.dests}


def _saved_references(project):
    records = (path_functions.info(item) for item in project.dests)
    return {record['name']: record['saved_references'] for record in records}


def _incident_bindings(courses, project, identity):
    root = writer.load_next_compatible(courses)[0]
    catalogs.course_items(root)
    require(root.contents[0].value == 17, 'Unsupported native CourseList marker')
    documents = {name.casefold() for name in project.roots}
    for incident in writer.objects(root):
        if writer.kind(incident) == 'OTIncident':
            require(incident.clazz.version in (9, 10, 11, 12) and len(incident.contents) > 5
                    and incident.contents[2].encodings == [b'@'] and incident.contents[5].encodings == [b'i'] * 3,
                    'Cannot verify Path references in this native Incident layout')
            array_id, start_id, kind = incident.contents[5].values
            if kind == 5 and (array_id, start_id) == (identity['array_id'], identity['start_id']):
                document = catalogs.text(incident.contents[2].value)
                require(document.casefold() in documents and document.casefold() != identity['document'].casefold(),
                        'Cannot delete or move a Path referenced by a Path-speed Incident')


def _repair_references(project, catalog, removed, repairs, changes, movements):
    if not repairs:
        return
    catalog_rows = {path_functions.string(row.contents[1].value): row
                    for row in route_factory.wrapper(catalog, 'OTDestInfoList')}
    catalog_counts = incoming_counts(catalog)
    document_counts = {name: incoming_counts(root) for name, root in project.roots.items()}
    for dest in project.dests:
        name = path_functions.string(dest.contents[1].value)
        if name not in repairs:
            continue
        owner, _ = project.owners[id(dest)]
        root = project.roots[owner]
        old_movement = movements[name]
        requested = repairs[name]
        require(removed is None or removed not in requested, 'Repair paths cannot reference a Path being removed')
        selected, movement = _ordered_paths(project, requested, old_movement[0])
        require(movement[-1] == old_movement[-1], 'Itinerary repair must preserve its directional endpoints')
        require(_station_references(project, movement) == _station_references(project, old_movement),
                'Itinerary repair must preserve ordered station references')
        margins = route_factory.wrapper(dest.contents[5].value, 'OTSafetyMarginArray')
        require(not margins or movement == old_movement,
                'Changing the movement of an Itinerary with distance-based safety margins requires prior review')
        movements[name] = movement
        if path_functions.info(dest)['saved_references'] == requested:
            continue
        row = catalog_rows[name]
        require(document_counts[owner][id(dest)] == 1 and catalog_counts[id(row)] == 1,
                'Shared Itinerary or DestInfo owner')
        # If a new Path was staged on the same in-memory project then its object
        # can be used only in the document that really owns the Itinerary.
        require(selected[0][0] == owner, 'First Path must belong to the Itinerary document')
        changes.group(root, dest.contents[0], [path_functions.array_like(dest.contents[0].value, [selected[0][1]])])
        changes.group(root, dest.contents[4], [path_functions.array_like(dest.contents[4].value,
                      [inf(path, document) for document, path in selected])])
        changes.group(catalog, row.contents[4], [path_functions.array_like(row.contents[4].value,
                      [inf(path, document) for document, path in selected])])


def edit_path_lifecycle(documents, native_paths, catalog_blob, request, courses=None):
    project = _movement_project(documents, native_paths, catalog_blob)
    catalog, catalog_version = writer.load_next_compatible(catalog_blob)
    roots = {**project.roots, '$dest_catalog': catalog}
    before = {name: writer.fingerprint(root) for name, root in roots.items()}
    expected_movements = _saved_movements(project)
    changes = Changes()
    action = request['action']
    new_identity = None
    movement = None
    dependents = set()
    expected_refs = _saved_references(project)

    if action == 'create':
        _name_available(project, catalog, request['name'])
        document, (_, _, start_id) = exact_reference(request['routes'][0])
        selected, movement = _expanded_route_chain(project, (document, start_id), request['routes'])
        owner, holder, path = _allocated_path(
            project, request['name'], request['description'], selected, movement)
        new_identity = {'document': document, **ref(path)}
        _guard_fresh_identity(project, catalog, new_identity)
        root = project.roots[document]
        changes.contents(root, holder, path_functions.mutable_array(holder) + [path])
        changes.group(root, owner.contents[19], [path.contents[2].values[0]])
    else:
        identity = request['path']
        document = identity['document']
        root = project.roots[document]
        path = _get_path(project, identity)
        dependents = _linked_itineraries(project, catalog_blob, document, path,
                                         {key: identity[key] for key in ('name', 'array_id', 'start_id')})
        if action == 'rename':
            new_name = request['new_name']
            require(new_name != identity['name'], 'Use a distinct Path name')
            _name_available(project, catalog, new_name, path, identity)
            movement = project.path_view(path)[0]
            changes.group(root, path.contents[1], [path_functions.fresh_string(path.contents[1].value, new_name)])
            for dest in project.dests:
                name = path_functions.info(dest)['name']
                if name not in dependents:
                    continue
                doc, _ = project.owners[id(dest)]
                for info in _references(path_functions.mutable_array(dest.contents[4].value), identity):
                    changes.group(project.roots[doc], info.contents[0],
                                  [path_functions.fresh_string(info.contents[0].value, new_name)])
            for row in route_factory.wrapper(catalog, 'OTDestInfoList'):
                if path_functions.string(row.contents[1].value) in dependents:
                    for info in _references(path_functions.mutable_array(row.contents[4].value), identity):
                        changes.group(catalog, info.contents[0], [path_functions.fresh_string(info.contents[0].value, new_name)])
            new_identity = {**identity, 'name': new_name}
            for name in dependents:
                expected_refs[name] = [new_identity if entry == identity else entry for entry in expected_refs[name]]
        else:
            _incident_bindings(courses, project, identity)
            repairs = {repair['name']: repair['paths'] for repair in request['repairs']}
            require(set(repairs) == dependents and len(repairs) == len(request['repairs']),
                    'Supply exactly one repaired sequence for every dependent Itinerary: ' + ', '.join(sorted(dependents)))
            removed = identity
            if action == 'move':
                new_document, (_, _, start_id) = exact_reference(request['routes'][0])
                selected, movement = _expanded_route_chain(project, (new_document, start_id), request['routes'])
                if movement[0] == (document, identity['start_id']):
                    _, old_routes = project.path_view(path)
                    new_routes = [(doc, ref(route)) for doc, route in selected]
                    require(new_routes != old_routes, 'Provide a changed Route sequence')
                    counts = incoming_counts(root)
                    require(all(counts[id(path.contents[field].value)] == 1 for field in (0, 4)), 'Shared Path Route array')
                    changes.group(root, path.contents[0], [path_functions.array_like(path.contents[0].value, [selected[0][1]])])
                    changes.group(root, path.contents[4], [path_functions.array_like(path.contents[4].value,
                                  [inf(route) for _, route in selected])])
                    project.path_views[id(path)] = (movement, new_routes)
                    new_identity = identity
                    removed = None
                else:
                    target_end = project.model(movement[0])
                    existing = (route_factory.wrapper(target_end.contents[16].value, 'OTShuntingList')
                                + route_factory.wrapper(target_end.contents[17].value, 'OTPathList'))
                    require(not any(ident(other)[0].casefold() == identity['name'].casefold() for other in existing),
                            'A Path at the destination End already uses this name')
                    new_owner, new_holder, replacement = _allocated_path(
                        project, identity['name'], path_functions.info(path)['description'], selected, movement)
                    new_identity = {'document': new_document, **ref(replacement)}
                    _guard_fresh_identity(project, catalog, new_identity)
                    _incident_bindings(courses, project, new_identity)
                    new_root = project.roots[new_document]
                    changes.contents(new_root, new_holder, path_functions.mutable_array(new_holder) + [replacement])
                    changes.group(new_root, new_owner.contents[19], [new_identity['array_id']])
                    project.owners[id(replacement)] = movement[0]
                    project.path_view(replacement)
            require(action == 'move' or not any('use_moved_path' in entry for refs in repairs.values() for entry in refs),
                    'use_moved_path is only available when moving a Path')
            repairs = {name: [new_identity if 'use_moved_path' in entry else entry for entry in refs]
                       for name, refs in repairs.items()}
            _repair_references(project, catalog, removed, repairs, changes, expected_movements)
            expected_refs.update(repairs)
            if removed is not None:
                owner_key = (document, identity['start_id'])
                holder = project.model(owner_key).contents[17].value
                exclusive(root, holder)
                array = holder.contents[0].value
                changes.contents(root, array, [entry for entry in path_functions.mutable_array(array) if entry is not path])

    output = {name: writer.dump_verified(root, project.versions[name]) if id(root) in changes.touched else documents[name]
              for name, root in project.roots.items()}
    new_catalog = writer.dump_verified(catalog, catalog_version) if id(catalog) in changes.touched else catalog_blob
    checked = _movement_project(output, native_paths, new_catalog)
    require(_saved_references(checked) == expected_refs, 'Itinerary reference readback differs from the requested operation')
    require(_saved_movements(checked) == expected_movements, 'Itinerary movement readback differs from the requested operation')
    if new_identity is not None:
        require(checked.path_view(_get_path(checked, new_identity))[0] == movement,
                'Path movement differs after archive reload')
    if action == 'delete' or (action == 'move' and new_identity != request['path']):
        identity = request['path']
        require(not any(checked.owners[id(item)] == (identity['document'], identity['start_id'])
                        and ident(item)[1] == identity['array_id'] for item in checked.paths_objects),
                'Old Path identity is still allocated to an ordinary Path')
    changes.restore()
    require({name: writer.fingerprint(root) for name, root in roots.items()} == before,
            'Archive changes include fields outside the requested transaction')
    return output, new_catalog, {'operation': action + '_native_path', 'path': new_identity or request['path'],
        'dependent_itineraries': sorted(dependents), 'movement': movement, 'dest_catalog_changed': new_catalog != catalog_blob,
        'running_time_revalidation_required': action in ('delete', 'move') and bool(dependents),
        'native_simulation_executed': False}


def _bound_course(service, binding, run, run_blob):
    rows = [line.split('#') for line in run_blob.decode('ascii').splitlines() if line.startswith('CourseFile#')]
    require(len(rows) == 1 and len(rows[0]) == 3 and not rows[0][-1], 'Expected one native CourseFile binding')
    raw = rows[0][1]
    path = Path(raw)
    if not path.is_absolute():
        path = run.parent / path
    require(raw and not any(char in raw for char in '%$\\') and '..' not in path.parts
            and path.suffix == '.courses' and path.is_relative_to(run.parent), 'Unsupported CourseFile binding')
    selected, blob, _, _ = service.checked(binding)
    require(selected == path, 'Selected Course catalog differs from the run CourseFile')
    return selected, blob


class PathLifecycleTools(ItineraryEditTools):
    def edit(self, args):
        inputs = {name: self.checked(source) for name, source in args.documents.items()}
        catalog_path, catalog, _, _ = self.checked(args.dest_catalog)
        paths = {name: item[0] for name, item in inputs.items()}
        if len({catalog_path, *paths.values()}) != len(paths) + 1:
            raise APIError('PATH_LIFECYCLE_SCOPE', 'Use distinct archive files')
        run, run_blob, check_scope, scope = self.checked_document_list(args, inputs)
        bound_dest_catalog(self, run, run_blob, catalog_path)
        if args.target_directory is not None and self.path(args.target_directory).is_relative_to(run.parent):
            raise APIError('PATH_LIFECYCLE_SCOPE', 'Use a fresh target outside the source project')
        documents = {name: item[1] for name, item in inputs.items()}
        dependencies = {run: run_blob, catalog_path: catalog, **{item[0]: item[1] for item in inputs.values()}}
        spec = args.edit.model_dump()
        try:
            courses = None
            if isinstance(args.edit, RemovePath):
                course_path, courses = _bound_course(self, args.edit.courses, run, run_blob)
                dependencies[course_path] = courses
            changed, dest_output, report = edit_path_lifecycle(documents, run_infrastructure_paths(run_blob),
                                                                catalog, spec, courses)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
            raise APIError('CURRENT_PATH_LIFECYCLE', str(error)[:500]) from error
        settings = {paths[name]: blob for name, blob in changed.items() if blob != documents[name]}
        if dest_output != catalog:
            settings[catalog_path] = dest_output
        members = {file.name: blob for file, blob in settings.items()}
        manifest = {'format': 'opentrack-current-path-lifecycle-v1', 'document_scope': scope,
                    'files': {name: {'sha256': sha(blob), 'bytes': len(blob)} for name, blob in members.items()},
                    'replacement_for': {file.name: file.relative_to(self.root).as_posix() for file in settings},
                    'sources': {file.relative_to(self.root).as_posix(): {'sha256': sha(blob)}
                                for file, blob in dependencies.items()}, 'complete_relocated_project': False}
        result = {'preview_only': args.preview_only, 'saved': False, 'manifest': manifest,
                  'bundle_type': 'Path lifecycle with dependent worksheets and DestInfo', 'change_report': report,
                  'fresh_archive_reload_verified': True, 'native_application_started': False}
        return self.publish_bundle(inputs=dependencies, members=members, manifest=manifest, result=result,
                                   target_directory=args.target_directory, scope_check=check_scope, windows_publication=True)


def tool_definitions(root):
    return [('opentrack_edit_current_path_lifecycle', 'Create an ordinary cross-document Path, rename it with its saved '
             'Itinerary references, or delete or move it with explicit repairs for every affected Itinerary. '
             'Removals check the run-bound Course catalog for Path-speed Incidents. Preview or save the changed '
             'worksheets and DestInfo together.', EditPathLifecycle, PathLifecycleTools(root).edit, False, False)]
