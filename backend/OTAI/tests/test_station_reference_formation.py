"""Check a projected native formation while keeping its geometry independent of chainage."""

from types import SimpleNamespace

import pytest

from opentrack_ai.current_archive import catalogs, course_factories, network_composition_plan, writer
from opentrack_ai.current_archive import station_reference_formation as formation
from test_course_formation_rebind import formation_source


EVENT = {'kind': 'join', 'main_course': 'A01', 'other_course': 'A02', 'station_sign': 'RDG', 'main_visit_index': 1}


def _fixture(monkeypatch, *, revised_offset=500, occupied=True):
    members = formation_source()
    catalog, version = writer.load_next_compatible(members['courses'])
    first, second = catalogs.course_items(catalog)
    for obj in (first, second):
        obj.contents[5].value = 1
    writer.set_elements(second.contents[2].value, [course_factories.string(second, 'I Supplier')])
    members['courses'] = writer.dump_verified(catalog, version)
    state = {'files': members, 'roles': {key: key for key in members}, 'run': b'TrainType#main#\n'}

    def visit(sign, end, head, distance):
        stop = {'end_key': ('Line', end), 'signal_id': end + 100, 'stop_edge_key': ('Line', 45),
                'head_edge_offset_m': head, 'available_length_m': 500, 'distance_m': distance}
        return {'station_sign': sign, 'end_key': ('Line', end), 'stop_edge_key': ('Line', 45),
                'stop_edge_length_m': 500, 'incoming_track_id': '1', 'default_stop': stop}

    def trace(project, name, _category, _speed):
        origin = visit('EA', 5 if project.revised else 3, 0, 0)
        edge = visit('RDG', 18, project.stop_offset, 1500 if project.revised else 1600)
        end = visit('WB', 31, 500, 2500 if project.revised else 2600)
        return {'visits': [origin, edge, end] if name == 'I Main' else [origin, edge]}

    route = SimpleNamespace(contents={6: SimpleNamespace(values=[3, 20., 0.])})
    signal = SimpleNamespace(contents={0: SimpleNamespace(value=30), 9: SimpleNamespace(values=[0, 0, int(occupied)])})
    previous = SimpleNamespace(dests=['I Main', 'I Supplier'], revised=False, stop_offset=500, owners={id(route): ('Line', 5)})
    target = SimpleNamespace(dests=previous.dests, revised=True, stop_offset=revised_offset, owners=previous.owners)
    monkeypatch.setattr(formation, 'ident', lambda name: (name, -1, -1))
    monkeypatch.setattr(formation, 'route_trace', trace)
    monkeypatch.setattr('opentrack_ai.current_archive.course_formation_rebind.ident', lambda name: (name, -1, -1))
    monkeypatch.setattr(network_composition_plan, '_arrival_route', lambda *args: route)
    monkeypatch.setattr(network_composition_plan, '_entry_signal', lambda *args: ('Line', signal))
    monkeypatch.setattr(network_composition_plan, '_route_name', lambda item: 'Supply')
    return state, previous, target


def test_native_join_slots_and_exact_consist_lengths_survive_remote_endpoint_shift(monkeypatch):
    state, old, new = _fixture(monkeypatch)
    result = formation.review_endpoint_formations(state, old, new, {'A01'}, [EVENT])
    receiver, feeder = result['projected_composition']['events'][0]['initial_main'], result['projected_composition']['events'][0]['initial_other']
    incoming, supply = receiver['length_m'], feeder['length_m']
    assert result['course_ids'] == {'A01', 'A02'} and result['split_origins'] == set()
    assert result['berth_relocations'] == {}
    assert result['connection_rows'] == {('A01', 1, 0), ('A02', 1, 0)}
    assert result['formation_by_visit'] == {'A01': [
        (incoming, incoming), (incoming, incoming + supply), (incoming + supply, incoming + supply)]}
    event, = result['receipts']
    assert event['unchanged_physical_heads']['A01']['head_edge_offset_m'] == 500
    assert event['before']['native_occupied_entry'] == event['after']['native_occupied_entry']
    assert formation.endpoint_formation_turnrounds(state, result, []) == {}
    with pytest.raises(ValueError, match='join-supply exit'):
        formation.endpoint_formation_turnrounds(state, result, [
            {'from_course': 'A02', 'to_course': 'A01', 'movement': 'continue'}])


def test_saved_join_guard_rejects_physical_shift_and_missing_occupied_entry(monkeypatch):
    state, old, revised = _fixture(monkeypatch, revised_offset=499)
    with pytest.raises(ValueError, match='move the actual formation stopping point'):
        formation.review_endpoint_formations(state, old, revised, {'A01'}, [EVENT])
    state, old, revised = _fixture(monkeypatch, occupied=False)
    with pytest.raises(ValueError, match='explicitly allow occupied entry'):
        formation.review_endpoint_formations(state, old, revised, {'A01'}, [EVENT])


