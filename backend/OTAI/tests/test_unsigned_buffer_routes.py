from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import path_functions, route_factory, writer
from opentrack_ai.current_archive.buffer_route_inspection import inspect_archive
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.route_discovery_tools import discover_from
from opentrack_ai.current_archive.route_fetch_tools import fetch_routes
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, model_id, project_from, transform

from test_route_fetch import candidate
from test_itinerary_native_edit import schematic_document
from test_saved_terminal_halts import case, clean_platform, terminal_platform


def unsigned_terminal(terminal_platform):
    docs, paths, dest, signed, donor = terminal_platform
    current = project_from(docs, paths, dest)
    buffer = current.model(('RDG', signed['expected_buffer_end_id']))
    signal = buffer.contents[11].value
    buffer.contents[11].value = None
    reference = ('RDG', signed['station_reference_end_id'])
    for half in (reference, current.related(reference)):
        current.model(half).contents[20].value = 1
    root = current.roots['RDG']
    writer.set_elements(root.contents[2].value, [obj for obj in current.models['RDG'] if obj is not signal])
    data = writer.dump_verified(root, current.versions['RDG'])
    return {'RDG': data}, paths, dest, {**signed, 'expected_buffer_signal_id': None, 'station_reference_end_id': None}, donor


def test_discover_save_and_mark_an_unsigned_physical_buffer(terminal_platform):
    docs, paths, dest, operation, donor = unsigned_terminal(terminal_platform)
    graph = project_from(docs, paths, dest)
    start = 'RDG', operation['arrival_route']['start_id']
    route = graph.routes[0]
    chain = graph.route_view(route)
    args = SimpleNamespace(include_buffer_stops=False, routes_per_start=2, max_expansions_per_start=30, max_hops=20)
    assert discover_from(graph, start, args, {})['routes'] == []
    args.include_buffer_stops = True
    discovered, = discover_from(graph, start, args, {})['routes']
    assert discovered['terminal_kind'] == 'buffer_stop' and list(discovered['end_sequence']) == chain
    fetched, result = fetch_routes(docs, paths, dest, [{'name': 'New buffer route', 'description': '', 'candidate': discovered,
        'release_groups': 'native_default', 'reserve_previous': False, 'allow_duplicate_movement': True}])
    new_ref = result['created_routes'][0]['route']
    marker = {**operation['markers'][0], 'maximum_length_for_marker_m': 100}
    request = {**operation, 'arrival_route': {'document': 'RDG', **new_ref}, 'markers': [marker]}
    updated, report = transform(fetched, paths, dest, 'RDG', request, shapes=donor)
    before, after = (project_from(item, paths, dest) for item in (fetched, updated))
    assert _movement_manifest(before) == _movement_manifest(after)
    assert report['terminal_has_signal'] is False and report['unsigned_buffer_fallback_is_geometry_only']
    assert after.model(chain[-1]).contents[11].value is None
    assert after.model(chain[-2]).contents[11].value.contents[8].values[0] == 8
    report = inspect_archive(after.roots['RDG'])
    assert {item['name'] for item in report['routes']} == {'Arrive', 'New buffer route'}
    assert all(item['terminal_signal_id'] is None and item['station_reference_end_ids'] == [] for item in report['routes'])


def test_buffer_mode_refuses_open_track_or_undeclared_endpoint(terminal_platform):
    docs, paths, dest, operation, _ = unsigned_terminal(terminal_platform)
    graph = project_from(docs, paths, dest)
    route = graph.routes[0]
    chain = graph.route_view(route)
    packet = {'name': 'Restricted', 'release_groups': 'native_default', 'reserve_previous': False,
              'allow_duplicate_movement': True}
    with pytest.raises(ValueError, match='signal-free physical buffer'):
        fetch_routes(docs, paths, dest, [{**packet, 'candidate': {**candidate(graph, chain[:-1]), 'terminal_kind': 'buffer_stop'}}])
    with pytest.raises(ValueError, match='main signals'):
        fetch_routes(docs, paths, dest, [{**packet, 'candidate': candidate(graph, chain)}])


def test_read_only_detector_resolves_buffer_even_with_unrelated_duplicate_id(terminal_platform):
    docs, paths, dest, operation, _ = unsigned_terminal(terminal_platform)
    root, _ = writer.load_next_compatible(docs['RDG'])
    models, _ = route_factory.document(root)
    station = next(obj for obj in models if writer.kind(obj) == 'OTStationModel')
    edge = next(obj for obj in models if writer.kind(obj) == 'OTEdgeModel')
    station.contents[0].value = model_id(edge)
    report = inspect_archive(root)
    route, = report['routes']
    assert route['buffer_end_id'] == operation['expected_buffer_end_id'] and route['station_sign'] == 'P9'
    assert report['duplicate_graphic_ids'] == {model_id(edge): 2} and not report['full_project_validation_performed']


