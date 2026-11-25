"""Preserve native timetable commitments while changing booked platform tracks."""

from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import course_factories as cf
from opentrack_ai.current_archive.native_course_platform_rebind import (
    CoursePlatforms, _check_physical_links, _review_choices,
)
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_operating_plan_edit import connection, row


def platform_trace(*visits):
    return {
        'edges': [('Line', 24)],
        'visits': [
            {'station_sign': station, 'end_key': ('Line', end), 'minimum_elapsed_s': index * 50,
             'incoming_track_id': track, 'stopping_area_length_m': 400}
            for index, (station, end, track) in enumerate(visits)
        ],
    }


def track_graph():
    edge = SimpleNamespace(contents=[None] * 19 + [SimpleNamespace(value=native.string('Origin'))])
    return SimpleNamespace(model=lambda _: edge, related=lambda key: (key[0], key[1] ^ 1))


def reviewed(mode='pin', reference=20):
    return CoursePlatforms.model_validate({
        'course_id': 'Train', 'expected_itineraries': ['Old'], 'itineraries': ['New'],
        'visits': [{'index': 1, 'station_sign': 'Platform', 'from_reference': ['Line', 10],
                    'to_reference': ['Line', reference], 'track': mode}],
    })


def booked_platform():
    itinerary = platform_trace(('Start', 0, None), ('Platform', 10, 'P1'), ('End', 100, 'Term'))
    edited = platform_trace(('Start', 0, None), ('Platform', 20, 'P2'), ('End', 100, 'Term'))
    rows = [row('Train', station, i, clock) for i, (station, clock) in enumerate(
        [('Start', '08:00:00'), ('Platform', '08:03:00'), ('End', '08:08:00')])]
    rows[1].contents[10].value = rows[2].contents[10].value = 3
    cf.settext(rows[1], 7, '08:05:00')
    cf.settext(rows[1], 18, 'P1')
    return itinerary, edited, rows


def test_track_is_rebound_and_clock_values_stay_the_same():
    before, after, rows = booked_platform()
    report, = _review_choices(track_graph(), reviewed(), rows, [before], [after],
                              {'length_m': 209}, {'Start', 'Platform', 'End'}, (0, 43200))
    assert report['old_track_id'] == 'P1' and report['new_track_id'] == 'P2'
    assert report['from_stop_end'] == ('Line', 10) and report['to_stop_end'] == ('Line', 20)
    assert report['arrival_s'] == 28980 and report['departure_s'] == 29100


def test_multiple_tracks_need_explicit_clear_and_a_booked_train_must_fit():
    before, after, rows = booked_platform()
    alternative = platform_trace(('Start', 0, None), ('Platform', 30, 'P3'), ('End', 100, 'Term'))
    with pytest.raises(ValueError, match='common saved track'):
        _review_choices(track_graph(), reviewed(), rows, [before], [after, alternative],
                        {'length_m': 400}, {'Start', 'Platform', 'End'}, (0, 43200))
    report, = _review_choices(track_graph(), reviewed('unrestricted'), rows, [before], [after, alternative],
                              {'length_m': 400}, {'Start', 'Platform', 'End'}, (0, 43200))
    assert report['new_track_id'] == ''
    with pytest.raises(ValueError, match='absent or too short'):
        _review_choices(track_graph(), reviewed(), rows, [before], [after],
                        {'length_m': 401}, {'Start', 'Platform', 'End'}, (0, 43200))
    with pytest.raises(ValueError, match='Reviewed platform reference differs'):
        _review_choices(track_graph(), reviewed(reference=999), rows, [before], [after],
                        {'length_m': 209}, {'Start', 'Platform', 'End'}, (0, 43200))


def test_reversing_turnround_moves_both_native_endpoints():
    link = connection('A', 'B', 'Platform')
    link.contents[4].value = 2
    visits = {'A': [row('A', 'Start', 0, '08:00:00'), row('A', 'Platform', 1, '08:03:00', connections=(link,))],
              'B': [row('B', 'Platform', 0, '08:09:00'), row('B', 'End', 1, '08:12:00')]}
    a_before = platform_trace(('Start', 0, None), ('Platform', 10, 'P1'))
    a_after = platform_trace(('Start', 0, None), ('Platform', 20, 'P2'))
    b_before = platform_trace(('Platform', 11, None), ('End', 100, 'Term'))
    b_after = platform_trace(('Platform', 21, None), ('End', 100, 'Term'))
    moves = {('A', False): a_before, ('A', True): a_after, ('B', False): b_before, ('B', True): b_after}
    trace = lambda course, after: [moves[course, after]]
    proof, = _check_physical_links(track_graph(), visits, {'A': [], 'B': []}, trace, {})
    assert proof['reverse'] and proof['arrival_ends'] == [('Line', 20)] and proof['departure_ends'] == [('Line', 21)]
    moves['B', True] = b_before
    with pytest.raises(ValueError, match='separate linked endpoints'):
        _check_physical_links(track_graph(), visits, {'A': []}, trace, {})
