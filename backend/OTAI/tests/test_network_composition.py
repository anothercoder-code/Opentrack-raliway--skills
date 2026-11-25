"""Directed platform and clearance checks for actual split/join configuration."""

import unittest
from pathlib import Path

import pytest

from opentrack_ai.current_archive.network_composition_plan import _admit_spatial_event, _check_receiver_clearance
from opentrack_ai.current_archive.network_operating_plan import CompositionEvent, _planned_rows


def event_location(station, end, length, a, d, track='1'):
    return {'station_sign': station, 'end_key': end, 'stop_edge_key': ('B', 20) if length else None,
            'stop_edge_length_m': length, 'stopping_area_length_m': length, 'incoming_track_id': track, 'minimum_elapsed_s': 0,
            'planned': {'station_sign': station, 'arrival_s': a, 'departure_s': d,
                        'stop': True, 'track_id': track if length else ''}}


def receiver(length, area):
    return {'itinerary': 'I MAIN', 'consist_length_m': length, 'maximum_speed_kmh': 110,
            'visits': [event_location('B', ('B', 8), area, 50, 150)]}


class NetworkCompositionTest(unittest.TestCase):
    def test_split_child_uses_the_exact_same_directed_native_platform(self):
        main = receiver(418, 500)
        child = {'itinerary': 'I CHILD', 'consist_length_m': 209, 'maximum_speed_kmh': 110,
                 'visits': [event_location('B', ('B', 8), None, 155, 155)]}
        child['visits'][0]['planned']['track_id'] = '1'
        event = {'kind': 'split', 'main_course': 'MAIN', 'other_course': 'CHILD', 'station_sign': 'B'}
        out = _admit_spatial_event(None, event, {'MAIN': main, 'CHILD': child}, {})
        self.assertEqual(out['receiver_projected_after_m'], 209)
        child['visits'][0]['end_key'] = ('B', 9)
        with self.assertRaisesRegex(ValueError, 'same directed station reference'):
            _admit_spatial_event(None, event, {'MAIN': main, 'CHILD': child}, {})

    def test_join_rejects_both_units_when_combined_length_exceeds_platform(self):
        main = receiver(209, 400)
        other = receiver(209, 400)
        other['visits'][0]['planned']['arrival_s'] = 90
        event = {'kind': 'join', 'main_course': 'MAIN', 'other_course': 'SUPPLY', 'station_sign': 'B'}
        with self.assertRaisesRegex(ValueError, 'Joined train must fit'):
            _admit_spatial_event(None, event, {'MAIN': main, 'SUPPLY': other}, {})

    def test_stopped_origin_requires_a_declared_split(self):
        origin = event_location('B', ('B', 8), None, 100, 100)
        terminal = event_location('C', ('C', 8), 500, 200, 200)
        terminal['minimum_elapsed_s'] = 90
        trace = {'visits': [origin, terminal]}
        entry = {'visits': [origin['planned'], terminal['planned']]}
        with self.assertRaisesRegex(ValueError, 'stopped child activated'):
            _planned_rows(entry, trace, {'length_m': 209}, {'B', 'C'}, 'S#0', 0, 500)
        rows = _planned_rows(entry, trace, {'length_m': 209}, {'B', 'C'}, 'S#0', 0, 500, split_origin_stop=True)
        self.assertTrue(rows[0]['stop_at_station'])

    def test_split_uses_effective_length_after_a_prior_join(self):
        main = receiver(209, 500)
        child = {'itinerary': 'I CHILD', 'consist_length_m': 209, 'maximum_speed_kmh': 110,
                 'visits': [event_location('B', ('B', 8), None, 155, 155)]}
        event = {'kind': 'split', 'main_course': 'MAIN', 'other_course': 'CHILD', 'station_sign': 'B'}
        out = _admit_spatial_event(None, event, {'MAIN': main, 'CHILD': child}, {},
                                   current_formation={'length_m': 418})
        self.assertEqual((out['receiver_before_m'], out['receiver_projected_after_m']), (418, 209))

    def test_clearance_tracks_both_states_and_later_reduced_stops(self):
        visits = [event_location('A', ('A', 8), None, 0, 0), event_location('B', ('B', 8), 500, 50, 100),
                  event_location('C', ('C', 8), 430, 150, 160), event_location('D', ('D', 8), 500, 230, 250),
                  event_location('E', ('E', 8), 220, 300, 300)]
        entries = [{'main_course': 'MAIN', 'spatial': {'receiver_visit_index': 1, 'receiver_before_m': 209,
                                                        'receiver_projected_after_m': 418}},
                   {'main_course': 'MAIN', 'spatial': {'receiver_visit_index': 3, 'receiver_before_m': 418,
                                                       'receiver_projected_after_m': 209}}]
        reports = {'MAIN': {'consist_length_m': 209, 'visits': visits}}
        rows = _check_receiver_clearance(reports, entries)['MAIN']
        self.assertEqual([(row['arrival_length_m'], row['departure_length_m']) for row in rows],
                         [(209, 418), (418, 418), (418, 209), (209, 209)])
        visits[2]['stop_edge_length_m'] = 400
        with self.assertRaisesRegex(ValueError, 'directed stopping Edge at MAIN#2'):
            _check_receiver_clearance(reports, entries)

    def test_later_stop_uses_the_actual_available_length_across_edges(self):
        visits = [event_location('A', ('A', 8), None, 0, 0),
                  event_location('B', ('B', 8), 500, 50, 100),
                  event_location('C', ('C', 8), 100, 150, 150)]
        visits[2]['default_stop'] = {'available_length_m': 600}
        reports = {'MAIN': {'consist_length_m': 418, 'visits': visits}}
        entries = [{'main_course': 'MAIN', 'spatial': {'receiver_visit_index': 1, 'receiver_before_m': 418,
                                                       'receiver_projected_after_m': 209}}]
        stop = _check_receiver_clearance(reports, entries)['MAIN'][-1]
        self.assertEqual((stop['arrival_length_m'], stop['available_length_m']), (209, 600))


