"""Geometry preflight for native reciprocal split and join timetable commands."""

from collections import defaultdict
from math import isfinite

from . import route_factory, writer
from .movement_edits import _movement_project
from .multi_document.core import ident, ref
from .operating_plan_edit import need
from .route_edit_tools import _route_shape
from .shunting_workflow.core import plan_connections


def _route_reference(record):
    return record['name'], record['array_id'], record['start_id']


def itinerary_routes(project, dest):
    _, paths = project.dest_view(dest)
    for owner, info in paths:
        path = project.itinerary_path((owner, info['start_id']), _route_reference(info))
        for document, reference in project.path_view(path)[1]:
            if reference.get('kind') == 'shunting':
                continue
            start = document, reference['start_id']
            yield project.owned(start, 'OTRoute', _route_reference(reference))


def _arrival_route(project, dest, event_end):
    """Look up the specific ordinary route ending at the joining occurrence."""
    incoming = {id(route): route for route in itinerary_routes(project, dest)
                if project.route_view(route)[-1] == event_end}
    need(len(incoming) == 1, 'Select an unambiguous saved arrival Route for occupied-entry joining')
    return next(iter(incoming.values()))


def _entry_signal(project, route):
    key = project.owners[id(route)]
    first = project.model(key)
    signal = first.contents[11].value
    need(signal is not None, 'The exact occupied-entry Route must start at a native signal')
    route_factory.layout(signal, 'OTSignalModel', 11, route_factory.SIGNAL, graphic=True)
    need(signal.contents[7].value is first and signal.contents[8].values[0] in (1, 2, 24, 25, 26),
         'The occupied-entry Signal must be the paired native main signal at the Route origin')
    flags = signal.contents[9].values[2]
    need(type(flags) is int and -(2**31) <= flags < 2**31, 'Unknown Signal11 flags')
    return key[0], signal


def occupied_entry_route_parts(project, primary):
    _route_shape(primary)
    owner = project.owners[id(primary)]
    marker = ref(primary)
    records = [row for row in project.continuations
               if row['source_document'] == owner[0] and row['route'] == marker]
    need(len(records) == int(primary.contents[5].values[4] != -1),
         'Exact native occupied-entry continuation is not unique')
    if not records:
        return [(owner, primary)]
    record, = records
    receiving = record['target_document'], record['target_connector']
    fragment = project.owned(receiving, 'OTRoute', ident(primary))
    _route_shape(fragment)
    return [(owner, primary), (receiving, fragment)]


def _station_location(report, sign, index=None):
    visits = report['visits']
    if index is not None:
        need(0 < index < len(visits) - 1 and visits[index]['station_sign'] == sign,
             'Selected main visit must match an interior occurrence in the saved directed itinerary')
        return index, visits[index]
    hits = [(position, visit) for position, visit in enumerate(visits) if visit['station_sign'] == sign]
    need(len(hits) == 1, 'Select exactly one station occurrence in each Course')
    return hits[0]


def _berth_position(document, segments, distance):
    for edge, length in segments:
        if distance <= length:
            return {'document': document, 'edge_id': edge, 'offset_m': distance}
        distance -= length
    raise ValueError('Formation position is outside the reviewed directed berth')


