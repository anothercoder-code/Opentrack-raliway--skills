"""Exercise new saved topology operations on an existing two-document project."""

import pytest

from opentrack_ai.current_archive.saved_geometry import model_id, project_from
from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_cross_document_route_native_edit import NATIVE_PATHS, fixture
from test_itinerary_native_edit import fixture as line_fixture
from test_saved_geometry import active_edge, apply, shapes_for


def save_project(project):
    return {name: writer.dump_verified(root, project.versions[name]) for name, root in project.roots.items()}


def test_rotate_both_ends_and_signal_offsets_with_native_quarter_turn():
    docs, catalog = fixture()
    source = project_from(docs, NATIVE_PATHS, catalog)
    after, report = apply(docs, catalog, {'action': 'rotate_vertex', 'end_id': 0, 'delta_degrees': 90})
    assert len(report['objects']) == 4
    assert report['pivot_xy'] == [30, 30]
    for ident, alignment in ((0, (0, 3)), (1, (0, 4))):
        old, new = [project.model(('A', ident)) for project in (source, after)]
        assert tuple(new.contents[i].value for i in (4, 5)) == alignment
        signal = new.contents[11].value
        assert tuple(signal.contents[i].value for i in (4, 5)) == alignment
        old_signal = old.contents[11].value
        assert signal.contents[2].value == 60 - old_signal.contents[3].value
        assert signal.contents[3].value == old_signal.contents[2].value
        assert signal.contents[1].value == old_signal.contents[1].value


def test_cut_double_vertex_separates_its_legs_and_preserves_terminal_movement():
    docs, catalog, paths, _ = line_fixture('Line.opentrack')
    source = project_from(docs, paths, catalog)
    route = source.routes[1]
    original_movement = source.route_view(route)
    terminal = original_movement[-1]
    back = source.related(terminal)
    old_end = source.model(terminal)
    old_signal = old_end.contents[11].value
    operation = {'action': 'cut_double_vertex', 'end_id': back[1], 'second_x': 221, 'second_y': 59}
    after, report = apply(docs, catalog, operation, target='Line', shapes=shapes_for(docs['Line']))
    assert report['former_end_ids'] == [back[1], terminal[1]]
    assert report['no_connecting_edge_created'] and report['movement_count_checked'] > 1
    assert all(len(item['edge_ids']) == 1 for item in report['preserved_attachments'])
    assert after.route_view(after.routes[1]) == original_movement
    for old_id, new_id in report['separated_pairs']:
        assert after.related(('Line', old_id)) == ('Line', new_id)
        cap = after.model(('Line', new_id))
        assert all(cap.contents[slot].value is None for slot in (9, 10, 11))
    new_end = after.model(terminal)
    signal = new_end.contents[11].value
    assert model_id(signal) == model_id(old_signal)
    assert all(signal.contents[i].value - new_end.contents[i].value
               == old_signal.contents[i].value - old_end.contents[i].value for i in (2, 3))


def test_cut_refuses_a_used_through_vertex_or_an_occupied_position():
    docs, catalog, paths, _ = line_fixture('Line.opentrack')
    project = project_from(docs, paths, catalog)
    through, terminal = project.route_view(project.routes[1])
    shapes = shapes_for(docs['Line'])
    operation = {'action': 'cut_double_vertex', 'end_id': through[1], 'second_x': 221, 'second_y': 59}
    with pytest.raises(ValueError, match='saved movement depends on passage'):
        apply(docs, catalog, operation, target='Line', shapes=shapes)
    old_end = project.model(terminal)
    with pytest.raises(ValueError, match='unoccupied position'):
        apply(docs, catalog, {**operation, 'end_id': terminal[1], 'second_x': float(old_end.contents[2].value),
                              'second_y': float(old_end.contents[3].value)}, target='Line', shapes=shapes)


