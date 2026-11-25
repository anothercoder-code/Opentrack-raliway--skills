"""Verify saved formation events around endpoint and reviewed split-berth edits."""

from collections import defaultdict
from functools import cache
import math

from . import catalogs, course_factories, writer
from .catalog_batch_reuse.course_batch import course_record
from .consist_workflow.core import summary
from .course_formation_rebind import ExistingFormationMove, verify_formation_moves
from .graph_references import incoming_counts
from .multi_document.core import ident, need, ref
from .native_station_rebind import grouped_rows
from .network_composition_plan import itinerary_routes
from .network_operating_plan import _projected_turnrounds, resolve_visit_stop, route_trace
from .operating_plan_edit import text
from .saved_platform_resize import OPERATING_FILES
from .shunting_workflow.core import plan_connections
from .station_reference_connections import _closure
from .zero_operations.speed_preferences import index_for_course


def _formation_archives(state):
    return {role: state['files'][state['roles'][role]] for role in OPERATING_FILES}


def _stock_archives(raw):
    def load(role):
        return writer.load_next_compatible(raw[role])[0]
    courses = {row['course_id']: row for row in map(course_record, catalogs.course_items(load('courses')))}
    trains = {text(obj, 0): obj for obj in catalogs.train_items(load('trains'))}
    depot = {text(obj, 1): obj for obj in catalogs.engine_items(load('depot'))}
    return courses, trains, depot


def _formation_changes(projected, groups, vehicle):
    changes = defaultdict(dict)
    for event in projected['events']:
        changes[event['main_course']][event['main_visit_index']] = event
    result = {}
    for cid, events in changes.items():
        length = vehicle(cid)['length_m']
        visits = []
        for index in range(len(groups[cid])):
            event = events.get(index)
            outgoing = length
            if event is not None:
                need(length == event['initial_main']['length_m'], 'Native formation state differs at the reviewed visit')
                outgoing = event['projected_main_length_m']
            visits.append((length, outgoing))
            length = outgoing
        result[cid] = visits
    return result


def _physical_head(trace, index, arrive, depart, cid):
    visit = trace['visits'][index]
    point = resolve_visit_stop(visit, arrive)
    need(point is not None and point['head_edge_offset_m'] is not None
         and point['available_length_m'] >= max(arrive, depart)
         and point['head_edge_offset_m'] >= max(arrive, depart),
         f'Current formation does not fit one directed Edge behind the booked stop for {cid}#{index}')
    return {key: point[key] for key in ('end_key', 'signal_id', 'stop_edge_key', 'head_edge_offset_m', 'available_length_m')}


def _keep_heads(receipt, event, trace, groups, lengths, vehicle):
    """Native event geometry is unchanged even when path-relative chainage is revised."""
    need(receipt['before'] == receipt['after'] and receipt['before_itinerary_groups'] == receipt['after_itinerary_groups'],
         f'Endpoint relocation would move the saved {event.kind} berth or occupied approach')
    main, partner, index = event.main_course, event.other_course, event.main_visit_index
    arrive, depart = lengths[main][index]
    comparisons = [(main, index, arrive, depart)]
    if event.kind == 'join':
        mass_length = vehicle(partner)['length_m']
        comparisons.append((partner, len(groups[partner]) - 1, mass_length, mass_length))
    heads = {}
    for cid, index, arrival, departure in comparisons:
        before, after = [_physical_head(trace(cid, revised)[0], index, arrival, departure, cid)
                         for revised in (False, True)]
        need(before == after, f'Endpoint relocation would move the actual formation stopping point for {cid}#{index}')
        heads[cid] = after
    return {**receipt, 'unchanged_physical_heads': heads}


def _event_identity(event):
    return event.main_course, event.main_visit_index, event.other_course


def _read_formation_events(reviews):
    events, relocations = [], {}
    for row in reviews:
        if isinstance(row, ExistingFormationMove):
            events.append(row)
            continue
        fields = dict(row)
        requested = {kind: fields.pop(f'{kind}_berth_relocation', None) for kind in ('split', 'join')}
        event = ExistingFormationMove.model_validate(fields)
        events.append(event)
        if all(item is None for item in requested.values()):
            continue
        key = _event_identity(event)
        relocation = requested[event.kind]
        need(relocation is not None and sum(item is not None for item in requested.values()) == 1
             and key not in relocations, 'Only a distinct matching formation event can move a reviewed berth')
        before, after = (relocation[side] for side in ('expected_head', 'replacement_head'))
        need(before['document'] == after['document'] and before['signal_id'] == after['signal_id']
             and before['end_id'] != after['end_id'],
             'A formation berth migration must retain the native main signal on a different End in the same worksheet')
        relocations[key] = {'kind': event.kind, 'before': before, 'after': after}
    return events, relocations


