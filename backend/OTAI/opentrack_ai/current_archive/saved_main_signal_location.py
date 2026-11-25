"""Rebind an adjacent native main-signal move and every known movement reference."""

from . import catalogs, path_functions as paths, route_factory, writer
from .graphic_alignment import signal_alignment_for_end
from .graph_references import incoming_counts
from .incident_operations import SCHEMA as INCIDENT_LAYOUT
from .multi_document.core import ident, need, ref
from .path_lifecycle_tools import Changes
from .route_discovery_tools import main_signal
from .route_edit_tools import _route_shape
from .saved_geometry import _movement_geometry, _movement_manifest, model_id, position, project_from
from .saved_station_areas import end_pair, station_model
from .zero_generation.topology import flt


def _select(project, document, request):
    old_key = document, request['from_end_id']
    new_key = document, request['to_end_id']
    need(old_key != new_key, 'Select a different directional End for the signal')
    old, new = project.model(old_key), project.model(new_key)
    old_pair, new_pair = (project.model(project.related(key)) for key in (old_key, new_key))
    need(all(writer.kind(end) == 'OTEndModel' for end in (old, new, old_pair, new_pair)),
         'The original adjacent move cannot cross a Connector')
    need(main_signal(old) and new.contents[11].value is None, 'Select a main signal and a free destination End')
    signal = old.contents[11].value
    alignment = tuple(signal.contents[slot].value for slot in (4, 5))
    need(model_id(signal) == request['signal_id']
         and signal_alignment_for_end(old) == alignment == signal_alignment_for_end(new),
         'The reviewed main signal and target direction must match the saved drawing')
    forward = request['direction'] == 'forward'
    depart, arrive = (old_pair, new) if forward else (new_pair, old)
    need(all(end.contents[9].value is not None and end.contents[10].value is None for end in (depart, arrive)),
         'The original adjacent move cannot cross a switch or an unconnected End')
    edge = depart.contents[9].value
    need(edge is arrive.contents[9].value and model_id(edge) == request['expected_edge_id'],
         'The destination is not the next reviewed End in this direction')
    need(old.contents[12].value is new.contents[12].value,
         'The signal cannot change station membership without a station-approach review')
    need(not route_factory.wrapper(old.contents[16].value, 'OTShuntingList'),
         'The original signal owner also owns a Shunting or Overlap')
    need(not any(route_factory.wrapper(new.contents[i].value, label)
                 for i, label in ((15, 'OTRouteList'), (16, 'OTShuntingList'), (17, 'OTPathList'))),
         'The destination End already owns a saved movement')
    return old_key, new_key, signal, edge


def _shift(sequence, old, new, forward, *, keep_closed_reference=False):
    nodes = list(sequence)
    starts_at_signal, ends_at_signal = nodes[0] == old, nodes[-1] == old
    if starts_at_signal:
        if forward:
            need(len(nodes) >= 2 and nodes[1] == new, 'Outgoing movement does not use the reviewed adjacent edge')
            nodes.pop(0)
        else:
            nodes.insert(0, new)
    if ends_at_signal and (not starts_at_signal or keep_closed_reference):
        if forward:
            nodes.append(new)
        else:
            need(len(nodes) >= 2 and nodes[-2] == new, 'Incoming movement does not use the reviewed adjacent edge')
            nodes.pop()
    need(len(nodes) >= 2, 'Moving the signal would collapse a saved movement')
    return nodes


def _move_owners(project, old_key, new_key, changes, counts):
    old, new = project.model(old_key), project.model(new_key)
    root = project.roots[old_key[0]]
    for slot in (15, 17):
        first, second = (end.contents[slot].value for end in (old, new))
        old_list, new_list = first.contents[0].value, second.contents[0].value
        need(all(counts[id(item)] == 1 for item in (first, second, old_list, new_list)),
             'Shared native Route or Path ownership lists')
        changes.group(root, first.contents[0], [paths.array_like(old_list, [])])
        changes.group(root, second.contents[0], [paths.array_like(new_list, paths.mutable_array(old_list))])
    changes.group(root, new.contents[19], [max(old.contents[19].value, new.contents[19].value)])
    changes.group(root, old.contents[19], [-1])


