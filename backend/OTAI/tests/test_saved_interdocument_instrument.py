import pytest

from opentrack_ai.current_archive import native_monitoring, writer
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, project_from
from opentrack_ai.current_archive.saved_interdocument_instrument import relocate_cross_document_measuring_instrument
from opentrack_ai.current_archive.saved_temporary_labels import label_index, new_label

from test_native_monitoring import worksheets
from test_saved_multi_document_reroute import chain


@pytest.fixture
def measurement_transfer(chain, worksheets):
    docs, paths, catalog, _ = chain
    project = project_from(docs, paths, catalog)
    route = project.owned(('A', 8), 'OTRoute', ('R:A-B', 0, 8))
    source = {'action': 'create_instrument', 'end_id': 12, 'name': 'Transfer gauge', 'edge_ids': [23, 22],
              'frame': [123.5, 43.25, 79.5, 45], 'display': ['name', 'clock', 'speed', 'train_count'],
              'visible': False, 'direction_code': 2}
    data, result = native_monitoring.transform(docs['A'], worksheets[1], [source])
    selected, = result['after']['instruments']
    review = {'action': 'relocate_cross_document_measuring_instrument', 'instrument_id': selected['id'],
              'from_end': {'document': 'A', 'end_id': 12}, 'to_end': {'document': 'B', 'end_id': 4},
              'expected_edge_ids': [23, 22], 'replacement_edge_ids': [21, 20],
              'reviewed_end_chain': [{'document': sheet, 'end_id': model} for sheet, model in project.route_view(route)]}
    return {**docs, 'A': data}, paths, catalog, review, selected, source


@pytest.mark.parametrize('unset_frame', [False, True])
def test_transfers_local_references_and_preserves_settings_in_both_archives(measurement_transfer, worksheets, unset_frame):
    documents, paths, catalog, review, selected, source = measurement_transfer
    if unset_frame:
        # Default window geometry and an immutable presentation object shared
        # with a second source instrument are both legal in a native archive.
        data, result = native_monitoring.transform(documents['A'], worksheets[1], [
            {**source, 'end_id': 8, 'name': 'Other gauge'}])
        root, version = writer.load_next_compatible(data)
        _, by_id = native_monitoring.models(root)
        instrument = by_id[selected['id']]
        for slot in (9, 10):
            instrument.contents[slot].values = [0.0, 0.0]
        another = next(row for row in result['after']['instruments'] if row['id'] != selected['id'])
        by_id[another['id']].contents[13].value = instrument.contents[13].value
        documents = {**documents, 'A': writer.dump_verified(root, version)}
    base = project_from(documents, paths, catalog)
    copies, receipt = relocate_cross_document_measuring_instrument(documents, paths, catalog, 'A', review)
    assert sorted(copies) == ['A', 'B']
    fresh = project_from({**documents, **copies}, paths, catalog)
    instrument, = native_monitoring.records(fresh.roots['B'])['instruments']
    assert receipt['from_instrument'] == {'document': 'A', 'instrument_id': selected['id']}
    assert receipt['to_instrument'] == {'document': 'B', 'instrument_id': max(base.byid['B']) + 1}
    assert instrument == {**selected, 'id': max(base.byid['B']) + 1, 'end_id': 4, 'edge_ids': [21, 20],
                          'frame': [0.0] * 4 if unset_frame else [*receipt['after_frame_origin'], 79.5, 45.0]}
    assert selected['id'] not in fresh.byid['A'] and fresh.model(('A', 12)).contents[13].value is None
    assert fresh.model(('B', 4)).contents[13].value is fresh.model(('B', instrument['id']))
    assert receipt['connector_pair'] == (('A', 17), ('B', 0)) and receipt['nonselected_graph_verified']
    assert receipt['native_execution_tested'] is False and _movement_manifest(fresh) == _movement_manifest(base)
    assert len(native_monitoring.records(fresh.roots['A'])['instruments']) == int(unset_frame)


def test_refuses_stale_observation_order_unqualified_track_wrong_direction_and_occupied_end(measurement_transfer, worksheets):
    docs, paths, catalog, review, _, source = measurement_transfer
    for delta, detail in [
        ({'expected_edge_ids': [22, 23]}, 'Edge order'),
        ({'replacement_edge_ids': [20, 20]}, 'distinct destination'),
        ({'replacement_edge_ids': [99999]}, 'OTEdgeModel'),
        ({'reviewed_end_chain': review['reviewed_end_chain'][::-1]}, 'nonrepeating directed chain'),
        ({'from_end': {'document': 'A', 'end_id': 8}}, 'does not carry'),
    ]:
        with pytest.raises(ValueError, match=detail):
            relocate_cross_document_measuring_instrument(docs, paths, catalog, 'A', {**review, **delta})
    occupied, _ = native_monitoring.transform(docs['B'], worksheets[1], [
        {**source, 'end_id': 4, 'name': 'Already placed', 'edge_ids': [20]}])
    with pytest.raises(ValueError, match='already has a measuring instrument'):
        relocate_cross_document_measuring_instrument({**docs, 'B': occupied}, paths, catalog, 'A', review)


