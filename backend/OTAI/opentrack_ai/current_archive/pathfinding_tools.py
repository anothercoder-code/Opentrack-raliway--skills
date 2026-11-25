"""Find and save native Paths between successive exit signals on saved Routes."""

from collections import defaultdict
from typing import Annotated, Literal

from pydantic import Field, StrictInt

from ..errors import APIError
from . import path_functions, route_factory, writer
from .bundle_tools import CourseBundles, Source
from .itinerary_edit_tools import bound_dest_catalog, run_infrastructure_paths
from .movement_edits import _movement_project
from .multi_document.core import ref
from .next_tools import NextFunctions, Ordinal
from .operation_tools import Name
from .path_append import MAX_ROUTES
from .path_lifecycle_tools import Changes, _allocated_path, _bound_course, _guard_fresh_identity, _incident_bindings
from .project_candidate_publication import ProjectSave
from .route_discovery_tools import main_signal
from .tools import sha


class FindPaths(ProjectSave):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    dest_catalog: Source
    courses: Source
    document: Name
    start_end_ids: Annotated[list[Ordinal], Field(max_length=1000)] = Field(default_factory=list)
    naming: Literal['standard', 'treno'] = 'standard'
    duplicate_policy: Literal['reuse', 'append'] = 'reuse'
    max_paths: Annotated[StrictInt, Field(ge=1, le=1000)] = 100
    max_expansions: Annotated[StrictInt, Field(ge=1, le=1_000_000)] = 50_000


require = route_factory.require


def exit_signal(end):
    return (writer.kind(end) == 'OTEndModel' and main_signal(end)
            and end.contents[11].value.contents[8].values[1] == 4)


def _text(obj):
    return '' if obj is None else path_functions.string(obj)


def _end_label(project, key, naming):
    end = project.model(key)
    station = end.contents[12].value
    prefix = '' if station is None else _text(station.contents[7].value)
    prefix = prefix + '_' if prefix else ''
    addition = _text(end.contents[18].value) or _text(project.model(project.related(key)).contents[18].value)
    signal = _text(end.contents[11].value.contents[13].value)
    if signal:
        return prefix + '_'.join(part for part in (addition, signal if naming == 'standard' else '') if part)
    return prefix + (addition or f'[{key[1]}]')


def _name(project, source, destination, naming):
    return f'P:{_end_label(project, source, naming)}-{_end_label(project, destination, naming)}'


def _route_index(project):
    index = defaultdict(list)
    for route in project.routes:
        owner = project.owners[id(route)]
        if writer.kind(project.model(owner)) == 'OTEndModel':
            index[owner].append((route, tuple(project.route_view(route))))
    return index


def _discover(project, document, starts, max_paths, max_expansions):
    require(document in project.roots, 'Select a worksheet in the run document set')
    eligible = [project.key(end) for end in project.ends(document) if exit_signal(end)]
    if starts:
        requested = [(document, end_id) for end_id in starts]
        require(len(set(requested)) == len(requested), 'Duplicate selected starting End')
        require(all(key in eligible for key in requested), 'Every selected End must be an original exit signal')
        eligible = requested

    index = _route_index(project)
    paths = []
    rejected_revisited = expansions = 0
    for start in eligible:
        movement = [start]
        visited = {start}
        chain = []
        pending = [(iter(index[start]), 0)]
        while pending:
            routes, entered = pending[-1]
            next_route = next(routes, None)
            if next_route is None:
                pending.pop()
                if entered:
                    visited.difference_update(movement[-entered:])
                    del movement[-entered:]
                    chain.pop()
                continue
            expansions += 1
            require(expansions <= max_expansions, 'Pathfinding expansion limit reached; narrow the selected starting Ends')
            route, nodes = next_route
            tail = nodes[1:]
            if not visited.isdisjoint(tail):
                rejected_revisited += 1
                continue
            require(len(movement) + len(tail) <= MAX_ROUTES, 'Expanded Path exceeds the supported directional-End limit')
            destination = tail[-1]
            segment = (nodes[0][0], route)
            if exit_signal(project.model(destination)):
                paths.append(((*movement, *tail), (*chain, segment)))
                require(len(paths) <= max_paths, 'Pathfinding result limit reached; narrow the selected starting Ends')
            elif index[destination]:
                movement.extend(tail)
                visited.update(tail)
                chain.append(segment)
                pending.append((iter(index[destination]), len(tail)))
    return eligible, paths, expansions, rejected_revisited


def _unique_name(base, used):
    for number in range(10000):
        candidate = base if number == 0 else f'{base}.{number}'
        if candidate.casefold() not in used:
            return candidate
    raise ValueError('No free original Path name suffix')


def _generated_name(name, base):
    stem, dot, suffix = name.rpartition('.')
    return name == base or (dot and stem == base and suffix.isascii() and suffix.isdecimal()
                            and 1 <= len(suffix) <= 4 and suffix[0] != '0')


