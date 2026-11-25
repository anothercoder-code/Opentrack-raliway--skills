"""Route-selective local branches, including two branches on the same Route."""

from copy import deepcopy

import pytest

from opentrack_ai.current_archive import native_occupation_groups, route_factory, writer
from opentrack_ai.current_archive.multi_document import generate, operations
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, project_from, transform
from opentrack_ai.current_archive.saved_geometry_tools import RerouteLocalJunctionTrackSpans
from opentrack_ai.current_archive.saved_track_replacement import _protection_manifest
from opentrack_ai.current_archive.saved_track_reroute import _walk_span
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_itinerary_native_edit import schematic_document


@pytest.fixture
def junction():
    document = 'Yard'
    paths = {document: 'Yard.opentrack'}
    line = generate.spec()
    line['vertices'] = [{**generate.vertex(name, 100 * index), 'y': y} for index, (name, y) in enumerate((
        ('A', 100), ('O1', 50), ('N1', 150), ('B', 100), ('O2', 50), ('N2', 150), ('C', 100),
    ))]
    parts = {'old1': [('A', 'O1', 100), ('O1', 'B', 100)], 'new1': [('A', 'N1', 70), ('N1', 'B', 150)],
             'old2': [('B', 'O2', 100), ('O2', 'C', 100)], 'new2': [('B', 'N2', 110), ('N2', 'C', 135)]}
    line['edges'] = [{**line['edges'][0], 'key': a + b, 'from': [a, 1], 'to': [b, 0], 'length_m': length}
                     for series in parts.values() for a, b, length in series]
    data, ids = schematic_document(line, [('A', 0), ('A', 1), ('C', 0), ('C', 1)])
    root, version = writer.load_next_compatible(data)
    models, by_id = route_factory.document(root)
    stations = []
    for index, sign in enumerate(('A', 'C'), start=max(by_id) + 1):
        station = native.obj([('OTStationModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], [
            ('i', [index]), ('f', [0.0]), ('f', [100.0]), ('f', [50.0]), ('i', [0]), ('i', [0]),
            ('@', [None]), ('@', [native.string(sign)]), ('ii', [2, 4]), ('ii', [1, 0]),
        ])
        for number in ids[sign]:
            by_id[number].contents[12].value = station
            by_id[number].contents[20].value = 2
        stations.append(station)
    writer.set_elements(root.contents[2].value, [*models, *stations])
    data = writer.dump_verified(root, version)
    route_defs = {'Forward': [ids[name][0] for name in ('A', 'O1', 'B', 'O2', 'C')],
                  'Reverse': [ids[name][1] for name in ('C', 'O2', 'B', 'O1', 'A')]}
    routes = {}
    for name, ends in route_defs.items():
        data, route = native.build_route(data, name=name, end_ids=ends, description='',
                                         release_groups='each_end', reserve_previous=False)
        routes[name] = {'document': document, **{key: route[key] for key in ('name', 'array_id', 'start_id')}}
    docs, catalog = {document: data}, writer.dump_verified(generate.wrapped('OTDestInfoList', []))

    def sources():
        return {'document_paths': paths, 'complete_document_set': True,
                'expected_hashes': {document: sha(docs[document]), '$dest_catalog': sha(catalog)}}

    for name, route in routes.items():
        docs, path = operations.create_path(docs, catalog, name='Path ' + name, routes=[route], **sources())
        expanded, _ = operations.create_itinerary(docs, catalog, name='Service ' + name,
                                                    paths=[path['created']], **sources())
        docs, catalog = expanded['documents'], expanded['catalog']

    project = project_from(docs, paths, catalog)
    edge_ids = {
        name: [project.edge_between((document, ids[first][0]), (document, ids[last][0]))[1]
               for first, last, _ in rows] for name, rows in parts.items()
    }
    route = routes['Forward']
    owner = {'document': document, 'end_id': route['start_id']}
    alignments = []
    for index, start in ((1, 'A'), (2, 'B')):
        replacement = edge_ids[f'new{index}']
        _, length, rows = _walk_span(project, document, (document, ids[start][1]), replacement)
        alignments.append({'start_end_id': ids[start][1], 'old_edge_ids': edge_ids[f'old{index}'],
                           'replacement_edge_ids': replacement, 'expected_replacement_length_m': length,
                           'expected_replacement_safety_element_ids': [row['safety_element_id'] for row in rows],
                           'routes': [route], 'route_anchor_rebindings': [{'fragment_owner': owner,
                               'route': {key: route[key] for key in ('name', 'array_id', 'start_id')},
                               'anchors': [{'old_end_id': ids[f'O{index}'][0], 'new_end_id': ids[f'N{index}'][0]}]}]})
    original_members = edge_ids['old1'] + edge_ids['old2']
    additions = edge_ids['new1'] + edge_ids['new2']
    adjusted, _ = native_occupation_groups.transform(docs[document], document, [
        {'action': 'create', 'name': 'Combined_Throat', 'edge_ids': original_members},
        {'action': 'create', 'name': 'Reverse_Throat', 'edge_ids': original_members},
        {'action': 'create', 'name': 'Forward_Throat', 'edge_ids': additions},
    ])
    docs[document] = adjusted
    operation = {'action': 'reroute_local_junction_track_spans', 'alignments': alignments,
                 'witness_itineraries': {'Service Forward': 465},
                 'occupation_group_extensions': [{'name': 'Combined_Throat', 'document': document,
                     'expected_edge_ids': original_members, 'added_edge_ids': additions}]}
    return document, docs, paths, catalog, operation, ids, edge_ids


def test_two_local_alignments_revise_one_route_while_retaining_reverse_release_and_monitoring(junction):
    document, docs, paths, catalog, operation, ids, edges = junction
    before = project_from(docs, paths, catalog)
    reviewed = RerouteLocalJunctionTrackSpans.model_validate(operation)
    replacements, report = transform(docs, paths, catalog, document, reviewed.model_dump())
    after = project_from(replacements, paths, catalog)
    assert report['witness_itineraries']['Service Forward'] == {
        'before_length_m': 400, 'after_length_m': 465, 'crossing_indices': [0, 1]}
    forward, = report['rewritten_routes']
    assert [key['new'][1] for key in forward['rebound_release_boundaries']] == [ids['N1'][0], ids['N2'][0]]
    previous, actual = _movement_manifest(before), _movement_manifest(after)
    untouched = {key for key in previous if 'Reverse' in key[2][0]}
    assert len(untouched) == 3 and all(previous[key] == actual[key] for key in untouched)
    old_protection, new_protection = _protection_manifest(before, document), _protection_manifest(after, document)
    reverse, = [key for key in old_protection if key[2][0] == 'Reverse']
    assert new_protection[reverse] == old_protection[reverse]
    groups = {row['name']: row['edge_ids'] for row in native_occupation_groups.records(after.roots[document], document)}
    assert groups['Combined_Throat'] == edges['old1'] + edges['old2'] + edges['new1'] + edges['new2']
    assert groups['Reverse_Throat'] == edges['old1'] + edges['old2']
    assert groups['Forward_Throat'] == edges['new1'] + edges['new2']
    assert report['original_track_chains_retained'] and report['continuation_ownership_verified']


def test_overlapping_local_reviews_and_transferring_retained_monitors_are_rejected(junction):
    document, docs, paths, catalog, operation, _, edges = junction
    overlapping = deepcopy(operation)
    overlapping['alignments'][1] = deepcopy(overlapping['alignments'][0])
    overlapping['alignments'][1].pop('route_anchor_rebindings')
    with pytest.raises(ValueError, match='overlap in the same original Route'):
        transform(docs, paths, catalog, document, overlapping)
    moved = deepcopy(operation)
    moved['occupation_group_rebindings'] = [{'name': 'Reverse_Throat', 'document': document,
        'expected_edge_ids': edges['old1'] + edges['old2'],
        'edge_rebindings': [{'old_edge_id': edges['old1'][0], 'new_edge_ids': edges['new1']}]}]
    with pytest.raises(ValueError, match='monitor Edge still traversed'):
        transform(docs, paths, catalog, document, moved)
