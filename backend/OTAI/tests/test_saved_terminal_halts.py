import pytest

from opentrack_ai.current_archive import path_functions, writer
from opentrack_ai.current_archive.network_operating_plan import _planned_rows, resolve_visit_stop, route_trace
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, model_id, project_from, transform
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_saved_halt_creation import case, clean_platform
from test_saved_geometry import shapes_for


@pytest.fixture
def terminal_platform(case, clean_platform):
    _, _, _, _, ends = case
    docs, paths, dest, ordinary, donor = clean_platform
    project = project_from(docs, paths, dest)
    for name, kind in [('C', 2), ('D', 1)]:
        for half in ends[name]:
            project.model(('RDG', half)).contents[20].value = kind
    bumper = project.model(('RDG', ends['D'][0]))
    operation = {**ordinary, 'action': 'create_terminal_station_halt_signals', 'platform_entry_end_id': ends['B'][0],
                 'station_reference_end_id': ends['C'][0], 'expected_buffer_end_id': ends['D'][0],
                 'expected_buffer_signal_id': model_id(bumper.contents[11].value), 'maximum_train_length_m': 90,
                 'expected_platform_edge_ids': ordinary['expected_platform_edge_ids'][1:],
                 'markers': [{**ordinary['markers'][1], 'expected_position_from_entry_m': 100}]}
    return {'RDG': writer.dump_verified(project.roots['RDG'], project.versions['RDG'])}, paths, dest, operation, donor


@pytest.mark.parametrize(('kind', 'threshold', 'signal_type', 'head'), [('head', None, 6, 100), ('tail', None, 20, 190), ('length', 100, 8, 100)])
def test_markers_at_internal_reference_keep_signalized_buffer(terminal_platform, kind, threshold, signal_type, head):
    docs, paths, dest, request, donor = terminal_platform
    marker = {**request['markers'][0], 'stop_reference': kind, 'maximum_length_for_marker_m': threshold}
    saved, report = transform(docs, paths, dest, 'RDG', {**request, 'markers': [marker]}, shapes=donor)
    original, fresh = (project_from(data, paths, dest) for data in (docs, saved))
    assert _movement_manifest(original) == _movement_manifest(fresh) and report['nonselected_graph_verified']
    buffer = fresh.model(('RDG', request['expected_buffer_end_id']))
    assert model_id(buffer.contents[11].value) == request['expected_buffer_signal_id']
    assert buffer.contents[20].value == 1 and fresh.model(fresh.related(fresh.key(buffer))).contents[9].value is None
    reference = fresh.model(('RDG', request['station_reference_end_id']))
    assert reference.contents[20].value == 2 and reference.contents[11].value.contents[8].values[0] == signal_type
    result, = report['stop_selection_by_train_length']
    assert result['before']['example_head_position_m'] == 200 and result['after']['example_head_position_m'] == head


def test_refuses_bad_buffer_identity_and_distance_past_buffer(terminal_platform):
    docs, paths, dest, request, donor = terminal_platform
    with pytest.raises(ValueError, match='physical buffer'):
        transform(docs, paths, dest, 'RDG', {**request, 'expected_buffer_signal_id': 999}, shapes=donor)
    tail = {**request['markers'][0], 'stop_reference': 'tail', 'maximum_length_for_marker_m': None}
    with pytest.raises(ValueError, match='beyond the existing exit signal'):
        transform(docs, paths, dest, 'RDG', {**request, 'markers': [tail], 'maximum_train_length_m': 101}, shapes=donor)


