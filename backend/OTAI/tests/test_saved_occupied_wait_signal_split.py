"""Preserve the exact original stop-and-wait tuple on the new occupied-entry Route."""

import pytest

from opentrack_ai.current_archive import route_factory, writer
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.saved_geometry_tools import MainSignalRouteSplit, ReviewedOccupiedEntrySplit
from opentrack_ai.current_archive.saved_main_signal_split import _without_occupied_entry, insert_signal_in_saved_route
from opentrack_ai.current_archive.saved_timing_signal_split import DEFAULT_ROUTE_TIMING, release_keys, stored_route_timing

from test_saved_main_signal_split import _join_split_source


def local_case(wait, *, saved_flags=7):
    docs, paths, dest, banks, operation = _join_split_source()
    project = project_from(docs, paths, dest)
    review = operation['split_route']['occupied_entry']
    review.pop('expected_speed_kmh')
    review['expected_wait_s'] = wait
    ref = operation['split_route']['route']
    primary = project.owned(('Line', ref['start_id']), 'OTRoute',
                            tuple(ref[key] for key in ('name', 'array_id', 'start_id')))
    primary.contents[6].values[:] = [saved_flags, 0, 45]
    docs['Line'] = writer.dump_verified(project.roots['Line'], project.versions['Line'])
    return docs, paths, dest, banks, operation


def execute(case):
    docs, paths, dest, banks, op = case
    changed, report = insert_signal_in_saved_route(docs, paths, dest, 'Line', op, banks['courses'],
                                                   operating_banks=banks, run_bytes=b'TrainType#main#\n')
    return project_from(changed, paths, dest), report


def test_waiting_entry_is_confined_to_the_reviewed_new_suffix():
    case = local_case(45)
    saved, report = execute(case)
    prefix, suffix = [saved.owned(('Line', row['start_id']), 'OTRoute',
                                  tuple(row[key] for key in ('name', 'array_id', 'start_id')))
                      for row in (report['upstream_route'], report['downstream_route'])]
    assert prefix.contents[6].values == [0, 40, 0] and suffix.contents[6].values == [7, 0, 45]
    signal = saved.model(saved.route_view(suffix)[0]).contents[11].value
    assert signal.contents[9].values[2] & 1 and suffix.contents[11].value == 0
    proof = report['occupied_entry_transfer']
    assert proof['values'] == [7, 0, 45] and proof['independent_reservation']
    assert proof['berth']['contact']['offset_m'] == 78
    end_ids = [end[1] for end in saved.route_view(suffix)]
    for options in ({}, {'allow_speed_occupied_entry': True}):
        with pytest.raises(ValueError, match='occupied-entry/discrete flags unsupported'):
            route_factory.validate_chain(saved.roots['Line'], suffix, end_ids, **options)
    route_factory.validate_chain(saved.roots['Line'], suffix, end_ids, allow_wait_occupied_entry=True)


@pytest.mark.parametrize(('wait', 'saved_flags'), [(46, 7), (45, 5), (45, 15)])
def test_waiting_entry_rejects_unverified_wait_and_flag_tuple(wait, saved_flags):
    with pytest.raises(ValueError, match='explicitly reviewed terminal overlap, occupied entry or slow-zone fields'):
        execute(local_case(wait, saved_flags=saved_flags))


def test_typed_wait_is_explicit_exclusive_and_whole_seconds():
    review = local_case(45)[-1]['split_route']['occupied_entry']
    assert ReviewedOccupiedEntrySplit.model_validate(review).expected_wait_s == 45
    for bad in ({**review, 'expected_speed_kmh': 20}, {**review, 'expected_wait_s': None},
                {**review, 'expected_wait_s': 0}, {**review, 'expected_wait_s': 45.25}):
        with pytest.raises(ValueError):
            ReviewedOccupiedEntrySplit.model_validate(bad)


def case_with_wait_and_release(*, source_release=9):
    docs, paths, dest, banks, op = local_case(45)
    selected = op['split_route']['route']
    project = project_from(docs, paths, dest)
    original = project.owned(('Line', selected['start_id']), 'OTRoute',
                             tuple(selected[key] for key in ('name', 'array_id', 'start_id')))
    original.contents[5].values[2] = source_release
    docs['Line'] = writer.dump_verified(project.roots['Line'], project.versions['Line'])
    op['split_route']['timing'] = {**DEFAULT_ROUTE_TIMING, 'release_time_s': 9,
        'release_group_starts': [{'document': doc, 'end_id': end} for doc, end in release_keys(project, original)]}
    return docs, paths, dest, banks, op


def test_zero_speed_wait_and_reviewed_release_seconds_are_independent():
    case = case_with_wait_and_release()
    MainSignalRouteSplit.model_validate(case[-1]['split_route'])
    saved, report = execute(case)
    prefix, suffix = [saved.owned(('Line', row['start_id']), 'OTRoute',
                                  tuple(row[key] for key in ('name', 'array_id', 'start_id')))
                      for row in (report['upstream_route'], report['downstream_route'])]
    expected = {**DEFAULT_ROUTE_TIMING, 'release_time_s': 9}
    assert stored_route_timing(prefix) == stored_route_timing(suffix) == expected
    assert prefix.contents[6].values == [0, 40, 0] and suffix.contents[6].values == [7, 0, 45]
    assert prefix.contents[11].value == suffix.contents[11].value == 0
    joint = report['occupied_entry_release_delay_split']
    assert joint['independent_reservation'] and joint['native_joint_readback_verified']
    assert joint['occupancy']['values'] == [7, 0, 45]
    assert joint['upstream_release'] == {'end': saved.route_view(prefix)[-1], 'route_delay_s': 9}
    assert joint['occupied_entry_release'] == {'end': saved.route_view(suffix)[-1], 'route_delay_s': 9}


def test_zero_speed_wait_rejects_timing_that_disagrees_with_source():
    with pytest.raises(ValueError, match='original Route data|explicitly reviewed'):
        execute(case_with_wait_and_release(source_release=5))


def test_cross_document_cold_compare_resets_native_wait_fields_on_both_upstream_parts():
    shape = {'profile': {'occupied_entry': [7, 0., 45.], 'allow_occupied_entry': True,
                         'occupied_entry_use_speed': True, 'occupied_entry_use_time': True,
                         'occupied_entry_speed_kmh': 0., 'occupied_entry_wait_s': 45., 'description': 'Existing'}}
    assert _without_occupied_entry(shape)['profile'] == {
        'occupied_entry': [0, 40., 0.], 'allow_occupied_entry': False, 'occupied_entry_use_speed': False,
        'occupied_entry_use_time': False, 'occupied_entry_speed_kmh': 40., 'occupied_entry_wait_s': 0.,
        'description': 'Existing',
    }
