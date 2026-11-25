import pytest

from opentrack_ai.current_archive.multi_document.core import ident
from opentrack_ai.current_archive.network_operating_plan import route_trace
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, project_from, transform

from test_saved_cross_platform_halts import cross_platform
from test_saved_geometry import shapes_for
from test_saved_multi_document_reroute import chain
from test_saved_platform_resize import _operating


@pytest.mark.parametrize(('document', 'edge_id'), [('A', 23), ('B', 20)])
def test_split_on_either_side_keeps_the_platform_and_connector(cross_platform, document, edge_id):
    documents, paths, dest, baseline = cross_platform
    request = {**baseline, 'action': 'split_cross_document_platform_edge', 'reference_document': 'B',
               'edge_id': edge_id, 'expected_edge_length_m': 500, 'first_length_m': 215}
    original = project_from(documents, paths, dest)
    updated, report = transform(documents, paths, dest, document, request, shapes=shapes_for(documents[document]))
    assert set(updated) == {document} and report['lengths_m'] == [215, 285]
    assert report['cross_platform']['length_m'] == 1500
    fresh = project_from({**documents, **updated}, paths, dest)
    assert fresh.block_end(('A', 17)) == ('B', 0)
    assert _movement_manifest(fresh, [(document, item) for item in report['new_end_ids']]) == _movement_manifest(original)
    station = fresh.model((document, report['station_id']))
    for item in report['new_end_ids']:
        assert fresh.model((document, item)).contents[12].value is station
    with pytest.raises(ValueError, match='Edge length differs'):
        transform(documents, paths, dest, document, {**request, 'expected_edge_length_m': 501},
                  shapes=shapes_for(documents[document]))


def test_resize_both_platform_documents_updates_the_booked_stop(cross_platform):
    documents, paths, dest, baseline = cross_platform
    stock, run, consist = _operating()
    request = {**baseline, 'action': 'resize_used_cross_document_platform_span', 'expected_platform_length_m': 1500,
               'replacement_platform_length_m': 1575,
               'edges': [{'document': 'A', 'edge_id': 23, 'expected_length_m': 500, 'length_m': 525},
                         {'document': 'B', 'edge_id': 21, 'expected_length_m': 500, 'length_m': 550}],
               'visit_reviews': [{'course_id': 'Booked', 'visit_index': 1, 'expected_train_length_m': consist['length_m'],
                                  'expected_reference_distance_m': 2000, 'expected_head_distance_m': 2000,
                                  'expected_available_length_m': 1500, 'replacement_reference_distance_m': 2075,
                                  'replacement_head_distance_m': 2075, 'replacement_available_length_m': 1575}]}
    updated, report = transform(documents, paths, dest, 'B', request, platform_inputs=stock, run_bytes=run)
    assert set(updated) == {'A', 'B'}
    stop, = report['verified_platform_visits']
    assert stop['before']['reference_end'] == stop['after']['reference_end'] == ('B', 8)
    assert stop['after']['head_distance_m'] == 2075 and report['nonselected_graph_verified']
    with pytest.raises(ValueError, match='reciprocal native connector'):
        transform(documents, paths, dest, 'B', {**request, 'expected_connector_pair': {
            'a': request['expected_connector_pair']['b'], 'b': request['expected_connector_pair']['a']}},
            platform_inputs=stock, run_bytes=run)


@pytest.mark.parametrize('branch_end', [4, 5])
def test_resize_crossing_berth_keeps_local_turnout_and_reciprocal_connector(cross_platform, branch_end):
    documents, paths, dest, baseline = cross_platform
    vertex, receipt = transform(documents, paths, dest, 'B', {
        'action': 'insert_vertex', 'x': 270, 'y': 160, 'orientation': 'horizontal',
        'names': ['Passing branch', 'Passing branch reverse']}, shapes=shapes_for(documents['B']))
    documents = {**documents, **vertex}
    branch, added = transform(documents, paths, dest, 'B', {
        'action': 'insert_edge', 'end_ids': [branch_end, receipt['added_vertex_end_ids'][0]],
        'length_m': 75, 'track_name': 'Siding', 'line_name': 'Line', 'remark': '',
        'allow_safety_regroup': True, 'radius_m': 0, 'gradient_per_mille': 0, 'rack_rail': False,
        'speeds': [{'train_type': '0', 'speed12_kmh': 40, 'speed21_kmh': 40}]}, shapes=shapes_for(documents['B']))
    documents.update(branch)
    original = project_from(documents, paths, dest)
    span = [('A', 23), ('B', 20), ('B', 21)]
    stock, run, consist = _operating()
    request = {**baseline, 'action': 'resize_used_cross_document_platform_span',
               'expected_platform_length_m': 1500, 'replacement_platform_length_m': 1575,
               'edges': [{'document': 'A', 'edge_id': 23, 'expected_length_m': 500, 'length_m': 525},
                         {'document': 'B', 'edge_id': 21, 'expected_length_m': 500, 'length_m': 550}],
               'visit_reviews': [{'course_id': 'Booked', 'visit_index': 1, 'expected_train_length_m': consist['length_m'],
                                  'expected_reference_distance_m': 2000, 'expected_head_distance_m': 2000,
                                  'expected_available_length_m': 1500, 'replacement_reference_distance_m': 2075,
                                  'replacement_head_distance_m': 2075, 'replacement_available_length_m': 1575}]}
    updated, report = transform(documents, paths, dest, 'B', request, platform_inputs=stock, run_bytes=run)
    fresh = project_from({**documents, **updated}, paths, dest)
    assert set(updated) == {'A', 'B'}
    assert fresh.block_end(('A', 17)) == ('B', 0) and fresh.block_end(('B', 0)) == ('A', 17)
    assert fresh.report()['continuations'] == original.report()['continuations']
    itinerary, = [item for item in fresh.dests if ident(item)[0] == 'I:chain:forward']
    trace = route_trace(fresh, itinerary)
    visit, = [row for row in trace['visits'] if row['end_key'] == ('B', 8)]
    assert visit['stopping_area_edge_keys'] == span and visit['stopping_area_length_m'] == 1575
    assert ('B', added['edge_id']) not in trace['edges']
    assert fresh.model(('B', added['edge_id'])).contents[9].values[1] == 75
    assert report['nonselected_graph_verified']
