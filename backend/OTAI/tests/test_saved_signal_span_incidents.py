"""Retain an exact original position speed interval across a new main signal."""

import pytest

from opentrack_ai.current_archive import catalogs, writer
from opentrack_ai.current_archive.infrastructure_incidents.core import create
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.saved_geometry_tools import MainSignalRouteSplit
from opentrack_ai.current_archive.saved_main_signal_split import insert_signal_in_saved_route
from opentrack_ai.current_archive.saved_span_incident_rebinding import span_incident_bindings

from test_itinerary_lifecycle import course_archive
from test_saved_main_signal_split import sending_corridor


@pytest.fixture
def reviewed_case(sending_corridor):
    docs, paths, dest, project, base = sending_corridor
    operation = {**base, 'split_route': {**base['split_route'], 'reserve_with_previous': True}}
    selected = operation['split_route']
    role = selected['route']
    name = role['name']
    primary = project.owned(('A', role['start_id']), 'OTRoute', (name, role['array_id'], role['start_id']))
    sequence = project.route_view(primary)
    boundary = 'A', operation['end_id']
    assert sequence[1] == boundary
    edges = [project.edge_between(first, last) for first, last in zip(sequence, sequence[1:])]
    length = project.model(edges[0]).contents[9].values[1]
    original = {'begin_route': name, 'end_route': name, 'begin_offset_km': f'{(length - 20)/1000:.3f}',
                'end_offset_km': f'{(length + 30)/1000:.3f}'}
    transferred = {**original, 'end_route': selected['continued_name'], 'end_offset_km': '0.030'}
    physical = [{'document': doc, 'edge_id': nid} for doc, nid in edges[:2]]
    event = {'name': 'Cross relay speed', 'type': 'route_span_speed', 'course_id': 'C01', **original,
             'begin_time': '10:00:00', 'end_time': '11:00:00', 'begin_day': 0, 'end_day': 0,
             'enabled': True, 'probability_percentage': 100, 'head_only': True, 'reduced_speed_kmh': 25}
    root, version = writer.load_next_compatible(course_archive(C01=['I:A-B']))
    course, = catalogs.course_items(root)
    course.contents[5].value = 1
    array = root.contents[1].value
    writer.set_elements(array, [create(event, array)])
    selected['route_span_incident_rebindings'] = [{'name': event['name'], 'expected_selector': original,
        'replacement_selector': transferred, 'expected_edge_refs': physical, 'replacement_edge_refs': physical}]
    return docs, paths, dest, project, operation, writer.dump_verified(root, version)


def test_explicit_rebinding_preserves_identical_edge_offsets_on_distinct_native_routes(reviewed_case):
    docs, paths, dest, before, operation, course = reviewed_case
    MainSignalRouteSplit.model_validate(operation['split_route'])
    changed, result = insert_signal_in_saved_route(docs, paths, dest, 'A', operation, course)
    updated = changed.pop('$course_catalog')
    after = project_from({**docs, **changed}, paths, dest)
    old, = span_incident_bindings(course, before)
    new, = span_incident_bindings(updated, after)
    assert new['selector']['end_route'] == operation['split_route']['continued_name']
    assert old['attachment']['edges'] == new['attachment']['edges']
    assert old['attachment']['begin'] == new['attachment']['begin'] and old['attachment']['end'] == new['attachment']['end']
    assert len(old['attachment']['routes']) == 1 and len(new['attachment']['routes']) == 2
    assert result['route_span_incident_rebindings'][0]['after'] == new


def test_review_cannot_move_offset_even_with_same_edge_ids(reviewed_case):
    docs, paths, dest, _, operation, course = reviewed_case
    review, = operation['split_route']['route_span_incident_rebindings']
    review['replacement_selector']['end_offset_km'] = '0.031'
    with pytest.raises(ValueError, match='same directed physical positions and interval'):
        insert_signal_in_saved_route(docs, paths, dest, 'A', operation, course)


def test_omitted_review_or_independent_reservation_are_rejected(reviewed_case):
    docs, paths, dest, _, operation, course = reviewed_case
    selected = operation['split_route']
    with pytest.raises(ValueError, match='ordinary synchronized reservation'):
        insert_signal_in_saved_route(docs, paths, dest, 'A', {**operation, 'split_route': {
            **selected, 'reserve_with_previous': False}}, course)
    del selected['route_span_incident_rebindings']
    with pytest.raises(ValueError, match='saved route-relative Incident'):
        insert_signal_in_saved_route(docs, paths, dest, 'A', operation, course)
