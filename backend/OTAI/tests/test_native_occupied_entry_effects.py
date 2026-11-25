import pytest

from opentrack_ai.current_archive.native_occupied_entry_effects import holding_plateau, measured_cap


def test_original_cap_evidence_requires_positive_co_timed_motion_and_bounded_range():
    motion = {'distance': [(0, 0), (1, 10), (2, 20), (3, 21), (4, 30)],
              'speed': [(0, 99), (1, 20), (2, 20), (3, 18), (4, 25)],
              'rounded_speed_tolerance_kmh': .050001}
    result = measured_cap(motion, 0.1, 22, 20)
    assert result == {'maximum_measured_speed_kmh': 20, 'matching_sample_count': 2,
                      'matching_position_range_m': [10, 20]}
    with pytest.raises(ValueError, match='did not show'):
        measured_cap(motion, .1, 30, 20)
    with pytest.raises(ValueError, match='No co-timed'):
        measured_cap(motion, 32, 50, 20)


def test_occupied_receiver_or_denied_donor_requires_still_observed_standstill_at_exact_site():
    motion = {'speed': [(10, 10), (12, 0), (22, 0), (23, 10)],
              'distance': [(10, 20), (12, 45), (22, 45), (23, 60)]}
    assert holding_plateau(motion, 45, 22, .2)['duration_s'] == 10
    for where, when in ((50, 21), (45, 23)):
        with pytest.raises(ValueError, match='expected position'):
            holding_plateau(motion, where, when, .2)
