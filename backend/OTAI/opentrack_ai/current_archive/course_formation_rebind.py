"""Revalidate existing native formation events and migrate their occupied-entry settings."""

from bisect import bisect_right
from collections import defaultdict
from math import isfinite
from typing import Annotated, Literal

from pydantic import Field

from . import catalogs, native_connections, writer
from .multi_document.core import ident
from .network_composition_plan import (
    _admit_spatial_event, _arrival_route, _check_receiver_clearance, _entry_signal, _station_location,
    itinerary_routes, occupied_entry_route_parts, verify_event_geometry, verify_join_berth_geometry,
    verify_split_berth_geometry,
)
from .network_operating_plan import route_trace
from .operating_plan_edit import need, text, timetable_time
from .operating_plan_edit_tools import Id, Index
from .route_edit_tools import _route_shape
from .saved_geometry import project_from
from .shunting_workflow.core import plan_connections
from .tools import Input


class ExistingFormationMove(Input):
    kind: Literal['split', 'join']
    main_course: Id
    other_course: Id
    station_sign: Id
    target_station_sign: Id | None = None
    main_visit_index: Annotated[Index, Field(gt=0)]
    occupied_entry: Literal['use_target', 'copy_previous'] = 'use_target'


def _settings(project, route):
    _route_shape(route)
    _, signal = _entry_signal(project, route)
    flags, speed, wait = route.contents[6].values
    need(type(flags) is int and 0 <= flags <= 15, 'Unknown occupied-entry flags')
    need(all(isfinite(value) and value >= 0 for value in (speed, wait)),
         'Occupied-entry speed and wait must be finite and nonnegative')
    return signal, flags, speed, wait


def _selected_arrivals(project, itineraries, choices, event, station):
    course = event.other_course
    need(course in choices and choices[course], 'A supplying Course needs a saved Itinerary')
    routes = {}
    for name in choices[course]:
        itinerary = itineraries[name]
        terminal = route_trace(project, itinerary)['visits'][-1]
        need(terminal['station_sign'] == station,
             'The supplying Course terminal does not match the reviewed join station')
        route = _arrival_route(project, itinerary, terminal['end_key'])
        routes[id(route)] = route
    return list(routes.values())