def _native_berth_request(head):
    document = head['document']
    return {'station_end': {'document': document, 'end_id': head['end_id']}, 'signal_id': head['signal_id'],
            'head': {'document': document, 'edge_id': head['edge_id'], 'offset_m': head['edge_offset_m']},
            'platform_edges': [{'document': document, 'edge_id': edge} for edge in head['platform_edge_ids']]}


def _saved_multiedge_berth(event, trace, lengths):
    main, index, _ = _event_identity(event)
    arrive, depart = lengths[main][index]
    visit = trace(main, False)[0]['visits'][index]
    point = resolve_visit_stop(visit, arrive)
    if point is None or point['head_edge_offset_m'] is None or point['head_edge_offset_m'] >= max(arrive, depart):
        return None
    document, end = visit['end_key']
    edges = visit.get('stopping_area_edge_keys', [])
    need(1 < len(edges) <= 100 and all(sheet == document for sheet, _ in edges)
         and point['stop_edge_key'] == edges[-1] and point['available_length_m'] >= max(arrive, depart),
         'An existing multi-Edge formation requires one complete same-sheet native berth')
    return _native_berth_request({'document': document, 'end_id': end, 'signal_id': point['signal_id'],
        'edge_id': point['stop_edge_key'][1], 'edge_offset_m': point['head_edge_offset_m'],
        'platform_edge_ids': [edge for _, edge in edges]})


def _saved_berth_track(project, movement, index):
    visit = movement['visits'][index]
    edges = visit['stopping_area_edge_keys']
    nodes, distances = movement['_directed_nodes'], movement['_node_distances_m']
    end = nodes.index(visit['end_key'])
    track = []
    for i, edge in enumerate(edges, end - len(edges)):
        start, finish = nodes[i:i + 2]
        protections = [project.model(key).contents[7].value for key in (project.actual_related(start), finish)]
        track.append({'edge': edge, 'start': start, 'end': finish, 'length_m': distances[i + 1] - distances[i],
                      'safety_elements': [None if item is None else project.key(item) for item in protections]})
    return track


def _retained_berth_snapshot(project, spatial, event, movement, itinerary):
    native = spatial[f'native_{event.kind}_berth']
    point = {key: val for key, val in native.items() if key != 'head_distance_m'}
    if event.kind == 'split':
        original = point['native_birth']
        routes = list(itinerary_routes(project, itinerary))
        arrival = routes[original['matched_predecessor_route_index']]
        point['parent_arrival_route'] = {'document': project.owners[id(arrival)][0], **ref(arrival)}
        point['native_birth'] = {key: val for key, val in original.items()
                                 if key not in ('arrival_head_distance_m', 'matched_predecessor_route_index',
                                                'arrival_approach')}
        point['native_birth']['arrival_edge_offset_m'] = original['arrival_approach']['offset_m']
    else:
        need(point['donor_nominal_head_distance_m'] - point['donor_contact_distance_m'] == spatial['receiver_before_m'],
             'The existing join must keep contact at the actual receiver tail')
        del point['donor_nominal_head_distance_m'], point['donor_contact_distance_m']
    return {**point, 'directed_platform': _saved_berth_track(project, movement, event.main_visit_index)}


def _keep_multiedge_berth(receipt, event, projects, destinations, trace):
    native_field = f'native_{event.kind}_berth'
    scopes = [{key: val for key, val in receipt[side].items() if key != native_field} for side in ('before', 'after')]
    need(scopes[0] == scopes[1] and receipt['before_itinerary_groups'] == receipt['after_itinerary_groups'],
         f'An unselected {event.kind} berth or occupied approach changed during endpoint relocation')
    witnesses = []
    for revised, side in enumerate(('before', 'after')):
        movement, = trace(event.main_course, bool(revised))
        witnesses.append(_retained_berth_snapshot(projects[revised], receipt[side], event, movement,
                                                  destinations[revised][movement['itinerary_name']]))
    need(witnesses[0] == witnesses[1],
         f'An unselected {event.kind} berth changed its physical position, directed track or protection')
    return {**receipt, 'retained_berth': witnesses[0]}


