"""Native cold read of the exact terminal pair with concurrent preparations."""

import pytest

from opentrack_ai.current_archive import catalogs, writer
from opentrack_ai.current_archive.multi_document.core import ident
from opentrack_ai.current_archive.movement_edits import edit_route
from opentrack_ai.current_archive.route_edit_tools import edit_cross_document_movement
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.saved_geometry_tools import CreateMainSignal, MainSignalRouteSplit
from opentrack_ai.current_archive.saved_main_signal_split import insert_signal_in_saved_route
from opentrack_ai.current_archive.saved_terminal_overlap import overlap_reference
from opentrack_ai.current_archive.saved_timing_signal_split import DEFAULT_ROUTE_TIMING, stored_route_timing
from opentrack_ai.current_archive.zero_generation import native_signal_routes as native

from test_itinerary_lifecycle import course_archive
from test_operating_plan_edit import connection, dictionary, row
from test_saved_main_signal_split import _review_overlap, _with_overlap, receiving_corridor


RUN = (
    b'Start Day Offset#0#\nStart Time#10:00:00#\nStop Day Offset#0#\nStop Time#11:00:00#\n'
    b'Step#0.2#\nUse Switch Time and Route Res. Time#1#\n'
)


def timetable(*, with_connection=False):
    links = [connection('C01', 'C02', 'Terminal')] if with_connection else []
    terminal = row('C01', 'Terminal', 1, '10:30:00', connections=links)
    terminal.contents[10].value |= 1
    return writer.dump_verified(dictionary({'C01#0': row('C01', 'Origin', 0, '10:10:00'), 'C01#1': terminal}))


def finite_case(receiving, *, anchored=True):
    docs, paths, dest, _, base, nodes, _ = receiving
    docs, approved = _with_overlap(docs, paths, dest, base)
    op = _review_overlap(base, approved)
    plan = op['split_route']
    route = {key: value for key, value in plan['route'].items() if key != 'document'}
    cut, terminal = op['end_id'], nodes[-1][1]
    anchors = [cut, terminal] if anchored else [terminal]
    pair, _ = edit_cross_document_movement(
        docs, paths, dest, 'A', route, [end for label, end in nodes if label == 'A'],
        [end for label, end in nodes if label == 'B'], [route['start_id']], anchors)
    docs = {**docs, **pair}
    docs['A'], _ = edit_route(docs['A'], route, {'release_time_s': 9, 'reserve_time_s': 12})
    project = project_from(docs, paths, dest)
    station = native.obj([('OTStationModel', 1), ('OTGraphicModel', 1), ('NSObject', 0)], [
        ('i', [max(project.byid['B']) + 1]), ('f', [0.0]), ('f', [100.0]), ('f', [50.0]), ('i', [0]), ('i', [0]),
        ('@', [None]), ('@', [native.string('Terminal')]), ('ii', [2, 4]), ('ii', [1, 0]),
    ])
    for end in (nodes[-1], project.related(nodes[-1])):
        model = project.model(end)
        model.contents[12].value = station
        model.contents[20].value = 2
    holders = project.roots['B'].contents[2].value
    writer.set_elements(holders, [*project.models['B'], station])
    docs['B'] = writer.dump_verified(project.roots['B'], project.versions['B'])
    course_root, version = writer.load_next_compatible(course_archive(C01=['I:A-B']))
    catalogs.course_items(course_root)[0].contents[5].value = 1
    banks = {'courses': writer.dump_verified(course_root, version), 'timetable': timetable()}
    plan['timing'] = {**DEFAULT_ROUTE_TIMING, 'release_time_s': 9, 'reserve_time_s': 12,
                      'parallel_overlap_preparation': True, 'release_group_starts': [
                          {'document': 'A', 'end_id': route['start_id']},
                          *({'document': 'B', 'end_id': number} for number in anchors)]}
    return docs, paths, dest, op, banks


def save(case, run=RUN):
    docs, paths, dest, op, banks = case
    return insert_signal_in_saved_route(docs, paths, dest, 'B', op, banks['courses'], operating_banks=banks, run_bytes=run)


def test_parallel_preparation_cold_reads_both_native_delays_and_the_same_overlap(receiving_corridor):
    case = finite_case(receiving_corridor)
    docs, paths, dest, op, _ = case
    with pytest.raises(ValueError, match='five operating archive hashes'):
        CreateMainSignal.model_validate(op)
    eligible = {**op, 'operating_sha256': {key: '0' * 64 for key in ('courses', 'timetable', 'trains', 'depot', 'stations')}}
    CreateMainSignal.model_validate(eligible)
    edited, result = save(case)
    fresh = project_from({**docs, **edited}, paths, dest)
    front, back = (fresh.owned((item['document'], item['start_id']), 'OTRoute',
                               tuple(item[key] for key in ('name', 'array_id', 'start_id')))
                   for item in (result['upstream_route'], result['downstream_route']))
    assert ident(back)[0] == op['split_route']['continued_name']
    assert [stored_route_timing(route)['reserve_time_s'] for route in (front, back)] == [12, 12]
    assert overlap_reference(front) == ('', -1)
    assert overlap_reference(back) == (op['split_route']['terminal_overlap']['shunting']['name'],
                                       op['split_route']['terminal_overlap']['shunting']['start_id'])
    assert result['parallel_overlap_preparation']['original_tail_scan_retains_both_when_clear']
    assert not result['parallel_overlap_preparation']['native_runtime_verified']


def test_parallel_preparation_rejects_missing_anchor_timing_and_connections(receiving_corridor):
    with pytest.raises(ValueError, match='original effective release anchor'):
        save(finite_case(receiving_corridor, anchored=False))
    case = finite_case(receiving_corridor)
    with pytest.raises(ValueError, match='Enable the original switch and route reservation timing'):
        save(case, RUN.replace(b'Time#1#', b'Time#0#'))
    case[-1]['timetable'] = timetable(with_connection=True)
    with pytest.raises(ValueError, match='without saved Connections'):
        save(case)


def test_positive_overlap_requires_parallel_preparation_acknowledgement(receiving_corridor):
    case = finite_case(receiving_corridor)
    op = case[3]
    op['split_route']['timing'].pop('parallel_overlap_preparation')
    with pytest.raises(ValueError, match='exactly for a synchronized terminal overlap'):
        MainSignalRouteSplit.model_validate(op['split_route'])
    with pytest.raises(ValueError, match='default reservation and distance'):
        save(case)
