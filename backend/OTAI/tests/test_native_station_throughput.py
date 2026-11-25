from pathlib import Path
from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive.native_station_throughput import (
    configured_window, reconcile_totals, rolling_peak, station_timelines, summarize_window,
)


def observation(clock, kind, station):
    return {'time_s': clock, 'kind': kind, 'station': station}


def course(course_id, *events):
    return {'course_id': course_id, 'events': events, 'origin_event': events[0],
            'last_observed_event': events[-1]}


def test_midnight_intervals_keep_station_event_counts_separate_from_course_ends():
    names = {'E': 'Entry', 'H': 'Hub', 'T': 'Terminal'}
    schedules = [
        course('C1', observation(86160, 'Dep.', 'Entry'), observation(86370, 'Arr.', 'Hub'),
               observation(86400, 'Dep.', 'Hub'), observation(86400, 'Pass', 'Hub'),
               observation(86700, 'Arr.', 'Terminal')),
        course('C2', observation(86400, 'Dep.', 'Hub'), observation(86700, 'Pass', 'Terminal')),
    ]
    timeline = station_timelines(schedules, names, 86100, 87000)
    data = [
        {'station': 'E', 'arrivals': 0, 'departures': 1, 'passes': 0},
        {'station': 'H', 'arrivals': 1, 'departures': 2, 'passes': 1},
        {'station': 'T', 'arrivals': 1, 'departures': 0, 'passes': 1},
    ]
    assert len(reconcile_totals(data, timeline, names)) == 3
    before = summarize_window(timeline['H'], 86100, 86400, 60)
    after = summarize_window(timeline['H'], 86400, 87000, 60)
    assert before['event_counts']['arrivals'] == 1 and before['event_counts']['departures'] == 0
    assert after['event_counts']['departures'] == 2 and after['event_counts']['origin_departures'] == 1
    assert after['event_counts']['passes'] == 1 and after['distinct_course_count'] == 2
    assert after['event_counts']['station_events'] == 3 and after['event_counts']['terminal_completions'] == 0
    terminal = summarize_window(timeline['T'], 86400, 87000, 60)
    assert terminal['event_counts']['terminal_arrivals'] == 1
    assert terminal['event_counts']['terminal_passes'] == 1
    assert terminal['event_counts']['terminal_completions'] == 2


def test_roll_forward_uses_half_open_integer_grid_and_earliest_peak():
    events = [{'time_s': stamp} for stamp in (3, 3, 6, 7, 7, 10)]
    for width in range(1, 13):
        count_per_start = [sum(start <= event['time_s'] < start + width for event in events)
                           for start in range(13 - width)]
        measured = rolling_peak(events, 0, 12, width)
        assert measured['count'] == max(count_per_start)
        assert measured['start_s'] == count_per_start.index(max(count_per_start))
        assert measured['stop_s'] == measured['start_s'] + width
    assert rolling_peak(events, 0, 12, 3)['start_s'] == 5
    assert rolling_peak([], 0, 12, 4)['first_event'] is None


def test_rejects_unresolved_labels_and_missing_or_mismatched_native_station_counts():
    observed = course('C', observation(3, 'Dep.', 'Origin'), observation(7, 'Arr.', 'Terminal'))
    with pytest.raises(ValueError, match='ambiguous frozen station label'):
        station_timelines([observed], {'A': 'Origin', 'B': 'Origin', 'T': 'Terminal'}, 0, 10)
    names = {'A': 'Origin', 'T': 'Terminal'}
    completed = station_timelines([observed], names, 0, 10)
    with pytest.raises(ValueError, match='disagree'):
        reconcile_totals([{'station': 'A', 'arrivals': 0, 'departures': 1, 'passes': 0}], completed, names)
    with pytest.raises(ValueError, match='Negative'):
        reconcile_totals([{'station': 'A', 'arrivals': 0, 'departures': -1, 'passes': 0}], completed, names)


def test_original_protocol_window_must_match_frozen_days_in_both_directions():
    file = b'Start Day Offset#0#\nStart Time#23:15:00#\nStop Day Offset#1#\nStop Time#01:30:00#\n'
    run = SimpleNamespace(settings={'project_root': Path('C:/fixture')}, dependency=lambda _: file,
                          receipt={'protocol': {'configured_window': '23:15:00 - 1 / 01:30:00'}})
    assert configured_window(run, {'input_sha256': {'line.run': 'digest'}}) == [83700, 91800]
    run.receipt['protocol']['configured_window'] = '23:14:00 - 1/01:30:00'
    with pytest.raises(ValueError, match='configured window differ'):
        configured_window(run, {'input_sha256': {'line.run': 'digest'}})
