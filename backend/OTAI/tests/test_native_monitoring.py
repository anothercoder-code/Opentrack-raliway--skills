import pytest

from opentrack_ai.current_archive import native_monitoring as monitor, route_factory, writer as w
from opentrack_ai.current_archive.native_monitoring_formats import instruments, occupation_statistics, power_supply
from opentrack_ai.current_archive.zero_generation import native_signal_routes as ns


GRAPHIC = ('OTGraphicModel', 1)
OBJECT = ('NSObject', 0)


def graphic(class_name, version, encodings):
    defaults = {'i': 0, 'f': 0.0, '@': None}
    return ns.obj([(class_name, version), GRAPHIC, OBJECT],
                  [(encoding, [defaults[x] for x in encoding]) for encoding in encodings])


def array(entries=()):
    return ns.obj([('NSMutableArray', 0), ('NSArray', 0), OBJECT],
                  [('i', [len(entries)])] + [('@', [value]) for value in entries])


def doc(version, models):
    layout = monitor.DOCUMENT3 + (['i', '@'] if version == 4 else [])
    graph = ns.obj([('OTDocument', version), OBJECT], [
        (group, [None if c == '@' else 0.0 if c == 'f' else 0 for c in group]) for group in layout
    ])
    graph.contents[2].value = array(models)
    return w.dump_verified(graph)


@pytest.fixture
def worksheets():
    color = ns.obj([('NSColor', 0), OBJECT], [('i', [0]), ('ffff', [0.0, 0.0, 0.0, 1.0])])
    power = graphic('OTPowerSupplyModel', 2, monitor.SUPPLY)
    power.contents[0].value = 775
    power.contents[7].value = ns.string('Stock Power')
    power.contents[8].values = [2, 0, 0, 0]
    power.contents[9].value = color
    power.contents[11].value = 1
    power.contents[12].value = array()
    measuring = graphic('OTMeasuringModel', 3, monitor.INSTRUMENT)
    measuring.contents[0].value = 796
    measuring.contents[8].value = 3
    measuring.contents[9].values = [10.0, 20.0]
    measuring.contents[10].values = [80.0, 42.0]
    measuring.contents[11].value = ns.string('Stock Monitor')
    measuring.contents[12].value = array()
    measuring.contents[13].value = color
    measuring.contents[14].value = color
    measuring.contents[16].value = 3
    donor = doc(3, [power, measuring])
    end = graphic('OTEndModel', 7, route_factory.END)
    opposite = graphic('OTEndModel', 7, route_factory.END)
    first = graphic('OTEdgeModel', 3, route_factory.EDGE)
    second = graphic('OTEdgeModel', 3, route_factory.EDGE)
    signal = graphic('OTSignalModel', 11, route_factory.SIGNAL)
    for index, row in enumerate((end, opposite, first, second, signal), start=7):
        row.contents[0].value = index
    end.contents[8].value = 8
    opposite.contents[8].value = 7
    end.contents[11].value = signal
    signal.contents[7].value = end
    signal.contents[8].values = [1, 4, 2]
    opposite.contents[9].value = first
    opposite.contents[10].value = second
    source = doc(4, [end, opposite, first, second, signal])
    return source, donor


def test_power_edge_identity_and_reciprocal_instrument_are_written(worksheets):
    source, donor = worksheets
    operations = [
        {'action': 'create_supply', 'name': 'District', 'power_system_code': 4, 'position': [190, 60],
         'edge_ids': [9, 10]},
        {'action': 'create_instrument', 'end_id': 7, 'name': 'Monitor', 'frame': [25, 60, 80, 42],
         'display': ['course', 'clock', 'signal_stops', 'switch_operations'], 'visible': False},
    ]
    saved, proof = monitor.transform(source, donor, operations)
    data, _ = w.load(saved)
    _, items = monitor.models(data)
    assert items[9].contents[17].value is items[10].contents[17].value is items[12]
    assert items[7].contents[13].value is items[13]
    assert items[13].contents[7].value is items[7]
    assert items[13].clazz.version == 4
    assert items[13].contents[17].values == [0, 80.0]
    assert proof['after']['instruments'][0]['display'] == ['course', 'clock', 'switch_operations', 'signal_stops']
    edited, review = monitor.transform(saved, None, [{'action': 'set_edge_supply', 'supply_id': None, 'edge_ids': [9]},
        {'action': 'update_instrument', 'id': 13, 'name': 'Passing monitor', 'visible': True}])
    assert review['after']['power_supplies'][0]['edge_ids'] == [10]
    assert review['after']['instruments'][0]['visible']
    assert edited != saved


