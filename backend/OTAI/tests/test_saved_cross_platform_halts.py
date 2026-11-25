import pytest

from opentrack_ai.current_archive import path_functions, writer
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, model_id, project_from, transform
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_saved_halt_creation import case, clean_platform
from test_saved_geometry import shapes_for
from test_saved_multi_document_reroute import chain
from test_saved_platform_resize import _operating


@pytest.fixture(scope='module')
def cross_platform(chain):
    initial, paths, catalog, alternatives = chain
    docs = dict(initial)
    for edge in alternatives['crossings'][0]['replacement_edges']:
        updated, _ = transform(docs, paths, catalog, edge['document'], {'action': 'delete_edge', 'edge_id': edge['edge_id']})
        docs.update(updated)
    project = project_from(docs, paths, catalog)
    local_a = path_functions.clone(project.model(('A', 12)).contents[12].value)
    local_b = project.model(('B', 8)).contents[12].value
    local_a.contents[0].value = max(project.byid['A']) + 1
    local_a.contents[7].value = native.string(path_functions.string(local_b.contents[7].value))
    writer.set_elements(project.roots['A'].contents[2].value, [*project.models['A'], local_a])
    for key in (('A', 12), ('A', 13), ('A', 16)):
        project.model(key).contents[12].value = local_a
    project.model(('B', 1)).contents[12].value = local_b
    for name in ('A', 'B'):
        docs[name] = writer.dump_verified(project.roots[name], project.versions[name])
    request = {'action': 'create_cross_document_station_halt_signals', 'maximum_train_length_m': 90,
        'expected_station_sign': path_functions.string(local_b.contents[7].value),
        'station_areas': [{'document': 'A', 'station_id': model_id(local_a)}, {'document': 'B', 'station_id': model_id(local_b)}],
        'arrival_route': {'document': 'A', 'start_id': 8, 'array_id': 0, 'name': 'R:A-B'},
        'expected_connector_pair': {'a': {'document': 'A', 'end_id': 17}, 'b': {'document': 'B', 'end_id': 0}},
        'expected_platform_edge_ids': [{'document': name, 'edge_id': key} for name, key in [('A', 23), ('B', 20), ('B', 21)]],
        'expected_halt_signals': [], 'markers': [
            {'document': 'A', 'end_id': 12, 'signal_name': 'tail_a', 'stop_reference': 'tail',
             'expected_position_from_entry_m': 0},
            {'document': 'B', 'end_id': 4, 'signal_name': 'length_b', 'stop_reference': 'length',
             'maximum_length_for_marker_m': 200, 'expected_position_from_entry_m': 1000}]}
    return docs, paths, catalog, request


def test_creates_document_qualified_marks_on_both_worksheets(cross_platform, clean_platform):
    docs, paths, catalog, request = cross_platform
    *_, old_request, donor = clean_platform
    operation = {**request, 'donor_signal_id': old_request['donor_signal_id']}
    output, report = transform(docs, paths, catalog, 'B', operation, shapes=donor)
    assert set(output) == {'A', 'B'}
    assert report['platform_length_m'] == 1500 and report['connector_pair'] == (('A', 17), ('B', 0))
    assert report['nonselected_graph_verified'] and report['destination_catalog_unchanged']
    initial = project_from(docs, paths, catalog)
    saved = project_from({**docs, **output}, paths, catalog)
    assert _movement_manifest(initial) == _movement_manifest(saved)
    assert initial.report()['continuations'] == saved.report()['continuations']
    evidence, = report['stop_selection_by_train_length']
    assert (evidence['before']['document'], evidence['before']['example_head_position_m']) == ('B', 1500)
    assert (evidence['after']['document'], evidence['after']['example_head_position_m']) == ('A', 90)
    for row, end_id, code in zip(report['added_signals'], (12, 4), (20, 9), strict=True):
        signal = saved.model((row['document'], row['signal_id']))
        end = saved.model((row['document'], end_id))
        assert end.contents[11].value is signal and signal.contents[7].value is end
        assert signal.contents[8].values[0] == code


