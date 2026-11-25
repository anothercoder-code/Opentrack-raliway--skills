"""Save cross-document itineraries composed of ordinary Paths and local Shunting Paths."""

from typing import Annotated, Literal

from pydantic import Field, StrictInt

from ..errors import APIError
from . import catalogs, course_factories, path_functions, route_factory, writer
from .current_shunting_tools import CreateShunting
from .current_shunting_workflow import core as shunting
from .finite_itinerary_workflow import MAX_PATH_REFERENCES, create_finite_itinerary
from .itinerary_edit_tools import (
    EditableItineraryProject, ItineraryEditTools, ProjectItineraryEdit, _project,
    _select_dest, bound_dest_catalog, replace_paths, run_infrastructure_paths,
)
from .multi_document.core import ident, need, ref
from .multi_document.operations import create_path, exclusive
from .multi_document_tools import Inventory, MultiDocumentTools, NewPath, Ref
from .operation_tools import Name
from .prepare_contract.preflight import check as preflight
from .project_candidate_publication import ProjectSave, project_target, publish_candidate, require_external_target
from .project_workflow.relocation import relocate_project
from .tools import Input, sha


class OrdinarySegment(Ref):
    kind: Literal['path']


class ExistingShuntingSegment(Ref):
    kind: Literal['shunting']


class NewShuntingSegment(CreateShunting):
    kind: Literal['create_shunting']
    action: Literal['create'] = 'create'
    document: Name


class NewCrossingPath(Ref):
    kind: Literal['create_crossing_path']
    path_name: Name


class NewOrdinaryPath(NewPath):
    kind: Literal['create_ordinary_path']


Segment = Annotated[OrdinarySegment | ExistingShuntingSegment | NewShuntingSegment | NewCrossingPath | NewOrdinaryPath,
                    Field(discriminator='kind')]
Segments = Annotated[list[Segment], Field(min_length=2, max_length=MAX_PATH_REFERENCES)]


class EditSegmentedShunting(ProjectItineraryEdit):
    action: Literal['create_itinerary', 'replace_paths']
    paths: Segments


EndId = Annotated[StrictInt, Field(ge=0, le=2147483647)]
ConnectorKey = Annotated[tuple[Name, EndId], Field(strict=False)]


class DirectedBoundary(Input):
    source_connector: ConnectorKey
    receiving_connector: ConnectorKey


class RebindShunting(ProjectSave):
    source_project: Inventory
    name: Name
    paths: Segments
    expected_bound_courses: Annotated[list[Name], Field(min_length=1, max_length=1000)]


class RebindSingleBoundaryShunting(RebindShunting):
    boundary: DirectedBoundary


class RebindMultiBoundaryShunting(RebindShunting):
    boundaries: Annotated[list[DirectedBoundary], Field(min_length=2, max_length=99)]


def _create_local_path(project, document, spec, catalog):
    keys = [(document, value) for value in spec['end_ids']]
    need(len(keys) >= 2 and len(set(keys)) == len(keys), 'Use a simple local Shunting movement')
    nodes = [project.model(key) for key in keys]
    need(all(writer.kind(node) == 'OTEndModel' for node in nodes), 'Local Shunting requires ordinary Ends')
    for first, last in zip(keys, keys[1:]):
        project.edge_between(first, last)
    name = spec['name']
    for root in (*project.roots.values(), writer.load(catalog)[0]):
        for record in writer.objects(root):
            kind = writer.kind(record)
            if kind in ('OTPath', 'OTRoute', 'OTShunting'):
                need(path_functions.string(record.contents[1].value) != name, 'Movement name already exists')
            if kind in ('OTArrayInfo', 'OTArrayExtInfo'):
                need(path_functions.string(record.contents[0].value) != name, 'Movement name would capture a saved reference')
            if kind in ('OTRoute', 'OTShunting'):
                need(path_functions.string(record.contents[7].value) != name, 'Movement name would capture a saved Overlap')
    root, version = project.roots[document], project.versions[document]
    owner = nodes[0]
    path_functions.guard_counter_references(root, owner, allow_local_shunting=True)
    holder = owner.contents[16].value
    exclusive(root, holder)
    array = holder.contents[0].value
    original_groups = list(array.contents)
    original_graph = writer.fingerprint(root)
    path, allocation = shunting.allocate_shunting_path(nodes, spec)
    writer.set_elements(array, path_functions.mutable_array(array) + [path])
    owner.contents[19].value = allocation['saved_highest_rsp_id']
    output = writer.dump_verified(root, version)
    array.contents = original_groups
    owner.contents[19].value = allocation['previous_highest_rsp_id']
    need(writer.fingerprint(root) == original_graph, 'Unexpected Shunting changes outside the owner and ID counter')
    return output, {'document': document, **ref(path)}, allocation


