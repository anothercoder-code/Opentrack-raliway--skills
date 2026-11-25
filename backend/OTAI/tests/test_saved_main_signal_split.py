"""Regressions for putting a native signal inside a saved local or continued Route."""

import pytest

from opentrack_ai.current_archive import catalogs, course_factories, path_functions, route_factory, writer
from opentrack_ai.current_archive.current_shunting_workflow.core import build_shunting_path
from opentrack_ai.current_archive.multi_document import generate, operations
from opentrack_ai.current_archive.multi_document.core import ident, sha
from opentrack_ai.current_archive.network_operating_plan import route_trace
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.saved_main_signal_create import create_saved_main_signal
from opentrack_ai.current_archive.saved_main_signal_split import _saved_part, insert_signal_in_saved_route
from opentrack_ai.current_archive.saved_terminal_overlap import overlap_reference, set_overlap_reference
from opentrack_ai.current_archive.saved_timing_signal_split import DEFAULT_ROUTE_TIMING, release_keys, stored_route_timing, timing_groups
from opentrack_ai.current_archive.signal_operating_fields import _append_indications
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_course_formation_rebind import formation_source
from test_itinerary_lifecycle import course_archive
from test_itinerary_native_edit import schematic_document
from test_saved_main_signal_location import corridor


@pytest.fixture(scope='module')
def occupied_corridor():
    docs, paths, dest, keys = corridor()
    baseline = project_from(docs, paths, dest)
    routes = {ident(row)[0]: row for row in baseline.routes}
    source = routes['Approach']
    native_courses, version = writer.load_next_compatible(course_archive(C01=['Through'], N01=['FromSignal']))
    for item in catalogs.course_items(native_courses):
        item.contents[5].value = 1
    courses = writer.dump_verified(native_courses, version)
    end = keys['B']
    operation = {'action': 'create_main_signal', 'end_id': end[1], 'signal_name': 'NEW BLOCK', 'main_role': 'block',
                 'placement': {'x': 150, 'y': 30, 'angle': 0, 'alignment_x': 1, 'alignment_y': 0},
                 'sight_m': 500, 'delay_s': 0, 'show_symbol': True, 'show_icon': True,
                 'split_route': {'route': {'document': 'Line', 'name': 'Approach', 'array_id': ident(source)[1],
                                           'start_id': keys['A'][1]}, 'continued_name': 'Approach Relay',
                                 'expected_upstream_edge_ids': [baseline.edge_between(keys['A'], end)[1]],
                                 'expected_downstream_edge_ids': [baseline.edge_between(end, keys['C'])[1]],
                                 'reserve_with_previous': False}}
    return docs, paths, dest, keys, baseline, courses, operation


@pytest.mark.parametrize('reservation', [False, True])
def test_split_adds_one_signal_preserves_route_identity_and_keeps_complete_native_movements(occupied_corridor, reservation):
    docs, paths, dest, keys, baseline, courses, op = occupied_corridor
    request = {**op, 'split_route': {**op['split_route'], 'reserve_with_previous': reservation}}
    with pytest.raises(ValueError, match='needs a joint signal and Route edit'):
        create_saved_main_signal(docs, paths, dest, 'Line', request, courses)
    saved, report = insert_signal_in_saved_route(docs, paths, dest, 'Line', request, courses)
    fresh = project_from(saved, paths, dest)
    assert saved.keys() == {'Line'} and report['destination_catalog_unchanged']
    assert report['active_courses'] == ['C01'] and report['affected_itineraries'] == ['Through']
    original = [row for row in baseline.routes if ident(row)[0] == 'Approach'][0]
    routes = {ident(row)[0]: row for row in fresh.routes}
    assert ident(routes['Approach']) == ident(original)
    assert ident(routes['Approach Relay']) == ('Approach Relay', 0, keys['B'][1])
    for name, sequence, reserve in (('Approach', 'AB', False), ('Approach Relay', 'BC', reservation)):
        route = routes[name]
        nodes = [keys[item] for item in sequence]
        assert fresh.route_view(route) == nodes
        assert [fresh.key(item) for item in path_functions.mutable_array(route.contents[12].values[0])] == nodes
        assert route.contents[5].values == [0, 400, 5, 0, -1, 0]
        assert route.contents[6].values == [0, 40, 0] and route.contents[8].values == [0, 0]
        assert route.contents[11].value == int(reserve)
    end = fresh.model(keys['B'])
    signal = end.contents[11].value
    assert end.contents[20].value == 1 and signal.contents[0].value == report['signal_id']
    assert signal.contents[7].value is end and signal.contents[8].values[1] == 3
    old_paths = {ident(item)[0]: baseline.path_view(item) for item in baseline.paths_objects}
    new_paths = {ident(item)[0]: fresh.path_view(item) for item in fresh.paths_objects}
    assert old_paths['P:Departure'] == new_paths['P:Departure']
    assert [row[1]['name'] for row in new_paths['P:Approach'][1]] == ['Approach', 'Approach Relay']
    assert old_paths['P:Approach'][0] == new_paths['P:Approach'][0]
    assert {ident(item): baseline.dest_view(item) for item in baseline.dests} == {
        ident(item): fresh.dest_view(item) for item in fresh.dests}


def test_rejects_mismatched_edges_and_busy_internal_direction(occupied_corridor):
    docs, paths, dest, keys, _, courses, original = occupied_corridor
    wrong = {**original, 'split_route': {**original['split_route'], 'expected_upstream_edge_ids': [9999]}}
    with pytest.raises(ValueError, match='ordered directed Edge sequences'):
        insert_signal_in_saved_route(docs, paths, dest, 'Line', wrong, courses)
    overlapping, _ = native.build_route(docs['Line'], name='Competing Route',
        end_ids=[keys[token][1] for token in 'ABC'], description='', release_groups='global', reserve_previous=False)
    with pytest.raises(ValueError, match='Another saved Route or Shunting'):
        insert_signal_in_saved_route({'Line': overlapping}, paths, dest, 'Line', original, courses)


