import pytest

from opentrack_ai.current_archive.native_delay_batch_tools import aggregate, distribution, union_seconds
from opentrack_ai.current_archive.native_evaluation_formats import protocol


def test_occupation_union_does_not_double_count_parallel_members():
    assert union_seconds([(103.0, 120.0), (110.0, 130.0), (145.0, 160.0)], (100, 200)) == 42
    assert union_seconds([(99.99, 101), (200, 200.01)], (100, 200)) == 1
    with pytest.raises(ValueError, match='outside the frozen run window'):
        union_seconds([(90, 99)], (100, 200))


def test_batch_statistics_exclude_control_and_keep_missing_resource_data_distinct():
    row = {'document': 'J22', 'name': 'Shared', 'native_statistics': {
        'occupation_count': 17, 'average_reservation_percentage': 27.05},
        'reservation_union_s': 80, 'occupation_union_s': 60}
    timing = {'course_id': 'T1', 'departure_delay_s': 10, 'terminal_delay_s': 20,
              'terminal_within_threshold': True}
    observations = [
        {'scenario': 0, 'course_timings': [dict(timing, terminal_delay_s=0)], 'resources': [row]},
        {'scenario': 7, 'course_timings': [timing], 'resources': [row]},
        {'scenario': 17, 'course_timings': [dict(timing, terminal_delay_s=200, terminal_within_threshold=False)],
         'resources': [dict(row, native_statistics=None, occupation_union_s=None, reservation_union_s=None)]},
    ]
    report = aggregate(180, 'OTAI/job', observations, observations[1:])
    assert report['observations'][0]['scenario'] == 0
    assert report['verified_numbered_scenarios'] == [7, 17]
    timings, = report['course_statistics']
    assert timings['terminal_delay_s']['median'] == 110
    assert timings['terminal_delay_s']['p95_nearest_rank'] == 200
    assert timings['within_threshold_count'] == 1
    resource, = report['resource_statistics']
    assert resource['verified_trials'] == 2
    assert resource['occupation_union_s']['samples'] == 1
    assert resource['occupation_total_s'] == 60
    assert resource['native_average_reservation_pct']['samples'] == 1
    assert distribution([]) is None


def test_original_protocol_loads_eight_occupation_columns():
    text = ('// Produced by OpenTrack: sample\n// Desc. : OT_protocol\n'
            'Scenario:\nDelay Scenario    : 17\nOccupations:\n'
            'J22_Safety23\t17\t17.00\t17.00\t0.00\t27.05\t27.05\t0.00\n')
    result = protocol(text)
    assert result['delay_scenario'] == '17'
    row, = result['occupation_statistics']
    assert row['name'] == 'J22_Safety23'
    assert row['count'] == 17
    assert row['mean_reservation_pct'] == 27.05
