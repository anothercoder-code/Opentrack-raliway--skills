"""Native split keeping a prefix speed zone and an independent terminal overlap."""

from copy import deepcopy

import pytest

from opentrack_ai.current_archive import writer
from opentrack_ai.current_archive.multi_document import generate
from opentrack_ai.current_archive.route_edit_tools import edit_cross_document_movement
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.saved_geometry_tools import MainSignalRouteSplit
from opentrack_ai.current_archive.saved_main_signal_split import insert_signal_in_saved_route
from opentrack_ai.current_archive.saved_slow_overlap_signal_split import check_slow_zone_overlap
from opentrack_ai.current_archive.saved_terminal_overlap import overlap_reference
from opentrack_ai.current_archive.saved_timing_signal_split import DEFAULT_ROUTE_TIMING, stored_route_timing
from opentrack_ai.current_archive.signal_operating_fields import append_route_aspects

from test_itinerary_lifecycle import course_archive
from test_saved_main_signal_split import _with_overlap, sending_corridor


@pytest.fixture
def protected(sending_corridor):
    docs, paths, dest, graph, operation = sending_corridor
    selected = operation['split_route']['route']
    route = graph.owned(('A', selected['start_id']), 'OTRoute',
                        (selected['name'], selected['array_id'], selected['start_id']))
    sequence = graph.route_view(route)
    origin, zone_end, cut = sequence[:3]
    edges = [graph.edge_between(left, right) for left, right in zip(sequence, sequence[1:])]
    x, y = (float(graph.model(cut).contents[slot].value) for slot in (2, 3))
    operation = {**operation, 'end_id': cut[1], 'placement': generate.signal_placement(graph.model(cut), x, y),
                 'split_route': {**operation['split_route'], 'reserve_with_previous': True,
                                 'expected_upstream_edge_ids': [number for _, number in edges[:2]],
                                 'expected_downstream_edge_ids': [number for _, number in edges[2:]]}}
    docs, overlap = _with_overlap(docs, paths, dest, operation)
    aspects, _ = append_route_aspects(docs, paths, dest, [origin], [{'start_end': origin, 'speeds_kmh': [40]}])
    docs = {**docs, **aspects}

    def zone(finish):
        ends = [{'document': document, 'end_id': number} for document, number in (origin, finish)]
        outputs, _ = edit_cross_document_movement(
            docs, paths, dest, 'A', {key: value for key, value in selected.items() if key != 'document'},
            [number for name, number in sequence if name == 'A'], [number for name, number in sequence if name == 'B'],
            slow_speed_zone_ends=ends, signal_aspects=[4])
        request = deepcopy(operation)
        request['split_route'].update(terminal_overlap=overlap, slow_zone={
            'start': ends[0], 'finish': ends[1], 'expected_native_aspect_code': 4,
            'expected_speed_kmh': 40, 'expected_head_only': False,
        })
        return {**docs, **outputs}, request

    return paths, dest, sequence, edges, zone_end, cut, zone


def run(docs, paths, dest, operation):
    return insert_signal_in_saved_route(docs, paths, dest, 'A', operation, course_archive(C01=['I:A-B']))


def test_joint_fixed_slow_zone_and_terminal_overlap_save_and_cold_read(protected):
    paths, dest, sequence, edges, zone_end, cut, zone = protected
    docs, operation = zone(zone_end)
    MainSignalRouteSplit.model_validate(operation['split_route'])
    changed, report = run(docs, paths, dest, operation)
    proof = report['slow_zone_overlap_split']
    assert proof['native_joint_readback_verified'] and proof['linked_downstream_reservation_requested']
    assert proof['upstream_speed_zone']['ends'] == [sequence[0], zone_end]
    assert proof['upstream_speed_zone']['edge_keys'] == edges[:1]
    assert proof['upstream_speed_zone']['speed_kmh'] == 40 and proof['downstream_aspect_code'] == 0
    assert proof['terminal_overlap']['release_time_s'] == 35 and proof['terminal_overlap']['edge_keys'][0][0] == 'B'
    saved = project_from({**docs, **changed}, paths, dest)
    upstream, downstream = [saved.owned((row['document'], row['start_id']), 'OTRoute',
                                        (row['name'], row['array_id'], row['start_id']))
                            for row in (report['upstream_route'], report['downstream_route'])]
    assert saved.route_view(upstream) == sequence[:3] and saved.route_view(downstream) == sequence[2:]
    assert stored_route_timing(upstream) == stored_route_timing(downstream) == DEFAULT_ROUTE_TIMING
    assert overlap_reference(upstream) == ('', -1)
    assert overlap_reference(downstream) == (proof['terminal_overlap']['shunting']['name'], sequence[-1][1])
    assert downstream.contents[11].value == 1

    downstream.contents[5].values[2] = 9
    with pytest.raises(ValueError, match='differ after native cold read'):
        check_slow_zone_overlap(saved, upstream, downstream, cut,
                                {key: value for key, value in proof.items() if key != 'native_joint_readback_verified'},
                                report['slow_zone_split'], report['terminal_overlap_transfer'])


def test_fixed_zone_must_finish_strictly_before_relay(protected):
    paths, dest, _, _, _, cut, zone = protected
    docs, operation = zone(cut)
    with pytest.raises(ValueError, match='strictly before the new Signal'):
        run(docs, paths, dest, operation)


def test_slow_zone_and_overlap_reject_nonadjacent_cross_section_exclusion(protected):
    paths, dest, _, edges, zone_end, _, zone = protected
    docs, operation = zone(zone_end)
    graph = project_from(docs, paths, dest)
    upstream = graph.model(edges[0])
    downstream = graph.model(edges[2])
    upstream.contents[13].value = downstream
    downstream.contents[14].value = upstream
    docs['A'] = writer.dump_verified(graph.roots['A'], graph.versions['A'])
    with pytest.raises(ValueError, match='independent Edges, Safety Elements and Edge exclusions'):
        run(docs, paths, dest, operation)


def test_schema_rejects_independent_reservation_for_combined_protections(protected):
    _, _, _, _, zone_end, _, zone = protected
    _, operation = zone(zone_end)
    selection = {**operation['split_route'], 'reserve_with_previous': False}
    with pytest.raises(ValueError, match='synchronized reservation and default Route timing'):
        MainSignalRouteSplit.model_validate(selection)


def test_combined_protection_rejects_original_nondefault_route_and_shunting_reservation(protected):
    paths, dest, _, _, zone_end, _, zone = protected
    docs, operation = zone(zone_end)
    graph = project_from(docs, paths, dest)
    reference = operation['split_route']['route']
    primary = graph.owned(('A', reference['start_id']), 'OTRoute',
                          tuple(reference[key] for key in ('name', 'array_id', 'start_id')))
    primary.contents[5].values[3] = 12
    timed = {**docs, 'A': writer.dump_verified(graph.roots['A'], graph.versions['A'])}
    with pytest.raises(ValueError, match='default reservation or the exact reviewed timing'):
        run(timed, paths, dest, operation)
    shunting, = [obj for obj in writer.objects(graph.roots['B']) if writer.kind(obj) == 'OTShunting']
    shunting.contents[5].values[3] = 12
    timed = {**docs, 'B': writer.dump_verified(graph.roots['B'], graph.versions['B'])}
    with pytest.raises(ValueError, match='zero Shunting reservation delay'):
        run(timed, paths, dest, operation)
