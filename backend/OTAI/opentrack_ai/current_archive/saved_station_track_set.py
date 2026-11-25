"""Rebuild a connected selection of used station and throat rails in one save."""

from math import isfinite

from . import path_functions, saved_station_areas, writer
from .multi_document.core import need
from .saved_crossing_dependencies import verify_transfers
from .saved_geometry import _edge, _insert_movement_nodes, _movement_manifest, _speed_table, model_id, position, project_from
from .saved_platform_replacement import _occupation_groups, _replace_track, _visits, _waypoints
from .saved_track_replacement import _protection_manifest
from .saved_track_topology import _builder


def _station_membership(project, document, ends, station, operation):
    scope = operation['station_scope']
    if scope == 'platform':
        return saved_station_areas.platform_split_station(project, document, operation, *ends)
    for end in ends:
        saved_station_areas.end_pair(project, document, end)
    groups = [end.contents[12].value for end in ends]
    ordinary = all(end.contents[20].value == 1 for end in ends)
    if scope == 'junction_core':
        need(ordinary and all(group is None for group in groups),
             'A junction core Edge requires two ordinary ungrouped Ends')
        need(list(map(model_id, ends)) == operation.get('expected_end_ids'),
             'The original junction core Edge directional Ends differ from the review')
        safety = ends[0].contents[7].value
        element = operation.get('expected_safety_element_id')
        need(writer.kind(safety) == 'OTElement' and project.key(safety) == (document, element)
             and ends[1].contents[7].value is safety
             and set(ends) <= set(path_functions.mutable_array(safety.contents[7].value)),
             'The original junction core Edge Safety Element membership differs from the review')
        return None
    need(scope == 'boundary_approach' and ordinary,
         'A station boundary approach requires ordinary Ends without a station reference')
    need(any(group is station for group in groups) and any(group is None for group in groups),
         'A station boundary approach must meet the selected station at exactly one End')
    return None


def _require_connected(vertices):
    remaining = list(vertices)
    connected = set(remaining.pop())
    while remaining:
        adjacent = [pair for pair in remaining if connected.intersection(pair)]
        need(adjacent, 'The selected rails must form one connected station track set')
        connected.update(end for pair in adjacent for end in pair)
        remaining = [pair for pair in remaining if pair not in adjacent]


def _turnout(end):
    return {'end_id': model_id(end),
            'edge_ids': [model_id(end.contents[slot].value) for slot in (9, 10)],
            'switch_time_s': end.contents[21].value, 'default_second_leg': bool(end.contents[22].value)}


def _review_junction_turnouts(project, document, core_edges, turnouts, reviews):
    indexed = {item['end_id']: item for item in reviews}
    need(len(indexed) == len(reviews) and indexed.keys() == turnouts.keys(),
         'Review every junction core turnout once with its exact ordered legs')
    need(not core_edges or turnouts, 'The reviewed junction core must include a native turnout')
    for end_id, before in turnouts.items():
        selected = indexed[end_id]
        end = project.model((document, end_id))
        branch = end.contents[22].value
        legs = before['edge_ids']
        seconds = before['switch_time_s']
        need(branch in (0, 1) and isfinite(seconds) and seconds >= 0
             and legs == selected['expected_edge_ids'] and legs[branch] == selected['expected_default_edge_id']
             and seconds == selected['expected_switch_time_s'],
             f'The original junction turnout {end_id} legs, default or switch time differ from the review')


def _expected_movements(project, document, inserts):
    by_direction = {(project.key(a), project.key(b)): (model_id(edge), [(document, model_id(end)) for end in nodes])
                    for (a, b), (edge, nodes) in inserts.items()}
    expected, affected_edges = {}, {}
    for identity, (sequence, refs, physics) in _movement_manifest(project).items():
        adjusted, used = [], set()
        for a, b in zip(sequence, sequence[1:]):
            adjusted.append(a)
            replacement = by_direction.get((project.actual_related(a), b))
            if replacement is not None:
                used.add(replacement[0])
                adjusted.extend(replacement[1])
        adjusted.append(sequence[-1])
        if used:
            affected_edges[identity] = used
        expected[identity] = adjusted, refs, physics
    return expected, affected_edges