def test_no_foreign_edge_or_existing_instrument_overwrite(worksheets):
    source, donor = worksheets
    with pytest.raises(ValueError, match='OTEdgeModel'):
        monitor.transform(source, donor, [{'action': 'create_supply', 'name': 'District', 'power_system_code': 4,
                                          'position': [0, 0], 'edge_ids': [7]}])
    op = {'action': 'create_instrument', 'end_id': 7, 'name': 'Counter', 'frame': [25, 60, 80, 42]}
    with pytest.raises(ValueError, match='without an existing'):
        monitor.transform(source, donor, [op, {**op, 'name': 'Another'}])
    with pytest.raises(ValueError, match='anchored main signal'):
        monitor.transform(source, donor, [{**op, 'end_id': 8, 'display': ['signal_stops']}])


def test_power_supply_and_propulsion_share_edges_without_sharing_slots(worksheets):
    from opentrack_ai.current_archive.native_monitoring_tools import EditMonitoring

    source, donor = worksheets
    operations = [
        {'action': 'create_supply', 'name': 'No traction supply', 'power_system_code': 0,
         'position': [1, 2], 'edge_ids': [9]},
        {'action': 'create_supply', 'name': 'Maglev custom 100', 'power_system_code': 200,
         'position': [3, 4], 'edge_ids': [10]},
        {'action': 'create_propulsion_segment', 'name': 'Segment 1', 'power_system_code': 1000,
         'position': [5, 6], 'edge_ids': [9]},
        {'action': 'create_propulsion_segment', 'name': 'Overlap segment', 'power_system_code': 1002,
         'position': [7, 8], 'edge_ids': [10], 'allow_multiple_trains': True},
        {'action': 'create_propulsion_group', 'name': 'Group A', 'position': [9, 10],
         'segment_ids': [15, 14], 'max_active_segments': 1},
    ]
    request = EditMonitoring.model_validate({
        'source': {'path': 'fixture.opentrack', 'sha256': 'a' * 64},
        'operations': operations, 'preview_only': True,
    })
    saved, receipt = monitor.transform(source, donor, [item.model_dump() for item in request.operations])
    root, _ = w.load(saved)
    _, items = monitor.models(root)
    assert [row['id'] for row in receipt['operations']] == [12, 13, 14, 15, 16]
    assert [items[9].contents[i].value is items[j] for i, j in ((17, 12), (18, 14))] == [True, True]
    assert [items[10].contents[i].value is items[j] for i, j in ((17, 13), (18, 15))] == [True, True]
    assert w.elements(items[16].contents[12].value) == [items[15], items[14]]
    assert receipt['after'] == monitor.records(root)
    assert receipt['after']['power_supplies'][-1]['segment_ids'] == [15, 14]

    edited, proof = monitor.transform(saved, None, [
        {'action': 'set_edge_propulsion_segment', 'segment_id': None, 'edge_ids': [9]},
        {'action': 'update_propulsion_segment', 'id': 15, 'power_system_code': 1001,
         'allow_multiple_trains': False},
        {'action': 'update_propulsion_group', 'id': 16, 'segment_ids': [15], 'max_active_segments': 0},
        {'action': 'update_supply', 'id': 12, 'power_system_code': 1},
    ])
    _, models = monitor.models(w.load(edited)[0])
    assert models[9].contents[17].value is models[12] and models[9].contents[18].value is None
    assert [row['power_system_code'] for row in proof['after']['power_supplies']] == [1, 200, 1000, 1001, 2000]
    assert proof['after']['power_supplies'][-2]['allow_multiple_trains'] is False
    assert proof['after']['power_supplies'][-1]['max_active_segments'] == 0

    with pytest.raises(ValueError, match='regular power supply'):
        monitor.transform(saved, None, [{'action': 'set_edge_supply', 'supply_id': 14, 'edge_ids': [9]}])
    with pytest.raises(ValueError, match='native propulsion segment'):
        monitor.transform(saved, None, [{'action': 'update_propulsion_group', 'id': 16, 'segment_ids': [12]}])
    with pytest.raises(ValueError, match='already has'):
        monitor.transform(saved, None, [{'action': 'set_edge_propulsion_segment', 'segment_id': 15, 'edge_ids': [9]}])

    reduced, deletion = monitor.transform(saved, donor, [
        {'action': 'delete_power_model', 'id': 16},
        {'action': 'create_propulsion_group', 'name': 'Group B', 'position': [0, 0],
         'segment_ids': [15, 14], 'max_active_segments': 1},
        {'action': 'delete_power_model', 'id': 14},
    ])
    _, retained = monitor.models(w.load(reduced)[0])
    assert 14 not in retained and 16 not in retained
    assert retained[9].contents[17].value is retained[12] and retained[9].contents[18].value is None
    assert w.elements(retained[17].contents[12].value) == [retained[15]]
    assert deletion['operations'][-1] == {'action': 'delete_power_model', 'id': 14,
        'cleared_supply_edge_ids': [], 'cleared_propulsion_edge_ids': [9], 'removed_from_group_ids': [17]}

    extra_reference = items[7].contents[18]
    extra_reference.value = items[14]
    with pytest.raises(ValueError, match='additional references'):
        monitor.transform(w.dump_verified(root), None, [{'action': 'delete_power_model', 'id': 14}])


