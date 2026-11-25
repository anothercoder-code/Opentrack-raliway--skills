"""Verify archived reciprocal Connection6 and native endpoint movement."""

import pytest

from opentrack_ai.current_archive import catalogs, course_factories, route_factory, writer
from opentrack_ai.current_archive.multi_document.core import ident, sha
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.station_reference_connections import review_saved_turnrounds, verify_turnround_geometry
from opentrack_ai.current_archive.station_reference_rebinding import rebind_station_reference_endpoints

from test_itinerary_lifecycle import course_archive
from test_native_rolling_stock_import import stock
from test_operating_plan_edit import connection, dictionary, row
from test_station_reference_rebinding import endpoint_fixture


def _connection(owner, target, station, *, flags, minimum):
    obj = connection(owner, target, station)
    obj.contents[4].value = flags
    course_factories.settext(obj, 3, minimum)
    course_factories.settext(obj, 5, None)
    return obj


def _turnrounds():
    courses, version = writer.load_next_compatible(course_archive(A=['EndFromWest'], B=['Westbound'], C=['Eastbound']))
    for course in catalogs.course_items(courses):
        course_factories.settext(course, 3, 'Passenger')
        course.contents[5].value = 1
    depot, trains = stock(120)
    rows = dict()
    for cid, index, station, time, day, links in (
        ('A', 0, 'W', '23:47:00', 0, []),
        ('A', 1, 'P', '23:59:00', 0, [_connection('A', 'B', 'P', flags=2, minimum='00:04:00')]),
        ('B', 0, 'P', '00:02:00', 1, [_connection('B', 'A', 'P', flags=0, minimum='00:01:40')]),
        ('B', 1, 'W', '00:10:00', 1, [_connection('B', 'C', 'W', flags=2, minimum='00:01:30')]),
        ('C', 0, 'W', '00:12:00', 1, [_connection('C', 'B', 'W', flags=0, minimum='00:01:30')]),
        ('C', 1, 'E', '00:27:00', 1, []),
    ):
        item = row(cid, station, index, time, connections=links)
        item.contents[10].value |= index
        item.contents[15].values[:2] = [day, day]
        rows[f'{cid}#{index}'] = item
    banks = {'courses': writer.dump_verified(courses, version), 'trains': writer.dump_verified(trains),
             'depot': writer.dump_verified(depot), 'timetable': writer.dump_verified(dictionary(rows))}
    reviews = [{'from_course': first, 'to_course': second, 'movement': movement}
               for first, second, movement in (('A', 'B', 'reverse'), ('B', 'C', 'continue'))]
    return banks, reviews


def _alter_timetable(banks, change):
    root, version = writer.load_next_compatible(banks['timetable'])
    change(course_factories.timetable(root))
    return {**banks, 'timetable': writer.dump_verified(root, version)}


def test_recovers_complete_chain_and_uses_successor_hold_with_absolute_midnight_times():
    banks, reviews = _turnrounds()
    result = review_saved_turnrounds(banks, {'A'}, reviews)
    assert [item['to_course'] for item in result] == ['B', 'C']
    first = result[0]
    assert (first['from_visit_index'], first['to_visit_index'], first['from_connection_index'], first['to_connection_index']) == (1, 0, 0, 0)
    assert (first['planned_arrival_s'], first['planned_departure_s'], first['planned_gap_s']) == (86340, 86520, 180)
    assert (first['station_sign'], first['minimum_hold_s'], first['predecessor_recorded_hold_s']) == ('P', 100, 240)
    assert first['train_length_m'] == 22 and first['train'] == 'Passenger'
    assert first['timetable_sha256'] == sha(banks['timetable'])


def test_rejects_missing_approval_and_unrelated_review():
    banks, reviews = _turnrounds()
    with pytest.raises(ValueError, match='every direct reciprocal turnround'):
        review_saved_turnrounds(banks, {'A'}, reviews[:1])
    with pytest.raises(ValueError, match='every direct reciprocal turnround'):
        review_saved_turnrounds(banks, {'Unconnected'}, reviews[:1])
    assert review_saved_turnrounds(banks, {'Unconnected'}, []) == []
    assert review_saved_turnrounds(banks, set(), []) == []


@pytest.mark.parametrize(('case', 'message'), (
    ('missing', 'reciprocal Connection6 pair'), ('action', 'ordinary fixed-formation'),
    ('wait', 'native successor minimum hold'), ('interval', 'without interval inheritance'),
    ('station', 'same saved native station'), ('time_reference', 'ordinary fixed-formation'),
))
def test_rejects_unsupported_or_inconsistent_native_connection(case, message):
    banks, reviews = _turnrounds()

    def change(rows):
        group = rows['B#0'].contents[9].value
        obj, = catalogs.array(group)
        if case == 'missing':
            writer.set_elements(group, [])
        elif case == 'action':
            obj.contents[4].value = 1
        elif case == 'wait':
            course_factories.settext(obj, 3, '00:03:01')
        elif case == 'interval':
            course_factories.settext(rows['C#0'], 2, 'B')
        elif case == 'station':
            course_factories.settext(obj, 6, 'Somewhere else')
        elif case == 'time_reference':
            obj.contents[7].value = 1

    with pytest.raises(ValueError, match=message):
        review_saved_turnrounds(_alter_timetable(banks, change), {'A'}, reviews)