def test_rejects_nondefault_approach_and_route_speed_incident(occupied_corridor):
    docs, paths, dest, keys, _, courses, op = occupied_corridor
    root, version = writer.load_next_compatible(docs['Line'])
    stored = next(row for row in writer.objects(root) if writer.kind(row) == 'OTRoute' and ident(row)[0] == 'Approach')
    stored.contents[8].values[:] = [100.0, 25.0]
    with pytest.raises(ValueError, match='default reservation'):
        insert_signal_in_saved_route({'Line': writer.dump_verified(root, version)}, paths, dest, 'Line', op, courses)
    incidents, version = writer.load_next_compatible(courses)
    incident = native.obj([('OTIncident', 9), ('NSObject', 0)], [
        ('i', [17]), ('@', [native.string('Selected Route restriction')]), ('@', [native.string('Line')]),
        ('i', [0]), ('i', [0]), ('iii', [0, keys['A'][1], 4]),
    ])
    writer.set_elements(incidents.contents[1].value, [incident])
    with pytest.raises(ValueError, match='Route-speed Incident'):
        insert_signal_in_saved_route(docs, paths, dest, 'Line', op, writer.dump_verified(incidents, version))


def station_corridor(*, reverse, station_signs=('W', 'P', 'E'), edge_length=100):
    spec = generate.spec()
    spec['vertices'] = [generate.vertex(label, 100 * (index + 1)) for index, label in enumerate('ABCDEFG')]
    template, = spec['edges']
    spec['edges'] = [{**template, 'key': a + b, 'from': [a, 1], 'to': [b, 0], 'length_m': edge_length}
                     for a, b in zip('ABCDEF', 'BCDEFG', strict=True)]
    signal_ends = [(name, 0) for name in 'ACG'] + ([(name, 1) for name in 'GC'] if reverse else [])
    document, ends = schematic_document(spec, signal_ends)
    root, version = writer.load_next_compatible(document)
    models, by_id = route_factory.document(root)
    added = []
    for sign, limits in zip(station_signs, ('A', 'CBDE', 'GF'), strict=True):
        group = native.obj([('OTStationModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], [
            ('i', [max(by_id) + 1 + len(added)]), ('f', [0.0]), ('f', [100.0]), ('f', [50.0]), ('i', [0]), ('i', [0]),
            ('@', [None]), ('@', [native.string(sign)]), ('ii', [2, 4]), ('ii', [1, 0]),
        ])
        for index, label in enumerate(limits):
            for number in ends[label]:
                end = by_id[number]
                end.contents[12].value = group
                end.contents[20].value = 2 if index == 0 else 1
        added.append(group)
    writer.set_elements(root.contents[2].value, [*models, *added])
    docs, paths = {'Line': writer.dump_verified(root, version)}, {'Line': 'Line.opentrack'}
    dest = writer.dump_verified(generate.wrapped('OTDestInfoList', []))

    def dependencies():
        return {'document_paths': paths, 'complete_document_set': True,
                'expected_hashes': {'Line': sha(docs['Line']), '$dest_catalog': sha(dest)}}

    movements = [('Approach P', 'ABC', 0), ('Depart P', 'CDEFG', 0)]
    if reverse:
        movements.append(('Back to P', 'GFEDC', 1))
    saved_paths = []
    for name, keys, direction in movements:
        docs['Line'], route = native.build_route(docs['Line'], name=name, description='',
            end_ids=[ends[key][direction] for key in keys], release_groups='global', reserve_previous=False)
        docs, report = operations.create_path(docs, dest, name=f'P {name}', routes=[{
            'document': 'Line', 'name': name, 'array_id': route['array_id'], 'start_id': route['start_id'],
        }], **dependencies())
        saved_paths.append(report['created'])
    for name, use in [('Through', saved_paths[:2]), *([('Dormant reverse', saved_paths[2:])] if reverse else [])]:
        built, _ = operations.create_itinerary(docs, dest, name=name, paths=use, **dependencies())
        docs, dest = built['documents'], built['catalog']
    original = project_from(docs, paths, dest)
    new_point = 'Line', ends['D'][0]
    route_sequence = [('Line', ends[name][0]) for name in 'CDEFG']
    edge_ids = [original.edge_between(a, b)[1] for a, b in zip(route_sequence, route_sequence[1:])]
    op = {'action': 'create_main_signal', 'end_id': new_point[1], 'signal_name': 'NEW STATION BLOCK', 'main_role': 'block',
          'placement': generate.signal_placement(original.model(new_point), 400, 30),
          'sight_m': 500, 'delay_s': 0, 'show_symbol': True, 'show_icon': True, 'split_route': {
              'route': {'document': 'Line', 'name': 'Depart P', 'array_id': 0, 'start_id': ends['C'][0]},
              'continued_name': 'Depart P Relay', 'expected_upstream_edge_ids': edge_ids[:1],
              'expected_downstream_edge_ids': edge_ids[1:], 'reserve_with_previous': False,
          }}
    return docs, paths, dest, original, op


def test_station_area_split_keeps_complete_cold_stopping_profiles():
    docs, paths, dest, original, op = station_corridor(reverse=False)
    saved, result = insert_signal_in_saved_route(docs, paths, dest, 'Line', op, course_archive(C01=['Through']))
    fresh = project_from(saved, paths, dest)
    a, = original.dests
    b, = fresh.dests
    assert route_trace(original, a) == route_trace(fresh, b)
    assert [row['stopping_area_length_m'] for row in route_trace(fresh, b)['visits']] == [None, 100, 100]
    assert result['station_berths_preserved']['station_sign'] == 'P'
    assert result['station_berths_preserved']['both_directions_checked']


def test_station_area_split_rejects_shortening_an_unassigned_opposite_direction_berth():
    docs, paths, dest, original, op = station_corridor(reverse=True)
    reverse, = [row for row in original.dests if ident(row)[0] == 'Dormant reverse']
    assert route_trace(original, reverse)['visits'][-1]['stopping_area_length_m'] == 200
    with pytest.raises(ValueError, match='stopping profile in Itinerary Dormant reverse'):
        insert_signal_in_saved_route(docs, paths, dest, 'Line', op, course_archive(C01=['Through']))


@pytest.fixture(scope='module')
def receiving_corridor():
    paths = {name: f'OTDocuments/{name}.opentrack' for name in 'AB'}
    a, _ = schematic_document(generate.spec(), [('left', 0), ('left', 1)])
    layout = generate.spec()
    labels = ('left', 'join', 'split', 'interior', 'right', 'runout')
    layout['vertices'] = [generate.vertex(label, 100 * (index + 1)) for index, label in enumerate(labels)]
    basis, = layout['edges']
    layout['edges'] = [{**basis, 'key': right, 'from': [left, 1], 'to': [right, 0]}
                       for left, right in zip(labels[:-1], labels[1:], strict=True)]
    b, ends = schematic_document(layout, [('join', 0), ('join', 1), ('right', 0)])
    docs, dest, _ = generate.make_pair({'A': a, 'B': b}, paths)
    root, version = writer.load_next_compatible(docs['B'])
    models, by_id = route_factory.document(root)
    middle = [by_id[ends[label][0]] for label in labels[1:-1]]
    old_boundary_signal = middle[0].contents[11].value
    middle[0].contents[11].value = None
    writer.set_elements(root.contents[2].value, [item for item in models if item is not old_boundary_signal])
    fragment, = route_factory.wrapper(by_id[0].contents[15].value, 'OTRouteList')
    fragment.contents[0].value = path_functions.array_like(fragment.contents[0].value, middle)
    fragment.contents[12].values[0] = path_functions.array_like(fragment.contents[12].values[0], middle)
    docs['B'] = writer.dump_verified(root, version)
    graph = project_from(docs, paths, dest)
    split = 'B', ends['split'][0]
    main = graph.owned(('A', 0), 'OTRoute', ('R:A-B', 0, 0))
    nodes = graph.route_view(main)
    index = nodes.index(split)
    edges = [graph.edge_between(x, y)[1] for x, y in zip(nodes, nodes[1:])]
    op = {'action': 'create_main_signal', 'end_id': split[1], 'signal_name': 'RECEIVING BLOCK', 'main_role': 'block',
          'placement': generate.signal_placement(graph.model(split), 300, 30),
          'sight_m': 500, 'delay_s': 0, 'show_symbol': True, 'show_icon': True, 'split_route': {
              'route': {'document': 'A', 'name': 'R:A-B', 'array_id': 0, 'start_id': 0},
              'continued_name': 'Receiving relay', 'expected_upstream_edge_ids': edges[:index],
              'expected_downstream_edge_ids': edges[index:], 'reserve_with_previous': True,
          }}
    return docs, paths, dest, graph, op, nodes, index


def test_split_only_changes_the_receiving_fragment_and_inserts_a_well_bound_local_route(receiving_corridor):
    docs, paths, dest, old, op, nodes, index = receiving_corridor
    changed, report = insert_signal_in_saved_route(docs, paths, dest, 'B', op, course_archive(C01=['I:A-B']))
    fresh = project_from({**docs, **changed}, paths, dest)
    primary_id = ('R:A-B', 0, 0)
    assert _saved_part(old, old.owned(('A', 0), 'OTRoute', primary_id)) == _saved_part(
        fresh, fresh.owned(('A', 0), 'OTRoute', primary_id))
    assert fresh.block_end(('A', 5)) == old.block_end(('A', 5)) == ('B', 0)
    split = nodes[index]
    fragment = fresh.owned(('B', 0), 'OTRoute', primary_id)
    downstream = fresh.owned(split, 'OTRoute', ('Receiving relay', 0, split[1]))
    assert fresh.route_view(fragment) == nodes[2:index + 1]
    assert fresh.route_view(downstream) == nodes[index:]
    assert [fresh.key(item) for item in path_functions.mutable_array(fragment.contents[12].values[0])] == nodes[2:index + 1]
    assert [fresh.key(item) for item in path_functions.mutable_array(downstream.contents[12].values[0])] == nodes[index:]
    assert downstream.contents[11].value == 1
    assert report['receiving_fragment']['sending_primary_preserved'] and report['receiving_fragment']['continuation_index'] == 2
    assert report['upstream_route']['document'] == 'A' and report['downstream_route']['document'] == 'B'
    assert report['receiving_fragment']['old_end_ids'] == [key[1] for key in nodes[2:]]
    assert report['receiving_fragment']['new_end_ids'] == [key[1] for key in nodes[2:index + 1]]
    path = fresh.owned(('A', 0), 'OTPath', ('P:A-B', 1, 0))
    assert fresh.path_view(path) == (nodes, [('A', ref_record(primary_id)), ('B', ref_record(ident(downstream)))])
    assert {ident(item): old.dest_view(item) for item in old.dests} == {ident(item): fresh.dest_view(item) for item in fresh.dests}


def ref_record(identity):
    return dict(zip(('name', 'array_id', 'start_id'), identity, strict=True))


def test_receiving_split_cannot_use_the_connector_or_the_receiving_terminal(receiving_corridor):
    docs, paths, dest, _, op, nodes, _ = receiving_corridor
    courses = course_archive(C01=['I:A-B'])
    with pytest.raises(ValueError, match='strictly internal to the original movement'):
        insert_signal_in_saved_route(docs, paths, dest, 'A', {**op, 'end_id': nodes[1][1]}, courses)
    with pytest.raises(ValueError, match='strictly internal to the original movement'):
        insert_signal_in_saved_route(docs, paths, dest, 'B', {**op, 'end_id': nodes[-1][1]}, courses)


@pytest.fixture(scope='module')
def sending_corridor():
    paths = {name: f'OTDocuments/{name}.opentrack' for name in 'AB'}
    spec = generate.spec()
    spec['vertices'] = [generate.vertex(name, 100 * (index + 1)) for index, name in enumerate('LMNR')]
    basis, = spec['edges']
    spec['edges'] = [{**basis, 'key': left + right, 'from': [left, 1], 'to': [right, 0]}
                     for left, right in ('LM', 'MN', 'NR')]
    a, a_ids = schematic_document(spec, [('L', 0)])
    remote = generate.spec()
    remote['vertices'].append(generate.vertex('runout', 330))
    remote['edges'].append({**remote['edges'][0], 'key': 'tail', 'from': ['right', 1], 'to': ['runout', 0]})
    b, b_ids = schematic_document(remote, [('right', 0)])
    roots, versions, models = {}, {}, {}
    for sheet, source in (('A', a), ('B', b)):
        roots[sheet], versions[sheet] = writer.load_next_compatible(source)
        _, models[sheet] = route_factory.document(roots[sheet])
    connectors = {'A': a_ids['R'][1], 'B': b_ids['left'][0]}
    for sheet, other in (('A', 'B'), ('B', 'A')):
        connector = models[sheet][connectors[sheet]]
        connector.clazz = writer.Class(b'OTConnModel', 1, connector.clazz)
        connector.contents.extend([writer.TypedValue(b'@', native.string('')),
            writer.TypedValue(b'@', native.string(other)), writer.TypedValue(b'i', connectors[other]),
            writer.TypedValue(b'i', 0)])
    local = [models['A'][a_ids[name][0]] for name in 'LMNR']
    inbound = models['B'][b_ids['right'][0]]
    primary_id = ('R:A-B', 0, a_ids['L'][0])
    primary = generate.route(*primary_id, local, len(local))
    primary.contents[12].values[0] = native.arr(local[:-1])
    fragment = generate.route(*primary_id, [inbound], -1, fragment=True)
    fragment.contents[12].values[0] = native.arr([inbound])
    for owner, route in ((local[0], primary), (models['B'][connectors['B']], fragment)):
        writer.set_elements(owner.contents[15].value.contents[0].value, [route])
    local[0].contents[19].value = 0
    documents = {name: writer.dump_verified(root, versions[name]) for name, root in roots.items()}
    dest = writer.dump_verified(generate.wrapped('OTDestInfoList', []))

    def bindings():
        return {'document_paths': paths, 'complete_document_set': True,
                'expected_hashes': {**{name: sha(blob) for name, blob in documents.items()}, '$dest_catalog': sha(dest)}}

    reference = {'document': 'A', **ref_record(primary_id)}
    documents, report = operations.create_path(documents, dest, name='P:A-B', routes=[reference], **bindings())
    files, _ = operations.create_itinerary(documents, dest, name='I:A-B', paths=[report['created']], **bindings())
    documents, dest = files['documents'], files['catalog']
    graph = project_from(documents, paths, dest)
    primary = graph.owned(('A', primary_id[2]), 'OTRoute', primary_id)
    nodes = graph.route_view(primary)
    split = nodes[1]
    edges = [graph.edge_between(first, second)[1] for first, second in zip(nodes, nodes[1:])]
    op = {'action': 'create_main_signal', 'end_id': split[1], 'signal_name': 'SENDING BLOCK', 'main_role': 'block',
          'placement': generate.signal_placement(graph.model(split), 200, 30),
          'sight_m': 500, 'delay_s': 0, 'show_symbol': True, 'show_icon': True,
          'split_route': {'route': reference, 'continued_name': 'Sending relay', 'expected_upstream_edge_ids': edges[:1],
                          'expected_downstream_edge_ids': edges[1:], 'reserve_with_previous': True}}
    return documents, paths, dest, graph, op


def test_sending_split_shortens_primary_and_rekeys_the_same_receiving_fragment(sending_corridor):
    docs, paths, dest, old, op = sending_corridor
    previous, = old.continuations
    owner = 'A', previous['route']['start_id']
    receiver_owner = 'B', previous['target_connector']
    old_identity = ('R:A-B', 0, owner[1])
    receiving_before = _saved_part(old, old.owned(receiver_owner, 'OTRoute', old_identity))
    nodes = old.route_view(old.owned(owner, 'OTRoute', old_identity))
    changed, report = insert_signal_in_saved_route(docs, paths, dest, 'A', op, course_archive(C01=['I:A-B']))
    fresh = project_from({**docs, **changed}, paths, dest)
    assert changed.keys() == {'A', 'B'}
    identity = ('Sending relay', 0, nodes[1][1])
    upstream = fresh.owned(owner, 'OTRoute', old_identity)
    downstream = fresh.owned(nodes[1], 'OTRoute', identity)
    assert upstream.contents[5].values[4] == -1 and fresh.route_view(upstream) == nodes[:2]
    assert downstream.contents[5].values[4] == 3 and fresh.route_view(downstream) == nodes[1:]
    assert upstream.contents[11].value == 0 and downstream.contents[11].value == 1
    assert _saved_part(fresh, fresh.owned(receiver_owner, 'OTRoute', identity)) == {
        **receiving_before, 'identity': identity}
    assert report['release_group_end_ids'] == {'upstream': [key[1] for key in nodes[:2]],
                                               'downstream': [key[1] for key in (*nodes[1:3], nodes[-1])]}
    rebound, = fresh.continuations
    assert fresh.block_end(('A', previous['source_connector'])) == receiver_owner
    assert rebound['source_connector'] == previous['source_connector']
    assert rebound['remote_end_ids'] == previous['remote_end_ids']
    assert report['sending_fragment'] == {'previous_continuation_index': 4, 'upstream_continuation_index': -1,
        'downstream_continuation_index': 3, 'source_connector_end_id': previous['source_connector'],
        'receiving_document': 'B', 'receiving_connector_end_id': receiver_owner[1],
        'receiving_end_ids': [nodes[-1][1]], 'receiving_release_group_end_ids': [nodes[-1][1]],
        'previous_receiving_route': ref_record(old_identity), 'replacement_receiving_route': ref_record(identity)}
    old_path, = old.paths_objects
    first, = fresh.paths_objects
    assert ident(first) == ident(old_path)
    assert fresh.path_view(first) == (nodes, [('A', ref_record(old_identity)), ('A', ref_record(identity))])


@pytest.mark.parametrize('replacement', [False, True])
def test_sending_split_rejects_route_incidents_on_either_receiving_identity(sending_corridor, replacement):
    docs, paths, dest, old, op = sending_corridor
    courses, version = writer.load_next_compatible(course_archive(C01=['I:A-B']))
    start_id = op['end_id'] if replacement else op['split_route']['route']['start_id']
    incident = native.obj([('OTIncident', 9), ('NSObject', 0)], [
        ('i', [17]), ('@', [native.string('Receiving Route restriction')]), ('@', [native.string('B')]),
        ('i', [0]), ('i', [0]), ('iii', [0, start_id, 4]),
    ])
    writer.set_elements(courses.contents[1].value, [incident])
    with pytest.raises(ValueError, match='Route-speed Incident'):
        insert_signal_in_saved_route(docs, paths, dest, 'A', op, writer.dump_verified(courses, version))


def _with_overlap(docs, paths, dest, operation, *, implicit=False, lock_conflict=False, linked_successor=False,
                  duplicate_shunting=False):
    project = project_from(docs, paths, dest)
    selected = operation['split_route']['route']
    source = selected['document']
    route = project.owned((source, selected['start_id']), 'OTRoute',
                          (selected['name'], selected['array_id'], selected['start_id']))
    sequence = project.route_view(route)
    terminal = sequence[-1]
    trail = project.model(terminal)
    departure = project.model(project.actual_related(terminal))
    edge = departure.contents[9].value
    runout, = [obj for obj in (edge.contents[7].value, edge.contents[8].value) if obj is not departure]
    identity = trail.contents[19].value + 1
    name = 'Terminal run-out'
    spec = {
        'name': name, 'description': '', 'end_ids': [terminal[1], project.key(runout)[1]],
        'speed_kmh': 30, 'release_time_s': 35, 'reservation_time_s': 0,
    }
    shunting = build_shunting_path([trail, runout], identity, spec)
    shuntings = [shunting]
    if duplicate_shunting:
        shuntings.insert(0, build_shunting_path([trail, runout], identity + 1, {**spec, 'release_time_s': 40}))
    writer.set_elements(trail.contents[16].value.contents[0].value, shuntings)
    trail.contents[19].value = identity + int(duplicate_shunting)
    set_overlap_reference(route, (name, -1 if implicit else terminal[1]))
    if lock_conflict:
        original_first_edge = project.model(project.edge_between(sequence[0], sequence[1]))
        original_first_edge.contents[13].value = edge
        edge.contents[14].value = original_first_edge
    if linked_successor:
        following, = route_factory.wrapper(trail.contents[15].value, 'OTRouteList')
        following.contents[11].value = 1
    updated = {doc: writer.dump_verified(project.roots[doc], project.versions[doc])
               for doc in {source, terminal[0]}}
    approval = {'shunting': {'document': terminal[0], **ref_record(ident(shunting))},
                'edge_ids': [project.key(edge)[1]]}
    return {**docs, **updated}, approval


def _review_overlap(operation, approval, *, synchronized=True):
    return {**operation, 'split_route': {**operation['split_route'],
                                         'reserve_with_previous': synchronized, 'terminal_overlap': approval}}


@pytest.mark.parametrize(('fixture', 'target', 'implicit'), [
    ('occupied_corridor', 'Line', False),
    ('receiving_corridor', 'B', True),
    ('sending_corridor', 'A', False),
])
def test_terminal_overlap_moves_to_only_the_effective_suffix(request, fixture, target, implicit):
    case = request.getfixturevalue(fixture)
    docs, paths, dest = case[:3]
    operation = case[-1] if fixture != 'receiving_corridor' else case[4]
    courses = case[-2] if fixture == 'occupied_corridor' else course_archive(C01=['I:A-B'])
    docs, approval = _with_overlap(docs, paths, dest, operation, implicit=implicit)
    before = project_from(docs, paths, dest)
    changed, report = insert_signal_in_saved_route(docs, paths, dest, target, _review_overlap(operation, approval), courses)
    fresh = project_from({**docs, **changed}, paths, dest)
    assert changed.keys() == ({'Line'} if target == 'Line' else {'A', 'B'})
    upstream, downstream = [fresh.owned((ref['document'], ref['start_id']), 'OTRoute',
                                        (ref['name'], ref['array_id'], ref['start_id']))
                            for ref in (report['upstream_route'], report['downstream_route'])]
    binding = (approval['shunting']['name'], -1 if implicit else approval['shunting']['start_id'])
    assert overlap_reference(upstream) == ('', -1)
    assert overlap_reference(downstream) == binding
    assert downstream.contents[11].value == 1
    assert [route for route in fresh.routes if overlap_reference(route) != ('', -1)] == [downstream]
    assert fresh.shunting_movements == before.shunting_movements
    assert report['terminal_overlap_transfer']['edge_ids'] == approval['edge_ids']
    assert report['terminal_overlap_transfer']['stored_reference'] == list(binding)
    assert report['terminal_overlap_transfer']['release_time_s'] == 35
    assert report['terminal_overlap_transfer']['synchronized_reservation']
    if fixture == 'receiving_corridor':
        assert report['receiving_fragment']['sending_primary_preserved'] is False


def test_terminal_overlap_requires_exact_review_and_the_last_synchronized_route(occupied_corridor):
    docs, paths, dest, _, _, courses, op = occupied_corridor
    with_overlap, approval = _with_overlap(docs, paths, dest, op)
    with pytest.raises(ValueError, match='explicitly reviewed terminal overlap'):
        insert_signal_in_saved_route(with_overlap, paths, dest, 'Line', op, courses)
    with pytest.raises(ValueError, match='synchronized downstream reservation'):
        insert_signal_in_saved_route(with_overlap, paths, dest, 'Line', _review_overlap(op, approval, synchronized=False), courses)
    wrong = {**approval, 'edge_ids': [9999]}
    with pytest.raises(ValueError, match='Reviewed overlap Edges'):
        insert_signal_in_saved_route(with_overlap, paths, dest, 'Line', _review_overlap(op, wrong), courses)
    subsequent_link, _ = _with_overlap(docs, paths, dest, op, linked_successor=True)
    with pytest.raises(ValueError, match='last Route in the synchronized reservation chain'):
        insert_signal_in_saved_route(subsequent_link, paths, dest, 'Line', _review_overlap(op, approval), courses)


def test_terminal_overlap_rejects_a_locking_conflict_with_the_upstream_movement(occupied_corridor):
    docs, paths, dest, _, _, courses, op = occupied_corridor
    conflict, approval = _with_overlap(docs, paths, dest, op, lock_conflict=True)
    with pytest.raises(ValueError, match='whole original Route share'):
        insert_signal_in_saved_route(conflict, paths, dest, 'Line', _review_overlap(op, approval), courses)


def test_terminal_overlap_rejects_a_same_name_at_the_native_owner_even_with_an_exact_array_id(receiving_corridor):
    docs, paths, dest, _, op, _, _ = receiving_corridor
    courses = course_archive(C01=['I:A-B'])
    ambiguous, approval = _with_overlap(docs, paths, dest, op, duplicate_shunting=True)
    with pytest.raises(ValueError, match='ambiguous Shunting name at its End'):
        insert_signal_in_saved_route(ambiguous, paths, dest, 'B', _review_overlap(op, approval), courses)


def _join_split_source(edge_length=100, *, extra_user=False, allow_signal=True):
    docs, paths, dest, graph, operation = station_corridor(
        reverse=False, station_signs=('EA', 'RDG', 'WB'), edge_length=edge_length)
    route = next(item for item in graph.routes if ident(item)[0] == 'Approach P')
    source, boundary, terminal = graph.route_view(route)
    entry = graph.model(source).contents[11].value
    if allow_signal:
        entry.contents[9].values[2] |= 1
    graph.model(terminal).contents[11].value.contents[8].values[1] = 4
    route.contents[6].values[:] = [3, 20., 0.]
    root = graph.roots['Line']
    docs['Line'] = writer.dump_verified(root, graph.versions['Line'])
    itinerary_paths = {ident(item)[0]: ident(item) for item in graph.paths_objects}
    for name, path in [('Join donor', 'P Approach P'), ('Other departure', 'P Depart P')]:
        updated, _ = operations.create_itinerary(docs, dest, name=name,
            paths=[{'document': 'Line', **ref_record(itinerary_paths[path])}],
            document_paths=paths, complete_document_set=True,
            expected_hashes={'Line': sha(docs['Line']), '$dest_catalog': sha(dest)})
        docs, dest = updated['documents'], updated['catalog']
    banks = formation_source()
    course_bank, course_version = writer.load_next_compatible(banks['courses'])
    first, second = catalogs.course_items(course_bank)
    extra_bank, _ = writer.load_next_compatible(course_archive(A03=['Through' if extra_user else 'Other departure']))
    unrelated, = catalogs.course_items(extra_bank)
    for course, label in ((first, 'Through'), (second, 'Join donor'),
                          (unrelated, 'Through' if extra_user else 'Other departure')):
        course.contents[2].value = native.arr([native.string(label)])
        course.contents[5].value = 1
    writer.set_elements(catalogs.course_array(course_bank), [first, second, unrelated])
    banks['courses'] = writer.dump_verified(course_bank, course_version)
    preceding, stop = graph.edge_between(source, boundary), graph.edge_between(boundary, terminal)
    protection = graph.model(stop).contents[7].value.contents[7].value
    review = {'terminal_end': {'document': 'Line', 'end_id': terminal[1]}, 'stop_edge_id': stop[1],
              'expected_speed_kmh': 20, 'expected_safety_element_id': graph.key(protection)[1],
              'receiver_course': 'A01', 'donor_course': 'A02', 'station_sign': 'RDG'}
    return docs, paths, dest, banks, {**operation, 'end_id': boundary[1], 'split_route': {
        'route': {'document': 'Line', **ref_record(ident(route))}, 'continued_name': 'Joined berth',
        'expected_upstream_edge_ids': [preceding[1]], 'expected_downstream_edge_ids': [stop[1]],
        'reserve_with_previous': False, 'occupied_entry': review,
    }}


def _join_split(case):
    docs, paths, dest, banks, op = case
    return insert_signal_in_saved_route(docs, paths, dest, 'Line', op, banks['courses'],
                                        operating_banks=banks, run_bytes=b'TrainType#main#\n')


def test_speed_occupied_entry_moves_only_to_the_local_join_suffix():
    case = _join_split_source()
    _, paths, dest, _, op = case
    changes, report = _join_split(case)
    fresh = project_from(changes, paths, dest)
    old, new = [fresh.owned((row['document'], row['start_id']), 'OTRoute',
                            (row['name'], row['array_id'], row['start_id']))
                for row in (report['upstream_route'], report['downstream_route'])]
    assert old.contents[6].values == [0, 40, 0] and new.contents[6].values == [3, 20, 0]
    assert fresh.model(fresh.owners[id(old)]).contents[11].value.contents[9].values[2] & 1
    new_signal = fresh.model(('Line', op['end_id'])).contents[11].value
    assert new_signal.contents[9].values[2] & 1 and new.contents[11].value == 0
    proof = report['occupied_entry_transfer']
    assert proof['receiver_length_m'] == proof['donor_length_m'] == 22
    assert proof['combined_length_m'] == 44
    assert proof['berth']['contact']['offset_m'] == 78 and proof['berth']['donor_tail']['offset_m'] == 56


@pytest.mark.parametrize(('kwargs', 'message'), [
    ({'edge_length': 44}, 'Both complete formations'),
    ({'allow_signal': False}, 'original entry Signal'),
    ({'extra_user': True}, 'only be used by the two reviewed enabled Courses'),
])
def test_speed_occupied_entry_requires_a_clear_complete_join_witness(kwargs, message):
    with pytest.raises(ValueError, match=message):
        _join_split(_join_split_source(**kwargs))


def _slow_zone_source(docs, paths, dest, target, operation, position, *, head_only=True, allow_track_speed=True):
    project = project_from(docs, paths, dest)
    ref = operation['split_route']['route']
    source = ref['document'], ref['start_id']
    primary = project.owned(source, 'OTRoute', (ref['name'], ref['array_id'], ref['start_id']))
    nodes = project.route_view(primary)
    cut = nodes.index((target, operation['end_id']))
    bounds = {
        'upstream': (nodes[0], nodes[cut]),
        'crossing': (nodes[0], nodes[-1]),
        'downstream': (nodes[cut], nodes[-1]),
    }[position]
    parts = {source[0]: primary}
    record = next((row for row in project.continuations if row['route'] == ref_record(ident(primary))), None)
    if record is not None:
        receiver = record['target_document'], record['target_connector']
        parts[receiver[0]] = project.owned(receiver, 'OTRoute', ident(primary))
    for slot, bound in enumerate(bounds, 1):
        parts[bound[0]].contents[12].values[slot] = project.model(bound)
    if bounds[-1][0] != source[0]:
        # An earlier saved primary end is only an archive handoff. The receiver overrides it.
        handoff = record['local_end_ids'][-1]
        primary.contents[12].values[2] = project.model((source[0], handoff))
    primary.contents[11].value = int(head_only) * 2
    route_ind, = route_factory.wrapper(primary.contents[4].value, 'OTSigIndList')
    route_ind.contents[0].value = 4
    owner = project.model(source)
    signal = owner.contents[11].value
    holder = signal.contents[10].value
    aspects = route_factory.wrapper(holder, 'OTSigIndList') if allow_track_speed else []
    signal.contents[10].value = _append_indications(holder, aspects, [4], owner)
    updated = {doc: writer.dump_verified(project.roots[doc], project.versions[doc]) for doc in parts}
    review = {side: {'document': key[0], 'end_id': key[1]} for side, key in zip(('start', 'finish'), bounds, strict=True)}
    review.update(expected_native_aspect_code=4, expected_speed_kmh=40, expected_head_only=head_only)
    request = {**operation, 'split_route': {**operation['split_route'], 'slow_zone': review}}
    return {**docs, **updated}, request, nodes, cut


@pytest.mark.parametrize('position', ['upstream', 'crossing', 'downstream'])
@pytest.mark.parametrize(('fixture', 'target', 'head_only'), [
    ('local', 'Line', True),
    ('sending_corridor', 'A', False),
    ('receiving_corridor', 'B', True),
])
def test_finite_slow_zone_rebinds_in_local_sending_and_receiving_splits(request, position, fixture, target, head_only):
    if fixture == 'local':
        docs, paths, dest, _, op = station_corridor(reverse=False)
        courses = course_archive(C01=['Through'])
    else:
        case = request.getfixturevalue(fixture)
        docs, paths, dest, _, op = case[:5]
        courses = course_archive(C01=['I:A-B'])
    protected, op, nodes, cut = _slow_zone_source(
        docs, paths, dest, target, op, position, head_only=head_only)
    changed, receipt = insert_signal_in_saved_route(protected, paths, dest, target, op, courses)
    project = project_from({**protected, **changed}, paths, dest)
    report = receipt['slow_zone_split']
    assert report['position'] == position and report['aspect_code'] == 4
    assert report['original_signal_aspect_codes'] == [0, 4]
    first, second = report['upstream'], report['downstream']
    assert first['zone_edges'] + second['zone_edges'] == report['original_zone_edges']
    assert report['original_zone_m_from_route_origin'][1] > report['original_zone_m_from_route_origin'][0]
    assert first['effective_zone_anchors'] == ((None, None) if position == 'downstream' else (nodes[0], nodes[cut]))
    assert second['effective_zone_anchors'] == ((None, None) if position == 'upstream' else (nodes[cut], nodes[-1]))
    assert first['aspect_code'] == (0 if position == 'downstream' else 4)
    assert second['head_only'] == (head_only and position != 'upstream')
    assert first['head_only'] == (head_only and position != 'downstream')
    new_signal = project.model(nodes[cut]).contents[11].value
    assert [row.contents[0].value for row in route_factory.wrapper(new_signal.contents[10].value, 'OTSigIndList')] == (
        [0] if position == 'upstream' else [0, 4])
    if fixture != 'local' and position == 'crossing':
        handoff = report['original_raw_zone_anchors']['A'][1]
        assert handoff[0] == 'A'
        continued = first if fixture == 'receiving_corridor' else second
        assert continued['raw_zone_anchors']['A'][1] == handoff
        assert continued['raw_zone_anchors']['B'][1] == (nodes[cut] if fixture == 'receiving_corridor' else nodes[-1])


def test_slow_zone_split_rejects_local_handoff_as_effective_finish_and_requires_available_track_aspect(receiving_corridor):
    docs, paths, dest, _, op, _, _ = receiving_corridor
    courses = course_archive(C01=['I:A-B'])
    protected, reviewed, _, _ = _slow_zone_source(docs, paths, dest, 'B', op, 'crossing')
    wrong = reviewed['split_route']['slow_zone']
    project = project_from(protected, paths, dest)
    source_ref = dict(op['split_route']['route'])
    sender = source_ref.pop('document')
    row, = [item for item in project.continuations if item['route'] == source_ref and item['source_document'] == sender]
    wrong['finish'] = {'document': 'A', 'end_id': row['local_end_ids'][-1]}
    with pytest.raises(ValueError, match='effective original slow-speed zone'):
        insert_signal_in_saved_route(protected, paths, dest, 'B', reviewed, courses)
    protected, reviewed, _, _ = _slow_zone_source(
        docs, paths, dest, 'B', op, 'downstream', allow_track_speed=False)
    with pytest.raises(ValueError, match='track-speed code 0 already available'):
        insert_signal_in_saved_route(protected, paths, dest, 'B', reviewed, courses)


def test_slow_zone_end_counter_admits_one_exact_route_role_and_refuses_unreviewed_or_duplicate_owners():
    docs, paths, dest, _, op = station_corridor(reverse=False)
    protected, reviewed, _, _ = _slow_zone_source(docs, paths, dest, 'Line', op, 'upstream')
    root, _ = writer.load_next_compatible(protected['Line'])
    _, by_id = route_factory.document(root)
    end = by_id[reviewed['end_id']]
    routes = {ident(obj)[0]: obj for obj in writer.objects(root) if writer.kind(obj) == 'OTRoute'}
    selected = routes[reviewed['split_route']['route']['name']]
    with pytest.raises(ValueError, match='Unknown incoming owner'):
        path_functions.guard_counter_references(root, end, reviewed_zone_owners=(routes['Approach P'],))
    path_functions.guard_counter_references(root, end, reviewed_zone_owners=(selected,))
    selected.contents[12].values[1] = end
    with pytest.raises(ValueError, match='Only one reviewed native slow-zone anchor'):
        path_functions.guard_counter_references(root, end, reviewed_zone_owners=(selected,))


def test_slow_zone_requires_the_metric_indication_owned_by_the_original_signal():
    docs, paths, dest, _, op = station_corridor(reverse=False)
    protected, reviewed, nodes, _ = _slow_zone_source(docs, paths, dest, 'Line', op, 'crossing')
    graph = project_from(protected, paths, dest)
    signal = graph.model(nodes[0]).contents[11].value
    _, restricted = route_factory.wrapper(signal.contents[10].value, 'OTSigIndList')
    restricted.contents[1].value = graph.model(nodes[-1])
    protected['Line'] = writer.dump_verified(graph.roots['Line'], graph.versions['Line'])
    with pytest.raises(ValueError, match='original starting signal does not own'):
        insert_signal_in_saved_route(protected, paths, dest, 'Line', reviewed, course_archive(C01=['Through']))


def _timed_source(docs, paths, dest, operation, *, approach_length=40, partition_conflict=False):
    graph = project_from(docs, paths, dest)
    original = dict(operation['split_route']['route'])
    document = original.pop('document')
    owner = document, original['start_id']
    route = graph.owned(owner, 'OTRoute', (original['name'], original['array_id'], original['start_id']))
    values = {**DEFAULT_ROUTE_TIMING, 'release_distance_m': 60, 'use_release_distance': True,
              'release_time_s': 9, 'reserve_time_s': 12, 'approach_length_m': approach_length,
              'approach_speed_kmh': 28, 'reservation_distance_m': 600, 'use_reservation_distance': True}
    for slot, parts in timing_groups(route, values).items():
        route.contents[slot].values[:] = parts
    anchors = release_keys(graph, route)
    touched = {document}
    continuation = next((item for item in graph.continuations
                         if item['source_document'] == document and item['route'] == original), None)
    if continuation is not None:
        coord = continuation['target_document'], continuation['target_connector']
        fragment = graph.owned(coord, 'OTRoute', ident(route))
        anchors += release_keys(graph, fragment)
    if partition_conflict:
        a, cut, b = graph.route_view(route)
        left, right = (graph.model(graph.edge_between(first, last)) for first, last in ((a, cut), (cut, b)))
        left.contents[13].value = right
        right.contents[14].value = left
    updated = {sheet: writer.dump_verified(graph.roots[sheet], graph.versions[sheet]) for sheet in touched}
    review = {**values, 'release_group_starts': [{'document': sheet, 'end_id': ordinal} for sheet, ordinal in anchors]}
    request = {**operation, 'split_route': {**operation['split_route'], 'timing': review, 'reserve_with_previous': True}}
    return {**docs, **updated}, request


@pytest.mark.parametrize(('fixture', 'target'), (
    ('occupied_corridor', 'Line'),
    ('sending_corridor', 'A'),
    ('receiving_corridor', 'B'),
))
def test_timing_only_moves_to_its_original_entry_or_terminal(request, fixture, target):
    case = request.getfixturevalue(fixture)
    docs, paths, dest = case[:3]
    op = case[4] if fixture == 'receiving_corridor' else case[-1]
    courses = case[-2] if fixture == 'occupied_corridor' else course_archive(C01=['I:A-B'])
    protected, op = _timed_source(docs, paths, dest, op)
    changed, receipt = insert_signal_in_saved_route(protected, paths, dest, target, op, courses)
    fresh = project_from({**protected, **changed}, paths, dest)
    first, second = [fresh.owned((row['document'], row['start_id']), 'OTRoute',
                                 (row['name'], row['array_id'], row['start_id']))
                     for row in (receipt['upstream_route'], receipt['downstream_route'])]
    left = stored_route_timing(first)
    assert left == {**DEFAULT_ROUTE_TIMING, 'reserve_time_s': 12, 'release_time_s': 9,
                    'reservation_distance_m': 600, 'use_reservation_distance': True}
    right = stored_route_timing(second)
    assert right == {**DEFAULT_ROUTE_TIMING, 'release_time_s': 9, 'release_distance_m': 60,
                     'approach_length_m': 40, 'approach_speed_kmh': 28, 'use_release_distance': True}
    assert first.contents[11].value == 0 and second.contents[11].value == 1
    timing = receipt['timing_split']
    terminal = timing['terminal_m_from_original_route_origin']
    assert timing['terminal_release_m_from_original_route_origin'] == terminal + 60
    assert timing['terminal_approach_m_from_original_route_origin'] == [terminal - 40, terminal]
    assert timing['run_switch_and_reservation_time_required_for_delay']
    if fixture != 'occupied_corridor':
        crossing, = [row for row in fresh.continuations if row['route'] in
                     [ref_record(ident(obj)) for obj in (first, second)]]
        fragment = fresh.owned((crossing['target_document'], crossing['target_connector']), 'OTRoute',
                               (crossing['route']['name'], crossing['route']['array_id'], crossing['route']['start_id']))
        assert stored_route_timing(fragment) == DEFAULT_ROUTE_TIMING
        assert timing['cut_already_a_group_anchor']


def test_timing_split_rejects_truncated_approach_unreviewed_anchors_and_unsynchronized_entry(occupied_corridor):
    docs, paths, dest, _, _, courses, op = occupied_corridor
    protected, request = _timed_source(docs, paths, dest, op, approach_length=101)
    with pytest.raises(ValueError, match='approach section must fit entirely'):
        insert_signal_in_saved_route(protected, paths, dest, 'Line', request, courses)
    protected, request = _timed_source(docs, paths, dest, op)
    expected = request['split_route']['timing']
    expected['release_group_starts'] = expected['release_group_starts'][:1]
    with pytest.raises(ValueError, match='exact saved ordered release-group Ends'):
        insert_signal_in_saved_route(protected, paths, dest, 'Line', request, courses)
    protected, request = _timed_source(docs, paths, dest, op)
    request['split_route']['reserve_with_previous'] = False
    with pytest.raises(ValueError, match='downstream Route to reserve with the previous'):
        insert_signal_in_saved_route(protected, paths, dest, 'Line', request, courses)


def test_timing_split_cannot_release_resources_shared_between_the_two_sections(occupied_corridor):
    docs, paths, dest, _, _, courses, op = occupied_corridor
    protected, request = _timed_source(docs, paths, dest, op, partition_conflict=True)
    with pytest.raises(ValueError, match='may not share a Safety Element or Edge exclusion'):
        insert_signal_in_saved_route(protected, paths, dest, 'Line', request, courses)


def test_timed_local_split_retains_an_existing_internal_release_group_after_the_relay():
    docs, paths, dest, graph, op = station_corridor(reverse=False)
    source = op['split_route']['route']
    route = graph.owned(('Line', source['start_id']), 'OTRoute', (source['name'], source['array_id'], source['start_id']))
    first, cut, _, retained, last = path_functions.mutable_array(route.contents[0].value)
    route.contents[12].values[0] = path_functions.array_like(route.contents[12].values[0], [first, cut, retained, last])
    docs['Line'] = writer.dump_verified(graph.roots['Line'], graph.versions['Line'])
    protected, request = _timed_source(docs, paths, dest, op)
    _, result = insert_signal_in_saved_route(protected, paths, dest, 'Line', request, course_archive(C01=['Through']))
    group = result['timing_split']['saved_release_group_starts']
    assert group == {'upstream': [graph.key(point) for point in (first, cut)],
                     'downstream': [graph.key(point) for point in (cut, retained, last)]}
