import pytest

from opentrack_ai.current_archive import native_monitoring, native_occupation_groups, path_functions
from opentrack_ai.current_archive.current_shunting_workflow import core as shunting
from opentrack_ai.current_archive.itinerary_edit_tools import set_safety_margins
from opentrack_ai.current_archive.route_edit_tools import _route_shape
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, model_id, project_from

from test_saved_geometry import apply, shapes_for
from test_native_monitoring import worksheets
from test_saved_track_replacement import alternative
from test_saved_track_topology import save_project


@pytest.fixture
def parallel_spans(alternative):
    docs, catalog, edge_id, replacement, via = alternative
    shape = shapes_for(docs['Line'])
    source = project_from(docs, {'Line': 'Line.opentrack'}, catalog)
    original = source.model(('Line', edge_id))
    first = model_id(original.contents[7].value)
    length = original.contents[9].values[1]
    split, divided = apply(docs, catalog, {'action': 'split_edge', 'edge_id': edge_id,
                                          'first_length_m': length // 3}, target='Line', shapes=shape)
    old_edges = [edge_id, divided['new_edge_id']]
    split.model(('Line', replacement[0])).contents[9].values[1] += 120
    spur, vertex = apply(save_project(split), catalog, {'action': 'insert_vertex', 'x': 117, 'y': 160,
                                                        'orientation': 'horizontal', 'names': ['', '']},
                         target='Line', shapes=shape)
    junction = spur.related(('Line', via))[1]
    spur, _ = apply(save_project(spur), catalog, {'action': 'insert_edge', 'end_ids': [junction, vertex['added_vertex_end_ids'][0]],
        'length_m': 50, 'radius_m': 0, 'gradient_per_mille': 0, 'remark': '', 'rack_rail': False,
        'allow_safety_regroup': False, 'track_name': 'Default spur', 'line_name': '',
        'speeds': [{'train_type': '0', 'speed12_kmh': 20, 'speed21_kmh': 20}]}, target='Line', shapes=shape)
    spur, _ = apply(save_project(spur), catalog, {'action': 'set_vertex_details', 'end_id': junction,
        'both_halves': False, 'changes': {'default_second_leg': True, 'switch_time_s': 2}}, target='Line')
    source_bytes = save_project(spur)
    old_route = spur.route_view(spur.routes[0])
    safety = [model_id(spur.model(('Line', item)).contents[7].value.contents[7].value) for item in replacement]
    operation = {'action': 'reroute_used_track_span', 'start_end_id': first, 'old_edge_ids': old_edges,
                 'replacement_edge_ids': replacement, 'expected_replacement_safety_element_ids': safety,
                 'expected_replacement_length_m': length + 120}
    return source_bytes, catalog, operation, junction, old_route, via


def with_partial_shunting(docs, old_route):
    source, _ = shunting.create(docs['Line'], {'name': 'S:Partial', 'description': '',
        'end_ids': [key[1] for key in old_route[:2]], 'speed_kmh': 20.0, 'release_time_s': 1, 'reservation_time_s': 1})
    return {**docs, 'Line': source}


def test_reroute_alternative_turnout_and_keep_partial_movements(parallel_spans):
    docs, catalog, operation, junction, old_route, via = parallel_spans
    docs = with_partial_shunting(docs, old_route)
    original = project_from(docs, {'Line': 'Line.opentrack'}, catalog)
    updated, report = apply(docs, catalog, operation, target='Line')
    assert report['original_track_chain_retained'] and report['signal_and_release_settings_preserved']
    assert all(edge in updated.byid['Line'] for edge in operation['old_edge_ids'])
    assert updated.route_view(updated.routes[0]) == [old_route[0], ('Line', via), old_route[-1]]
    assert {row['kind'] for row in report['affected_movement_distances']} == {'route', 'shunting', 'path', 'itinerary'}
    assert all(row['after_distance_m'] - row['before_distance_m'] == 120 for row in report['affected_movement_distances'])
    assert next(row['switch'] for row in report['replacement_span']
                if row['switch'] and row['switch']['end_id'] == junction) == {
                    'end_id': junction, 'selected_leg': 1, 'default_leg': 2, 'switch_time_s': 2.0,
                }
    partial = next(key for key in original.shunting_movements if key[1] == 'S:Partial')
    assert original.shunting_movements[partial] == updated.shunting_movements[partial] == tuple(old_route[:2])


def test_reroute_retires_old_edges_and_explicit_orphan_pair(parallel_spans):
    docs, catalog, operation, _, old_route, _ = parallel_spans
    retained, _ = apply(docs, catalog, operation, target='Line')
    orphan = old_route[1]
    orphan_pair = {orphan[1], retained.related(orphan)[1]}
    updated, report = apply(docs, catalog, {**operation, 'retire_original': True,
        'retire_isolated_end_ids': [orphan[1]]}, target='Line')

    assert report['original_track_chain_retained'] is False
    assert report['signal_and_release_settings_preserved']
    assert [row['edge_id'] for row in report['retirement']['edges']] == operation['old_edge_ids']
    assert set(report['retirement']['removed_end_ids']) == orphan_pair
    assert orphan_pair.isdisjoint(updated.byid['Line'])
    assert set(operation['old_edge_ids']).isdisjoint(updated.byid['Line'])
    assert set(operation['replacement_edge_ids']) <= updated.byid['Line'].keys()
    assert _movement_manifest(updated) == _movement_manifest(retained)


@pytest.mark.parametrize('retire', [False, True])
def test_local_reroute_transfers_reviewed_instrument_members_at_fixed_outer_end(parallel_spans, worksheets, retire):
    docs, catalog, operation, junction, old_route, _ = parallel_spans
    project = project_from(docs, {'Line': 'Line.opentrack'}, catalog)
    spur = model_id(project.model(('Line', junction)).contents[10].value)
    old = operation['old_edge_ids'][0]
    replacement = operation['replacement_edge_ids']
    owner = operation['start_end_id']
    source = {'action': 'create_instrument', 'end_id': owner, 'name': 'Span Meter',
              'edge_ids': [spur, old], 'frame': [120, 62, 80, 42], 'direction_code': 2,
              'display': ['course', 'clock', 'speed', 'train_count'], 'visible': False}
    monitored, receipt = native_monitoring.transform(docs['Line'], worksheets[1], [source])
    expected, = receipt['after']['instruments']
    review = {'document': 'Line', 'instrument_id': expected['id'], 'expected_end_id': owner,
              'expected_edge_ids': [spur, old],
              'edge_rebindings': [{'old_edge_id': old, 'new_edge_ids': replacement}]}
    with pytest.raises(ValueError, match='archived observers'):
        apply({**docs, 'Line': monitored}, catalog, operation, target='Line')
    result, report = apply({**docs, 'Line': monitored}, catalog,
                           {**operation, 'retire_original': retire, 'instrument_edge_rebindings': [review]},
                           target='Line')
    changes = report['dependency_transfers']
    instrument, = native_monitoring.records(result.roots['Line'])['instruments']
    assert instrument == {**expected, 'edge_ids': [spur, *replacement]}
    assert changes['native_readback_verified']
    assert changes['instrument_edge_rebindings'][0]['after_edge_ids'] == instrument['edge_ids']
    assert (old in result.byid['Line']) == (not retire)

    interior = old_route[1][1]
    inside, receipt = native_monitoring.transform(docs['Line'], worksheets[1], [{**source, 'end_id': interior}])
    wrong = {**review, 'expected_end_id': interior, 'instrument_id': receipt['after']['instruments'][0]['id']}
    with pytest.raises(ValueError, match='Span interiors must be ordinary Ends'):
        apply({**docs, 'Line': inside}, catalog, {**operation, 'instrument_edge_rebindings': [wrong]}, target='Line')
    if retire:
        unrelated, _ = native_monitoring.transform(docs['Line'], worksheets[1], [{**source, 'edge_ids': [spur]}])
        with pytest.raises(ValueError, match='Track endpoints carry measuring instruments'):
            apply({**docs, 'Line': unrelated}, catalog, {**operation, 'retire_original': True}, target='Line')


def test_reroute_retirement_requires_complete_reference_closure(parallel_spans):
    docs, catalog, operation, _, old_route, _ = parallel_spans
    retire = {**operation, 'retire_original': True}
    with pytest.raises(ValueError, match="saved shunting 'S:Partial' still traverses"):
        apply(with_partial_shunting(docs, old_route), catalog, retire, target='Line')

    monitored, _ = native_occupation_groups.transform(docs['Line'], 'Line', [
        {'action': 'create', 'name': 'OldBranch', 'edge_ids': [operation['old_edge_ids'][0]]},
    ])
    with pytest.raises(ValueError, match="occupation monitor 'OldBranch' still refers"):
        apply({**docs, 'Line': monitored}, catalog, retire, target='Line')

    with pytest.raises(ValueError, match='Only confirmed interior pairs'):
        apply(docs, catalog, {**retire, 'retire_isolated_end_ids': [operation['start_end_id']]}, target='Line')


def test_explicit_span_requests_fail_mismatched_safety_or_removed_release_anchors(parallel_spans):
    docs, catalog, operation, _, old_route, _ = parallel_spans
    with pytest.raises(ValueError, match='ordered Safety Element'):
        apply(docs, catalog, {**operation, 'expected_replacement_safety_element_ids': [10001, 10002]}, target='Line')
    project = project_from(docs, {'Line': 'Line.opentrack'}, catalog)
    route = project.routes[0]
    groups = route.contents[_route_shape(route) + 1].values
    groups[0] = path_functions.array_like(groups[0], [project.model(key) for key in old_route])
    protected_docs = save_project(project)
    with pytest.raises(ValueError, match='release-group and slow-zone anchors'):
        apply(protected_docs, catalog, operation, target='Line')


def test_length_changing_reroute_requires_explicit_margin_mapping(parallel_spans):
    docs, catalog, operation, _, _, _ = parallel_spans
    docs['Line'], _ = set_safety_margins(docs['Line'], 'Service', [
        {'position_m': 500, 'safety_margin_m': 35}, {'position_m': 1700, 'safety_margin_m': 45},
    ])
    with pytest.raises(ValueError, match='explicit map_itinerary_safety_margins'):
        apply(docs, catalog, operation, target='Line')
    _, report = apply(docs, catalog, {**operation, 'map_itinerary_safety_margins': True}, target='Line')
    mapped, = report['mapped_safety_margin_profiles']
    assert mapped['after'] == [{'position_m': 560.0, 'safety_margin_m': 35},
                               {'position_m': 1820.0, 'safety_margin_m': 45}]
