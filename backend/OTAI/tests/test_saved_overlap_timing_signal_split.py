"""Review exact protection and independent timers for a native Overlap split."""

from copy import deepcopy

import pytest

from opentrack_ai.current_archive.saved_overlap_timing_signal_split import (
    check_overlap_release_delay, plan_overlap_release_delay,
)
from opentrack_ai.current_archive.saved_timing_signal_split import DEFAULT_ROUTE_TIMING


@pytest.fixture
def protections():
    overlap = {'shunting': {'document': 'WB', 'name': 'M15_WB_Runout', 'array_id': 0, 'start_id': 8},
               'end_ids': [8, 12, 16], 'edge_ids': [22, 23], 'safety_element_ids': [11, 15],
               'release_time_s': 35, 'reservation_time_s': 0, 'shunting_speed_kmh': 30.0}
    route_delays = {**DEFAULT_ROUTE_TIMING, 'release_time_s': 9}
    timing = {'original': deepcopy(route_delays), 'upstream': deepcopy(route_delays), 'downstream': deepcopy(route_delays),
              'new_release_boundary': ('WB', 4), 'terminal_release_boundary': ('WB', 8),
              'terminal_m_from_original_route_origin': 2200, 'terminal_release_m_from_original_route_origin': 2200,
              'terminal_approach_m_from_original_route_origin': None}
    return overlap, timing


def test_native_release_seconds_are_kept_on_both_routes_and_shunting(protections):
    overlap, timing = protections
    plan = plan_overlap_release_delay(overlap, timing, reserve_with_previous=True)
    assert plan['upstream_release'] == {'end': ('WB', 4), 'route_delay_s': 9}
    assert plan['downstream_release'] == {'end': ('WB', 8), 'route_delay_s': 9}
    assert plan['terminal_overlap'] == {
        'shunting': overlap['shunting'], 'edge_ids': [22, 23], 'safety_element_ids': [11, 15],
        'shunting_release_delay_s': 35,
    }
    saved = {**overlap, 'synchronized_reservation': True, 'upstream_reference_cleared': True}
    assert check_overlap_release_delay(plan, saved, timing)['native_joint_readback_verified']


@pytest.mark.parametrize(('field', 'value'), [
    ('reserve_time_s', 3),
    ('release_distance_m', 10),
    ('use_release_distance', True),
    ('reservation_distance_m', 5100),
    ('use_reservation_distance', True),
    ('approach_length_m', 10),
    ('approach_speed_kmh', 20),
    ('release_time_s', 0),
    ('release_time_s', 5),
])
def test_overlap_rejects_unreviewed_timing_or_approach(protections, field, value):
    overlap, timing = protections
    timing['original'][field] = value
    with pytest.raises(ValueError, match='default reservation and distance|length and speed together'):
        plan_overlap_release_delay(overlap, timing, reserve_with_previous=True)


def test_overlap_requires_synchronized_reservation_and_exact_terminal(protections):
    overlap, timing = protections
    with pytest.raises(ValueError, match='synchronized reservation'):
        plan_overlap_release_delay(overlap, timing, reserve_with_previous=False)
    with pytest.raises(ValueError, match='zero Shunting reservation delay'):
        plan_overlap_release_delay({**overlap, 'reservation_time_s': 3}, timing, reserve_with_previous=True)
    with pytest.raises(ValueError, match='original effective terminal'):
        plan_overlap_release_delay({**overlap, 'shunting': {**overlap['shunting'], 'start_id': 12}},
                                   timing, reserve_with_previous=True)


def test_cold_read_rejects_reset_release_or_changed_shunting_delay(protections):
    overlap, timing = protections
    plan = plan_overlap_release_delay(overlap, timing, reserve_with_previous=True)
    saved = {**overlap, 'synchronized_reservation': True, 'upstream_reference_cleared': True}
    with pytest.raises(ValueError, match='independent releases differ'):
        check_overlap_release_delay(plan, {**saved, 'release_time_s': 9}, timing)
    with pytest.raises(ValueError, match='independent releases differ'):
        check_overlap_release_delay(plan, {**saved, 'upstream_reference_cleared': False}, timing)
    timing['upstream']['release_time_s'] = 5
    with pytest.raises(ValueError, match='positive Route release seconds'):
        check_overlap_release_delay(plan, saved, timing)


@pytest.mark.parametrize('release', [5, 9])
def test_terminal_approach_is_kept_entirely_on_the_overlap_owner(protections, release):
    overlap, timing = protections
    timings = {**DEFAULT_ROUTE_TIMING, 'release_time_s': release}
    approach = {**timings, 'approach_length_m': 400.0, 'approach_speed_kmh': 28.0}
    timing.update(original=approach, upstream=timings, downstream=dict(approach),
                  cut_m_from_original_route_origin=1700, terminal_approach_m_from_original_route_origin=[1800, 2200])
    plan = plan_overlap_release_delay(overlap, timing, reserve_with_previous=True)
    assert plan['terminal_approach'] == {'end': ('WB', 8), 'distance_m_from_original_route_origin': [1800, 2200],
                                         'length_m': 400, 'speed_kmh': 28}
    assert plan['downstream_release']['route_delay_s'] == release
    saved = {**overlap, 'synchronized_reservation': True, 'upstream_reference_cleared': True}
    assert check_overlap_release_delay(plan, saved, timing)['native_joint_readback_verified']

    timing['cut_m_from_original_route_origin'] = 1801
    with pytest.raises(ValueError, match='complete reviewed terminal approach interval'):
        plan_overlap_release_delay(overlap, timing, reserve_with_previous=True)
    timing['cut_m_from_original_route_origin'] = 1800
    assert plan_overlap_release_delay(overlap, timing, reserve_with_previous=True) == plan
    timing['downstream']['approach_speed_kmh'] = 27.0
    with pytest.raises(ValueError, match='approach confined to the downstream Route'):
        check_overlap_release_delay(plan, saved, timing)


def test_terminal_approach_cannot_mix_with_positive_reservation_delay(protections):
    overlap, timing = protections
    defaults = timing['original']
    constrained = {**defaults, 'approach_length_m': 400.0, 'approach_speed_kmh': 28.0}
    timing.update(original={**constrained, 'reserve_time_s': 12},
                  upstream={**defaults, 'reserve_time_s': 12}, downstream=constrained,
                  cut_m_from_original_route_origin=1700, terminal_approach_m_from_original_route_origin=[1800, 2200])
    with pytest.raises(ValueError, match='default reservation and distance'):
        plan_overlap_release_delay(overlap, timing, reserve_with_previous=True)