def prepare_join_permissions(state, project, requests, events):
    copies = [event for event in events if event.occupied_entry == 'copy_previous']
    if not copies:
        return state, project, []
    need(all(event.kind == 'join' for event in copies), 'Only a join has an occupied-entry approach')
    run_courses = state['files'][state['roles']['courses']]
    root = writer.load_next_compatible(run_courses)[0]
    choices = {text(course, 0): [catalogs.text(item) for item in catalogs.array(course.contents[2].value)]
               for course in catalogs.course_items(root)}
    selected = {item.course_id: item.itineraries for item in requests}
    planned = {**choices, **selected}
    destinations = {ident(item)[0]: item for item in project.dests}
    users = defaultdict(set)
    for cid, names in planned.items():
        for name in names:
            for route in itinerary_routes(project, destinations[name]):
                users[route].add(cid)
    changes = defaultdict(dict)
    receipt = []

    def add_update(owner, group, values):
        prior = changes[owner[0]].get(id(group))
        need(prior is None or prior[2] == values, 'Reviewed joins require contradictory approach settings')
        changes[owner[0]][id(group)] = group, list(group.values), values

    for event in copies:
        previous = _selected_arrivals(project, destinations, choices, event, event.station_sign)
        targets = _selected_arrivals(project, destinations, planned, event, event.target_station_sign or event.station_sign)
        old_options = set()
        for route in previous:
            old_signal, flags, speed, wait = _settings(project, route)
            need(flags & 1 and old_signal.contents[9].values[2] & 1,
                 'Every original supplying Route and entry signal must authorize occupied entry')
            old_options.add((flags & 7, speed, wait))
        need(len(old_options) == 1, 'Original approaches have different occupied-entry settings; review each target')
        (flags, speed, wait), = old_options
        for target in targets:
            signal, _, _, _ = _settings(project, target)
            owners_and_settings = []
            for owner, part in occupied_entry_route_parts(project, target):
                group = part.contents[6]
                stored = group.values[0]
                need(type(stored) is int and 0 <= stored <= 15, 'Unknown occupied-entry flags')
                owners_and_settings.append((owner, group, [(stored & ~7) | flags, speed, wait]))
            for part_owner, group, values in owners_and_settings:
                add_update(part_owner, group, values)
            signal_group = signal.contents[9]
            enable_signal = not signal_group.values[2] & 1
            if not enable_signal and all(group.values == values for _, group, values in owners_and_settings):
                continue
            need(users[target] <= selected.keys(),
                 'The target occupied-entry Route also serves an unselected Course')
            owner = project.owners[id(target)]
            if enable_signal:
                need(all(used <= selected.keys() for route, used in users.items()
                         if project.owners[id(route)] == owner and route.contents[6].values[0] & 1),
                     'Enabling the entry signal affects another booked Route')
                original = list(signal_group.values)
                original[2] |= 1
                add_update(owner, signal_group, original)
            receipt.append({'other_course': event.other_course, 'station_sign': event.station_sign,
                            'old_route': ident(previous[0]), 'old_routes': [ident(route) for route in previous],
                            'new_route': ident(target), 'new_route_owner': owner,
                            'route_fragment_owners': [part_owner for part_owner, _, _ in owners_and_settings],
                            'new_entry_signal_id': signal.contents[0].value, 'occupied_entry_speed_kmh': speed,
                            'occupied_entry_wait_s': wait, 'use_speed': bool(flags & 2), 'use_time': bool(flags & 4)})

    documents, files = dict(state['documents']), dict(state['files'])
    for sheet, worksheet_edits in changes.items():
        relevant = [change for change in worksheet_edits.values() if change[1] != change[2]]
        if not relevant:
            continue
        root = project.roots[sheet]
        before = writer.fingerprint(root)
        try:
            for group, _, values in relevant:
                group.values[:] = values
            documents[sheet] = writer.dump_verified(root, project.versions[sheet])
        finally:
            for group, original, _ in relevant:
                group.values[:] = original
        need(writer.fingerprint(root) == before, 'Occupied-entry migration touched unrelated worksheet fields')
        files[state['document_members'][sheet]] = documents[sheet]
    updated = {**state, 'documents': documents, 'files': files}
    fresh = project_from(documents, state['document_paths'], files[state['roles']['dest']])
    for row in receipt:
        primary = fresh.owned(row['new_route_owner'], 'OTRoute', row['new_route'])
        signal, flags, speed, wait = _settings(fresh, primary)
        need(signal.contents[0].value == row['new_entry_signal_id'] and signal.contents[9].values[2] & 1,
             'Occupied-entry signal authorization differs after cold read')
        expected_flags = 1 | (2 if row['use_speed'] else 0) | (4 if row['use_time'] else 0)
        expected = (expected_flags, row['occupied_entry_speed_kmh'], row['occupied_entry_wait_s'])
        need((flags & 7, speed, wait) == expected, 'Occupied-entry primary settings differ after cold read')
        for _, part in occupied_entry_route_parts(fresh, primary):
            fragment_flags, fragment_speed, fragment_wait = part.contents[6].values
            need((fragment_flags & 7, fragment_speed, fragment_wait) == expected,
                 'Occupied-entry continuation settings differ after cold read')
    return updated, fresh, receipt


def _reports(events, groups, trace_for, vehicle, planned_tracks, revised):
    names = {cid for event in events for cid in (event.main_course, event.other_course)}
    result = {}
    for cid in sorted(names):
        options = trace_for(cid, revised)
        stock = vehicle(cid)
        result[cid] = []
        for trace in options:
            locations = []
            for i, (loc, row) in enumerate(zip(trace['visits'], groups[cid], strict=True)):
                sign = text(row, 5)
                need(loc['station_sign'] == sign, 'Formation rebind must retain the booked station visits')
                planned = {'station_sign': sign, 'stop': bool(row.contents[10].value & 1),
                           'arrival_s': timetable_time(row, 'arrival'), 'departure_s': timetable_time(row, 'departure'),
                           'track_id': planned_tracks.get((cid, i), text(row, 18)) if revised else text(row, 18)}
                locations.append({**loc, 'planned': planned})
            result[cid].append({'itinerary': trace['itinerary_name'], 'visits': locations, '_formation_trace': trace,
                                'consist_length_m': stock['length_m'], 'maximum_speed_kmh': stock['maximum_speed_kmh']})
    return result


