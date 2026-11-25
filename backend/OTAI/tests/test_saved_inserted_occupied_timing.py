"""Check explicit terminal occupied timing through the saved insertion review."""

from copy import deepcopy

import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.multi_document.core import ident
from opentrack_ai.current_archive.multi_document.generate import route as route_fragment
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.saved_geometry_tools import InsertOperationalDocumentSpan
from opentrack_ai.current_archive.saved_inserted_occupied_timing import (
    apply_inserted_occupied_timing, plan_inserted_occupied_timing,
)
from opentrack_ai.current_archive.saved_occupied_signal_split import verify_occupied_signal_split
from opentrack_ai.current_archive.saved_timing_signal_split import DEFAULT_ROUTE_TIMING, stored_route_timing

from test_saved_document_insertion import chain
from test_saved_insertion_occupied_wait import with_wait
from test_saved_main_signal_split import _join_split_source


TIMING = {'release_time_s': 9, 'approach_length_m': 15, 'approach_speed_kmh': 28}
BANKS = {role: 'a' * 64 for role in ('courses', 'timetable', 'trains', 'depot', 'stations')}


@pytest.mark.parametrize('with_speed', [False, True])
def test_typed_review_binds_one_timed_formation_for_both_occupied_modes(chain, with_speed):
    operation = with_wait(chain[-1])
    row = operation['routes'][0]
    if with_speed:
        row['expected_occupied_entry'].pop('expected_wait_s')
        row['expected_occupied_entry']['expected_speed_kmh'] = 20
    row['expected_occupied_entry_timing'] = TIMING
    with pytest.raises(ValueError, match='five operating archive hashes'):
        InsertOperationalDocumentSpan.model_validate(operation)
    operation['operating_sha256'] = BANKS
    InsertOperationalDocumentSpan.model_validate(operation)
    for field, value in (('reserve_with_previous', True), ('middle_entry_release_end_ids', [4])):
        bad = deepcopy(operation)
        bad['routes'][0][field] = value
        with pytest.raises(ValueError, match='independent reservation and original implicit terminal release'):
            InsertOperationalDocumentSpan.model_validate(bad)


def test_legacy_speed_review_cannot_enable_timing_without_formation(chain):
    operation = deepcopy(chain[-1])
    row = operation['routes'][0]
    row.update(preserve_local_protection=True, expected_occupied_entry_timing=TIMING,
               expected_occupied_entry={'terminal_end': {'document': 'B', 'end_id': 8},
                                        'stop_edge_id': 9, 'expected_speed_kmh': 20})
    with pytest.raises(ValueError, match='reviewed berth'):
        InsertOperationalDocumentSpan.model_validate(operation)


def timing_case(*, length=15, reserve=0, wait=False):
    docs, paths, dest, banks, operation = _join_split_source()
    project = project_from(docs, paths, dest)
    request = operation['split_route']
    reference = request['route']
    original = project.owned(('Line', reference['start_id']), 'OTRoute',
                             tuple(reference[key] for key in ('name', 'array_id', 'start_id')))
    if wait:
        request['occupied_entry'].pop('expected_speed_kmh')
        request['occupied_entry']['expected_wait_s'] = 45
        original.contents[6].values[:] = [7, 0, 45]
    original.contents[5].values[2:4] = [9, reserve]
    original.contents[8].values[:] = [length, 28]
    sequence = project.route_view(original)
    writer.set_elements(original.contents[12].values[0], [project.model(sequence[0])])
    berth = verify_occupied_signal_split(project, original, sequence, sequence[-2],
                                       request['occupied_entry'], banks, b'TrainType#main#\n')
    fragment = route_fragment(*ident(original), [project.model(sequence[-1])], -1, fragment=True)
    return project, original, fragment, berth, banks, {**TIMING, 'approach_length_m': length}


@pytest.mark.parametrize('wait', [False, True])
def test_reviewed_occupied_timing_is_separated_from_prefix_and_fragment(wait):
    project, original, fragment, berth, banks, timing = timing_case(wait=wait)
    proof = plan_inserted_occupied_timing(project, original, fragment, berth, timing, banks, [])
    assert proof['source_approach']['clear_distance_beyond_contact_m'] == 7
    after = route_fragment('After', 0, 4, [project.model(project.route_view(original)[-1])], -1)
    apply_inserted_occupied_timing(original, after, proof['timing'])
    assert stored_route_timing(original) == {**DEFAULT_ROUTE_TIMING, 'release_time_s': 9}
    assert stored_route_timing(after) == {**DEFAULT_ROUTE_TIMING, **timing}
    assert stored_route_timing(fragment) == DEFAULT_ROUTE_TIMING
    assert original.contents[6].values == berth['values']


@pytest.mark.parametrize('length', [22, 23])
def test_insertion_rejects_touching_or_crossing_the_donor_contact(length):
    project, original, fragment, berth, banks, timing = timing_case(length=length, wait=True)
    with pytest.raises(ValueError, match='strictly beyond'):
        plan_inserted_occupied_timing(project, original, fragment, berth, timing, banks, [])


@pytest.mark.parametrize('explicit', [False, True])
def test_insertion_cannot_copy_positive_preparation_into_an_independent_occupied_route(explicit):
    project, original, fragment, berth, banks, timing = timing_case(reserve=12)
    if explicit:
        timing['reserve_time_s'] = 12
    with pytest.raises(ValueError, match='default preparation'):
        plan_inserted_occupied_timing(project, original, fragment, berth, timing, banks, [])

