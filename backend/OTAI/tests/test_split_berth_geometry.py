"""Prove a moved native split berth with one physical tail on each possible rail."""

from copy import deepcopy

import pytest

from opentrack_ai.current_archive import course_factories, route_factory, writer
from opentrack_ai.current_archive.multi_document import operations
from opentrack_ai.current_archive.multi_document.core import ident, ref, sha
from opentrack_ai.current_archive.network_composition_plan import (
    _admit_spatial_event, _check_receiver_clearance, _entry_signal, itinerary_routes,
    verify_join_berth_geometry, verify_split_berth_geometry,
)
from opentrack_ai.current_archive.network_operating_plan import _planned_rows, route_trace
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.saved_main_signal_location import relocate_station_main_signal

from test_saved_station_signal_reference import grouped_corridor


EVENT = {'kind': 'split', 'main_course': 'MAIN', 'other_course': 'CHILD',
         'station_sign': 'Platform', 'main_visit_index': 1}
JOIN = {**EVENT, 'kind': 'join', 'other_course': 'DONOR'}


def _point(edge, offset):
    return {'document': 'Line', 'edge_id': edge[1], 'offset_m': offset}


@pytest.fixture(scope='module')
def shifted_berth():
    docs, paths, catalog, keys, station_id, request = grouped_corridor()
    project = project_from(docs, paths, catalog)
    first = project.edge_between(keys['B'], keys['C'])
    second = project.edge_between(keys['C'], keys['D'])
    root, version = writer.load_next_compatible(docs['Line'])
    models, by_id = route_factory.document(root)
    station = by_id[station_id]
    by_id[first[1]].contents[9].values[1] = 200
    by_id[keys['C'][1]].contents[11].value.contents[8].values[1] = 4
    by_id[keys['A'][1]].contents[11].value.contents[9].values[2] |= 1
    approach = next(item for item in writer.objects(root) if writer.kind(item) == 'OTRoute' and ident(item)[0] == 'Approach')
    approach.contents[6].values[:] = [3, 20.0, 0.0]
    added = []
    for label in 'ABE':
        group = station
        if label != 'B':
            group = course_factories.clone(station)
            group.contents[0].value = station_id + len(added) + 1
            course_factories.settext(group, 7, label)
            added.append(group)
        end = by_id[keys[label][1]]
        for member in (end, by_id[end.contents[8].value]):
            member.contents[12].value = group
            member.contents[20].value = 1 if label == 'B' else 2
    writer.set_elements(root.contents[2].value, [*models, *added])
    docs = {'Line': writer.dump_verified(root, version)}
    approach_path = next(item for item in project.paths_objects if ident(item)[0] == 'P:Approach')
    written, _ = operations.create_itinerary(docs, catalog, name='ToPlatform', paths=[{'document': 'Line', **ref(approach_path)}],
        document_paths=paths, expected_hashes={'Line': sha(docs['Line']), '$dest_catalog': sha(catalog)}, complete_document_set=True)
    docs, catalog = written['documents'], written['catalog']
    original = project_from(docs, paths, catalog)
    changed, _ = relocate_station_main_signal(docs, paths, catalog, 'Line', request, None, station_id=station_id)
    revised = project_from({'Line': changed['Line']}, paths, changed['$dest_catalog'])
    shapes = []
    for graph, end, edges, offset in ((original, keys['C'], [first], 200), (revised, keys['D'], [first, second], 100)):
        defs = {ident(obj)[0]: obj for obj in graph.dests}

        def report(name, formation, leading_stop):
            trace = route_trace(graph, defs[name])
            visits = [{**row, 'planned': {'stop': row['station_sign'] == 'Platform', 'track_id': '',
                                          'arrival_s': (2000 if name == 'ToPlatform' else 1000) + index}}
                      for index, row in enumerate(trace['visits'])]
            assert visits[0]['planned']['stop'] == leading_stop
            return {'itinerary': name, '_formation_trace': trace, 'visits': visits,
                    'consist_length_m': formation, 'maximum_speed_kmh': 120}

        reports = {'MAIN': report('Through', 180, False), 'CHILD': report('FromSignal', 110, True),
                   'DONOR': report('ToPlatform', 30, False)}
        expected = {'station_end': {'document': 'Line', 'end_id': end[1]}, 'signal_id': request['signal_id'],
                    'platform_edges': [{'document': 'Line', 'edge_id': edge[1]} for edge in edges],
                    'head': _point(edges[-1], offset)}
        shapes.append((graph, defs, reports, expected))
    return (*shapes, first, second)


def _verify(shape, expected=None):
    graph, defs, reports, review = shape
    return verify_split_berth_geometry(graph, EVENT, reports['MAIN'], reports['CHILD'], defs,
                                       review if expected is None else expected, arrival_length_m=180, retained_length_m=70)


