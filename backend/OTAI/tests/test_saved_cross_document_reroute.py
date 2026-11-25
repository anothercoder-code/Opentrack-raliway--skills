import pytest

from opentrack_ai.current_archive import native_monitoring, native_occupation_groups, path_functions, route_factory, writer
from opentrack_ai.current_archive.current_shunting_workflow import core as shunting
from opentrack_ai.current_archive.infrastructure_incidents import core as incidents
from opentrack_ai.current_archive.itinerary_edit_tools import set_safety_margins
from opentrack_ai.current_archive.route_edit_tools import _protection_values, _route_shape
from opentrack_ai.current_archive.saved_edge_exclusion import _links
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, model_id, position, project_from
from opentrack_ai.current_archive.saved_geometry_tools import RerouteCrossDocumentTrackSpan, SavedGeometryTools
from opentrack_ai.current_archive.saved_junction_reroute import _commit_continuations
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_cross_document_route_native_edit import NATIVE_PATHS, fixture
from test_itinerary_lifecycle import course_archive
from test_native_monitoring import worksheets
from test_saved_geometry import apply, shapes_for
from test_saved_track_topology import save_project


FORWARD = ('R:A-B', 0, 0)
REVERSE = ('R:B-A', 0, 5)


def end_ref(doc, end_id):
    return {'document': doc, 'end_id': end_id}


@pytest.fixture
def crossing():
    docs, catalog = fixture()
    project = project_from(docs, NATIVE_PATHS, catalog)
    old = [project.edge_between(a, b) for a, b in [(('A', 0), ('A', 4)), (('A', 4), ('B', 4))]]
    new = [project.edge_between(a, b) for a, b in [(('A', 0), ('A', 8)), (('A', 8), ('B', 4))]]
    operation = {
        'action': 'reroute_cross_document_track_span', 'start_end': end_ref('A', 1),
        'old_edges': [{'document': key[0], 'edge_id': key[1]} for key in old],
        'replacement_edges': [{'document': key[0], 'edge_id': key[1]} for key in new],
        'expected_replacement_length_m': 3600,
        'expected_replacement_safety_elements': [
            {'document': key[0], 'element_id': model_id(project.model(key).contents[7].value.contents[7].value)}
            for key in new],
    }
    return docs, catalog, operation


def test_reroute_moves_both_continuations_and_keeps_primary_and_path_identities(crossing):
    docs, catalog, operation = crossing
    old = project_from(docs, NATIVE_PATHS, catalog)
    after, report = apply(docs, catalog, operation)
    assert report['changed_documents'] == ['A', 'B'] and report['original_connector_pair_retained']
    assert report['old_pair'] == [('A', 5), ('B', 0)] and report['new_pair'] == [('A', 9), ('B', 8)]
    assert report['continuation_ownership_verified'] and report['destination_catalog_unchanged']
    assert report['old_length_m'] == 2000 and report['new_length_m'] == 3600
    assert len(report['rewritten_routes']) == 2
    assert {row['kind'] for row in report['affected_movement_distances']} == {'route', 'path', 'itinerary'}
    assert all(row['after_distance_m'] - row['before_distance_m'] == 1600 for row in report['affected_movement_distances'])
    assert after.route_view(after.owned(('A', 0), 'OTRoute', FORWARD)) == [('A', 0), ('A', 8), ('B', 4)]
    assert after.route_view(after.owned(('B', 5), 'OTRoute', REVERSE)) == [('B', 5), ('B', 9), ('A', 1)]
    assert after.route_view(after.owned(('B', 8), 'OTRoute', FORWARD)) == [('B', 4)]
    assert after.route_view(after.owned(('A', 9), 'OTRoute', REVERSE)) == [('A', 1)]
    assert after.block_end(('A', 5)) == ('B', 0)
    assert [old.path_view(obj)[1] for obj in old.paths_objects] == [after.path_view(obj)[1] for obj in after.paths_objects]
    with pytest.raises(ValueError, match='Unresolved exact OTRoute'):
        after.owned(('B', 0), 'OTRoute', FORWARD)


