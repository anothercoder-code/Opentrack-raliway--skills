"""Edits to existing Route and Path records in current OpenTrack archives."""

from . import path_append, path_functions as paths, route_factory, writer as archive
from .graph_references import reference_inventory
from .multi_document.core import layout
from .signal_protection.core import boolean, intval, real


require = route_factory.require

# The native reservation-with-previous flag shares its integer with
# slowSpeedOnlyForHead. Editing one must preserve the other.
ROUTE_FIELDS = {
    'release_distance_m': (5, 0, intval),
    'announce_distance_m': (5, 1, intval),
    'release_time_s': (5, 2, intval),
    'reserve_time_s': (5, 3, intval),
    'approach_length_m': (8, 0, real),
    'approach_speed_kmh': (8, 1, real),
    'reservation_distance_m': (10, 0, intval),
    'use_reservation_distance': (10, 1, boolean),
    'use_release_distance': (10, 2, boolean),
    'reserve_previous': (11, 0, boolean),
}


def _owned(root, kind, ref):
    _, models = route_factory.document(root)
    obj = path_append.select(root, kind, ref)
    owner = models.get(ref['start_id'])
    route_factory.layout(owner, 'OTEndModel', 7, route_factory.END, graphic=True)
    slot, list_class = (15, 'OTRouteList') if kind == 'OTRoute' else (17, 'OTPathList')
    wrapper = owner.contents[slot].value
    rows = route_factory.wrapper(wrapper, list_class)
    objects, incoming = reference_inventory(root)
    require(incoming[id(root)] == 0 and incoming[id(wrapper)] == 1
            and incoming[id(wrapper.contents[0].value)] == 1, 'Shared root or owner list')
    require(sum(row is obj for row in rows) == 1, 'Movement must belong to its declared owner')
    for row in rows:
        paths.shape(row, kind)
    require(sum(row.contents[2].values == obj.contents[2].values for row in rows) == 1
            and sum(paths.string(row.contents[1].value) == ref['name'] for row in rows) == 1,
            'Ambiguous movement identity at its owning End')
    for other in objects:
        if archive.kind(other) == list_class and other is not wrapper:
            require(obj not in route_factory.wrapper(other, list_class), 'Movement belongs to multiple owners')
    return obj, wrapper, incoming


def _local_nodes(route, models, by_id):
    nodes = path_append.route_nodes(route, models)
    require(len({id(end) for end in nodes}) == len(nodes), 'Repeated End in the local Route')
    for first, second in zip(nodes, nodes[1:]):
        paired = by_id.get(first.contents[8].value)
        route_factory.layout(paired, 'OTEndModel', 7, route_factory.END, graphic=True)
        require(paired is not first and paired.contents[8].value == first.contents[0].value,
                'Related End pair is not reciprocal')
        edges = set()
        for edge in (paired.contents[9].value, paired.contents[10].value):
            if edge is None:
                continue
            route_factory.layout(edge, 'OTEdgeModel', 3, route_factory.EDGE, graphic=True)
            a, b = edge.contents[7].value, edge.contents[8].value
            require(by_id.get(edge.contents[0].value) is edge and (a is paired or b is paired),
                    'Edge is outside the document or breaks its reverse reference')
            if (a is paired and b is second) or (a is second and b is paired):
                require(edge in (second.contents[9].value, second.contents[10].value)
                        and edge.contents[9].values[1] > 0, 'Edge is absent at the next End or has no length')
                edges.add(id(edge))
        require(len(edges) == 1, 'Missing or ambiguous directed Edge between consecutive Ends')
    return nodes