def _move_graphic(project, old_key, new_key, signal, changes, counts):
    root = project.roots[old_key[0]]
    old, new = (project.model(key) for key in (old_key, new_key))
    holder = signal.contents[10].value
    indications = route_factory.wrapper(holder, 'OTSigIndList')
    need(counts[id(holder)] == counts[id(holder.contents[0].value)] == 1,
         'Selected main signal shares its saved indication list')
    for indication in indications:
        need(counts[id(indication)] == 1 and indication.contents[1].value is old,
             'Unexpected native indication ownership on the relocated signal')
        changes.group(root, indication.contents[1], [new])
    changes.group(root, old.contents[11], [None])
    changes.group(root, new.contents[11], [signal])
    changes.group(root, signal.contents[7], [new])
    previous = position(signal)
    after = [flt(value + new_pos - old_pos, 'Translated main signal coordinate')
             for value, new_pos, old_pos in zip(previous, position(new), position(old), strict=True)]
    for slot, value in zip((2, 3), after, strict=True):
        changes.group(root, signal.contents[slot], [value])
    return previous, after


def _route_chunks(project, route, keys):
    count = route.contents[5].values[4]
    if count == -1:
        return [(route, keys[0][0], keys)]
    crossing = next(item for item in project.continuations
                    if item['source_document'] == keys[0][0] and item['route'] == ref(route))
    target = crossing['target_document']
    tail = project.owned((target, crossing['target_connector']), 'OTRoute', ident(route))
    boundary = next(i for i, key in enumerate(keys) if key[0] == target)
    return [(route, keys[0][0], keys[:boundary]), (tail, target, keys[boundary:])]


def _rewrite_route(project, route, nodes, old, new, changes, counts):
    parts = _route_chunks(project, route, nodes)
    for item, document, keys in parts:
        root = project.roots[document]
        previous = item.contents[0].value
        saved = paths.mutable_array(previous)
        selected = [project.model(key) for key in keys]
        if selected == saved:
            continue
        protection = item.contents[_route_shape(item) + 1]
        releases, *zone = protection.values
        need(counts[document][id(previous)] == counts[document][id(releases)] == 1,
             'A changed Route uses a shared movement or release list')
        old_end, new_end = project.model(old), project.model(new)
        anchored = list(dict.fromkeys(new_end if end is old_end else end
                                      for end in paths.mutable_array(releases)))
        need(all(end in selected for end in anchored)
             and sorted(anchored, key=selected.index) == anchored,
             'Relocation would invalidate an original Route release boundary')
        need(all(end is None or end in selected for end in zone),
             'Relocation would remove an explicit slow-speed zone endpoint')
        changes.group(root, item.contents[0], [paths.array_like(previous, selected)])
        changes.group(root, protection, [paths.array_like(releases, anchored), *zone])
        if item.contents[5].values[4] != -1:
            values = list(item.contents[5].values)
            values[4] = len(selected)
            changes.group(root, item.contents[5], values)
    return parts


def _reference_key(document, value):
    return document, value['name'], value['array_id'], value['start_id']


def _update_references(root, rows, resolved, changes, counts, old, new, identities):
    need(len(rows) == len(resolved), 'Saved reference list differs from the reconstructed movement')
    for row, (document, item) in zip(rows, resolved, strict=True):
        if _reference_key(document, item) in identities:
            need(counts[id(row)] == 1 and row.contents[1].values == [item['array_id'], old[1]],
                 'Shared or mismatched saved movement reference')
            changes.group(root, row.contents[1], [item['array_id'], new[1]])


def _guard_incident_bindings(courses, old, route_keys, path_keys, names):
    if courses is None:
        return
    root, _ = writer.load_next_compatible(courses)
    catalogs.course_items(root)
    for incident in catalogs.array(root.contents[1].value):
        catalogs.shape(incident, 'OTIncident', 12, INCIDENT_LAYOUT)
        array_id, start_id, kind = incident.contents[5].values
        document = catalogs.text(incident.contents[2].value).casefold()
        if document == old[0].casefold() and start_id == old[1]:
            need(not (kind == 4 and array_id in route_keys or kind == 5 and array_id in path_keys),
                 'Move the saved Route- or Path-speed Incident together with its original movement')
        if kind == 13:
            targets = {paths.string(incident.contents[i].value) for i in (10, 11)
                       if incident.contents[i].value is not None}
            need(targets.isdisjoint(names), 'An incident shares the extent of a changed Route')


def _guard_movement_bindings(roots, records, moved, new):
    known = {id(row) for item in records for row in paths.mutable_array(item.contents[4].value)}
    identities = {(name, array, end) for _, name, array, old_end in moved for end in (old_end, new[1])}
    for root in roots.values():
        for item in writer.objects(root):
            kind = writer.kind(item)
            need(kind not in ('OTRouteExclusionCondition', 'OTRouteRuleSet'),
                 'Saved Route rule objects need an explicit rule-aware relocation')
            if kind in ('OTArrayInfo', 'OTArrayExtInfo') and id(item) not in known:
                key = paths.string(item.contents[0].value), *item.contents[1].values
                need(key not in identities, 'An unaudited archive reference observes the selected Route or Path')