@pytest.fixture
def relocatable_monitor(worksheets):
    source, donor = worksheets
    root, version = w.load(source)
    listing, items = monitor.models(root)
    for first_id, second_id, position, headings in ((12, 13, [100, 40], [3, 4]), (14, 15, [200, 80], [1, 2])):
        for ident, opposite, heading in ((first_id, second_id, headings[0]), (second_id, first_id, headings[1])):
            end = graphic('OTEndModel', 7, route_factory.END)
            end.contents[0].value = ident
            end.contents[8].value = opposite
            end.contents[2].value, end.contents[3].value = position
            end.contents[4].value = heading
            items[ident] = end
    for edge_id, end_id in ((9, 14), (10, 15)):
        event_edge = items[edge_id]
        event_edge.contents[7].value = items[8]
        event_edge.contents[8].value = items[end_id]
        items[end_id].contents[9].value = event_edge
    through_edge = graphic('OTEdgeModel', 3, route_factory.EDGE)
    through_edge.contents[0].value = 16
    through_edge.contents[7].value = items[7]
    through_edge.contents[8].value = items[12]
    items[7].contents[9].value = items[12].contents[9].value = through_edge
    w.set_elements(listing, [*items.values(), through_edge])
    current, receipt = monitor.transform(w.dump_verified(root, version), donor, [{
        'action': 'create_instrument', 'end_id': 7, 'name': 'Passage counter', 'frame': [25, 60, 80, 42],
        'display': ['clock', 'speed'], 'edge_ids': [9, 10], 'direction_code': 2, 'visible': False,
    }])
    return current, {'action': 'relocate_instrument', 'id': receipt['operations'][0]['id'],
                     'from_end_id': 7, 'to_end_id': 12}


