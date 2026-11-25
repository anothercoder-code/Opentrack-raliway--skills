from copy import deepcopy

import pytest

from opentrack_ai.current_archive import native_occupation_groups, path_functions, writer
from opentrack_ai.current_archive.itinerary_edit_tools import _margin_members, _margin_values, set_safety_margins
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.multistation_timetable.topology import generate_network_project
from opentrack_ai.current_archive.saved_geometry import _movement_manifest, model_id, project_from, transform
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_itinerary_lifecycle import course_archive
from test_itinerary_native_edit import schematic_document
from test_saved_geometry import shapes_for


@pytest.fixture(scope='module')
def chain():
    header, _ = schematic_document(generate.spec(), [('left', 0)])
    train_list = native.obj([('OTTrainList', 3), ('OTMutableArray', 0), ('NSObject', 0)], [
        ('i', [17]), *[('@', [native.arr()]) for _ in range(3)],
    ])
    timetable = native.obj([('NSMutableDictionary', 0), ('NSDictionary', 0), ('NSObject', 0)], [('i', [0])])
    sources = {'header': header, 'shapes': shapes_for(header), 'depot': writer.dump_verified(native.arr()),
               'trains': writer.dump_verified(train_list), 'courses': course_archive(),
               'timetable': writer.dump_verified(timetable)}
    files, initial = generate_network_project(sources, expected_hashes={key: sha(item) for key, item in sources.items()}, spec={
        'topology': 'chain', 'execution_root': 'D:/test-three-document-route', 'half_link_length_m': 500,
        'stations': [{'id': name, 'name': 'Station ' + name} for name in ('A', 'B', 'C')],
    })
    paths = initial['document_paths']
    docs = {name: files[f'OTDocuments/{name}.opentrack'] for name in paths}
    catalog = files['OTData/chain.dest']

    def edit(name, operation):
        updated, receipt = transform(docs, paths, catalog, name, operation, shapes=sources['shapes'])
        docs.update(updated)
        return receipt

    def vertex(name, x):
        return edit(name, {'action': 'insert_vertex', 'x': x, 'y': 86, 'orientation': 'horizontal',
                           'names': ['', '']})['added_vertex_end_ids']

    def edge(name, start, stop, length):
        return edit(name, {'action': 'insert_edge', 'end_ids': [start, stop], 'length_m': length,
            'radius_m': 0, 'gradient_per_mille': 0, 'rack_rail': False, 'remark': '', 'track_name': 'Alternate',
            'line_name': 'chain', 'allow_safety_regroup': False,
            'speeds': [{'train_type': '0', 'speed12_kmh': 75, 'speed21_kmh': 75}]})['edge_id']

    def end_ref(name, item):
        return {'document': name, 'end_id': item}

    sections = []
    for left, right, half_length in (('A', 'B', 520), ('B', 'C', 530)):
        approach, sender = vertex(left, 414)
        receiver, exit = vertex(right, 40)
        edges = [(left, edge(left, 13, approach, half_length)), (right, edge(right, 4, exit, half_length))]
        edit(left, {'action': 'replace_connectors', 'unlink': [],
                    'link': [{'a': end_ref(left, sender), 'b': end_ref(right, receiver)}]})
        project = project_from(docs, paths, catalog)
        sections.append({'start_end': end_ref(left, 13), 'expected_replacement_length_m': half_length * 2,
            'old_edges': [{'document': left, 'edge_id': 23}, {'document': right, 'edge_id': 20}],
            'replacement_edges': [{'document': name, 'edge_id': local_id} for name, local_id in edges],
            'expected_replacement_safety_elements': [
                {'document': item[0], 'element_id': model_id(project.model(item).contents[7].value.contents[7].value)}
                for item in edges]})
    operation = {'action': 'reroute_multi_document_track_span', 'witness_itinerary': 'I:chain:forward',
                 'expected_witness_length_m': 4100, 'crossings': sections}
    return docs, paths, catalog, operation


def test_two_distinct_replacements_rebind_three_documents_and_keep_middle_station(chain):
    docs, paths, catalog, operation = chain
    updated, report = transform(docs, paths, catalog, 'A', operation)
    fresh = project_from(updated, paths, catalog)
    assert report['changed_documents'] == report['witness_crossing_documents'] == ['A', 'B', 'C']
    assert report['witness_old_length_m'] == 4000 and report['witness_new_length_m'] == 4100
    assert report['witness_station_markers'] == [(('A', 8), 'A'), (('B', 8), 'B'), (('C', 8), 'C')]
    assert report['destination_catalog_unchanged']
    assert all(row['continuation_ownership_verified'] for row in report['crossing_edits'])
    new_pairs = report['replacement_connector_pairs']
    assert all(fresh.block_end(a) == b and fresh.block_end(b) == a for a, b in new_pairs)
    assert fresh.block_end(('A', 17)) == ('B', 0) and fresh.block_end(('B', 17)) == ('C', 0)
    assert [row['source_document'] for row in fresh.continuations] == ['A', 'B', 'B', 'C']


def test_two_retirements_commit_across_three_documents_with_middle_station_kept(chain):
    docs, paths, catalog, operation = chain
    retained, _ = transform(docs, paths, catalog, 'A', operation)
    request = deepcopy(operation)
    for crossing in request['crossings']:
        crossing['retire_original'] = True
    updated, report = transform(docs, paths, catalog, 'A', request)
    actual = project_from(updated, paths, catalog)
    expected = project_from(retained, paths, catalog)
    assert _movement_manifest(expected) == _movement_manifest(actual)
    assert all(not row['original_connector_pair_retained'] for row in report['crossing_edits'])
    for pair in report['original_connector_pairs']:
        assert all(key not in actual.byid[doc] for doc, key in pair)
    for pair in report['replacement_connector_pairs']:
        assert actual.block_end(pair[0]) == pair[1]
    assert report['witness_station_markers'] == [(('A', 8), 'A'), (('B', 8), 'B'), (('C', 8), 'C')]