def test_original_traction_verification_uses_the_previous_composition_departure(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'scripts'))
    from verify_native_composition import assess_compositions

    engine = {'kind': 'engine', 'name': 'ENGINE'}
    single = {'formation': [engine], 'length_m': 209}
    double = {'formation': [engine, engine], 'length_m': 418}
    events = [
        {'kind': 'join', 'main_course': 'MAIN', 'other_course': 'SUP', 'station_sign': 'B',
         'initial_main': single, 'initial_other': single, 'projected_main_length_m': 418},
        {'kind': 'split', 'main_course': 'MAIN', 'other_course': 'DET', 'station_sign': 'C',
         'initial_main': double, 'initial_other': single, 'projected_main_length_m': 209},
    ]
    courses = {
        'MAIN': {'completion_verified': True, 'origin_event': {'time_s': 100},
                 'events': [{'kind': 'Dep.', 'time_s': 250}, {'kind': 'Dep.', 'time_s': 550},
                            {'kind': 'Arr.', 'time_s': 750}]},
        'SUP': {'completion_verified': True, 'events': [{'kind': 'Arr.', 'time_s': 200}]},
        'DET': {'completion_verified': True, 'events': [{'kind': 'Arr.', 'time_s': 800}]},
    }
    messages = ('NORMAL\t00:03:20\tMAIN\tCourse MAIN: Trains joined at B\t(B)\n'
                'NORMAL\t00:08:20\tDET\tCourse DET: Trains splitted at C\t(C)\n')
    traction = '\n'.join(f'{departure + step}\t0\t{step}\t1\t{force}\t0'
                         for departure, force in [(100, 280), (250, 560), (550, 280)] for step in (1, 2))
    rows = assess_compositions(events, courses, messages, native_traction={'MAIN': traction})
    assert [row['native_traction_comparison']['expected_identical_power_unit_count_ratio'] for row in rows] == [2, 0.5]
    assert all(row['native_traction_comparison']['tractive_effort_change_corrobates_archives'] for row in rows)
    assert rows[1]['native_traction_comparison']['prior_departure_s'] == 250
    with pytest.raises(ValueError, match='out of order'):
        assess_compositions(events[::-1], courses, messages)


