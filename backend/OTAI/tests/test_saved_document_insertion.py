"""Check connector reattachment and the transitive Route and Path rewrite."""

import pytest

from opentrack_ai.current_archive import path_functions, route_factory, writer
from opentrack_ai.current_archive.itinerary_edit_tools import _margin_members, _margin_values, set_safety_margins
from opentrack_ai.current_archive.movement_edits import edit_route
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.route_edit_tools import edit_cross_document_movement
from opentrack_ai.current_archive.saved_document_insertion import _middle_chain, _route_profile, _stored_zone
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, model_id, project_from, transform
from opentrack_ai.current_archive.saved_geometry_tools import InsertOperationalDocumentSpan
from opentrack_ai.current_archive.saved_terminal_overlap import overlap_reference
from opentrack_ai.current_archive.signal_operating_fields import append_route_aspects
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_itinerary_native_edit import schematic_document
from test_path_lifecycle_native import course_catalog, cross_project
from test_saved_geometry import shapes_for


def end(sheet, ordinal):
    return {'document': sheet, 'end_id': ordinal}


@pytest.fixture(scope='module')
def chain():
    documents, paths, catalog, path_refs, _ = cross_project()
    specification = generate.spec()
    profile, = specification['edges']
    specification['vertices'] = [generate.vertex(key, 40 + 100 * i) for i, key in enumerate('XYZ')]
    specification['edges'] = [{**profile, 'key': a + b, 'from': [a, 1], 'to': [b, 0], 'length_m': 200}
                              for a, b in ('XY', 'YZ')]
    documents['M'], ends = schematic_document(specification, [('Y', 0), ('Y', 1)])
    paths['M'] = 'OTDocuments/M.opentrack'
    project = project_from(documents, paths, catalog)
    edges = [obj for obj in project.models['M'] if writer.kind(obj) == 'OTEdgeModel']
    originals = {row['source_document']: row for row in project.continuations}
    operation = InsertOperationalDocumentSpan(
        action='insert_operational_document_span',
        old_pair={'a': end('A', originals['A']['source_connector']),
                  'b': end('B', originals['A']['target_connector'])},
        middle_start=end('M', ends['X'][0]), middle_finish=end('M', ends['Z'][1]),
        middle_first_edge_ids=[model_id(edges[0])], middle_second_edge_ids=[model_id(edges[1])],
        expected_middle_safety_elements=[model_id(edge.contents[7].value.contents[7].value) for edge in edges],
        expected_middle_length_m=400,
        routes=[{'route': {'document': name, **row['route']}, 'continued_name': 'R:M-' + row['target_document']}
                for name, row in originals.items()],
    ).model_dump()
    return documents, paths, catalog, path_refs, operation


def test_bidirectional_reconnection_retains_identities_and_extends_exact_path_sequences(chain):
    documents, paths, catalog, path_refs, operation = chain
    output, report = transform(documents, paths, catalog, 'A', operation, courses=course_catalog())
    assert report['changed_documents'] == ['A', 'B', 'M']
    assert len(report['rewritten_routes']) == len(report['rewritten_paths']) == 2
    before = project_from(documents, paths, catalog)
    after = project_from(output, paths, catalog)
    assert report['itinerary_and_catalog_references_preserved']
    assert all(after.block_end(a) == b and after.block_end(b) == a for a, b in report['new_connector_pairs'])
    old_a, old_b = report['removed_direct_crossing']
    assert before.block_end(old_a) == old_b
    assert {after.block_end(outer)[0] for outer in (old_a, old_b)} == {'M'}
    for sheet, old_ref in path_refs.items():
        owner = sheet, old_ref['start_id']
        identity = old_ref['name'], old_ref['array_id'], old_ref['start_id']
        old_nodes, old_refs = before.path_view(before.owned(owner, 'OTPath', identity))
        new_nodes, new_refs = after.path_view(after.owned(owner, 'OTPath', identity))
        assert [key for key in new_nodes if key[0] != 'M'] == old_nodes
        assert new_refs[0] == old_refs[0] and new_refs[1][0] == 'M'
    assert {path_functions.info(obj)['name']: path_functions.info(obj)['saved_references'] for obj in before.dests} == {
        path_functions.info(obj)['name']: path_functions.info(obj)['saved_references'] for obj in after.dests}
    old_movements, new_movements = _movement_manifest(before), _movement_manifest(after)
    for key in old_movements:
        if key[0] in ('path', 'itinerary'):
            assert sum(item[1] for item in new_movements[key][2]) - sum(item[1] for item in old_movements[key][2]) == 400