def _verify_join_contact(witnesses, relocation):
    before, after = (witnesses[side] for side in ('before', 'after'))
    saved_edges, target_edges = (relocation[side]['platform_edge_ids'] for side in ('before', 'after'))
    shared = min(len(saved_edges), len(target_edges))
    need(shared > 0 and saved_edges[:shared] == target_edges[:shared],
         'A moved join berth must follow the same directed platform from its unchanged beginning')
    for key in ('arrival_route', 'occupied_entry', 'contact_safety_elements'):
        need(before[key] == after[key], 'A moved join berth changed its occupied-entry Route, signal or protection')
    old, revised = before['contact'], after['contact']
    shift = after['available_length_m'] - before['available_length_m']
    need(shift != 0 and (old['document'], old['edge_id']) == (revised['document'], revised['edge_id'])
         and math.isclose(revised['offset_m'] - old['offset_m'], shift, rel_tol=0, abs_tol=1e-7),
         'The reviewed join contact must move by the berth shift on the same physical Edge')


def _moved_formation_berth(receipt, event, trace, lengths, relocation):
    main, index, partner = _event_identity(event)
    arrive, depart = lengths[main][index]
    scopes = ('native_occupied_entry', 'receiver_before_m', 'secondary_length_m',
              'receiver_projected_after_m', 'receiver_visit_index')
    need(all(receipt['before'][key] == receipt['after'][key] for key in scopes),
         f'Moving the {event.kind} berth changed an unrelated formation condition')
    witnesses = {}
    for side, revised in (('before', False), ('after', True)):
        expected = relocation[side]
        native = receipt[side][f'native_{event.kind}_berth']
        visit = trace(main, revised)[0]['visits'][index]
        point = resolve_visit_stop(visit, arrive)
        document = expected['document']
        need(point is not None and native['available_length_m'] == expected['available_length_m']
             and native['head_distance_m'] == point['distance_m']
             and point['end_key'] == (document, expected['end_id'])
             and point['signal_id'] == expected['signal_id']
             and point['stop_edge_key'] == (document, expected['edge_id'])
             and point['head_edge_offset_m'] == expected['edge_offset_m'],
             f'Saved head position or available platform length differs for {main}#{index} ({side})')
        if event.kind == 'split':
            stock = {'retained_length_m': depart, 'split_child_course_id': partner,
                     'split_child_length_m': arrive - depart}
        else:
            stock = {'joined_length_m': depart, 'supplying_course_id': partner,
                     'supplying_length_m': depart - arrive}
        witnesses[side] = {**native, 'arrival_length_m': arrive, **stock}
    if event.kind == 'join':
        _verify_join_contact(witnesses, relocation)
    return {**receipt, f'{event.kind}_berth_relocation': witnesses}, {'kind': event.kind, **witnesses}


