from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive.native_interlocking import decode_cycles
from opentrack_ai.current_archive import native_platform_choice as platform


def test_a_terminal_monitor_cannot_identify_two_saved_routes():
    def choice(resource, controls):
        return {'origin_end': ('Station', 7), 'platform_station_sign': 'EXT',
                'resource': {'document': 'Ext', 'safety_element_id': resource},
                'elements': {('Ext', number): [] for number in controls}}

    first = choice(34, [34, 55])
    second = choice(41, [41, 55])
    platform.validate_choice_resources([first, second])
    with pytest.raises(ValueError, match='only one'):
        platform.validate_choice_resources([first, choice(41, [34, 41, 55])])
    with pytest.raises(ValueError, match='same|one directed'):
        platform.validate_choice_resources([first, {**second, 'origin_end': ('Station', 8)}])


def test_availability_uses_physical_occupation_and_reservation_separately():
    preferred = {'itinerary': 'P1', 'cycle': {'reservation_s': [45, 67]}}
    alternate = {'itinerary': 'P2', 'cycle': {'reservation_s': [35, 60]}}
    blocker = {'course_id': 'BLOCKER', 'occupation_s': [20, 40], 'reservation_s': [10, 44]}
    check = platform.blocker_relation
    assert check('occupied_at_alternative_reservation', preferred, alternate, blocker, 30)['verified']
    assert not check('occupied_at_alternative_reservation', preferred, {
        **alternate, 'cycle': {'reservation_s': [42, 60]},
    }, blocker, 30)['verified']
    assert check('released_before_primary_reservation', preferred, preferred, blocker, 30)['verified']
    assert not check('released_before_primary_reservation', preferred, preferred, blocker, 45)['verified']
    assert check('unoccupied_at_primary_reservation', preferred, preferred, blocker, 45)['verified']


def test_reservation_without_physical_occupation_does_not_choose_platform():
    only_reserved = {'cycle': {'reservation_s': [6, 12], 'occupation_s': [None, None]}}
    same_timestamp = {'cycle': {'reservation_s': [6, 12], 'occupation_s': [12, 12]}}
    physically_used = {'cycle': {'reservation_s': [6, 12], 'occupation_s': [8, 12]}}
    assert not platform.occupied_cycle(only_reserved)
    assert not platform.occupied_cycle(same_timestamp)
    assert platform.occupied_cycle(physically_used)


def test_platform_decision_needs_matching_original_reservation_positions(monkeypatch):
    series = {
        'st1': {'units': ['s', 'km'], 'points': [(0, 0), (20, .098), (40, .2)]},
        'step1': {'units': ['s', 'km'], 'points': [(10, .1), (10, .2)]},
    }
    monkeypatch.setattr(platform.fmt, 'series', lambda _text, kind, _course: series[kind])
    run = SimpleNamespace(original_text=lambda _name: 'sealed original')
    selection = {'span': {'from_m': 100, 'to_m': 200}, 'route_length_m': 200,
                 'cycle': {'occupation_s': [20, 47], 'reservation_s': [10, 50]}}
    assert platform.verify_platform_motion(run, 'C', selection, 5)['final_position_m'] == 200
    series['step1']['points'] = [(10, .3), (10, .4)]
    with pytest.raises(ValueError, match='does not cover'):
        platform.verify_platform_motion(run, 'C', selection, 5)


def test_explicitly_empty_original_monitor_file_is_valid_when_enabled():
    empty = '// Produced by OpenTrack: sample\n// Desc. : OT_occ\n// x-Legend: [s]\n'
    assert decode_cycles(empty, 'Platform', allow_empty=True) == []
    with pytest.raises(ValueError, match='Missing or truncated'):
        decode_cycles(empty, 'Platform')


def test_priority_coverage_requires_physical_blocker_for_each_higher_choice():
    first = {'course_id': 'R1', 'reservation_s': [10, 60], 'occupation_s': [25, 56]}
    second = {'course_id': 'R2', 'reservation_s': [20, 65], 'occupation_s': [35, 61]}
    occupied = 'occupied_at_selected_reservation'
    clear = 'unreserved_at_selected_reservation'
    checked = lambda name, mode, row, clock: {'itinerary': name, **platform.availability_at_selection(mode, row, clock)}
    choices = ['P1', 'P2', 'P3']
    out = platform.occupied_priority_coverage(choices, 'P3', [checked('P1', occupied, first, 40)])
    assert out['missing_occupied_itineraries'] == ['P2'] and not out['verified']
    assert platform.occupied_priority_coverage(choices, 'P3', [
        checked('P1', occupied, first, 40), checked('P2', occupied, second, 40),
    ])['verified']
    assert not checked('P2', occupied, second, 30)['verified']  # Reserved, physically empty.
    assert not checked('P2', clear, second, 30)['verified']
    assert checked('P2', clear, second, 15)['verified']
    assert not checked('P2', occupied, second, 61)['verified']  # Exact clearance clock is ambiguous.


def test_throat_order_uses_native_clocks_and_not_course_row_order():
    rows = [
        {'course_id': 'D1', 'reservation_s': [10, 20], 'occupation_s': [11, 19]},
        {'course_id': 'D2', 'reservation_s': [40, 48], 'occupation_s': [41, 47]},
        {'course_id': 'TEST', 'reservation_s': [25, 33], 'occupation_s': [26, 31]},
    ]
    actual = platform.ordered_authorities(rows, ['D1', 'TEST', 'D2'])
    assert actual['verified'] and actual['release_to_next_reservation_s'] == [5, 7]
    assert not platform.ordered_authorities(rows, ['D1', 'D2', 'TEST'])['verified']
    with pytest.raises(ValueError, match='exactly one complete'):
        platform.ordered_authorities([*rows, rows[0]], ['D1', 'TEST', 'D2'])
