"""Tests for dependency-aware saved worksheet editing."""

from pathlib import Path

import pytest

from opentrack_ai.current_archive import native_monitoring, writer
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.saved_geometry import inspect_vertex, model_id, project_from, transform
from opentrack_ai.current_archive.saved_geometry_tools import EditGeometry, SavedGeometryTools
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native, topology
from opentrack_ai.errors import APIError

from test_cross_document_route_native_edit import NATIVE_PATHS, fixture
from test_itinerary_native_edit import schematic_document
from test_native_monitoring import worksheets as measurement_worksheets


def apply(documents, catalog, action, target='A', **kwargs):
    paths = {name: f'{name}.opentrack' for name in documents}
    output, report = transform(documents, paths, catalog, target, action, **kwargs)
    return project_from({**documents, **output}, paths, catalog), report


def active_edge(project, document):
    return project.model(project.edge_between((document, 0), (document, 4)))


def shapes_for(blob):
    root, version = writer.load_next_compatible(blob)
    inventory = {writer.kind(obj): obj for obj in writer.objects(root)}
    names = {*topology.CLASS_SHAPES, 'NSMutableArray', 'NSMutableDictionary', 'NSString'}
    return writer.dump_verified(native.arr([inventory[name] for name in sorted(names)]), version)


def test_move_translates_both_signals_with_original_relative_positions():
    docs, catalog = fixture()
    before = project_from(docs, NATIVE_PATHS, catalog)
    after, report = apply(docs, catalog, {'action': 'move_vertex', 'end_id': 0, 'x': 55, 'y': 50})
    assert report['movement_count_checked'] > 0
    for key in (('A', 0), ('A', 1)):
        prior, moved = before.model(key), after.model(key)
        for slot, base, delta in ((2, 55, 25), (3, 50, 20)):
            assert moved.contents[slot].value == base
            assert moved.contents[11].value.contents[slot].value == prior.contents[11].value.contents[slot].value + delta


@pytest.fixture
def measured_vertex(measurement_worksheets):
    docs, catalog = fixture()
    before = project_from(docs, NATIVE_PATHS, catalog)
    edge = before.edge_between(('A', 0), ('A', 4))[1]
    native, receipt = native_monitoring.transform(docs['A'], measurement_worksheets[1], [
        {'action': 'create_instrument', 'end_id': 0, 'name': 'Arrival', 'frame': [120, 85, 80, 42],
         'edge_ids': [edge], 'direction_code': 1, 'display': ['signal_stops', 'course']},
        {'action': 'create_instrument', 'end_id': 1, 'name': 'Departure', 'frame': [140, 65, 100, 42],
         'edge_ids': [edge], 'direction_code': 2, 'visible': False},
    ])
    root, version = writer.load_next_compatible(native)
    _, models = native_monitoring.models(root)
    first_id, second_id = [row['id'] for row in receipt['after']['instruments']]
    first, second = models[first_id], models[second_id]
    first.contents[2].value += 22
    second.contents[9].values = [0.0, 0.0]
    second.contents[10].values = [0.0, 0.0]
    return {**docs, 'A': writer.dump_verified(root, version)}, catalog, [first_id, second_id], edge


def test_measured_vertex_translation_preserves_independent_window_offsets(measured_vertex):
    docs, catalog, ids, edge = measured_vertex
    result, report = apply(docs, catalog, {'action': 'move_vertex', 'end_id': 0, 'x': 55, 'y': 50})
    first, second = report['instruments']
    assert report['instrument_graphics_verified']
    assert [first['after']['id'], second['after']['id']] == ids
    assert first['before']['xy'] == [52, 30] and first['after']['xy'] == [77, 50]
    assert first['after']['frame'] == [145, 105, 80, 42]
    assert second['after']['xy'] == [55, 50] and second['after']['frame'] == [0, 0, 0, 0]
    assert first['after']['edge_ids'] == second['after']['edge_ids'] == [edge]
    before = native_monitoring.records(writer.load_next_compatible(docs['A'])[0])['instruments']
    actual = native_monitoring.records(result.roots['A'])['instruments']
    assert actual == [{**before[0], 'frame': [145, 105, 80, 42]}, before[1]]


def test_measured_vertex_rotation_leaves_independent_instrument_windows_upright(measured_vertex):
    docs, catalog, _, _ = measured_vertex
    original = project_from(docs, NATIVE_PATHS, catalog)
    after, report = apply(docs, catalog, {'action': 'rotate_vertex', 'end_id': 0, 'delta_degrees': 90})
    assert report['instrument_graphics_verified']
    assert len(report['instruments']) == 2 and all(row['before'] == row['after'] for row in report['instruments'])
    assert native_monitoring.records(after.roots['A']) == native_monitoring.records(original.roots['A'])
    assert after.model(('A', 0)).contents[4].value != original.model(('A', 0)).contents[4].value