def _match_boundary(project, reference, first, second, expected):
    local = project.related(first)
    need(writer.kind(project.model(local)) == 'OTConnModel', 'Directed movement lacks a source connector')
    remote = project.block_end(local)
    need(local == expected['source_connector'] and remote == expected['receiving_connector'],
         'Actual directed connector pair differs from the requested source and receiving connectors')
    need(project.block_end(remote) == local and project.actual_related(first) == project.related(remote),
         'Expected reciprocal native connector and its receiving directed End')
    return {'approach_end': first, 'source_connector': local, 'receiving_connector': remote,
            'receiving_departure_end': project.related(remote), 'receiving_arrival_end': second,
            'crossing_path': reference, 'crossing_edge': project.edge_between(first, second)}


def _match_boundaries(project, movement, references, kinds, crossings, expected):
    need(len(crossings) == len(expected), 'Saved movement must match the number of declared worksheet boundaries')
    need(len(movement) == len(set(movement)), 'A boundary shunting itinerary must not repeat a directed End')
    if len(crossings) > 1:
        first_path_index, last_path_index = crossings[0][2], crossings[-1][2]
        need('shunting' in kinds[first_path_index + 1:last_path_index],
             'Select a local Shunting Path between two declared worksheet crossings')
    return [_match_boundary(project, references[index], start, end, requested)
            for (start, end, index), requested in zip(crossings, expected, strict=True)]


def _create_ordinary_segment(project, documents, document_paths, catalog, segment):
    single = segment['kind'] == 'create_crossing_path'
    if single:
        routes = [{key: segment[key] for key in ('document', 'name', 'array_id', 'start_id')}]
        name = segment['path_name']
    else:
        routes, name = segment['routes'], segment['name']
    need(not any(existing == name for _, existing in project.shunting_movements),
         'Ordinary Path name would shadow a native Shunting Path')
    changed, report = create_path(
        documents, catalog, document_paths=document_paths, complete_document_set=True,
        expected_hashes={**{key: sha(blob) for key, blob in documents.items()}, '$dest_catalog': sha(catalog)},
        name=name, routes=routes, project_type=EditableItineraryProject)
    if single:
        nodes = report['runtime_end_keys']
        need(sum(a[0] != b[0] for a, b in zip(nodes, nodes[1:])) == 1,
             'Create the crossing Path from exactly one native continued ordinary Route')
    return changed, report['created']


