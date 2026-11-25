"""Account for the exact saved turnout leg when testing an ordinary station berth."""

import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.multi_document.core import ident
from opentrack_ai.current_archive.network_operating_plan import route_trace
from opentrack_ai.current_archive.saved_geometry import project_from, transform

from test_saved_halt_creation import clean_platform
from test_saved_halt_location import case
from test_saved_geometry import shapes_for
from test_saved_multi_document_reroute import chain
from test_saved_platform_replacement import occupied_platform
from test_saved_platform_resize import _operating, _request


def _add_siding(docs, paths, catalog, end, shapes, suffix=''):
    vertex, receipt = transform(docs, paths, catalog, 'B', {
        'action': 'insert_vertex', 'x': 250, 'y': 140 + 4 * len(suffix), 'orientation': 'horizontal',
        'names': ['Berth branch' + suffix, 'Berth branch reverse' + suffix]}, shapes=shapes)
    docs.update(vertex)
    branch, result = transform(docs, paths, catalog, 'B', {
        'action': 'insert_edge', 'end_ids': [end, receipt['added_vertex_end_ids'][0]],
        'length_m': 90, 'track_name': 'Siding', 'line_name': 'Line', 'remark': '',
        'allow_safety_regroup': True, 'radius_m': 0, 'gradient_per_mille': 0, 'rack_rail': False,
        'speeds': [{'train_type': '0', 'speed12_kmh': 40, 'speed21_kmh': 40}]}, shapes=shapes)
    docs.update(branch)
    return result['edge_id']


@pytest.fixture
def turnout_berth(occupied_platform):
    docs, paths, catalog, request, shapes = occupied_platform
    docs = dict(docs)
    replaced, split = transform(docs, paths, catalog, 'B', request, shapes=shapes)
    docs.update(replaced)
    reference, turnout = [row['end_ids'][0] for row in split['replacement_waypoints']]
    graph = project_from(docs, paths, catalog)
    departure = graph.related(('B', turnout))[1]
    branch = _add_siding(docs, paths, catalog, departure, shapes)
    return docs, paths, catalog, request['station_id'], split['replacement_edge_ids'], reference, turnout, branch


@pytest.mark.parametrize('separate_reference', [False, True])
def test_resize_booked_berth_keeps_only_the_selected_turnout_leg(turnout_berth, separate_reference):
    docs, paths, catalog, station, edges, reference, turnout, siding = turnout_berth
    berth_end = ('B', reference if separate_reference else 8)
    if separate_reference:
        project = project_from(docs, paths, catalog)
        for key, kind in ((berth_end, 2), (('B', 8), 1)):
            for half in (key, project.related(key)):
                project.model(half).contents[20].value = kind
        docs['B'] = writer.dump_verified(project.roots['B'], project.versions['B'])
    inputs, run, consist = _operating()
    request = _request(station, edges, [(edges[0], 130, 155)], 525, consist,
                       new_head=2025, new_available=525)
    if separate_reference:
        request['visit_reviews'][0].update(expected_reference_distance_m=1630, replacement_reference_distance_m=1655)

    outputs, report = transform(docs, paths, catalog, 'B', request, run_bytes=run, platform_inputs=inputs)
    fresh = project_from({**docs, **outputs}, paths, catalog)
    itinerary, = [item for item in fresh.dests if ident(item)[0] == 'I:chain:forward']
    trace = route_trace(fresh, itinerary)
    visit, = [row for row in trace['visits'] if row['end_key'] == berth_end]
    assert visit['stopping_area_edge_keys'] == [('B', edge) for edge in edges]
    assert visit['stopping_area_length_m'] == 525
    review, = report['verified_platform_visits']
    assert review['after']['head_distance_m'] == 2025
    assert review['after']['reference_end'] == berth_end
    assert fresh.model(('B', turnout)).contents[12].value is fresh.model(berth_end).contents[12].value
    assert fresh.model(('B', siding)).contents[9].values[1] == 90
    assert ('B', siding) not in trace['edges']