def _route_values(obj, fields):
    result = {}
    for field in fields:
        if field == 'description':
            result[field] = paths.string(obj.contents[3].value)
        elif field == 'release_groups':
            result[field] = [end.contents[0].value for end in paths.mutable_array(obj.contents[12].values[0])]
        else:
            group, slot, normalize = ROUTE_FIELDS[field]
            value = obj.contents[group].values[slot]
            if field == 'reserve_previous':
                require(value in (0, 1, 2, 3), 'Unexpected Route reservation/head-only flags')
                value = bool(value & 1)
            elif normalize is boolean:
                require(value in (0, 1), 'Unexpected persisted Route boolean')
                value = bool(value)
            result[field] = value
    return result


def _verify_inverse(data, root, version, obj, snapshots):
    for group, values in snapshots.items():
        obj.contents[group].values[:] = values
    original, original_version = archive.load_next_compatible(data)
    require(archive.dump_verified(root, version) == archive.dump_verified(original, original_version),
            'Unexpected changes outside the selected movement fields')


def edit_route(data, ref, changes):
    require(type(changes) is dict and changes and changes.keys() <= ROUTE_FIELDS.keys() | {'description', 'release_groups'},
            'At least one supported Route field is required')
    root, version = archive.load_next_compatible(data)
    route, _, incoming = _owned(root, 'OTRoute', ref)
    before = _route_values(route, changes)
    snapshots = {}
    expected = {}
    for field, value in changes.items():
        if field == 'description':
            group, slot = 3, 0
            replacement = paths.fresh_string(route.contents[3].value, value)
        elif field == 'release_groups':
            require(value in ('global', 'each_end'), 'Release groups must be global or each_end')
            group, slot = 12, 0
            current = route.contents[group].values[slot]
            require(incoming[id(current)] == 1, 'Release-group array is shared')
            end_ids = [end.contents[0].value for end in paths.mutable_array(route.contents[0].value)]
            _, nodes, _, _, _ = route_factory.validate_chain(root, route, end_ids)
            selected = [nodes[0], nodes[-1]] if value == 'global' else nodes
            replacement = paths.array_like(current, selected)
            value = [end.contents[0].value for end in selected]
        else:
            group, slot, normalize = ROUTE_FIELDS[field]
            value = normalize(value)
            replacement = int(value) if normalize is boolean else value
            if field == 'reserve_previous':
                replacement |= route.contents[group].values[slot] & ~1
        snapshots.setdefault(group, list(route.contents[group].values))
        route.contents[group].values[slot] = replacement
        expected[field] = value
    if 'approach_length_m' in changes or 'approach_speed_kmh' in changes:
        length, speed = (real(float(value)) for value in route.contents[8].values)
        require((length == 0) == (speed == 0), 'Approach length and speed must both be positive or both zero')
    output = archive.dump_verified(root, version)
    fresh, _ = archive.load_next_compatible(output)
    saved, _, _ = _owned(fresh, 'OTRoute', ref)
    after = _route_values(saved, changes)
    require(after == expected, 'Route field readback mismatch')
    _verify_inverse(data, root, version, route, snapshots)
    return output, {'operation': 'edit_route', 'identity': ref, 'before': before, 'after': after,
                    'native_runtime_verified': False}


APPROACH_FIELDS = ('approach_length_m', 'approach_speed_kmh')


