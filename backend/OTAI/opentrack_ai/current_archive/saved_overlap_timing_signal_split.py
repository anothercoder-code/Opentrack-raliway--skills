"""Keep a terminal Shunting overlap and the final main Route's approach and release."""

from math import isfinite

from .multi_document.core import need
from .saved_timing_signal_split import DEFAULT_ROUTE_TIMING


def plan_overlap_release_delay(overlap, timing, *, reserve_with_previous):
    """Retain the terminal slip owner with independent main Route approach and release."""
    need(reserve_with_previous is True,
         'Terminal overlap and Route timing require synchronized reservation')
    original = timing['original']
    release = original['release_time_s']
    length, speed = original['approach_length_m'], original['approach_speed_kmh']
    need(all(type(value) in (int, float) and isfinite(value) for value in (length, speed))
         and 0 <= length <= 10 ** 7 and 0 <= speed <= 1000 and (length > 0) == (speed > 0),
         'Terminal overlap requires an exact whole terminal approach length and speed together')
    expected = {**DEFAULT_ROUTE_TIMING, 'release_time_s': release}
    downstream = {**expected, 'approach_length_m': length, 'approach_speed_kmh': speed}
    need(type(release) is int and 0 < release <= 86400
         and (length > 0 or release != DEFAULT_ROUTE_TIMING['release_time_s'])
         and timing['upstream'] == expected and original == timing['downstream'] == downstream
         and timing['terminal_release_m_from_original_route_origin'] == timing['terminal_m_from_original_route_origin'],
         'Terminal overlap requires default reservation and distance settings, positive Route release seconds '
         'and any reviewed approach confined to the downstream Route')
    terminal_m = timing['terminal_m_from_original_route_origin']
    expected_approach = [terminal_m - length, terminal_m] if length else None
    need(timing['terminal_approach_m_from_original_route_origin'] == expected_approach
         and (not length or timing['cut_m_from_original_route_origin'] <= expected_approach[0]),
         'The downstream Route must contain the complete reviewed terminal approach interval')
    shunt = overlap['shunting']
    terminal = timing['terminal_release_boundary']
    need((shunt['document'], shunt['start_id']) == terminal and overlap['reservation_time_s'] == 0,
         'The terminal overlap must begin at the original effective terminal and have zero Shunting reservation delay')

    # OTInterlock creates per-Route releases; OTDest builds the terminal
    # SlipInfo from the Shunting and executes its separate release schedule.
    result = {
        'upstream_release': {'end': timing['new_release_boundary'], 'route_delay_s': release},
        'downstream_release': {'end': terminal, 'route_delay_s': release},
        'terminal_overlap': {'shunting': shunt, 'edge_ids': overlap['edge_ids'],
                             'safety_element_ids': overlap['safety_element_ids'],
                             'shunting_release_delay_s': overlap['release_time_s']},
        'synchronized_reservation': True,
    }
    if length:
        result['terminal_approach'] = {'end': terminal, 'distance_m_from_original_route_origin': expected_approach,
                                       'length_m': length, 'speed_kmh': speed}
    return result


def check_overlap_release_delay(planned, saved_overlap, saved_timing):
    """Check the joint release contract after both native archive readbacks."""
    saved = plan_overlap_release_delay(
        saved_overlap, saved_timing, reserve_with_previous=saved_overlap['synchronized_reservation'])
    need(saved == planned and saved_overlap['upstream_reference_cleared'],
         'The saved terminal SlipInfo owner, approach or independent releases differ after native cold read')
    return {**saved, 'native_joint_readback_verified': True}
