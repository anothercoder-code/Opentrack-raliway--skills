"""Combined native main signal split protection on local and continued Routes."""

import pytest

from opentrack_ai.current_archive import catalogs, writer
from opentrack_ai.current_archive.multi_document.core import ident
from opentrack_ai.current_archive.saved_geometry import project_from
from opentrack_ai.current_archive.saved_main_signal_split import insert_signal_in_saved_route
from opentrack_ai.current_archive.saved_timing_signal_split import (
    DEFAULT_ROUTE_TIMING, release_keys, stored_route_timing, timing_groups,
)

from test_itinerary_lifecycle import course_archive
from test_saved_main_signal_split import (
    _slow_zone_source, occupied_corridor, receiving_corridor, sending_corridor, station_corridor,
)


def _combined_source(docs, paths, dest, target, op, *, zone_position='upstream', reserve=True, **timing_changes):
    protected, op, nodes, cut = _slow_zone_source(docs, paths, dest, target, op, zone_position)
    graph = project_from(protected, paths, dest)
    spec = op['split_route']['route']
    document = spec['document']
    route = graph.owned((document, spec['start_id']), 'OTRoute', (spec['name'], spec['array_id'], spec['start_id']))
    values = {**DEFAULT_ROUTE_TIMING, 'release_time_s': 9, 'approach_length_m': 40,
              'approach_speed_kmh': 28, **timing_changes}
    for slot, parts in timing_groups(route, values).items():
        route.contents[slot].values[:] = parts
    anchors = release_keys(graph, route)
    fragments = [row for row in graph.continuations if row['source_document'] == document
                 and row['route'] == {key: spec[key] for key in ('name', 'array_id', 'start_id')}]
    for row in fragments:
        receiving = (row['target_document'], row['target_connector'])
        anchors += release_keys(graph, graph.owned(receiving, 'OTRoute', ident(route)))
    protected[document] = writer.dump_verified(graph.roots[document], graph.versions[document])
    op['split_route']['reserve_with_previous'] = reserve
    op['split_route']['timing'] = {**values, 'release_group_starts': [
        {'document': sheet, 'end_id': number} for sheet, number in anchors]}
    return protected, op, nodes, cut


@pytest.mark.parametrize(('fixture', 'target'), [
    ('local', 'Line'), ('sending_corridor', 'A'), ('receiving_corridor', 'B'),
])
def test_combined_station_and_continued_route_split_cold_read(request, fixture, target):
    if fixture == 'local':
        docs, paths, dest, _, op = station_corridor(reverse=False)
        courses = course_archive(C01=['Through'])
    else:
        docs, paths, dest, _, op = request.getfixturevalue(fixture)[:5]
        courses = course_archive(C01=['I:A-B'])
    protected, op, nodes, cut = _combined_source(docs, paths, dest, target, op)
    changed, receipt = insert_signal_in_saved_route(protected, paths, dest, target, op, courses)
    saved = project_from({**protected, **changed}, paths, dest)
    joined = receipt['slow_zone_timing_split']
    assert joined['slow_zone_m_from_original_route_origin'][1] == joined['cut_m_from_original_route_origin']
    assert joined['zone_to_approach_m'] > 0
    assert joined['synchronized_downstream_reservation'] and joined['release_time_s'] == 9
    first, second = [saved.owned((row['document'], row['start_id']), 'OTRoute',
                                 (row['name'], row['array_id'], row['start_id']))
                     for row in (receipt['upstream_route'], receipt['downstream_route'])]
    assert [saved.route_view(first), saved.route_view(second)] == [nodes[:cut + 1], nodes[cut:]]
    assert first.contents[11].value == 2 and second.contents[11].value == 1
    assert stored_route_timing(first) == {**DEFAULT_ROUTE_TIMING, 'release_time_s': 9}
    assert stored_route_timing(second) == {**DEFAULT_ROUTE_TIMING, 'release_time_s': 9,
                                          'approach_length_m': 40, 'approach_speed_kmh': 28}
    if fixture != 'local':
        part = first if fixture == 'receiving_corridor' else second
        continued, = [row for row in saved.continuations if row['route']['name'] == ident(part)[0]]
        receiver = saved.owned((continued['target_document'], continued['target_connector']), 'OTRoute', ident(part))
        assert receiver.contents[11].value == 0
        assert stored_route_timing(receiver) == DEFAULT_ROUTE_TIMING


@pytest.mark.parametrize(('changes', 'error'), [
    ({'zone_position': 'crossing'}, 'entire slow zone'),
    ({'zone_position': 'downstream'}, 'entire slow zone'),
    ({'approach_length_m': 100}, 'positive separating distance'),
    ({'reserve_time_s': 12}, 'only release delay and terminal approach'),
    ({'release_distance_m': 60, 'use_release_distance': True}, 'only release delay and terminal approach'),
    ({'reservation_distance_m': 600, 'use_reservation_distance': True}, 'only release delay and terminal approach'),
    ({'reserve': False}, 'requires synchronized downstream reservation'),
])
def test_combined_split_rejects_unreviewed_interactions(occupied_corridor, changes, error):
    docs, paths, dest, _, _, courses, op = occupied_corridor
    protected, op, _, _ = _combined_source(docs, paths, dest, 'Line', op, **changes)
    with pytest.raises(ValueError, match=error):
        insert_signal_in_saved_route(protected, paths, dest, 'Line', op, courses)


