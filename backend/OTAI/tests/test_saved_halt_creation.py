import pytest

from opentrack_ai.current_archive import route_factory, writer
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, model_id, project_from, transform
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_saved_halt_location import case


@pytest.fixture
def clean_platform(case):
    docs, paths, dest, previous, _ = case
    root, version = writer.load_next_compatible(docs['RDG'])
    models, by_id = route_factory.document(root)
    original = by_id[previous['signal_id']]
    original.contents[8].values = [8, 1, 0]
    original.contents[9].values = [1, 400, 129, 40]
    original.contents[10].value = native.wrapped('OTSigIndList', [])
    donor = writer.dump_verified(root, version)
    original.contents[7].value.contents[11].value = None
    writer.set_elements(root.contents[2].value, [obj for obj in models if obj is not original])
    docs = {'RDG': writer.dump_verified(root, version)}
    request = {'action': 'create_station_halt_signals', 'station_id': previous['station_id'],
               'arrival_route': previous['arrival_route'], 'donor_signal_id': previous['signal_id'],
               'expected_platform_edge_ids': previous['expected_platform_edge_ids'], 'expected_halt_signals': [],
               'markers': [{'end_id': key, 'signal_name': f'P9_{length}M', 'stop_reference': 'length',
                            'maximum_length_for_marker_m': length, 'graphic_offset_y': 8,
                            'expected_position_from_entry_m': distance}
                           for key, length, distance in [(previous['from_end_id'], 150, 100), (previous['to_end_id'], 250, 200)]]}
    return docs, paths, dest, request, donor


def test_creates_two_length_markers_with_original_priority_and_unchanged_movement(clean_platform):
    docs, paths, dest, operation, donor = clean_platform
    output, report = transform(docs, paths, dest, 'RDG', operation, shapes=donor)
    before = project_from(docs, paths, dest)
    after = project_from(output, paths, dest)
    assert _movement_manifest(before) == _movement_manifest(after)
    assert report['nonselected_graph_verified'] and report['unchanged_exit_signal_id'] > 0
    first, second = report['added_signal_ids']
    assert report['halt_signals_after'] == [
        {'signal_id': signal_id, 'end_id': operation['markers'][i]['end_id'], 'signal_type': code}
        for i, (signal_id, code) in enumerate([(first, 51), (second, 52)])]
    assert [(row['length_lte_m'], row['after']['signal_id']) for row in report['stop_selection_by_train_length']] == [
        (150, first), (250, second), (None, report['unchanged_exit_signal_id'])]
    for marker_id in (first, second):
        marker = after.model(('RDG', marker_id))
        owner = marker.contents[7].value
        assert owner.contents[11].value is marker and marker.contents[3].value - owner.contents[3].value == 8
        assert not route_factory.wrapper(marker.contents[10].value, 'OTSigIndList')


@pytest.mark.parametrize(('reference', 'code', 'factor'), [('head', 6, 0), ('center', 21, 0.5), ('tail', 20, 1)])
def test_general_stop_types_map_to_train_head_and_audited_length(clean_platform, reference, code, factor):
    docs, paths, dest, request, donor = clean_platform
    first, second = request['markers']
    regular = {**second, 'signal_name': 'General', 'stop_reference': reference, 'maximum_length_for_marker_m': None}
    output, report = transform(docs, paths, dest, 'RDG', {**request, 'markers': [first, regular],
                               'maximum_train_length_m': 100}, shapes=donor)
    marked = project_from(output, paths, dest).model(('RDG', regular['end_id'])).contents[11].value
    assert marked.contents[8].values[0] == code
    selection, = report['stop_selection_by_train_length']
    assert selection['after']['signal_id'] == model_id(marked)
    assert selection['after']['head_offset_per_train_m'] == factor
    assert selection['after']['example_head_position_m'] == 200 + factor * 100


def test_refuses_unreviewed_location_and_train_tail_clearance(clean_platform):
    docs, paths, dest, request, donor = clean_platform
    _, marker = request['markers']
    tail = {**marker, 'stop_reference': 'tail', 'maximum_length_for_marker_m': None}
    with pytest.raises(ValueError, match='beyond the existing exit signal'):
        transform(docs, paths, dest, 'RDG', {**request, 'markers': [tail], 'maximum_train_length_m': 101}, shapes=donor)
    with pytest.raises(ValueError, match='physical marker position differs'):
        transform(docs, paths, dest, 'RDG', {**request, 'markers': [{**marker, 'expected_position_from_entry_m': 201}]}, shapes=donor)