def review_endpoint_formations(state, before, after, active_endpoint_courses, reviews):
    """Verify exact saved split/join rows for the affected connected Course chain."""
    empty = {'course_ids': set(), 'connection_rows': set(), 'formation_by_visit': {}, 'split_origins': set(),
             'berth_relocations': {}, 'verified_berth_indices': {'split': set(), 'join': set()},
             'receipts': [], 'projected_composition': {'events': []}}
    if not reviews:
        return empty
    events, relocations = _read_formation_events(reviews)
    need(all(event.target_station_sign in (None, event.station_sign) and event.occupied_entry == 'use_target'
             for event in events), 'Endpoint formation review requires the original station and occupied-entry settings')
    raw = _formation_archives(state)
    timetable, _ = writer.load_next_compatible(raw['timetable'])
    groups = grouped_rows(course_factories.timetable(timetable))
    closure = list(_closure(groups, active_endpoint_courses))
    linked_ids = {data[key] for _, _, _, _, data in closure for key in ('course_id', 'target_course_id')}
    participants = {cid for event in events for cid in (event.main_course, event.other_course)}
    need(participants <= linked_ids, 'Every formation participant must be in the affected saved Connection6 chain')
    courses, trains, depot = _stock_archives(raw)
    need(participants <= courses.keys() and all(courses[cid]['enabled'] and len(courses[cid]['itineraries']) == 1
         and courses[cid]['spacing_mode_code'] == 0 and courses[cid]['train'] in trains for cid in participants),
         'A reviewed formation Course requires one enabled fixed-block Itinerary and a saved Train')
    destinations = [{ident(obj)[0]: obj for obj in project.dests} for project in (before, after)]

    @cache
    def vehicle(cid):
        return summary(trains[courses[cid]['train']], depot)

    @cache
    def trace(cid, revised):
        name, = courses[cid]['itineraries']
        need(name in destinations[revised], 'Reviewed formation Course has no matching saved Itinerary')
        project = (before, after)[revised]
        category = str(index_for_course(state['run'], courses[cid]['speed_type']))
        return [{'itinerary_name': name,
                 **route_trace(project, destinations[revised][name], category, vehicle(cid)['maximum_speed_kmh'])}]

    operations = [event.model_dump(exclude={'occupied_entry', 'target_station_sign'}) for event in events]
    archived, projected = plan_connections(raw, {
        'schema': 'split-join-timetable-plan/1', 'operations': operations,
        'accept_unverified_spatial_and_dynamic_execution': True,
    }, child_before_main=False, sequential_main=True, verify_existing=True)
    need(archived == raw['timetable'], 'Endpoint review must keep the original timetable archive')
    lengths = _formation_changes(projected, groups, vehicle)
    berth_reviews, retained = defaultdict(dict), set()
    for event in events:
        key = _event_identity(event)
        if key in relocations:
            declaration = {side: _native_berth_request(relocations[key][side]) for side in ('before', 'after')}
        else:
            snapshot = _saved_multiedge_berth(event, trace, lengths)
            if snapshot is None:
                continue
            declaration = {'before': snapshot, 'after': snapshot}
            retained.add(key)
        berth_reviews[f'{event.kind}_berth_reviews'][key] = declaration
    receipts, verified = verify_formation_moves(
        before, after, events, state, groups, trace, vehicle, {}, linked_ids, **berth_reviews)
    counts = incoming_counts(timetable)
    consumed, connection_rows = set(), set()
    for cid, row, ordinal, obj, data in closure:
        index = row.contents[3].value
        key = (cid, index, data['target_course_id'])
        if key in verified:
            need(key not in consumed and counts[id(obj)] == 1, 'A reviewed formation row must own one native Connection6')
            consumed.add(key)
            connection_rows.add((cid, index, ordinal))
            continue
        formation_change = bool(data['flags'] & 1 or data['flags'] & 2 and 0 < index < len(groups[cid]) - 1)
        need(not formation_change, 'Review the whole affected native split/join chain exactly once')
    need(consumed == verified, 'Every reviewed formation row must resolve to its exact native connection slot')

    by_event = {(row['main_row'], row['other_course']): row for row in receipts}
    reviewed = [(f'{event.main_course}#{event.main_visit_index}', event.other_course) for event in events]
    need(set(reviewed) == by_event.keys(), 'Native formation reports differ from the approved Course rows')
    preserved, moved_berths = [], {}
    verified_berths = {'split': set(), 'join': set()}
    for key, event in zip(reviewed, events, strict=True):
        identity = _event_identity(event)
        receipt = by_event[key]
        if identity in relocations:
            row, witnesses = _moved_formation_berth(receipt, event, trace, lengths, relocations[identity])
            moved_berths[identity[:2]] = witnesses
            verified_berths[event.kind].add(identity[:2])
        elif identity in retained:
            row = _keep_multiedge_berth(receipt, event, (before, after), destinations, trace)
            verified_berths[event.kind].add(identity[:2])
        else:
            row = _keep_heads(receipt, event, trace, groups, lengths, vehicle)
        preserved.append(row)
    return {'course_ids': participants, 'connection_rows': connection_rows, 'formation_by_visit': lengths,
            'split_origins': {event.other_course for event in events if event.kind == 'split'},
            'berth_relocations': moved_berths, 'verified_berth_indices': verified_berths,
            'receipts': preserved, 'projected_composition': projected}


def endpoint_formation_turnrounds(state, formation, endpoint_link_reviews):
    """Require a terminal successor to declare the exact ordered current stock."""
    if not formation['receipts'] or not endpoint_link_reviews:
        return {}
    courses, trains, depot = _stock_archives(_formation_archives(state))
    need(all(review[side] in courses and courses[review[side]]['train'] in trains for review in endpoint_link_reviews
             for side in ('from_course', 'to_course')), 'Reviewed formation transfer requires two exact saved Trains')
    return _projected_turnrounds(endpoint_link_reviews, formation['projected_composition'], courses, trains, depot)
