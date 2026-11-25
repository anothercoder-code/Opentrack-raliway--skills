"""Existing native connections retain their original fields during formation review."""

from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import course_formation_rebind as rebind, network_composition_plan as composition
from opentrack_ai.current_archive import course_factories as cf, writer
from opentrack_ai.current_archive.shunting_workflow.core import plan_connections

from test_native_service_import import service_plan
from test_operating_plan_edit import connection, dictionary, row


def formation_source(join_flags=1):
    plan = service_plan()
    receiver = connection('A01', 'A02', 'RDG')
    supplier = connection('A02', 'A01', 'RDG')
    receiver.contents[4].value = 1
    supplier.contents[4].value = join_flags
    cf.settext(receiver, 5, 'HH:MM:SS')
    cf.settext(supplier, 5, 'HH:MM:SS')
    main_stop = row('A01', 'RDG', 1, '08:05:00', connections=(receiver,))
    cf.settext(main_stop, 7, '08:25:00')
    source_end = row('A02', 'RDG', 1, '08:12:00', connections=(supplier,))
    main_stop.contents[10].value = source_end.contents[10].value = 3
    records = {
        'A01#0': row('A01', 'EA', 0, '08:00:00'),
        'A01#1': main_stop,
        'A01#2': row('A01', 'WB', 2, '08:45:00'),
        'A02#0': row('A02', 'EA', 0, '08:06:00'),
        'A02#1': source_end,
    }
    for key, item in records.items():
        if key.startswith('A01'):
            item.contents[4].value = 2
    return {**{role: writer.dump_verified(plan.roots[role]) for role in ('courses', 'depot', 'trains', 'stations')},
            'timetable': writer.dump_verified(dictionary(records))}


def existing_join():
    return {'schema': 'split-join-timetable-plan/1',
            'operations': [{'kind': 'join', 'main_course': 'A01', 'other_course': 'A02',
                            'station_sign': 'RDG', 'main_visit_index': 1}],
            'accept_unverified_spatial_and_dynamic_execution': True}


def test_saved_join_is_verified_without_rebuilding_native_connections():
    input_files = formation_source()
    same_table, review = plan_connections(input_files, existing_join(), sequential_main=True, verify_existing=True)
    assert same_table == input_files['timetable']
    assert review['existing_connections_verified'] and review['new_connection_records'] == 0
    event, = review['events']
    assert event['main_row'] == 'A01#1' and event['other_row'] == 'A02#1'
    assert event['minimum_wait_s'] == 60
    assert event['projected_main_length_m'] == event['initial_main']['length_m'] + event['initial_other']['length_m']


def test_saved_join_rejects_counterpart_of_wrong_role():
    with pytest.raises(ValueError, match='does not match the reviewed station, role'):
        plan_connections(formation_source(join_flags=2), existing_join(), sequential_main=True, verify_existing=True)


LEFT, RIGHT = ('RDG', 20), ('RDG', 30)


def movement(label, end, *, role, length=500):
    def stop(sign, location, active, arrival, departure):
        return {'station_sign': sign, 'end_key': location, 'stop_edge_key': ('RDG', location[1] + 100),
                'stop_edge_length_m': length, 'incoming_track_id': str(location[1]),
                'planned': {'stop': active, 'arrival_s': arrival, 'departure_s': departure, 'track_id': ''}}

    a = stop('EA', ('EA', 0), False, 0, 0)
    b = stop('RDG', end, True, 100, 220)
    c = stop('WB', ('WB', 1), False, 330, 330)
    if role == 'split_child':
        visits = [stop('RDG', end, True, 190, 190), c]
    elif role == 'join_supply':
        visits = [a, stop('RDG', end, True, 190, 190)]
    else:
        visits = [a, b, c]
    return {'itinerary': label, 'visits': visits, 'consist_length_m': 418 if role == 'split_main' else 209,
            'maximum_speed_kmh': 80}


def operation(kind):
    request = {'kind': kind, 'main_course': 'A01', 'other_course': 'A02', 'main_visit_index': 1, 'station_sign': 'RDG'}
    event = {**request, 'initial_main': {'length_m': 418 if kind == 'split' else 209},
             'projected_main_length_m': 209 if kind == 'split' else 418}
    return [request], {'events': [event]}


