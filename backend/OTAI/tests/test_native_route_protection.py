import pytest

from opentrack_ai.current_archive import native_route_protection as protection


def test_matched_speed_uses_exact_native_clocks_and_does_not_interpolate():
    speed = {'points': [(2.1, 20), (2.2, 20.0), (2.4, 40)], 'units': ['s', 'mph']}
    front = [(2.1, 10), (2.2, 15), (2.3, 18), (2.4, 20)]
    points = protection.joined_motion(speed, front)
    assert [time for time, _, _ in points] == [2.1, 2.2, 2.4]
    assert [value for _, _, value in points] == pytest.approx([32.18688, 32.18688, 64.37376])
    with pytest.raises(ValueError, match='Conflicting original speed values'):
        protection.joined_motion({**speed, 'points': [*speed['points'], (2.2, 30)]}, front)


def test_fixed_metric_cap_needs_actual_distinct_at_cap_positions_on_each_side():
    samples = [(1.0, 5.0, 20), (1.5, 8.0, 40), (1.6, 8.0, 40), (2.0, 12.0, 40), (3.0, 20.0, 0)]
    assert protection.speed_window(samples, 0, 20, 40)['near_fixed_speed_samples'] == 2
    assert protection.speed_window(samples, 0, 20, None)['near_fixed_speed_samples'] is None
    with pytest.raises(ValueError, match='does not corroborate'):
        protection.speed_window(samples[:3] + [(2.0, 12.0, 39.0)], 0, 20, 40)
    with pytest.raises(ValueError, match='does not corroborate'):
        protection.speed_window(samples + [(2.4, 16.0, 42.0)], 0, 20, 40)


def test_signal_legend_binds_the_physical_signal_coordinate_and_one_saved_aspect():
    text = ('// Produced by OpenTrack: Mon Nov 23 19:37:18 2026\n'
            '// Signal Positions of Course: A\n// Itineraries: 1: Exact\n'
            '// Type    : OT_Legend\n// Desc.   : OT_Signals\n// x-Legend: [km]\n'
            '0.1000\tMS\tS:East\t40\n')
    route = {'origin_signal': 'S:East', 'route_start_m': 100, 'fixed_speed_kmh': 40}
    assert protection.signal_legend(text, 'A', 'Exact', route) == '40'
    with pytest.raises(ValueError, match='does not bind'):
        protection.signal_legend(text.replace('0.1000', '0.2000'), 'A', 'Exact', route)
    with pytest.raises(ValueError, match='differs from the frozen single aspect'):
        protection.signal_legend(text.replace('\t40', '\t40, 60'), 'A', 'Exact', route)
    assert protection.signal_legend(text.replace('\t40', '\tTS'), 'A', 'Exact',
                                    {**route, 'fixed_speed_kmh': None}) == 'TS'


def test_release_reaches_exact_physical_boundary_at_fractional_clock_between_front_samples():
    route = {'release_group_starts': [{'end': ['RDG', 9], 'distance_m': 0},
                                      {'end': ['RDG', 29], 'distance_m': 100},
                                      {'end': ['EA', 9], 'distance_m': 300}]}
    run = {'origin_m': 0, 'terminal_m': 300}
    front = [(1.0, 0), (5.0, 110), (5.2, 120), (8.0, 300)]
    times = [t for t, _ in front]
    reserved = [{'time_s': 1, 'from_m': 0, 'to_m': 300}]
    released = [{'time_s': 5.1, 'from_m': 0, 'to_m': 100}]
    first, middle, last = protection.release_boundaries(route, run, front, times, reserved, released)
    assert first['kind'] == last['kind'] == 'course_endpoint_archive_anchor'
    assert middle['advance']['time_s'] == 5.1 and middle['front_bracket_s_m'] == [[5.0, 110], [5.2, 120]]
    with pytest.raises(ValueError, match='No original release advance'):
        protection.release_boundaries(route, run, front, times, reserved, [{**released[0], 'to_m': 99}])
    with pytest.raises(ValueError, match='lacks prior original reservation'):
        protection.release_boundaries(route, run, front, times, [{**reserved[0], 'from_m': 150}], released)
    with pytest.raises(ValueError, match='downstream front movement'):
        protection.release_boundaries(route, run, front, times, reserved, [{**released[0], 'time_s': 4.0}])