def edit_segmented(documents, document_paths, catalog, name, segments, action, description=None, *, boundaries=None):
    changed = dict(documents)
    project = _project(changed, document_paths, catalog)
    refs, kinds, movement, edges, crossings, shunting_controls = [], [], [], [], [], []
    new_allocations = []
    if boundaries is not None:
        original_movement, _ = project.dest_view(_select_dest(project, name))
        original_edges = [project.edge_between(start, end) for start, end in zip(original_movement, original_movement[1:])]
    previous = None
    for segment in segments:
        kind = segment['kind']
        if kind in ('create_crossing_path', 'create_ordinary_path'):
            changed, reference = _create_ordinary_segment(project, changed, document_paths, catalog, segment)
            project = _project(changed, document_paths, catalog)
            kind = 'path'
        elif kind == 'create_shunting':
            spec = {key: value for key, value in segment.items() if key not in ('kind', 'document', 'action')}
            document = segment['document']
            changed[document], reference, allocation = _create_local_path(project, document, spec, catalog)
            project = _project(changed, document_paths, catalog)
            shunting.verify_shunting_allocation(project.model((document, reference['start_id'])),
                                                {key: value for key, value in reference.items() if key != 'document'},
                                                allocation)
            if allocation['editor_copy_rsp_id'] is not None:
                new_allocations.append({'path': reference, **allocation})
            kind = 'shunting'
        else:
            reference = {key: segment[key] for key in ('document', 'name', 'array_id', 'start_id')}
        start = (reference['document'], reference['start_id'])
        need(previous is None or previous == start, 'Segments must join at the same directional End')
        identity = tuple(reference[key] for key in ('name', 'array_id', 'start_id'))
        selected = (project.itinerary_path(start, identity) if kind == 'shunting'
                    else project.owned(start, 'OTPath', identity))
        automatic = route_factory.wrapper(project.model(start).contents[16].value, 'OTShuntingList')
        need(any(row is selected for row in automatic) == (kind == 'shunting'),
             'Segment kind must agree with the native ordinary or automatic Shunting list')
        if kind == 'shunting':
            body, = path_functions.mutable_array(selected.contents[0].value)
            security = body.contents[5].values
            shunting_controls.append({'path': reference, 'speed_kmh': body.contents[-1].value,
                                      'release_time_s': security[2], 'reservation_time_s': security[3]})
        nodes = project.path_view(selected)[0]
        crossings.extend((first, last, len(refs)) for first, last in zip(nodes, nodes[1:])
                         if first[0] != last[0])
        refs.append(reference)
        kinds.append(kind)
        movement.extend(nodes if not movement else nodes[1:])
        edges.append([project.edge_between(first, last) for first, last in zip(nodes, nodes[1:])])
        previous = nodes[-1]
    need('shunting' in kinds, 'At least one local Shunting segment is required')
    need(crossings, 'The ordinary Paths must cross a connected document boundary')
    boundary_receipt = {}
    if boundaries is not None:
        need(movement == original_movement and [edge for segment in edges for edge in segment] == original_edges,
             'An in-use Itinerary must preserve the complete directed walk, physical edges and station references')
        matched = _match_boundaries(project, movement, refs, kinds, crossings, boundaries)
        boundary_receipt = {'directed_boundaries': matched, 'physical_edges_preserved': True}
        if len(matched) == 1:
            boundary_receipt['directed_boundary'] = matched[0]
    if action == 'replace_paths':
        output, catalog_output, report = replace_paths(changed, catalog, document_paths, name, refs, description)
        changed[report['owner_document']] = output
    else:
        bundle, report = create_finite_itinerary(changed, catalog, document_paths=document_paths,
            expected_hashes={**{key: sha(blob) for key, blob in changed.items()}, '$dest_catalog': sha(catalog)},
            complete_document_set=True, name=name, paths=refs, description=description or '',
            project_type=EditableItineraryProject)
        changed, catalog_output = bundle['documents'], bundle['catalog']
    if new_allocations:
        report['created_shunting_rsp_allocations'] = new_allocations
    return changed, catalog_output, {**report, 'operation': 'edit_segmented_shunting_itinerary',
        'name': name, 'segment_kinds': kinds, 'segment_edges': edges, 'ordered_paths': refs,
        'shunting_controls': shunting_controls,
        'runtime_end_keys': movement, 'single_cross_document_shunting_record': False, **boundary_receipt}


class SegmentedShuntingTools(ItineraryEditTools):
    def edit(self, args):
        inputs = {key: self.checked(source) for key, source in args.documents.items()}
        catalog_path, catalog, _, _ = self.checked(args.catalog)
        path_by_key = {key: item[0] for key, item in inputs.items()}
        self.same_project([catalog_path, *path_by_key.values()])
        if len({catalog_path, *path_by_key.values()}) != len(inputs) + 1:
            raise APIError('SHUNTING_ITINERARY_SCOPE', 'Use distinct input files')
        runpath, runblob, scope_check, evidence = self.checked_document_list(args, inputs)
        bound_dest_catalog(self, runpath, runblob, catalog_path)
        if args.target_directory is not None and self.path(args.target_directory).is_relative_to(runpath.parent):
            raise APIError('SHUNTING_ITINERARY_SCOPE', 'Use a fresh target outside the source project')
        documents = {key: item[1] for key, item in inputs.items()}
        segments = [segment.model_dump() for segment in args.paths]
        try:
            changed, output_catalog, report = edit_segmented(documents, run_infrastructure_paths(runblob),
                catalog, args.name, segments, args.action, args.description)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
            raise APIError('SHUNTING_ITINERARY_EDIT', str(error)[:500]) from error
        updated = {path_by_key[key].name: data for key, data in changed.items() if data != documents[key]}
        members = {**updated, catalog_path.name: output_catalog}
        dependencies = {runpath: runblob, catalog_path: catalog, **{item[0]: item[1] for item in inputs.values()}}
        manifest = {'format': 'opentrack-segmented-shunting-itinerary-v1',
            'files': {member: {'sha256': sha(data), 'bytes': len(data)} for member, data in members.items()},
            'sources': {str(file.relative_to(self.root)): {'sha256': sha(data)} for file, data in dependencies.items()},
            'replacement_for': {file.name: file.relative_to(self.root).as_posix() for file in (catalog_path, *path_by_key.values())
                                if file.name in members},
            'document_scope': evidence, 'complete_relocated_project': False}
        result = {'preview_only': args.preview_only, 'saved': False, 'manifest': manifest,
                  'bundle_type': 'Local Shuntings and cross-document Itinerary', 'change_report': report,
                  'fresh_archive_reload_verified': True, 'native_application_started': False}
        return self.publish_bundle(inputs=dependencies, members=members, manifest=manifest, result=result,
                                   target_directory=args.target_directory, scope_check=scope_check, windows_publication=True)