@pytest.mark.parametrize('retire', [False, True])
def test_crossing_rebinds_receiving_instrument_with_outer_owner_and_verified_new_edges(crossing, worksheets, retire):
    docs, catalog, operation = crossing
    old = operation['old_edges'][1]['edge_id']
    new = operation['replacement_edges'][1]['edge_id']
    source = {'action': 'create_instrument', 'end_id': 4, 'name': 'Receiving Meter', 'edge_ids': [old],
              'frame': [120, 62, 80, 42], 'direction_code': 2, 'display': ['course', 'clock', 'speed'], 'visible': False}
    monitored, receipt = native_monitoring.transform(docs['B'], worksheets[1], [source])
    expected, = receipt['after']['instruments']
    review = {'document': 'B', 'instrument_id': expected['id'], 'expected_end_id': 4, 'expected_edge_ids': [old],
              'edge_rebindings': [{'old_edge_id': old, 'new_edge_ids': [new]}]}
    with pytest.raises(ValueError, match='archived observers'):
        apply({**docs, 'B': monitored}, catalog, operation)
    candidate, report = apply({**docs, 'B': monitored}, catalog,
                              {**operation, 'retire_original': retire, 'instrument_edge_rebindings': [review]})
    native_record, = native_monitoring.records(candidate.roots['B'])['instruments']
    proof = report['dependency_transfers']
    assert native_record == {**expected, 'edge_ids': [new]}
    assert proof['native_readback_verified'] and report['continuation_ownership_verified']
    assert proof['instrument_edge_rebindings'][0]['before_edge_ids'] == [old]
    assert proof['instrument_edge_rebindings'][0]['after_edge_ids'] == [new]
    assert (old in candidate.byid['B']) == (not retire)


def test_junction_routes_share_former_track_but_select_distinct_replacements(crossing):
    docs, catalog, fixture_operation = crossing
    forward = {key: value for key, value in fixture_operation.items() if key != 'action'}
    old_a, old_b = forward['old_edges']
    first, new_b = forward['replacement_edges']
    shapes = shapes_for(docs['A'])
    project = project_from(docs, NATIVE_PATHS, catalog)
    x, _ = position(project.model(('A', 8)))
    _, y = position(project.model(('A', 1)))
    project, _ = apply(docs, catalog, {'action': 'move_vertex', 'end_id': 8, 'x': x, 'y': y})
    docs = save_project(project)
    project, split = apply(docs, catalog, {'action': 'split_edge', 'edge_id': first['edge_id'],
                                         'first_length_m': 600}, shapes=shapes)
    first_end, second_end = split['new_end_ids']
    project, branch = apply(save_project(project), catalog, {'action': 'insert_edge',
        'end_ids': [second_end, 4], 'length_m': 250, 'radius_m': 0, 'gradient_per_mille': 0,
        'track_name': 'Alternate connector approach', 'line_name': '', 'allow_safety_regroup': True,
        'rack_rail': False, 'remark': '', 'speeds': [{'train_type': '0', 'speed12_kmh': 50, 'speed21_kmh': 50}]},
        shapes=shapes)
    docs = save_project(project)
    lead = {'document': 'A', 'edge_id': project.edge_between(('A', 0), ('A', first_end))[1]}
    new_exit = {'document': 'A', 'edge_id': project.edge_between(('A', first_end), ('A', 8))[1]}
    shortcut = {'document': 'A', 'edge_id': branch['edge_id']}

    def select(document, identity):
        name, array_id, start_id = identity
        return {'document': document, 'name': name, 'array_id': array_id, 'start_id': start_id}

    def review(section, rails, routes, length):
        return {**section, 'replacement_edges': rails, 'routes': routes,
                'expected_replacement_length_m': length,
                'expected_replacement_safety_elements': [
                    {'document': ref['document'], 'element_id': model_id(
                        project.model((ref['document'], ref['edge_id'])).contents[7].value.contents[7].value)}
                    for ref in rails]}

    forward = review(forward, [lead, new_exit, new_b], [select('A', FORWARD)], 3600)
    reverse = review({**forward, 'connector_policy': 'retain_pair'},
                     [lead, shortcut, old_b], [select('B', REVERSE)], 1850)
    for document, name in (('A', 'I:A-B'), ('B', 'I:B-A')):
        docs[document], _ = set_safety_margins(docs[document], name, [
            {'position_m': 1000, 'safety_margin_m': 30},
            {'position_m': 2000, 'safety_margin_m': 45},
        ])
    operation = {'action': 'reroute_junction_track_spans', 'crossings': [forward, reverse],
                 'witness_itineraries': {'I:A-B': 3600, 'I:B-A': 1850}, 'retire_original': True,
                 'map_itinerary_safety_margins': True}
    after, receipt = apply(docs, catalog, operation)
    assert receipt['witness_itineraries']['I:A-B']['crossing_indices'] == [0]
    assert receipt['witness_itineraries']['I:B-A']['crossing_indices'] == [1]
    assert after.route_view(after.owned(('A', 0), 'OTRoute', FORWARD)) == [
        ('A', 0), ('A', first_end), ('A', 8), ('B', 4)]
    assert after.route_view(after.owned(('B', 5), 'OTRoute', REVERSE)) == [
        ('B', 5), ('B', 1), ('A', second_end), ('A', 1)]
    assert after.block_end(('B', 0)) == ('A', 5) and after.block_end(('B', 8)) == ('A', 9)
    assert receipt['retirement'][0]['removed_edge_ids'] == [old_a['edge_id']]
    assert old_a['edge_id'] not in after.byid['A']
    assert old_b['edge_id'] in after.byid['B']
    mapped = {row['identity'][0]: [point['position_m'] for point in row['after']]
              for row in receipt['mapped_safety_margin_profiles']}
    assert mapped == {'I:A-B': [1800, 3600], 'I:B-A': [925, 1850]}

    original = docs.copy()
    with pytest.raises(ValueError, match='primary Route only once'):
        apply(docs, catalog, {**operation, 'crossings': [forward, {**reverse, 'routes': forward['routes']}]})
    with pytest.raises(ValueError, match='Each reviewed crossing needs a saved witness'):
        apply(docs, catalog, {**operation, 'witness_itineraries': {'I:A-B': 3600}})
    with pytest.raises(ValueError, match='requires explicit map_itinerary_safety_margins'):
        apply(docs, catalog, {**operation, 'map_itinerary_safety_margins': False})
    assert docs == original


