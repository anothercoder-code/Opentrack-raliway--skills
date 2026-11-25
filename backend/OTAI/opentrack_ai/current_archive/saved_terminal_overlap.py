"""Bind and read terminal Overlap references of continued native Routes."""

from math import isfinite

from . import path_functions, writer
from .current_shunting_workflow.core import build_shunting_path
from .multi_document.core import need, ref
from .multi_document.operations import exclusive
from .path_lifecycle_tools import _guard_fresh_identity, _incident_bindings
from .route_edit_tools import _route_owner_counts
from .route_lifecycle_tools import _guard_incidents
from .saved_geometry import _movement_manifest, project_from
from .shunting_lifecycle_tools import _find, _owned_body


def overlap_reference(route):
    return path_functions.string(route.contents[7].value), route.contents[9].value


def set_overlap_reference(route, reference, *, changes=None, root=None):
    name, start_id = reference
    label = path_functions.fresh_string(route.contents[7].value, name)
    if changes is None:
        route.contents[7].value = label
        route.contents[9].value = start_id
    else:
        changes.group(root, route.contents[7], [label])
        changes.group(root, route.contents[9], [start_id])


def terminal_overlap(project, route, approved):
    movement = project.route_view(route)
    owner = project.owners[id(route)]
    terminal = movement[-1]
    selected = approved['shunting']
    need(route.contents[5].values[4] >= 0 and terminal[0] != owner[0]
         and terminal == (selected['document'], selected['start_id']),
         'An overlap must begin at the continued primary Route’s exact expanded terminal End')
    return _read_terminal_overlap(project, movement, approved)


def _read_terminal_overlap(project, movement, approved):
    terminal = movement[-1]
    selected = approved['shunting']
    need(terminal == (selected['document'], selected['start_id']),
         'The reviewed overlap must start at the expanded terminal End')
    path_reference = {key: value for key, value in selected.items() if key != 'document'}
    shunting = _find(project, terminal[0], path_reference)
    _, body, _ = _owned_body(project, shunting, path_reference, terminal[0])
    path, _ = project.path_view(shunting)
    edges = [project.edge_between(a, b)[1] for a, b in zip(path, path[1:])]
    need(edges == approved['edge_ids'] and not set(path).intersection(movement[:-1]),
         'Reviewed overlap Edges differ or re-enter the primary movement')
    need(body.clazz.superclass.version == 6 and body.contents[6].values == [0, 40.0, 0.0]
         and type(body.contents[5].values[2]) is int and 0 <= body.contents[5].values[2] <= 86400
         and type(body.contents[5].values[3]) is int and 0 <= body.contents[5].values[3] <= 86400
         and isfinite(body.contents[11].value) and 0 < body.contents[11].value <= 1000,
         'The terminal overlap has an unsupported protection profile')
    return {
        'shunting': selected, 'end_ids': [key[1] for key in path], 'edge_ids': edges,
        'safety_element_ids': [project.model((terminal[0], edge_id)).contents[7].value.contents[7].value.contents[0].value
                               for edge_id in edges],
        'release_time_s': body.contents[5].values[2], 'reservation_time_s': body.contents[5].values[3],
        'shunting_speed_kmh': body.contents[11].value,
    }


def split_terminal_overlap(project, route, approved, complete_movement):
    """Verify overlap identity and locking resources over both parts of a split movement."""
    movement = project.route_view(route)
    selected = approved['shunting']
    need(overlap_reference(route) in ((selected['name'], selected['start_id']), (selected['name'], -1)),
         'The saved terminal overlap reference does not match the reviewed Shunting')
    overlap = _read_terminal_overlap(project, movement, approved)
    terminal = complete_movement[-1]
    need(movement[-1] == terminal, 'The overlapping Route must retain the original expanded terminal End')
    need(not any(project.owners[id(other)] == terminal and other.contents[11].value & 1
                 for other in project.routes),
         'The terminal overlap must belong to the last Route in the synchronized reservation chain')
    path = [(terminal[0], number) for number in overlap['end_ids']]
    earlier_vertices = set(complete_movement[:-1])
    earlier_vertices.update(project.related(end) for end in complete_movement[:-1])
    need(not earlier_vertices.intersection(path[1:]) and project.related(terminal) not in path[1:],
         'The terminal overlap returns to a physical vertex already used by the whole original Route')

    edges = {project.edge_between(a, b) for a, b in zip(complete_movement, complete_movement[1:])}
    overlap_edges = {(terminal[0], number) for number in overlap['edge_ids']}
    movement_elements, movement_exclusions = _edge_locking_resources(project, edges)
    overlap_elements, overlap_exclusions = _edge_locking_resources(project, overlap_edges)
    need(not (edges & overlap_edges
              or (movement_elements | movement_exclusions) & (overlap_elements | overlap_exclusions)),
         'The terminal overlap and whole original Route share an Edge, Safety Element or Edge exclusion')
    return overlap


def _edge_locking_resources(project, keys):
    def element_keys(edge):
        return {project.key(edge.contents[slot].value.contents[7].value) for slot in (7, 8)}

    elements, exclusions = set(), set()
    for key in keys:
        edge = project.model(key)
        elements.update(element_keys(edge))
        for slot in (13, 14):
            linked = edge.contents[slot].value
            if linked is not None:
                exclusions.update(element_keys(linked))
    return elements, exclusions


