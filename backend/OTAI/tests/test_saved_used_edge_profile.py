import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.itinerary_edit_tools import _margin_members, set_safety_margins
from opentrack_ai.current_archive.saved_geometry import _speed_table, model_id, project_from

from test_cross_document_route_native_edit import NATIVE_PATHS, fixture
from test_itinerary_native_edit import fixture as line_fixture
from test_saved_geometry import apply
from test_saved_track_topology import save_project


def with_rows(blob, name, positions):
    return set_safety_margins(blob, name, [
        {'position_m': point, 'safety_margin_m': 30 + i} for i, point in enumerate(positions)
    ])[0]


def test_length_updates_cross_document_itinerary_margins_and_both_directions():
    docs, catalog = fixture()
    docs['A'] = with_rows(docs['A'], 'I:A-B', [250, 1000, 1500, 2000])
    old = project_from(docs, NATIVE_PATHS, catalog)
    edge_id = old.edge_between(('A', 4), ('B', 4))[1]
    operation = {'action': 'edit_used_edge_profile', 'edge_id': edge_id, 'length_m': 1120,
                 'gradient_per_mille': 7.5, 'speeds': [{'train_type': '0', 'speed12_kmh': 45, 'speed21_kmh': 65}]}
    with pytest.raises(ValueError, match='explicit map_itinerary_safety_margins'):
        apply(docs, catalog, operation, target='B')
    after, report = apply(docs, catalog, {**operation, 'map_itinerary_safety_margins': True}, target='B')
    assert report['changed_documents'] == ['A', 'B']
    assert report['before']['length_m'] == 1000 and report['after']['length_m'] == 1120
    assert report['after']['gradient_per_mille'] == 7.5
    assert report['before']['storage_end_ids'] == report['after']['storage_end_ids']
    assert not report['after']['equal_directional_speed_flag']
    assert report['after']['speeds_kmh']['0'] == [45, 65]
    assert report['signal_and_release_settings_preserved'] and report['destination_catalog_unchanged']
    assert {r['kind'] for r in report['movements']} == {'route', 'path', 'itinerary'}
    assert all(r['after_distance_m'] - r['before_distance_m'] == 120 for r in report['movements'])
    mapped, = report['mapped_safety_margin_profiles']
    assert [(r['position_m'], r['safety_margin_m']) for r in mapped['after']] == [
        (250, 30), (1000, 31), (1560, 32), (2120, 33),
    ]
    assert after.dest_view(after.dests[0]) == old.dest_view(old.dests[0])


def test_speed_edit_detaches_shared_table_and_leaves_distance_margins_unchanged():
    docs, catalog, paths, _ = line_fixture('Line.opentrack')
    docs['Line'] = with_rows(docs['Line'], 'Service', [300, 1600])
    project = project_from(docs, paths, catalog)
    old_route = project.route_view(project.routes[0])
    edge, neighbour = (project.model(project.edge_between(*project.route_view(route))) for route in project.routes)
    original_speeds = [record.contents[i].value for record in _speed_table(neighbour).values() for i in (1, 2)]
    neighbour.contents[16].value = edge.contents[16].value
    after, report = apply(save_project(project), catalog, {
        'action': 'edit_used_edge_profile', 'edge_id': model_id(edge),
        'speeds': [{'train_type': '0', 'speed12_kmh': 30, 'speed21_kmh': 35}],
    }, target='Line')
    updated = after.model(('Line', model_id(edge)))
    untouched = after.model(('Line', model_id(neighbour)))
    assert [record.contents[i].value for record in _speed_table(untouched).values()
            for i in (1, 2)] == original_speeds
    assert updated.contents[16].value is not untouched.contents[16].value
    assert after.route_view(after.routes[0]) == old_route
    assert all(r['before_distance_m'] == r['after_distance_m'] for r in report['movements'])
    assert report['mapped_safety_margin_profiles'] == []


def test_explicit_length_mapping_rejects_shared_margin_rows():
    docs, catalog, paths, _ = line_fixture('Line.opentrack')
    docs['Line'] = with_rows(docs['Line'], 'Service', [700])
    project = project_from(docs, paths, catalog)
    _, margins, (shared,) = _margin_members(project.dests[0])
    writer.set_elements(margins, [shared, shared])
    edge_id = project.edge_between(*project.route_view(project.routes[0]))[1]
    with pytest.raises(ValueError, match='shares safety-margin objects'):
        apply(save_project(project), catalog, {'action': 'edit_used_edge_profile', 'edge_id': edge_id,
              'length_m': 1450, 'map_itinerary_safety_margins': True}, target='Line')
