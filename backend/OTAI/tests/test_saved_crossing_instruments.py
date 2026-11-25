from copy import deepcopy

import pytest

from opentrack_ai.current_archive import native_monitoring, writer
from opentrack_ai.current_archive.saved_cross_document_reroute import _inspect_alignment, _walk_crossing
from opentrack_ai.current_archive.saved_crossing_instruments import (
    apply_instrument_edge_rebindings, prepare_instrument_edge_rebindings, verify_instrument_edge_rebindings,
)
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, model_id, position, project_from, transform

from test_native_monitoring import worksheets
from test_saved_geometry import apply, shapes_for
from test_saved_multi_document_reroute import chain
from test_saved_track_reroute import alternative, parallel_spans


@pytest.fixture
def monitored_crossings(chain, worksheets):
    documents, paths, catalog, request = chain
    first, second = request['crossings']
    new_first = first['replacement_edges'][1]['edge_id']
    new_second = second['replacement_edges'][0]['edge_id']
    new, receipt = native_monitoring.transform(documents['B'], worksheets[1], [{
        'action': 'create_instrument', 'end_id': 8, 'name': 'Station Crossing Meter',
        'edge_ids': [23, 21, 20], 'frame': [120, 62, 80, 42], 'direction_code': 2,
        'display': ['course', 'clock', 'speed', 'train_count'], 'visible': False,
    }])
    instrument = receipt['after']['instruments'][0]['id']
    dependency = {field: [row for section in (first, second) for row in section[field]]
                  for field in ('old_edges', 'replacement_edges')}
    review = {'document': 'B', 'instrument_id': instrument, 'expected_end_id': 8, 'expected_edge_ids': [23, 21, 20],
              'edge_rebindings': [{'old_edge_id': 20, 'new_edge_ids': [new_first]},
                                  {'old_edge_id': 23, 'new_edge_ids': [new_second]}]}
    return {**documents, 'B': new}, paths, catalog, request, dependency, review, [new_second, 21, new_first]


def test_one_saved_instrument_preserves_order_settings_and_owner_on_both_crossings(monitored_crossings):
    documents, paths, catalog, request, dependency, review, expected = monitored_crossings
    graph = project_from(documents, paths, catalog)
    movement = _movement_manifest(graph)
    instrument, = native_monitoring.records(graph.roots['B'])['instruments']
    plan, before, after = prepare_instrument_edge_rebindings(graph, dependency, [review])
    assert before == {'B': {20: 1, 23: 1}}
    assert after == {'B': {expected[0]: 1, expected[2]: 1}}
    for crossing in request['crossings']:
        with pytest.raises(ValueError, match='archived observers'):
            _inspect_alignment(graph, crossing, {})
        _inspect_alignment(graph, crossing, {}, reviewed_instruments=before)
    result, = apply_instrument_edge_rebindings(graph, plan)
    assert result['before_edge_ids'] == [23, 21, 20] and result['after_edge_ids'] == expected
    changed = writer.dump_verified(graph.roots['B'], graph.versions['B'])
    fresh = project_from({**documents, 'B': changed}, paths, catalog)
    verify_instrument_edge_rebindings(fresh, plan)
    cold, = native_monitoring.records(fresh.roots['B'])['instruments']
    assert cold == {**instrument, 'edge_ids': expected}
    assert _movement_manifest(fresh) == movement
    for crossing in request['crossings']:
        start = crossing['start_end']['document'], crossing['start_end']['end_id']
        _walk_crossing(fresh, start, crossing['old_edges'], {})
        _walk_crossing(fresh, start, crossing['replacement_edges'], {}, reviewed_instruments=after)


