from pathlib import Path

import pytest

from opentrack_ai.current_archive.native_headway_tools import measure_course, normalized_options


def test_headway_configuration_comparison_rebases_only_declared_paths():
    first = b'Start Time#09:00:00#\nInfrastructure Document#/case1/track.opentrack#\nOutputPath#/case1/output#\n'
    second = first.replace(b'/case1/', b'/case2/')
    assert normalized_options(first, Path('/case1')) == normalized_options(second, Path('/case2'))
    with pytest.raises(ValueError, match='outside the frozen project'):
        normalized_options(first, Path('/case2'))
    changed = second.replace(b'09:00:00', b'09:01:00')
    assert normalized_options(first, Path('/case1')) != normalized_options(changed, Path('/case2'))


def test_delays_use_all_native_planned_events_and_ignore_unplanned_passes():
    departure = {'planned_s': 100, 'time_s': 103}
    pass_with_schedule = {'planned_s': 130, 'time_s': 138}
    pass_without_schedule = {'time_s': 139}
    terminal = {'planned_s': 160, 'time_s': 159}
    course = {'origin_event': departure, 'last_observed_event': terminal,
              'events': [departure, pass_with_schedule, pass_without_schedule, terminal]}
    measured = measure_course(course)
    assert measured['maximum_lateness_s'] == 8
    assert measured['worst_timing_event'] == pass_with_schedule
    assert measured['arrival_s'] == 159
    terminal['planned_s'] = None
    with pytest.raises(ValueError, match='Both endpoints'):
        measure_course(course)
