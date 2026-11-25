"""Native signal, station reference, and dependent movements relocate together."""

import pytest

from opentrack_ai.current_archive import catalogs, path_functions, route_factory, writer
from opentrack_ai.current_archive.multi_document.core import ident
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.saved_main_signal_location import (
    _shift,
    relocate_main_signal,
    relocate_station_main_signal,
)
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_saved_main_signal_location import corridor


def grouped_corridor():
    docs, paths, dest, keys = corridor()
    root, version = writer.load_next_compatible(docs['Line'])
    models, by_id = route_factory.document(root)
    station_id = max(by_id) + 1
    station = native.obj([('OTStationModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], [
        ('i', [station_id]), ('f', [0.0]), ('f', [120.0]), ('f', [50.0]), ('i', [0]), ('i', [0]),
        ('@', [None]), ('@', [native.string('Platform')]), ('ii', [2, 4]), ('ii', [1, 0]),
    ])
    for name, kind in (('C', 2), ('D', 1)):
        end = by_id[keys[name][1]]
        for member in (end, by_id[end.contents[8].value]):
            member.contents[12].value = station
            member.contents[20].value = kind
    writer.set_elements(root.contents[2].value, [*models, station])
    docs = {'Line': writer.dump_verified(root, version)}
    before = project_from(docs, paths, dest)
    request = {'action': 'relocate_main_signal', 'from_end_id': keys['C'][1], 'to_end_id': keys['D'][1],
               'signal_id': before.model(keys['C']).contents[11].value.contents[0].value,
               'expected_edge_id': before.edge_between(keys['C'], keys['D'])[1], 'direction': 'forward'}
    return docs, paths, dest, keys, station_id, request


def test_joint_move_preserves_signal_and_updates_same_station_pairs_routes_paths_and_dest_index():
    docs, paths, dest, keys, station_id, request = grouped_corridor()
    with pytest.raises(ValueError, match='would gain or lose a station reference'):
        relocate_main_signal(docs, paths, dest, 'Line', request, None)
    changed, receipt = relocate_station_main_signal(docs, paths, dest, 'Line', request, None, station_id=station_id)
    assert changed.keys() == {'Line', '$dest_catalog'}
    before = project_from(docs, paths, dest)
    after = project_from({'Line': changed['Line']}, paths, changed['$dest_catalog'])
    assert before.model(keys['C']).contents[11].value.contents[0].value == request['signal_id']
    assert after.model(keys['C']).contents[11].value is None
    signal = after.model(keys['D']).contents[11].value
    assert signal.contents[0].value == request['signal_id']
    assert signal.contents[7].value is after.model(keys['D'])
    station = after.model(('Line', station_id))
    for key, kind in ((keys['C'], 1), (keys['D'], 2)):
        for member in (key, after.related(key)):
            end = after.model(member)
            assert end.contents[12].value is station and end.contents[20].value == kind
    moves = {ident(route)[0]: route for route in after.routes}
    for name, expected in (('Approach', 'ABCD'), ('Departure', 'DE')):
        route = moves[name]
        nodes = [keys[key] for key in expected]
        assert after.route_view(route) == nodes
        assert [after.key(end) for end in path_functions.mutable_array(route.contents[12].values[0])] == [nodes[0], nodes[-1]]
    itineraries = {ident(item)[0]: after.dest_view(item) for item in after.dests}
    assert itineraries['Through'][0] == [keys[key] for key in 'ABCDE']
    assert itineraries['FromSignal'][0] == [keys['D'], keys['E']]
    catalog, _ = writer.load_next_compatible(changed['$dest_catalog'])
    indexed = {catalogs.text(row.contents[1].value): row for row in route_factory.wrapper(catalog, 'OTDestInfoList')}
    assert indexed['FromSignal'].contents[3].value == keys['D'][1]
    assert receipt['changed_itinerary_endpoints'] == [{'itinerary': 'FromSignal', 'original_start': keys['C'],
        'replacement_start': keys['D'], 'original_end': keys['E'], 'replacement_end': keys['E']}]


def test_joint_move_requires_exact_station_identity():
    docs, paths, dest, keys, _, request = grouped_corridor()
    with pytest.raises(ValueError, match='OTStationModel'):
        relocate_station_main_signal(docs, paths, dest, 'Line', request, None, station_id=keys['D'][1])


def test_closed_itinerary_keeps_both_occurrences_at_the_relocated_signal():
    assert _shift(list('ABCA'), 'A', 'B', True, keep_closed_reference=True) == list('BCAB')
    assert _shift(list('ABCA'), 'A', 'C', False, keep_closed_reference=True) == list('CABC')