def test_refuses_stale_order_wrong_local_owner_and_incomplete_mapping(monitored_crossings):
    documents, paths, catalog, _, dependency, review, _ = monitored_crossings
    graph = project_from(documents, paths, catalog)
    variants = [({'expected_edge_ids': [20, 21, 23]}, 'Edge order'), ({'expected_end_id': 9}, 'does not carry'),
                ({'edge_rebindings': review['edge_rebindings'][:1]}, 'all old-only')]
    for values, reason in variants:
        with pytest.raises(ValueError, match=reason):
            prepare_instrument_edge_rebindings(graph, dependency, [{**review, **values}])
    duplicate = deepcopy(review)
    duplicate['edge_rebindings'][1]['new_edge_ids'] = duplicate['edge_rebindings'][0]['new_edge_ids']
    with pytest.raises(ValueError, match='repeat an Edge'):
        prepare_instrument_edge_rebindings(graph, dependency, [duplicate])
    assert writer.dump_verified(graph.roots['B'], graph.versions['B']) == documents['B']


@pytest.mark.parametrize(('retire', 'move_members', 'only_owner'), [(True, True, False), (False, False, False), (False, False, True)])
def test_local_instrument_follows_reviewed_parallel_span_owner(parallel_spans, worksheets, retire, move_members, only_owner):
    documents, catalog, operation, junction, old_nodes, target = parallel_spans
    graph = project_from(documents, {'Line': 'Line.opentrack'}, catalog)
    owner = old_nodes[1][1]
    spur = model_id(graph.model(('Line', junction)).contents[10].value)
    old_edge = operation['old_edge_ids'][0]
    members = [old_edge, spur] if move_members else [spur]
    if only_owner:
        members = []
    source = {'action': 'create_instrument', 'end_id': owner, 'name': 'Relocating meter', 'edge_ids': members,
              'frame': [120, 62, 80, 42], 'direction_code': 2, 'display': ['course', 'clock'], 'visible': False}
    monitored, proof = native_monitoring.transform(documents['Line'], worksheets[1], [source])
    before, = proof['after']['instruments']
    if not move_members:
        root, version = writer.load_next_compatible(monitored)
        _, items = native_monitoring.models(root)
        instrument = items[before['id']]
        instrument.contents[9].values = [0.0, 0.0]
        instrument.contents[10].values = [0.0, 0.0]
        monitored = writer.dump_verified(root, version)
    review = {'document': 'Line', 'instrument_id': before['id'], 'expected_end_id': owner, 'replacement_end_id': target,
              'expected_edge_ids': members, 'edge_rebindings': [{'old_edge_id': old_edge,
                  'new_edge_ids': operation['replacement_edge_ids']}] if move_members else []}
    request = {**operation, 'instrument_edge_rebindings': [review], 'retire_original': retire,
               'retire_isolated_end_ids': [owner] if retire else []}
    doc = {**documents, 'Line': monitored}
    outside = next(model_id(graph.model(('Line', spur)).contents[slot].value) for slot in (7, 8)
                   if model_id(graph.model(('Line', spur)).contents[slot].value) != junction)
    with pytest.raises(ValueError, match='corresponding reviewed'):
        apply(doc, catalog, {**request, 'instrument_edge_rebindings': [{**review, 'replacement_end_id': outside}]}, target='Line')
    saved, receipt = apply(doc, catalog, request, target='Line')
    result, = receipt['dependency_transfers']['instrument_edge_rebindings']
    after, = native_monitoring.records(saved.roots['Line'])['instruments']
    wanted = [*operation['replacement_edge_ids'], spur] if move_members else members
    assert result['before_end_id'] == owner and result['after_end_id'] == target and after['end_id'] == target
    assert after['id'] == before['id'] and after['edge_ids'] == wanted
    assert after['direction_code'] == before['direction_code'] and after['display'] == before['display'] and not after['visible']
    assert receipt['dependency_transfers']['native_readback_verified']
    if retire:
        assert owner not in saved.byid['Line'] and set(operation['old_edge_ids']).isdisjoint(saved.byid['Line'])
        assert after['frame'][2:] == [80.0, 42.0] and after['frame'][:2] == result['after_frame_origin']
    else:
        assert saved.model(('Line', owner)).contents[13].value is None and after['frame'] == [0.0, 0.0, 0.0, 0.0]