def test_relocate_measuring_instrument_keeps_identity_settings_and_independent_monitoring_area(relocatable_monitor):
    source, operation = relocatable_monitor
    saved, proof = monitor.transform(source, None, [operation])
    old, = proof['before']['instruments']
    new, = proof['after']['instruments']
    assert new == {**old, 'end_id': 12, 'frame': [125, 100, 80, 42]}
    assert proof['operations'][0]['before_edge_ids'] == proof['operations'][0]['after_edge_ids'] == [9, 10]
    _, items = monitor.models(w.load(saved)[0])
    instrument = items[operation['id']]
    assert items[7].contents[13].value is None
    assert instrument.contents[7].value is items[12]
    assert items[12].contents[13].value is instrument
    assert [item.value for item in instrument.contents[2:6]] == [100, 40, 3, 0]
    assert instrument.contents[17].values == [0, 80.0]


def test_relocating_measuring_instrument_preserves_unset_native_window_frame(relocatable_monitor):
    source, operation = relocatable_monitor
    root, version = w.load(source)
    _, models = monitor.models(root)
    instrument = models[operation['id']]
    instrument.contents[9].values = [0.0, 0.0]
    instrument.contents[10].values = [0.0, 0.0]
    saved, proof = monitor.transform(w.dump_verified(root, version), None, [operation])
    assert proof['after']['instruments'][0]['frame'] == [0.0] * 4
    assert proof['operations'][0]['frame_translation'] == [0.0, 0.0]
    _, readback = monitor.models(w.load(saved)[0])
    assert readback[operation['id']].contents[7].value is readback[12]
    assert [field.value for field in readback[operation['id']].contents[2:4]] == [100, 40]


def test_relocate_can_replace_and_clear_exact_reviewed_edge_group(relocatable_monitor):
    source, operation = relocatable_monitor
    saved, proof = monitor.transform(source, None, [{**operation, 'expected_edge_ids': [9, 10], 'edge_ids': [16]}])
    assert proof['after']['instruments'][0]['edge_ids'] == [16]
    _, proof = monitor.transform(saved, None, [{**operation, 'from_end_id': 12, 'to_end_id': 7,
        'expected_edge_ids': [16], 'edge_ids': []}])
    assert proof['after']['instruments'][0]['edge_ids'] == []
    with pytest.raises(ValueError, match='Edge area has changed'):
        monitor.transform(source, None, [{**operation, 'expected_edge_ids': [9], 'edge_ids': []}])
    with pytest.raises(ValueError, match='both expected and replacement'):
        monitor.transform(source, None, [{**operation, 'edge_ids': []}])


def test_relocate_refuses_wrong_source_occupied_target_inactive_counting_and_invalid_edges(relocatable_monitor, worksheets):
    source, operation = relocatable_monitor
    with pytest.raises(ValueError, match='Reviewed source End'):
        monitor.transform(source, None, [{**operation, 'from_end_id': 8}])
    occupied, _ = monitor.transform(source, worksheets[1], [
        {'action': 'create_instrument', 'end_id': 12, 'name': 'Existing', 'frame': [0, 0, 80, 42]},
    ])
    with pytest.raises(ValueError, match='without an existing measuring instrument'):
        monitor.transform(occupied, None, [operation])
    stop, _ = monitor.transform(source, None, [
        {'action': 'update_instrument', 'id': operation['id'], 'display': ['signal_stops']},
    ])
    with pytest.raises(ValueError, match='anchored main signal'):
        monitor.transform(stop, None, [operation])
    with pytest.raises(ValueError, match='OTEdgeModel'):
        monitor.transform(source, None, [{**operation, 'expected_edge_ids': [9, 10], 'edge_ids': [12]}])


def test_stock_automatic_main_signal_selection_preserves_existing_instruments(worksheets):
    source, donor = worksheets
    root, version = w.load(source)
    listing, items = monitor.models(root)
    other = graphic('OTSignalModel', 11, route_factory.SIGNAL)
    other.contents[0].value = 12
    other.contents[7].value = items[8]
    other.contents[8].values[0] = 24
    items[8].contents[11].value = other
    w.set_elements(listing, [*items.values(), other])
    pair = w.dump_verified(root, version)
    action = {'action': 'create_instruments_at_locations', 'location': 'main_signal'}

    _, single = monitor.transform(pair, donor, [{**action, 'selected_end_ids': [7]}])
    assert single['operations'][0]['candidate_end_ids'] == [7]
    assert single['after']['instruments'] == []
    saved, both = monitor.transform(pair, donor, [action])
    assert both['operations'][0]['created'] == [
        {'end_id': 8, 'instrument_id': 13}, {'end_id': 7, 'instrument_id': 14}]
    assert all('signal_stops' in entry['display'] for entry in both['after']['instruments'])
    _, rerun = monitor.transform(saved, donor, [action])
    assert rerun['operations'][0]['already_monitored_end_ids'] == [7, 8]
    assert rerun['after'] == rerun['before']


