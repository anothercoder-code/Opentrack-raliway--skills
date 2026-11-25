"""Independent plan admission needs the actual directed station occurrences."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from opentrack_ai.current_archive import route_factory, writer
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.multi_document.core import ident
from opentrack_ai.current_archive.native_link_start import _native_match, successor_start
from opentrack_ai.current_archive.network_operating_plan import (
    _composition_visit_lengths, _planned_rows, _turnround_commands, resolve_visit_stop, route_trace,
)
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.saved_main_signal_split import insert_signal_in_saved_route
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_itinerary_native_edit import schematic_document
from test_itinerary_lifecycle import course_archive
from test_saved_main_signal_split import sending_corridor


def it(stop_key, station, elapsed, length, track):
    return {'station_sign': station, 'minimum_elapsed_s': elapsed, 'stop_edge_length_m': length, 'stopping_area_length_m': length,
            'incoming_track_id': track, 'end_key': stop_key}


def visit(station, a, d, stop, track=''):
    return {'station_sign': station, 'arrival_s': a, 'departure_s': d, 'stop': stop, 'track_id': track}


def platform_trace(markers, station_reference=None, *, reverse=False, limits=None, internal_role=None,
                   linked_reservation=True):
    diagram = generate.spec()
    names = 'OABCDEF'
    side = int(reverse)
    exit_name = 'B' if reverse else 'D'
    reference_name = station_reference or exit_name
    diagram['vertices'] = [generate.vertex(name, 20 + i * 100) for i, name in enumerate(names)]
    profile, = diagram['edges']
    diagram['edges'] = [{**profile, 'key': a + b, 'from': [a, 1], 'to': [b, 0], 'length_m': 100}
                        for a, b in zip(names, names[1:])]
    for edge in diagram['edges']:
        if limits and edge['key'] in limits:
            forward, backward = limits[edge['key']]
            edge['equal_speed'] = False
            edge['speeds'] = [dict(train_type='0', speed12_kmh=forward, speed21_kmh=backward)]
    signal_ends = [(name, side) for name in ('O', exit_name, 'F')] + list(markers)
    if internal_role is not None:
        signal_ends.append(('B', 0))
    doc, ids = schematic_document(diagram, signal_ends)
    root, version = writer.load_next_compatible(doc)
    models, by_id = route_factory.document(root)
    by_id[ids[exit_name][side]].contents[11].value.contents[8].values[1] = 4
    if internal_role is not None:
        by_id[ids['B'][0]].contents[11].value.contents[8].values[1] = internal_role
    for (name, facing), code in markers.items():
        by_id[ids[name][facing]].contents[11].value.contents[8].values[:] = [code, 1, 0]
    stations = []
    for i, (reference, members, sign) in enumerate((('O', 'O', 'O'), (reference_name, 'ABCDE', 'P'),
                                                    ('F', 'F', 'F'))):
        station = native.obj([('OTStationModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], [
            ('i', [1000 + i]), ('f', [0.0]), ('f', [20.0]), ('f', [10.0]), ('i', [0]), ('i', [0]),
            ('@', [None]), ('@', [native.string(sign)]), ('ii', [2, 4]), ('ii', [1, 0]),
        ])
        stations.append(station)
        for name in members:
            for end_id in ids[name]:
                by_id[end_id].contents[12].value = station
                by_id[end_id].contents[20].value = 2 if name == reference else 1
    writer.set_elements(root.contents[2].value, [*models, *stations])
    docs = {'Line': writer.dump_verified(root, version)}
    if internal_role is not None:
        docs['Line'], _ = native.build_route(docs['Line'], name='Platform exit movement',
            end_ids=[ids[name][0] for name in 'BCD'], description='', release_groups='global',
            reserve_previous=linked_reservation)
    catalog = writer.dump_verified(generate.wrapped('OTDestInfoList', []))
    graph = project_from(docs, {'Line': 'Line.opentrack'}, catalog)
    nodes = [('Line', ids[name][side]) for name in (names[::-1] if reverse else names)]
    with patch.object(graph, 'dest_view', return_value=(nodes, [])):
        return route_trace(graph, object(), '0', 60), ids


def test_only_a_directed_internal_block_continuing_to_the_berth_exit_preserves_platform_extent():
    marks = {('C', 0): 21}
    original, _ = platform_trace(marks)
    continued, ids = platform_trace(marks, internal_role=3)
    assert continued == original
    location = continued['visits'][1]
    assert location['stopping_area_length_m'] == 300
    assert [marker['end_key'] for marker in location['halt_platform']['markers']] == [('Line', ids['C'][0])]
    assert resolve_visit_stop(location, 200)['distance_m'] == 400

    other_main, _ = platform_trace(marks, internal_role=2)
    assert other_main['visits'][1]['stopping_area_length_m'] == 100
    without_halt, _ = platform_trace({}, internal_role=3)
    assert without_halt['visits'][1]['stopping_area_length_m'] == 100
    independent, _ = platform_trace(marks, internal_role=3, linked_reservation=False)
    assert independent['visits'][1]['stopping_area_length_m'] == 100


@pytest.mark.parametrize(('role', 'expected_length'), [(2, 1000), (3, 2000), (4, 1000)])
def test_only_opposing_continued_block_preserves_the_platform_approach(sending_corridor, role, expected_length):
    docs, paths, dest, original, request = sending_corridor
    changes, _ = insert_signal_in_saved_route(docs, paths, dest, 'A', request, course_archive(C01=['I:A-B']))
    primary, = [route for route in original.routes if original.owners[id(route)][0] == 'A']
    nodes = original.route_view(primary)
    reverse_start = original.related(nodes[-1])
    receiver = original.block_end(original.related(nodes[-2]))
    platform = [original.related(node) for node in reversed(nodes[:3])]
    walked = [reverse_start, original.related(receiver), *platform]

    def cold_trace(documents, opposite_role=None):
        project = project_from(documents, paths, dest)
        for group, sign in (([reverse_start], 'O'), (platform, 'P')):
            sheet = group[0][0]
            station = native.obj([('OTStationModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], [
                ('i', [1000]), ('f', [0.0]), ('f', [20.0]), ('f', [10.0]), ('i', [0]), ('i', [0]),
                ('@', [None]), ('@', [native.string(sign)]), ('ii', [2, 4]), ('ii', [1, 0]),
            ])
            for key in group:
                for half in (key, project.related(key)):
                    end = project.model(half)
                    end.contents[12].value = station
                    end.contents[20].value = 2 if key == group[-1] else 1
            collection = project.roots[sheet].contents[2].value
            writer.set_elements(collection, [*writer.elements(collection), station])
        head = project.model(platform[-1])
        terminal = native.main_signal_model(head, name='Platform exit', model_id=1001,
            placement=generate.signal_placement(head, 100, 30), sight_m=500, delay_s=0,
            show_symbol=True, show_icon=True)
        head.contents[11].value = terminal
        collection = project.roots['A'].contents[2].value
        writer.set_elements(collection, [*writer.elements(collection), terminal])
        if opposite_role is not None:
            reverse_signal = project.model(nodes[1]).contents[11].value
            reverse_signal.contents[8].values[1] = opposite_role
        cold = project_from({name: writer.dump_verified(root, project.versions[name])
                             for name, root in project.roots.items()}, paths, dest)
        if opposite_role is not None:
            assert any(row['route']['name'] == 'Sending relay' for row in cold.continuations)
        assert [ident(item)[0] for item in cold.dests] == ['I:A-B']
        with patch.object(cold, 'dest_view', return_value=(walked, [])):
            return route_trace(cold, object(), '0', 60)

    baseline = cold_trace(docs)
    changed = cold_trace({**docs, **changes}, role)
    original_stop = resolve_visit_stop(baseline['visits'][-1], 900)
    reviewed_stop = resolve_visit_stop(changed['visits'][-1], 900)
    assert original_stop['available_length_m'] == 2000
    assert reviewed_stop['available_length_m'] == expected_length
    assert original_stop['head_end_key'] == reviewed_stop['head_end_key'] == platform[-1]
    assert original_stop['distance_m'] == reviewed_stop['distance_m'] == 4000
    assert original_stop['signal_id'] == reviewed_stop['signal_id'] == 1001
    if role == 3:
        assert changed == baseline


class NetworkOperatingPlanTest(unittest.TestCase):
    def test_station_reference_before_or_after_exit_preserves_actual_head_stop(self):
        original, ids = platform_trace({('C', 0): 6})
        for reference, distance in (('B', 200), ('E', 500)):
            with self.subTest(reference=reference):
                changed, _ = platform_trace({('C', 0): 6}, reference)
                location = changed['visits'][1]
                self.assertEqual(location['end_key'], ('Line', ids[reference][0]))
                self.assertEqual(location['distance_m'], distance)
                self.assertEqual(location['default_stop']['distance_m'], 400)
                self.assertEqual(location['default_stop']['available_length_m'], 300)
                self.assertEqual(location['default_stop']['end_key'], ('Line', ids['D'][0]))
                for field in ('end_key', 'distance_m', 'minimum_elapsed_s', 'available_length_m', 'stop_edge_key'):
                    self.assertEqual(location['head_stop'][field], original['visits'][1]['head_stop'][field])
                entry = {'visits': [visit('O', 0, 0, False), visit('P', 18, 28, True), visit('F', 46, 46, False)]}
                rows = _planned_rows(entry, changed, {'length_m': 200}, {'O', 'P', 'F'}, 'T#0', 0, 90)
                self.assertTrue(rows[1]['stop_at_station'])

    def test_reference_without_own_signal_rejects_halt_marker_beyond_distinct_exit(self):
        changed, _ = platform_trace({('C', 0): 6, ('E', 0): 6}, 'B')
        self.assertIn('before its one exit', changed['visits'][1]['halt_stop_issue'])

    def test_finite_return_uses_each_occurrence_in_order(self):
        a = ('A', 14)
        b = ('B', 32)
        trace = {'visits': [it(a, 'A', 0, None, None), it(b, 'B', 100, 250, 'Down'), it(a, 'A', 240, 260, 'Loop')]}
        entry = {'visits': [visit('A', 86300, 86300, False), visit('B', 86410, 86450, True, 'Down'),
                            visit('A', 86600, 86600, True, 'Loop')]}
        rows = _planned_rows(entry, trace, {'length_m': 230}, {'A', 'B'}, 'T#0', 0, 172800)
        self.assertEqual([row['station_sign'] for row in rows], ['A', 'B', 'A'])
        self.assertEqual([row['arrival_day_offset'] for row in rows], [0, 1, 1])
        self.assertEqual([row['track_id'] for row in rows], ['', 'Down', 'Loop'])
        self.assertFalse(rows[0]['stop_at_station'])
        self.assertTrue(rows[-1]['stop_at_station'])

    def test_direction_length_and_necessary_timing_are_independent(self):
        a = it(('A', 15), 'A', 0, None, None)
        b = it(('B', 42), 'B', 110, 210, 'Down')
        state = {'visits': [a, b]}
        entry = {'visits': [visit('A', 1, 1, False), visit('B', 155, 155, True, 'Other')]}
        with self.assertRaisesRegex(ValueError, 'saved incoming Edge'):
            _planned_rows(entry, state, {'length_m': 200}, {'A', 'B'}, 'T#0', 0, 1000)
        entry['visits'][1]['track_id'] = 'Down'
        with self.assertRaisesRegex(ValueError, 'absent or too short'):
            _planned_rows(entry, state, {'length_m': 211}, {'A', 'B'}, 'T#0', 0, 1000)
        entry['visits'][1] = visit('B', 20, 20, True, 'Down')
        with self.assertRaisesRegex(ValueError, 'speed lower bound'):
            _planned_rows(entry, state, {'length_m': 190}, {'A', 'B'}, 'T#0', 0, 1000)

    def test_primary_reference_end_targets_exact_row_without_constraining_alternative(self):
        a = it(('A', 15), 'A', 0, None, None)
        b = it(('B', 42), 'B', 110, 250, 'Down')
        other = it(('A', 27), 'A', 220, 250, 'Up')
        trace = {'visits': [a, b, other]}
        entry = {'visits': [visit('A', 1, 1, False), visit('B', 115, 115, False),
                            {**visit('A', 225, 225, True), 'primary_reference_end': ['A', 15]}]}
        with self.assertRaisesRegex(ValueError, 'directed station reference.*row 2'):
            _planned_rows(entry, trace, {'length_m': 190}, {'A', 'B'}, 'T#0', 0, 1000)
        rows = _planned_rows(entry, trace, {'length_m': 190}, {'A', 'B'}, 'T#0', 0, 1000, primary=False)
        self.assertEqual([row['station_sign'] for row in rows], ['A', 'B', 'A'])

    def test_regular_stop_can_use_the_complete_contiguous_platform_area(self):
        a = it(('A', 15), 'A', 0, None, None)
        b = {**it(('B', 42), 'B', 110, 60, 'Down'), 'stopping_area_length_m': 300}
        state = {'visits': [a, b]}
        entry = {'visits': [visit('A', 1, 1, False), visit('B', 155, 155, True, 'Down')]}
        rows = _planned_rows(entry, state, {'length_m': 90}, {'A', 'B'}, 'T#0', 0, 1000)
        self.assertTrue(rows[-1]['stop_at_station'])
        with self.assertRaisesRegex(ValueError, 'absent or too short'):
            _planned_rows(entry, state, {'length_m': 301}, {'A', 'B'}, 'T#0', 0, 1000)

    def test_last_directed_head_marker_sets_the_available_platform_and_travel_time(self):
        trace, ids = platform_trace({('B', 0): 6, ('C', 0): 6, ('B', 1): 21, ('E', 1): 6})
        origin, platform, _ = trace['visits']
        stop = platform['head_stop']
        self.assertEqual(platform['end_key'], ('Line', ids['D'][0]))
        self.assertEqual(platform['distance_m'], 400)
        self.assertEqual(platform['stopping_area_length_m'], 300)
        self.assertEqual(stop['end_key'], ('Line', ids['C'][0]))
        self.assertEqual((stop['distance_m'], stop['available_length_m']), (300, 200))
        self.assertAlmostEqual(stop['minimum_elapsed_s'], 18.0)
        self.assertAlmostEqual(origin['minimum_elapsed_s'], 0)
        entry = {'visits': [visit('O', 0, 0, False), visit('P', 20, 30, True), visit('F', 50, 50, False)]}
        self.assertTrue(_planned_rows(entry, trace, {'length_m': 200}, {'O', 'P', 'F'}, 'T#0', 0, 1000)[1]['stop_at_station'])
        with self.assertRaisesRegex(ValueError, 'too short'):
            _planned_rows(entry, trace, {'length_m': 201}, {'O', 'P', 'F'}, 'T#0', 0, 1000)
        entry['visits'][-1] = visit('F', 45, 45, False)
        with self.assertRaisesRegex(ValueError, 'speed lower bound'):
            _planned_rows(entry, trace, {'length_m': 200}, {'O', 'P', 'F'}, 'T#0', 0, 1000)

    def test_marker_beyond_the_actual_exit_blocks_only_a_scheduled_halt(self):
        trace, _ = platform_trace({('B', 0): 6, ('E', 0): 6})
        entry = {'visits': [visit('O', 0, 0, False), visit('P', 40, 50, True), visit('F', 80, 80, False)]}
        with self.assertRaisesRegex(ValueError, 'beyond the station reference'):
            _planned_rows(entry, trace, {'length_m': 100}, {'O', 'P', 'F'}, 'T#0', 0, 1000)
        through = {'visits': [visit('O', 0, 0, False), visit('P', 40, 40, False), visit('F', 80, 80, False)]}
        self.assertFalse(_planned_rows(through, trace, {'length_m': 100}, {'O', 'P', 'F'}, 'T#0', 0, 1000)[1]['stop_at_station'])

    def test_first_eligible_length_stop_and_exit_fallback(self):
        trace, ids = platform_trace({('B', 0): 8, ('C', 0): 9})
        location = trace['visits'][1]
        for length, marker, position in ((100, 'B', 200), (101, 'C', 300), (200, 'C', 300), (201, 'D', 400)):
            with self.subTest(length=length):
                stop = resolve_visit_stop(location, length)
                self.assertEqual(stop['end_key'], ('Line', ids[marker][0]))
                self.assertEqual(stop['distance_m'], position)
                self.assertEqual(stop['target_speed_kmh'], 0)

    def test_general_center_overrides_short_mark_and_times_partial_next_edge(self):
        trace, ids = platform_trace({('B', 0): 9, ('C', 0): 21}, limits={'CD': (30, 50)})
        location = trace['visits'][1]
        planned = [visit('O', 0, 0, False), visit('P', 27, 40, True), visit('F', 90, 90, False)]
        resolved = []
        _planned_rows({'visits': planned}, trace, {'length_m': 120}, {'O', 'P', 'F'}, 'T#0', 0, 1000,
                      resolved_visits=resolved)
        stop = resolved[1]['stopping_point']
        self.assertEqual(location['distance_m'], 400)
        self.assertEqual(stop['end_key'], ('Line', ids['C'][0]))
        self.assertIsNone(stop['head_end_key'])
        self.assertEqual((stop['marker_distance_m'], stop['distance_m'], stop['head_edge_offset_m']), (300, 360, 60))
        self.assertEqual((stop['directional_speed_limit_kmh'], stop['effective_speed_limit_kmh'],
                          stop['target_speed_kmh']), (30, 30, 0))
        self.assertAlmostEqual(resolved[1]['leg_minimum_elapsed_s'], 25.2)
        self.assertAlmostEqual(resolved[2]['leg_minimum_elapsed_s'], 16.8)
        planned[1]['arrival_s'] = 25
        with self.assertRaisesRegex(ValueError, 'speed lower bound'):
            _planned_rows({'visits': planned}, trace, {'length_m': 120}, {'O', 'P', 'F'}, 'T#0', 0, 1000)

    def test_reverse_tail_marker_follows_reverse_edges_and_exit_bound(self):
        trace, ids = platform_trace({('C', 1): 20, ('C', 0): 6}, reverse=True, limits={'BC': (50, 25)})
        location = trace['visits'][1]
        stop = resolve_visit_stop(location, 80)
        self.assertEqual(stop['end_key'], ('Line', ids['C'][1]))
        self.assertEqual((stop['marker_distance_m'], stop['distance_m'], stop['head_edge_offset_m']), (300, 380, 80))
        self.assertEqual(stop['directional_speed_limit_kmh'], 25)
        self.assertAlmostEqual(stop['minimum_elapsed_s'], 29.52)
        with self.assertRaisesRegex(ValueError, 'beyond the directed platform exit'):
            resolve_visit_stop(location, 101)

    def test_formation_length_after_split_selects_the_later_visit_marker(self):
        trace, ids = platform_trace({('B', 0): 33, ('C', 0): 8})
        platform = trace['visits'][1]
        shifted = {**platform['halt_platform'], 'start_distance_m': 400, 'start_elapsed_s': 24}
        later = {**platform, 'station_sign': 'Q', 'halt_platform': shifted}
        route = {'visits': [trace['visits'][0], platform, later]}
        scheduled = [visit('O', 0, 0, False), visit('P', 30, 45, True), visit('Q', 80, 80, True)]
        service = SimpleNamespace(course_id='A', visits=[SimpleNamespace(station_sign=v['station_sign']) for v in scheduled])
        child = SimpleNamespace(course_id='B', visits=[])
        event = SimpleNamespace(kind='split', main_course='A', other_course='B', main_visit_index=1, station_sign='P')
        stock = {'A': {'length_m': 80}, 'B': {'length_m': 30}}
        schedule = _composition_visit_lengths(SimpleNamespace(courses=[service, child], composition_events=[event]), stock)
        resolved = []
        _planned_rows({'visits': scheduled}, route, stock['A'], {'O', 'P', 'Q'}, 'T#0', 0, 1000,
                      formation_by_visit=schedule['A'], resolved_visits=resolved)
        self.assertEqual([(r['arrival_consist_length_m'], r['departure_consist_length_m']) for r in resolved],
                         [(80, 80), (80, 50), (50, 50)])
        self.assertEqual(resolved[1]['stopping_point']['end_key'], ('Line', ids['C'][0]))
        self.assertEqual(resolved[2]['stopping_point']['end_key'], ('Line', ids['B'][0]))

    def test_turnround_requires_exact_course_pair_and_saved_turnround_time(self):
        a = {'train': 'Engine 1', 'minimum_turnround_s': 20,
             'visits': [visit('A', 10, 10, False), visit('B', 150, 150, True)]}
        b = {'train': 'Engine 1', 'minimum_turnround_s': 20,
             'visits': [visit('B', 180, 180, False), visit('A', 430, 430, True)]}
        links = [{'from_course': 'X', 'to_course': 'Y'}]
        bound, = _turnround_commands({'X': a, 'Y': b}, links, {})
        self.assertEqual((bound.course_id, bound.target_course_id, bound.index), ('X', 'Y', 1))
        b['visits'][0]['departure_s'] = 165
        with self.assertRaisesRegex(ValueError, 'saved Category minimum'):
            _turnround_commands({'X': a, 'Y': b}, links, {})

    def test_successor_origin_uses_first_end_despite_interior_arrival_head(self):
        a, b, p, reverse_p, end = ('Main', 1), ('Main', 2), ('Main', 10), ('Other', 11), ('Main', 20)
        graph = SimpleNamespace(route_view=lambda nodes: nodes,
                                actual_related=lambda key: {p: reverse_p, reverse_p: p}.get(key, key))
        before = [[a, b, p]]
        arrival = {'end_key': p, 'station_sign': 'P', 'visit_index': 1,
                   'stopping_point': {'distance_m': 240, 'signal_id': 99}}
        trace = {'_directed_nodes': [a, b, p], '_node_distances_m': [0, 100, 300]}
        pair = ('X', 'Y')
        with patch('opentrack_ai.current_archive.native_link_start.itinerary_routes',
                   side_effect=lambda project, routes: routes):
            for movement, origin, match in (('continue', p, 'exact'), ('reverse', reverse_p, 'actual_related')):
                with self.subTest(movement=movement):
                    successor = [[origin, end]]
                    successor_trace = {'_directed_nodes': [origin, end]}
                    result = successor_start(graph, before, successor, trace, successor_trace, arrival,
                                             {'end_key': origin, 'station_sign': 'P'}, movement, pair)
                    self.assertEqual(result['arrival_head_distance_m'], 240)
                    self.assertEqual(result['birth_end_key'], origin)
                    self.assertEqual(result['match'], match)
                    self.assertEqual(result['birth_sim_position'],
                                     {'dest_index': 0, 'route_index': 0, 'end_index': 0, 'offset_m': 0})
            successor = [[b, p, end]]
            successor_trace = {'_directed_nodes': [b, p, end]}
            with self.assertRaisesRegex(ValueError, 'first directed End'):
                successor_start(graph, before, successor, trace, successor_trace, arrival,
                                {'end_key': p, 'station_sign': 'P'}, 'continue', pair)
            with self.assertRaisesRegex(ValueError, 'common native Station sign'):
                successor_start(graph, before, successor, trace, successor_trace, arrival,
                                {'end_key': p, 'station_sign': 'Q'}, 'continue', pair)
            with self.assertRaisesRegex(ValueError, 'paired terminal'):
                successor_start(graph, before, successor, trace, successor_trace, arrival,
                                {'end_key': p, 'station_sign': 'P'}, 'reverse', pair)
            before = [[a, b], [b, p]]
            shifted = {**arrival, 'stopping_point': {'distance_m': 80, 'signal_id': 98}}
            with self.assertRaisesRegex(ValueError, 'absent from the arrival head Route'):
                successor_start(graph, before, [[p, end]], trace, {'_directed_nodes': [p, end]}, shifted,
                                {'end_key': p, 'station_sign': 'P'}, 'continue', pair)

    def test_native_route_scan_precedes_endpoint_and_direction_preference(self):
        a, b, p, target = ('P', 1), ('P', 2), ('P', 3), ('Q', 1)
        graph = SimpleNamespace(actual_related=lambda key: target if key in (b, p) else key)
        previous = [(0, 2, [a, b, p]), (2, 3, [p, a])]
        self.assertEqual(_native_match(graph, target, previous, 0, -1), (0, p, 'actual_related'))
        self.assertEqual(_native_match(graph, target, previous, -1, 0), (0, b, 'actual_related'))