def test_rejects_different_saved_train_even_if_both_consist_lengths_match():
    banks, reviews = _turnrounds()
    courses, course_version = writer.load_next_compatible(banks['courses'])
    trains, train_version = writer.load_next_compatible(banks['trains'])
    other = course_factories.clone(catalogs.train_items(trains)[0])
    course_factories.settext(other, 0, 'Other exact Train')
    train_array = trains.contents[3].value
    writer.set_elements(train_array, [*catalogs.array(train_array), other])
    course_factories.settext(catalogs.course_items(courses)[1], 3, 'Other exact Train')
    changed = {**banks, 'courses': writer.dump_verified(courses, course_version),
               'trains': writer.dump_verified(trains, train_version)}
    with pytest.raises(ValueError, match='same exact ordered native Train'):
        review_saved_turnrounds(changed, {'A'}, reviews)


@pytest.mark.parametrize(('movement', 'successor', 'successor_routes', 'match'), (
    ('reverse', 'Westbound', ('BA', 'AO'), 'actual_related'),
    ('continue', 'Eastbound', ('BC',), 'exact'),
))
def test_revised_routes_keep_the_native_match_and_restart_at_exact_first_end(endpoint_fixture, movement, successor, successor_routes, match):
    docs, paths, dest, moved, routes, _ = endpoint_fixture
    # The reference-rebinding fixture uses geometry after the typed station change.
    first_root, version = writer.load_next_compatible(docs['Line'])
    _, by_id = route_factory.document(first_root)
    for former, replacement in moved.items():
        by_id[former[1]].contents[20].value = 2
        by_id[replacement[1]].contents[20].value = 1
    original = project_from({'Line': writer.dump_verified(first_root, version)}, paths, dest)
    revisions = [('EndFromWest', ('OA', 'AB')), (successor, successor_routes)]
    saved, catalog, _ = rebind_station_reference_endpoints(
        docs, paths, dest, moved, [{'itinerary': name, 'replacement_routes': [routes[key] for key in route_keys]}
                                  for name, route_keys in revisions])
    updated = project_from({**docs, **saved}, paths, catalog)
    banks, requests = _turnrounds()
    link = {**review_saved_turnrounds(banks, {'A'}, requests)[0], 'movement': movement, 'to_itinerary': successor}

    def context(project):
        itineraries = {ident(item)[0]: item for item in project.dests}
        first, second = itineraries['EndFromWest'], itineraries[successor]
        first_nodes, first_edges = project.dest_view(first)
        second_nodes, _ = project.dest_view(second)
        first_distances = list(range(0, len(first_nodes) * 120, 120))
        fixed = {'station_sign': 'P', 'arrival_consist_length_m': 22, 'departure_consist_length_m': 22}
        stop = {**fixed, 'visit_index': 1, 'end_key': first_nodes[-1],
                'stopping_point': {'distance_m': first_distances[-1], 'signal_id': None, 'available_length_m': 120,
                                   'stop_edge_key': first_edges[-1], 'head_edge_offset_m': 120},
                'planned': {'arrival_s': 86340, 'departure_s': 86340, 'stop': True}}
        start = {**fixed, 'visit_index': 0, 'end_key': second_nodes[0],
                 'planned': {'arrival_s': 86520, 'departure_s': 86520, 'stop': False}}
        return {'A': (first, {'_directed_nodes': first_nodes, '_node_distances_m': first_distances}, [{}, stop]),
                'B': (second, {'_directed_nodes': second_nodes}, [start, {}])}

    old, new = context(original), context(updated)
    result, = verify_turnround_geometry([link], original, updated, old, new)
    assert result['after']['birth_end_key'] == moved[result['before']['birth_end_key']]
    assert result['after']['first_route'] == routes[successor_routes[0]]
    assert result['before']['match'] == result['after']['match'] == match
    assert result['after']['arrival_head_distance_m'] == result['before']['arrival_head_distance_m'] + 120
    assert result['after']['birth_sim_position'] == {'dest_index': 0, 'route_index': 0, 'end_index': 0, 'offset_m': 0}

    wrong = 'continue' if movement == 'reverse' else 'reverse'
    with pytest.raises(ValueError, match='paired terminal/starting Ends'):
        verify_turnround_geometry([{**link, 'movement': wrong}], original, updated, old, new)