def test_automatic_turnout_instruments_require_actual_local_edge_incidence(worksheets):
    source, donor = worksheets
    with pytest.raises(ValueError, match='Turnout leg endpoint is not reciprocal'):
        monitor.transform(source, donor, [{'action': 'create_instruments_at_locations', 'location': 'switch'}])


def test_stock_finder_and_signed_kilometres_select_directional_models(worksheets):
    from opentrack_ai.current_archive.worksheet_finder_tools import (
        ById, ByKilometre, ByName, Conflicts, worksheet_results,
    )

    root, version = w.load(worksheets[0])
    listing, items = monitor.models(root)
    items[7].contents[14].value = -99999.0
    items[7].contents[18].value = ns.string('Track North')
    items[8].contents[14].value = -1.0
    items[8].contents[18].value = ns.string('Track South')
    items[11].contents[13].value = ns.string('W_EXIT')
    items[9].contents[7].value = items[7]
    items[9].contents[8].value = items[8]
    items[9].contents[9].values[1] = 200
    items[7].contents[9].value = items[9]
    w.set_elements(listing, [items[num] for num in (7, 8, 9, 11)])
    _, models = monitor.models(w.load(w.dump_verified(root, version))[0])
    graph = {'Test': models}

    def matches(query):
        result, unresolved = worksheet_results(graph, 'Test', query)
        assert not unresolved
        return result

    assert matches(ById(kind='object_id', id=9)) == [{'id': 9, 'class': 'OTEdgeModel'}]
    assert [row['id'] for row in matches(ByName(kind='vertex_name', name='Track', match='contains'))] == [7, 8]
    assert matches(ByName(kind='signal_name', name='W_EXIT'))[0]['end_id'] == 7
    assert [row['id'] for row in matches(ByKilometre(kind='kilometre_point', kilometre_point=-1))] == [7, 8]
    result, = matches(Conflicts(kind='kilometre_conflicts'))
    assert result['discrepancy_m'] == -200
    models[7].contents[14].value = -0.8
    assert matches(Conflicts(kind='kilometre_conflicts'))[0]['signed_kilometre_length_m'] == -200
    models[7].contents[14].value = -1.2
    assert not matches(Conflicts(kind='kilometre_conflicts'))


def test_finder_follows_original_remote_connector_for_an_unset_kilometre():
    from opentrack_ai.current_archive.worksheet_finder_tools import kilometres

    def pair(owner, remote):
        connector = ns.obj([('OTConnModel', 1), ('OTEndModel', 7), GRAPHIC, OBJECT], [
            (group, [None if code == '@' else 0 for code in group])
            for group in route_factory.END + ['@', '@', 'i', 'i']
        ])
        end = graphic('OTEndModel', 7, route_factory.END)
        end.contents[0].value = 8
        end.contents[8].value = 9
        end.contents[14].value = -99999.0
        connector.contents[0].value = 9
        connector.contents[8].value = 8
        connector.contents[25].value = ns.string(remote)
        connector.contents[26].value = 9
        return {owner: {8: end, 9: connector}}

    graphs = pair('Left', 'Right')
    assert kilometres(graphs, 'Left', graphs['Left'][8]) is None
    graphs.update(pair('Right', 'Left'))
    graphs['Right'][8].contents[14].value = 42.0
    assert kilometres(graphs, 'Left', graphs['Left'][8]) == 42.0
    graphs['Right'][9].contents[26].value = 10
    with pytest.raises(ValueError, match='Nonreciprocal remote connector'):
        kilometres(graphs, 'Left', graphs['Left'][8])


