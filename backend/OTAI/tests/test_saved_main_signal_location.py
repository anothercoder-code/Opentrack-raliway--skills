"""Verify the original adjacent main-signal action and native reference closure."""

import pytest

from opentrack_ai.current_archive import catalogs, path_functions, route_factory, writer
from opentrack_ai.current_archive.multi_document import generate, operations
from opentrack_ai.current_archive.multi_document.core import ident
from opentrack_ai.current_archive.saved_geometry import project_from, transform
from opentrack_ai.current_archive.tools import sha
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_itinerary_native_edit import schematic_document


def corridor():
    line = generate.spec()
    line['vertices'] = [generate.vertex(name, 50 + 100 * index) for index, name in enumerate('ABCDE')]
    template, = line['edges']
    line['edges'] = [{**template, 'key': a + b, 'from': [a, 1], 'to': [b, 0], 'length_m': 100}
                     for a, b in zip('ABCD', 'BCDE', strict=True)]
    document, ends = schematic_document(line, [(name, 0) for name in 'ACE'])
    names = {'Line': 'OTDocuments/Line.opentrack'}
    docs = {'Line': document}
    dest = writer.dump_verified(generate.wrapped('OTDestInfoList', []))

    def options():
        return {'document_paths': names, 'expected_hashes': {'Line': sha(docs['Line']), '$dest_catalog': sha(dest)},
                'complete_document_set': True}

    keys = {name: ('Line', pair[0]) for name, pair in ends.items()}
    refs = []
    for name, nodes in (('Approach', 'ABC'), ('Departure', 'CDE')):
        docs['Line'], receipt = native.build_route(docs['Line'], name=name, description='',
            end_ids=[keys[node][1] for node in nodes], release_groups='global', reserve_previous=False)
        refs.append({'document': 'Line', 'name': name, 'array_id': receipt['array_id'], 'start_id': keys[nodes[0]][1]})
    paths = []
    for route in refs:
        docs, receipt = operations.create_path(docs, dest, name='P:' + route['name'], routes=[route], **options())
        paths.append(receipt['created'])
    for name, selected in (('Through', paths), ('FromSignal', paths[1:])):
        output, _ = operations.create_itinerary(docs, dest, name=name, paths=selected, **options())
        docs, dest = output['documents'], output['catalog']
    return docs, names, dest, keys


@pytest.mark.parametrize(('direction', 'target', 'approach', 'exit'), [
    ('forward', 'D', 'ABCD', 'DE'),
    ('backward', 'B', 'AB', 'BCDE'),
])
def test_relocate_maintains_counter_ids_paths_and_durable_dest_references(direction, target, approach, exit):
    docs, names, dest, keys = corridor()
    base = project_from(docs, names, dest)
    source_signal = base.model(keys['C']).contents[11].value
    adjacent = base.edge_between(keys['C'], keys[target]) if direction == 'forward' else (
        base.edge_between(keys[target], keys['C']))
    op = {'action': 'relocate_main_signal', 'signal_id': source_signal.contents[0].value,
          'from_end_id': keys['C'][1], 'to_end_id': keys[target][1], 'direction': direction, 'expected_edge_id': adjacent[1]}
    changes, report = transform(docs, names, dest, 'Line', op)
    assert set(changes) == {'Line', '$dest_catalog'}
    saved = project_from({'Line': changes['Line']}, names, changes['$dest_catalog'])
    assert saved.model(keys['C']).contents[11].value is None
    signal = saved.model(keys[target]).contents[11].value
    assert signal.contents[0].value == op['signal_id']
    assert signal.contents[7].value is saved.model(keys[target])
    assert signal.contents[8].values == source_signal.contents[8].values
    assert all(row.contents[1].value is saved.model(keys[target])
               for row in route_factory.wrapper(signal.contents[10].value, 'OTSigIndList'))
    old_routes = {ident(row)[0]: ident(row) for row in base.routes}
    routes = {ident(row)[0]: row for row in saved.routes}
    assert ident(routes['Departure']) == ('Departure', old_routes['Departure'][1], keys[target][1])
    for name, expected in (('Approach', approach), ('Departure', exit)):
        row = routes[name]
        vertices = [keys[node] for node in expected]
        assert saved.route_view(row) == vertices
        assert [saved.key(item) for item in path_functions.mutable_array(row.contents[12].values[0])] == (
            [vertices[0], vertices[-1]])
    itineraries = {ident(row)[0]: saved.dest_view(row) for row in saved.dests}
    assert itineraries['Through'][0] == [keys[node] for node in 'ABCDE']
    assert itineraries['FromSignal'][0] == [keys[node] for node in exit]
    root, _ = writer.load(changes['$dest_catalog'])
    updated = {catalogs.text(row.contents[1].value): row for row in route_factory.wrapper(root, 'OTDestInfoList')}
    assert updated['FromSignal'].contents[3].value == keys[target][1]
    assert report['signal_shift_m'] == (100 if direction == 'forward' else -100)
    assert report['nonselected_graph_verified']


def test_relocate_rejects_occupied_target_and_wrong_direction():
    docs, names, dest, keys = corridor()
    graph = project_from(docs, names, dest)
    old = graph.model(keys['C'])
    signal_id = old.contents[11].value.contents[0].value
    op = {'action': 'relocate_main_signal', 'signal_id': signal_id,
          'from_end_id': keys['C'][1], 'to_end_id': keys['E'][1], 'direction': 'forward', 'expected_edge_id': 1}
    with pytest.raises(ValueError, match='free destination'):
        transform(docs, names, dest, 'Line', op)
    with pytest.raises(ValueError, match='next reviewed End'):
        transform(docs, names, dest, 'Line', {**op, 'to_end_id': keys['B'][1]})