def test_formation_selection_stays_within_the_affected_archived_chain(monkeypatch):
    state, old, new = _fixture(monkeypatch)
    with pytest.raises(ValueError, match='participants? must be in the affected saved Connection6 chain'):
        formation.review_endpoint_formations(state, old, new, {'Other'}, [EVENT])
    with pytest.raises(ValueError, match='requires the original station and occupied-entry settings'):
        formation.review_endpoint_formations(state, old, new, {'A01'}, [{**EVENT, 'target_station_sign': 'Another'}])


def test_split_berth_review_requires_exact_retained_signal_and_physical_head():
    before = {'document': 'R2', 'end_id': 108, 'signal_id': 384, 'edge_id': 318, 'edge_offset_m': 500,
              'platform_edge_ids': [318], 'available_length_m': 500}
    after = {**before, 'end_id': 112, 'edge_id': 319, 'edge_offset_m': 100,
             'platform_edge_ids': [318, 319], 'available_length_m': 600}
    request = {'expected_head': before, 'replacement_head': after}
    with pytest.raises(ValueError, match='matching formation event'):
        formation._read_formation_events([{**EVENT, 'split_berth_relocation': request}])
    review = {**EVENT, 'kind': 'split', 'split_berth_relocation': request}
    with pytest.raises(ValueError, match='retain the native main signal'):
        formation._read_formation_events([{**review, 'split_berth_relocation': {
            **request, 'replacement_head': {**after, 'signal_id': 385}}}])
    events, moved = formation._read_formation_events([review])
    event, = events
    witnesses = moved[('A01', 1, 'A02')]
    assert formation._native_berth_request(after) == {
        'station_end': {'document': 'R2', 'end_id': 112}, 'signal_id': 384,
        'head': {'document': 'R2', 'edge_id': 319, 'offset_m': 100},
        'platform_edges': [{'document': 'R2', 'edge_id': 318}, {'document': 'R2', 'edge_id': 319}],
    }
    fixed = {'native_occupied_entry': None, 'receiver_before_m': 418, 'secondary_length_m': 209,
             'receiver_projected_after_m': 209, 'receiver_visit_index': 1}
    receipt = {side: {**fixed, 'native_split_berth': {
        'available_length_m': point['available_length_m'], 'head_distance_m': distance}}
        for side, point, distance in (('before', before, 30000), ('after', after, 30100))}

    def trace(_course, revised):
        point, distance = (after, 30100) if revised else (before, 30000)
        return [{'visits': [{}, {'default_stop': {'distance_m': distance, 'end_key': ('R2', point['end_id']),
            'signal_id': point['signal_id'], 'stop_edge_key': ('R2', point['edge_id']),
            'head_edge_offset_m': point['edge_offset_m']}}]}]

    lengths = {'A01': [(418, 418), (418, 209), (209, 209)]}
    report, proof = formation._moved_formation_berth(receipt, event, trace, lengths, witnesses)
    assert proof['kind'] == 'split' and report['split_berth_relocation'] == {
        side: proof[side] for side in ('before', 'after')}
    assert proof['after'] == {'available_length_m': 600, 'head_distance_m': 30100, 'arrival_length_m': 418,
                              'retained_length_m': 209, 'split_child_course_id': 'A02', 'split_child_length_m': 209}
    mismatched = {**witnesses, 'after': {**after, 'available_length_m': 599}}
    with pytest.raises(ValueError, match='available platform length differs'):
        formation._moved_formation_berth(receipt, event, trace, lengths, mismatched)


