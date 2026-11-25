"""Keep a reviewed occupied berth and an independent timed native release."""

import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.saved_geometry_tools import MainSignalRouteSplit
from opentrack_ai.current_archive.saved_main_signal_split import insert_signal_in_saved_route
from opentrack_ai.current_archive.saved_occupied_timing_signal_split import plan_occupied_release_delay
from opentrack_ai.current_archive.saved_timing_signal_split import DEFAULT_ROUTE_TIMING, release_keys, stored_route_timing

from test_saved_main_signal_split import _join_split_source
from test_saved_occupied_wait_signal_split import case_with_wait_and_release


def timed_case(delay):
    docs, paths, dest, banks, operation = _join_split_source()
    project = project_from(docs, paths, dest)
    ref = operation['split_route']['route']
    route = project.owned(('Line', ref['start_id']), 'OTRoute',
                          tuple(ref[key] for key in ('name', 'array_id', 'start_id')))
    route.contents[5].values[2] = delay
    docs['Line'] = writer.dump_verified(project.roots['Line'], project.versions['Line'])
    operation['split_route']['timing'] = {
        **DEFAULT_ROUTE_TIMING, 'release_time_s': delay,
        'release_group_starts': [{'document': doc, 'end_id': end} for doc, end in release_keys(project, route)],
    }
    return docs, paths, dest, banks, operation


def execute(case):
    docs, paths, dest, banks, operation = case
    changed, result = insert_signal_in_saved_route(docs, paths, dest, 'Line', operation, banks['courses'],
                                                  operating_banks=banks, run_bytes=b'TrainType#main#\n')
    return project_from(changed, paths, dest), result


@pytest.mark.parametrize('delay', [9, 17])
def test_occupied_entry_and_timed_releases_survive_native_roundtrip(delay):
    case = timed_case(delay)
    MainSignalRouteSplit.model_validate(case[-1]['split_route'])
    saved, report = execute(case)
    readback = report['occupied_entry_release_delay_split']
    prefix, suffix = [saved.owned(('Line', row['start_id']), 'OTRoute',
                                  tuple(row[key] for key in ('name', 'array_id', 'start_id')))
                      for row in (report['upstream_route'], report['downstream_route'])]
    assert stored_route_timing(prefix) == stored_route_timing(suffix) == {**DEFAULT_ROUTE_TIMING, 'release_time_s': delay}
    assert prefix.contents[6].values == [0, 40, 0] and suffix.contents[6].values == [3, 20, 0]
    assert prefix.contents[11].value == suffix.contents[11].value == 0
    assert readback['independent_reservation'] and readback['native_joint_readback_verified']
    assert readback['upstream_release'] == {'end': saved.route_view(prefix)[-1], 'route_delay_s': delay}
    assert readback['occupied_entry_release'] == {'end': saved.route_view(suffix)[-1], 'route_delay_s': delay}
    assert readback['occupancy']['berth']['contact']['offset_m'] == 78
    entry = report['occupied_entry_transfer']
    timing = report['timing_split']
    with pytest.raises(ValueError, match='separate downstream reservation'):
        plan_occupied_release_delay(entry, timing, reserve_with_previous=True)
    timing['original']['approach_length_m'] = 20
    with pytest.raises(ValueError, match='reservation, distance and approach settings'):
        plan_occupied_release_delay(entry, timing, reserve_with_previous=False)


def approach_case(length, *, explicit=True, wait=False):
    docs, paths, dest, banks, operation = case_with_wait_and_release() if wait else timed_case(9)
    graph = project_from(docs, paths, dest)
    reference = operation['split_route']['route']
    route = graph.owned(('Line', reference['start_id']), 'OTRoute',
                        tuple(reference[key] for key in ('name', 'array_id', 'start_id')))
    route.contents[8].values[:] = [length, 28]
    docs['Line'] = writer.dump_verified(graph.roots['Line'], graph.versions['Line'])
    operation['split_route']['timing'].update(approach_length_m=length, approach_speed_kmh=28,
                                              preserve_occupied_terminal_approach=explicit)
    return docs, paths, dest, banks, operation


@pytest.mark.parametrize('wait', [False, True])
def test_occupied_entry_rejects_adding_an_unreviewed_approach_to_the_release_split(wait):
    with pytest.raises(ValueError, match='reservation, distance and approach settings'):
        execute(approach_case(15, explicit=False, wait=wait))


@pytest.mark.parametrize('wait, mode', [(False, [3, 20, 0]), (True, [7, 0, 45])])
def test_occupied_entry_and_disjoint_terminal_approach_survive_native_roundtrip(wait, mode):
    case = approach_case(15, wait=wait)
    MainSignalRouteSplit.model_validate(case[-1]['split_route'])
    saved, result = execute(case)
    prefix, suffix = [saved.owned(('Line', row['start_id']), 'OTRoute',
                                  tuple(row[key] for key in ('name', 'array_id', 'start_id')))
                      for row in (result['upstream_route'], result['downstream_route'])]
    assert stored_route_timing(prefix) == {**DEFAULT_ROUTE_TIMING, 'release_time_s': 9}
    assert stored_route_timing(suffix) == {**DEFAULT_ROUTE_TIMING, 'release_time_s': 9,
                                           'approach_length_m': 15, 'approach_speed_kmh': 28}
    assert prefix.contents[6].values == [0, 40, 0] and suffix.contents[6].values == mode
    assert prefix.contents[11].value == suffix.contents[11].value == 0
    readback = result['occupied_entry_release_delay_split']
    assert readback['native_joint_readback_verified']
    approach = readback['terminal_approach']
    assert approach['start_offset_m'] == 85 and approach['end_offset_m'] == 100
    assert approach['donor_contact_offset_m'] == 78 and approach['clear_distance_beyond_contact_m'] == 7
    if wait:
        assert readback['scheduled_zero_speed_at_entry'] == {
            'end': saved.route_view(suffix)[0], 'saved_wait_s': 45, 'distance_to_terminal_approach_m': 85,
        }
    else:
        assert 'scheduled_zero_speed_at_entry' not in readback


@pytest.mark.parametrize('length', [22, 23])
@pytest.mark.parametrize('wait', [False, True])
def test_occupied_entry_rejects_terminal_approach_touching_or_crossing_contact(length, wait):
    with pytest.raises(ValueError, match='strictly beyond'):
        execute(approach_case(length, wait=wait))


def test_terminal_approach_does_not_authorize_synchronized_wait_entry():
    request = approach_case(15, wait=True)[-1]['split_route']
    request['reserve_with_previous'] = True
    with pytest.raises(ValueError, match='independent'):
        MainSignalRouteSplit.model_validate(request)


@pytest.mark.parametrize('mode', [[5, 0, 45], [7, 20, 45], [7, 0, 45.25]])
def test_approach_helper_rejects_unreviewed_occupied_entry_tuples(mode):
    _, result = execute(approach_case(15, wait=True))
    entry = {**result['occupied_entry_transfer'], 'values': mode}
    with pytest.raises(ValueError, match='zero-speed timed'):
        plan_occupied_release_delay(entry, result['timing_split'], reserve_with_previous=False,
                                    preserve_terminal_approach=True)
