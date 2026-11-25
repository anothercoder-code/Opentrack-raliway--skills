import pytest

from opentrack_ai.current_archive import native_occupation_groups
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, model_id, project_from, transform

from test_saved_geometry import shapes_for
from test_saved_multi_document_reroute import chain


@pytest.fixture
def occupied_platform(chain):
    base, paths, catalog, crossing = chain
    docs = dict(base)
    alternate = next(row['edge_id'] for row in crossing['crossings'][0]['replacement_edges'] if row['document'] == 'B')
    ordinary, _ = transform(docs, paths, catalog, 'B', {'action': 'delete_edge', 'edge_id': alternate})
    docs.update(ordinary)
    before = project_from(docs, paths, catalog)
    berth = before.model(('B', 21))
    station = berth.contents[7].value.contents[12].value
    shapes = shapes_for(docs['B'])
    docs['B'], _ = native_occupation_groups.transform(docs['B'], 'B', [
        {'action': 'create', 'name': 'StationBerth', 'edge_ids': [20, 21], 'selected': True},
    ])
    request = {'action': 'replace_used_platform_edge', 'edge_id': 21, 'station_id': model_id(station),
               'expected_edge_length_m': 500, 'occupation_groups': [{'name': 'StationBerth', 'expected_edge_ids': [20, 21]}],
               'waypoints': [{'distance_from_first_end_m': 130, 'x': 157, 'y': 52},
                             {'distance_from_first_end_m': 350, 'x': 197, 'y': 54}]}
    return docs, paths, catalog, request, shapes


def test_replaces_in_use_platform_chain_preserves_operating_profile_and_monitor(occupied_platform):
    docs, paths, catalog, request, shapes = occupied_platform
    before = project_from(docs, paths, catalog)
    changed, report = transform(docs, paths, catalog, 'B', request, shapes=shapes)
    assert sorted(changed) == ['B']
    assert report['lengths_m'] == [130, 220, 150]
    assert report['signal_and_release_settings_preserved'] and report['station_sign'] == 'B'
    assert any(row['station_sign'] == 'B' and row['stopping_area_length_m'] == 500
               for item in report['verified_stopping_itineraries'] for row in item['visits'])
    after = project_from({**docs, **changed}, paths, catalog)
    assert 21 not in after.byid['B']
    station = after.model(('B', request['station_id']))
    assert all(after.model(('B', item)).contents[12].value is station for item in report['station_member_end_ids_added'])
    monitors = native_occupation_groups.records(after.roots['B'], 'B')
    assert len(monitors) == 1 and monitors[0]['edge_ids'] == [20, *report['replacement_edge_ids']]
    removed = [('B', item) for item in report['station_member_end_ids_added']]
    assert _movement_manifest(before) == _movement_manifest(after, inserted=removed)


def test_replacement_requires_exact_existing_monitor_and_admissible_geometry(occupied_platform):
    docs, paths, catalog, request, shapes = occupied_platform
    for edits, message in (
        ({'occupation_groups': []}, 'Confirm every occupation group'),
        ({'occupation_groups': [{'name': 'StationBerth', 'expected_edge_ids': [21, 20]}]}, 'original order'),
        ({'waypoints': request['waypoints'][::-1]}, 'strictly ordered interior distances'),
        ({'expected_edge_length_m': 499}, 'saved platform track length differs'),
    ):
        with pytest.raises(ValueError, match=message):
            transform(docs, paths, catalog, 'B', {**request, **edits}, shapes=shapes)


def test_replacement_refuses_a_change_in_guarded_berth_length(occupied_platform, chain):
    base, paths, catalog, _ = chain
    _, _, _, request, shapes = occupied_platform
    # This source still has a second inbound approach at the platform entry.
    # The normal planner reports a different clearance after segmentation.
    with pytest.raises(ValueError, match='stop location, available length or stopping track changed'):
        transform(base, paths, catalog, 'B', {**request, 'occupation_groups': []}, shapes=shapes)