def test_join_contact_retains_the_saved_approach_and_moves_with_the_berth():
    old = {'document': 'R4', 'end_id': 108, 'signal_id': 384, 'edge_id': 318, 'edge_offset_m': 500,
           'platform_edge_ids': [318], 'available_length_m': 500}
    revised = {**old, 'end_id': 112, 'edge_id': 319, 'edge_offset_m': 100,
               'platform_edge_ids': [318, 319], 'available_length_m': 600}
    approvals = {'expected_head': old, 'replacement_head': revised}
    events, moved = formation._read_formation_events([{**EVENT, 'join_berth_relocation': approvals}])
    event, = events
    relocation = moved[('A01', 1, 'A02')]
    assert relocation['kind'] == 'join'
    assert formation._native_berth_request(revised)['head'] == {'document': 'R4', 'edge_id': 319, 'offset_m': 100}
    approach = {'document': 'R4', 'name': 'R_R4_D1_HOME_EXIT', 'start_id': 40, 'array_id': 0}
    occupied = {'signal_id': 401, 'signal_flags': 1, 'route_flags': 3, 'speed_kmh': 20.0, 'wait_s': 0.0,
                'signal_role': 'entry', 'signal_type': 3}
    safety = [{'document': 'R4', 'element_id': 19}, {'document': 'R4', 'element_id': 20}]
    fixed = {'native_occupied_entry': occupied, 'receiver_before_m': 209, 'secondary_length_m': 209,
             'receiver_projected_after_m': 418, 'receiver_visit_index': 1}
    receipt = {side: {**fixed, 'native_join_berth': {
        'arrival_route': approach, 'occupied_entry': occupied, 'contact_safety_elements': safety,
        'available_length_m': point['available_length_m'], 'head_distance_m': distance,
        'contact': {'document': 'R4', 'edge_id': 318, 'offset_m': contact}}}
        for side, point, distance, contact in (('before', old, 30000, 291), ('after', revised, 30100, 391))}

    def trace(_course, after):
        head, distance = (revised, 30100) if after else (old, 30000)
        return [{'visits': [{}, {'default_stop': {'distance_m': distance, 'end_key': ('R4', head['end_id']),
            'signal_id': 384, 'stop_edge_key': ('R4', head['edge_id']), 'head_edge_offset_m': head['edge_offset_m']}}]}]

    lengths = {'A01': [(209, 209), (209, 418), (418, 418)]}
    saved, proof = formation._moved_formation_berth(receipt, event, trace, lengths, relocation)
    assert proof['kind'] == 'join' and saved['join_berth_relocation']['after']['supplying_length_m'] == 209
    assert proof['after']['contact']['offset_m'] == 391 and proof['after']['joined_length_m'] == 418
    for field, value, message in (
        ('arrival_route', {**approach, 'array_id': 1}, 'occupied-entry Route'),
        ('occupied_entry', {**occupied, 'route_flags': 7}, 'occupied-entry Route'),
        ('contact_safety_elements', safety[:1], 'occupied-entry Route'),
        ('contact', {'document': 'R4', 'edge_id': 317, 'offset_m': 391}, 'same physical Edge'),
        ('contact', {'document': 'R4', 'edge_id': 318, 'offset_m': 390}, 'same physical Edge'),
    ):
        newer = {**proof, 'after': {**proof['after'], field: value}}
        with pytest.raises(ValueError, match=message):
            formation._verify_join_contact(newer, relocation)


def test_retained_multiedge_join_only_allows_chainage_changes():
    events, _ = formation._read_formation_events([EVENT])
    event, = events
    nodes = [('R4', 100), ('R4', 108), ('R4', 112)]
    edges = [('R4', 318), ('R4', 319)]
    end = nodes[-1]
    point = {'end_key': end, 'stop_edge_key': edges[-1], 'signal_id': 384,
             'head_edge_offset_m': 100, 'available_length_m': 600}

    def trace(_cid, revised):
        shift = 100 if revised else 0
        return [{'itinerary_name': 'Receiver', '_directed_nodes': nodes,
                 '_node_distances_m': [value - shift for value in (29500, 30000, 30100)],
                 'visits': [{}, {'end_key': end, 'stopping_area_edge_keys': edges, 'default_stop': point}]}]

    request = formation._saved_multiedge_berth(event, trace, {'A01': [(209, 209), (209, 418)]})
    assert request['platform_edges'] == [{'document': sheet, 'edge_id': edge} for sheet, edge in edges]
    native = {**request, 'contact': {'document': 'R4', 'edge_id': 318, 'offset_m': 391},
              'donor_tail': {'document': 'R4', 'edge_id': 318, 'offset_m': 182}}
    receipt = {'before_itinerary_groups': [], 'after_itinerary_groups': []}
    for side, shift in (('before', 0), ('after', 100)):
        receipt[side] = {'receiver_before_m': 209, 'native_join_berth': {
            **native, 'head_distance_m': 30100 - shift, 'donor_nominal_head_distance_m': 60100 - shift,
            'donor_contact_distance_m': 59891 - shift}}

    def graph(safety_element):
        record = SimpleNamespace(contents={7: SimpleNamespace(value=safety_element)})
        return SimpleNamespace(model=lambda _key: record, key=lambda item: ('R4', item), actual_related=lambda key: key)

    destinations = [{'Receiver': None}, {'Receiver': None}]
    stable = formation._keep_multiedge_berth(receipt, event, (graph(107), graph(107)), destinations, trace)
    assert stable['retained_berth']['contact']['offset_m'] == 391
    assert [item['length_m'] for item in stable['retained_berth']['directed_platform']] == [500, 100]
    with pytest.raises(ValueError, match='physical position, directed track or protection'):
        formation._keep_multiedge_berth(receipt, event, (graph(107), graph(108)), destinations, trace)