def split_fixture(monkeypatch):
    origin, junction, far = ('EA', 0), ('WB', 1), ('WB', 22)
    route_choices = {'P-left': [(origin, LEFT), (LEFT, junction), (junction, ('RDG', 31), far)],
                     'P-right': [(origin, RIGHT), (RIGHT, junction)]}
    related = {}

    def local_pair(key):
        return key[0], key[1] ^ 1

    def dest_nodes(name):
        route = route_choices[name]
        return [*route[0], *(end for line in route[1:] for end in line[1:])], []

    graph = SimpleNamespace(related=local_pair, actual_related=lambda key: related.get(key, local_pair(key)),
                            route_view=lambda route: route, dest_view=dest_nodes)
    monkeypatch.setattr(rebind, 'itinerary_routes', lambda project, itinerary: iter(route_choices[itinerary]))
    monkeypatch.setattr(composition, 'itinerary_routes', lambda project, itinerary: iter(route_choices[itinerary]))
    options = {'A01': [movement('P-left', LEFT, role='split_main'), movement('P-right', RIGHT, role='split_main')],
               'A02': [movement('C-right', RIGHT, role='split_child'), movement('C-left', LEFT, role='split_child')]}
    identities = {variant['itinerary']: variant['itinerary'] for variants in options.values() for variant in variants}
    return graph, route_choices, related, options, identities


def test_split_matches_directed_platform_instead_of_child_priority_or_remote_route(monkeypatch):
    graph, routes, related, options, identities = split_fixture(monkeypatch)
    outbound_alias = ('Relay', 14)
    routes['P-left'][1] = LEFT, outbound_alias, ('WB', 1)
    related[outbound_alias] = RIGHT
    requests, report = operation('split')
    rebind._validate_geometry(graph, requests, report, options, identities)
    groups = report['events'][0]['itinerary_groups']
    assert [(group['station_end_key'], group['other_itineraries']) for group in groups] == [
        (LEFT, ['C-left']), (RIGHT, ['C-right'])]
    assert set(report['receiver_stopping_clearance_by_itinerary']['A01']) == {'P-left', 'P-right'}


def test_split_checks_competing_actual_related_end_and_unmatched_platform(monkeypatch):
    graph, routes, related, options, identities = split_fixture(monkeypatch)
    competitor = ('Relay', 12)
    routes['P-left'][0] = ('EA', 0), competitor, LEFT
    related[competitor] = RIGHT
    requests, report = operation('split')
    with pytest.raises(ValueError, match='split alternative|child origin'):
        rebind._validate_geometry(graph, requests, report, options, identities)
    related.clear()
    options['A02'][0] = movement('C-right', ('RDG', 40), role='split_child')
    with pytest.raises(ValueError, match='matching directed Itinerary'):
        rebind._validate_geometry(graph, requests, report, options, identities)


def test_split_rejects_head_stop_before_the_directed_route_boundary(monkeypatch):
    graph, _, _, options, identities = split_fixture(monkeypatch)
    options['A01'][0]['visits'][1]['head_stop'] = {'end_key': ('RDG', 19)}
    requests, report = operation('split')
    with pytest.raises(ValueError, match='actual stop at the directed station boundary'):
        rebind._validate_geometry(graph, requests, report, options, identities)


def test_split_checks_capacity_on_each_covered_parent_alternative(monkeypatch):
    graph, _, _, options, identities = split_fixture(monkeypatch)
    options['A01'][1] = movement('P-right', RIGHT, role='split_main', length=350)
    requests, report = operation('split')
    with pytest.raises(ValueError, match='complete initial train must fit'):
        rebind._validate_geometry(graph, requests, report, options, identities)


def test_join_keeps_permission_check_for_each_donor_approach_on_one_shared_end(monkeypatch):
    offers = {name: SimpleNamespace(name=name, contents={6: SimpleNamespace(values=[3, speed, 0])})
              for name, speed in (('A-north', 20), ('A-south', 25))}
    signals = {name: SimpleNamespace(contents={0: SimpleNamespace(value=i), 9: SimpleNamespace(values=[0, 0, 1])})
               for i, name in enumerate(offers, 10)}
    graph = SimpleNamespace(owners={id(route): ('RDG', i) for i, route in enumerate(offers.values(), 40)})
    monkeypatch.setattr(composition, '_arrival_route', lambda project, itinerary, end: offers[itinerary])
    monkeypatch.setattr(composition, '_entry_signal', lambda project, route: ('RDG', signals[route.name]))
    monkeypatch.setattr(composition, '_route_name', lambda route: route.name)
    options = {'A01': [movement('R-north', LEFT, role='join_main'), movement('R-south', LEFT, role='join_main')],
               'A02': [movement('A-north', LEFT, role='join_supply'), movement('A-south', LEFT, role='join_supply')]}
    identities = {variant['itinerary']: variant['itinerary'] for variants in options.values() for variant in variants}
    requests, report = operation('join')
    rebind._validate_geometry(graph, requests, report, options, identities)
    group, = report['events'][0]['itinerary_groups']
    assert [row['occupied_entry_speed_kmh'] for row in group['supplying_approaches']] == [20, 25]
    assert set(report['receiver_stopping_clearance_by_itinerary']['A01']) == {'R-north', 'R-south'}
    signals['A-south'].contents[9].values[2] = 0
    with pytest.raises(ValueError, match='entrance signal must explicitly allow'):
        rebind._validate_geometry(graph, requests, report, options, identities)