def test_missing_reverse_route_or_unapproved_safety_group_aborts(chain):
    documents, paths, catalog, _, operation = chain
    original = documents.copy()
    with pytest.raises(ValueError, match='Review every existing Route'):
        transform(documents, paths, catalog, 'A', {**operation, 'routes': operation['routes'][:1]},
                  courses=course_catalog())
    with pytest.raises(ValueError, match='ordered Safety Element IDs'):
        transform(documents, paths, catalog, 'A', {**operation, 'expected_middle_safety_elements': [0, 0]},
                  courses=course_catalog())
    assert documents == original


def test_occupied_entry_follows_only_the_reviewed_terminal_leg(chain):
    documents, paths, catalog, _, operation = chain
    source = project_from(documents, paths, catalog)
    old, = [row for row in source.continuations if row['source_document'] == 'A']
    owner, receiver = ('A', old['route']['start_id']), ('B', old['target_connector'])
    identity = tuple(old['route'][key] for key in ('name', 'array_id', 'start_id'))
    route = source.owned(owner, 'OTRoute', identity)
    approach_edge = source.edge_between(*source.route_view(route)[-2:])
    original_length = source.model(approach_edge).contents[9].values[1]
    split, _ = transform(documents, paths, catalog, 'B', {
        'action': 'split_edge', 'edge_id': approach_edge[1], 'first_length_m': original_length // 2,
    }, shapes=shapes_for(documents['B']), courses=course_catalog())
    docs = {**documents, **split}
    source = project_from(docs, paths, catalog)
    route = source.owned(owner, 'OTRoute', identity)
    approach, terminal = source.route_view(route)[-2:]
    edge = source.edge_between(approach, terminal)
    station = native.obj([('OTStationModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], [
        ('i', [10000]), ('f', [0.0]), ('f', [100.0]), ('f', [50.0]), ('i', [0]), ('i', [0]),
        ('@', [None]), ('@', [native.string('JOIN')]), ('ii', [2, 4]), ('ii', [1, 0]),
    ])
    for pair, kind in ((approach, 1), (terminal, 2)):
        for key in (pair, source.related(pair)):
            model = source.model(key)
            model.contents[12].value = station
            model.contents[20].value = kind
    models = source.roots['B'].contents[2].value
    writer.set_elements(models, [*writer.elements(models), station])
    route.contents[6].values[:] = (3, 20.0, 0.0)
    source.owned(receiver, 'OTRoute', identity).contents[6].values[:] = (3, 20.0, 0.0)
    source.model(owner).contents[11].value.contents[9].values[2] |= 1
    docs.update({sheet: writer.dump_verified(source.roots[sheet], source.versions[sheet]) for sheet in ('A', 'B')})

    with pytest.raises(ValueError, match='occupied-entry or distance'):
        transform(docs, paths, catalog, 'A', operation, courses=course_catalog())
    approval = {'terminal_end': end(*terminal), 'stop_edge_id': edge[1], 'expected_speed_kmh': 20}

    def apply(review):
        plans = [{**row, 'preserve_local_protection': True, 'expected_occupied_entry': review}
                 if row['route']['document'] == 'A' else row for row in operation['routes']]
        return transform(docs, paths, catalog, 'A', {**operation, 'routes': plans}, courses=course_catalog())

    with pytest.raises(ValueError, match='exact directed station stopping Edge'):
        apply({**approval, 'stop_edge_id': edge[1] + 1})
    with pytest.raises(ValueError, match='reviewed speed-only setting'):
        apply({**approval, 'expected_speed_kmh': 25})
    changes, report = apply(approval)
    after = project_from({**docs, **changes}, paths, catalog)
    plan = next(row for row in report['rewritten_routes'] if row['retained_owner'] == owner)
    assert plan['transferred_occupied_entry']['stop_edge'] == edge
    assert plan['retained_protection']['occupied_entry'] == [0, 40.0, 0.0]
    assert plan['middle_entry_protection']['occupied_entry'] == [0, 40.0, 0.0]
    assert plan['middle_exit_protection']['occupied_entry'] == [3, 20.0, 0.0]
    assert plan['preserved_receiving_protection']['occupied_entry'] == [3, 20.0, 0.0]
    relay = after.model(plan['intermediate_owner']).contents[11].value
    assert relay.contents[9].values[2] & 1
    successor = after.owned(plan['intermediate_owner'], 'OTRoute', plan['added_route'])
    assert after.route_view(successor)[-2:] == [approach, terminal]


def test_refuses_incidents_or_safety_margins_on_transitively_edited_movements(chain):
    documents, paths, catalog, old_paths, operation = chain
    with pytest.raises(ValueError, match='Path-speed Incident'):
        transform(documents, paths, catalog, 'A', operation, courses=course_catalog(old_paths['A']))
    project = project_from(documents, paths, catalog)
    selected = next(dest for dest in project.dests if project.owners[id(dest)][0] == 'A')
    name = path_functions.info(selected)['name']
    distance = sum(project.model(project.edge_between(a, b)).contents[9].values[1]
                   for a, b in zip(project.dest_view(selected)[0], project.dest_view(selected)[0][1:]))
    edited, _ = set_safety_margins(documents['A'], name, [{'position_m': distance, 'safety_margin_m': 25.0}])
    with pytest.raises(ValueError, match='distance-based safety margins'):
        transform({**documents, 'A': edited}, paths, catalog, 'A', operation, courses=course_catalog())


def test_protected_reconnection_retains_release_planes_and_maps_reviewed_boundary(chain):
    documents, paths, catalog, _, operation = chain
    project = project_from(documents, paths, catalog)
    crossing = next(row for row in project.continuations if row['source_document'] == 'A')
    reference = crossing['route']
    revised_docs, _ = edit_cross_document_movement(
        documents, paths, catalog, 'A', reference,
        crossing['local_end_ids'], crossing['remote_end_ids'],
        primary_release_group_end_ids=crossing['local_end_ids'],
        continuation_release_group_end_ids=crossing['remote_end_ids'],
    )
    amended, _ = edit_route(revised_docs['A'], reference, {
        'approach_length_m': 300, 'approach_speed_kmh': 28, 'reserve_time_s': 12, 'release_time_s': 9,
    })
    revised_docs['A'] = amended
    definition = next(item for item in project.dests if project.owners[id(item)][0] == 'A')
    name = path_functions.info(definition)['name']
    nodes, _ = project.dest_view(definition)
    prefix = 0
    for a, b in zip(nodes, nodes[1:]):
        if a[0] != b[0]:
            break
        prefix += project.model(project.edge_between(a, b)).contents[9].values[1]
    revised_docs['A'], _ = set_safety_margins(revised_docs['A'], name, [
        {'position_m': position, 'safety_margin_m': margin}
        for position, margin in ((prefix - 25, 20), (prefix, 35), (prefix + 25, 50))
    ])
    inputs = {**documents, **revised_docs}

    with pytest.raises(ValueError, match='requires explicit preserve_local_protection'):
        transform(inputs, paths, catalog, 'A', operation, courses=course_catalog())
    _, (forward, _), _ = _middle_chain(project, operation)
    first, second = forward
    routes = [{
        **row, 'preserve_local_protection': True, 'reserve_with_previous': True,
        'middle_entry_release_end_ids': [first[-1][1]], 'middle_exit_release_end_ids': [first[-1][1], second[-1][1]],
    } if row['route']['document'] == 'A' else row for row in operation['routes']]
    approved = {**operation, 'routes': routes, 'safety_margin_mappings': [
        {'itinerary': name, 'expected_insertion_position_m': prefix, 'at_boundary': 'downstream'},
    ]}
    output, report = transform(inputs, paths, catalog, 'A', approved, courses=course_catalog())
    fresh = project_from(output, paths, catalog)
    saved_route = next(row for row in report['rewritten_routes'] if row['retained_owner'][0] == 'A')
    assert saved_route['retained_protection']['approach'] == [300.0, 28.0]
    assert saved_route['retained_protection']['timing'][2:4] == [9, 12]
    assert saved_route['retained_protection']['release_group_end_ids'] == crossing['local_end_ids']
    assert saved_route['preserved_receiving_protection']['release_group_end_ids'] == crossing['remote_end_ids']
    assert saved_route['middle_exit_protection']['route_flags'] == 1
    assert saved_route['middle_exit_protection']['release_group_end_ids'] == [first[-1][1], second[-1][1]]
    saved = next(item for item in fresh.dests if path_functions.info(item)['name'] == name)
    assert _margin_values(_margin_members(saved)[2]) == [
        {'position_m': position, 'safety_margin_m': margin}
        for position, margin in ((prefix - 25, 20), (prefix + 400, 35), (prefix + 425, 50))
    ]
    upstream = {**approved, 'safety_margin_mappings': [{**approved['safety_margin_mappings'][0], 'at_boundary': 'upstream'}]}
    _, unchanged_boundary = transform(inputs, paths, catalog, 'A', upstream, courses=course_catalog())
    assert unchanged_boundary['mapped_safety_margin_profiles'][0]['after'][1]['position_m'] == prefix
    bad_mapping = {**approved, 'safety_margin_mappings': [{**approved['safety_margin_mappings'][0],
                                                         'expected_insertion_position_m': prefix + 1}]}
    with pytest.raises(ValueError, match='exact insertion position'):
        transform(inputs, paths, catalog, 'A', bad_mapping, courses=course_catalog())


def test_preserves_fixed_local_slow_zone_and_head_flag_at_exact_original_anchors(chain):
    documents, paths, catalog, _, operation = chain
    project = project_from(documents, paths, catalog)
    route = next(row for row in operation['routes'] if row['route']['document'] == 'A')
    reference = route['route']
    identity = reference['name'], reference['array_id'], reference['start_id']
    owner = ('A', reference['start_id'])
    updated, _ = append_route_aspects(documents, paths, catalog, [owner],
                                      [{'start_end': owner, 'speeds_kmh': [40]}])
    revised = {**documents, **updated}
    project = project_from(revised, paths, catalog)
    selected = project.owned(owner, 'OTRoute', identity)
    nodes = path_functions.mutable_array(selected.contents[0].value)
    first, last = nodes
    wrapper = selected.contents[4].value
    aspect, = [item for item in route_factory.wrapper(wrapper, 'OTSigIndList') if item.contents[0].value == 4]
    writer.set_elements(wrapper.contents[0].value, [aspect])
    selected.contents[12].values[1:] = [first, last]
    selected.contents[11].value |= 2
    revised['A'] = writer.dump_verified(project.roots['A'], project.versions['A'])
    zone = [model_id(first), model_id(last)]

    with pytest.raises(ValueError, match='requires explicit local review'):
        transform(revised, paths, catalog, 'A', operation, courses=course_catalog())
    approved_routes = [{**row, 'preserve_local_protection': True, 'expected_local_slow_zone_end_ids': zone}
                       if row['route']['document'] == 'A' else row for row in operation['routes']]
    output, report = transform(revised, paths, catalog, 'A', {**operation, 'routes': approved_routes},
                               courses=course_catalog())
    after = project_from(output, paths, catalog)
    saved = after.owned(owner, 'OTRoute', identity)
    protection = _route_profile(saved)
    assert protection['slow_speed_zone_end_ids'] == zone
    assert protection['slow_speed_only_for_head'] and protection['signal_aspects'] == [4]
    assert protection == report['rewritten_routes'][0]['retained_protection']
    wrong = [{**row, 'expected_local_slow_zone_end_ids': zone[::-1]} if row['route']['document'] == 'A' else row
             for row in approved_routes]
    with pytest.raises(ValueError, match='exactly match both Ends'):
        transform(revised, paths, catalog, 'A', {**operation, 'routes': wrong}, courses=course_catalog())


def test_explicit_whole_path_speed_extension_checks_bound_selection_target_and_speed(chain):
    documents, paths, catalog, path_refs, operation = chain
    courses = course_catalog(path_refs['A'])
    run = (b'Start Day Offset#0#\nStart Time#08:00:00#\nStop Day Offset#0#\n'
           b'Stop Time#09:00:00#\n')
    request = {'event': 'Slow', 'path': path_refs['A'], 'expected_speed_kmh': 40}
    selected = {**operation, 'path_speed_event_extensions': [request]}
    with pytest.raises(ValueError, match='enabled run-selected'):
        transform(documents, paths, catalog, 'A', selected, courses=courses, run_bytes=run)
    enabled = run + b'Incident#Slow#\n'
    output, report = transform(documents, paths, catalog, 'A', selected, courses=courses, run_bytes=enabled)
    assert output.keys() == documents.keys()
    receipt, = report['extended_path_speed_events']
    assert receipt['path'] == path_refs['A'] and receipt['stored_event_unchanged']
    assert receipt['extends_over_inserted_track'] and receipt['reduced_speed_kmh'] == 40
    wrong_speed = {**selected, 'path_speed_event_extensions': [{**request, 'expected_speed_kmh': 50}]}
    with pytest.raises(ValueError, match='fixed-speed'):
        transform(documents, paths, catalog, 'A', wrong_speed, courses=courses, run_bytes=enabled)


def test_splits_original_crossing_slow_zone_at_the_reviewed_native_signal(chain):
    documents, paths, catalog, _, operation = chain
    project = project_from(documents, paths, catalog)
    original = next(row for row in project.continuations if row['source_document'] == 'A')
    route = original['route']
    identity = route['name'], route['array_id'], route['start_id']
    owner = 'A', route['start_id']
    receiver = 'B', original['target_connector']
    updated, _ = append_route_aspects(documents, paths, catalog, [owner],
                                      [{'start_end': owner, 'speeds_kmh': [40]}])
    documents = {**documents, **updated}
    project = project_from(documents, paths, catalog)
    primary = project.owned(owner, 'OTRoute', identity)
    terminal = project.owned(receiver, 'OTRoute', identity)
    finish = project.route_view(terminal)[-1]
    holder = primary.contents[4].value
    aspect, = [item for item in route_factory.wrapper(holder, 'OTSigIndList') if item.contents[0].value == 4]
    writer.set_elements(holder.contents[0].value, [aspect])
    primary.contents[11].value = 2
    primary.contents[12].values[1:] = [project.model(owner), None]
    terminal.contents[12].values[1:] = [None, project.model(finish)]
    documents.update({key: writer.dump_verified(project.roots[key], project.versions[key]) for key in ('A', 'B')})

    with pytest.raises(ValueError, match='requires explicit local review'):
        transform(documents, paths, catalog, 'A', operation, courses=course_catalog())
    approval = {'start': end(*owner), 'finish': end(*finish), 'expected_speed_kmh': 40}
    plans = [{**item, 'preserve_local_protection': True, 'expected_cross_document_slow_zone': approval}
             if item['route']['document'] == 'A' else item for item in operation['routes']]
    edited, result = transform(documents, paths, catalog, 'A', {**operation, 'routes': plans}, courses=course_catalog())
    saved = project_from(edited, paths, catalog)
    record = next(row for row in result['rewritten_routes'] if row['retained_owner'] == owner)
    zone = record['split_cross_document_slow_zone']
    relay = zone['split']
    authored = record['added_route']
    incoming = saved.block_end(('A', original['source_connector']))
    assert _stored_zone(saved, saved.owned(owner, 'OTRoute', identity)) == (owner, None)
    assert _stored_zone(saved, saved.owned(incoming, 'OTRoute', identity)) == (None, relay)
    assert _stored_zone(saved, saved.owned(relay, 'OTRoute', authored)) == (relay, None)
    assert _stored_zone(saved, saved.owned(receiver, 'OTRoute', authored)) == (None, finish)
    signal = saved.model(relay).contents[11].value
    assert [ind.contents[0].value for ind in route_factory.wrapper(signal.contents[10].value, 'OTSigIndList')] == [0, 4]
    assert record['middle_exit_protection']['signal_aspects'] == [4]
    assert record['middle_exit_protection']['slow_speed_only_for_head']
    wrong = [{**item, 'expected_cross_document_slow_zone': {**approval, 'expected_speed_kmh': 50}}
             if item['route']['document'] == 'A' else item for item in plans]
    with pytest.raises(ValueError, match='differs from the original aspect'):
        transform(documents, paths, catalog, 'A', {**operation, 'routes': wrong}, courses=course_catalog())


def test_creates_and_transfers_overlap_at_original_expanded_terminal(chain):
    documents, paths, catalog, _, operation = chain
    project = project_from(documents, paths, catalog)
    forward = next(row for row in project.continuations if row['source_document'] == 'A')
    reference = {'document': 'A', **forward['route']}
    identity = reference['name'], reference['array_id'], reference['start_id']
    owner = 'A', reference['start_id']
    route = project.owned(owner, 'OTRoute', identity)
    terminal = project.route_view(route)[-1]
    shapes = shapes_for(documents['B'])
    added, vertex = transform(documents, paths, catalog, 'B',
                              {'action': 'insert_vertex', 'x': 300, 'y': 30,
                               'orientation': 'horizontal', 'names': ['', '']}, shapes=shapes)
    prepared = {**documents, **added}
    arrival = vertex['added_vertex_end_ids'][0]
    added, track = transform(prepared, paths, catalog, 'B', {
        'action': 'insert_edge', 'end_ids': [project.related(terminal)[1], arrival],
        'length_m': 200, 'radius_m': 0, 'gradient_per_mille': 0, 'rack_rail': False,
        'remark': '', 'track_name': 'Overlap', 'line_name': 'B', 'allow_safety_regroup': False,
        'speeds': [{'train_type': '0', 'speed12_kmh': 60, 'speed21_kmh': 60}],
    }, shapes=shapes)
    prepared.update(added)
    binding = {'action': 'bind_cross_document_terminal_overlap', 'route': reference, 'create_overlap': {
        'document': 'B', 'name': 'TerminalRunout', 'end_ids': [terminal[1], arrival],
        'edge_ids': [track['edge_id']], 'speed_kmh': 30, 'release_time_s': 35, 'reservation_time_s': 0,
    }}
    values = course_catalog()
    edits, bound = transform(prepared, paths, catalog, 'A', binding, courses=values)
    assert bound['created_overlap'] and sorted(edits) == ['A', 'B']
    prepared.update(edits)
    resources = bound['terminal_overlap']
    assert resources['shunting']['document'] == 'B' and resources['edge_ids'] == [track['edge_id']]
    assert resources['release_time_s'] == 35
    with pytest.raises(ValueError, match='explicit terminal review'):
        transform(prepared, paths, catalog, 'A', operation, courses=values)
    approval = {'shunting': resources['shunting'], 'edge_ids': resources['edge_ids']}
    forward_plans = [{**row, 'preserve_local_protection': True, 'expected_terminal_overlap': approval}
                     if row['route']['document'] == 'A' else row for row in operation['routes']]
    writes, report = transform(prepared, paths, catalog, 'A', {**operation, 'routes': forward_plans}, courses=values)
    installed = project_from(writes, paths, catalog)
    shifted = next(row for row in report['rewritten_routes'] if row['retained_owner'] == owner)
    assert shifted['transferred_terminal_overlap'] == resources
    assert overlap_reference(installed.owned(owner, 'OTRoute', identity)) == ('', -1)
    receiver = ('B', forward['target_connector'])
    assert overlap_reference(installed.owned(receiver, 'OTRoute', shifted['added_route'])) == ('', -1)
    successor = installed.owned(shifted['intermediate_owner'], 'OTRoute', shifted['added_route'])
    assert overlap_reference(successor) == ('TerminalRunout', terminal[1])
    assert installed.route_view(successor)[-1] == terminal
    assert installed.shunting_movements[terminal, 'TerminalRunout'] == (terminal, ('B', arrival))