def approach_batch(data, references, changes, sort_by):
    """Apply one original Inspector approach edit to selected saved Routes."""
    from .route_edit_tools import _indications

    require(references and len(references) <= 256, 'Select 1 to 256 distinct Routes')
    require(changes.keys() <= set(APPROACH_FIELDS), 'Only Route approach fields are supported')
    require(sort_by in ('selection', 'description', 'number_of_signal_aspects'), 'Invalid Route sort order')
    identities = {(ref['start_id'], ref['array_id']) for ref in references}
    require(len(identities) == len(references), 'Duplicate Route selection')
    normalized = {field: real(value) for field, value in changes.items()}
    root, version = archive.load_next_compatible(data)
    original = archive.fingerprint(root)
    selected = []
    results = []
    for ref in references:
        route, _, _ = _owned(root, 'OTRoute', ref)
        before = _route_values(route, APPROACH_FIELDS)
        after = {**before, **normalized}
        description = archive.string(route.contents[3].value) or ''
        aspect_count = len(_indications(route)[1]) if route.contents[4].value is not None else 0
        selected.append((ref, route, before, after))
        results.append({'identity': ref, 'description': description, 'number_of_signal_aspects': aspect_count,
                        'before': before, 'after': after, 'has_approach_zone': after['approach_length_m'] > 0})
    output = data
    changed_routes = sum(before != after for _, _, before, after in selected)
    if changed_routes:
        try:
            for _, route, _, after in selected:
                route.contents[8].values[:] = [after[field] for field in APPROACH_FIELDS]
            output = archive.dump_verified(root, version)
            fresh, _ = archive.load_next_compatible(output)
            for ref, _, _, after in selected:
                route, _, _ = _owned(fresh, 'OTRoute', ref)
                require(_route_values(route, APPROACH_FIELDS) == after, 'Approach batch failed exact archive readback')
        finally:
            for _, route, before, _ in selected:
                route.contents[8].values[:] = [before[field] for field in APPROACH_FIELDS]
        require(archive.fingerprint(root) == original, 'Approach batch changed other native Route fields or references')

    def identity_key(item):
        ref = item['identity']
        return (ref['name'], ref['start_id'], ref['array_id'])

    if sort_by == 'description':
        results.sort(key=lambda item: (item['description'], *identity_key(item)))
    elif sort_by == 'number_of_signal_aspects':
        results.sort(key=lambda item: (-item['number_of_signal_aspects'], *identity_key(item)))
    return output, {'operation': 'edit_route_approach_batch', 'sort_by': sort_by, 'routes': results,
                    'changed_route_count': changed_routes, 'native_runtime_verified': False}


def edit_path_description(data, ref, description):
    root, _ = archive.load_next_compatible(data)
    _owned(root, 'OTPath', ref)
    return paths.set_description(data, 'OTPath', ref['name'], description, ref['array_id'], ref['start_id'])


def _path_references(root, documents, target_document, ref):
    known_documents = {name.casefold() for name in documents}
    for info in archive.objects(root):
        if archive.kind(info) != 'OTArrayExtInfo':
            continue
        layout(info, [('OTArrayExtInfo', 0), ('OTArrayInfo', 0), ('NSObject', 0)], ['@', 'ii', '@'])
        label = paths.string(info.contents[2].value).casefold()
        require(label in known_documents, 'Unresolved native document label in Path dependency')
        array_id, start_id = info.contents[1].values
        if (label == target_document.casefold() and start_id == ref['start_id']
                and (array_id == ref['array_id'] or paths.string(info.contents[0].value) == ref['name'])):
            yield info


def _has_path_dependents(roots, dest_catalog, target_document, path, ref, incoming):
    catalog, _ = archive.load_next_compatible(dest_catalog)
    for row in route_factory.wrapper(catalog, 'OTDestInfoList'):
        layout(row, [('OTDestInfo', 1), ('NSObject', 0)], ['i', '@', '@', 'i', '@'])
    has_external_reference = False
    for root in (*roots.values(), catalog):
        for _ in _path_references(root, roots, target_document, ref):
            has_external_reference = True
    return incoming[id(path)] != 1 or has_external_reference


def _movement_project(documents, document_paths, dest_catalog, *, allow_external_destinations=False):
    from .itinerary_edit_tools import EditableItineraryProject
    from .tools import sha

    require(document_paths is not None, 'Referenced or cross-document Path requires exact run document paths and DestInfo catalog')
    project = EditableItineraryProject(
        documents, document_paths=document_paths,
        expected_hashes={name: sha(blob) for name, blob in documents.items()},
        complete_document_set=True,
    )
    project.check_dest_catalog(dest_catalog, allow_external=allow_external_destinations)
    return project


