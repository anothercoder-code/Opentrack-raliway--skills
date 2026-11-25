"""Prove native Path and destination index persistence after station endpoint changes."""

import pytest

from opentrack_ai.current_archive import path_functions, route_factory, writer
from opentrack_ai.current_archive.itinerary_edit_tools import (
    EditableItineraryProject, _margin_members, _margin_values, set_safety_margins,
)
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.multi_document.core import ident, sha
from opentrack_ai.current_archive.multi_document.operations import create_itinerary, create_path
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, project_from
from opentrack_ai.current_archive.station_reference_rebinding import rebind_station_reference_endpoints
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_itinerary_native_edit import schematic_document


@pytest.fixture(scope='module')
def endpoint_fixture():
    diagram = generate.spec()
    diagram['vertices'] = [generate.vertex(key, 40 + 80 * i) for i, key in enumerate('OABC')]
    edge, = diagram['edges']
    diagram['edges'] = [{**edge, 'key': a + b, 'from': [a, 1], 'to': [b, 0], 'length_m': 120}
                        for a, b in zip('OAB', 'ABC')]
    data, ends = schematic_document(diagram, [(key, direction) for key in 'OABC' for direction in (0, 1)])
    root, version = writer.load_next_compatible(data)
    models, ids = route_factory.document(root)
    station = native.obj([('OTStationModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], [
        ('i', [max(ids) + 1]), ('f', [0.0]), ('f', [120.0]), ('f', [50.0]), ('i', [0]), ('i', [0]),
        ('@', [None]), ('@', [native.string('P')]), ('ii', [2, 4]), ('ii', [1, 0]),
    ])
    for key in 'AB':
        for end in ends[key]:
            ids[end].contents[12].value = station
            ids[end].contents[20].value = 2 if key == 'B' else 1
    writer.set_elements(root.contents[2].value, [*models, station])
    docs = {'Line': writer.dump_verified(root, version)}
    paths = {'Line': 'Line.opentrack'}
    catalog = writer.dump_verified(generate.wrapped('OTDestInfoList', []))
    routes = {}
    for a, b, side in (('O', 'A', 0), ('A', 'B', 0), ('B', 'C', 0),
                        ('C', 'B', 1), ('B', 'A', 1), ('A', 'O', 1)):
        docs['Line'], report = native.build_route(docs['Line'], name=a + b, end_ids=[ends[a][side], ends[b][side]],
            description='', release_groups='global', reserve_previous=False)
        routes[a + b] = {'document': 'Line', 'name': a + b, 'array_id': report['array_id'], 'start_id': ends[a][side]}

    def configuration():
        return {'document_paths': paths, 'expected_hashes': {**{name: sha(data) for name, data in docs.items()},
                  '$dest_catalog': sha(catalog)}, 'complete_document_set': True, 'project_type': EditableItineraryProject}

    references = {}
    for name, selected in (('OriginalEast', ['AB', 'BC']), ('After', ['BC']), ('FromWest', ['OA']),
                           ('FromEast', ['CB', 'BA']), ('OriginalWest', ['AO'])):
        docs, result = create_path(docs, catalog, name=name, routes=[routes[key] for key in selected], **configuration())
        references[name] = result['created']

    for name, selection in (('Eastbound', 'OriginalEast'), ('Another usage of shared Path', 'OriginalEast'),
                            ('EndFromWest', 'FromWest'), ('EndFromEast', 'FromEast'), ('Westbound', 'OriginalWest')):
        output, _ = create_itinerary(docs, catalog, name=name, paths=[references[selection]], **configuration())
        docs, catalog = output['documents'], output['catalog']
    moved = {('Line', a): ('Line', b) for a, b in zip(ends['A'], ends['B'], strict=True)}
    return docs, paths, catalog, moved, routes, references


def _review(itinerary, routes, *keys):
    return {'itinerary': itinerary, 'replacement_routes': [routes[key] for key in keys]}


def test_trims_and_extends_exact_station_ends_with_native_path_reuse(endpoint_fixture):
    docs, paths, src, moved, routes, refs = endpoint_fixture
    reviews = [_review('Eastbound', routes, 'BC'), _review('EndFromWest', routes, 'OA', 'AB'),
               _review('EndFromEast', routes, 'CB'), _review('Westbound', routes, 'BA', 'AO')]
    output, catalog, report = rebind_station_reference_endpoints(docs, paths, src, moved, reviews)
    result = {item['itinerary']: item for item in report['endpoint_rebindings']}
    assert output.keys() == {'Line'} and report['catalog_bindings_verified']
    assert result['Eastbound']['replacement_paths'] == [refs['After']]
    assert result['Eastbound']['prefix_length_change_m'] == -120 and result['EndFromWest']['suffix_length_change_m'] == 120
    assert result['EndFromEast']['suffix_length_change_m'] == -120 and result['Westbound']['prefix_length_change_m'] == 120
    assert ({'document': 'Line', 'start_id': routes['BA']['start_id']}.items()
            <= result['Westbound']['replacement_paths'][0].items())
    assert result['Westbound']['replacement_paths'][1:] == [refs['OriginalWest']]
    assert result['EndFromWest']['replacement_paths'][:1] == [refs['FromWest']]
    assert len(report['created_paths']) == 3
    old = project_from(docs, paths, src)
    fresh = project_from({**docs, **output}, paths, catalog)
    old_movements, new_movements = _movement_manifest(old), _movement_manifest(fresh)
    assert all(new_movements[key] == row for key, row in old_movements.items()
               if key[0] != 'itinerary' or key[2][0] == 'Another usage of shared Path')
    inactive, = [item for item in fresh.dests if ident(item)[0] == 'Another usage of shared Path']
    assert path_functions.info(inactive)['saved_references'] == [refs['OriginalEast']]
    west, = [item for item in fresh.dests if ident(item)[0] == 'Westbound']
    assert fresh.dest_view(west)[0][0] == result['Westbound']['replacement_start']


def test_rejects_unchanged_ends_nonpaired_request_and_unmapped_safety_margin(endpoint_fixture):
    docs, paths, catalog, moved, routes, _ = endpoint_fixture
    with pytest.raises(ValueError, match='exact reviewed revised directional Ends'):
        rebind_station_reference_endpoints(docs, paths, catalog, moved, [_review('Eastbound', routes, 'AB', 'BC')])
    wrong = dict(zip(moved, reversed(list(moved.values())), strict=True))
    with pytest.raises(ValueError, match='common directed movement|leave|exact reviewed revised'):
        rebind_station_reference_endpoints(docs, paths, catalog, wrong, [_review('Eastbound', routes, 'BC')])
    after, _ = set_safety_margins(docs['Line'], 'Eastbound', [{'position_m': 100, 'safety_margin_m': 25}])
    with pytest.raises(ValueError, match='distance-based safety margins'):
        rebind_station_reference_endpoints({'Line': after}, paths, catalog, moved, [_review('Eastbound', routes, 'BC')])


@pytest.mark.parametrize('name,route_names,old_points,new_points', [
    ('Eastbound', ('BC',), [(30, 25), (75, 50), (140, 15)], [(0, 50), (20, 15)]),
    ('Eastbound', ('BC',), [(30, 25), (120, 50), (120, 15), (140, 70)], [(0, 50), (0, 15), (20, 70)]),
    ('Westbound', ('BA', 'AO'), [(0, 25), (15, 50), (120, 60)], [(120, 25), (135, 50), (240, 60)]),
    ('EndFromEast', ('CB',), [(0, 25), (120, 50), (120, 15), (140, 70)], [(0, 25), (120, 50), (120, 15)]),
    ('EndFromWest', ('OA', 'AB'), [(0, 25), (120, 50)], [(0, 25), (120, 50)]),
])
def test_maps_safety_margins_along_the_retained_directed_track(endpoint_fixture, name, route_names, old_points, new_points):
    docs, paths, catalog, moved, routes, _ = endpoint_fixture
    old_rows, new_rows = (
        [{'position_m': float(position), 'safety_margin_m': float(margin)} for position, margin in points]
        for points in (old_points, new_points)
    )
    source, _ = set_safety_margins(docs['Line'], name, old_rows)
    request = {**_review(name, routes, *route_names), 'map_itinerary_safety_margins': True}
    output, revised_catalog, result = rebind_station_reference_endpoints({'Line': source}, paths, catalog, moved, [request])
    project = project_from(output, paths, revised_catalog)
    saved, = [definition for definition in project.dests if ident(definition)[0] == name]
    assert _margin_values(_margin_members(saved)[2]) == new_rows
    report, = result['endpoint_rebindings']
    assert report['mapped_safety_margins']['before'] == old_rows
    assert report['mapped_safety_margins']['after'] == new_rows


def test_new_start_owns_path_and_itinerary_in_its_new_native_worksheet():
    paths = {name: f'{name}.opentrack' for name in ('A', 'B')}
    first, _ = schematic_document(generate.spec(), [('left', 0), ('left', 1)])
    line = generate.spec()
    line['vertices'].append(generate.vertex('terminal', 430))
    line['edges'].append({**line['edges'][0], 'key': 'departure', 'from': ['right', 1], 'to': ['terminal', 0]})
    second, ends = schematic_document(line, [('right', 0), ('right', 1), ('terminal', 0), ('terminal', 1)])
    docs, catalog, _ = generate.make_pair({'A': first, 'B': second}, paths)
    new_end, terminal = ends['right'][0], ends['terminal'][0]
    receiving, version = writer.load_next_compatible(docs['B'])
    _, by_id = route_factory.document(receiving)
    left, right = by_id[new_end], by_id[terminal]
    departure = generate.route('Platform departure', 0, new_end, [left, right], -1)
    writer.set_elements(left.contents[15].value.contents[0].value, [departure])
    left.contents[19].value = 0
    docs['B'] = writer.dump_verified(receiving, version)
    replacement = {'document': 'B', 'name': 'Platform departure', 'array_id': 0, 'start_id': new_end}
    original_route = {'document': 'A', 'name': 'R:A-B', 'array_id': 0, 'start_id': 0}

    def config():
        return {'document_paths': paths, 'expected_hashes': {**{key: sha(blob) for key, blob in docs.items()},
                  '$dest_catalog': sha(catalog)}, 'complete_document_set': True, 'project_type': EditableItineraryProject}

    docs, original_path = create_path(docs, catalog, name='Original cross-sheet Path',
                                      routes=[original_route, replacement], **config())
    written, _ = create_itinerary(docs, catalog, name='Board and depart', paths=[original_path['created']], **config())
    docs, catalog = written['documents'], written['catalog']
    for sheet, members, references in (('A', [0, 1, 4], []), ('B', [1, *ends['right']], ends['right'])):
        root, version = writer.load_next_compatible(docs[sheet])
        models, by_id = route_factory.document(root)
        station = native.obj([('OTStationModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], [
            ('i', [max(by_id) + 1]), ('f', [0.0]), ('f', [120.0]), ('f', [50.0]), ('i', [0]), ('i', [0]),
            ('@', [None]), ('@', [native.string('Joint')]), ('ii', [2, 4]), ('ii', [1, 0]),
        ])
        for number in members:
            by_id[number].contents[12].value = station
            by_id[number].contents[20].value = 2 if number in references else 1
        writer.set_elements(root.contents[2].value, [*models, station])
        docs[sheet] = writer.dump_verified(root, version)
    moved = {('A', old): ('B', revised) for old, revised in zip((0, 1), ends['right'], strict=True)}
    outputs, new_catalog, result = rebind_station_reference_endpoints(docs, paths, catalog, moved, [
        {'itinerary': 'Board and depart', 'replacement_routes': [replacement]},
    ])
    graph = project_from({**docs, **outputs}, paths, new_catalog)
    match, = [item for item in graph.dests if ident(item)[0] == 'Board and depart']
    assert set(outputs) == {'A', 'B'} and graph.owners[id(match)] == ('B', None)
    actual_nodes, actual_paths = graph.dest_view(match)
    assert actual_nodes == [('B', new_end), ('B', terminal)]
    assert (actual_paths[0][0], actual_paths[0][1]['start_id']) == ('B', new_end)
    native_dest, _ = writer.load_next_compatible(new_catalog)
    saved, = [item for item in route_factory.wrapper(native_dest, 'OTDestInfoList')
              if path_functions.string(item.contents[1].value) == 'Board and depart']
    assert path_functions.string(saved.contents[2].value) == 'B.opentrack' and saved.contents[3].value == new_end
    assert result['endpoint_rebindings'][0]['prefix_length_change_m'] == -2000
    assert graph.owned(('A', 0), 'OTPath', ('Original cross-sheet Path', original_path['created']['array_id'], 0))