def alternative_join_fixture(monkeypatch):
    fork = ('RDG', 12)
    receiver_prefix = [('EA', 0), ('EA', 15), fork]
    donor_prefix = [('EA', 4), ('EA', 17), fork]
    approach = {side: SimpleNamespace(name=f'Approach-{side[1]}',
                                      contents={6: SimpleNamespace(values=[3, 20, 0])})
                for side in (LEFT, RIGHT)}
    views = {id(candidate): [fork, end] for end, candidate in approach.items()}
    routes = {name: [prefix, approach[end], *([tail] if tail else [])]
              for prefix, name, end, tail in (
                  (receiver_prefix, 'R-left', LEFT, [LEFT, ('WB', 1)]),
                  (receiver_prefix, 'R-right', RIGHT, [RIGHT, ('WB', 1)]),
                  (donor_prefix, 'D-left', LEFT, None),
                  (donor_prefix, 'D-right', RIGHT, None),
              )}
    owners = {id(candidate): fork for candidate in approach.values()}
    graph = SimpleNamespace(route_view=lambda route: views[id(route)] if id(route) in views else route,
                            actual_related=lambda end: (end[0], end[1] ^ 1), owners=owners)
    signal = SimpleNamespace(contents={0: SimpleNamespace(value=21), 9: SimpleNamespace(values=[0, 0, 1])})
    for module in (rebind, composition):
        monkeypatch.setattr(module, 'itinerary_routes', lambda project, itinerary: iter(routes[itinerary]))
    monkeypatch.setattr(composition, '_entry_signal', lambda project, route: ('RDG', signal))
    monkeypatch.setattr(composition, '_route_name', lambda route: route.name)
    options = {'A01': [movement('R-left', LEFT, role='join_main'), movement('R-right', RIGHT, role='join_main')],
               'A02': [movement('D-right', RIGHT, role='join_supply'), movement('D-left', LEFT, role='join_supply')]}
    return graph, options, routes, {name: name for name in routes}


def test_join_matches_preannounced_platform_with_opposite_course_priorities(monkeypatch):
    graph, options, _, identities = alternative_join_fixture(monkeypatch)
    requests, report = operation('join')
    rebind._validate_geometry(graph, requests, report, options, identities)
    groups = report['events'][0]['itinerary_groups']
    assert [(row['station_end_key'], row['other_itineraries']) for row in groups] == [
        (LEFT, ['D-left']), (RIGHT, ['D-right'])]
    assert [row['supplying_approaches'][0]['arrival_route']['name'] for row in groups] == [
        'Approach-20', 'Approach-30']
    assert set(report['receiver_stopping_clearance_by_itinerary']['A01']) == {'R-left', 'R-right'}


def test_join_accepts_different_earlier_routes_that_converge_before_platform_selection(monkeypatch):
    graph, options, routes, identities = alternative_join_fixture(monkeypatch)
    requests, report = operation('join')
    prefix = routes['D-left'][0]
    routes['D-left'][0] = [prefix[0], ('EA', 35), prefix[-1]]
    rebind._validate_geometry(graph, requests, report, options, identities)
    assert len(report['events'][0]['itinerary_groups']) == 2


def test_join_rejects_inaccessible_route_changes_and_cross_platform_aliases(monkeypatch):
    graph, options, routes, identities = alternative_join_fixture(monkeypatch)
    requests, report = operation('join')
    prefix = routes['D-left'][0]
    receiver = routes['R-left']
    alternate = routes['R-right']
    receiver[:1] = [[('EA', 0), ('RDG', 6)], [('RDG', 6), ('RDG', 12)]]
    alternate.append([('RDG', 6), ('WB', 22)])
    with pytest.raises(ValueError, match='native route-change order'):
        rebind._validate_geometry(graph, requests, report, options, identities)
    receiver[:2] = [alternate[0]]
    alternate.pop()
    routes['D-left'].append(routes['D-right'][1])
    with pytest.raises(ValueError, match='terminal supplying Route'):
        rebind._validate_geometry(graph, requests, report, options, identities)
    routes['D-left'].pop()
    prefix.insert(1, ('RDG', LEFT[1] ^ 1))
    with pytest.raises(ValueError, match='match just its own platform'):
        rebind._validate_geometry(graph, requests, report, options, identities)