def _linked_itineraries(project, dest_catalog, target_document, target, ref):
    external_refs = {
        name: {id(info) for info in _path_references(root, project.roots, target_document, ref)}
        for name, root in project.roots.items()
    }
    incoming = {name: reference_inventory(root)[1] for name, root in project.roots.items()
                if name == target_document or external_refs[name]}
    allowed_references = {name: set() for name in project.roots}
    permitted_path_edges = 1  # Ordinary PathList ownership.
    dependents = set()
    identity = {'document': target_document, **ref}
    for dest in project.dests:
        if identity not in paths.info(dest)['saved_references']:
            continue
        name = paths.string(dest.contents[1].value)
        document, _ = project.owners[id(dest)]
        document_incoming = incoming[document]
        first = dest.contents[0].value
        references = dest.contents[4].value
        require(document_incoming[id(dest)] == 1 and document_incoming[id(first)] == 1
                and document_incoming[id(references)] == 1,
                'Dependent Itinerary definition or Path arrays are shared')
        if paths.mutable_array(first)[0] is target:
            permitted_path_edges += 1
        for info in paths.mutable_array(references):
            if id(info) in external_refs[document]:
                require(document_incoming[id(info)] == 1, 'Dependent Itinerary reference info is shared')
                allowed_references[document].add(id(info))
        dependents.add(name)
    require(incoming[target_document][id(target)] == permitted_path_edges, 'Unrecognised incoming Path references')
    require(external_refs == allowed_references, 'Unrecognised saved external Path reference')
    catalog, _ = archive.load_next_compatible(dest_catalog)
    catalog_counts = reference_inventory(catalog)[1]
    catalog_refs = {id(info) for info in _path_references(catalog, project.roots, target_document, ref)}
    known_catalog_refs = set()
    for row in route_factory.wrapper(catalog, 'OTDestInfoList'):
        if paths.string(row.contents[1].value) not in dependents:
            continue
        refs = row.contents[4].value
        require(catalog_counts[id(row)] == 1 and catalog_counts[id(refs)] == 1,
                'Dependent DestInfo definition or Path reference array is shared')
        for info in paths.mutable_array(refs):
            if id(info) in catalog_refs:
                require(catalog_counts[id(info)] == 1, 'Dependent DestInfo Path reference info is shared')
                known_catalog_refs.add(id(info))
    require(known_catalog_refs == catalog_refs, 'Unrecognised saved DestInfo Path reference')
    return dependents


def verify_itinerary_movements(before_project, after_project):
    """Verify an infrastructure edit leaves Itinerary references and stops valid."""
    def inventory(project):
        return {paths.string(dest.contents[1].value): dest for dest in project.dests}

    before = inventory(before_project)
    after = inventory(after_project)
    require(before.keys() == after.keys(), 'Itinerary identities changed during movement edit')
    changed = []
    for name, dest in before.items():
        saved = after[name]
        old_movement, old_paths = before_project.dest_view(dest)
        new_movement, new_paths = after_project.dest_view(saved)
        require(old_paths == new_paths and before_project.owners[id(dest)] == after_project.owners[id(saved)],
                'Movement edit changes saved Itinerary Path references or owner')
        if old_movement == new_movement:
            continue
        require(old_movement[0] == new_movement[0] and old_movement[-1] == new_movement[-1],
                'Movement edit changes an Itinerary directional endpoint')
        old_stations = [end for end in old_movement if before_project.model(end).contents[12].value is not None]
        new_stations = [end for end in new_movement if after_project.model(end).contents[12].value is not None]
        require(old_stations == new_stations, 'Movement edit changes an Itinerary ordered Station references')
        require(not route_factory.wrapper(dest.contents[5].value, 'OTSafetyMarginArray'),
                'Movement edit changes an Itinerary with distance-based safety margins')
        changed.append(name)
    return sorted(changed)