def _by_event_end(variants, sign, index=None):
    positions = defaultdict(list)
    for variant in variants:
        _, visit = _station_location(variant, sign, index)
        positions[visit['end_key']].append(variant)
    return positions


def _validate_split_selector(project, itineraries, sign, visit_index, main_groups, child_groups):
    # At a stop on the Route boundary, routeBeforeSimPos returns the
    # arriving Route. The original searches it first (620454, 64ca98).
    child_origins = set(child_groups)
    for end, variants in main_groups.items():
        for variant in variants:
            _, visit = _station_location(variant, sign, visit_index)
            stop = visit.get('head_stop') or visit.get('default_stop')
            need(stop is None or stop['end_key'] == end,
                 'Multiple split platforms require the actual stop at the directed station boundary')
            route_ends = [project.route_view(route)
                          for route in itinerary_routes(project, itineraries[variant['itinerary']])]
            arrivals = [index for index, nodes in enumerate(route_ends) if nodes[-1] == end]
            need(len(arrivals) == 1 and arrivals[0] + 1 < len(route_ends)
                 and route_ends[arrivals[0] + 1][0] == end,
                 'Multiple split platforms require an exact arrival and departure Route boundary')
            arrival = set(route_ends[arrivals[0]])
            candidates = arrival | {project.actual_related(node) for node in arrival}
            need(candidates & child_origins == {end},
                 'A split alternative must identify exactly its matching child origin on the parent Routes')


def _validate_join_selector(project, itineraries, sign, visit_index, groups):
    # Native join preannouncement resolves an End, then actualRelated, in
    # each destination's ordered Routes (64bf60, 476cec). The platform
    # branch must remain available until that choice becomes obligatory.
    choices = []
    ends_by_platform = {end: (end, project.actual_related(end)) for end in groups}
    for end, variants in groups.items():
        for variant in variants:
            _, visit = _station_location(variant, sign, visit_index)
            stop = visit.get('head_stop') or visit.get('default_stop')
            need(stop is None or stop['end_key'] == end,
                 'A multiple-platform join must stop at its directed station reference')
            label = variant['itinerary']
            routes = list(itinerary_routes(project, itineraries[label]))
            nodes = [tuple(project.route_view(route)) for route in routes]
            arrivals = [i for i, route_nodes in enumerate(nodes) if route_nodes[-1] == end]
            need(len(arrivals) == 1, 'Every join option needs one exact arrival Route at its platform')
            index, = arrivals
            need((visit_index is None and index == len(routes) - 1)
                 or (visit_index is not None and index + 1 < len(routes) and nodes[index + 1][0] == end),
                 'A multiple-platform join needs a terminal supplying Route and a receiver Route boundary')
            for platform, (announced, related) in ends_by_platform.items():
                first = next((i for i, route_nodes in enumerate(nodes) if announced in route_nodes), None)
                if first is None:
                    first = next((i for i, route_nodes in enumerate(nodes) if related in route_nodes), None)
                need(first == (index if platform == end else None),
                     'A join option must match just its own platform in the original preannouncement search')
            starts = [route_nodes[0] for route_nodes in nodes]
            positions = defaultdict(list)
            for i, start in enumerate(starts):
                positions[start].append(i)
            choices.append((end, starts, positions, index))
    need(len({starts[index] for _, starts, _, index in choices}) == 1,
         'All join options for each Course must have one common directed platform junction')
    for origin, starts, _, incoming in choices:
        for destination, _, positions, target in choices:
            if origin == destination:
                continue
            # produceChangeLists scans source Routes in order and looks up
            # each shared first End beyond its previous destination index.
            last = -1
            match = None
            for start in starts[:incoming + 1]:
                hits = positions.get(start, ())
                at = bisect_right(hits, last)
                match = hits[at] if at < len(hits) else None
                if match is not None:
                    last = match
            need(match == target,
                 'The native route-change order must still reach every join platform at this junction')