def test_rejects_connector_half_and_unreviewed_platform_order(cross_platform, clean_platform):
    docs, paths, catalog, request = cross_platform
    *_, old_request, donor = clean_platform
    operation = {**request, 'donor_signal_id': old_request['donor_signal_id']}
    crossing = {**operation['markers'][0], 'end_id': 16, 'expected_position_from_entry_m': 500}
    with pytest.raises(ValueError, match='ordinary paired platform Ends'):
        transform(docs, paths, catalog, 'B', {**operation, 'markers': [crossing]}, shapes=donor)
    with pytest.raises(ValueError, match='ordered two-worksheet platform Edge sequence'):
        transform(docs, paths, catalog, 'B', {**operation, 'expected_platform_edge_ids': operation['expected_platform_edge_ids'][::-1]}, shapes=donor)


def test_moves_existing_cross_platform_head_and_native_indication(cross_platform, clean_platform):
    docs, paths, catalog, request = cross_platform
    *_, old_request, donor = clean_platform
    source = {**request['markers'][0], 'stop_reference': 'head', 'signal_name': 'head_a'}
    created, receipt = transform(docs, paths, catalog, 'B', {**request, 'markers': [source],
        'donor_signal_id': old_request['donor_signal_id']}, shapes=donor)
    source_id = receipt['added_signals'][0]['signal_id']
    baseline = project_from({**docs, **created}, paths, catalog)
    marker = baseline.model(('A', source_id))
    marker.contents[10].value = native.wrapped('OTSigIndList', [native.obj([('OTSigInd', 0), ('NSObject', 0)],
        [('i', [0]), ('@', [marker.contents[7].value])])])
    marker.contents[9].values[1] = 415
    source_docs = {**docs, 'A': writer.dump_verified(baseline.roots['A'], baseline.versions['A'])}
    action = {**request, 'action': 'relocate_cross_document_station_halt_signal', 'signal_id': source_id,
              'from_end': {'document': 'A', 'end_id': 12}, 'to_end': {'document': 'B', 'end_id': 4},
              'expected_stop_shift_m': 1000, 'expected_halt_signals': receipt['halt_signals_after']}
    output, report = transform(source_docs, paths, catalog, 'B', action)
    assert set(output) == {'A', 'B'} and report['stop_shift_m'] == 1000 and report['nonselected_graph_verified']
    assert report['from_signal'] == {'document': 'A', 'signal_id': source_id}
    saved = project_from({**source_docs, **output}, paths, catalog)
    assert _movement_manifest(baseline) == _movement_manifest(saved) and baseline.report()['continuations'] == saved.report()['continuations']
    assert saved.model(('A', 12)).contents[11].value is None and source_id not in saved.byid['A']
    target_id = report['to_signal']['signal_id']
    new = saved.model(('B', target_id))
    new_owner = saved.model(('B', 4))
    assert new.contents[7].value is new_owner and new_owner.contents[11].value is new
    indication, = path_functions.mutable_array(new.contents[10].value.contents[0].value)
    assert indication.contents[1].value is new_owner and new.contents[9].values[1] == 415
    assert report['stable_stop_signal_selection_by_train_length'][0]['signal_id'] == ('B', target_id)
    with pytest.raises(ValueError, match='stop shift'):
        transform(source_docs, paths, catalog, 'B', {**action, 'expected_stop_shift_m': 999})
    with pytest.raises(ValueError, match='opposite sides'):
        transform(source_docs, paths, catalog, 'B', {**action, 'to_end': {'document': 'A', 'end_id': 16}})
    indication_array = marker.contents[10].value.contents[0].value
    original_indication, = path_functions.mutable_array(indication_array)
    writer.set_elements(indication_array, [original_indication, original_indication])
    shared = {**source_docs, 'A': writer.dump_verified(baseline.roots['A'], baseline.versions['A'])}
    with pytest.raises(ValueError, match='saved halt indication is shared'):
        transform(shared, paths, catalog, 'B', action)