def _expanded_route_chain(project, owner, routes):
    selected, movement = [], [owner]
    for value in routes:
        ref = path_append.exact_ref({k: v for k, v in value.items() if k != 'document'})
        document = value.get('document', movement[-1][0])
        key = (document, ref['start_id'])
        require(key == movement[-1], 'Disconnected Route sequence at the exact directional End')
        route = project.owned(key, 'OTRoute', (ref['name'], ref['array_id'], ref['start_id']))
        nodes = project.route_view(route)
        require(nodes[0] == key, 'Continuation fragment cannot be used as a Route source')
        selected.append((document, route))
        movement.extend(nodes[1:])
        require(len(movement) <= path_append.MAX_ROUTES, 'Expanded Path exceeds supported directional-End limit')
    require(len(set(movement)) == len(movement), 'Repeated or cyclic directional Ends in the Path')
    return selected, movement


def _replace_path_fields(path, chain, description, incoming):
    first, infos = path.contents[0].value, path.contents[4].value
    require(incoming[id(first)] == 1 and incoming[id(infos)] == 1, 'Shared Path Route arrays')
    template = paths.mutable_array(infos)[0]
    rebuilt = []
    for route in chain:
        info = paths.clone(template)
        info.contents[0].value = route.contents[1].value
        info.contents[1].values[:] = route.contents[2].values
        rebuilt.append(info)
    snapshots = {index: list(path.contents[index].values) for index in (0, 3, 4)}
    path.contents[0].value = paths.array_like(first, [chain[0]])
    path.contents[4].value = paths.array_like(infos, rebuilt)
    if description is not None:
        path.contents[3].value = paths.fresh_string(path.contents[3].value, description)
    return snapshots


def _replace_expanded_path(documents, document_paths, target_document, dest_catalog, ref, routes, description):
    project = _movement_project(documents, document_paths, dest_catalog)
    root, version = project.roots[target_document], project.versions[target_document]
    path, _, incoming = _owned(root, 'OTPath', ref)
    owner = project.owners[id(path)]
    old_movement, old_routes = project.path_view(path)
    before = paths.info(path)
    dependents = _linked_itineraries(project, dest_catalog, target_document, path, ref)
    selected, movement = _expanded_route_chain(project, owner, routes)
    new_routes = [(document, path_append.identity(route)) for document, route in selected]
    if dependents:
        require(old_movement[-1] == movement[-1], 'Referenced Path must preserve the final directional End')

    snapshots = _replace_path_fields(path, [route for _, route in selected], description, incoming)
    output = archive.dump_verified(root, version)
    checked = _movement_project({**documents, target_document: output}, document_paths, dest_catalog)
    saved = checked.owned(owner, 'OTPath', (ref['name'], ref['array_id'], ref['start_id']))
    saved_movement, saved_routes = checked.path_view(saved)
    after = paths.info(saved)
    expected = {**before, 'saved_references': [identity for _, identity in new_routes],
                'description': before['description'] if description is None else description}
    require(after == expected and saved_movement == movement and saved_routes == new_routes,
            'Path Route chain or description readback mismatch')
    updated_dependents = _linked_itineraries(checked, dest_catalog, target_document, saved, ref)
    require(updated_dependents == dependents, 'Dependent Itinerary set changed during Path edit')
    changed_itineraries = verify_itinerary_movements(project, checked)
    require(set(changed_itineraries) <= dependents, 'Unrelated Itinerary movement changed during Path edit')
    _verify_inverse(documents[target_document], root, version, path, snapshots)
    return output, {
        'operation': 'edit_path_routes', 'before': before, 'after': after,
        'before_end_ids': [end for _, end in old_movement], 'after_end_ids': [end for _, end in movement],
        'before_directional_ends': old_movement, 'after_directional_ends': movement,
        'before_route_documents': [document for document, _ in old_routes],
        'after_route_documents': [document for document, _ in saved_routes],
        'dependent_itineraries': sorted(dependents), 'rerouted_itineraries': changed_itineraries,
        'dest_catalog_unchanged': True,
        'dest_catalog_bindings_verified': True, 'running_time_revalidation_required': old_routes != saved_routes,
        'native_runtime_verified': False,
    }