def _station_ends(project, keys):
    return [key for key in keys if project.model(key).contents[20].value == 2]


def _station_reference_pairs(project, document, station_id, old, new):
    need(writer.kind(project.model((document, station_id))) == 'OTStationModel', 'Select an exact saved OTStationModel identity')
    station = station_model(project, document, station_id)
    first, second = (end_pair(project, document, project.model(key)) for key in (old, new))
    need(all(item.contents[12].value is station and item.contents[20].value == kind and item.contents[10].value is None
             for pair, kind in ((first, 2), (second, 1)) for item in pair),
         'Select adjacent nonbranching reference and ordinary End pairs in the reviewed StationModel')
    return {project.key(previous): project.key(replacement) for previous, replacement in zip(first, second, strict=True)}


def _review_station_sequence(project, original, revised, station_ends):
    source = _station_ends(project, original)
    if not station_ends:
        need(_station_ends(project, revised) == source,
             'An Itinerary would gain or lose a station reference; review the operating plan')
        return
    targets = set(station_ends.values())
    saved = [key for key in revised
             if key in targets or (key not in station_ends and project.model(key).contents[20].value == 2)]
    need(saved == [station_ends.get(key, key) for key in source],
         'The joint signal and station move changes an unrelated Itinerary Station occurrence')
    for former, replacement in ((original[0], revised[0]), (original[-1], revised[-1])):
        need(replacement == station_ends.get(former, former),
             'The joint signal and station move requires each affected Itinerary endpoint to move to its exact related End')


def relocate_main_signal(documents, document_paths, dest_blob, document, request, courses):
    return _relocate_main_signal(documents, document_paths, dest_blob, document, request, courses)


def relocate_station_main_signal(documents, document_paths, dest_blob, document, request, courses, *, station_id):
    """Move an adjacent signal, paired reference and saved movements in one private geometry transaction."""
    need(type(station_id) is int and station_id >= 0, 'Select an exact saved StationModel identity')
    return _relocate_main_signal(documents, document_paths, dest_blob, document, request, courses, station_id=station_id)


