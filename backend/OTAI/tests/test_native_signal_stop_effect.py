import pytest

from opentrack_ai.current_archive.native_incident_effects import PHYSICS_LOG_OPTION, checked_inputs
from opentrack_ai.current_archive.native_signal_stop_effect import matched_stop, stop_warnings


def observed(reserve, depart, dwell, count, *, position=2025, station='Platform 9'):
    return {'position_m': position, 'reservation_s': reserve, 'stationary': {'start_s': 100, 'duration_s': dwell},
            'resumed': {'time_s': reserve + .5, 'position_m': 2025.2},
            'outcome': {'statistics': {'signal_stops': count}, 'events': [
                {'kind': 'Arr.', 'station': station, 'time_s': 100, 'planned_s': 100},
                {'kind': 'Dep.', 'station': station, 'time_s': depart, 'planned_s': 220},
            ]}}


def test_completed_hold_preserves_scheduled_stop_and_reports_exact_additional_wait():
    control = observed(220.91, 220, 120.91, 0)
    treatment = observed(263.14, 263, 163.14, 1)
    result = matched_stop(control, treatment, [190, 350], 220, 42, .2)
    assert result['verified_effect']
    assert result['additional_stationary_time_s'] == 42.23
    assert result['departure_event_change_s'] == 43
    assert result['incident_first_running_sample_past_signal']['time_s'] == 263.64
    assert not matched_stop(control, treatment, [190, 350], 220, 41, .2)['verified_effect']
    assert not matched_stop(control, observed(263.14, 263, 163.14, 0), [190, 350], 220, 42, .2)['verified_effect']


@pytest.mark.parametrize(('position', 'station', 'active'), [
    (2000, 'Platform 9', [190, 350]), (2025, 'Platform 8', [190, 350]), (2025, 'Platform 9', [190, 263.5]),
])
def test_stop_proof_rejects_another_position_departure_or_resumption_after_incident(position, station, active):
    with pytest.raises(ValueError, match='common station stop|common planned station departure|finite hold'):
        matched_stop(observed(220.91, 220, 120.91, 0), observed(263.14, 263, 163.14, 1,
                     position=position, station=station), active, 220, 42, .2)


def test_message_is_bound_to_exact_course_signal_name_and_worksheet():
    raw = ('// Produced by OpenTrack: fixture\n// Desc. : OT_messages\n'
           'WARNING\t10:25:00\tRDG09\tCourse RDG09: Stop at Signal S:RDG:88 at RDG\t(RDG)\n'
           'WARNING\t10:25:01\tRDG09\tCourse RDG09: Stop at Signal S:RDG:8 at RDG\t(Other)\n'
           'WARNING\t10:25:02\tRDG90\tCourse RDG90: Stop at Signal S:RDG:8 at RDG\t(RDG)\n'
           'WARNING\t10:25:03\tRDG09\tCourse RDG09: Stop at Signal S:RDG:8 at RDG\t(RDG)\n')
    signal = {'document': 'RDG', 'signal_name': 'S:RDG:8'}
    assert [row['clock'] for row in stop_warnings(raw, 'RDG09', signal)] == ['10:25:03']


def test_single_optional_logging_difference_does_not_mask_physical_changes():
    plain = ([('Performance', '100'), (PHYSICS_LOG_OPTION, '1')], {'stations': 'sha'}, 'dest', 'courses')
    applied = ([('Performance', '100')], *plain[1:])
    assert checked_inputs(plain, plain, 'signal_stop') is None
    assert checked_inputs(plain, applied, 'signal_stop') == {'option': PHYSICS_LOG_OPTION, 'control': '1', 'incident': None}
    physical_change = ([('Performance', '99')], *plain[1:])
    asset_change = (applied[0], {'stations': 'new sha'}, *plain[2:])
    for changed, kind in ((physical_change, 'signal_stop'), (asset_change, 'signal_stop'), (applied, 'path_speed')):
        with pytest.raises(ValueError, match='changes more than'):
            checked_inputs(plain, changed, kind)