def _checked_chain(root, chain, models, by_id):
    ends = path_append.check_chain(chain, models)
    objects, incoming = reference_inventory(root)
    owners = {}
    for route in chain:
        nodes = _local_nodes(route, models, by_id)
        wrapper = nodes[0].contents[15].value
        require(incoming[id(wrapper)] == 1 and incoming[id(wrapper.contents[0].value)] == 1,
                'Route owner list is shared')
        owners[id(route)] = wrapper
    seen = set()
    for wrapper in objects:
        if archive.kind(wrapper) != 'OTRouteList':
            continue
        for route in route_factory.wrapper(wrapper, 'OTRouteList'):
            identity = id(route)
            if identity in owners:
                require(owners[identity] is wrapper and identity not in seen, 'Route belongs to multiple owners')
                seen.add(identity)
    return ends


def edit_path_routes(documents, target_document, dest_catalog, ref, routes, description=None, *, document_paths=None):
    """Replace saved ordered Route infos and the single persisted first Route."""
    require(type(routes) is list and 1 <= len(routes) <= path_append.MAX_ROUTES
            and all(type(item) is dict for item in routes), 'Explicit Route sequence required')
    sources = {name: archive.load_next_compatible(blob) for name, blob in documents.items()}
    roots = {name: definition[0] for name, definition in sources.items()}
    for document in roots.values():
        route_factory.document(document)
    root, version = sources[target_document]
    path, _, incoming = _owned(root, 'OTPath', ref)
    models, by_id = route_factory.document(root)
    dependent = _has_path_dependents(roots, dest_catalog, target_document, path, ref, incoming)
    qualified = any(isinstance(item, dict) and 'document' in item for item in routes)
    if dependent or qualified:
        return _replace_expanded_path(documents, document_paths, target_document, dest_catalog, ref, routes, description)
    try:
        old_chain = path_append.resolve_path(root, path, models)
    except paths.Unsupported:
        if document_paths is None:
            raise
        return _replace_expanded_path(documents, document_paths, target_document, dest_catalog, ref, routes, description)
    old_ends = _checked_chain(root, old_chain, models, by_id)
    chain = [path_append.select(root, 'OTRoute', item) for item in routes]
    ends = _checked_chain(root, chain, models, by_id)
    require(ends[0] is old_ends[0], 'Replacement starts at a different End; Path owner cannot change')
    before = paths.info(path)
    snapshots = _replace_path_fields(path, chain, description, incoming)
    expected_description = before['description'] if description is None else description
    output = archive.dump_verified(root, version)
    fresh, _ = archive.load_next_compatible(output)
    saved, _, _ = _owned(fresh, 'OTPath', ref)
    fresh_models, fresh_ids = route_factory.document(fresh)
    fresh_chain = path_append.resolve_path(fresh, saved, fresh_models)
    fresh_ends = _checked_chain(fresh, fresh_chain, fresh_models, fresh_ids)
    after = paths.info(saved)
    before_end_ids = [end.contents[0].value for end in old_ends]
    end_ids = [end.contents[0].value for end in ends]
    require([path_append.identity(route) for route in fresh_chain] == routes
            and after['description'] == expected_description
            and [end.contents[0].value for end in fresh_ends] == end_ids,
            'Path Route chain or description readback mismatch')
    _verify_inverse(documents[target_document], root, version, path, snapshots)
    return output, {'operation': 'edit_path_routes', 'before': before, 'after': after,
                    'before_end_ids': before_end_ids, 'after_end_ids': end_ids,
                    'dependent_itineraries': [], 'dest_catalog_unchanged': True,
                    'running_time_revalidation_required': chain != old_chain,
                    'native_runtime_verified': False}