def _reviewed_berth(project, report, visit, expected, stopping_length_m):
    from .network_operating_plan import MAIN, resolve_visit_stop

    end = visit['end_key']
    point = resolve_visit_stop(visit, stopping_length_m)
    owner = project.model(end)
    signal = owner.contents[11].value
    need(not visit.get('halt_stop_issue') and point is not None and point['head_end_key'] == end
         and point['end_key'] == end and signal is not None and signal.contents[7].value is owner
         and signal.contents[8].values[0] in MAIN and signal.contents[8].values[1] == 4
         and signal.contents[0].value == point['signal_id'],
         'A reviewed berth requires an actual head at its paired directional main exit Signal')
    document = end[0]
    berth = visit['stopping_area_edge_keys']
    trace = report['_formation_trace']
    nodes, distances = trace['_directed_nodes'], trace['_node_distances_m']
    need(nodes.count(end) == 1 and 1 <= len(berth) <= 100 and len(set(berth)) == len(berth)
         and all(key[0] == document for key in berth),
         'A reviewed berth needs one occurrence and a finite same-sheet directed track chain')
    terminal = nodes.index(end)
    start = terminal - len(berth)
    need(start >= 0 and trace['edges'][start:terminal] == berth and point['distance_m'] == distances[terminal],
         'The reviewed berth must be exactly the contiguous native approach to the head')
    segments = []
    station = owner.contents[12].value
    for i, edge in enumerate(berth, start):
        first, last = nodes[i:i + 2]
        paired = project.actual_related(first)
        length = distances[i + 1] - distances[i]
        track = project.model(edge)
        need(project.edge_between(first, last) == edge and length > 0 and length == track.contents[9].values[1]
             and all(key[0] == document and writer.kind(project.model(key)) == 'OTEndModel'
                     and project.model(key).contents[12].value is station
                     and project.model(key).contents[10].value is None for key in (first, paired, last)),
             'The reviewed berth must follow adjacent nonbranching Ends in one native StationModel')
        segments.append((edge[1], length))
    area = distances[terminal] - distances[start]
    need(0 < stopping_length_m <= area == point['available_length_m']
         and point['stop_edge_key'] == berth[-1] and point['head_edge_offset_m'] == segments[-1][1],
         'The exact native head and the arriving formation must fit the directed berth')
    actual = {'station_end': {'document': document, 'end_id': end[1]}, 'signal_id': point['signal_id'],
              'platform_edges': [{'document': document, 'edge_id': edge} for edge, _ in segments],
              'head': _berth_position(document, segments, area)}
    need(actual == expected, 'Reviewed berth, directional head or ordered platform Edges differ from native readback')
    return actual, point, segments


def verify_split_berth_geometry(project, event, main, child, itineraries, expected, *, arrival_length_m, retained_length_m):
    """Check one explicit same-direction split on a continuous same-sheet native berth."""
    from .native_link_start import successor_start

    sign = event['station_sign']
    index, visit = _station_location(main, sign, event['main_visit_index'])
    child_index, origin = _station_location(child, sign)
    end = visit['end_key']
    need(event['kind'] == 'split' and 0 < index < len(main['visits']) - 1
         and child_index == 0 and origin['end_key'] == end
         and visit['planned']['stop'] and origin['planned']['stop'],
         'A reviewed split requires a stopped parent interior visit and the same directed child origin')
    need(0 < retained_length_m < arrival_length_m, 'A reviewed split must leave part of the actual parent formation')
    actual, point, segments = _reviewed_berth(project, main, visit, expected, arrival_length_m)
    document = end[0]
    area = point['available_length_m']
    parent_dest = itineraries[main['itinerary']]
    child_dest = itineraries[child['itinerary']]
    parent_routes = list(itinerary_routes(project, parent_dest))
    child_first = next(iter(itinerary_routes(project, child_dest)), None)
    arrivals = [i for i, route in enumerate(parent_routes) if project.route_view(route)[-1] == end]
    need(len(arrivals) == 1 and arrivals[0] + 1 < len(parent_routes)
         and child_first is parent_routes[arrivals[0] + 1] and project.owners[id(child_first)] == end,
         'The same-direction split child must use the exact native departure Route of its parent at the berth')
    birth = successor_start(project, parent_dest, child_dest, main['_formation_trace'], child['_formation_trace'],
                            {**visit, 'visit_index': index, 'stopping_point': point}, origin, 'continue',
                            (event['main_course'], event['other_course']))
    need(birth['matched_predecessor_route_index'] == arrivals[0],
         'The original split Route scan selects a different berth arrival Route')
    return {**actual, 'head_distance_m': point['distance_m'], 'available_length_m': area,
            'arrival_tail': _berth_position(document, segments, area - arrival_length_m),
            'retained_tail': _berth_position(document, segments, area - retained_length_m),
            'child_first_route': {'document': document, **ref(child_first)}, 'native_birth': birth}