def test_junction_connector_names_are_checked_after_all_departures(crossing):
    docs, catalog, _ = crossing
    project = project_from(docs, NATIVE_PATHS, catalog)
    old_receiver, other_receiver = ('B', 0), ('B', 8)
    first = project.owned(old_receiver, 'OTRoute', FORWARD)
    second = path_functions.clone(first)
    second.contents[2].values[:] = [0, 10]
    other_identity = FORWARD[0], 0, 10
    other_holder = project.model(other_receiver).contents[15].value
    writer.set_elements(other_holder.contents[0].value, [second])
    old_key = old_receiver, 'OTRoute', FORWARD
    other_key = other_receiver, 'OTRoute', other_identity
    protection = {'B': {old_key: {'release': 4}, other_key: {'release': 6}}}
    first_new = other_receiver, 'OTRoute', FORWARD
    second_new = old_receiver, 'OTRoute', other_identity
    with pytest.raises(ValueError, match='ambiguous continuation name'):
        _commit_continuations(project, [(first, old_key, first_new, {'release': 4})], protection)
    assert project.owned(old_receiver, 'OTRoute', FORWARD) is first
    _commit_continuations(project, [
        (first, old_key, first_new, {'release': 4}), (second, other_key, second_new, {'release': 6}),
    ], protection)
    assert route_factory.wrapper(other_holder, 'OTRouteList') == [first]
    assert project.owned(old_receiver, 'OTRoute', other_identity) is second
    assert protection == {'B': {first_new: {'release': 4}, second_new: {'release': 6}}}


def test_reroute_can_remove_both_old_crossing_approaches_and_boundary_pairs(crossing):
    docs, catalog, operation = crossing
    retained, _ = apply(docs, catalog, operation)
    after, report = apply(docs, catalog, {**operation, 'retire_original': True})
    assert report['original_connector_pair_retained'] is False
    assert report['continuation_ownership_verified']
    assert after.block_end(('A', 9)) == ('B', 8)
    assert after.block_end(('B', 8)) == ('A', 9)
    assert _movement_manifest(after) == _movement_manifest(retained)
    assert [row['removed_end_ids'] for row in report['retirement']] == [[4, 5], [0, 1]]
    for row in report['retirement']:
        document = row['document']
        removed = set(retained.byid[document]) - set(after.byid[document])
        assert removed == {*row['removed_edge_ids'], *row['removed_end_ids'], *row['removed_safety_element_ids']}
        assert row['removed_edge_ids'] == [edge['edge_id'] for edge in operation['old_edges']
                                           if edge['document'] == document]


def test_crossing_retirement_blocks_partial_shunting_and_other_sheet_occupation_group(crossing):
    docs, catalog, operation = crossing
    retire = {**operation, 'retire_original': True}
    project = project_from(docs, NATIVE_PATHS, catalog)
    start, end = (project.model(('A', item)) for item in (0, 4))
    array_id = start.contents[19].value + 1
    spec = {'name': 'S:Partial approach', 'description': '', 'end_ids': [0, 4],
            'speed_kmh': 25, 'release_time_s': 1, 'reservation_time_s': 1}
    path = shunting.build_shunting_path([start, end], array_id, spec)
    array = start.contents[16].value.contents[0].value
    writer.set_elements(array, [*path_functions.mutable_array(array), path])
    start.contents[19].value = array_id
    with pytest.raises(ValueError, match="saved shunting 'S:Partial approach' still refers"):
        apply(save_project(project), catalog, retire)

    edge_id = operation['old_edges'][1]['edge_id']
    source = project_from(docs, NATIVE_PATHS, catalog)
    root = source.roots['A']
    _, array, _ = native_occupation_groups.entries(root)
    other_blob, _ = native_occupation_groups.transform(docs['B'], 'B', [
        {'action': 'create', 'name': 'RemoteApproach', 'edge_ids': [edge_id]},
    ])
    other_root = writer.load_next_compatible(other_blob)[0]
    _, _, remote = native_occupation_groups.entries(other_root)
    writer.set_elements(array, remote)
    with pytest.raises(ValueError, match="monitor 'RemoteApproach' still refers"):
        apply(save_project(source), catalog, retire)


