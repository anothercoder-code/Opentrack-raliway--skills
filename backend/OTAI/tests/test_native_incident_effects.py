from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import catalogs, writer
from opentrack_ai.current_archive.infrastructure_incidents.core import create
from opentrack_ai.current_archive.native_incident_effects import (
    common_exposure, course_bank, printed_clock, traction_comparison, verified_activation,
)
from test_itinerary_lifecycle import course_archive


def physics(clock, position, speed, force):
    return {'time_s': clock, 'distance_km': position, 'speed_kmh': speed, 'tractive_effort_kn': force,
            'acceleration_mps2': 1}


def test_original_active_intersection_excludes_opposite_time_and_longitudinal_regions():
    original = [physics(1, 1.0, 20, 10), physics(2, 1.1, 25, 10), physics(3, 1.2, 30, 10),
                physics(4, 1.3, 35, 10), physics(9, 1.4, 40, 10)]
    changed = [physics(1, .8, 10, 10), physics(2, 1.0, 25, 10), physics(3, 1.1, 30, 10),
               physics(4, 1.2, 35, 10), physics(9, 1.3, 40, 10)]
    common, control, incident = common_exposure(original, changed, [2, 4], [0, 300], 1000)
    assert common == [100, 200]
    assert [row['time_s'] for row in control] == [2, 3]
    assert [row['time_s'] for row in incident] == [3, 4]
    with pytest.raises(ValueError, match='traverse'):
        common_exposure(original, changed, [2, 3], [0, 100], 1000)


def test_tractive_effort_compares_same_reported_speeds():
    control = [physics(0, 0, i, 280) for i in range(1, 6)]
    applied = [physics(0, 0, i, 140) for i in range(3, 8)]
    result = traction_comparison(control, applied, .5)
    assert result['verified_effect'] and result['matching_factor_count'] == 3
    assert [witness['speed_kmh'] for witness in result['compared_speed_witnesses']] == [3, 4, 5]
    assert not traction_comparison(control, applied, .4)['verified_effect']
    assert not traction_comparison(control, applied[:2], .5)['verified_effect']


def test_native_incident_clock_binds_target_and_accounts_for_days():
    messages = (
        '// Produced by OpenTrack: fixture\n// Desc. : OT_messages\n'
        'NORMAL\t23:59:50\tC\tCourse C: Incident started: Power\t(Line)\n'
        'NORMAL\t00:00:10\tC\tCourse C: Incident stopped: Power\t(Line)\n'
    )
    protocol = {'listed_incidents': [{'name': 'Power', 'start': '23:59:50', 'end': '1 / 00:00:10'}]}
    run = SimpleNamespace(receipt={'protocol': protocol}, original_text=lambda name: messages)
    item = {'name': 'Power', 'begin_time': '23:59:50', 'end_time': '00:00:10', 'begin_day': 0, 'end_day': 1}
    declared, observed, logs = verified_activation(run, item, 'C', 'Power', 1.21)
    assert declared == observed == [86390, 86410] and len(logs) == 2
    assert printed_clock('23:59:59', 86400) == 86399
    assert printed_clock('23:59:59', 86400.04) == 86399
    with pytest.raises(ValueError, match='target'):
        verified_activation(run, item, 'Other Course', 'Power', 1.21)


def test_only_selected_event_may_be_removed_from_incident_bank_comparison():
    clean = course_archive(C=['I'])
    root, version = writer.load_next_compatible(clean)
    incidents = root.contents[1].value
    values = dict(type='train_power_limit', course_id='C', name='Power', begin_time='00:05:00', end_time='00:15:00',
                  begin_day=0, end_day=0, enabled=True, probability_percentage=100, limited_power_kw=2000)
    writer.set_elements(incidents, [create(values, incidents)])
    applied = writer.dump_verified(root, version)
    _, selected, target_signature = course_bank(applied, 'Power')
    assert selected == values
    assert target_signature == course_bank(clean, 'Power')[2]
    bank, _, signature = course_bank(applied, 'Another event')
    assert signature != target_signature
    assert len(catalogs.array(bank.contents[1].value)) == 1
