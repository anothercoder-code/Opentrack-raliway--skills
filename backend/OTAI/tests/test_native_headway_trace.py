import pytest

from opentrack_ai.current_archive.native_headway_trace import (
    Progress, clock_difference, clock_range, first_positive_sample, inspect_monitor,
)


def test_checkpoint_expands_position_and_printed_time_rounding():
    points = Progress([(45.00, 96), (45.20, 99.8), (45.40, 100.0), (45.60, 101.4)])
    assert points.crossing(100) == {
        'seconds': [45.194999, 45.605001],
        'samples_s_m': [(45.2, 99.8), (45.6, 101.4)],
    }
    assert points.crossing(101.4) is None
    assert points.crossing(96) is None
    assert clock_difference([45.19, 45.61], [45.39, 45.81]) == [-0.22, 0.62]


def test_sparse_native_jump_preserves_its_same_timestamp_bounds():
    trace = Progress([(32.4, 0), (32.4, 1300), (80, 1300), (80, 2600)])
    bounds = trace.crossing(500)
    assert bounds['seconds'] == [32.394999, 32.405001]
    assert trace.reservation_shape({('Line', 13): [{'from_m': 0, 'to_m': 1300}]}, 0, .2) == {
        'sample_count': 4, 'same_printed_clock_advance_count': 2,
        'progressive_advances_within_one_saved_element': 0, 'first_progressive_advance': None,
    }


def test_dense_advances_are_bound_to_one_saved_element_and_positive_motion_is_reported_as_sample():
    spans = {('Line', 20): [{'from_m': 0, 'to_m': 100}],
             ('Line', 21): [{'from_m': 100, 'to_m': 200}]}
    trace = Progress([(10.0, 108.0), (10.20, 114.0), (10.40, 149.9), (10.60, 150.1), (12.00, 200.0)])
    data = trace.reservation_shape(spans, 50, .2)
    assert data['progressive_advances_within_one_saved_element'] == 2
    assert data['first_progressive_advance'] == {
        'document': 'Line', 'safety_element_id': 20, 'span_in_output_coordinate_m': [50, 150],
        'samples_s_m': [(10, 108), (10.2, 114)],
    }
    assert first_positive_sample([(10.12, 0), (10.32, .4), (10.52, .8)]) == {
        'first_positive_sample_s_kmh': (10.32, .4), 'previous_sample_s_kmh': (10.12, 0),
    }
    with pytest.raises(ValueError, match='nondecreasing'):
        Progress([(10.2, 14), (10.4, 9)])
    with pytest.raises(ValueError, match='nondecreasing'):
        Progress([(-1, 0), (10.4, 9)])


def test_monitored_handover_can_be_shorter_than_nominal_step_without_quantizing_the_clock():
    class Railway:
        def resource(self, reference):
            return {'document': 'Line', 'safety_element_id': 7}, [
                {'course_id': 'A', 'reservation_s': [13.0, 19.53], 'occupation_s': [15.23, 19.53]},
                {'course_id': 'B', 'reservation_s': [19.59, 25.10], 'occupation_s': [21.50, 25.10]},
            ]

    route = {'spans': {('Line', 7): [{'from_m': 100, 'to_m': 170}]}}
    progress = {'A': Progress([(15.23, 99), (15.43, 101)]),
                'B': Progress([(21.50, 99), (21.70, 101)])}
    data = inspect_monitor(Railway(), {}, ['A', 'B'], route, progress, 0, .2)
    assert data['leading_release_to_following_reservation_printed_s'] == .06
    assert data['leading_release_to_following_reservation_bounds_s'] == [.049998, .070002]
    assert data['positive_gap_shorter_than_configured_step']
    assert clock_range(.0, .0) == [0, .005001]
    with pytest.raises(ValueError, match='within one configured step'):
        inspect_monitor(Railway(), {}, ['A','B'], route, {**progress, 'B': progress['A']}, 0, .2)
