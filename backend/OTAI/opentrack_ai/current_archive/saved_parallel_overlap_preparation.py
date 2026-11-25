"""Review the finite synchronized terminal pair with two equal native preparations."""

from . import catalogs, course_factories, writer
from .catalog_batch_reuse.course_batch import course_record
from .multi_document.core import ident, need
from .network_composition_plan import itinerary_routes
from .operating_plan_edit import ROW_FLAGS, text, timetable_time
from .runfile_parameters import inspect_runfile
from .saved_timing_signal_split import DEFAULT_ROUTE_TIMING


SWITCH_TIMING = b'Use Switch Time and Route Res. Time'


def _single_terminal_course(project, route, course_items, timetable, terminal):
    users = {}
    for item in project.dests:
        routes = list(itinerary_routes(project, item))
        if route not in routes:
            continue
        name = ident(item)[0]
        need(name not in users and routes.count(route) == 1 and routes[-1] is route,
             'The reviewed overlap Route must be used once as the final leg of every saved Itinerary that uses it')
        users[name] = item
    active = [record for record in map(course_record, course_items) if record['enabled']]
    need(len(active) == 1, 'Parallel overlap preparation requires exactly one enabled native Course')
    course, = active
    choices = course['itineraries']
    need(len(choices) == 1 and choices[0] in users and course['spacing_mode_code'] == 0
         and course['additional_reservation_time_s'] == course['additional_release_time_s'] == 0,
         'Use a fixed-block Course on one exact terminal Itinerary and zero additional reservation/release delay')
    root, _ = writer.load_next_compatible(timetable)
    rows = list(course_factories.timetable(root).values())
    need(all(not catalogs.array(row.contents[9].value) for row in rows),
         'Parallel overlap preparation requires a timetable without saved Connections')
    schedule = sorted((row for row in rows if text(row, 1) == course['course_id']),
                      key=lambda row: row.contents[3].value)
    station = project.model(terminal).contents[12].value
    need(len(schedule) >= 2 and writer.kind(station) == 'OTStationModel'
         and text(schedule[-1], 5) == catalogs.text(station.contents[7].value)
         and schedule[-1].contents[10].value & ROW_FLAGS['stop_at_station']
         and timetable_time(schedule[-1], 'arrival') is not None,
         'The active Course needs an actual booked terminal stop at the original overlap boundary')
    return course['course_id'], choices[0]


def _plain_resources(project, sequence, overlap, delay_s):
    slip = [(overlap['shunting']['document'], number) for number in overlap['end_ids']]
    controlled = {key for end in (*sequence, *slip)
                  for key in (end, project.related(end), project.actual_related(end))}
    need(all(project.model(key).contents[21].value == 0 for key in controlled),
         'Parallel overlap preparation requires zero saved switch time on both main sections and the overlap')
    signals = [project.model(key).contents[11].value for key in (sequence[0], sequence[-1])]
    need(delay_s == 0 and all(writer.kind(signal) == 'OTSignalModel' and signal.clazz.version == 11
             and signal.contents[8].values[0] == 1 and not signal.contents[9].values[2] & 2
             and signal.contents[16].value == 0 for signal in signals),
         'Parallel overlap preparation needs ordinary physical main signals and zero signal-specific delay')
    terminal = sequence[-1]
    need(not any(project.owners[id(item)] == terminal for item in project.routes),
         'The overlap owner must terminate the available forward main-Route chain')


def plan_parallel_overlap_preparation(project, route, sequence, timing, overlap, course_root, operating_banks,
                                      run_bytes, *, reserve_with_previous, signal_delay_s):
    """Keep both preparation events at the same nominal time and retain the first slip ownership pass."""
    need(type(run_bytes) is bytes and type(operating_banks) is dict and type(operating_banks.get('timetable')) is bytes,
         'Parallel overlap preparation requires frozen native CourseList, Timetable and Project .run')
    settings = inspect_runfile(run_bytes)
    options = settings['editable_options']
    need(settings['editable'] and options[SWITCH_TIMING] == b'1',
         'Enable the original switch and route reservation timing explicitly')
    need(all(options[key] in (None, b'0') for key in
             (b'Optimize Dispatching', b'Optimize Train Sequence', b'Multithreaded', b'Delay Scenario'))
         and not any(key == b'Incident' for key, _ in settings['readonly'])
         and not catalogs.array(course_root.contents[1].value),
         'Parallel overlap preparation requires the isolated run without extra incidents or optimization')
    original = timing['original']
    delay, release = original['reserve_time_s'], original['release_time_s']
    same_timing = {**DEFAULT_ROUTE_TIMING, 'reserve_time_s': delay, 'release_time_s': release}
    need(reserve_with_previous is True and type(delay) is int and 0 < delay <= 86400
         and type(release) is int and 0 < release <= 86400
         and original == timing['upstream'] == same_timing
         and timing['downstream'] == {**same_timing, 'reserve_time_s': 0},
         'Use synchronized reservation and positive Route preparation/release seconds with default approach and distance')
    start, cut, terminal = (timing[key] for key in
                            ('reservation_origin', 'new_release_boundary', 'terminal_release_boundary'))
    need(timing['original_release_group_starts'] == [start, cut, terminal],
         'Parallel overlap preparation needs the relay at the original effective release anchor')
    need(overlap['reservation_time_s'] == 0 and overlap['release_time_s'] > 0
         and (overlap['shunting']['document'], overlap['shunting']['start_id']) == terminal,
         'Keep the exact terminal Shunting with zero preparation and a positive overlap release')
    _plain_resources(project, sequence, overlap, signal_delay_s)
    course_id, itinerary = _single_terminal_course(
        project, route, catalogs.course_items(course_root), operating_banks['timetable'], terminal)
    scope = {'course_id': course_id, 'itinerary': itinerary, 'saved_route_delay_s': [delay, delay],
             'main_release_s': release, 'overlap_release_s': overlap['release_time_s'],
             'original_release_anchor': cut, 'terminal_end': terminal,
             'terminal_overlap': overlap, 'native_runtime_verified': False}
    return {**timing, 'downstream': same_timing}, scope


def check_parallel_overlap_preparation(saved, prefix, suffix, timing, overlap, review, labels, running):
    itinerary, = [item for item in saved.dests if ident(item)[0] == review['itinerary']]
    routes = list(itinerary_routes(saved, itinerary))
    start, cut, terminal = (timing[key] for key in
                            ('reservation_origin', 'new_release_boundary', 'terminal_release_boundary'))
    need(review['itinerary'] in labels and running == [review['course_id']]
         and routes[-2:] == [prefix, suffix] and suffix.contents[11].value == 1
         and timing['saved_release_group_starts'] == {'upstream': [start, cut], 'downstream': [cut, terminal]}
         and overlap['upstream_reference_cleared'] and overlap['synchronized_reservation']
         and all(overlap[key] == value for key, value in review['terminal_overlap'].items()),
         'The native readback must retain the same last overlap, exact preparation and both release anchors')
    return {**review, 'original_tail_scan_retains_both_when_clear': True,
            'native_archive_readback_verified': True}