def test_split_selects_exact_repeated_directed_occurrence():
    first = event_location('B', ('B', 8), 300, 50, 150)
    second = event_location('B', ('B', 8), 500, 250, 350)
    main = receiver(418, 500)
    main['visits'] = [event_location('A', ('A', 8), None, 0, 0), first, second,
                      event_location('C', ('C', 8), 500, 450, 450)]
    child = {'itinerary': 'I CHILD', 'consist_length_m': 209, 'maximum_speed_kmh': 110,
             'visits': [event_location('B', ('B', 8), None, 400, 400)]}
    reports = {'MAIN': main, 'CHILD': child}
    event = {'kind': 'split', 'main_course': 'MAIN', 'other_course': 'CHILD', 'station_sign': 'B'}
    with pytest.raises(ValueError, match='exactly one station occurrence'):
        _admit_spatial_event(None, event, reports, {})
    indexed = CompositionEvent.model_validate({**event, 'main_visit_index': 2})
    result = _admit_spatial_event(None, indexed.model_dump(), reports, {})
    assert result['receiver_visit_index'] == 2
    assert result['available_length_m'] == 500
    with pytest.raises(ValueError, match='complete initial train must fit'):
        _admit_spatial_event(None, {**event, 'main_visit_index': 1}, reports, {})
    with pytest.raises(ValueError, match='interior occurrence'):
        _admit_spatial_event(None, {**event, 'main_visit_index': 3}, reports, {})


def test_original_occurrence_check_distinguishes_two_stops_with_the_same_sign(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'scripts'))
    from verify_native_composition import verify_occurrence

    def event(kind, time, planned):
        return {'station': 'Station B', 'kind': kind, 'time_s': time, 'planned_s': planned}

    course = {
        'distance': {'first': [0, 0], 'units': ['s', 'km']},
        'events': [event('Arr.', 10, 9), event('Dep.', 30, 29),
                   event('Arr.', 110, 109), event('Dep.', 130, 129)],
        'stationary_intervals': [
            {'start_s': 10.4, 'end_s': 30, 'distance_reference_m': 497},
            {'start_s': 110.4, 'end_s': 130, 'distance_reference_m': 1491},
        ],
    }
    occurrence = {'index': 6, 'previous_visits': 1, 'same_station_visit_indices': [1, 6], 'station': 'Station B',
                  'distance_m': 1500, 'stop_edge_length_m': 100, 'planned': {'arrival_s': 109, 'departure_s': 129}}
    verified = verify_occurrence(course, occurrence, [112])
    assert verified['main_visit_index'] == 6
    assert verified['native_stopped_position_m'] == 1491
    with pytest.raises(ValueError, match='outside the selected repeated stop'):
        verify_occurrence(course, occurrence, [12])
    with pytest.raises(ValueError, match='lacks one exact original'):
        verify_occurrence(course, {**occurrence, 'distance_m': 500}, [112])


def test_continued_stock_checks_exact_order_instead_of_original_train_name(monkeypatch):
    from opentrack_ai.current_archive import network_operating_plan as operating

    engine = {'kind': 'engine', 'name': 'ENGINE'}
    trailer = {'kind': 'trailer', 'name': 'different display name', 'signature_sha256': 'full trailer digest'}
    monkeypatch.setattr(operating, 'text', lambda row, field: row['category'])
    monkeypatch.setattr(operating, 'vehicles', lambda row, depot: [(i, '', '', item)
                        for i, item in enumerate(row.get('formation', []))])
    trains = {'FULL': {'category': 'CAT'}, 'RESIDUAL': {'category': 'CAT', 'formation': [engine, trailer]}}
    plans = {'BEFORE': {'train': 'FULL'}, 'AFTER': {'train': 'RESIDUAL'}}
    event = {'kind': 'split', 'main_course': 'BEFORE', 'other_course': 'CHILD', 'main_row': 'BEFORE#1',
             'projected_main_formation': [engine, trailer], 'projected_main_length_m': 400}
    link = {'from_course': 'BEFORE', 'to_course': 'AFTER', 'movement': 'continue'}
    transfers = operating._projected_turnrounds([link], {'events': [event]}, plans, trains, {})
    assert transfers['BEFORE', 'AFTER']['projected_length_m'] == 400
    assert transfers['BEFORE', 'AFTER']['to_declared_train'] == 'RESIDUAL'
    with pytest.raises(ValueError, match='powered vehicle at both ends'):
        operating._projected_turnrounds([{**link, 'movement': 'reverse'}], {'events': [event]}, plans, trains, {})
    with pytest.raises(ValueError, match='split-child origin'):
        operating._projected_turnrounds([{**link, 'to_course': 'CHILD'}], {'events': [event]}, plans, trains, {})
    trains['RESIDUAL']['formation'].reverse()
    with pytest.raises(ValueError, match='exact ordered post-composition stock'):
        operating._projected_turnrounds([link], {'events': [event]}, plans, trains, {})