def verify_join_berth_geometry(project, event, receiver, donor, itineraries, expected, *, arrival_length_m, joined_length_m):
    """Resolve same-direction contact at the receiver's actual tail on a shared native arrival Route."""
    sign = event['station_sign']
    index, visit = _station_location(receiver, sign, event['main_visit_index'])
    donor_index, terminal = _station_location(donor, sign)
    end = visit['end_key']
    need(event['kind'] == 'join' and 0 < index < len(receiver['visits']) - 1
         and donor_index == len(donor['visits']) - 1 and terminal['end_key'] == end
         and visit['planned']['stop'] and terminal['planned']['stop'],
         'A reviewed join requires a stopped receiver interior visit and a same-direction donor terminal')
    donor_length = donor['consist_length_m']
    need(0 < arrival_length_m < joined_length_m and joined_length_m == arrival_length_m + donor_length,
         'A reviewed join must account for the complete actual receiver and donor formations')
    actual, head, segments = _reviewed_berth(project, receiver, visit, expected, arrival_length_m)
    _, donor_head, donor_segments = _reviewed_berth(project, donor, terminal, expected, donor_length)
    document = end[0]
    area = head['available_length_m']
    need(donor_segments == segments and joined_length_m <= area,
         'The receiver and donor must fit together on the exact same directed berth')
    incoming = _arrival_route(project, itineraries[receiver['itinerary']], end)
    donor_routes = list(itinerary_routes(project, itineraries[donor['itinerary']]))
    need(donor_routes and donor_routes[-1] is incoming
         and _arrival_route(project, itineraries[donor['itinerary']], end) is incoming,
         'The receiver and the terminal donor must share the exact native directional arrival Route')
    route_nodes = project.route_view(incoming)
    berth_edges = visit['stopping_area_edge_keys']
    route_edges = [project.edge_between(a, b) for a, b in zip(route_nodes, route_nodes[1:])]
    need(len(route_edges) >= len(berth_edges) and route_edges[-len(berth_edges):] == berth_edges,
         'The whole directed contact berth must be within the common occupied-entry arrival Route')
    owner, _ = project.owners[id(incoming)]
    _, entry = _entry_signal(project, incoming)
    route_flags, speed, wait = incoming.contents[6].values
    signal_flags = entry.contents[9].values[2]
    need(type(route_flags) is int and 0 <= route_flags <= 15 and bool(route_flags & 1) and bool(signal_flags & 1)
         and all(isfinite(value) and value >= 0 for value in (speed, wait)),
         'The shared occupied-entry Route and its entrance Signal must both admit the join')
    contact = _berth_position(document, segments, area - arrival_length_m)
    contact_key = document, contact['edge_id']
    location = route_edges.index(contact_key)
    length = dict(segments)[contact['edge_id']]
    need(route_edges.count(contact_key) == 1 and 0 < contact['offset_m'] < length,
         'The first occupied contact Edge must contain the actual receiver tail in its interior')
    near, far = project.actual_related(route_nodes[location]), route_nodes[location + 1]
    resources = [project.key(project.model(key).contents[7].value) for key in (near, far)]
    need(resources[0] == resources[1], 'The actual join contact Edge must have one native Safety Element owner')
    return {**actual, 'head_distance_m': head['distance_m'], 'available_length_m': area,
            'contact': contact, 'donor_tail': _berth_position(document, segments, area - joined_length_m),
            'donor_contact_distance_m': donor_head['distance_m'] - arrival_length_m,
            'donor_nominal_head_distance_m': donor_head['distance_m'],
            'arrival_route': {'document': owner, **ref(incoming)},
            'occupied_entry': {'signal_id': entry.contents[0].value, 'signal_flags': signal_flags,
                               'route_flags': route_flags, 'speed_kmh': speed, 'wait_s': wait,
                               'signal_type': entry.contents[8].values[0], 'signal_role': entry.contents[8].values[1]},
            'contact_safety_elements': [{'document': sheet, 'element_id': number} for sheet, number in resources]}