def test_insert_rechain_delete_unused_track_and_vertex_preserve_active_route():
    docs, catalog = fixture()
    shapes = shapes_for(docs['A'])
    project, added = apply(docs, catalog, {
        'action': 'insert_vertex', 'x': 140, 'y': 99, 'orientation': 'horizontal', 'names': ['NewL', 'NewR'],
    }, shapes=shapes)
    new_left, new_right = added['added_vertex_end_ids']
    alternate = project.model(('A', 1)).contents[10].value
    active = active_edge(project, 'A')
    main_identity = model_id(active)
    edge_identity = model_id(alternate)
    source = save_project(project)
    with pytest.raises(ValueError, match='used by saved movement'):
        apply(source, catalog, {'action': 'delete_edge', 'edge_id': main_identity})

    after, _ = apply(source, catalog, {'action': 'rechain_edge', 'edge_id': edge_identity,
                                      'end_ids': [1, new_left], 'allow_safety_regroup': False})
    assert after.model(('A', edge_identity)).contents[8].value is after.model(('A', new_left))
    assert after.model(('A', 8)).contents[9].value is None
    assert model_id(active_edge(after, 'A')) == main_identity

    after, report = apply(save_project(after), catalog, {'action': 'delete_edge', 'edge_id': edge_identity})
    assert report['previous_safety_groups_kept']
    assert after.model(('A', 1)).contents[10].value is None
    assert edge_identity not in after.byid['A']

    after, report = apply(save_project(after), catalog, {
        'action': 'insert_edge', 'end_ids': [1, new_left], 'length_m': 75, 'radius_m': 0,
        'gradient_per_mille': 3, 'rack_rail': False, 'remark': '', 'track_name': 'Spare', 'line_name': 'Line',
        'speeds': [{'train_type': '0', 'speed12_kmh': 50, 'speed21_kmh': 40}], 'allow_safety_regroup': False,
    }, shapes=shapes)
    new_edge = report['edge_id']
    assert after.model(('A', new_edge)).contents[9].values[1] == 75
    with pytest.raises(ValueError, match='still has track'):
        apply(save_project(after), catalog, {'action': 'delete_vertex', 'end_id': new_right})
    after, _ = apply(save_project(after), catalog, {'action': 'delete_edge', 'edge_id': new_edge})
    after, report = apply(save_project(after), catalog, {'action': 'delete_vertex', 'end_id': new_left})
    assert report['removed_end_ids'] == [new_left, new_right]
    assert new_left not in after.byid['A'] and new_right not in after.byid['A']
    assert model_id(active_edge(after, 'A')) == main_identity


def test_import_and_move_native_bitmap_payload_is_unchanged():
    docs, catalog = fixture()
    root, version = writer.load_next_compatible(docs['A'])
    bitmap_payload = b'Test raster payload'
    bitmap = native.obj([('NSBitmapImageRep', 17), ('NSImageRep', 17), ('NSObject', 0)],
                        [('i', [len(bitmap_payload)]),
                         (f'[{len(bitmap_payload)}c]', [writer.Array(bitmap_payload)])])
    logo = native.obj([('OTLogoModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], [
        ('i', [100000]), ('f', [0.0]), ('f', [35.0]), ('f', [20.0]), ('i', [0]), ('i', [0]), ('@', [None]),
        ('@', [bitmap]), ('ff', [30.0, 10.0]), ('ffff', [20.0, 15.0, 30.0, 10.0]), ('i', [1]),
    ])
    array = root.contents[2].value
    writer.set_elements(array, [*writer.elements(array), logo])
    donor = writer.dump_verified(root, version)
    inserted, report = apply(docs, catalog, {
        'action': 'import_decoration', 'graphic_id': 100000, 'delta_x': 10, 'delta_y': 15, 'text': None,
    }, drawing_donor=donor)
    selected = report['graphic_id']
    moved, _ = apply(save_project(inserted), catalog, {
        'action': 'edit_decoration', 'graphic_id': selected, 'delta_x': 5, 'delta_y': -5, 'text': None,
    })
    obj = moved.model(('A', selected))
    assert [obj.contents[2].value, obj.contents[3].value] == [50, 30]
    assert obj.contents[9].values == [35, 25, 30, 10]
    assert obj.contents[7].value.contents[1].value.elements == bitmap_payload


def test_native_drawing_edit_keeps_flip_and_updates_outline_size_and_fill():
    docs, catalog = fixture()
    root, version = writer.load_next_compatible(docs['A'])
    rect_id = 100000
    rect = native.obj([('OTRectModel', 0), ('OTResizeModel', 0), ('OTGraphicModel', 1), ('NSObject', 0)], [
        ('i', [rect_id]), ('f', [0.0]), ('f', [35.0]), ('f', [20.0]), ('i', [0]), ('i', [0]), ('@', [None]),
        ('if', [1, 0.5]), ('ff', [33.0, 17.0]), ('ff', [55.0, 25.0]), ('@', [None]), ('@', [None]),
    ])
    array = root.contents[2].value
    writer.set_elements(array, [*writer.elements(array), rect])
    docs['A'] = writer.dump_verified(root, version)
    project, result = apply(docs, catalog, {
        'action': 'edit_decoration', 'graphic_id': rect_id, 'delta_x': 5, 'delta_y': -5, 'text': None,
        'drawing_style': {'width_points': 60, 'height_points': 15, 'line_width_points': 2.5,
                          'filled': True, 'fill_rgb': [213, 220, 236], 'line_rgb': [21, 34, 82]},
    })
    edited = project.model(('A', rect_id))
    assert edited.contents[7].values == [3, 2.5]
    assert edited.contents[8].values == [38, 12]
    assert edited.contents[9].values == [65, 20]
    assert result['drawing_style_after']['fill_color'] == {'rgb': [213, 220, 236], 'alpha': 1.0}
    assert result['drawing_style_after']['line_color'] == {'rgb': [21, 34, 82], 'alpha': 1.0}
    assert result['destination_catalog_unchanged']
    updated, result = apply(save_project(project), catalog, {
        'action': 'edit_decoration', 'graphic_id': rect_id, 'delta_x': 0, 'delta_y': 0, 'text': None,
        'drawing_style': {'filled': False},
    })
    assert not result['drawing_style_after']['filled']
    assert updated.model(('A', rect_id)).contents[7].values == [1, 2.5]