def test_split_chain_uses_the_actual_head_and_positions_both_tails(shifted_berth):
    old, changed, first, second = shifted_berth
    previous, update = _verify(old), _verify(changed)
    assert previous['arrival_tail'] == _point(first, 20)
    assert previous['retained_tail'] == _point(first, 130)
    assert (update['available_length_m'], update['head_distance_m']) == (300, 400)
    assert update['arrival_tail'] == _point(first, 120)
    assert update['retained_tail'] == _point(second, 30)
    assert update['child_first_route']['name'] == 'Departure'
    assert update['child_first_route']['start_id'] == update['station_end']['end_id']
    assert update['native_birth']['match'] == 'exact'
    assert update['native_birth']['birth_sim_position'] == {'dest_index': 0, 'route_index': 0, 'end_index': 0, 'offset_m': 0}


def test_only_exact_ordered_berth_and_matching_child_origin_are_admitted(shifted_berth):
    _, changed, _, _ = shifted_berth
    graph, defs, reports, review = changed
    wrong = {**review, 'platform_edges': list(reversed(review['platform_edges']))}
    with pytest.raises(ValueError, match='ordered platform Edges differ'):
        _verify(changed, wrong)
    wrong = deepcopy(reports['CHILD'])
    wrong['visits'][0]['end_key'] = reports['MAIN']['visits'][0]['end_key']
    with pytest.raises(ValueError, match='same directed child origin'):
        verify_split_berth_geometry(graph, EVENT, reports['MAIN'], wrong, defs, review,
                                   arrival_length_m=180, retained_length_m=70)


def test_legacy_single_edge_and_planned_row_checks_only_release_verified_visit(shifted_berth):
    _, changed, _, _ = shifted_berth
    graph, defs, reports, _ = changed
    with pytest.raises(ValueError, match='must fit the directed stopping Edge'):
        _admit_spatial_event(graph, EVENT, reports, defs)
    proof = _verify(changed)
    spatial = _admit_spatial_event(graph, EVENT, reports, defs, split_berth=proof)
    assert _check_receiver_clearance(reports, [{**EVENT, 'spatial': spatial}])['MAIN'] == [{
        'visit_index': 1, 'station_sign': 'Platform', 'available_length_m': 300,
        'arrival_length_m': 180, 'departure_length_m': 70,
    }]
    trace = reports['MAIN']['_formation_trace']
    visits = [{'station_sign': item['station_sign'], 'stop': i == 1, 'arrival_s': 100 * (i + 1),
               'departure_s': 100 * (i + 1) + (40 if i == 1 else 0), 'track_id': ''}
              for i, item in enumerate(trace['visits'])]
    options = {'formation_by_visit': [(180, 180), (180, 70), (70, 70)]}
    args = ({'visits': visits}, trace, {'length_m': 180}, {visit['station_sign']: None for visit in visits}, 'fixture', 0, 500)
    with pytest.raises(ValueError, match='on the directed stopping Edge'):
        _planned_rows(*args, **options)
    resolved = []
    _planned_rows(*args, **options, verified_split_berth_indices={1}, resolved_visits=resolved)
    assert resolved[1]['stopping_point']['head_edge_offset_m'] == 100
    assert resolved[1]['stopping_point']['available_length_m'] == 300


def test_join_uses_actual_receiver_tail_on_the_shared_occupied_entry_route(shifted_berth):
    old, changed, first, second = shifted_berth

    def contact(shape):
        graph, defs, reports, review = shape
        return verify_join_berth_geometry(graph, JOIN, reports['MAIN'], reports['DONOR'], defs, review,
                                         arrival_length_m=160, joined_length_m=190)

    before, after = contact(old), contact(changed)
    assert (before['head'], after['head']) == (_point(first, 200), _point(second, 100))
    assert (before['contact'], after['contact']) == (_point(first, 40), _point(first, 140))
    assert (before['donor_tail'], after['donor_tail']) == (_point(first, 10), _point(first, 110))
    assert after['donor_nominal_head_distance_m'] == 400 and after['donor_contact_distance_m'] == 240
    assert before['contact_safety_elements'] == after['contact_safety_elements']
    assert before['arrival_route'] == after['arrival_route'] and after['arrival_route']['name'] == 'Approach'
    assert before['occupied_entry'] == after['occupied_entry']
    assert (after['occupied_entry']['route_flags'], after['occupied_entry']['speed_kmh']) == (3, 20)


def test_join_rejects_loss_of_native_occupied_entry_permission(shifted_berth):
    _, (graph, defs, reports, review), _, _ = shifted_berth
    arrival, = list(itinerary_routes(graph, defs['ToPlatform']))
    _, entry_signal = _entry_signal(graph, arrival)
    flags = entry_signal.contents[9].values[2]
    try:
        entry_signal.contents[9].values[2] = flags & ~1
        with pytest.raises(ValueError, match='entrance Signal must both admit the join'):
            verify_join_berth_geometry(graph, JOIN, reports['MAIN'], reports['DONOR'], defs, review,
                                      arrival_length_m=160, joined_length_m=190)
    finally:
        entry_signal.contents[9].values[2] = flags
