"""Exercise the allowed directed-platform change of a compound signal Save."""

from copy import deepcopy

import pytest

from opentrack_ai.current_archive.network_operating_plan import _platform_profile, resolve_visit_stop
from opentrack_ai.current_archive.saved_geometry_tools import CreateMainSignal
from opentrack_ai.current_archive.saved_signal_halt_transaction import _expected_visit, _verify_profiles
from opentrack_ai.current_archive.signal_type_workflow.core import TYPES


DOC = 'Station'
EXIT = (DOC, 5)
OLD, NEW = (DOC, 2), (DOC, 3)
SEGMENTS = [{
    'from_end_key': (DOC, end), 'to_end_key': (DOC, end + 1), 'edge_key': (DOC, 10 + end),
    'length_m': 100, 'minimum_elapsed_s': 5, 'track_id': 'A',
    'directional_speed_limit_kmh': 72, 'effective_speed_limit_kmh': 72,
} for end in range(1, 5)]


def platform(markers):
    return {'end_key': EXIT, 'distance_m': 1400, 'station_sign': 'A',
            **_platform_profile(SEGMENTS, markers, (1, 10), EXIT, 1000, 50)}


@pytest.mark.parametrize(('kind', 'head'), [
    ('stop_head', 1200),
    ('stop_center', 1240),
    ('stop_tail', 1280),
    ('stop_length_100m', 1200),
])
def test_expected_move_recomputes_physical_and_elapsed_stopping_point(kind, head):
    before = platform([(1, (TYPES[kind], 20))])
    after, move = _expected_visit(before, OLD, NEW, 20, 100)
    assert move['before']['platform_position_m'] == 100
    assert move['after']['platform_position_m'] == 200
    assert after == platform([(2, (TYPES[kind], 20))])
    stop = resolve_visit_stop(after, 80)
    assert stop['distance_m'] == head
    assert stop['marker_distance_m'] == 1200
    assert stop['minimum_elapsed_s'] == 50 + (head - 1000) / 20


def test_expected_move_must_keep_marker_choice_for_unbooked_length_ranges():
    before = platform([(1, (TYPES['stop_length_50m'], 20)), (2, (TYPES['stop_length_100m'], 21))])
    with pytest.raises(ValueError, match='train-length range'):
        _expected_visit(before, OLD, (DOC, 4), 20, 200)


def test_same_numeric_signal_on_other_worksheet_is_not_approved():
    before = platform([(1, (TYPES['stop_center'], 20))])
    assert _expected_visit(before, ('Other', OLD[1]), ('Other', NEW[1]), 20, 100) == (before, None)


@pytest.mark.parametrize('unexpected', ['reverse_visit', 'physical_edges', 'reference', 'stop_duration'])
def test_unrelated_movement_or_visit_change_aborts_the_combined_save(unexpected):
    before = {'forward': {'visits': [platform([(1, (TYPES['stop_center'], 20))])], 'edges': [(DOC, 11)]},
              'reverse': {'visits': [platform([])], 'edges': [(DOC, 11)]}}
    after = deepcopy(before)
    after['forward']['visits'][0] = platform([(2, (TYPES['stop_center'], 20))])
    assert len(_verify_profiles(before, after, OLD, NEW, 20, 100)) == 1
    if unexpected == 'reverse_visit':
        after['reverse']['visits'][0]['distance_m'] += 1
    elif unexpected == 'physical_edges':
        after['reverse']['edges'].append((DOC, 23))
    elif unexpected == 'reference':
        after['forward']['visits'][0]['end_key'] = (DOC, 6)
    else:
        after['forward']['visits'][0]['minimum_elapsed_s'] = 66
    with pytest.raises(ValueError, match='another native visit or movement'):
        _verify_profiles(before, after, OLD, NEW, 20, 100)


def test_public_input_requires_joined_review_operating_hashes_and_existing_route():
    args = {'action': 'create_main_signal', 'end_id': 6, 'signal_name': 'B', 'main_role': 'block',
            'placement': {'angle': 0, 'x': 1, 'y': 0, 'alignment_x': 1, 'alignment_y': 0},
            'split_route': {'route': {'document': DOC, 'name': 'R', 'array_id': 0, 'start_id': 9},
                            'continued_name': 'R2', 'expected_upstream_edge_ids': [8],
                            'expected_downstream_edge_ids': [9]},
            'halt_relocation': {'station_id': 30, 'signal_id': 20, 'from_end_id': 2, 'to_end_id': 3,
                'arrival_route': {'document': DOC, 'name': 'Approach', 'array_id': 0, 'start_id': 1},
                'expected_platform_edge_ids': [11, 12, 13, 14], 'expected_stop_shift_m': 100, 'visit_reviews': []},
            'operating_sha256': {name: 'a' * 64 for name in ('courses', 'timetable', 'stations', 'trains', 'depot')}}
    assert CreateMainSignal.model_validate(args).halt_relocation.from_end_id == 2
    with pytest.raises(ValueError, match='five operating archive hashes'):
        CreateMainSignal.model_validate({**args, 'operating_sha256': None})
    with pytest.raises(ValueError, match='block signal with a reviewed Route split'):
        CreateMainSignal.model_validate({**args, 'split_route': None})