def test_crossing_retirement_will_not_remove_outer_signal_end(crossing):
    docs, catalog, operation = crossing
    with pytest.raises(ValueError, match='only reviewed isolated interior pairs'):
        apply(docs, catalog, {**operation, 'retire_original': True, 'retire_isolated_ends': [end_ref('A', 1)]})


@pytest.fixture
def same_connector_alternative(crossing):
    docs, catalog, operation = crossing
    shape = shapes_for(docs['A'])
    detached, _ = apply(docs, catalog, {'action': 'replace_connectors', 'link': [],
                        'unlink': [{'a': end_ref('A', 9), 'b': end_ref('B', 8)}]})
    branch, edge = apply(save_project(detached), catalog, {'action': 'insert_edge', 'end_ids': [9, 4], 'length_m': 150,
        'radius_m': 0, 'gradient_per_mille': 0, 'track_name': 'Branch return', 'line_name': '',
        'allow_safety_regroup': True, 'rack_rail': False, 'remark': '',
        'speeds': [{'train_type': '0', 'speed12_kmh': 50, 'speed21_kmh': 50}]}, shapes=shape)
    docs = save_project(branch)
    old_a, common_b = operation['old_edges']
    first = operation['replacement_edges'][0]
    replacement = [first, {'document': 'A', 'edge_id': edge['edge_id']}, common_b]
    docs['A'], _ = native_occupation_groups.transform(docs['A'], 'A', [
        {'action': 'create', 'name': 'Approach', 'edge_ids': [old_a['edge_id']], 'selected': True},
    ])
    return docs, catalog, {**operation, 'connector_policy': 'retain_pair', 'retire_original': True,
        'replacement_edges': replacement, 'expected_replacement_length_m': 2950,
        'expected_replacement_safety_elements': [
            {'document': row['document'], 'element_id': model_id(branch.model((row['document'], row['edge_id']))
                                                                .contents[7].value.contents[7].value)} for row in replacement],
        'occupation_group_rebindings': [{'document': 'A', 'name': 'Approach', 'expected_edge_ids': [old_a['edge_id']],
            'edge_rebindings': [{'old_edge_id': old_a['edge_id'], 'new_edge_ids': [first['edge_id'], edge['edge_id']]}]}],
    }


def test_reroute_reuses_connector_and_retires_only_the_changed_approach(same_connector_alternative):
    docs, catalog, operation = same_connector_alternative
    before = project_from(docs, NATIVE_PATHS, catalog)
    after, report = apply(docs, catalog, operation)
    assert report['changed_documents'] == ['A']
    assert report['old_pair'] == report['new_pair'] == [('A', 5), ('B', 0)]
    assert report['original_connector_pair_retained'] and report['continuation_ownership_verified']
    assert after.block_end(('A', 5)) == ('B', 0) and after.block_end(('B', 0)) == ('A', 5)
    assert after.route_view(after.owned(('B', 0), 'OTRoute', FORWARD)) == [('B', 4)]
    assert after.route_view(after.owned(('A', 5), 'OTRoute', REVERSE)) == [('A', 9), ('A', 1)]
    assert report['retirement'] == [{'document': 'A', 'removed_edge_ids': [operation['old_edges'][0]['edge_id']],
                                   'removed_end_ids': [], 'removed_safety_element_ids': []}]
    assert native_occupation_groups.records(after.roots['A'], 'A')[0]['edge_ids'] == [
        row['edge_id'] for row in operation['replacement_edges'][:2]]
    old, new = _movement_manifest(before), _movement_manifest(after)
    assert old.keys() == new.keys() and all(old[key][1] == new[key][1] for key in old)