def _validate_geometry(project, operations, report, options, itineraries, split_berth_reviews=None, join_berth_reviews=None):
    berth_reviews = {'split': split_berth_reviews or {}, 'join': join_berth_reviews or {}}
    clearance_events = defaultdict(list)
    for request, event in zip(operations, report['events'], strict=True):
        main_id, other_id = event['main_course'], event['other_course']
        sign = event['station_sign']
        berth_review = berth_reviews[event['kind']].get((main_id, event['main_visit_index'], other_id))
        main_groups = _by_event_end(options[main_id], sign, event['main_visit_index'])
        other_groups = _by_event_end(options[other_id], sign)
        need(main_groups.keys() == other_groups.keys(),
             'Every reviewed formation platform needs a matching directed Itinerary on both Courses')
        if berth_review is not None:
            need(len(options[main_id]) == len(options[other_id]) == 1,
                 'A reviewed formation berth requires one exact Itinerary per Course')
        if len(main_groups) > 1:
            if event['kind'] == 'split':
                _validate_split_selector(project, itineraries, sign, event['main_visit_index'], main_groups, other_groups)
            else:
                _validate_join_selector(project, itineraries, sign, event['main_visit_index'], main_groups)
                _validate_join_selector(project, itineraries, sign, None, other_groups)

        groups = []
        for end, mains in main_groups.items():
            others = other_groups[end]

            def check(main, other):
                reports = {main_id: main, other_id: other}
                split_berth = join_berth = None
                if berth_review is not None:
                    previous = event['initial_main']['length_m']
                    continued = event['projected_main_length_m']
                    if event['kind'] == 'split':
                        split_berth = verify_split_berth_geometry(project, event, main, other, itineraries, berth_review,
                            arrival_length_m=previous, retained_length_m=continued)
                    else:
                        join_berth = verify_join_berth_geometry(project, event, main, other, itineraries, berth_review,
                            arrival_length_m=previous, joined_length_m=continued)
                spatial = _admit_spatial_event(project, request, reports, itineraries,
                                               current_formation=event['initial_main'], split_berth=split_berth,
                                               join_berth=join_berth)
                verify_event_geometry(event, spatial)
                return spatial

            # Within a directed platform, both Courses have one timetable and
            # stock state. Check each receiver's stop and each supplying approach.
            approach_checks = []
            for main in mains:
                spatial = check(main, others[0])
                clearance_events[main_id, main['itinerary']].append({**event, 'spatial': spatial})
                if main is options[main_id][0]:
                    event['spatial'] = spatial
                if main is mains[0]:
                    approach_checks.append(spatial['native_occupied_entry'])
            for other in others[1:]:
                approach_checks.append(check(mains[0], other)['native_occupied_entry'])
            groups.append({'station_end_key': end, 'receiver_itineraries': [item['itinerary'] for item in mains],
                           'other_itineraries': [item['itinerary'] for item in others],
                           'supplying_approaches': approach_checks if event['kind'] == 'join' else []})
        event['itinerary_groups'] = groups

    clearance = defaultdict(dict)
    for cid, alternatives in options.items():
        for alternative in alternatives:
            label = alternative['itinerary']
            checks = clearance_events.get((cid, label))
            if checks:
                clearance[cid][label] = _check_receiver_clearance({cid: alternative}, checks)[cid]
    report['receiver_stopping_clearance'] = {cid: rows[options[cid][0]['itinerary']] for cid, rows in clearance.items()}
    report['receiver_stopping_clearance_by_itinerary'] = dict(clearance)


