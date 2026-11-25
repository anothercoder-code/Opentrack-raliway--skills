"""Preserve a reviewed occupied-entry permission and berth in a native Route split."""

from math import isfinite

from . import catalogs, course_factories, writer
from .catalog_batch_reuse.course_batch import course_record
from .multi_document.core import ident, need
from .native_station_rebind import grouped_rows
from .network_composition_plan import itinerary_routes, verify_join_berth_geometry
from .network_operating_plan import route_trace
from .operating_plan_edit import text
from .saved_document_insertion import _occupied_signal, _occupied_stop
from .saved_terminal_overlap import _edge_locking_resources
from .shunting_workflow.core import plan_connections
from .zero_operations.speed_preferences import index_for_course


ORDINARY_ENTRY = (0, 40.0, 0.0)


def occupied_entry_values(review):
    speed, wait = review.get('expected_speed_kmh'), review.get('expected_wait_s')
    need((speed is None) != (wait is None), 'Review exactly one occupied-entry speed or zero-speed wait')
    if wait is not None:
        need(type(wait) is int and 0 < wait <= 86400, 'Review the native positive whole-second occupied-entry wait')
        return (7, 0.0, float(wait))
    need(type(speed) in (int, float) and isfinite(speed) and 0 < speed <= 1000,
         'Review the finite native occupied-entry speed')
    return (3, speed, 0.0)


def _join_event(banks, review):
    participants = review['receiver_course'], review['donor_course']
    need(participants[0] != participants[1], 'Select two distinct occupied-entry Courses')
    saved, receipt = plan_connections(banks, {
        'schema': 'split-join-timetable-plan/1', 'accept_unverified_spatial_and_dynamic_execution': True,
        'operations': [{'kind': 'join', 'main_course': participants[0], 'other_course': participants[1],
                        'station_sign': review['station_sign']}],
    }, verify_existing=True, sequential_main=True)
    event, = receipt['events']
    need(saved == banks['timetable'] and event['main_arrival_s'] < event['other_event_s'],
         'Occupied-entry migration requires a verified receiver booked to arrive before its donor')
    table, _ = writer.load_next_compatible(saved)
    rows = grouped_rows(course_factories.timetable(table))
    for course in participants:
        need(sum(len(catalogs.array(row.contents[9].value)) for row in rows[course]) == 1,
             'Each reviewed Course must have only its one reciprocal join, with no other formation or stock continuation')
    return event, rows


def _linked_join_event(project, banks, run_bytes, review):
    """Audit the whole saved split, stock continuation and occupied join as one chain."""
    from .station_reference_connections import review_saved_turnrounds, verify_turnround_geometry
    from .station_reference_formation import endpoint_formation_turnrounds, review_endpoint_formations
    from .station_reference_operating import _operating_for_links, _resolved_courses

    events, turnrounds = review.get('formation_events'), review.get('turnrounds')
    need(type(events) is list and len(events) == 2 and type(turnrounds) is list and len(turnrounds) == 1,
         'Review one preceding split, one occupied join and their original reciprocal stock continuation')
    preceding, joining = events
    transfer, = turnrounds
    receiver, donor = review['receiver_course'], review['donor_course']
    parent = preceding['main_course']
    need(len({receiver, donor, parent}) == 3 and preceding['kind'] == 'split'
         and preceding['other_course'] == donor
         and (joining['kind'], joining['main_course'], joining['other_course'], joining['station_sign']) ==
             ('join', receiver, donor, review['station_sign'])
         and transfer == {'from_course': parent, 'to_course': receiver, 'movement': 'continue'},
         'The reviewed source must split into the original donor and same-direction continuing receiver of this join')
    state = {'files': banks, 'roles': {key: key for key in banks}, 'run': run_bytes}
    participants = {receiver, donor}
    formation = review_endpoint_formations(state, project, project, participants, events)
    projected = endpoint_formation_turnrounds(state, formation, turnrounds)
    need(projected.keys() == {(parent, receiver)},
         'The receiver must inherit the exact current parent formation after the reviewed split')
    links = review_saved_turnrounds(banks, participants, turnrounds, formation_rows=formation['connection_rows'],
                                    projected_transfers=projected)
    saved_link, = links
    operating, stations, bounds = _operating_for_links(banks, run_bytes, set(), links, formation=formation)
    context, _ = _resolved_courses(project, operating, stations, bounds, formation)
    physical_link, = verify_turnround_geometry(links, project, project, context, context)
    split, event = formation['projected_composition']['events']
    retained = projected[parent, receiver]
    need(split['main_departure_s'] < saved_link['planned_arrival_s'] < saved_link['planned_departure_s']
         < event['main_arrival_s'] < event['other_event_s']
         and split['other_event_s'] < event['other_event_s'],
         'The split and saved continuation must precede both join arrivals on the absolute timetable')
    need(split['initial_other'] == event['initial_other']
         and split['projected_main_length_m'] == retained['projected_length_m'] == event['initial_main']['length_m'],
         'The occupied join must use the actual retained and detached stock from the preceding split')
    root, _ = writer.load_next_compatible(banks['timetable'])
    rows = grouped_rows(course_factories.timetable(root))
    return event, rows, {
        'preceding_split': {
            'main_row': split['main_row'], 'child_row': split['other_row'],
            'station_sign': split['station_sign'], 'arrival_length_m': split['initial_main']['length_m'],
            'detached_length_m': split['initial_other']['length_m'], 'retained_length_m': split['projected_main_length_m'],
        },
        'stock_continuation': physical_link,
        'formation_connection_rows': sorted(formation['connection_rows']),
        'reviewed_join_rows': [event['main_row'], event['other_row']],
        'timetable_sha256': saved_link['timetable_sha256'],
    }


