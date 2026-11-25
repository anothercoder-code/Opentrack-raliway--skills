"""Verified stop marker relocation retains native signal and movement identities."""

import pytest

from opentrack_ai.current_archive import path_functions, route_factory, writer
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.saved_geometry import project_from, transform
from opentrack_ai.current_archive.saved_halt_location import _stop_selection
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_itinerary_native_edit import schematic_document
from test_saved_geometry import shapes_for


@pytest.fixture
def case():
    source = generate.spec()
    source['vertices'] = [generate.vertex(key, 80 + 100 * index) for index, key in enumerate('ABCD')]
    edge, = source['edges']
    source['edges'] = [{**edge, 'key': a + b, 'from': [a, 1], 'to': [b, 0], 'length_m': 100}
                       for a, b in ('AB', 'BC', 'CD')]
    blob, ends = schematic_document(source, [(key, 0) for key in 'ABD'])
    root, version = writer.load_next_compatible(blob)
    models, by_id = route_factory.document(root)
    marker = by_id[ends['B'][0]].contents[11].value
    marker.contents[8].values[:] = [6, 1, 0]
    marker_id = marker.contents[0].value
    station_id = max(by_id) + 1
    station = native.obj([('OTStationModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], [
        ('i', [station_id]), ('f', [0.0]), ('f', [100.0]), ('f', [50.0]), ('i', [0]), ('i', [0]),
        ('@', [None]), ('@', [native.string('P9')]), ('ii', [2, 4]), ('ii', [1, 0]),
    ])
    for name in 'ABCD':
        for half in ends[name]:
            by_id[half].contents[12].value = station
            by_id[half].contents[20].value = 2 if name == 'D' else 1
    writer.set_elements(root.contents[2].value, [*models, station])
    directed = [ends[key][0] for key in 'ABCD']
    blob, route = native.build_route(writer.dump_verified(root, version), name='Arrive', end_ids=directed,
                                     description='', release_groups='global', reserve_previous=False)
    docs = {'RDG': blob}
    paths = {'RDG': 'RDG.opentrack'}
    catalog = writer.dump_verified(generate.wrapped('OTDestInfoList', []))
    stored = project_from(docs, paths, catalog)
    edges = [stored.edge_between(('RDG', a), ('RDG', b))[1] for a, b in zip(directed, directed[1:])]
    operation = {
        'action': 'relocate_station_halt_signal', 'station_id': station_id, 'signal_id': marker_id,
        'from_end_id': directed[1], 'to_end_id': directed[2],
        'arrival_route': {'document': 'RDG', 'name': 'Arrive', 'array_id': route['array_id'], 'start_id': directed[0]},
        'expected_platform_edge_ids': edges, 'expected_stop_shift_m': 100,
    }
    return docs, paths, catalog, operation, ends


def test_moves_native_stop_and_reverses_to_own_source_graph(case):
    docs, paths, catalog, operation, _ = case
    output, receipt = transform(docs, paths, catalog, 'RDG', operation)
    checked = project_from(output, paths, catalog)
    previous, following = (checked.model(('RDG', operation[k])) for k in ('from_end_id', 'to_end_id'))
    marker = checked.model(('RDG', operation['signal_id']))
    assert previous.contents[11].value is None and following.contents[11].value is marker
    assert marker.contents[7].value is following
    indication, = route_factory.wrapper(marker.contents[10].value, 'OTSigIndList')
    assert indication.contents[1].value is following
    assert receipt['position_from_platform_entry_before_m'] == 100
    assert receipt['position_from_platform_entry_after_m'] == 200
    assert receipt['nonselected_graph_verified'] and receipt['movement_count_checked'] == 1
    reverse = {**operation, 'from_end_id': operation['to_end_id'], 'to_end_id': operation['from_end_id'],
               'expected_stop_shift_m': -100}
    same, _ = transform(output, paths, catalog, 'RDG', reverse)
    baseline, _ = writer.load_next_compatible(docs['RDG'])
    restored, _ = writer.load_next_compatible(same['RDG'])
    assert writer.fingerprint(restored) == writer.fingerprint(baseline)


def test_refuses_changed_edge_sequence_wrong_direction_or_main_signal(case):
    docs, paths, catalog, operation, ends = case
    graph = project_from(docs, paths, catalog)
    exit_signal = graph.model(('RDG', ends['D'][0])).contents[11].value.contents[0].value
    variants = [
        ({'expected_platform_edge_ids': list(reversed(operation['expected_platform_edge_ids']))}, 'reviewed order'),
        ({'to_end_id': ends['C'][1]}, 'same directed station approach'),
        ({'expected_stop_shift_m': 50}, 'reviewed shift'),
        ({'signal_id': exit_signal}, 'reviewed old End does not carry'),
    ]
    for edits, message in variants:
        with pytest.raises(ValueError, match=message):
            transform(docs, paths, catalog, 'RDG', {**operation, **edits})


def test_move_reviewed_length_marker_preserving_two_marker_selection(case):
    docs, paths, catalog, request, ends = case
    shapes = shapes_for(docs['RDG'])
    output, split = transform(docs, paths, catalog, 'RDG', {'action': 'split_platform_edge',
        'edge_id': request['expected_platform_edge_ids'][-1], 'station_id': request['station_id'],
        'first_length_m': 50}, shapes=shapes)
    root, version = writer.load_next_compatible(output['RDG'])
    models, by_id = route_factory.document(root)
    marker = by_id[request['signal_id']]
    marker.contents[8].values[0] = 51
    next_end = by_id[split['new_end_ids'][0]]
    other = path_functions.clone(marker)
    other_id = max(by_id) + 1
    other.contents[0].value = other_id
    other.contents[8].values[0] = 52
    other.contents[7].value = next_end
    other.contents[10].value = native.wrapped('OTSigIndList', [])
    next_end.contents[11].value = other
    writer.set_elements(root.contents[2].value, [*models, other])
    output['RDG'] = writer.dump_verified(root, version)
    reviewed = {**request, 'expected_platform_edge_ids': [*request['expected_platform_edge_ids'], split['new_edge_id']],
        'expected_halt_signals': [{'signal_id': request['signal_id'], 'end_id': request['from_end_id'], 'signal_type': 51},
                                  {'signal_id': other_id, 'end_id': split['new_end_ids'][0], 'signal_type': 52}]}
    with pytest.raises(ValueError, match='exact ordered expected_halt_signals'):
        transform(output, paths, catalog, 'RDG', {**reviewed, 'expected_halt_signals': None})
    with pytest.raises(ValueError, match='halt signal order or identity'):
        transform(output, paths, catalog, 'RDG', {**reviewed, 'expected_halt_signals': reviewed['expected_halt_signals'][::-1]})
    moved, report = transform(output, paths, catalog, 'RDG', reviewed)
    saved = project_from(moved, paths, catalog)
    exit_signal = saved.model(('RDG', ends['D'][0])).contents[11].value.contents[0].value
    assert report['signal_type'] == 51
    assert report['halt_signals_after'] == [{**reviewed['expected_halt_signals'][0], 'end_id': request['to_end_id']},
                                            reviewed['expected_halt_signals'][1]]
    assert report['stable_stop_signal_selection_by_train_length'] == [
        {'length_gt_m': 0, 'length_lte_m': 150, 'signal_id': request['signal_id']},
        {'length_gt_m': 150, 'length_lte_m': 250, 'signal_id': other_id},
        {'length_gt_m': 250, 'length_lte_m': None, 'signal_id': exit_signal},
    ]
    assert saved.model(('RDG', split['new_end_ids'][0])).contents[11].value is saved.model(('RDG', other_id))


def test_original_length_selection_rejects_reordering_that_captures_another_train_class():
    short = {'signal_id': 41, 'end_id': 7, 'signal_type': 51}
    long = {'signal_id': 42, 'end_id': 9, 'signal_type': 52}
    with pytest.raises(ValueError, match='would change the selected native stop'):
        _stop_selection([short, long], [long, short], 8)
    general = {'signal_id': 43, 'end_id': 10, 'signal_type': 6}
    assert all(row['signal_id'] == general['signal_id']
               for row in _stop_selection([short, long, general], [long, short, general], 8))
