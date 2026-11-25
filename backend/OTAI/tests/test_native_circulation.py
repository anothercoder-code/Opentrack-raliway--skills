import pytest

from opentrack_ai.current_archive.native_circulation import occupation_transition, transfer_days, transition_motion


def transition(mode, *, station='RDG', positive_before_departure=False):
    predecessor = {'terminal': {'clock': '00:01:40', 'time_s': 100}}
    successor = {'course_id': 'NEXT', 'origin': {'clock': '00:10:00', 'time_s': 600},
                 'speed': [(100.4, 0), (600, 0), (600.2, 1)],
                 'position': [(100.4, 0), (600, 0), (600.2, 1)]}
    kinds = ['activation', 'ready']
    clock = '00:01:40'
    if mode == 'unlinked':
        kinds = ['ready']
        clock = '00:10:00'
        successor['speed'] = [(600, 0), (600, 0), (600.2, 1)]
        successor['position'] = [(600, 0), (600, 0), (600.2, 1)]
    if positive_before_departure:
        successor['speed'].insert(1, (599, 1))
    events = [{'kind': kind, 'course_id': 'NEXT', 'station': station, 'clock': clock} for kind in kinds]
    return predecessor, successor, events


def test_linked_course_requires_corroborated_activation_and_zero_speed_hold():
    predecessor, successor, events = transition('linked')
    result = transition_motion(predecessor, successor, events, 'RDG', 420, 1.05, True)
    assert result['verified'] and result['successor_activation_s'] == 100.4
    assert result['successor_stationary_interval']['duration_s'] == pytest.approx(499.6)
    assert not transition_motion(predecessor, successor, events, 'EA', 420, 1.05, True)['verified']
    assert not transition_motion(predecessor, successor, events, 'RDG', 501, 1.05, True)['verified']
    early_motion = transition('linked', positive_before_departure=True)
    assert not transition_motion(*early_motion, 'RDG', 420, 1.05, True)['verified']


def test_independent_departure_at_same_time_does_not_prove_activation():
    before, after, events = transition('unlinked')
    assert transition_motion(before, after, events, 'RDG', 420, 1.05, False)['verified']
    assert not transition_motion(before, after, events, 'RDG', 420, 1.05, True)['verified']


def test_same_occupation_element_can_show_continuous_handover_or_separate_departure():
    before, after, events = transition('linked')
    motion = transition_motion(before, after, events, 'RDG', 420, 1.05, True)
    old = {'course_id': 'OLD', 'reservation_s': [70, 100.2], 'occupation_s': [90, 100.2]}
    continuous = {'course_id': 'NEXT', 'reservation_s': [100.2, 640], 'occupation_s': [100.2, 640]}
    restart = {'course_id': 'NEXT', 'reservation_s': [600, 640], 'occupation_s': [600, 640]}
    result = occupation_transition([old, continuous], 'OLD', 'NEXT', 'continue', 'linked', motion, 1.05)
    assert result['verified'] and result['continuous_monitored_handover']
    assert not occupation_transition([old, restart], 'OLD', 'NEXT', 'continue', 'linked', motion, 1.05)['verified']
    result = occupation_transition([old, restart], 'OLD', 'NEXT', 'reverse', 'linked', motion, 1.05)
    assert result['verified'] and not result['continuous_monitored_handover']
    with pytest.raises(ValueError, match='exactly one cycle'):
        occupation_transition([old, old, restart], 'OLD', 'NEXT', 'reverse', 'linked', motion, 1.05)


def test_midnight_uses_absolute_original_clocks_and_reports_planned_days_independently():
    assert transfer_days(86040, 86580, 85985, 86580) == {
        'planned_day_offsets': [0, 1], 'actual_day_offsets': [0, 1],
        'planned_crosses_midnight': True, 'crosses_midnight': True,
    }
    late = transfer_days(86040, 86580, 86400, 87000)
    assert late['planned_crosses_midnight'] and not late['crosses_midnight']
    assert late['actual_day_offsets'] == [1, 1]