def test_measured_vertex_edit_needs_exact_reciprocal_local_owner(measured_vertex):
    docs, catalog, ids, _ = measured_vertex
    root, version = writer.load_next_compatible(docs['A'])
    _, models = native_monitoring.models(root)
    models[ids[0]].contents[7].value = models[1]
    source = {**docs, 'A': writer.dump_verified(root, version)}
    with pytest.raises(ValueError, match='unique reciprocal local End'):
        apply(source, catalog, {'action': 'move_vertex', 'end_id': 0, 'x': 55, 'y': 50})


def test_current_vertex_inspector_and_explicit_switch_edit():
    docs, catalog = fixture()
    before = inspect_vertex(docs['A'], 0)
    assert before['pair_checks'] == {'same_position': True, 'same_kilometre_point': True, 'same_name': False}
    after, _ = apply(docs, catalog, {
        'action': 'set_vertex_details', 'end_id': 1, 'both_halves': False,
        'changes': {'name': 'Facing turnout', 'switch_time_s': 2.5, 'default_second_leg': True},
    })
    end = after.model(('A', 1))
    assert end.contents[21].value == 2.5 and end.contents[22].value == 1
    saved = inspect_vertex(writer.dump_verified(after.roots['A'], after.versions['A']), 1)
    assert saved['ends'][0]['name'] == 'Facing turnout'
    with pytest.raises(ValueError, match='two-branch ordinary End'):
        apply(docs, catalog, {'action': 'set_vertex_details', 'end_id': 0, 'both_halves': False,
                              'changes': {'switch_time_s': 2}})


def test_edit_exact_signal_sight_without_changing_other_fields_or_movements():
    docs, catalog = fixture()
    first, other = inspect_vertex(docs['A'], 0)['ends']
    operation = {
        'action': 'set_signal_sight', 'end_id': first['end_id'], 'signal_id': first['signal_id'],
        'expected_sight_m': first['signal_sight_m'], 'sight_m': first['signal_sight_m'] + 200,
    }
    after, report = apply(docs, catalog, operation)
    assert report['movement_count_checked'] > 0 and report['nonselected_graph_verified']
    assert report['before_sight_m'] == first['signal_sight_m']
    saved = writer.dump_verified(after.roots['A'], after.versions['A'])
    assert inspect_vertex(saved, 0)['ends'] == [{**first, 'signal_sight_m': operation['sight_m']}, other]
    signal = after.model(('A', first['signal_id']))
    signal.contents[9].values[1] = first['signal_sight_m']
    root, _ = writer.load_next_compatible(docs['A'])
    assert writer.fingerprint(after.roots['A']) == writer.fingerprint(root)
    with pytest.raises(ValueError, match='exact directional End'):
        apply(docs, catalog, {**operation, 'signal_id': other['signal_id']})
    with pytest.raises(ValueError, match='differs from the reviewed distance'):
        apply(docs, catalog, {**operation, 'expected_sight_m': first['signal_sight_m'] + 1})


def test_chainage_is_shared_across_connected_document_endpoints():
    docs, catalog = fixture()
    action = {
        'action': 'calculate_kilometre_points', 'direction': 'decreasing', 'itinerary': 'I:A-B',
        'end_sequence': None, 'start_km': 50, 'replace_conflicting': False,
    }
    after, report = apply(docs, catalog, action)
    assert report['physical_distance_m'] == 2000
    assert report['changed_documents'] == ['A', 'B']
    model = after.model
    assert all(model(key).contents[14].value == 50 for key in (('A', 0), ('A', 1)))
    assert all(model(key).contents[14].value == 49 for key in (('A', 4), ('A', 5), ('B', 0), ('B', 1)))
    assert all(model(key).contents[14].value == 48 for key in (('B', 4), ('B', 5)))
    updated = {name: writer.dump_verified(after.roots[name], after.versions[name]) for name in docs}
    with pytest.raises(ValueError, match='conflicts'):
        apply(updated, catalog, {**action, 'start_km': 60})


def test_reverse_keeps_physical_directional_speed_and_gradient():
    docs, catalog = fixture()
    project = project_from(docs, NATIVE_PATHS, catalog)
    edge = active_edge(project, 'A')
    edge.contents[9].values[3] = 5.5
    edge.contents[11].value = 0
    speed = edge.contents[16].value.contents[2].value
    speed.contents[1].value = 40
    speed.contents[2].value = 70
    docs['A'] = writer.dump_verified(project.roots['A'], project.versions['A'])
    after, report = apply(docs, catalog, {'action': 'reverse_edge', 'edge_id': model_id(edge)})
    assert report['before_end_ids'] == [1, 4]
    assert report['after_end_ids'] == [4, 1]
    assert report['after_gradient_per_mille'] == -5.5
    changed = active_edge(after, 'A')
    assert changed.contents[16].value.contents[2].value.contents[1].value == 70
    assert changed.contents[16].value.contents[2].value.contents[2].value == 40


