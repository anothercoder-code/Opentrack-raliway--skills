import pytest

from opentrack_ai.current_archive import native_occupation_groups
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, model_id, project_from, transform
from opentrack_ai.current_archive.saved_multi_document_reroute import _turnout_state

from test_saved_geometry import shapes_for
from test_saved_multi_document_reroute import chain
from test_saved_platform_replacement import occupied_platform


def selection(edge_id, x, length, scope='platform'):
    return {'edge_id': edge_id, 'expected_edge_length_m': length, 'station_scope': scope,
            'waypoints': [{'distance_from_first_end_m': length // 2, 'x': x, 'y': 52}]}


@pytest.fixture
def station_tracks(occupied_platform, chain):
    docs, paths, catalog, single, shapes = occupied_platform
    docs = dict(docs)
    alternate = next(row['edge_id'] for row in chain[3]['crossings'][1]['replacement_edges'] if row['document'] == 'B')
    ordinary, _ = transform(docs, paths, catalog, 'B', {'action': 'delete_edge', 'edge_id': alternate})
    docs.update(ordinary)
    before = project_from(docs, paths, catalog)
    docs['B'], _ = native_occupation_groups.transform(docs['B'], 'B', [
        {'action': 'create', 'name': 'JoinedTracks', 'edge_ids': [22, 21], 'selected': True},
    ])
    approach, departure = [selection(edge, x, before.model(('B', edge)).contents[9].values[1])
                           for edge, x in ((21, 160), (22, 320))]
    operation = {'action': 'replace_used_station_track_set', 'station_id': single['station_id'],
                 'edges': [approach, departure], 'occupation_groups': [*single['occupation_groups'],
                         {'name': 'JoinedTracks', 'expected_edge_ids': [22, 21]}]}
    return docs, paths, catalog, operation, shapes


def test_replaces_joined_station_tracks_once_and_updates_shared_monitors_in_order(station_tracks):
    docs, paths, catalog, operation, shapes = station_tracks
    changed, report = transform(docs, paths, catalog, 'B', operation, shapes=shapes)
    assert set(changed) == {'B'} and report['signal_and_release_settings_preserved']
    before = project_from(docs, paths, catalog)
    after = project_from({**docs, **changed}, paths, catalog)
    assert {21, 22}.isdisjoint(after.byid['B'])
    first, second = [row['replacement_edge_ids'] for row in report['tracks']]
    assert len(set(first + second)) == 4
    records = {row['name']: row for row in native_occupation_groups.records(after.roots['B'], 'B')}
    assert records['StationBerth']['edge_ids'] == [20, *first]
    assert records['JoinedTracks']['edge_ids'] == [*second, *first]
    inserted = [('B', end_id) for end_id in report['station_member_end_ids_added']]
    assert len(inserted) == 4
    assert _movement_manifest(before) == _movement_manifest(after, inserted=inserted)


def test_station_track_set_refuses_unreviewed_membership_coordinates_and_monitors(station_tracks):
    docs, paths, catalog, operation, shapes = station_tracks
    original = dict(docs)
    first, second = operation['edges']
    for changes, message in (
        ({'edges': [first, first]}, 'distinct station Edges'),
        ({'edges': [first, {**second, 'station_scope': 'boundary_approach'}]}, 'station boundary approach'),
        ({'edges': [first, {**second, 'waypoints': [dict(first['waypoints'][0])]}]}, 'coincides'),
        ({'occupation_groups': operation['occupation_groups'][:1]}, 'Confirm every occupation group'),
    ):
        with pytest.raises(ValueError, match=message):
            transform(docs, paths, catalog, 'B', {**operation, **changes}, shapes=shapes)
        assert docs == original


def test_station_track_set_refuses_changed_reverse_berth_with_retained_departure_branch(station_tracks, occupied_platform):
    _, paths, catalog, operation, shapes = station_tracks
    docs, *_ = occupied_platform
    # The fixture's alternate B–C connector is unused, but its branch changes the
    # effective unbranched reverse berth when its approach length is segmented.
    with pytest.raises(ValueError, match='stop location, available length or stopping track changed'):
        transform(docs, paths, catalog, 'B', {**operation, 'occupation_groups': operation['occupation_groups'][:1]},
                  shapes=shapes)


@pytest.fixture
def junction_core(chain):
    base, paths, catalog, _ = chain
    docs = dict(base)
    shapes = shapes_for(docs['B'])

    def edit(operation):
        changes, report = transform(docs, paths, catalog, 'B', operation, shapes=shapes)
        docs.update(changes)
        return report

    edge = 23
    inside = []
    for _ in range(3):
        split = edit({'action': 'split_edge', 'edge_id': edge, 'first_length_m': 100})
        edge = split['new_edge_id']
        inside.append(edge)
    first, second = inside[:2]
    project = project_from(docs, paths, catalog)
    turnout = model_id(project.model(('B', second)).contents[7].value)
    terminal, _ = edit({'action': 'insert_vertex', 'x': 390, 'y': 56, 'orientation': 'horizontal',
                        'names': ['', '']})['added_vertex_end_ids']
    retained = edit({'action': 'insert_edge', 'end_ids': [turnout, terminal], 'length_m': 105,
                     'radius_m': 0, 'gradient_per_mille': 0, 'rack_rail': False, 'remark': '', 'track_name': 'Branch',
                     'line_name': 'chain', 'allow_safety_regroup': False,
                     'speeds': [{'train_type': '0', 'speed12_kmh': 75, 'speed21_kmh': 75}]})['edge_id']
    docs['B'], _ = native_occupation_groups.transform(docs['B'], 'B', [
        {'action': 'create', 'name': 'Core', 'edge_ids': [retained, first, second], 'selected': True},
    ])
    project = project_from(docs, paths, catalog)
    selected = []
    for edge_id, x in ((first, 360), (second, 380)):
        edge = project.model(('B', edge_id))
        ends = [edge.contents[slot].value for slot in (7, 8)]
        selected.append({**selection(edge_id, x, 100, 'junction_core'), 'expected_end_ids': list(map(model_id, ends)),
                         'expected_safety_element_id': model_id(ends[0].contents[7].value)})
    station = model_id(project.model(('B', 8)).contents[12].value)
    operation = {'action': 'replace_used_station_track_set', 'station_id': station,
                 'edges': selected, 'occupation_groups': [{'name': 'Core', 'expected_edge_ids': [retained, first, second]}],
                 'junction_turnout_reviews': [{'end_id': turnout, 'expected_edge_ids': [second, retained],
                                              'expected_default_edge_id': second, 'expected_switch_time_s': 0}]}
    return docs, paths, catalog, shapes, operation


def test_junction_core_retires_shared_rails_and_preserves_ordered_turnout_and_occupation(junction_core):
    docs, paths, catalog, shapes, operation = junction_core
    changes, report = transform(docs, paths, catalog, 'B', operation, shapes=shapes)
    assert set(changes) == {'B'}
    old, current = (project_from(mapping, paths, catalog) for mapping in (docs, {**docs, **changes}))
    core = report['junction_core']
    old_edges = [row['edge_id'] for row in operation['edges']]
    assert core['edge_ids'] == old_edges
    assert {row['itinerary'] for row in core['station_witnesses']} >= {'I:chain:forward', 'I:chain:reverse'}
    assert len(core['ungrouped_end_ids_added']) == 4 and not report['station_member_end_ids_added']
    assert not report['ungrouped_boundary_approach_end_ids_added']
    for end_id in core['ungrouped_end_ids_added']:
        assert current.model(('B', end_id)).contents[12].value is None
    inserted = [('B', end_id) for end_id in core['ungrouped_end_ids_added']]
    assert _movement_manifest(old) == _movement_manifest(current, inserted=inserted)
    safety, = core['safety_elements']
    assert set(safety['after_end_ids']) - set(safety['before_end_ids']) == set(core['ungrouped_end_ids_added'])
    first, second = [row['replacement_edge_ids'] for row in report['tracks']]
    review, = operation['junction_turnout_reviews']
    turnout = _turnout_state(current, ('B', review['end_id']))
    retained = review['expected_edge_ids'][1]
    assert turnout == {'edge_ids': [second[0], retained], 'default_edge_id': second[0], 'switch_time_s': 0.0}
    monitored, = native_occupation_groups.records(current.roots['B'], 'B')
    assert monitored['edge_ids'] == [retained, *first, *second] and monitored['selected']


def test_junction_core_rejects_direction_safety_turnout_and_occupation_mismatch(junction_core):
    docs, paths, catalog, shapes, operation = junction_core
    first, second = operation['edges']
    turnout, = operation['junction_turnout_reviews']
    for changed, message in (
        ({'edges': [{**first, 'expected_end_ids': first['expected_end_ids'][::-1]}, second]}, 'directional Ends'),
        ({'edges': [{**first, 'expected_safety_element_id': 999}, second]}, 'Safety Element membership'),
        ({'junction_turnout_reviews': []}, 'Review every junction core turnout'),
        ({'junction_turnout_reviews': [{**turnout, 'expected_edge_ids': turnout['expected_edge_ids'][::-1]}]}, 'legs, default or switch time'),
        ({'occupation_groups': []}, 'Confirm every occupation group'),
    ):
        with pytest.raises(ValueError, match=message):
            transform(docs, paths, catalog, 'B', {**operation, **changed}, shapes=shapes)
