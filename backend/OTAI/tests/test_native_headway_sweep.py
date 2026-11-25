from pathlib import PureWindowsPath
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from opentrack_ai.current_archive.native_headway_sweep_tools import (
    aligned_block_boundary, measured_section, minimum_in_grid, original_shared_monitors,
)
from opentrack_ai.current_archive.zero_operations.run_bundle import CATALOG_KEYS
from opentrack_ai.native_execution import headway_source_blobs
from opentrack_ai.native_headway_plan import sweep_courses
from opentrack_ai.simulation_evidence import Control, HeadwaySweep


def trial(gap, late):
    return {'planned_departure_headway_s': gap, 'leading': {'maximum_lateness_s': 0},
            'following': {'maximum_lateness_s': late}}


def test_minimum_precedes_later_regression_without_assuming_monotonicity():
    numbers, rows, passing, adjacent = minimum_in_grid(
        [trial(4, 9), trial(1, 8), trial(3, 2), trial(2, 7)], 5)
    assert numbers == [1, 2, 3, 4]
    assert passing['planned_departure_headway_s'] == 3
    assert adjacent['planned_departure_headway_s'] == 2
    assert [row['passes'] for row in rows] == [False, False, True, False]


@pytest.mark.parametrize('candidates', [(1, 3), (1, 1), ()])
def test_missing_duplicate_or_empty_sweep_cannot_prove_minimum(candidates):
    with pytest.raises(ValueError, match='every integer'):
        minimum_in_grid([trial(gap, 0) for gap in candidates], 5)


def test_origin_section_requires_exact_preceding_release_extent():
    follow = [(93.98, 0), (93.98, 1300), (105.0, 1300), (105.0, 1600)]
    lead = [(93.85, 0), (93.85, 1300), (105.0, 1300), (105.0, 1600)]
    result = measured_section(follow, lead, 87, 93)
    assert result == {'from_m': 0, 'to_m': 1300, 'leading_release_s': 93.85,
                      'following_reservation_s': 93.98, 'handover_gap_s': .13}
    assert measured_section(follow, [(93.85, 0), (93.85, 1299)], 87, 93) is None
    assert measured_section(follow, [(93.99, 0), (93.99, 1300)], 87, 93) is None


def test_headway_sweep_refuses_random_scenarios_or_interactive_mode():
    sweep = HeadwaySweep(leading_course_id='A', following_course_id='B', maximum_s=98)
    base = {'action': 'start', 'job_directory': 'job', 'project_directory': 'source',
            'run_file': 'layout.run', 'headway_sweep': sweep}
    assert Control.model_validate({**base, 'scenarios': [0]}).headway_sweep == sweep
    with pytest.raises(ValidationError, match='headway|Headway'):
        Control.model_validate({**base, 'scenarios': [7]})
    with pytest.raises(ValidationError, match='headway|Headway'):
        Control.model_validate({**base, 'mode': 'interactive'})


def test_headway_source_accepts_stock_windows_catalog_separators():
    project = PureWindowsPath('D:/Study/Line')
    configured = {key: str(project / 'OTData' / f'native.{role}') for role, key in CATALOG_KEYS.items()}
    members = {f'OTData/native.{role}': role.encode() for role in CATALOG_KEYS}
    assert headway_source_blobs(project, configured, members) == {role: role.encode() for role in CATALOG_KEYS}


def test_sweep_admission_checks_order_and_shared_expected_movement():
    study = {'leading_course_id': 'A', 'following_course_id': 'B'}
    lead = {'course_id': 'A', 'origin_station': 'West', 'terminal_station': 'East', 'distance_m': 1000}
    follow = {**lead, 'course_id': 'B'}
    assert len(sweep_courses({'courses': [lead, follow]}, study)) == 2
    with pytest.raises(ValueError, match='ordered pair'):
        sweep_courses({'courses': [follow, lead]}, study)
    with pytest.raises(ValueError, match='ordered pair'):
        sweep_courses({'courses': [lead, {**follow, 'distance_m': 1001}]}, study)


def test_different_itineraries_may_have_independent_endpoints_and_lengths():
    study = HeadwaySweep(leading_course_id='A', following_course_id='B', maximum_s=60,
                         comparison_mode='shared_fixed_block').model_dump()
    lead = {'course_id': 'A', 'origin_station': 'West', 'terminal_station': 'East', 'distance_m': 1000}
    follow = {'course_id': 'B', 'origin_station': 'North', 'terminal_station': 'South', 'distance_m': 2400}
    assert [row['distance_m'] for row in sweep_courses({'courses': [lead, follow]}, study)] == [1000, 2400]
    with pytest.raises(ValueError, match='ordered pair'):
        sweep_courses({'courses': [follow, lead]}, study)


def test_shared_boundary_requires_release_and_physical_entry_change():
    blocked = {'verified': True, 'handover_gap_s': .18,
               'leading': {'reservation_s': [100, 120]},
               'following': {'reservation_s': [120.18, 160], 'occupation_s': [143, 159]}}
    passing = {'verified': True, 'handover_gap_s': .34,
               'leading': {'reservation_s': [100, 120]},
               'following': {'reservation_s': [120.34, 160], 'occupation_s': [141, 159]}}
    witness = aligned_block_boundary(blocked, passing, 31, 32, .2)
    assert witness['passing_reservation_aligned_s'] == 119.34
    assert witness['observed_extra_entry_time_s'] == 3
    with pytest.raises(ValueError, match='simulation step'):
        aligned_block_boundary(blocked, passing, 31, 32, .1)
    unchanged_entry = {**passing, 'following': {**passing['following'], 'occupation_s': [144, 159]}}
    with pytest.raises(ValueError, match='entry earlier'):
        aligned_block_boundary(blocked, unchanged_entry, 31, 32, .2)
    with pytest.raises(ValueError, match='exclusive'):
        aligned_block_boundary(blocked, {**passing, 'verified': False}, 31, 32, .2)


def test_discover_only_selected_monitors_covering_both_paths_with_native_output(monkeypatch):
    choices = [{'name': name, 'selected': selected, 'saved_document': 'Proof', 'edge_ids': edges}
               for name, selected, edges in (
                   ('usable', True, [4, 8]), ('partial', True, [4]),
                   ('hidden', False, [4, 8]), ('missing', True, [4, 8]),
               )]
    monkeypatch.setattr('opentrack_ai.current_archive.native_occupation_groups.records',
                        lambda root, document: choices)
    reference = SimpleNamespace(project=SimpleNamespace(roots={'Proof': object()}),
                                hashes={f'OT_Occ_{name}.occ' for name in ('usable', 'partial', 'hidden')})
    shared = [{'document': 'Proof', 'leading_spans': [{'route_edge_ids': [4]}],
               'following_spans': [{'route_edge_ids': [8]}]}]
    assert [item.model_dump() for item in original_shared_monitors(reference, shared)] == [
        {'document': 'Proof', 'group': 'usable'},
    ]