def find_paths(documents, paths, catalog_blob, courses, spec):
    project = _movement_project(documents, paths, catalog_blob)
    catalog, _ = writer.load_next_compatible(catalog_blob)
    eligible, proposals, expansions, revisited = _discover(
        project, spec.document, spec.start_end_ids, spec.max_paths, spec.max_expansions)
    document = spec.document
    root = project.roots[document]
    before = writer.fingerprint(root)
    changes = Changes()
    results = []
    try:
        for movement, selected in proposals:
            start, destination = movement[0], movement[-1]
            owner = project.model(start)
            existing = route_factory.wrapper(owner.contents[17].value, 'OTPathList')
            base = _name(project, start, destination, spec.naming)
            route_refs = [(sheet, ref(route)) for sheet, route in selected]
            same = next((item for item in existing if _generated_name(ref(item)['name'], base)
                         and path_functions.info(item)['saved_references'] == [r for _, r in route_refs]), None)
            if spec.duplicate_policy == 'reuse' and same is not None:
                path = same
                outcome = 'reused'
            else:
                name = _unique_name(base, {ref(item)['name'].casefold() for item in existing})
                require(len(name) <= 200 and all(ord(char) >= 32 and ord(char) != 127 for char in name),
                        'Original Path name cannot be represented within the supported Path reference domain')
                owner, holder, path = _allocated_path(project, name, '', selected, movement)
                identity = {'document': document, **ref(path)}
                _guard_fresh_identity(project, catalog, identity)
                _incident_bindings(courses, project, identity)
                changes.contents(root, holder, [*existing, path])
                changes.group(root, owner.contents[19], [identity['array_id']])
                outcome = 'created'
            results.append({
                'path': {'document': document, **ref(path)}, 'result': outcome,
                'movement': movement, 'routes': [{'document': sheet, **route} for sheet, route in route_refs],
                'distance_m': sum(project.model(project.edge_between(a, b)).contents[9].values[1]
                                  for a, b in zip(movement, movement[1:])),
            })

        output = documents[document]
        if changes.touched:
            output = writer.dump_verified(root, project.versions[document])
            fresh = _movement_project({**documents, document: output}, paths, catalog_blob)
            for row in results:
                path = row['path']
                reloaded = fresh.owned((document, path['start_id']), 'OTPath',
                                       (path['name'], path['array_id'], path['start_id']))
                movement, route_refs = fresh.path_view(reloaded)
                require(movement == list(row['movement'])
                        and [{'document': sheet, **route} for sheet, route in route_refs] == row['routes'],
                        'New Path or saved Route sequence failed fresh readback')
    finally:
        changes.restore()
    require(writer.fingerprint(root) == before, 'Pathfinding changed fields outside the new Paths and owner counters')
    return output, {
        'selected_document': document, 'eligible_starts': eligible, 'paths': results,
        'expansions': expansions, 'revisited_end_branches_excluded': revisited, 'naming': spec.naming,
        'created_count': sum(row['result'] == 'created' for row in results), 'unchanged_archive_graph_verified': True,
    }


class PathfindingTools(NextFunctions, CourseBundles):
    def find(self, args):
        inputs = {name: self.checked(source) for name, source in args.documents.items()}
        run_path, run, scope_check, scope = self.checked_document_list(args, inputs)
        catalog_path, catalog, _, _ = self.checked(args.dest_catalog)
        bound_dest_catalog(self, run_path, run, catalog_path)
        if args.target_directory is not None and self.path(args.target_directory).is_relative_to(run_path.parent):
            raise APIError('CURRENT_PATHFINDING', 'Publish outside the bound source project')
        documents = {name: item[1] for name, item in inputs.items()}
        try:
            course_path, courses = _bound_course(self, args.courses, run_path, run)
            output, report = find_paths(documents, run_infrastructure_paths(run), catalog, courses, args)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
            raise APIError('CURRENT_PATHFINDING', str(error)[:500]) from error
        dependencies = {run_path: run, catalog_path: catalog, course_path: courses,
                        **{item[0]: item[1] for item in inputs.values()}}
        changed = output != documents[args.document]
        source_path = inputs[args.document][0]
        manifest = {
            'format': 'opentrack-native-exit-pathfinding-increment-v1', 'document_scope': scope,
            'files': {source_path.name: {'sha256': sha(output), 'bytes': len(output)}} if changed else {},
            'replacement_for': {source_path.name: source_path.relative_to(self.root).as_posix()} if changed else {},
            'sources': {file.relative_to(self.root).as_posix(): {'sha256': sha(blob)}
                        for file, blob in dependencies.items()}, 'complete_relocated_project': False,
        }
        result = {'preview_only': args.preview_only, 'saved': False, 'manifest': manifest, 'change_report': report,
                  'fresh_archive_reload_verified': changed, 'native_application_started': False}
        if not changed:
            from ..json_safe import checked_json

            scope_check()
            for file, blob in dependencies.items():
                if self.secure_bytes(file) != blob:
                    raise APIError('SOURCE_CHANGED', 'A Pathfinding input changed', str(file))
            return checked_json(result)
        return self.publish_bundle(
            inputs=dependencies, members={source_path.name: output}, manifest=manifest, result=result,
            target_directory=args.target_directory, scope_check=scope_check,
        )


def tool_definitions(root):
    return [('opentrack_find_and_save_exit_paths',
             'Find every supported exit-to-next-exit Path over existing saved Routes in a bound project. '
             'Select one worksheet and optional starting End IDs. Apply verified OpenTrack or Treno names '
             'and preview or save fresh worksheet bytes, preserving existing Route and Itinerary identities.',
             FindPaths, PathfindingTools(root).find, False, False)]