def _review_berths(reviews, events, kind):
    if reviews is None:
        return {}
    signatures = {(event.main_course, event.main_visit_index, event.other_course)
                  for event in events if event.kind == kind}
    need(type(reviews) is dict and reviews.keys() <= signatures
         and all(type(sides) is dict and sides.keys() == {'before', 'after'}
                 and all(type(side) is dict and side for side in sides.values()) for sides in reviews.values()),
         f'A {kind} berth review requires both native geometries for exactly one existing {kind} per review')
    return reviews


def verify_formation_moves(original_project, candidate_project, events, inputs, groups, trace_for,
                           vehicle, planned_tracks, selected_ids, *, candidate_timetable=None, candidate_groups=None,
                           split_berth_reviews=None, join_berth_reviews=None):
    split_berths = _review_berths(split_berth_reviews, events, 'split')
    join_berths = _review_berths(join_berth_reviews, events, 'join')
    if not events:
        return [], set()
    signatures = {(event.main_course, event.main_visit_index, event.other_course) for event in events}
    need(len(signatures) == len(events), 'Select each saved formation event once')
    need(all({event.main_course, event.other_course} & selected_ids for event in events),
         'Every reviewed formation event must involve a reselected Course')
    raw = {role: inputs['files'][inputs['roles'][role]] for role in ('courses', 'timetable', 'trains', 'depot', 'stations')}
    validation = []
    for revised, project in ((False, original_project), (True, candidate_project)):
        effective = raw if not revised or candidate_timetable is None else {**raw, 'timetable': candidate_timetable}
        rows = candidate_groups if revised and candidate_groups is not None else groups
        operations = [
            {**event.model_dump(exclude={'occupied_entry', 'target_station_sign'}),
             'station_sign': (event.target_station_sign or event.station_sign) if revised else event.station_sign}
            for event in events
        ]
        itineraries = {ident(item)[0]: item for item in project.dests}
        reports = _reports(events, rows, trace_for, vehicle, planned_tracks, revised)
        table, result = plan_connections(
            effective, {'schema': 'split-join-timetable-plan/1', 'operations': operations,
                        'accept_unverified_spatial_and_dynamic_execution': True},
            child_before_main=False, sequential_main=True, verify_existing=True)
        need(table == effective['timetable'], 'Saved Connection6 archive differs during read-only formation accounting')
        side = 'after' if revised else 'before'
        _validate_geometry(project, operations, result, reports, itineraries,
                           {signature: pair[side] for signature, pair in split_berths.items()},
                           {signature: pair[side] for signature, pair in join_berths.items()})
        validation.append(result)
    before, after = validation
    approved = set()
    receipts = []
    for prior, current in zip(before['events'], after['events'], strict=True):
        main, other = current['main_course'], current['other_course']
        visit = current['main_visit_index']
        counterpart = 0 if current['kind'] == 'split' else len(groups[other]) - 1
        approved.update(((main, visit, other), (other, counterpart, main)))
        receipts.append({
            'kind': current['kind'], 'main_course': main, 'other_course': other, 'station_sign': current['station_sign'],
            'source_station_sign': prior['station_sign'],
            'main_row': current['main_row'], 'other_row': current['other_row'],
            'before': prior['spatial'], 'after': current['spatial'], 'continued_stock_m': current['projected_main_length_m'],
            'stored_minimum_wait_s': current['minimum_wait_s'],
            'receiver_stopping_clearance': after['receiver_stopping_clearance'][main],
            'before_itinerary_groups': prior['itinerary_groups'],
            'after_itinerary_groups': current['itinerary_groups'],
            'receiver_stopping_clearance_by_itinerary': after['receiver_stopping_clearance_by_itinerary'][main],
        })
    participants = {cid for event in events for cid in (event.main_course, event.other_course)}
    for cid, rows in groups.items():
        for index, row in enumerate(rows):
            for obj in catalogs.array(row.contents[9].value):
                link = native_connections.record(obj)
                partner = link['target_course_id']
                formation_change = (link['flags'] & 1
                                    or link['flags'] & 2 and 0 < index < len(rows) - 1)
                if formation_change and {cid, partner} & participants:
                    need((cid, index, partner) in approved,
                         'Include the whole saved join/split chain for every participating Course')
    return receipts, approved
