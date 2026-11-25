from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive.native_following import reference_gap, trajectory


def test_reference_gap_respects_recorded_time_and_position_precision():
    lead = [(10, .60), (11, .65), (12, .70), (13, .80)]
    follow = [(10, .30), (11, .35), (12, .40), (13, .50)]
    report = reference_gap(lead, follow, 10.2, 12.8)
    assert report['interval_count'] == 3
    assert report['reference_gap_lower_bound_m'] == pytest.approx(99.899)
    assert report['least_gap_witness'] == {
        'interval_s': [11, 12], 'leading_sample': (10, .60), 'following_sample': (13, .50),
    }


def test_reference_gap_fails_incomplete_or_reversed_coordinate_coverage():
    lead = [(10, .6), (11, .7)]
    with pytest.raises(ValueError, match='enclose the window'):
        reference_gap(lead, [(10.5, .2), (11, .3)], 10.25, 10.75)
    with pytest.raises(ValueError, match='nondecreasing reference'):
        reference_gap(lead, [(10, .3), (11, .2)], 10.25, 10.75)


def test_following_requires_matching_native_itinerary_and_sealed_trajectory():
    data = ('// Produced by OpenTrack: Mon Nov 23 17:00:00 2026\n'
            '// Distance/Time of Course: T01\n// Itineraries: 1: Main\n'
            '// Desc. : OT_st1\n// x-Legend: [s]\n// y-Legend: [km]\n'
            '10.00\t0.1000\n11.00\t0.2000\n')
    inputs = SimpleNamespace(expected_hashes={}, read=lambda name: data)
    with pytest.raises(ValueError, match='launcher SHA-256'):
        trajectory(inputs, 'T01', 'Main')
    inputs.expected_hashes = {'OT_T01.st1': 'sealed'}
    with pytest.raises(ValueError, match='Itinerary'):
        trajectory(inputs, 'T01', 'Other')
    assert trajectory(inputs, 'T01', 'Main') == [(10, .1), (11, .2)]