def test_signal_stop_measurement_requires_an_actual_target_main_signal(measurement_transfer, worksheets):
    docs, paths, catalog, review, _, source = measurement_transfer
    source, result = native_monitoring.transform(docs['A'], worksheets[1], [
        {**source, 'end_id': 8, 'name': 'Signals only', 'display': ['signal_stops']}])
    review = {**review, 'instrument_id': result['after']['instruments'][-1]['id'],
              'from_end': {'document': 'A', 'end_id': 8}}
    with pytest.raises(ValueError, match='anchored main signal'):
        relocate_cross_document_measuring_instrument({**docs, 'A': source}, paths, catalog, 'A', review)


@pytest.fixture
def labelled_measurement_transfer(measurement_transfer):
    docs, paths, catalog, review, selected, _ = measurement_transfer
    root, version = writer.load_next_compatible(docs['A'])
    graphics, items = native_monitoring.models(root)
    instrument = items[selected['id']]
    label = new_label(native_monitoring.new_id(items), [125.5, 142.0], 'Owned measuring label', 'Helvetica')
    base = label_index(label)
    label.contents[base + 2].value = instrument
    label.contents[base + 3].values = [1, 0, 0]
    instrument.contents[6].value = label
    writer.set_elements(graphics, [*writer.elements(graphics), label])
    docs = {**docs, 'A': writer.dump_verified(root, version)}
    return docs, paths, catalog, {**review, 'expected_label_id': label.contents[0].value}


def test_private_label_moves_with_instrument_and_receives_its_own_local_id(labelled_measurement_transfer):
    docs, paths, catalog, review = labelled_measurement_transfer
    before = project_from(docs, paths, catalog)
    old_label_id = review['expected_label_id']
    old_label = before.model(('A', old_label_id))
    old_base = label_index(old_label)
    new_instrument_id = max(before.byid['B']) + 1
    new_label_id = new_instrument_id + 1
    outputs, receipt = relocate_cross_document_measuring_instrument(docs, paths, catalog, 'A', review)
    fresh = project_from({**docs, **outputs}, paths, catalog)
    assert not ({review['instrument_id'], old_label_id} & set(fresh.byid['A']))
    instrument = fresh.model(('B', new_instrument_id))
    label = fresh.model(('B', new_label_id))
    base = label_index(label)
    assert instrument.contents[6].value is label and label.contents[base + 2].value is instrument
    assert receipt['from_label'] == {'document': 'A', 'label_id': old_label_id}
    assert receipt['to_label'] == {'document': 'B', 'label_id': new_label_id}
    assert receipt['before_label_center'] == [125.5, 142.0]
    translation = [before.model(('B', 4)).contents[slot].value - before.model(('A', 12)).contents[slot].value for slot in (2, 3)]
    assert receipt['after_label_center'] == pytest.approx([
        position + shift for position, shift in zip(receipt['before_label_center'], translation, strict=True)])
    assert receipt['after_label_frame'][:2] == pytest.approx([
        position + shift for position, shift in zip(receipt['before_label_frame'][:2], translation, strict=True)])
    assert receipt['after_label_frame'][2:] == receipt['before_label_frame'][2:]
    assert label.contents[base].value.contents[1].value.elements == old_label.contents[old_base].value.contents[1].value.elements
    assert label.contents[base + 3].values == old_label.contents[old_base + 3].values
    assert receipt['nonselected_graph_verified'] and _movement_manifest(fresh) == _movement_manifest(before)


def test_existing_label_requires_exact_review_and_no_extra_observer(labelled_measurement_transfer):
    docs, paths, catalog, review = labelled_measurement_transfer
    for label_id, message in [(None, 'Confirm the existing owned'), (review['instrument_id'], 'reviewed Label ID')]:
        with pytest.raises(ValueError, match=message):
            relocate_cross_document_measuring_instrument(docs, paths, catalog, 'A', {**review, 'expected_label_id': label_id})
    root, version = writer.load_next_compatible(docs['A'])
    _, items = native_monitoring.models(root)
    label = items[review['expected_label_id']]
    items[8].contents[6].value = label
    with pytest.raises(ValueError, match='without another saved observer'):
        relocate_cross_document_measuring_instrument(
            {**docs, 'A': writer.dump_verified(root, version)}, paths, catalog, 'A', review)