@pytest.mark.parametrize(('reference', 'factor'), [('center', 0.5), ('tail', 1)])
def test_relocates_booked_cross_platform_center_and_tail_markers(cross_platform, clean_platform, reference, factor):
    docs, paths, catalog, request = cross_platform
    *_, donor_request, donor = clean_platform
    updated, split = transform(docs, paths, catalog, 'A', {'action': 'split_edge', 'edge_id': 22, 'first_length_m': 250},
                               shapes=shapes_for(docs['A']))
    expanded = project_from({**docs, **updated}, paths, catalog)
    area = expanded.model(('A', request['station_areas'][0]['station_id']))
    for end_id in split['new_end_ids']:
        expanded.model(('A', end_id)).contents[12].value = area
    source = {**docs, 'A': writer.dump_verified(expanded.roots['A'], expanded.versions['A'])}
    base = {**request, 'expected_platform_edge_ids': [
        {'document': 'A', 'edge_id': split['new_edge_id']}, *request['expected_platform_edge_ids']]}
    marker = {**request['markers'][0], 'stop_reference': reference, 'signal_name': f'booked_{reference}',
              'expected_position_from_entry_m': 250}
    output, created = transform(source, paths, catalog, 'B', {**base, 'markers': [marker],
        'donor_signal_id': donor_request['donor_signal_id']}, shapes=donor)
    source.update(output)
    stock, run, consist = _operating()
    length = consist['length_m']
    old_head, new_head = (position + length * factor for position in (500, 1500))
    adopted = {'course_id': 'Booked', 'visit_index': 1, 'expected_train_length_m': length,
               'expected_reference_distance_m': 2000, 'replacement_reference_distance_m': 2000,
               'expected_head_distance_m': old_head, 'replacement_head_distance_m': new_head,
               'expected_tail_distance_m': old_head - length, 'replacement_tail_distance_m': new_head - length,
               'expected_available_length_m': old_head - 250, 'replacement_available_length_m': new_head - 250}
    action = {**base, 'action': 'relocate_cross_document_station_halt_signal',
              'signal_id': created['added_signals'][0]['signal_id'],
              'from_end': {'document': 'A', 'end_id': 12}, 'to_end': {'document': 'B', 'end_id': 4},
              'expected_stop_shift_m': 1000, 'expected_halt_signals': created['halt_signals_after'],
              'visit_reviews': [adopted]}
    with pytest.raises(ValueError, match='run-bound operating catalogs'):
        transform(source, paths, catalog, 'B', action)
    updated, result = transform(source, paths, catalog, 'B', action, platform_inputs=stock, run_bytes=run)
    assert set(updated) == {'A', 'B'} and result['stop_reference'] == reference and result['nonselected_graph_verified']
    assert (result['marker_before_m'], result['marker_after_m']) == (250, 1250)
    original, revised = project_from(source, paths, catalog), project_from({**source, **updated}, paths, catalog)
    assert _movement_manifest(original) == _movement_manifest(revised)
    stop, = result['verified_platform_visits']
    before, after = stop['before'], stop['after']
    assert (before['head_distance_m'], after['head_distance_m']) == (old_head, new_head)
    assert (before['tail_distance_m'], after['tail_distance_m']) == (old_head - length, new_head - length)
    assert (before['head_offset_from_marker_m'], after['head_offset_from_marker_m']) == (length * factor,) * 2
    assert before['stop_edge'][0] == 'A' and after['stop_edge'][0] == 'B'
    assert revised.model(('A', 12)).contents[11].value is None
    received = revised.model(('B', 4)).contents[11].value
    assert received.contents[0].value == result['to_signal']['signal_id']
    wrong = {**adopted, 'replacement_tail_distance_m': new_head - length + 1}
    with pytest.raises(ValueError, match='native train tail position differs'):
        transform(source, paths, catalog, 'B', {**action, 'visit_reviews': [wrong]},
                  platform_inputs=stock, run_bytes=run)