@pytest.mark.parametrize('junction', [False, True])
def test_continued_route_moves_interior_instrument_before_retiring_its_source(chain, worksheets, junction):
    initial, paths, catalog, source = chain
    docs = dict(initial)
    first, second = deepcopy(source['crossings'])
    shape = shapes_for(docs['A'])

    def edit(operation):
        changed, receipt = transform(docs, paths, catalog, 'A', operation, shapes=shape)
        docs.update(changed)
        return receipt

    graph = project_from(docs, paths, catalog)
    source_end = graph.model(('A', first['start_end']['end_id']))
    alternative_edge = graph.model(('A', first['replacement_edges'][0]['edge_id']))
    destination = next(alternative_edge.contents[slot].value for slot in (7, 8) if alternative_edge.contents[slot].value is not source_end)
    edit({'action': 'move_vertex', 'end_id': model_id(destination), 'x': position(destination)[0], 'y': position(source_end)[1]})
    for field in ('old_edges', 'replacement_edges'):
        split = edit({'action': 'split_edge', 'edge_id': first[field][0]['edge_id'], 'first_length_m': 100})
        first[field].insert(1, {'document': 'A', 'edge_id': split['new_edge_id']})
    graph = project_from(docs, paths, catalog)
    start = ('A', first['start_end']['end_id'])
    old_nodes, _, _, _ = _walk_crossing(graph, start, first['old_edges'])
    new_nodes, _, _, new_profiles = _walk_crossing(graph, start, first['replacement_edges'])
    old_owner, new_owner = old_nodes[0][1], new_nodes[0][1]
    first['expected_replacement_safety_elements'] = [
        {'document': row['document'], 'element_id': row['safety_element_id']} for row in new_profiles]
    old_edge, new_edge = (first[field][0]['edge_id'] for field in ('old_edges', 'replacement_edges'))
    docs['A'], receipts = native_monitoring.transform(docs['A'], worksheets[1], [{
        'action': 'create_instrument', 'end_id': old_owner, 'name': 'Crossing meter', 'edge_ids': [old_edge],
        'frame': [120.5, 62, 80, 42], 'direction_code': 2, 'display': ['course', 'clock'], 'visible': False}])
    instrument, = receipts['after']['instruments']
    review = {'document': 'A', 'instrument_id': instrument['id'], 'expected_end_id': old_owner, 'replacement_end_id': new_owner,
              'expected_edge_ids': [old_edge], 'edge_rebindings': [{'old_edge_id': old_edge, 'new_edge_ids': [new_edge]}]}
    common = {'retire_original': True, 'retire_isolated_ends': [{'document': 'A', 'end_id': old_owner}],
              'instrument_edge_rebindings': [review]}
    if junction:
        first['routes'] = [{'document': 'A', 'name': 'R:A-B', 'array_id': 0, 'start_id': 8},
                           {'document': 'B', 'name': 'R:B-A', 'array_id': 0, 'start_id': 9}]
        second['routes'] = [{'document': 'B', 'name': 'R:B-C', 'array_id': 0, 'start_id': 8},
                            {'document': 'C', 'name': 'R:C-B', 'array_id': 0, 'start_id': 9}]
        request = {'action': 'reroute_junction_track_spans', 'crossings': [first, second],
                   'witness_itineraries': {'I:chain:forward': 4100}, **common}
    else:
        request = {'action': 'reroute_cross_document_track_span', **first, **common}
    updated, report = transform(docs, paths, catalog, 'A', request)
    fresh = project_from({**docs, **updated}, paths, catalog)
    assert old_owner not in fresh.byid['A'] and old_edge not in fresh.byid['A']
    saved, = native_monitoring.records(fresh.roots['A'])['instruments']
    record, = report['dependency_transfers']['instrument_edge_rebindings']
    assert saved['id'] == instrument['id'] and saved['end_id'] == new_owner and saved['edge_ids'] == [new_edge]
    assert record['before_end_id'] == old_owner and record['after_end_id'] == new_owner
    assert report['dependency_transfers']['native_readback_verified'] and saved['frame'][:2] == record['after_frame_origin']