def test_turnout_without_paired_station_membership_is_not_a_usable_berth(turnout_berth):
    docs, paths, catalog, station, edges, _, turnout, _ = turnout_berth
    project = project_from(docs, paths, catalog)
    project.model(project.related(('B', turnout))).contents[12].value = None
    docs['B'] = writer.dump_verified(project.roots['B'], project.versions['B'])
    inputs, run, consist = _operating()
    request = _request(station, edges, [(edges[0], 130, 155)], 525, consist,
                       new_head=2025, new_available=525)
    with pytest.raises(ValueError, match='inconsistent station memberships'):
        transform(docs, paths, catalog, 'B', request, run_bytes=run, platform_inputs=inputs)


def _pair(project, end):
    key = 'B', end
    return (project.model(ref) for ref in (key, project.related(key)))


def test_platform_entry_turnout_does_not_include_the_external_approach(turnout_berth):
    docs, paths, catalog, station, edges, waypoint, _, siding = turnout_berth
    project = project_from(docs, paths, catalog)
    for end in (4, waypoint):
        for half in _pair(project, end):
            half.contents[12].value = None
    docs['B'] = writer.dump_verified(project.roots['B'], project.versions['B'])
    inputs, run, consist = _operating()
    request = _request(station, edges[-1:], [(edges[-1], 150, 175)], 175, consist,
                       former_available=150, new_available=175, new_head=2025)
    request['expected_platform_length_m'] = 150
    request['visit_reviews'][0]['replacement_reference_distance_m'] = 2025

    outputs, report = transform(docs, paths, catalog, 'B', request, run_bytes=run, platform_inputs=inputs)
    visit, = report['verified_platform_visits']
    assert visit['before']['available_length_m'] == 150 and visit['after']['available_length_m'] == 175
    updated = project_from({**docs, **outputs}, paths, catalog)
    assert updated.model(('B', edges[-2])).contents[9].values[1] == 220
    assert updated.model(('B', siding)).contents[9].values[1] == 90
    with pytest.raises(ValueError, match='outside the reviewed directed platform'):
        transform(docs, paths, catalog, 'B', {**request, 'edges': [
            {'edge_id': edges[-2], 'expected_length_m': 220, 'length_m': 245}]},
            run_bytes=run, platform_inputs=inputs)


@pytest.mark.parametrize('exit_half', [8, 9])
def test_platform_exit_turnout_is_separate_from_the_timetable_reference(turnout_berth, exit_half):
    docs, paths, catalog, station, edges, reference, _, _ = turnout_berth
    project = project_from(docs, paths, catalog)
    for end, kind in ((reference, 2), (8, 1)):
        for half in _pair(project, end):
            half.contents[20].value = kind
    for half in _pair(project, 12):
        half.contents[12].value = None
    for edge in edges:
        project.model(('B', edge)).contents[19].value = None
    docs['B'] = writer.dump_verified(project.roots['B'], project.versions['B'])
    siding = _add_siding(docs, paths, catalog, exit_half, shapes_for(docs['B']), ' exit')
    inputs, run, consist = _operating()
    request = _request(station, edges, [(edges[-1], 150, 175)], 525, consist,
                       new_available=525, new_head=2025)
    request['visit_reviews'][0].update(expected_reference_distance_m=1630, replacement_reference_distance_m=1630)

    outputs, report = transform(docs, paths, catalog, 'B', request, run_bytes=run, platform_inputs=inputs)
    visit, = report['verified_platform_visits']
    assert visit['before']['head_distance_m'] == 2000 and visit['after']['head_distance_m'] == 2025
    assert visit['after']['reference_end'] == ('B', reference)
    assert visit['after']['available_length_m'] == 525 and visit['after']['stop_signal_id'] == 24
    updated = project_from({**docs, **outputs}, paths, catalog)
    assert updated.model(('B', siding)).contents[9].values[1] == 90


