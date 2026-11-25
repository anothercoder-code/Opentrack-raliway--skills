"""Replace one in-use, fixed-station platform Edge in a single native write."""

from pathlib import PureWindowsPath

from . import native_occupation_groups as occupation, path_functions, route_factory, saved_station_areas, writer
from .graph_references import incoming_counts
from .multi_document.core import ident, need
from .network_operating_plan import route_trace
from .saved_crossing_dependencies import verify_transfers
from .saved_geometry import _edge, _insert_movement_nodes, _movement_manifest, _speed_table, model_id, position, project_from
from .saved_track_replacement import _protection_manifest, verify_replacement
from .saved_track_topology import _alignment, _builder, _replace_models
from .zero_generation import topology


def _waypoints(builder, occupied, edge, ends, station, operation):
    first, last = ends
    alignment = frozenset((_alignment(first), _alignment(last)))
    orientations = {frozenset(((1, 0), (2, 0))): 'horizontal', frozenset(((0, 4), (0, 3))): 'vertical'}
    need(alignment in orientations, 'Track Ends must have opposite original axial directions')
    total = edge.contents[9].values[1]
    distances = [0, *(row['distance_from_first_end_m'] for row in operation['waypoints']), total]
    need(3 <= len(distances) <= 34 and all(a < b for a, b in zip(distances, distances[1:])),
         'Provide strictly ordered interior distances on the original Edge')
    safety = first.contents[7].value
    need(last.contents[7].value is safety, 'Both old Ends must occupy the original exclusive Safety Element')
    pairs = []
    for row in operation['waypoints']:
        xy = tuple(topology.flt(row[axis], 'Replacement position') for axis in ('x', 'y'))
        need(xy not in occupied, 'The new vertex coincides with a native double vertex')
        occupied.add(xy)
        pair = builder.vertex({'x': float(xy[0]), 'y': float(xy[1]), 'orientation': orientations[alignment],
                               'names': ['', ''], 'insulated_joint': [False, False], 'axle_counter': [False, False]})
        approaching, = [end for end in pair if _alignment(end) == _alignment(last)]
        departing, = [end for end in pair if _alignment(end) == _alignment(first)]
        for end in pair:
            end.contents[7].value = safety
            end.contents[12].value = station
        pairs.append((approaching, departing))
    lengths = [b - a for a, b in zip(distances, distances[1:])]
    return builder.high, pairs, lengths


def _replace_track(project, document, edge, pairs, lengths, high):
    first, last = (edge.contents[slot].value for slot in (7, 8))
    outlet = [first, *(pair[1] for pair in pairs)]
    inlet = [*(pair[0] for pair in pairs), last]
    new_tracks = []
    for i, (a, b, length) in enumerate(zip(outlet, inlet, lengths, strict=True), 1):
        need(high + i < 2147483647, 'Native graphic ID exhausted')
        new = path_functions.clone(edge)
        new.contents[0].value = high + i
        new.contents[7].value, new.contents[8].value = a, b
        new.contents[9].values[1] = length
        for end in (a, b):
            if end in (first, last):
                field, = [slot for slot in (9, 10) if end.contents[slot].value is edge]
            else:
                field = 9
            end.contents[field].value = new
        new_tracks.append(new)
    additional = [end for pair in pairs for end in pair]
    element = first.contents[7].value
    members = element.contents[7].value
    need(incoming_counts(project.roots[document])[id(members)] == 1, 'The Safety Element member array has another owner')
    element.contents[7].value = path_functions.array_like(members, [*path_functions.mutable_array(members), *additional])
    current_models, _ = route_factory.document(project.roots[document])
    kept = [obj for obj in current_models if obj is not edge]
    _replace_models(project, document, [*kept, *additional, *new_tracks])
    return [model_id(track) for track in new_tracks]


def _occupation_groups(project, document, replacements, approvals):
    reviewed = {row['name']: row['expected_edge_ids'] for row in approvals}
    need(len(reviewed) == len(approvals), 'Select each reviewed local occupation group once')
    results = []
    for name, root in project.roots.items():
        _, models = route_factory.document(root)
        wrapper, array, groups = occupation.entries(root)
        for obj in groups:
            record = occupation.group_record(obj, models, name)
            saved = PureWindowsPath(record['saved_document']).name.casefold().removesuffix('.opentrack')
            if replacements.keys().isdisjoint(record['edge_ids']) or document.casefold() not in {name.casefold(), saved}:
                continue
            need(name == document and saved == document.casefold(), 'A foreign occupation group still observes the old platform Edge')
            group = record['name']
            need(reviewed.pop(group, None) == record['edge_ids'], 'Confirm every occupation group referencing the old Edge and its original order')
            counts = incoming_counts(root)
            need(all(counts[id(item)] == 1 for item in (wrapper, array, obj)), 'Occupation group uses shared objects')
            edge_ids = [item for edge in record['edge_ids'] for item in replacements.get(edge, [edge])]
            occupation.verify_edges(models, edge_ids)
            obj.contents[2].value = occupation.edge_array(edge_ids)
            results.append({'before': {**record, 'unresolved_edge_ids': [num for num in record['unresolved_edge_ids'] if num not in replacements]},
                            'after': {**record, 'edge_ids': edge_ids, 'unresolved_edge_ids': []}})
    need(not reviewed, 'An approved occupation group did not reference the old platform Edge')
    return results


