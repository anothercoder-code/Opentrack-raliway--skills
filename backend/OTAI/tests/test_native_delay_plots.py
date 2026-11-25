from collections import Counter

import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.native_delay_batch_tools import distribution
from opentrack_ai.current_archive.native_delay_plots import (
    PLOTS, attach_rows, named_summary, parse_plot, verified_plots, wilson,
)
from opentrack_ai.current_archive.zero_operations import station_binding
from test_operating_plan_edit import native_record


def plot(kind, rows, scenario=17):
    suffix = 'laststop' if kind == 'dellaststop' else kind[3:]
    return ('// Produced by OpenTrack: fixture\n// Type    : OT_BarYPlot\n// Desc.   : OT_delay' + suffix
            + f'\n// Scenario: Adh. Outside: good / Delay: {scenario} / Step: 0.2 s\n'
            + '// y-Legend: [s]\n' + '\n'.join('\t'.join(row) for row in rows) + '\n')


def test_signed_delays_and_current_placeholder_use_exact_original_formats():
    assert parse_plot(plot('delavg', [('T', '-0.8', '')]), 'delavg', 17) == [('T', '', None, -.8)]
    assert parse_plot(plot('delact', [('', '0.0', '', '00:00:00')]), 'delact', 17) == [('', '', '00:00:00', 0)]
    with pytest.raises(ValueError, match='scenario'):
        parse_plot(plot('delavg', [('T', '0.0', '')]), 'delavg', 18)
    with pytest.raises(ValueError, match='placeholder'):
        parse_plot(plot('delact', [('T', '0.0', '', '00:00:00')]), 'delact', 17)


def test_repeated_clock_refuses_ambiguous_fractional_values_across_days():
    record = {'course_id': 'T', 'station_sign': 'A', 'clock': '00:01:00', 'integer_delay_s': 0}
    a, b = dict(record, event_index=0), dict(record, event_index=3)
    repeated = [('T', 'A', '00:01:00', .0), ('T', 'A', '00:01:00', .2)]
    with pytest.raises(ValueError, match='Ambiguous'):
        attach_rows(repeated, [a, b])
    repeated[1] = repeated[0]
    assert Counter(row['original_delay_s'] for row in attach_rows(repeated, [a, b])) == {0: 2}


def test_all_nine_plots_reconcile_arrival_departure_average_and_cross_midnight_clock():
    source = {sign: native_record('OTStation', 3, ['i', '@', '@', 'i', 'iii', 'ii', '@', 'i', '@', '@'],
                                 {0: [17], 1: [station_binding.string(sign)], 2: [station_binding.string(sign)]})
              for sign in ('A', 'B', 'C')}
    station_bytes = writer.dump_verified(station_binding.dictionary(source.items()))
    expected = {
        'delall': [('T', '20.4', 'B', '00:05:20'), ('T', '4.2', 'A', '23:59:04'), ('T', '-3.8', 'C', '00:09:56')],
        'delallarr': [('T', '-3.8', 'C', '00:09:56')],
        'delalldep': [('T', '4.2', 'A', '23:59:04')],
        'delbegin': [('T', '4.2', 'A', '23:59:04')],
        'delend': [('T', '-3.8', 'C', '00:09:56')],
        'delavg': [('T', '0.2', '')],
        'delmax': [('T', '4.2', 'A', '23:59:04')],
        'dellaststop': [('T', '-3.8', 'C', '00:09:56')],
        'delact': [('', '0.0', '', '00:00:00')],
    }
    files = {'OT_Delay.' + suffix: plot(suffix, expected[suffix]) for suffix in PLOTS}
    evaluation = {'protocol': {'used_courses': ['T']}, 'courses': [{'course_id': 'T', 'events': [
        {'station': 'A', 'kind': 'Dep.', 'clock': '23:59:04', 'time_s': 86344, 'planned_s': 86340},
        {'station': 'B', 'kind': 'Pass', 'clock': '1 / 00:05:20', 'time_s': 86720, 'planned_s': 86700},
        {'station': 'C', 'kind': 'Arr.', 'clock': '1 / 00:09:56', 'time_s': 86996, 'planned_s': 87000},
    ]}]}

    class OriginalFiles:
        expected_hashes = files

        def read(self, name):
            return files[name]

    result = verified_plots(OriginalFiles(), evaluation, station_bytes, 17)
    assert result['verified'] and result['matched_passages'] == 1
    course, = result['courses']
    assert course['terminal_event']['time_s'] == 86996
    assert course['terminal_event']['original_delay_s'] == -3.8
    assert course['mean_arrival_departure_delay_s'] == .2
    assert course['maximum_nonnegative_arrival_departure_delay_s'] == 4.2
    files['OT_Delay.delmax'] = plot('delmax', [('T', '20.4', 'B', '00:05:20')])
    with pytest.raises(ValueError, match='nonnegative arrival/departure maximum'):
        verified_plots(OriginalFiles(), evaluation, station_bytes, 17)


def test_precision_changes_binary_threshold_and_confidence_uses_scenarios():
    course = {'course_id': 'T', 'terminal_event': {'integer_delay_s': 108, 'original_delay_s': 108.6},
              'initial_event': {'original_delay_s': 122.4}, 'mean_arrival_departure_delay_s': 115.5}
    scenario = {'original_delay_plots': {'verified': True, 'courses': [course]}}
    cases = [dict(scenario, scenario=i) for i in range(9)]
    summary = named_summary(cases, 108, .95, distribution)
    assert summary['scenario_all_courses_within_threshold_count'] == 0
    assert summary['integer_tt_all_courses_within_threshold_count'] == 8
    assert summary['scenario_level_conditional_wilson_interval'] == wilson(0, 8, .95) == [0, .32440756]
    assert summary['courses'][0]['integer_tt_and_named_threshold_disagreement_count'] == 8
    incomplete = named_summary([*cases, {'scenario': 9}], 108, .95, distribution)
    assert incomplete['scenario_level_conditional_wilson_interval'] is None
    assert incomplete['excluded_from_terminal_comparison'] == [9]
    census = named_summary([dict(scenario, scenario=i) for i in range(1, 201)], 108, .95, distribution)
    assert census['confidence_status'] == 'full_finite_scenario_enumeration'
    assert census['scenario_level_conditional_wilson_interval'] is None