def test_reversal_preserves_vehicle_identity_and_reverses_native_positions(monkeypatch):
    from opentrack_ai.current_archive import network_operating_plan as operating

    alpha, beta = [{'kind': 'engine', 'name': name, 'accounting_index': index}
                   for index, name in enumerate(('Alpha', 'Beta'), 1)]
    monkeypatch.setattr(operating, 'text', lambda row, field: row['category'])
    monkeypatch.setattr(operating, 'vehicles', lambda row, depot: [(i, '', '', item)
                        for i, item in enumerate(row['formation'])])
    predecessor = {'category': 'CAT'}
    successor = {'category': 'CAT', 'formation': [beta, alpha]}
    trains = {'FULL': predecessor, 'REVERSE': successor}
    plans = {'LEFT': {'train': 'FULL'}, 'RIGHT': {'train': 'REVERSE'}}
    event = {'kind': 'join', 'main_course': 'LEFT', 'other_course': 'SUPPLY', 'main_row': 'LEFT#1',
             'projected_main_formation': [alpha, beta], 'projected_main_length_m': 84}
    link = {'from_course': 'LEFT', 'to_course': 'RIGHT', 'movement': 'reverse'}
    transfer = operating._projected_turnrounds([link], {'events': [event]}, plans, trains, {})['LEFT', 'RIGHT']
    assert [(item['name'], item['accounting_index']) for item in transfer['formation']] == [('Beta', 1), ('Alpha', 2)]
    assert transfer['predecessor_formation'] == [alpha, beta]
    successor['formation'].reverse()
    with pytest.raises(ValueError, match='exact ordered post-composition stock'):
        operating._projected_turnrounds([link], {'events': [event]}, plans, trains, {})


def test_composition_plan_preserves_a_midnight_dwell_and_rejects_clock_rollback():
    from types import SimpleNamespace

    from opentrack_ai.current_archive.shunting_workflow.core import scheduled_times
    from opentrack_ai.current_archive.zero_generation.native_signal_routes import string

    def row(arrival, departure, days):
        fields = [None] * 16
        for index, value in ((6, arrival), (7, departure), (13, 'HH:MM:SS'), (14, 'HH:MM:SS')):
            fields[index] = SimpleNamespace(value=string(value))
        fields[10] = SimpleNamespace(value=3)
        fields[15] = SimpleNamespace(values=days)
        return SimpleNamespace(contents=fields)

    first = row('23:58:00', '00:04:00', [0, 1, 0, 0])
    following = row('00:10:00', '00:10:00', [1, 1, 0, 0])
    assert scheduled_times([first, following], allow_day_offsets=True) == {
        id(first): (86280, 86640), id(following): (87000, 87000),
    }
    with pytest.raises(ValueError, match='standalone timetable-only'):
        scheduled_times([first, following], allow_day_offsets=False)
    with pytest.raises(ValueError, match='chronological'):
        scheduled_times([first, row('00:10:00', '00:10:00', [0, 0, 0, 0])], allow_day_offsets=True)


def test_bare_native_composition_clock_binds_one_day_from_the_measured_stop(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / 'scripts'))
    from verify_native_composition import absolute_message_clock

    assert absolute_message_clock('00:03:00', 86382, 86880) == 86580
    assert absolute_message_clock('1 / 00:03:00', 86382, 86880) == 86580
    with pytest.raises(ValueError, match='ambiguous or outside'):
        absolute_message_clock('0 / 00:03:00', 86382, 86880)
    with pytest.raises(ValueError, match='ambiguous or outside'):
        absolute_message_clock('00:03:00', 0, 86880)