def _operating_visits(project, route, banks, run_bytes, event, rows):
    root, _ = writer.load_next_compatible(banks['courses'])
    courses = [course_record(obj) for obj in catalogs.course_items(root)]
    itineraries = {ident(obj)[0]: obj for obj in project.dests}
    receiver, donor = event['main_course'], event['other_course']
    participants = {receiver: event['initial_main'], donor: event['initial_other']}
    movements = {}
    users = set()
    for course in courses:
        if not course['enabled']:
            continue
        cid, choices = course['course_id'], course['itineraries']
        need(all(name in itineraries for name in choices), 'Enabled Course refers to an unknown saved Itinerary')
        uses = [name for name in choices if any(r is route for r in itinerary_routes(project, itineraries[name]))]
        if uses:
            users.add(cid)
        if cid not in participants:
            continue
        need(course['spacing_mode_code'] == 0 and len(choices) == 1 and uses == choices
             and sum(r is route for r in itinerary_routes(project, itineraries[uses[0]])) == 1,
             'The reviewed fixed-block Courses must each use the common arrival Route once on one native Itinerary')
        label, = choices
        stock = participants[cid]
        category = str(index_for_course(run_bytes, course['speed_type']))
        trace = route_trace(project, itineraries[label], category, stock['maximum_speed_kmh'])
        visits = trace['visits']
        need([visit['station_sign'] for visit in visits] == [text(row, 5) for row in rows[cid]],
             'The planned occupied-entry visits differ from the direction and order of the native Itinerary')
        movements[cid] = {
            'itinerary': label, 'consist_length_m': stock['length_m'], '_formation_trace': trace,
            'visits': [{**visit, 'planned': {'stop': bool(row.contents[10].value & 1)}}
                       for visit, row in zip(visits, rows[cid], strict=True)],
        }
    need(users == participants.keys() and movements.keys() == participants.keys(),
         'The occupied-entry Route must only be used by the two reviewed enabled Courses')
    return movements[receiver], movements[donor], itineraries


def verify_occupied_signal_split(project, arrival, sequence, split, review, banks, run_bytes):
    """Bind one saved join to the exact receiving berth and disjoint directed resources."""
    need(type(banks) is dict and type(run_bytes) is bytes,
         'Occupied entry requires the five SHA-bound operating catalogues and Project .run')
    values = occupied_entry_values(review)
    need(tuple(arrival.contents[6].values) == values,
         'The occupied-entry Route does not have the reviewed native speed or stop-and-wait setting')
    entry, flags = _occupied_signal(project, project.owners[id(arrival)])
    need(flags & 1, 'The original entry Signal must allow occupied entry')
    terminal, stop_edge = _occupied_stop(project, arrival, review)
    index = sequence.index(split)
    edges = [project.edge_between(a, b) for a, b in zip(sequence, sequence[1:])]
    need(0 < index < len(edges) and stop_edge == edges[-1] and stop_edge in edges[index:],
         'The reviewed stopping Edge must remain entirely after the new Signal')
    upstream, upstream_exclusions = _edge_locking_resources(project, edges[:index])
    downstream, downstream_exclusions = _edge_locking_resources(project, edges[index:])
    need(not (upstream | upstream_exclusions) & (downstream | downstream_exclusions),
         'The occupied-entry prefix and suffix share a Safety Element or Edge exclusion')

    chain = None
    if review.get('formation_events') is not None or review.get('turnrounds') is not None:
        event, rows, chain = _linked_join_event(project, banks, run_bytes, review)
    else:
        event, rows = _join_event(banks, review)
    receiver, donor, itineraries = _operating_visits(project, arrival, banks, run_bytes, event, rows)
    edge_length = project.model(stop_edge).contents[9].values[1]
    signal = project.model(terminal).contents[11].value
    berth = {
        'station_end': review['terminal_end'], 'signal_id': signal.contents[0].value,
        'platform_edges': [{'document': stop_edge[0], 'edge_id': stop_edge[1]}],
        'head': {'document': stop_edge[0], 'edge_id': stop_edge[1], 'offset_m': edge_length},
    }
    geometry = verify_join_berth_geometry(project, event, receiver, donor, itineraries, berth,
        arrival_length_m=event['initial_main']['length_m'], joined_length_m=event['projected_main_length_m'])
    need(geometry['donor_tail']['offset_m'] > 0
         and all(key == {'document': stop_edge[0], 'element_id': review['expected_safety_element_id']}
                 for key in geometry['contact_safety_elements']),
         'Both complete formations and the reviewed common occupied Safety Element must fit after the cutting signal')
    return {
        'values': list(values), 'signal_id': entry.contents[0].value, 'signal_flags': list(entry.contents[9].values),
        'berth': {key: value for key, value in geometry.items() if key not in {'occupied_entry', 'arrival_route'}},
        'receiver_course': event['main_course'], 'donor_course': event['other_course'],
        'station_sign': event['station_sign'], 'receiver_length_m': event['initial_main']['length_m'],
        'donor_length_m': event['initial_other']['length_m'], 'combined_length_m': event['projected_main_length_m'],
        **({'preceding_formation_chain': chain} if chain is not None else {}),
    }
