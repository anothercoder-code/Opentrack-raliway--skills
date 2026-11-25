"""Resize in-use native station track with an immutable booked timetable."""

from copy import deepcopy

import pytest

from opentrack_ai.current_archive import catalogs, course_factories, path_functions, route_factory, writer
from opentrack_ai.current_archive.consist_workflow.core import summary
from opentrack_ai.current_archive.saved_geometry import project_from, transform
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_itinerary_lifecycle import course_archive
from test_native_rolling_stock_import import stock
from test_operating_plan_edit import connection, dictionary, native_record, row
from test_saved_multi_document_reroute import chain
from test_saved_platform_replacement import occupied_platform


def _operating(timetable_extra=()):
    depot, trains = stock(120)
    vehicle, = catalogs.train_items(trains)
    consist = summary(vehicle, {'Motor': next(iter(catalogs.engine_items(depot)))})
    courses, _ = writer.load(course_archive(Booked=['I:chain:forward']))
    booked, = catalogs.course_items(courses)
    course_factories.settext(booked, 3, 'Passenger')
    course_factories.settext(booked, 4, 'Passenger')
    booked.contents[5].value = 1
    visits = [row('Booked', sign, i, time, connections=timetable_extra if i == 1 else ()) for i, (sign, time) in enumerate(
        [('A', '08:02:00'), ('B', '08:10:00'), ('C', '08:20:00')])]
    course_factories.settext(visits[1], 7, '08:12:00')
    visits[1].contents[10].value = visits[2].contents[10].value = 3
    stations = dictionary({name: native_record('OTStation', *catalogs.LAYOUTS['OTStation'],
                                                {1: [native.string(name)]}) for name in ('A', 'B', 'C')})
    timetable = dictionary({f'Booked#{i}': visit for i, visit in enumerate(visits)})
    bundles = {name: writer.dump_verified(obj) for name, obj in (
        ('depot', depot), ('trains', trains), ('courses', courses), ('timetable', timetable), ('stations', stations))}
    run = (b'Start Day Offset#0#\nStart Time#08:00:00#\nStop Day Offset#0#\n'
           b'Stop Time#09:00:00#\nStep#0.2#\nTrainType#Passenger#\n')
    return bundles, run, consist


def _request(station_id, edge_ids, edits, new_length, vehicle, *, former_head=2000, new_head=2050,
             former_available=500, new_available=550):
    return {'action': 'resize_used_platform_span', 'station_id': station_id,
            'arrival_route': {'document': 'A', 'name': 'R:A-B', 'array_id': 0, 'start_id': 8},
            'expected_platform_edge_ids': edge_ids, 'expected_platform_length_m': 500,
            'replacement_platform_length_m': new_length, 'edges': [
                {'edge_id': key, 'expected_length_m': old, 'length_m': new} for key, old, new in edits],
            'visit_reviews': [{'course_id': 'Booked', 'visit_index': 1, 'expected_train_length_m': vehicle['length_m'],
                               'expected_reference_distance_m': 2000, 'expected_head_distance_m': former_head,
                               'expected_available_length_m': former_available, 'replacement_reference_distance_m': 1500 + new_length,
                               'replacement_head_distance_m': new_head, 'replacement_available_length_m': new_available}]}


def _resize(occupied_platform, operation, operating=None):
    docs, paths, dest, _, _ = occupied_platform
    files, run, _ = _operating() if operating is None else operating
    return transform(docs, paths, dest, 'B', operation, run_bytes=run, platform_inputs=files)