def _admit_spatial_event(project, event, reports, itineraries, *, current_formation=None, split_berth=None,
                         join_berth=None, reverse_split=None):
    receiver = reports[event['main_course']]
    secondary = reports[event['other_course']]
    main_index, main = _station_location(receiver, event['station_sign'], event.get('main_visit_index'))
    _, other = _station_location(secondary, event['station_sign'])
    a = receiver['consist_length_m'] if current_formation is None else current_formation['length_m']
    b = secondary['consist_length_m']
    if reverse_split is None:
        approved_end = main['end_key'] == other['end_key']
    else:
        birth = reverse_split['native_birth']
        approved_end = (event['kind'] == 'split' and split_berth is None and
                        main['end_key'] == birth['arrival_station_end_key'] and
                        other['end_key'] == birth['birth_end_key'] and main_index == birth['from_visit_index'])
    need(main['stop_edge_key'] is not None and approved_end,
         'Train parts must use the same directed station reference, with a validated stopping Edge for the main train')
    need(main['planned']['stop'] and other['planned']['stop'], 'Both native composition participants must stop at the event')
    need(not other['planned'].get('track_id') or other['planned']['track_id'] == main['incoming_track_id'],
         'The requested composition track differs from the verified stopping Edge')
    need(split_berth is None or event['kind'] == 'split', 'A reviewed split berth only applies to a split event')
    need(join_berth is None or event['kind'] == 'join', 'A reviewed join berth only applies to a join event')
    berth = (reverse_split or split_berth) if event['kind'] == 'split' else join_berth
    area = main['stop_edge_length_m'] if berth is None else berth['available_length_m']
    settings = None
    if event['kind'] == 'split':
        need(other is secondary['visits'][0] and a > b and area >= a,
             'Split child must originate at the main stop and the complete initial train must fit the directed stopping Edge')
        after = a - b
    else:
        need(other is secondary['visits'][-1] and main['stop_edge_key'] == other['stop_edge_key'] and area >= a + b,
             'Joined train must fit the common directed stopping Edge at the supplying Course terminal')
        need(secondary['maximum_speed_kmh'] >= receiver['maximum_speed_kmh'],
             'Joined supply has lower vmax than the generated main running-time bound')
        need(main['planned']['arrival_s'] < other['planned']['arrival_s'],
             'Receiver must be planned to reach the common platform before the supplying Course')
        incoming = _arrival_route(project, itineraries[secondary['itinerary']], other['end_key'])
        flags, approach_speed, wait = incoming.contents[6].values
        _, signal = _entry_signal(project, incoming)
        need(type(flags) is int and bool(flags & 1) and bool(signal.contents[9].values[2] & 1),
             'Both the actual supplying Route and its entrance signal must explicitly allow occupied entry')
        settings = {
            'arrival_route': {'name': _route_name(incoming), 'owner': project.owners[id(incoming)]},
            'signal_id': signal.contents[0].value,
            'occupied_entry_speed_kmh': approach_speed,
            'occupied_entry_use_speed': bool(flags & 2),
            'occupied_entry_use_time': bool(flags & 4),
            'occupied_entry_wait_s': wait,
        }
        after = a + b
    result = {
        'station_end_key': main['end_key'],
        'receiver_visit_index': main_index,
        'stop_edge_key': main['stop_edge_key'],
        'available_length_m': area,
        'receiver_before_m': a,
        'secondary_length_m': b,
        'receiver_projected_after_m': after,
        'native_occupied_entry': settings,
    }
    if split_berth is not None:
        result['native_split_berth'] = split_berth
    if join_berth is not None:
        result['native_join_berth'] = join_berth
    if reverse_split is not None:
        result['native_reverse_split_berth'] = reverse_split
    return result


def _check_receiver_clearance(reports, events):
    from .network_operating_plan import resolve_visit_stop

    by_course = defaultdict(dict)
    for event in events:
        location = event['spatial']
        by_course[event['main_course']][location['receiver_visit_index']] = location
    clearance = {}
    for course, changes in by_course.items():
        active = reports[course]['consist_length_m']
        rows = []
        for index, visit in enumerate(reports[course]['visits']):
            if index == 0 or not visit['planned']['stop']:
                continue
            arrival = active
            change = changes.get(index)
            if change is not None:
                need(arrival == change['receiver_before_m'], 'A repeated formation change lost its incoming stock state')
                active = change['receiver_projected_after_m']
                length = change.get('available_length_m', visit['stop_edge_length_m'])
            else:
                stop = resolve_visit_stop(visit, arrival)
                length = (stop['available_length_m'] if stop is not None
                          else visit['stop_edge_length_m'])
            need(length is not None and length >= max(arrival, active),
                 f'Current composition does not fit the directed stopping Edge at {course}#{index}')
            rows.append({'visit_index': index, 'station_sign': visit['station_sign'], 'available_length_m': length,
                         'arrival_length_m': arrival, 'departure_length_m': active})
        clearance[course] = rows
    return clearance


def _route_name(route):
    from .path_functions import info
    return info(route)['name']