ACTIVE_TIMING_RUN = (
    b'Start Day Offset#0#\nStart Time#10:00:00#\nStop Day Offset#0#\n'
    b'Stop Time#11:00:00#\nStep#0.2#\nUse Switch Time and Route Res. Time#1#\n'
)


def delayed_courses(*, extra_delay=0, duplicated=False, alternatives=False):
    bindings = {'C01': ['I:A-B', 'I:elsewhere'] if alternatives else ['I:A-B']}
    if duplicated:
        bindings['C02'] = ['I:A-B']
    root, version = writer.load_next_compatible(course_archive(**bindings))
    for course in catalogs.course_items(root):
        course.contents[5].value = 1
        course.contents[12].values[0] = extra_delay
    return writer.dump_verified(root, version)


@pytest.mark.parametrize('delay', [12, 19])
def test_positive_prefix_timing_retains_original_controls_and_marks_retry_unverified(receiving_corridor, delay):
    docs, paths, dest, _, op = receiving_corridor[:5]
    protected, op, nodes, cut = _combined_source(docs, paths, dest, 'B', op, reserve_time_s=delay)
    op['split_route']['timing']['allow_delayed_prefix_retry'] = True
    saved, receipt = insert_signal_in_saved_route(protected, paths, dest, 'B', op, delayed_courses(),
                                                run_bytes=ACTIVE_TIMING_RUN)
    loaded = project_from({**protected, **saved}, paths, dest)
    front, rear = [loaded.owned((row['document'], row['start_id']), 'OTRoute',
                                (row['name'], row['array_id'], row['start_id']))
                   for row in (receipt['upstream_route'], receipt['downstream_route'])]
    assert loaded.route_view(front) + loaded.route_view(rear)[1:] == nodes
    assert loaded.route_view(front)[-1] == nodes[cut]
    assert (stored_route_timing(front)['reserve_time_s'], stored_route_timing(rear)['reserve_time_s']) == (delay, 0)
    assert rear.contents[11].value == 1
    timing = receipt['slow_zone_timing_split']
    assert timing['linked_downstream_reservation_requested']
    assert 'synchronized_downstream_reservation' not in timing
    assert timing['delayed_prefix_reservation'] == {
        'course_id': 'C01', 'itinerary': 'I:A-B', 'course_reservation_delay_s': 0,
        'maximum_saved_switch_time_s': 0, 'upstream_delay_s': delay, 'downstream_delay_s': 0,
        'initial_attempt_may_be_limited_to_prefix': True, 'same_clock_reservation_guaranteed': False,
        'subsequent_relay_lock_runtime_unverified': True, 'native_archive_readback_verified': True,
    }


@pytest.mark.parametrize(('failure', 'message'), [
    ('run_absent', 'bound native Project'),
    ('run_disabled', 'Enable the original switch and route reservation timing'),
    ('second_course', 'one enabled native Course'),
    ('alternate_path', 'one exact saved Itinerary'),
    ('additional_delay', 'zero additional reservation delay'),
    ('nonzero_switch', 'zero saved switch times'),
    ('unrequested_delay', 'without an explicit review'),
])
def test_positive_prefix_timing_rejects_unreviewed_runtime_assumptions(receiving_corridor, failure, message):
    docs, paths, dest, _, op = receiving_corridor[:5]
    delay = 0 if failure == 'unrequested_delay' else 12
    protected, op, nodes, _ = _combined_source(docs, paths, dest, 'B', op, reserve_time_s=delay)
    op['split_route']['timing']['allow_delayed_prefix_retry'] = True
    run = ACTIVE_TIMING_RUN
    if failure == 'run_absent':
        run = None
    elif failure == 'run_disabled':
        run = run.replace(b'Res. Time#1#', b'Res. Time#0#')
    elif failure == 'nonzero_switch':
        loaded = project_from(protected, paths, dest)
        affected = loaded.actual_related(nodes[0])
        loaded.model(affected).contents[21].value = 1.0
        protected[affected[0]] = writer.dump_verified(loaded.roots[affected[0]], loaded.versions[affected[0]])
    courses = delayed_courses(extra_delay=1 if failure == 'additional_delay' else 0,
                              duplicated=failure == 'second_course', alternatives=failure == 'alternate_path')
    with pytest.raises(ValueError, match=message):
        insert_signal_in_saved_route(protected, paths, dest, 'B', op, courses, run_bytes=run)