def test_split_updates_route_continuation_and_preserves_length_and_safety():
    docs, catalog = fixture()
    before = project_from(docs, NATIVE_PATHS, catalog)
    edge = active_edge(before, 'A')
    action = {'action': 'split_edge', 'edge_id': model_id(edge), 'first_length_m': 220}
    after, report = apply(docs, catalog, action, shapes=shapes_for(docs['A']))
    inserted_left, inserted_right = report['new_end_ids']
    assert report['lengths_m'] == [220, 780]
    assert after.route_view(after.owned(('A', 0), 'OTRoute', ('R:A-B', 0, 0))) == [
        ('A', 0), ('A', inserted_left), ('A', 4), ('B', 4),
    ]
    assert after.route_view(after.owned(('A', 5), 'OTRoute', ('R:B-A', 0, 5))) == [
        ('A', inserted_right), ('A', 1),
    ]
    ends = [after.model(('A', ident)) for ident in (inserted_left, inserted_right)]
    assert {model_id(end.contents[7].value) for end in ends} == {report['safety_element_id']}
    with pytest.raises(ValueError, match='positive physical length'):
        apply(docs, catalog, {**action, 'first_length_m': 1000}, shapes=shapes_for(docs['A']))


def connector_pair(a, b):
    return {'a': {'document': a[0], 'end_id': a[1]}, 'b': {'document': b[0], 'end_id': b[1]}}


def test_unused_external_connector_can_be_reassigned_and_active_route_is_guarded():
    docs, catalog = fixture()
    docs['C'], _ = schematic_document(generate.spec(), [('right', 0), ('right', 1)])
    after, report = apply(docs, catalog, {
        'action': 'replace_connectors', 'unlink': [connector_pair(('A', 9), ('B', 8))],
        'link': [connector_pair(('A', 9), ('C', 0))],
    })
    assert report['changed_documents'] == ['A', 'B', 'C']
    assert after.block_end(('A', 9)) == ('C', 0)
    assert after.block_end(('C', 0)) == ('A', 9)
    assert writer.kind(after.model(('B', 8))) == 'OTEndModel'
    with pytest.raises(ValueError, match='owns saved movement'):
        apply(docs, catalog, {'action': 'replace_connectors',
                             'unlink': [connector_pair(('A', 5), ('B', 0))], 'link': []})


def test_merge_and_reset_preserve_track_but_change_exclusive_groups():
    docs, catalog = fixture()
    before = project_from(docs, NATIVE_PATHS, catalog)
    occupied = before.model(('A', 1)).contents[7].value
    idle = before.model(('A', 0)).contents[7].value
    after, report = apply(docs, catalog, {'action': 'merge_safety_elements',
                          'element_ids': [model_id(occupied), model_id(idle)]})
    assert report['safety_regrouped']
    assert after.model(('A', 0)).contents[7].value is after.model(('A', 1)).contents[7].value
    regrouped = writer.dump_verified(after.roots['A'], after.versions['A'])
    reset, report = apply({**docs, 'A': regrouped}, catalog,
                          {'action': 'reset_safety_element', 'element_id': model_id(occupied)})
    assert report['new_element_ids']
    assert reset.model(('A', 0)).contents[7].value is not reset.model(('A', 1)).contents[7].value


def test_saved_bundle_preserves_source_and_refuses_overwrite(tmp_path):
    docs, catalog = fixture()
    root = Path(tmp_path)
    project = root / 'OTProjects' / 'Line'
    workspace = root / 'OTAI' / 'workspaces' / 'Edit'
    project.mkdir(parents=True)
    workspace.mkdir(parents=True)

    def save(path, data):
        path.write_bytes(data)
        return {'path': path.relative_to(root).as_posix(), 'sha256': sha(data)}

    args = EditGeometry(
        project_run=save(project / 'chain.run',
            b'Infrastructure Document#A.opentrack#\nInfrastructure Document#B.opentrack#\nDestInfoFile#line.dest#\n'),
        documents={name: save(project / file, docs[name]) for name, file in NATIVE_PATHS.items()},
        dest_catalog=save(project / 'line.dest', catalog), target_document='A',
        operation={'action': 'move_vertex', 'end_id': 0, 'x': 55, 'y': 50},
        preview_only=False, target_directory=(workspace / 'Candidate').relative_to(root).as_posix(),
    )
    tools = SavedGeometryTools(root)
    result = tools.edit(args)
    assert result['saved'] and result['atomic_directory_commit']
    filename = workspace / 'Candidate' / 'A.opentrack'
    assert sha(filename.read_bytes()) == result['manifest']['files'][filename.name]['sha256']
    assert (project / 'A.opentrack').read_bytes() == docs['A']
    with pytest.raises(APIError) as retry:
        tools.edit(args)
    assert retry.value.code == 'TARGET_EXISTS'