def test_finder_rejects_same_named_worksheet_from_another_snapshot(tmp_path):
    from opentrack_ai.current_archive.worksheet_finder_tools import verify_run_membership

    current = tmp_path / 'Current'
    run_path = current / 'line.run'
    worksheets = {current / 'EA.opentrack', current / 'RDG.opentrack'}
    options = b'Infrastructure Document#EA.opentrack#\nInfrastructure Document#RDG.opentrack#\n'
    verify_run_membership(run_path, options, worksheets)
    stale = tmp_path / 'Older' / 'RDG.opentrack'
    with pytest.raises(ValueError, match='exact paths declared'):
        verify_run_membership(run_path, options, {current / 'EA.opentrack', stale})


@pytest.mark.parametrize(('slot', 'start_s', 'end_s', 'duration_s'), [
    ('00:00 - 00:00', 0, 0, None),
    ('HH:MM - HH:MM', None, None, None),
    ('23:50 - 1 / 00:20', 85800, 87600, 1800),
])
def test_original_occupation_statistics_with_unset_and_cross_day_slots(slot, start_s, end_s, duration_s):
    stock = ('// Produced by OpenTrack: sample\r\n// Type    : OT_BarYPlot\r\n// Desc.   : OT_occstatistics\r\n'
             f'// Scenario: Step: 0.2 s / Occ. Time Slot: {slot}\r\n'
             '// x-Legend: none\r\n// y-Legend: [Tr.]\r\n// y1-Legend: [Tr./h]\r\n'
             '// y2-Legend: [Tr./h]\r\n// y3-Legend: [Tr./h]\r\n// y4-Legend: [%]\r\n'
             '// y5-Legend: [%]\r\n// y6-Legend: [%]\r\n'
             'RDG P9\t1\t1.00\t1.00\t0.00\t7.76\t7.76\t0.00\r\n')
    observation = occupation_statistics(stock)
    assert observation['time_slot'] == {'display_text': slot, 'start_s': start_s, 'end_s': end_s,
                                        'duration_s': duration_s}
    assert observation['units']['time_slot_reservation_percentage'] == '%'
    assert observation['records'] == [{'name': 'RDG P9', 'occupation_count': 1, 'average_trains_per_hour': 1.0,
                                       'peak_trains_per_hour': 1.0, 'time_slot_trains_per_hour': 0.0,
                                       'average_reservation_percentage': 7.76, 'peak_reservation_percentage': 7.76,
                                       'time_slot_reservation_percentage': 0.0}]
    with pytest.raises(ValueError, match='statistics plot type or units'):
        occupation_statistics(stock.replace('[Tr./h]', '[mph]'))
    with pytest.raises(ValueError, match='duplicate group name'):
        occupation_statistics(stock + stock.splitlines()[-1])


def test_original_power_and_instrument_output_variants():
    power = ('// Produced by OpenTrack: sample\n// Power Supply Output: District\n'
             '// Desc. : OT_PowerSupply\n// x-Legend: [s]\n// y-Legend: [kW]\n'
             '10.0\t0.000\n10.2\t82.000\n10.4\t-3.000\n')
    curve = power_supply(power)
    assert curve['summary']['maximum'] == 82
    assert curve['summary']['minimum'] == -3
    raw = ('// Produced by OpenTrack: sample\n// Desc. : OT_ins\n'
           '1\t0\t10.2\t6.0\tLINE01\t1\n1\t0\t10.20\t\t\t\t2\n'
           '// No. of Signal Stops    : 1\n// Sum of Signal Stop Time: 12.5\n')
    stats = instruments(raw)
    assert stats['records'][0]['course_id'] == 'LINE01'
    assert stats['records'][1]['switch_operations'] == 2
    assert stats['signal_stop_summaries'] == [{'signal_stops': 1, 'signal_stop_time_s': 12.5}]
