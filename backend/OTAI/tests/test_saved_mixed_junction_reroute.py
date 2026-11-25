"""One Route can combine a local choice and a new native continuation owner."""

from copy import deepcopy

import pytest

from opentrack_ai.current_archive import path_functions, writer
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, model_id, project_from, transform
from opentrack_ai.current_archive.saved_geometry_tools import RerouteJunctionTrackSpans
from opentrack_ai.current_archive.saved_track_replacement import _protection_manifest
from opentrack_ai.current_archive.saved_track_reroute import _walk_span
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_cross_document_route_native_edit import NATIVE_PATHS, fixture
from test_saved_geometry import shapes_for


@pytest.fixture
def mixed():
    docs, catalog = fixture()
    profiles = {'track_name': '1', 'line_name': 'A-B', 'radius_m': 0, 'gradient_per_mille': 0, 'remark': '',
                'rack_rail': False, 'allow_safety_regroup': True,
                'speeds': [{'train_type': '0', 'speed12_kmh': 80, 'speed21_kmh': 80}]}
    shape = shapes_for(docs['A'])

    def edit(operation):
        output, receipt = transform(docs, NATIVE_PATHS, catalog, 'A', operation, shapes=shape)
        docs.update(output)
        return receipt

    source = project_from(docs, NATIVE_PATHS, catalog)
    old = source.edge_between(('A', 0), ('A', 4))[1]
    former_alt = source.edge_between(('A', 0), ('A', 8))[1]
    edit({'action': 'delete_edge', 'edge_id': former_alt})
    edit({'action': 'split_edge', 'edge_id': old, 'first_length_m': 500})
    graph = project_from(docs, NATIVE_PATHS, catalog)
    reference = ('R:A-B', 0, 0)
    _, (_, middle), terminal, _ = graph.route_view(graph.owned(('A', 0), 'OTRoute', reference))
    assert terminal == ('A', 4)
    local_old = graph.edge_between(('A', 0), ('A', middle))[1]
    cross_old = graph.edge_between(('A', middle), ('A', 4))[1]
    middle_out = graph.related(('A', middle))[1]
    cross_new = edit({'action': 'insert_edge', 'end_ids': [middle_out, 8], 'length_m': 900, **profiles})['edge_id']
    local_vertex = edit({'action': 'insert_vertex', 'x': 58, 'y': 85, 'orientation': 'horizontal',
                         'names': ['Local1', 'Local2']})['added_vertex_end_ids']
    local_new = [edit({'action': 'insert_edge', 'end_ids': endpoints, 'length_m': 300, **profiles})['edge_id']
                 for endpoints in ([1, local_vertex[0]], [local_vertex[1], middle])]
    graph = project_from(docs, NATIVE_PATHS, catalog)
    for document, station_end in (('A', 0), ('B', 4)):
        station = native.obj([('OTStationModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], [
            ('i', [max(graph.byid[document]) + 1]), ('f', [0.0]), ('f', [100.0]), ('f', [50.0]),
            ('i', [0]), ('i', [0]), ('@', [None]), ('@', [native.string(document)]), ('ii', [2, 4]), ('ii', [1, 0]),
        ])
        key = (document, station_end)
        for end in (key, graph.related(key)):
            graph.model(end).contents[12].value = station
            graph.model(end).contents[20].value = 2
        writer.set_elements(graph.roots[document].contents[2].value, [*graph.models[document], station])
    primary = graph.owned(('A', 0), 'OTRoute', reference)
    current_release = primary.contents[12].values[0]
    primary.contents[12].values[0] = path_functions.array_like(current_release, [graph.model(('A', number))
                                                                               for number in (0, middle, 4)])
    docs = {name: writer.dump_verified(root, graph.versions[name]) for name, root in graph.roots.items()}
    graph = project_from(docs, NATIVE_PATHS, catalog)
    remote_old = graph.edge_between(('A', 4), ('B', 4))[1]
    remote_new = graph.edge_between(('A', 8), ('B', 4))[1]

    def edges(items):
        return [{'document': document, 'edge_id': ident} for document, ident in items]

    def safety(document, edge):
        return model_id(graph.model((document, edge)).contents[7].value.contents[7].value)

    route = {'document': 'A', 'name': reference[0], 'array_id': 0, 'start_id': 0}
    _, _, local_profile = _walk_span(graph, 'A', ('A', 1), local_new)
    operation = {'action': 'reroute_junction_track_spans', 'crossings': [{
        'start_end': {'document': 'A', 'end_id': middle_out}, 'old_edges': edges([('A', cross_old), ('B', remote_old)]),
        'replacement_edges': edges([('A', cross_new), ('B', remote_new)]), 'expected_replacement_length_m': 2700,
        'expected_replacement_safety_elements': [{'document': doc, 'element_id': safety(doc, part)}
                                                  for doc, part in (('A', cross_new), ('B', remote_new))],
        'routes': [route], 'release_boundary_rebindings': [
            {'old': {'document': 'A', 'end_id': 4}, 'new': {'document': 'A', 'end_id': 8}}],
    }], 'local_alignments': [{
        'document': 'A', 'start_end_id': 1, 'old_edge_ids': [local_old], 'replacement_edge_ids': local_new,
        'expected_replacement_length_m': 600, 'expected_replacement_safety_element_ids': [row['safety_element_id'] for row in local_profile],
        'routes': [route],
    }], 'witness_itineraries': {'I:A-B': 3300}}
    return docs, catalog, operation, middle, local_vertex[0]


def test_mixed_intervals_compose_once_on_one_route_and_preserve_reverse(mixed):
    docs, catalog, operation, middle, branch = mixed
    request = RerouteJunctionTrackSpans.model_validate(operation)
    replacements, report = transform(docs, NATIVE_PATHS, catalog, 'A', request.model_dump())
    before = project_from(docs, NATIVE_PATHS, catalog)
    after = project_from({**docs, **replacements}, NATIVE_PATHS, catalog)
    route = ('R:A-B', 0, 0)
    observed = after.owned(('A', 0), 'OTRoute', route)
    assert after.route_view(observed) == [('A', 0), ('A', branch), ('A', middle), ('A', 8), ('B', 4)]
    assert observed.contents[5].values[4] == 4 and after.block_end(('A', 9)) == ('B', 8)
    assert list(after.route_view(after.owned(('B', 8), 'OTRoute', route))) == [('B', 4)]
    zero = _protection_manifest(after, 'A')[(('A', 0), 'OTRoute', route)]
    assert zero['release_group_end_ids'] == [0, middle, 8]
    final_movement = _movement_manifest(after)
    for key, original in _movement_manifest(before).items():
        if key[2][0] in ('R:B-A', 'P:B-A', 'I:B-A'):
            assert final_movement[key] == original
    assert report['witness_itineraries']['I:A-B'] == {
        'before_length_m': 2000, 'after_length_m': 3300, 'crossing_indices': [0, 1],
    }


def test_mixed_overlap_or_unreviewed_changed_release_is_rejected(mixed):
    docs, catalog, operation, _, _ = mixed
    invalid = deepcopy(operation)
    invalid['local_alignments'].append(invalid['local_alignments'][0])
    with pytest.raises(ValueError, match='alignments overlap'):
        transform(docs, NATIVE_PATHS, catalog, 'A', invalid)
    invalid = deepcopy(operation)
    invalid['crossings'][0].pop('release_boundary_rebindings')
    with pytest.raises(ValueError, match='removed release anchor'):
        transform(docs, NATIVE_PATHS, catalog, 'A', invalid)


def test_mixed_reroute_cannot_remove_an_incident_from_retained_reverse_track(mixed):
    docs, catalog, operation, _, _ = mixed
    local, = operation['local_alignments']
    invalid = {**operation, 'track_incident_rebindings': [{'document': 'A', 'name': 'OriginalBlock',
        'edge_rebindings': [{'old_edge_id': local['old_edge_ids'][0], 'new_edge_ids': local['replacement_edge_ids']}]}]}
    with pytest.raises(ValueError, match='blockage cannot leave an original Edge'):
        transform(docs, NATIVE_PATHS, catalog, 'A', invalid)


def _both_directions(operation):
    reverse = {'document': 'B', 'name': 'R:B-A', 'array_id': 0, 'start_id': 5}
    operation['crossings'][0]['routes'].append(reverse)
    operation['local_alignments'][0]['routes'].append(reverse)
    operation['witness_itineraries']['I:B-A'] = 3300


def test_mixed_retirement_removes_both_approaches_and_collapses_turnouts(mixed):
    docs, catalog, operation, _, _ = mixed
    graph = project_from(docs, NATIVE_PATHS, catalog)
    _both_directions(operation)
    operation['retire_original'] = True
    request = RerouteJunctionTrackSpans.model_validate(operation)
    replacements, report = transform(docs, NATIVE_PATHS, catalog, 'A', request.model_dump())
    after = project_from({**docs, **replacements}, NATIVE_PATHS, catalog)
    pair = (('A', 5), ('B', 0))
    assert report['retired_connector_pairs'] == [pair]
    for end in (*pair, *(graph.related(end) for end in pair)):
        assert end[1] not in after.byid[end[0]]
    old_edges = [*operation['crossings'][0]['old_edges'],
                 {'document': 'A', 'edge_id': operation['local_alignments'][0]['old_edge_ids'][0]}]
    assert all(row['edge_id'] not in after.byid[row['document']] for row in old_edges)
    assert after.block_end(('A', 9)) == ('B', 8)
    assert report['retired_turnouts'] and not report['original_track_chains_retained']
    assert {row['after_length_m'] for row in report['witness_itineraries'].values()} == {3300}


def test_mixed_selective_retirement_keeps_usable_connector_and_rejects_sole_approach(mixed):
    docs, catalog, operation, _, _ = mixed
    local_edge = operation['local_alignments'][0]['old_edge_ids'][0]
    operation['retire_edges'] = [{'document': 'A', 'edge_id': local_edge}]
    with pytest.raises(ValueError, match='still refers to part of the retired crossing'):
        transform(docs, NATIVE_PATHS, catalog, 'A', operation)
    _both_directions(operation)
    replacements, report = transform(docs, NATIVE_PATHS, catalog, 'A', operation)
    after = project_from({**docs, **replacements}, NATIVE_PATHS, catalog)
    assert local_edge not in after.byid['A'] and report['retired_connector_pairs'] == []
    assert after.block_end(('A', 5)) == ('B', 0)
    operation['retire_edges'].append(operation['crossings'][0]['old_edges'][0])
    with pytest.raises(ValueError, match='Retire both unused approaches'):
        transform(docs, NATIVE_PATHS, catalog, 'A', operation)
