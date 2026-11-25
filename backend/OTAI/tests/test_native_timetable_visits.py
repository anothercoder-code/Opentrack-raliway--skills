import pytest

from opentrack_ai.current_archive.native_timetable_visit_tools import ExpectedVisit
from opentrack_ai.current_archive.native_timetable_visits import observe, series_at


def event(kind, actual, planned):
    return {'station': 'Same Station', 'kind': kind, 'time_s': actual, 'planned_s': planned}


def test_compared_planned_pass_can_be_printed_at_the_other_visit_departure():
    events = [event('Dep.', 30, 50), event('Pass', 30, 120), event('Pass', 90, None)]
    speeds = [(0, 60), (20, 0), (29, 0), (30, 10), (55, 60), (110, 60)]
    positions = [(0, 0), (20, 200), (30, 200), (50, 500), (80, 1300), (100, 1500), (110, 1700)]
    result, latest = observe(events, speeds, positions, [], {'distance_m': 1400},
                             ('Same Station', 120, 120), {'expected': 'pass'}, (1.05, 1), -1)
    assert result['verified'] and latest == 90
    assert result['passage']['planned_s'] is None
    assert result['original_planned_time_matches'] is False
    assert result['other_pass_events_reported_at_this_planned_time'] == [events[1]]
    earlier, _ = observe(events, speeds, positions, [], {'distance_m': 200},
                         ('Same Station', 120, 120), {'expected': 'pass'}, (1.05, 1), -1)
    assert earlier['verified'] is False


def test_stop_needs_the_exact_planned_pair_and_correct_physical_occurrence():
    events = [event('Arr.', 10, 20), event('Dep.', 18, 25), event('Arr.', 80, 90), event('Dep.', 95, 98)]
    segments = [{'start_s': 10, 'end_s': 18, 'duration_s': 8, 'distance_reference_m': 200},
                {'start_s': 80, 'end_s': 95, 'duration_s': 15, 'distance_reference_m': 1200}]
    positions = [(0, 0), (100, 1250)]
    visit = {'distance_m': 1200, 'stop_edge_length_m': 100}
    check = {'expected': 'stop', 'minimum_observed_dwell_s': 5}
    result, _ = observe(events, [], positions, segments, visit, ('Same Station', 20, 25), check, (1.05, 1), -1)
    assert result['verified'] is False
    result, latest = observe(events, [], positions, segments, visit, ('Same Station', 90, 98), check, (1.05, 1), -1)
    assert result['verified'] and latest == 95


def test_bounded_series_and_public_visit_validation():
    assert series_at([(10, 100), (25, 115)], 16) == 106
    assert series_at([(10, 100), (25, 115)], 30) is None
    request = {'visit_index': 7, 'station_sign': 'R2', 'reference_end': ['R2', 108], 'expected': 'stop'}
    with pytest.raises(ValueError, match='minimum observed dwell'):
        ExpectedVisit.model_validate(request)
    assert ExpectedVisit.model_validate({**request, 'minimum_observed_dwell_s': 5.0}).reference_end == ('R2', 108)