def test_resize_checks_existing_visits_clock_and_original_directed_graph(occupied_platform):
    docs, paths, dest, source, _ = occupied_platform
    _, _, consist = _operating()
    request = _request(source['station_id'], [21], [(21, 500, 550)], 550, consist)
    altered, receipt = _resize(occupied_platform, request)
    assert set(altered) == {'B'} and receipt['nonselected_graph_verified']
    graph = project_from({**docs, **altered}, paths, dest)
    assert graph.model(('B', 21)).contents[9].values[1] == 550
    visit, = receipt['verified_platform_visits']
    old, new = visit['before'], visit['after']
    assert old['reference_end'] == new['reference_end'] == ('B', 8)
    assert old['stop_signal_id'] == new['stop_signal_id'] and old['stop_edge'] == new['stop_edge'] == ('B', 21)
    assert (old['planned_arrival_s'], old['planned_departure_s']) == (new['planned_arrival_s'], new['planned_departure_s'])
    assert (old['available_length_m'], new['available_length_m']) == (500, 550)
    assert (old['head_distance_m'], new['head_distance_m']) == (2000, 2050)
    assert new['minimum_arrival_leg_s'] > old['minimum_arrival_leg_s']
    assert {item['identity'][0] for item in receipt['reviewed_movements'] if item['kind'] == 'itinerary'} >= {
        'I:chain:forward', 'I:chain:reverse'}


def test_resize_rejects_unsafe_booked_length_omission_wrong_expectation_and_linked_formation(occupied_platform):
    _, _, _, source, _ = occupied_platform
    _, _, consist = _operating()
    request = _request(source['station_id'], [21], [(21, 500, 550)], 550, consist)
    too_short = _request(source['station_id'], [21], [(21, 500, 1)], 1, consist)
    with pytest.raises(ValueError, match='absent or too short'):
        _resize(occupied_platform, too_short)
    with pytest.raises(ValueError, match='Review every affected booked'):
        _resize(occupied_platform, {**request, 'visit_reviews': []})
    wrong = deepcopy(request)
    wrong['visit_reviews'][0]['replacement_head_distance_m'] += 1
    with pytest.raises(ValueError, match='native platform stop position'):
        _resize(occupied_platform, wrong)
    with pytest.raises(ValueError, match='Connection requiring a separate formation review'):
        _resize(occupied_platform, request, _operating((connection('Booked', 'Feeder', 'B'),)))


def _add_center_marker(doc, end_id):
    root, version = writer.load_next_compatible(doc)
    models, by_id = route_factory.document(root)
    end = by_id[end_id]
    marker = path_functions.clone(by_id[8].contents[11].value)
    marker.contents[0].value = max(by_id) + 1
    marker.contents[7].value = end
    marker.contents[8].values[:] = [21, 1, 0]
    marker.contents[10].value = native.wrapped('OTSigIndList', [])
    end.contents[11].value = marker
    writer.set_elements(root.contents[2].value, [*models, marker])
    return writer.dump_verified(root, version), marker.contents[0].value


def test_resize_recomputes_center_stop_independently_from_changed_reference_chainage(occupied_platform):
    docs, paths, dest, source, shapes = occupied_platform
    replacement, split = transform(docs, paths, dest, 'B', source, shapes=shapes)
    replacement_ids = split['replacement_edge_ids']
    end_id = split['replacement_waypoints'][0]['end_ids'][0]
    revised, signal_id = _add_center_marker(replacement['B'], end_id)
    project = {**docs, 'B': revised}
    files, run, consist = _operating()
    head = 1630 + consist['length_m'] / 2
    request = _request(source['station_id'], replacement_ids,
                       [(replacement_ids[1], 220, 255), (replacement_ids[2], 150, 145)], 530, consist,
                       former_head=head, new_head=head, former_available=head - 1500, new_available=head - 1500)
    altered, receipt = transform(project, paths, dest, 'B', request, run_bytes=run, platform_inputs=files)
    assert set(altered) == {'B'} and len(receipt['edges']) == 2
    result, = receipt['verified_platform_visits']
    assert result['before']['reference_distance_m'] == 2000 and result['after']['reference_distance_m'] == 2030
    assert result['before']['head_distance_m'] == result['after']['head_distance_m'] == head
    assert result['after']['stop_marker_distance_m'] == 1630 and result['after']['stop_signal_id'] == signal_id