def test_one_middle_document_group_moves_in_order_across_both_crossings(chain):
    base, paths, catalog, operation = chain
    docs = dict(base)
    docs['B'], _ = native_occupation_groups.transform(docs['B'], 'B', [
        {'action': 'create', 'name': 'BothApproaches', 'edge_ids': [20, 23]},
    ])
    request = deepcopy(operation)
    expected = [20, 23]
    for index, section in enumerate(request['crossings']):
        edge = next(ref['edge_id'] for ref in section['replacement_edges'] if ref['document'] == 'B')
        section['retire_original'] = True
        section['occupation_group_rebindings'] = [{'document': 'B', 'name': 'BothApproaches', 'expected_edge_ids': expected[:],
            'edge_rebindings': [{'old_edge_id': expected[index], 'new_edge_ids': [edge]}]}]
        expected[index] = edge
    updated, report = transform(docs, paths, catalog, 'A', request)
    checked = project_from(updated, paths, catalog)
    row, = native_occupation_groups.records(checked.roots['B'], 'B')
    assert row['edge_ids'] == expected
    assert all(step['dependency_transfers']['native_readback_verified'] for step in report['crossing_edits'])


def test_batch_rebinds_one_original_monitor_for_both_crossings_and_updates_reviewed_turnout(chain):
    base, paths, catalog, operation = chain
    docs = dict(base)
    docs['B'], _ = native_occupation_groups.transform(docs['B'], 'B', [
        {'action': 'create', 'name': 'BothApproaches', 'edge_ids': [20, 21, 23], 'selected': True},
    ])
    request = deepcopy(operation)
    edge_ids = [next(row['edge_id'] for row in span['replacement_edges'] if row['document'] == 'B')
                for span in request['crossings']]
    request['occupation_group_rebindings'] = [{'document': 'B', 'name': 'BothApproaches',
        'expected_edge_ids': [20, 21, 23], 'edge_rebindings': [{'old_edge_id': 20, 'new_edge_ids': edge_ids[:1]},
                                                               {'old_edge_id': 23, 'new_edge_ids': edge_ids[1:]}]}]
    a_new = request['crossings'][0]['replacement_edges'][0]['edge_id']
    request['turnout_updates'] = [{'end': {'document': 'A', 'end_id': 13}, 'expected_edge_ids': [23, a_new],
        'expected_default_edge_id': 23, 'expected_switch_time_s': 0, 'default_edge_id': a_new, 'switch_time_s': 2.5}]
    updated, report = transform(docs, paths, catalog, 'A', request)
    after = project_from(updated, paths, catalog)
    row, = native_occupation_groups.records(after.roots['B'], 'B')
    assert row['edge_ids'] == [edge_ids[0], 21, edge_ids[1]] and row['selected']
    assert report['batch_dependency_transfers']['occupation_group_rebindings'][0]['before']['edge_ids'] == [20, 21, 23]
    turnout, = report['turnout_updates']
    assert turnout['after'] == {'edge_ids': [23, a_new], 'default_edge_id': a_new, 'switch_time_s': 2.5}
    end = after.model(('A', 13))
    assert end.contents[21].value == 2.5 and end.contents[22].value == 1

    bad = deepcopy(request)
    bad['turnout_updates'][0]['expected_edge_ids'].reverse()
    with pytest.raises(ValueError, match='original turnout legs'):
        transform(docs, paths, catalog, 'A', bad)
    bad = deepcopy(request)
    bad['crossings'][0]['retire_original'] = True
    with pytest.raises(ValueError, match='turnout legs present|legs must remain'):
        transform(docs, paths, catalog, 'A', bad)


def test_overlapping_or_wrong_length_requests_leave_source_intact(chain):
    docs, paths, catalog, operation = chain
    original = dict(docs)
    crossing = operation['crossings'][0]
    with pytest.raises(ValueError, match='disjoint and follow'):
        transform(docs, paths, catalog, 'A', {**operation, 'crossings': [crossing, crossing]})
    with pytest.raises(ValueError, match='Final witness distance differs'):
        transform(docs, paths, catalog, 'A', {**operation, 'expected_witness_length_m': 4110})
    assert docs == original


def test_margin_positions_follow_both_ordered_length_changes(chain):
    base, paths, catalog, operation = chain
    docs = dict(base)
    docs['A'], _ = set_safety_margins(docs['A'], 'I:chain:forward', [
        {'position_m': position, 'safety_margin_m': value} for position, value in ((500, 30), (1000, 35), (3000, 40), (3600, 45))
    ])
    confirmed = deepcopy(operation)
    for crossing in confirmed['crossings']:
        crossing['map_itinerary_safety_margins'] = True
    updated, result = transform(docs, paths, catalog, 'A', confirmed)
    assert all(len(row['mapped_safety_margin_profiles']) == 1 for row in result['crossing_edits'])
    project = project_from(updated, paths, catalog)
    target, = [dest for dest in project.dests if path_functions.string(dest.contents[1].value) == 'I:chain:forward']
    assert _margin_values(_margin_members(target)[2]) == [{'position_m': position, 'safety_margin_m': value}
        for position, value in ((500, 30), (1020, 35), (3070, 40), (3700, 45))]