def test_create_and_move_a_booked_centre_board_beyond_an_internal_turnout(occupied_platform, clean_platform):
    source, paths, catalog, replacement, shapes = occupied_platform
    *_, donor_request, donor_archive = clean_platform
    docs = dict(source)
    edited, split = transform(docs, paths, catalog, 'B', {**replacement, 'waypoints': [
        {'distance_from_first_end_m': metres, 'x': x, 'y': 52}
        for metres, x in [(130, 150), (245, 172), (350, 197), (415, 210)]]}, shapes=shapes)
    docs.update(edited)
    reference, turnout, first, second = [row['end_ids'][0] for row in split['replacement_waypoints']]
    graph = project_from(docs, paths, catalog)
    for end, kind in ((reference, 2), (8, 1)):
        for half in _pair(graph, end):
            half.contents[20].value = kind
    docs['B'] = writer.dump_verified(graph.roots['B'], graph.versions['B'])
    _add_siding(docs, paths, catalog, graph.related(('B', turnout))[1], shapes)
    banks, run, stock = _operating()
    length = stock['length_m']
    first_head, second_head = [1500 + offset + length / 2 for offset in (350, 415)]

    def witness(before, after):
        return {'course_id': 'Booked', 'visit_index': 1, 'expected_train_length_m': length,
                'expected_reference_distance_m': 1630, 'replacement_reference_distance_m': 1630,
                'expected_head_distance_m': before, 'replacement_head_distance_m': after,
                'expected_tail_distance_m': before - length, 'replacement_tail_distance_m': after - length,
                'expected_available_length_m': before - 1500, 'replacement_available_length_m': after - 1500}

    scope = {'station_id': replacement['station_id'], 'expected_platform_edge_ids': split['replacement_edge_ids'],
             'arrival_route': {'document': 'A', 'name': 'R:A-B', 'array_id': 0, 'start_id': 8}}
    add = {**scope, 'action': 'create_station_halt_signals', 'expected_halt_signals': [],
           'donor_signal_id': donor_request['donor_signal_id'], 'maximum_train_length_m': int(length),
           'markers': [{'end_id': first, 'signal_name': 'Centre', 'stop_reference': 'center',
                        'expected_position_from_entry_m': 350}], 'visit_reviews': [witness(2000, first_head)]}
    invalid = {**add, 'markers': [{**add['markers'][0], 'end_id': turnout, 'expected_position_from_entry_m': 245}]}
    with pytest.raises(ValueError, match='interior Ends'):
        transform(docs, paths, catalog, 'B', invalid, shapes=donor_archive, platform_inputs=banks, run_bytes=run)
    changed, creation = transform(docs, paths, catalog, 'B', add, shapes=donor_archive, platform_inputs=banks, run_bytes=run)
    signal, = creation['added_signal_ids']
    assert creation['verified_platform_visits'][0]['after']['head_distance_m'] == first_head
    assert creation['station_reference_end_id'] == reference and creation['unchanged_exit_signal_id'] == 24
    move = {**scope, 'action': 'relocate_station_halt_signal', 'signal_id': signal, 'from_end_id': first,
            'to_end_id': second, 'expected_stop_shift_m': 65,
            'expected_halt_signals': creation['halt_signals_after'], 'visit_reviews': [witness(first_head, second_head)]}
    altered, movement = transform({**docs, **changed}, paths, catalog, 'B', move, platform_inputs=banks, run_bytes=run)
    fresh = project_from({**docs, **altered}, paths, catalog)
    assert movement['verified_platform_visits'][0]['after']['head_distance_m'] == second_head
    assert fresh.model(('B', reference)).contents[11].value is None
    assert fresh.model(('B', first)).contents[11].value is None
    assert fresh.model(('B', second)).contents[11].value is fresh.model(('B', signal))
