"""Retain ordinary Route release timing and a separately authorized occupied entry."""

from math import isfinite

from .multi_document.core import need
from .saved_timing_signal_split import DEFAULT_ROUTE_TIMING


def _disjoint_terminal_approach(entry, timing):
    mode, entry_speed, wait = entry['values']
    original = timing['original']
    length, approach_speed = original['approach_length_m'], original['approach_speed_kmh']
    speed_entry = mode == 3 and entry_speed > 0 and wait == 0
    wait_entry = mode == 7 and entry_speed == 0 and 0 < wait <= 86400 and int(wait) == wait
    need((speed_entry or wait_entry)
         and all(type(value) in (float, int) and isfinite(value) and value > 0
                 for value in (length, approach_speed)),
         'The terminal approach requires speed-only or zero-speed timed occupied entry and a native positive approach zone')
    terminal = timing['terminal_m_from_original_route_origin']
    interval = [terminal - length, terminal]
    need(interval == timing['terminal_approach_m_from_original_route_origin']
         and timing['cut_m_from_original_route_origin'] <= interval[0],
         'The entire terminal approach zone must belong to the occupied-entry suffix')
    berth = entry['berth']
    head, contact = berth['head'], berth['contact']
    edge = {'document': head['document'], 'edge_id': head['edge_id']}
    start_offset = head['offset_m'] - length
    need(berth['platform_edges'] == [edge] and all(contact[key] == value for key, value in edge.items())
         and start_offset > contact['offset_m'],
         'The terminal approach zone must start strictly beyond the donor contact on the same directed stopping Edge')
    return {'terminal': timing['terminal_release_boundary'], 'speed_kmh': approach_speed,
            'distance_m_from_original_route_origin': interval, 'edge': edge,
            'start_offset_m': start_offset, 'end_offset_m': head['offset_m'],
            'donor_contact_offset_m': contact['offset_m'],
            'clear_distance_beyond_contact_m': start_offset - contact['offset_m']}


def plan_occupied_release_delay(entry, timing, *, reserve_with_previous, preserve_terminal_approach=False):
    """Review release seconds independently of the native occupied-entry authorization."""
    need(reserve_with_previous is False,
         'Timed occupied entry requires separate downstream reservation')
    delay = timing['original']['release_time_s']
    expected = {**DEFAULT_ROUTE_TIMING, 'release_time_s': delay}
    downstream = expected
    approach = None
    entry_halt = None
    if preserve_terminal_approach:
        approach = _disjoint_terminal_approach(entry, timing)
        downstream = {**expected, 'approach_length_m': timing['original']['approach_length_m'],
                      'approach_speed_kmh': timing['original']['approach_speed_kmh']}
        if entry['values'][0] == 7:
            entry_halt = {'end': timing['new_release_boundary'], 'saved_wait_s': int(entry['values'][2]),
                          'distance_to_terminal_approach_m': approach['distance_m_from_original_route_origin'][0]
                          - timing['cut_m_from_original_route_origin']}
    need(type(delay) is int and 0 < delay <= 86400 and delay != DEFAULT_ROUTE_TIMING['release_time_s']
         and timing['upstream'] == expected and timing['original'] == timing['downstream'] == downstream
         and (approach is not None or timing['terminal_approach_m_from_original_route_origin'] is None)
         and timing['terminal_release_m_from_original_route_origin'] == timing['terminal_m_from_original_route_origin'],
         'Occupied entry requires a positive nondefault Route release delay and default reservation, distance and approach settings '
         'apart from an explicitly reviewed terminal approach')
    terminal = timing['terminal_release_boundary']
    station_end = entry['berth']['station_end']
    need(terminal == (station_end['document'], station_end['end_id']),
         'The timed occupied-entry suffix must terminate at the reviewed directed berth')
    return {
        'upstream_release': {'end': timing['new_release_boundary'], 'route_delay_s': delay},
        'occupied_entry_release': {'end': terminal, 'route_delay_s': delay},
        'occupancy': {key: entry[key] for key in ('receiver_course', 'donor_course', 'values', 'berth')},
        'independent_reservation': True,
        **({'terminal_approach': approach} if approach is not None else {}),
        **({'scheduled_zero_speed_at_entry': entry_halt} if entry_halt is not None else {}),
    }


def check_occupied_release_delay(planned, saved_entry, saved_timing):
    observed = plan_occupied_release_delay(saved_entry, saved_timing,
                                           reserve_with_previous=not saved_entry['independent_reservation'],
                                           preserve_terminal_approach='terminal_approach' in planned)
    need(observed == planned and saved_entry['upstream_reset'],
         'The saved independent entry or its Route release timing differs after native cold read')
    return {**observed, 'native_joint_readback_verified': True}