def _create_overlap(project, route, catalog, specification, courses):
    movement = project.route_view(route)
    terminal = movement[-1]
    document = terminal[0]
    route_owner = project.owners[id(route)]
    keys = [(document, ordinal) for ordinal in specification['end_ids']]
    need(route.contents[5].values[4] >= 0 and document != route_owner[0] and specification['document'] == document
         and keys[0] == terminal
         and len(set(keys)) == len(keys) and not set(keys).intersection(movement[:-1]),
         'A new overlap must begin at the expanded terminal and never re-enter its Route')
    nodes = [project.model(key) for key in keys]
    need(all(writer.kind(node) == 'OTEndModel' for node in nodes), 'Create a local overlap along ordinary Ends')
    edges = [project.edge_between(a, b)[1] for a, b in zip(keys, keys[1:])]
    need(edges == specification['edge_ids'], 'The reviewed new overlap Edges do not match the current graph')
    name = specification['name']
    catalog_root, _ = writer.load_next_compatible(catalog)
    for root in (*project.roots.values(), catalog_root):
        for item in writer.objects(root):
            kind = writer.kind(item)
            if kind in ('OTPath', 'OTRoute', 'OTShunting', 'OTDest'):
                need(path_functions.string(item.contents[1].value).casefold() != name.casefold(),
                     'New overlap name would duplicate an existing movement name')
            if kind in ('OTArrayInfo', 'OTArrayExtInfo'):
                need(path_functions.string(item.contents[0].value).casefold() != name.casefold(),
                     'New overlap name would capture a saved reference')
            if kind == 'OTRoute':
                need(overlap_reference(item)[0].casefold() != name.casefold(),
                     'New overlap name would capture a saved overlap')
    owner = nodes[0]
    root = project.roots[document]
    path_functions.guard_counter_references(root, owner, allow_local_shunting=True)
    holder = owner.contents[16].value
    exclusive(root, holder)
    high = owner.contents[19].value + 1
    need(high <= 2147483647, 'Terminal End Path owner identity allocator exhausted')
    source = {key: value for key, value in specification.items() if key not in ('document', 'edge_ids')}
    shunting = build_shunting_path(nodes, high, {'description': '', **source})
    identity = {'document': document, **ref(shunting)}
    _guard_fresh_identity(project, catalog_root, identity)
    _incident_bindings(courses, project, identity)
    array = holder.contents[0].value
    writer.set_elements(array, [*path_functions.mutable_array(array), shunting])
    owner.contents[19].value = high
    return document, writer.dump_verified(root, project.versions[document]), {'shunting': identity, 'edge_ids': edges}


def bind_cross_document_terminal_overlap(documents, paths, catalog, target, operation, courses):
    need(courses is not None, 'The exact bound CourseList is required for overlap protection changes')
    project = project_from(documents, paths, catalog)
    before = _movement_manifest(project)
    reference = operation['route']
    identity = reference['name'], reference['array_id'], reference['start_id']
    owner = reference['document'], reference['start_id']
    need(owner[0] == target, 'Target document must be the primary Route’s document')
    _guard_incidents(courses, {(target.casefold(), identity[2], identity[1])}, {identity[0]})
    route = project.owned(owner, 'OTRoute', identity)
    need(overlap_reference(route) == ('', -1), 'The Route already has a stored overlap')
    approval = operation.get('overlap')
    new = operation.get('create_overlap')
    need((approval is None) != (new is None), 'Select one existing overlap or create one checked terminal path')
    changes = {}
    if new is not None:
        document, blob, approval = _create_overlap(project, route, catalog, new, courses)
        changes[document] = blob
        project = project_from({**documents, **changes}, paths, catalog)
        route = project.owned(owner, 'OTRoute', identity)
        movements = _movement_manifest(project)
        need(all(movements.get(key) == value for key, value in before.items()) and len(movements) == len(before) + 1,
             'A movement changed besides the new terminal overlap')
        before = movements
    selection = terminal_overlap(project, route, approval)
    record, = [item for item in project.continuations if item['source_document'] == target and item['route'] == ref(route)]
    companion = project.owned((record['target_document'], record['target_connector']), 'OTRoute', identity)
    need(overlap_reference(companion) == ('', -1), 'The original receiving fragment already has an overlap')
    _route_owner_counts(project, owner)
    anchor = selection['shunting']['name'], selection['shunting']['start_id']
    set_overlap_reference(route, anchor)
    changes[target] = writer.dump_verified(project.roots[target], project.versions[target])
    checked = project_from({**documents, **changes}, paths, catalog)
    saved = checked.owned(owner, 'OTRoute', identity)
    need(_movement_manifest(checked) == before and overlap_reference(saved) == anchor
         and terminal_overlap(checked, saved, approval) == selection,
         'The original overlap or another native movement changed after archive readback')
    return changes, {'action': operation['action'], 'route': reference, 'terminal_overlap': selection,
                     'stored_reference': anchor, 'created_overlap': new is not None, 'movement_bindings_preserved': True,
                     'changed_documents': sorted(changes), 'native_execution_tested': False}
