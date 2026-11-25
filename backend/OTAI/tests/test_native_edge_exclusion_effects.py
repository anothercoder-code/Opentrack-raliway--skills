from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive.native_edge_exclusion_effects import (
    protection_effect, target_observations, verified_traversals,
)


def row(course, reserve, occupy):
    return {'course_id': course, 'reservation_s': reserve, 'occupation_s': occupy}


def test_protection_effect_sorts_native_cycles_and_accounts_for_excess_occupation():
    source = row('East', [10, 50], [20, 40])
    control = row('West', [12, 60], [33, 52])
    treatment = row('West', [50.01, 75], [56, 70])
    protection = row('East', [10, 50], [None, None])
    later = row('Extra', [76, 79], [77, 78])
    result = protection_effect('East', 'West', [source, control], [source, treatment],
                               [control], [later, protection, treatment])
    assert result['native_direct_exclusion_verified']
    assert result['original_target_protection_only_cycle'] == protection
    assert result['target_authority_handover_s'] == .01
    assert result['target_reservation_delay_s'] == 38.01
    assert result['control_physical_overlap_s'] == 7
    assert result['exclusion_physical_overlap_s'] == 0

    # A later reservation can be valid yet unrelated to the observed direct handover.
    intermediate = row('Extra', [50, 50.01], [None, None])
    blocked = protection_effect('East', 'West', [source, control], [source, treatment],
                                [control], [intermediate, treatment, protection])
    assert not blocked['native_direct_exclusion_verified']
    assert not blocked['checks']['protected_then_target_authorities_consecutive']


@pytest.mark.parametrize('reservation,occupation', [([10, 46], [None, None]), ([10, 50], [22, 31]),
                                                    ([10, None], [None, None])])
def test_rejects_unmatched_or_physically_occupied_protection(reservation, occupation):
    source = row('East', [10, 50], [20, 40])
    control = row('West', [12, 60], [33, 52])
    treatment = row('West', [50.01, 75], [56, 70])
    protection = row('East', reservation, occupation)
    with pytest.raises(ValueError, match='match the original|target reservation-only'):
        protection_effect('East', 'West', [source, control], [source, treatment], [control], [treatment, protection])


def test_rejects_right_monitor_with_wrong_edge_or_crossing_saved_route():
    a = {'document': 'J22', 'safety_element_id': 7, 'route_edge_ids': [289]}
    b = {'document': 'J22', 'safety_element_id': 146, 'route_edge_ids': [322]}
    routes = {'East': {'spans': {('J22', 7): [{}]}}, 'West': {'spans': {('J22', 146): [{}]}}}
    run = SimpleNamespace(traversal=lambda course, *_: a if course == 'East' else b, routes=routes)
    assert verified_traversals(run, ['East', 'West'], [{}, {}], [289, 322], 5) == [a, b]
    with pytest.raises(ValueError, match='exact selected Edges'):
        verified_traversals(run, ['East', 'West'], [{}, {}], [321, 322], 5)
    routes['East']['spans'][('J22', 146)] = [{}]
    with pytest.raises(ValueError, match='respective monitored Safety Element'):
        verified_traversals(run, ['East', 'West'], [{}, {}], [289, 322], 5)


def test_approach_stop_uses_metre_origin_and_original_authority_end():
    start = {'start_s': 25, 'end_s': 30, 'duration_s': 5.0, 'distance_reference_m': 1000}
    approach = {'start_s': 31, 'end_s': 35, 'duration_s': 4.0, 'distance_reference_m': 1050}
    out = {'start_s': 45, 'end_s': 55, 'duration_s': 10.0, 'distance_reference_m': 2000}
    before = {'stationary_intervals': [out], 'last_observed_event': {'time_s': 40}}
    after = {'stationary_intervals': [start, approach, out], 'last_observed_event': {'time_s': 45},
             'distance': {'first': [25, 1], 'units': ['s', 'km']}}
    span = {'from_m': 1080, 'reservation_s': [35, 39]}
    protection = {'reservation_s': [28, 35]}
    result = target_observations(before, after, span, protection, 5)
    assert result['verified_approach_stop_ending_at_target_authority'] == {
        **approach, 'control_stop_at_same_position': False,
    }
    assert result['original_terminal_event_change_s'] == 5
    after['distance']['first'][1] = 1.05
    assert target_observations(before, after, span, protection, 5)[
        'verified_approach_stop_ending_at_target_authority'] is None