def configure_join_approaches(state, project, settings):
    """Set explicit occupied-entry speed on the exact incoming primary/continuation Route."""
    plans = {item.course_id: item for item in settings.courses}
    itineraries = {writer.string(item.contents[1].value): item for item in project.dests}
    chosen, signal_edits = {}, {}
    for event in settings.composition_events:
        if event.occupied_entry_speed_kmh is None:
            continue
        need(event.kind == 'join', 'Only a physical join can configure an occupied-entry approach')
        donor = plans[event.other_course]
        need(donor.visits[-1].station_sign == event.station_sign and donor.visits[-1].stop,
             'Configure occupied entry only for the supplying terminal stop')
        dest = itineraries[donor.itinerary]
        terminal = project.dest_view(dest)[0][-1]
        primary = _arrival_route(project, dest, terminal)
        signal_owner, signal = _entry_signal(project, primary)
        signal_edits[id(signal)] = signal_owner, signal
        for _, route in occupied_entry_route_parts(project, primary):
            obj_id = id(route)
            speed = float(event.occupied_entry_speed_kmh)
            need(obj_id not in chosen or chosen[obj_id][1] == speed, 'Conflicting speeds for the same native arrival Route')
            chosen[obj_id] = route, speed
    if not chosen:
        return state, project, []
    edits, restoration = [], {}
    for route, speed in chosen.values():
        owner = project.owners[id(route)][0]
        flags, _, wait = route.contents[6].values
        need(type(flags) is int and 0 <= flags <= 15, 'Unknown occupied-entry flags')
        restoration.setdefault(owner, []).append((route.contents[6], list(route.contents[6].values), [flags | 3, speed, wait]))
        edits.append({'document': owner, 'route': _route_name(route), 'occupied_entry_speed_kmh': speed})
    for owner, signal in signal_edits.values():
        group = signal.contents[9]
        prior_flags = list(group.values)
        flags = list(prior_flags)
        flags[2] |= 1
        restoration.setdefault(owner, []).append((group, prior_flags, flags))
        edits.append({'document': owner, 'signal_id': signal.contents[0].value, 'allow_occupied_entry': True})
    docs = dict(state['documents'])
    files = dict(state['files'])
    for owner, changes in restoration.items():
        root = project.roots[owner]
        before = writer.fingerprint(root)
        try:
            for group, _, new in changes:
                group.values = new
            docs[owner] = writer.dump_verified(root, project.versions[owner])
        finally:
            for group, old, _ in changes:
                group.values = old
        need(writer.fingerprint(root) == before, 'Unrelated infrastructure graph changed while preparing join')
        files[state['document_members'][owner]] = docs[owner]
    fresh = _movement_project(docs, state['document_paths'], files[state['roles']['dest']], allow_external_destinations=True)
    return {**state, 'documents': docs, 'files': files}, fresh, edits


def bind_composition(project, events, reports, itineraries, sources, *, verify_existing=False, reverse_splits=None):
    """Validate geometry and reuse the audited native Connection6 serializer."""
    table, report = plan_connections(
        sources,
        {'schema': 'split-join-timetable-plan/1', 'operations': events,
         'accept_unverified_spatial_and_dynamic_execution': True},
        child_before_main=False,
        sequential_main=True,
        verify_existing=verify_existing,
    )
    for event, item in zip(events, report['events'], strict=True):
        reverse = (reverse_splits or {}).get((item['main_course'], item['other_course']))
        checked = _admit_spatial_event(project, event, reports, itineraries, current_formation=item['initial_main'],
                                       reverse_split=reverse)
        verify_event_geometry(item, checked)
        item['spatial'] = checked
        if item['kind'] == 'split':
            item['planned_departure_order'] = ('main_then_child' if item['main_departure_s'] < item['other_event_s']
                                                else 'child_then_main_or_equal')
    report['receiver_stopping_clearance'] = _check_receiver_clearance(reports, report['events'])
    report['spatial_compatibility_verified'] = True
    report['scope'] = 'Native Connection6 and verified directed geometry, with dynamic stock behavior pending original run'
    return table, report


def verify_event_geometry(event, spatial):
    need(event['main_visit_index'] == spatial['receiver_visit_index'],
         'Native connection row differs from the directed Itinerary occurrence')
    need(event['projected_main_length_m'] == spatial['receiver_projected_after_m'],
         'Decoded stock accounting differs from the geometry admission')