def _visits(project, witness):
    retained = []
    for destination in project.dests:
        key = 'itinerary', project.owners[id(destination)], ident(destination)
        if key not in witness:
            continue
        trace = route_trace(project, destination)
        stays = []
        for row in trace['visits']:
            stay = {field: row[field] for field in ('station_sign', 'end_key', 'distance_m', 'stopping_area_length_m',
                                                   'incoming_track_id', 'halt_stop_issue')}
            for field in ('head_stop', 'default_stop'):
                stop = row.get(field)
                if stop is not None:
                    stay[field] = {name: stop[name] for name in ('signal_id', 'end_key', 'distance_m', 'available_length_m')}
            stays.append(stay)
        retained.append({'owner': key[1], 'identity': key[2], 'visits': stays})
    return retained


def replace_used_platform_edge(documents, paths, dest, document, operation, shapes):
    project = project_from(documents, paths, dest)
    old = _edge(project, document, operation)
    old_id = model_id(old)
    _speed_table(old)
    total = old.contents[9].values[1]
    need(total == operation['expected_edge_length_m'], 'The saved platform track length differs from the review')
    first, last = (old.contents[slot].value for slot in (7, 8))
    station = saved_station_areas.platform_split_station(project, document, operation, first, last)

    builder = _builder(project, document, shapes)
    occupied = {tuple(position(end)) for end in project.ends(document)}
    high, pairs, lengths = _waypoints(builder, occupied, old, (first, last), station, operation)
    forward = [pair[0] for pair in pairs]
    backward = [pair[1] for pair in reversed(pairs)]
    inserts = {(first, last): forward, (last, first): backward}
    plan = {(project.key(a), project.key(b)): [(document, model_id(end)) for end in nodes]
            for (a, b), nodes in inserts.items()}
    expected = {}
    touched = set()
    for identity, (sequence, refs, geometry) in _movement_manifest(project).items():
        adjusted = []
        for a, b in zip(sequence, sequence[1:]):
            adjusted.append(a)
            adjusted.extend(plan.get((project.actual_related(a), b), ()))
        adjusted.append(sequence[-1])
        if adjusted != sequence:
            touched.add(identity)
        expected[identity] = adjusted, refs, geometry
    need(touched, 'The selected platform Edge is outside all saved operational movement definitions')
    visits = _visits(project, touched)
    protection = _protection_manifest(project, document)
    rewritten = _insert_movement_nodes(project, document, lambda a, b: inserts.get((a, b), ()), unique_arrays=True)
    need(rewritten, 'Could not rebind any native Route or Shunting member to the platform replacement')
    new_ids = _replace_track(project, document, old, pairs, lengths, high)
    groups = _occupation_groups(project, document, {old_id: new_ids}, operation.get('occupation_groups', ()))
    waypoints = [{'end_ids': [model_id(end) for end in pair], 'xy': position(pair[0]),
                  'distance_from_first_end_m': row['distance_from_first_end_m']}
                 for pair, row in zip(pairs, operation['waypoints'], strict=True)]
    report = {'action': operation['action'], 'document': document, 'changed_documents': [document],
              'station_id': operation['station_id'], 'station_sign': path_functions.string(station.contents[7].value),
              'retired_edge_id': old_id, 'replacement_edge_ids': new_ids, 'lengths_m': lengths, 'length_m': total,
              'former_end_ids': [model_id(first), model_id(last)],
              'station_member_end_ids_added': sorted(model_id(end) for pair in pairs for end in pair),
              'replacement_waypoints': waypoints,
              'safety_element_id': model_id(first.contents[7].value), 'rewritten_movements': rewritten,
              'verified_stopping_itineraries': visits, 'occupation_groups': groups,
              'movement_count_checked': len(expected), 'destination_catalog_unchanged': True, 'native_execution_tested': False}
    output = writer.dump_verified(project.roots[document], project.versions[document])
    fresh = project_from({**documents, document: output}, paths, dest)
    need(_movement_manifest(fresh) == expected, 'A saved movement changed distance, track physics or operational references')
    need(_visits(fresh, touched) == visits, 'A station stop location, available length or stopping track changed')
    need([fresh.model((document, key)).contents[9].values[1] for key in new_ids] == lengths
         and all(position(fresh.model((document, end))) == point['xy']
                 for point in waypoints for end in point['end_ids']),
         'A replacement physical length or reviewed drawing coordinate differs after native readback')
    saved_station_areas.verify_members(fresh, document, report)
    verify_replacement(fresh, document, report, protection)
    verify_transfers(fresh, {}, groups)
    return {document: output}, report