def test_single_selected_direction_keeps_reverse_exclusion_monitor_and_berth(same_connector_alternative):
    docs, catalog, original = same_connector_alternative
    local = original['replacement_edges'][:2]
    old_edge = original['old_edges'][0]['edge_id']
    additions = [row['edge_id'] for row in local]
    shape = shapes_for(docs['A'])
    spare = []
    for x, side in ((240, 1), (340, 0)):
        after, report = apply(docs, catalog, {'action': 'insert_vertex', 'x': x, 'y': 112,
            'orientation': 'horizontal', 'names': ['', '']}, shapes=shape)
        docs = save_project(after)
        spare.append(report['added_vertex_end_ids'][side])
    after, report = apply(docs, catalog, {'action': 'insert_edge', 'end_ids': spare, 'length_m': 100,
        'radius_m': 0, 'gradient_per_mille': 0, 'track_name': 'Spur', 'line_name': '',
        'allow_safety_regroup': False, 'rack_rail': False, 'remark': '',
        'speeds': [{'train_type': '0', 'speed12_kmh': 25, 'speed21_kmh': 25}]},
        shapes=shape)
    spare_edge = report['edge_id']
    after, _ = apply(save_project(after), catalog, {'action': 'set_edge_exclusion', 'edge_id': additions[0],
                                                    'target_edge_id': spare_edge, 'expected_target_edge_id': None})
    common = original['old_edges'][1]['edge_id']
    docs = save_project(after)
    after, _ = apply(docs, catalog, {'action': 'split_edge', 'edge_id': common, 'first_length_m': 400},
                     target='B', shapes=shapes_for(docs['B']))
    route = after.owned(('A', 0), 'OTRoute', FORWARD)
    platform_entry = after.route_view(route)[-2]
    common_approach = {'document': 'B', 'edge_id': after.edge_between(('A', 4), platform_entry)[1]}
    for document, reference, area in (('A', ('A', 0), []), ('B', ('B', 4), [platform_entry])):
        station = native.obj([('OTStationModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], [
            ('i', [max(after.byid[document]) + 1]), ('f', [0.0]), ('f', [20.0]), ('f', [10.0]),
            ('i', [0]), ('i', [0]), ('@', [None]), ('@', [native.string(document)]),
            ('ii', [2, 4]), ('ii', [1, 0]),
        ])
        for end in [reference, *area]:
            for key in (end, after.related(end)):
                model = after.model(key)
                model.contents[12].value = station
                model.contents[20].value = 2 if end == reference else 1
        after.model(reference).contents[11].value.contents[8].values[1] = 4
        writer.set_elements(after.roots[document].contents[2].value, [*after.models[document], station])
    docs = save_project(after)
    before = project_from(docs, NATIVE_PATHS, catalog)
    replacement = [*local, common_approach]
    crossing = {'connector_policy': 'retain_pair', 'start_end': original['start_end'],
                'old_edges': [original['old_edges'][0], common_approach], 'replacement_edges': replacement,
                'expected_replacement_length_m': 2350,
                'expected_replacement_safety_elements': [{'document': row['document'], 'element_id': model_id(
                    before.model((row['document'], row['edge_id'])).contents[7].value.contents[7].value)}
                    for row in replacement],
                'routes': [{'document': 'A', 'name': FORWARD[0], 'array_id': FORWARD[1], 'start_id': FORWARD[2]}]}
    retained = {'document': 'A', 'source_edge_id': additions[0], 'target_edge_id': spare_edge}
    extend = {'document': 'A', 'name': 'Approach', 'expected_edge_ids': [old_edge], 'added_edge_ids': additions}
    request = {'action': 'reroute_junction_track_spans', 'crossings': [crossing],
               'witness_itineraries': {'I:A-B': 2950}, 'retained_exclusion_links': [retained],
               'occupation_group_extensions': [extend]}
    fresh, proof = apply(docs, catalog, request)
    assert fresh.block_end(('A', 5)) == ('B', 0)
    reverse = proof['retained_alignment_routes'][0]
    assert reverse['identity'] == REVERSE
    for fragment in reverse['fragments']:
        owner = fragment['owner']
        old, new = (graph.owned(owner, 'OTRoute', REVERSE) for graph in (before, fresh))
        assert before.route_view(old) == fresh.route_view(new)
        assert _protection_values(old, _route_shape(old)) == _protection_values(new, _route_shape(new))
    monitor, = native_occupation_groups.records(fresh.roots['A'], 'A')
    assert monitor['edge_ids'] == [old_edge, *additions]
    edges = {i: row for i, row in fresh.byid['A'].items() if writer.kind(row) == 'OTEdgeModel'}
    assert _links(edges) == {additions[0]: spare_edge}
    stop = proof['selected_station_stops']['I:A-B'][-1]
    assert stop['end_key'] == ('B', 4) and stop['stopping_area_length_m'] == 600
    assert (stop['before_reference_distance_m'], stop['after_reference_distance_m']) == (2000, 2950)

    with pytest.raises(ValueError, match='reciprocal Edge Exclusion Link differs'):
        apply(docs, catalog, {**request, 'retained_exclusion_links': [{**retained, 'target_edge_id': old_edge}]})
    with pytest.raises(ValueError, match='existing reviewed group Edge'):
        apply(docs, catalog, {**request, 'occupation_group_extensions': [{**extend, 'insert_before_edge_id': spare_edge}]})
    with pytest.raises(ValueError, match='distinct new alignment Edges'):
        apply(docs, catalog, {**request, 'occupation_group_extensions': [{**extend, 'added_edge_ids': [spare_edge]}]})
    with pytest.raises(ValueError, match='monitor Edge still used by an unedited saved Route'):
        apply(docs, catalog, {**request, 'occupation_group_extensions': [],
                              'occupation_group_rebindings': original['occupation_group_rebindings']})


def test_retained_connector_policy_leaves_default_and_residual_guards(same_connector_alternative):
    docs, catalog, operation = same_connector_alternative
    with pytest.raises(ValueError, match='different reciprocal pair'):
        apply(docs, catalog, {**operation, 'connector_policy': 'replace_pair'})
    with pytest.raises(ValueError, match="monitor 'Approach' still refers"):
        apply(docs, catalog, {**operation, 'occupation_group_rebindings': []})
    with pytest.raises(ValueError, match='only reviewed isolated interior pairs'):
        apply(docs, catalog, {**operation, 'retire_isolated_ends': [end_ref('A', 5)]})


@pytest.fixture
def observed_crossing(crossing):
    docs, catalog, operation = crossing
    shapes = shapes_for(docs['A'])
    ends = []
    for x, side in ((235, 1), (335, 0)):
        project, receipt = apply(docs, catalog, {'action': 'insert_vertex', 'x': x, 'y': 112,
            'orientation': 'horizontal', 'names': ['', '']}, shapes=shapes)
        docs = save_project(project)
        ends.append(receipt['added_vertex_end_ids'][side])
    project, receipt = apply(docs, catalog, {'action': 'insert_edge', 'end_ids': ends, 'length_m': 100,
        'radius_m': 0, 'gradient_per_mille': 0, 'track_name': 'Independent spur', 'line_name': '',
        'allow_safety_regroup': False, 'rack_rail': False, 'remark': '',
        'speeds': [{'train_type': '0', 'speed12_kmh': 20, 'speed21_kmh': 20}]}, shapes=shapes)
    spur = receipt['edge_id']
    a_old, b_old = (row['edge_id'] for row in operation['old_edges'])
    a_new, b_new = (row['edge_id'] for row in operation['replacement_edges'])
    project, _ = apply(save_project(project), catalog, {'action': 'set_edge_exclusion', 'edge_id': a_old,
        'target_edge_id': spur, 'expected_target_edge_id': None})
    docs = save_project(project)
    docs['B'], _ = native_occupation_groups.transform(docs['B'], 'B', [
        {'action': 'create', 'name': 'ArrivalApproach', 'edge_ids': [b_old], 'selected': False},
    ])
    transfers = {'exclusion_link_rebindings': [{'document': 'A', 'old_source_edge_id': a_old,
        'old_target_edge_id': spur, 'new_source_edge_id': a_new, 'new_target_edge_id': spur}],
        'occupation_group_rebindings': [{'document': 'B', 'name': 'ArrivalApproach', 'expected_edge_ids': [b_old],
            'edge_rebindings': [{'old_edge_id': b_old, 'new_edge_ids': [b_new]}]}]}
    return docs, catalog, {**operation, 'retire_original': True, **transfers}, (a_old, a_new, spur, b_new)


def test_crossing_transaction_transfers_exclusion_and_occupation_then_retires_old_edges(observed_crossing):
    docs, catalog, operation, (old, new, spur, receiving_edge) = observed_crossing
    project, report = apply(docs, catalog, operation)
    assert old not in project.byid['A']
    assert project.model(('A', new)).contents[13].value is project.model(('A', spur))
    assert project.model(('A', spur)).contents[14].value is project.model(('A', new))
    moved = report['dependency_transfers']
    assert moved['native_readback_verified'] and not report['original_connector_pair_retained']
    group, = native_occupation_groups.records(project.roots['B'], 'B')
    assert group['edge_ids'] == [receiving_edge] and group['selected'] is False
    assert group == moved['occupation_group_rebindings'][0]['after']


def test_crossing_refuses_unreviewed_or_wrong_dependency_transfers(observed_crossing):
    docs, catalog, operation, (old, new, spur, _) = observed_crossing
    with pytest.raises(ValueError, match='direct Edge Exclusion Link requires'):
        apply(docs, catalog, {**operation, 'exclusion_link_rebindings': []})
    with pytest.raises(ValueError, match="monitor 'ArrivalApproach' still refers"):
        apply(docs, catalog, {**operation, 'occupation_group_rebindings': []})
    exclusion, = operation['exclusion_link_rebindings']
    with pytest.raises(ValueError, match='old-only crossing Edge side'):
        apply(docs, catalog, {**operation, 'exclusion_link_rebindings': [{**exclusion, 'new_target_edge_id': old}]})
    group, = operation['occupation_group_rebindings']
    with pytest.raises(ValueError, match='saved occupation Edge order'):
        apply(docs, catalog, {**operation, 'occupation_group_rebindings': [{**group, 'expected_edge_ids': [new]}]})


def test_retained_old_alignment_cannot_lose_exclusion_used_by_partial_shunting(observed_crossing):
    docs, catalog, operation, _ = observed_crossing
    project = project_from(docs, NATIVE_PATHS, catalog)
    start, end = (project.model(('A', item)) for item in (0, 4))
    array_id = start.contents[19].value + 1
    spec = {'name': 'S:Remains on old alignment', 'description': '', 'end_ids': [0, 4],
            'speed_kmh': 25, 'release_time_s': 1, 'reservation_time_s': 1}
    path = shunting.build_shunting_path([start, end], array_id, spec)
    array = start.contents[16].value.contents[0].value
    writer.set_elements(array, [*path_functions.mutable_array(array), path])
    start.contents[19].value = array_id
    with pytest.raises(ValueError, match="saved shunting 'S:Remains on old alignment' still needs"):
        apply(save_project(project), catalog, {**operation, 'retire_original': False})


def test_bound_course_catalog_refuses_global_span_incident_when_retiring(crossing, tmp_path, monkeypatch):
    _, _, operation = crossing
    root, version = writer.load_next_compatible(course_archive())
    array = root.contents[1].value
    disturbance = incidents.create({'name': 'Slow area', 'type': 'position_speed', 'begin_time': '09:00:00',
        'end_time': '10:00:00', 'begin_day': 0, 'end_day': 0, 'line_id': '', 'track_id': '',
        'begin_km': '8.2', 'end_km': '8.8', 'enabled': True, 'probability_percentage': 100,
        'reduced_speed_kmh': 40}, array)
    writer.set_elements(array, [disturbance])
    courses = writer.dump_verified(root, version)
    service = SavedGeometryTools(tmp_path)
    monkeypatch.setattr(service, '_bound_catalog', lambda *args: (tmp_path / 'test.courses', courses))
    original = RerouteCrossDocumentTrackSpan.model_validate(operation)
    assert service._check_incident_targets(None, None, 'A', original)[1] == courses
    retire = RerouteCrossDocumentTrackSpan.model_validate({**operation, 'retire_original': True})
    with pytest.raises(ValueError, match='position or route-span Incident'):
        service._check_incident_targets(None, None, 'A', retire)


def test_crossing_incident_guard_requires_each_review_to_match_the_selected_alignment(crossing, tmp_path, monkeypatch):
    _, _, operation = crossing
    old_a, old_b = [row['edge_id'] for row in operation['old_edges']]
    new_a, new_b = [row['edge_id'] for row in operation['replacement_edges']]
    root, version = writer.load_next_compatible(course_archive())
    array = root.contents[1].value
    common = {'begin_time': '09:00:00', 'end_time': '10:00:00', 'begin_day': 0, 'end_day': 0,
              'enabled': False, 'probability_percentage': 100}
    writer.set_elements(array, [
        incidents.create({**common, 'name': 'Clos-A', 'type': 'edge_blockage', 'document': 'A', 'model_id': old_a}, array),
        incidents.create({**common, 'name': 'Clos-B', 'type': 'edge_group_blockage', 'document': 'B', 'model_ids': [old_b]}, array),
    ])
    courses = writer.dump_verified(root, version)
    service = SavedGeometryTools(tmp_path)
    monkeypatch.setattr(service, '_bound_catalog', lambda *args: (tmp_path / 'test.courses', courses))
    reviews = [{'name': f'Clos-{name}', 'document': name, 'expected_edge_ids': [old],
                'edge_rebindings': [{'old_edge_id': old, 'new_edge_ids': [new]}]}
               for name, old, new in (('A', old_a, new_a), ('B', old_b, new_b))]

    def checked(requests):
        args = RerouteCrossDocumentTrackSpan.model_validate({**operation, 'track_incident_rebindings': requests})
        return service._check_incident_targets(None, None, 'A', args)

    assert checked(reviews)[1] == courses
    with pytest.raises(ValueError, match='A saved track blockage Incident'):
        checked(reviews[:1])
    with pytest.raises(ValueError, match='Review each track blockage Incident only once'):
        checked([*reviews, reviews[0]])
    with pytest.raises(ValueError, match='reviewed same-worksheet replacement'):
        checked([{**reviews[0], 'edge_rebindings': [{'old_edge_id': old_a, 'new_edge_ids': [old_a]}]}, reviews[1]])


def test_boundary_release_anchor_needs_exact_approval_and_slow_zone_stays(crossing):
    docs, catalog, operation = crossing
    source = project_from(docs, NATIVE_PATHS, catalog)
    route = source.owned(('A', 0), 'OTRoute', FORWARD)
    fields = route.contents[_route_shape(route) + 1].values
    first, boundary = source.model(('A', 0)), source.model(('A', 4))
    fields[0] = path_functions.array_like(fields[0], [first, boundary])
    protected = save_project(source)
    with pytest.raises(ValueError, match='explicit matching connector-boundary'):
        apply(protected, catalog, operation)
    mapping = {'old': end_ref('A', 4), 'new': end_ref('A', 8)}
    approved = {**operation, 'release_boundary_rebindings': [mapping]}
    after, receipt = apply(protected, catalog, approved)
    forward = after.owned(('A', 0), 'OTRoute', FORWARD)
    assert _protection_values(forward, _route_shape(forward))['release_group_end_ids'] == [0, 8]
    assert receipt['rewritten_routes'][0]['rebound_release_boundaries'] == [{'old': ('A', 4), 'new': ('A', 8)}]
    with pytest.raises(ValueError, match='Only matching original and replacement'):
        apply(protected, catalog, {**operation, 'release_boundary_rebindings': [{**mapping, 'new': end_ref('A', 0)}]})
    fields[1:] = [first, boundary]
    with pytest.raises(ValueError, match='Existing slow-speed zone endpoints'):
        apply(save_project(source), catalog, approved)


def test_reject_wrong_reviewed_safety_or_same_connector_pair(crossing):
    docs, catalog, operation = crossing
    reversed_elements = operation['expected_replacement_safety_elements'][::-1]
    with pytest.raises(ValueError, match='ordered document Safety Element'):
        apply(docs, catalog, {**operation, 'expected_replacement_safety_elements': reversed_elements})
    with pytest.raises(ValueError, match='different reciprocal pair'):
        apply(docs, catalog, {**operation, 'replacement_edges': operation['old_edges']})


def test_exact_fragment_anchor_moves_both_release_and_zone_on_reroute(crossing):
    docs, catalog, operation = crossing
    original = project_from(docs, NATIVE_PATHS, catalog)
    forward = original.owned(('A', 0), 'OTRoute', FORWARD)
    flags = _route_shape(forward)
    group = forward.contents[flags + 1].values
    first, boundary = (original.model(('A', end)) for end in (0, 4))
    group[0] = path_functions.array_like(group[0], [first, boundary])
    group[1:] = [first, boundary]
    receiving = original.owned(('B', 0), 'OTRoute', FORWARD)
    receiving.contents[_route_shape(receiving) + 1].values[2] = original.model(('B', 4))
    docs = save_project(original)
    review = {
        'fragment_owner': end_ref('A', 0),
        'route': {'name': FORWARD[0], 'array_id': FORWARD[1], 'start_id': FORWARD[2]},
        'anchors': [{'old_end_id': 4, 'new_end_id': 8}],
    }
    reviewed = {**operation, 'route_anchor_rebindings': [review], 'retire_original': True}
    RerouteCrossDocumentTrackSpan.model_validate(reviewed)
    revised, receipt = apply(docs, catalog, reviewed)
    saved = revised.owned(('A', 0), 'OTRoute', FORWARD)
    before = _protection_values(forward, flags)
    after = _protection_values(saved, _route_shape(saved))
    assert after == {**before, 'release_group_end_ids': [0, 8], 'slow_speed_zone_end_ids': [0, 8]}
    proof = receipt['rewritten_routes'][0]
    expected = [{'old': ('A', 4), 'new': ('A', 8)}]
    assert proof['rebound_release_boundaries'] == proof['rebound_slow_speed_zone_ends'] == expected
    assert 4 not in revised.byid['A']
    receiving = revised.owned(('B', 8), 'OTRoute', FORWARD)
    assert receiving.contents[_route_shape(receiving) + 1].values[1:] == [None, revised.model(('B', 4))]
    with pytest.raises(ValueError, match='did not match a changed original fragment|explicit matching connector-boundary'):
        apply(docs, catalog, {**reviewed, 'route_anchor_rebindings': [{**review, 'fragment_owner': end_ref('A', 3)}]})
    with pytest.raises(ValueError, match='either the connector boundary'):
        apply(docs, catalog, {**reviewed,
              'release_boundary_rebindings': [{'old': end_ref('A', 4), 'new': end_ref('A', 8)}]})
