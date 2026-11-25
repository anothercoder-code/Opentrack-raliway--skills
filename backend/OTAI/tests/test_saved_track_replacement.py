import pytest

from opentrack_ai.current_archive import path_functions, writer
from opentrack_ai.current_archive.current_shunting_workflow import core as shunting
from opentrack_ai.current_archive.route_edit_tools import _protection_values, _route_shape
from opentrack_ai.current_archive.saved_geometry import _speed_table, model_id, project_from

from test_itinerary_native_edit import fixture as line_fixture
from test_saved_geometry import apply, shapes_for
from test_saved_track_topology import save_project


@pytest.fixture
def alternative():
    docs, catalog, paths, _ = line_fixture('Line.opentrack')
    project = project_from(docs, paths, catalog)
    movement = project.route_view(project.routes[0])
    source_edge = project.model(project.edge_between(*movement))
    edge_id = model_id(source_edge)
    end_ids = [model_id(source_edge.contents[i].value) for i in (7, 8)]
    total = source_edge.contents[9].values[1]
    shape = shapes_for(docs['Line'])
    docs['Line'], _ = shunting.create(docs['Line'], {
        'name': 'S:Shared', 'description': 'same track used by regular route and shunting',
        'end_ids': [key[1] for key in movement], 'speed_kmh': 40.0,
        'release_time_s': 3, 'reservation_time_s': 2,
    })
    staged, added = apply(docs, catalog, {'action': 'insert_vertex', 'x': 60, 'y': 78,
                                         'orientation': 'horizontal', 'names': ['', '']},
                          target='Line', shapes=shape)
    left, right = added['added_vertex_end_ids']
    edge_spec = {
        'action': 'insert_edge', 'radius_m': float(source_edge.contents[9].values[2]),
        'gradient_per_mille': float(source_edge.contents[9].values[3]),
        'rack_rail': bool(source_edge.contents[11].value & 2), 'allow_safety_regroup': False,
        'remark': '', 'track_name': path_functions.string(source_edge.contents[19].value),
        'line_name': path_functions.string(source_edge.contents[20].value),
        'speeds': [{'train_type': name, 'speed12_kmh': row.contents[1].value,
                    'speed21_kmh': row.contents[2].value} for name, row in _speed_table(source_edge).items()],
    }
    first_length = total // 3
    staged, first = apply(save_project(staged), catalog,
                          {**edge_spec, 'end_ids': [end_ids[0], left], 'length_m': first_length},
                          target='Line', shapes=shape)
    # Start the second insertion with its existing safety group so both
    # replacement Edges remain in the original exclusive section.
    reverse_speed = [{**row, 'speed12_kmh': row['speed21_kmh'], 'speed21_kmh': row['speed12_kmh']}
                     for row in edge_spec['speeds']]
    staged, second = apply(save_project(staged), catalog, {
        **edge_spec, 'end_ids': [end_ids[1], right], 'length_m': total - first_length,
        'gradient_per_mille': -edge_spec['gradient_per_mille'], 'speeds': reverse_speed,
    }, target='Line', shapes=shape)
    return save_project(staged), catalog, edge_id, [first['edge_id'], second['edge_id']], left


def test_retire_operational_edge_rebinds_route_path_itinerary_and_shunting(alternative):
    docs, catalog, edge_id, replacement, via = alternative
    old = project_from(docs, {'Line': 'Line.opentrack'}, catalog)
    after, report = apply(docs, catalog, {
        'action': 'replace_used_edge', 'edge_id': edge_id, 'replacement_edge_ids': replacement,
    }, target='Line')
    assert report['retired_edge_id'] == edge_id and edge_id not in after.byid['Line']
    assert report['signal_and_release_settings_preserved']
    assert report['destination_catalog_unchanged']
    assert {entry['kind'] for entry in report['affected_movement_identities']} == {
        'route', 'shunting', 'path', 'itinerary',
    }
    assert report['replacement_via_end_ids'] == [via]
    assert set(after.owners.values()) == set(old.owners.values())
    assert _protection_values(after.routes[0], _route_shape(after.routes[0])) == _protection_values(
        old.routes[0], _route_shape(old.routes[0]))
    assert after.route_view(after.routes[0])[1] == ('Line', via)
    assert next(iter(after.shunting_movements.values()))[1] == ('Line', via)


def test_replacement_wrong_order_or_unequal_physics_preserves_source(alternative):
    docs, catalog, edge_id, replacement, _ = alternative
    operation = {'action': 'replace_used_edge', 'edge_id': edge_id, 'replacement_edge_ids': replacement}
    with pytest.raises(ValueError, match='wrong order'):
        apply(docs, catalog, {**operation, 'replacement_edge_ids': replacement[::-1]}, target='Line')
    source = project_from(docs, {'Line': 'Line.opentrack'}, catalog)
    source.model(('Line', replacement[0])).contents[9].values[1] += 1
    changed_docs = save_project(source)
    unchanged = changed_docs.copy()
    with pytest.raises(ValueError, match='distance, directional physics'):
        apply(changed_docs, catalog, operation, target='Line')
    assert changed_docs == unchanged
    assert writer.kind(source.model(('Line', edge_id))) == 'OTEdgeModel'