def _relocate_main_signal(documents, document_paths, dest_blob, document, request, courses, *, station_id=None):
    project = project_from(documents, document_paths, dest_blob)
    catalog, catalog_version = writer.load_next_compatible(dest_blob)
    roots = {**project.roots, '$dest_catalog': catalog}
    counts = {name: incoming_counts(root) for name, root in roots.items()}
    fingerprints = {name: writer.fingerprint(root) for name, root in roots.items()}
    old, new, signal, edge = _select(project, document, request)
    station_ends = {} if station_id is None else _station_reference_pairs(project, document, station_id, old, new)
    forward = request['direction'] == 'forward'
    before = _movement_manifest(project)
    changes = Changes()
    expected = {}
    moved_routes, moved_paths = set(), set()
    affected_names = set()
    moved, itinerary_endpoints = [], []
    for route in project.routes:
        owner = project.owners[id(route)]
        if writer.kind(project.model(owner)) != 'OTEndModel':
            continue
        nodes = project.route_view(route)
        if old not in (nodes[0], nodes[-1]):
            continue
        next_nodes = _shift(nodes, old, new, forward, keep_closed_reference=bool(station_ends))
        parts = _rewrite_route(project, route, next_nodes, old, new, changes, counts)
        if owner == old:
            moved_routes.add((document, *ident(route)))
            for item, sheet, _ in parts:
                changes.group(roots[sheet], item.contents[2], [ident(item)[1], new[1]])
        name = ident(route)[0]
        affected_names.add(name)
        moved.append({'route': name, 'old_end_keys': nodes, 'new_end_keys': next_nodes})

    for path in project.paths_objects:
        owner = project.owners[id(path)]
        refs = project.path_views[id(path)][1]
        _update_references(roots[owner[0]], paths.mutable_array(path.contents[4].value),
                           refs, changes, counts[owner[0]], old, new, moved_routes)
        if owner == old:
            moved_paths.add((document, *ident(path)))
            changes.group(roots[document], path.contents[2], [ident(path)[1], new[1]])

    dest_counts = counts['$dest_catalog']
    catalog_rows = {paths.string(row.contents[1].value): row
                    for row in route_factory.wrapper(catalog, 'OTDestInfoList')}
    _guard_movement_bindings(roots, [*project.paths_objects, *project.dests, *catalog_rows.values()],
                             moved_routes | moved_paths, new)
    itineraries = {ident(dest): dest for dest in project.dests}
    for dest in project.dests:
        sheet = project.owners[id(dest)][0]
        _, refs = project.dest_views[id(dest)]
        _update_references(roots[sheet], paths.mutable_array(dest.contents[4].value),
                           refs, changes, counts[sheet], old, new, moved_paths)
        row = catalog_rows[ident(dest)[0]]
        _update_references(catalog, paths.mutable_array(row.contents[4].value),
                           refs, changes, dest_counts, old, new, moved_paths)
        if _reference_key(*refs[0]) in moved_paths:
            changes.group(catalog, row.contents[3], [new[1]])

    for (kind, owner, identity), (sequence, refs, geometry) in before.items():
        if kind == 'shunting':
            need(old not in sequence and new not in sequence,
                 'A saved Shunting or Overlap traverses an affected End')
            expected[kind, owner, identity] = sequence, refs, geometry
            continue
        nodes = _shift(sequence, old, new, forward, keep_closed_reference=bool(station_ends))
        if kind == 'itinerary':
            _review_station_sequence(project, sequence, nodes, station_ends)
            need(nodes == sequence or not route_factory.wrapper(
                itineraries[identity].contents[5].value, 'OTSafetyMarginArray'),
                'An Itinerary distance changes with existing position-based safety margins')
            if station_ends and nodes != sequence:
                itinerary_endpoints.append({'itinerary': identity[0], 'original_start': sequence[0],
                                            'replacement_start': nodes[0], 'original_end': sequence[-1],
                                            'replacement_end': nodes[-1]})
        if owner == old:
            owner = new
            identity = (*identity[:2], new[1])
        if refs is not None:
            identities = moved_paths if kind == 'itinerary' else moved_routes
            refs = [(sheet, {**entry, 'start_id': new[1]}) if _reference_key(sheet, entry) in identities
                    else (sheet, entry) for sheet, entry in refs]
        expected[kind, owner, identity] = nodes, refs, _movement_geometry(project, nodes, True)
    _guard_incident_bindings(courses, old, {item[2] for item in moved_routes},
                             {item[2] for item in moved_paths}, affected_names)
    _move_owners(project, old, new, changes, counts[document])
    prior_xy, after_xy = _move_graphic(project, old, new, signal, changes, counts[document])
    for keys, kind in ((station_ends, 1), (station_ends.values(), 2)):
        for key in keys:
            changes.group(roots[document], project.model(key).contents[20], [kind])
    changed = {name: writer.dump_verified(root, project.versions[name])
               for name, root in project.roots.items() if id(root) in changes.touched}
    final_dest = writer.dump_verified(catalog, catalog_version) if id(catalog) in changes.touched else dest_blob
    checked = project_from({**documents, **changed}, document_paths, final_dest)
    saved = checked.model((document, model_id(signal)))
    need(position(saved) == after_xy and saved.contents[7].value is checked.model(new)
         and checked.model(old).contents[11].value is None
         and _movement_manifest(checked) == expected,
         'Saved main signal or dependent Route, Path and Itinerary differs after reload')
    if station_ends:
        station = station_model(checked, document, station_id)
        for keys, kind in ((station_ends, 1), (station_ends.values(), 2)):
            need(all(checked.model(key).contents[12].value is station and checked.model(key).contents[20].value == kind
                     for key in keys), 'Saved native Station reference differs after reload')
    changes.restore()
    need({name: writer.fingerprint(root) for name, root in roots.items()} == fingerprints,
         'Relocation changed a field outside the reviewed signal and movement bindings')
    if final_dest != dest_blob:
        changed['$dest_catalog'] = final_dest
    station = project.model(old).contents[12].value
    receipt = {
        'action': request['action'], 'document': document, 'direction': request['direction'],
        'signal_id': model_id(signal), 'signal_name': paths.string(signal.contents[13].value),
        'from_end_id': old[1], 'to_end_id': new[1], 'edge_id': model_id(edge),
        'signal_shift_m': edge.contents[9].values[1] * (1 if forward else -1),
        'before_graphic_xy': prior_xy, 'after_graphic_xy': after_xy,
        'station_sign': paths.string(station.contents[7].value) if station is not None else None,
        'changed_documents': sorted(set(changed) - {'$dest_catalog'}),
        'destination_catalog_changed': final_dest != dest_blob, 'routes_rebound': moved,
        'paths_reowned': sorted(moved_paths), 'movement_count_checked': len(before),
        'nonselected_graph_verified': True, 'native_execution_tested': False,
    }
    if station_ends:
        receipt['station_reference_rebound'] = {'station_id': station_id, 'previous_ends': list(station_ends),
                                                'replacement_ends': list(station_ends.values())}
        receipt['changed_itinerary_endpoints'] = itinerary_endpoints
    return changed, receipt