def _junction_witnesses(project, station, core_edges, visits, affected_edges):
    covered = set()
    witnesses = []
    for row in visits:
        identity = 'itinerary', row['owner'], row['identity']
        edges = affected_edges[identity] & core_edges
        if edges and any(project.model(visit['end_key']).contents[12].value is station for visit in row['visits']):
            covered.update(edges)
            witnesses.append({'itinerary': row['identity'][0], 'core_edge_ids': sorted(edges)})
    need(covered == core_edges, 'Each junction core Edge needs a saved Itinerary through the reviewed station')
    return witnesses


def replace_used_station_track_set(documents, paths, dest, document, operation, shapes):
    project = project_from(documents, paths, dest)
    station = saved_station_areas.station_model(project, document, operation['station_id'])
    selected = operation['edges']
    old_ids = {row['edge_id'] for row in selected}
    need(2 <= len(selected) <= 32 and len(old_ids) == len(selected), 'Select between 2 and 32 distinct station Edges')
    builder = _builder(project, document, shapes)
    occupied = {tuple(position(end)) for end in project.ends(document)}
    plans, vertices, inserts, switches = [], [], {}, {}
    core_edges, core_switches, safety_members = set(), {}, {}
    for row in selected:
        edge = _edge(project, document, row)
        _speed_table(edge)
        edge_id = model_id(edge)
        need(edge.contents[9].values[1] == row['expected_edge_length_m'], f'The length of Edge {edge_id} differs from the review')
        first, last = (edge.contents[slot].value for slot in (7, 8))
        ends = first, last
        belonging = _station_membership(project, document, ends, station, {**row, 'station_id': operation['station_id']})
        is_core = row['station_scope'] == 'junction_core'
        if is_core:
            core_edges.add(edge_id)
            element = first.contents[7].value
            safety_members.setdefault(model_id(element), list(map(model_id, path_functions.mutable_array(element.contents[7].value))))
        vertices.append(tuple(min(project.key(end), project.related(project.key(end))) for end in ends))
        high, pairs, lengths = _waypoints(builder, occupied, edge, ends, belonging, row)
        builder.high = high + len(lengths)
        need(builder.high < 2147483647, 'Native graphic ID exhausted')
        need((first, last) not in inserts, 'Parallel Edges on the same directional Ends require separate review')
        inserts[first, last] = edge, [a for a, _ in pairs]
        inserts[last, first] = edge, [b for _, b in reversed(pairs)]
        for end in ends:
            if all(end.contents[slot].value is not None for slot in (9, 10)):
                before = _turnout(end)
                switches[model_id(end)] = before
                if is_core:
                    core_switches[model_id(end)] = before
        plans.append((edge, ends, pairs, lengths, high, row))
    _require_connected(vertices)
    _review_junction_turnouts(project, document, core_edges, core_switches, operation.get('junction_turnout_reviews', ()))
    expected, affected_edges = _expected_movements(project, document, inserts)
    need(set().union(*affected_edges.values()) == old_ids, 'Each selected Edge must have at least one saved operational movement')
    visits = _visits(project, affected_edges)
    witnesses = _junction_witnesses(project, station, core_edges, visits, affected_edges) if core_edges else []
    protection = _protection_manifest(project, document)
    rewritten = _insert_movement_nodes(project, document, lambda a, b: inserts.get((a, b), (None, ()))[1], unique_arrays=True)
    need(rewritten, 'Could not update native Route or Shunting movements for the selected station rails')

    tracks, replacements, new_legs, added_safety_members = [], {}, {}, {}
    for edge, ends, pairs, lengths, high, row in plans:
        edge_id = model_id(edge)
        new_ids = _replace_track(project, document, edge, pairs, lengths, high)
        replacements[edge_id] = new_ids
        end_ids = list(map(model_id, ends))
        new_legs[end_ids[0], edge_id] = new_ids[0]
        new_legs[end_ids[1], edge_id] = new_ids[-1]
        points = [{'end_ids': list(map(model_id, pair)), 'xy': position(pair[0]),
                   'distance_from_first_end_m': waypoint['distance_from_first_end_m']}
                  for pair, waypoint in zip(pairs, row['waypoints'], strict=True)]
        element_id = model_id(ends[0].contents[7].value)
        if element_id in safety_members:
            added_safety_members.setdefault(element_id, []).extend(end_id for point in points for end_id in point['end_ids'])
        tracks.append({'retired_edge_id': edge_id, 'replacement_edge_ids': new_ids, 'lengths_m': lengths,
                       'former_end_ids': end_ids, 'replacement_waypoints': points, 'station_scope': row['station_scope'],
                       'safety_element_id': element_id})
    groups = _occupation_groups(project, document, replacements, operation.get('occupation_groups', ()))
    output = writer.dump_verified(project.roots[document], project.versions[document])
    fresh = project_from({**documents, document: output}, paths, dest)
    need(_movement_manifest(fresh) == expected, 'A saved movement changed distance, track physics or operational references')
    need(_visits(fresh, affected_edges) == visits, 'A station stop location, available length or stopping track changed')
    need(_protection_manifest(fresh, document) == protection,
         'Signal indications, release groups, occupied entry or Shunting settings changed during replacement')
    need(old_ids.isdisjoint(fresh.byid[document]), 'A retired Edge survived native readback')
    after_switches = [_turnout(fresh.model((document, key))) for key in sorted(switches)]
    for after in after_switches:
        end_id = after['end_id']
        before = switches[end_id]
        legs = [new_legs.get((end_id, old_id), old_id) for old_id in before['edge_ids']]
        need(after == {**before, 'edge_ids': legs}, 'A native turnout leg, default or throwing time failed readback')
    memberships = {'platform': [], 'boundary_approach': [], 'junction_core': []}
    for track in tracks:
        need([fresh.model((document, key)).contents[9].values[1] for key in track['replacement_edge_ids']] == track['lengths_m'],
             'A replacement physical length failed native readback')
        members = memberships[track['station_scope']]
        for point in track['replacement_waypoints']:
            for end_id in point['end_ids']:
                end = fresh.model((document, end_id))
                need(position(end) == point['xy'] and model_id(end.contents[7].value) == track['safety_element_id'],
                     'A reviewed drawing coordinate or Safety Element failed native readback')
                members.append(end_id)
    inside, outside, core_members = (memberships[key] for key in ('platform', 'boundary_approach', 'junction_core'))
    saved_station_areas.verify_members(fresh, document, {'station_id': operation['station_id'],
                                                       'station_member_end_ids_added': inside,
                                                       'station_member_end_ids_removed': [*outside, *core_members]})
    verify_transfers(fresh, {}, groups)
    core = {}
    if core_edges:
        elements = []
        for element_id, before in sorted(safety_members.items()):
            safety = fresh.model((document, element_id))
            after = list(map(model_id, path_functions.mutable_array(safety.contents[7].value)))
            need(after == [*before, *added_safety_members[element_id]] and len(after) == len(set(after)),
                 'The junction Safety Element did not preserve its original members and attach each new End exactly once')
            elements.append({'element_id': element_id, 'before_end_ids': before, 'after_end_ids': after})
        core['junction_core'] = {'edge_ids': sorted(core_edges), 'turnout_end_ids': sorted(core_switches),
                                 'station_witnesses': witnesses, 'ungrouped_end_ids_added': sorted(core_members),
                                 'safety_elements': elements}
    return {document: output}, {'action': operation['action'], 'document': document, 'changed_documents': [document],
            'station_id': operation['station_id'], 'station_sign': path_functions.string(station.contents[7].value),
            'tracks': tracks, 'turnouts_before': [switches[key] for key in sorted(switches)], 'turnouts_after': after_switches,
            'station_member_end_ids_added': sorted(inside), 'ungrouped_boundary_approach_end_ids_added': sorted(outside),
            'rewritten_movements': rewritten, 'verified_stopping_itineraries': visits, 'occupation_groups': groups,
            'movement_count_checked': len(expected), 'destination_catalog_unchanged': True, 'native_execution_tested': False,
            'signal_and_release_settings_preserved': True, **core}