@pytest.mark.parametrize('signalized', [True, False])
def test_terminal_marker_move_separates_planned_stop_from_physical_buffer(terminal_platform, signalized, monkeypatch):
    docs, paths, dest, scope, donor = terminal_platform
    split_docs, split = transform(docs, paths, dest, 'RDG', {
        'action': 'split_platform_edge', 'edge_id': scope['expected_platform_edge_ids'][-1],
        'station_id': scope['station_id'], 'first_length_m': 40}, shapes=shapes_for(docs['RDG']))
    second = split['new_end_ids'][0]
    scope = {**scope, 'expected_platform_edge_ids': [*scope['expected_platform_edge_ids'], split['new_edge_id']]}
    project = project_from(split_docs, paths, dest)
    route, = project.routes
    nodes = project.route_view(route)
    first = nodes[0]
    origin = path_functions.clone(project.model(first).contents[12].value)
    origin.contents[0].value = max(project.byid['RDG']) + 1
    origin.contents[7].value = native.string('ORIGIN')
    for key in (first, project.related(first)):
        end = project.model(key)
        end.contents[20].value = 2
        end.contents[12].value = origin
    additions = [*project.models['RDG'], origin]
    reference_key = 'RDG', scope['station_reference_end_id']
    buffer_key = 'RDG', scope['expected_buffer_end_id']
    if not signalized:
        for key in (reference_key, project.related(reference_key)):
            project.model(key).contents[20].value = 1
        buffer = project.model(buffer_key)
        additions.remove(buffer.contents[11].value)
        buffer.contents[11].value = None
        scope = {**scope, 'station_reference_end_id': None, 'expected_buffer_signal_id': None}
    writer.set_elements(project.roots['RDG'].contents[2].value, additions)
    material = {'RDG': writer.dump_verified(project.roots['RDG'], project.versions['RDG'])}
    entry = {'visits': [{'station_sign': 'ORIGIN', 'arrival_s': 0, 'departure_s': 0, 'stop': False},
                        {'station_sign': 'P9', 'arrival_s': 90, 'departure_s': 90, 'stop': True}]}

    def inspect(files):
        cold = project_from(files, paths, dest)
        monkeypatch.setattr(cold, 'dest_view', lambda unused: (nodes, []))
        return cold, route_trace(cold, None)

    _, baseline = inspect(material)
    if signalized:
        assert resolve_visit_stop(baseline['visits'][-1], 90)['distance_m'] == 300
    else:
        assert resolve_visit_stop(baseline['visits'][-1], 90) is None
        with pytest.raises(ValueError, match='requires an eligible native halt marker'):
            _planned_rows(entry, baseline, {'length_m': 90}, {'ORIGIN', 'P9'}, 'test', 0, 150)

    marker = {**scope['markers'][0], 'stop_reference': 'head', 'maximum_length_for_marker_m': None}
    marked, created = transform(material, paths, dest, 'RDG', {**scope, 'markers': [marker]}, shapes=donor)
    ident, = created['added_signal_ids']
    move = {key: value for key, value in scope.items() if key not in ('markers', 'maximum_train_length_m', 'donor_signal_id')}
    move.update(action='relocate_terminal_station_halt_signal', from_end_id=marker['end_id'], to_end_id=second,
                signal_id=ident, expected_stop_shift_m=40, expected_halt_signals=created['halt_signals_after'])
    output, moved = transform(marked, paths, dest, 'RDG', move)
    _, before = inspect(marked)
    saved, after = inspect(output)
    assert before['visits'][-1]['distance_m'] == after['visits'][-1]['distance_m'] == (200 if signalized else 300)
    assert before['visits'][-1]['physical_buffer_end'] == after['visits'][-1]['physical_buffer_end'] == buffer_key
    assert resolve_visit_stop(before['visits'][-1], 90)['distance_m'] == 200
    point = resolve_visit_stop(after['visits'][-1], 90)
    assert point['distance_m'] == 240 and point['end_key'] == ('RDG', second)
    assert _planned_rows(entry, after, {'length_m': 90}, {'ORIGIN', 'P9'}, 'test', 0, 150)[-1]['stop_at_station']
    assert moved['signal_id'] == ident and moved['nonselected_graph_verified']
    assert saved.model(('RDG', second)).contents[11].value is saved.model(('RDG', ident))
    with pytest.raises(ValueError, match='interior Ends'):
        transform(marked, paths, dest, 'RDG', {**move, 'to_end_id': buffer_key[1]})