def _bound_course_ids(course_bytes, timetable_bytes, name, expected_courses):
    courses = writer.load_next_compatible(course_bytes)[0]
    bound = [catalogs.text(course.contents[0].value) for course in catalogs.course_items(courses)
             if name in {catalogs.text(item) for item in catalogs.array(course.contents[2].value)}]
    need(len(set(bound)) == len(bound) == len(expected_courses) and set(bound) == set(expected_courses),
         'Expected Course IDs must equal the actual unique Courses that select this Itinerary')
    rows = course_factories.timetable(writer.load_next_compatible(timetable_bytes)[0])
    need(set(bound) <= {catalogs.text(row.contents[1].value) for row in rows.values()},
         'Every affected Course requires its selected native timetable')
    return sorted(bound)


class BoundaryShuntingProjectTools(MultiDocumentTools):
    def rebind(self, args):
        state = self.load_project(args.source_project)
        target = project_target(self, args)
        require_external_target(target, state['base'])
        if target is not None and state['base'].is_relative_to(target):
            raise APIError('SHUNTING_ITINERARY_SCOPE', 'Publication target must also be disjoint from the source project')
        roles = state['roles']
        members = {name: state['files'][name] for name in state['selected']}
        run_name = args.source_project.run_file
        execution_root = state['root']
        boundaries = [args.boundary] if isinstance(args, RebindSingleBoundaryShunting) else args.boundaries
        try:
            bound = _bound_course_ids(members[roles['courses']], members[roles['timetable']], args.name,
                                      args.expected_bound_courses)
            changed, members[roles['dest']], report = edit_segmented(
                state['documents'], state['document_paths'], members[roles['dest']], args.name,
                [segment.model_dump() for segment in args.paths], 'replace_paths',
                boundaries=[boundary.model_dump() for boundary in boundaries])
            for document, data in changed.items():
                members[state['document_members'][document]] = data
            if target is not None:
                execution_root = target.as_posix()
                members, report['relocation'] = relocate_project(
                    members, source_root=state['root'], target_root=execution_root, run_file=run_name,
                    expected_hashes={name: sha(blob) for name, blob in members.items()},
                    project_type=EditableItineraryProject)

            def read_bound(absolute):
                need(absolute.startswith(execution_root + '/'), 'Unexpected member outside selected project')
                return members[absolute[len(execution_root) + 1:]]

            checked = preflight(members[run_name], read_bound)
            need(checked['passed_static_subset'], f'Native simulation preflight failed: {checked["errors"]}')
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
            raise APIError('SHUNTING_PROJECT_REBIND', str(error)[:800]) from error
        result = {'change_report': report, 'preview_only': args.preview_only, 'saved': False,
                  'execution_root': execution_root, 'changed_itinerary': args.name, 'bound_courses': bound,
                  'course_and_timetable_bytes_preserved': True, 'static_simulation_preflight': True,
                  'native_execution': False, 'source': self.source_receipt(args, state),
                  'files': {name: {'bytes': len(data), 'sha256': sha(data)} for name, data in members.items()}}
        if args.preview_only:
            self.recheck(state)
            return result
        return publish_candidate(self, target, members, result, lambda: self.recheck(state))


def tool_definitions(root):
    return [('opentrack_edit_segmented_shunting_itinerary',
             'Save a cross-document native Itinerary made of ordinary Paths and distinct local Shunting Paths. '
             'Optionally create local Shuntings or the Path for a continued ordinary Route, and publish '
             'all changed worksheets and .dest together. Use original_first_save when creating a local Shunting '
             'to match the original first-save End ID counter.',
             EditSegmentedShunting, SegmentedShuntingTools(root).edit, False, False),
            ('opentrack_rebind_single_boundary_shunting_project',
             'Rebind a named in-use Itinerary to local native Shunting Paths and an ordinary Path over one exact '
             'directed worksheet connector pair. Keep the original directed walk and bound Course/Timetable bytes, '
             'and save a statically checked complete native project to a fresh directory.',
             RebindSingleBoundaryShunting, BoundaryShuntingProjectTools(root).rebind, False, False),
            ('opentrack_rebind_multi_boundary_shunting_project',
             'Rebind a named in-use Itinerary across multiple explicitly ordered worksheet connector pairs, '
             'with native local Shunting between crossings. Preserve directed Ends, physical edges and the '
             'bound Course/Timetable, and save a statically checked complete native project to a fresh directory.',
             RebindMultiBoundaryShunting, BoundaryShuntingProjectTools(root).rebind, False, False)]