def test_cross_document_buffer_route_has_exact_companion_and_accepts_terminal_halt(terminal_platform):
    station_docs, _, _, halt, donor = unsigned_terminal(terminal_platform)
    station_root, _ = writer.load_next_compatible(station_docs['RDG'])
    _, station_models = route_factory.document(station_root)
    station = path_functions.clone(station_models[halt['station_id']])
    west, _ = schematic_document(generate.spec(), [('left', 0)])
    specification = generate.spec()
    specification['vertices'] = [generate.vertex(key, 100 + index * 100) for index, key in enumerate('PQRS')]
    edge = specification['edges'][0]
    specification['edges'] = [{**edge, 'key': a + b, 'from': [a, 1], 'to': [b, 0], 'length_m': length}
                              for a, b, length in [('P', 'Q', 100), ('Q', 'R', 120), ('R', 'S', 200)]]
    east, ends = schematic_document(specification, [])
    root, version = writer.load_next_compatible(east)
    models, byid = route_factory.document(root)
    station.contents[0].value = max(byid) + 1
    for name in 'QRS':
        for key in ends[name]:
            byid[key].contents[12].value = station
    writer.set_elements(root.contents[2].value, [*models, station])
    documents = {'A': west, 'B': writer.dump_verified(root, version)}
    paths = {name: name + '.opentrack' for name in documents}
    catalog = writer.dump_verified(generate.wrapped('OTDestInfoList', []))
    linked, _ = transform(documents, paths, catalog, 'A', {'action': 'replace_connectors', 'unlink': [],
        'link': [{'a': {'document': 'A', 'end_id': 5}, 'b': {'document': 'B', 'end_id': 0}}]})
    documents.update(linked)
    project = project_from(documents, paths, catalog)
    matching = SimpleNamespace(include_buffer_stops=True, routes_per_start=2, max_expansions_per_start=20, max_hops=20)
    route, = discover_from(project, ('A', 0), matching, {})['routes']
    assert route['terminal_kind'] == 'buffer_stop' and route['document_boundaries'] == 1 and route['one_route_storage_compatible']
    route_packet = {'name': 'Across to buffer', 'description': '', 'candidate': route, 'release_groups': 'native_default',
                    'reserve_previous': False, 'allow_duplicate_movement': False}
    with pytest.raises(ValueError, match='document boundary count differs'):
        fetch_routes(documents, paths, catalog, [{**route_packet, 'candidate': {**route, 'document_boundaries': 0}}])
    fetched, report = fetch_routes(documents, paths, catalog, [route_packet])
    saved = project_from(fetched, paths, catalog)
    output, = report['created_routes']
    primary = saved.owned(('A', 0), 'OTRoute', ('Across to buffer', 0, 0))
    companion = saved.owned(('B', 0), 'OTRoute', ('Across to buffer', 0, 0))
    assert saved.route_view(primary) == list(route['end_sequence']) and report['companion_count'] == 1
    assert primary.contents[5].values[4] == 2 and companion.contents[5].values[4] == -1
    assert output['fragments'][1]['owner'] == ('B', 0) and saved.block_end(('B', 0)) == ('A', 5)
    assert saved.model(('B', ends['S'][0])).contents[11].value is None
    new_halt = {**halt, 'station_id': model_id(station), 'arrival_route': {'document': 'A', **output['route']},
        'platform_entry_end_id': ends['Q'][0], 'expected_buffer_end_id': ends['S'][0],
        'expected_platform_edge_ids': [key[1] for key in route['edge_sequence'][-2:]],
        'markers': [{'end_id': ends['R'][0], 'signal_name': 'Remote head', 'stop_reference': 'head',
                     'expected_position_from_entry_m': 120}]}
    updated, receipt = transform(fetched, paths, catalog, 'B', new_halt, shapes=donor)
    fresh = project_from({**fetched, **updated}, paths, catalog)
    assert set(updated) == {'B'} and _movement_manifest(fresh) == _movement_manifest(saved)
    assert fresh.report()['continuations'] == saved.report()['continuations'] and receipt['platform_length_m'] == 320
    assert receipt['stop_selection_by_train_length'][0]['after']['example_head_position_m'] == 120
