"""Verify one frozen terminal-to-origin connection in a completed native job."""

from pathlib import Path

from . import native_evaluation_formats as fmt
from .native_circulation import lifecycle_messages, transition_motion
from .native_interlocking import metres_trace
from .native_platform_join import planned_itineraries, platform_signals
from .native_run_evaluation import OutputFiles, basename


def output_names(check):
    names = {'OT_Messages.txt'}
    for role in ('predecessor', 'successor'):
        prefix = f"OT_{basename(check[role]['course_id'])}"
        names.update(prefix + extension for extension in ('.tt', '.vt', '.st1', '.sigpos'))
    return names


def _main_signal_at_boundary(signals, endpoint, role, course):
    label = endpoint['label']
    boundary = next(iter(signals if role == 'origin' else reversed(signals)), None)
    matches = signals.get(label, ())
    fmt.require(boundary == label and len(matches) == 1,
                f'Original {role} main signal differs for {course}')
    metres, kind = matches[0]
    fmt.require(abs(metres - fmt.number(endpoint['position_m'])) <= .1,
                f'Original {role} main signal chainage differs for {course}')
    return {**endpoint, 'observed_position_m': metres, 'native_kind': kind}


def _read_course(files, expected):
    course, itinerary = basename(expected['course_id']), expected['itinerary']
    prefix = f'OT_{course}'
    clock_tolerance = fmt.number(expected.get('event_tolerance_s', 1.05))
    distance_tolerance = fmt.number(expected.get('distance_tolerance_m', 1.75))
    fmt.require(.01 <= clock_tolerance <= 5 and 0 < distance_tolerance <= 10,
                f'Native event or distance tolerance outside the reviewed range for {course}')
    legend = planned_itineraries(files.read(prefix + '.sigpos'), [itinerary], 'sigpos')
    signals = platform_signals(legend, course)
    origin_signal = _main_signal_at_boundary(signals, expected['origin'], 'origin', course)
    terminal_signal = _main_signal_at_boundary(signals, expected['terminal'], 'terminal', course)

    events = fmt.timetable(files.read(prefix + '.tt'), course)
    fmt.require(len(events) >= 2 and events[0]['kind'] == 'Dep.' and events[-1]['kind'] == 'Arr.'
                and events[-1]['station'] == expected['terminal_station'],
                f'Original timetable does not have the reviewed departure and terminal arrival for {course}')
    position = metres_trace(files.read(prefix + '.st1'), 'st1', course, itinerary)
    speed_text = planned_itineraries(files.read(prefix + '.vt'), [itinerary], 'vt')
    speed_data = fmt.series(speed_text, 'vt', course)
    factor = {'km/h': 1, 'mph': 1.609344}[speed_data['units'][1]]
    speed = [(clock, value * factor) for clock, value in speed_data['points']]
    fmt.require(speed and all(a[1] <= b[1] for a, b in zip(position, position[1:])),
                f'Original speed is absent or course chainage decreased for {course}')
    fmt.require(abs(position[0][1] - origin_signal['observed_position_m']) <= .17,
                f'Original first trajectory sample differs from the reviewed origin for {course}')

    arrival = events[-1]['time_s']
    head = fmt.number(expected['terminal_head_m'])
    fmt.require(origin_signal['observed_position_m'] < head <= terminal_signal['observed_position_m'] + .1,
                f'Frozen terminal head is outside the reviewed Route extent for {course}')
    near_arrival = [row for row in position if abs(row[0] - arrival) <= clock_tolerance]
    at_stop = min(near_arrival, key=lambda row: abs(row[0] - arrival), default=None)
    fmt.require(at_stop is not None and abs(at_stop[1] - head) <= distance_tolerance
                and abs(position[-1][1] - head) <= distance_tolerance,
                f'Original arrival and final head positions differ for {course}')
    last_moving = max((clock for clock, value in speed if value > 0), default=-1)
    zeros = [clock for clock, value in speed if value == 0 and clock > last_moving
             and abs(clock - arrival) <= clock_tolerance]
    fmt.require(last_moving >= events[0]['time_s'] - clock_tolerance and zeros
                and any(abs(clock - at_stop[0]) <= clock_tolerance for clock in zeros),
                f'Original terminal arrival has no matching zero-speed sample for {course}')
    return {'course_id': course, 'itinerary': itinerary, 'origin': events[0], 'terminal': events[-1],
            'position': position, 'speed': speed, 'clock_tolerance_s': clock_tolerance,
            'origin_signal': origin_signal, 'terminal_signal': terminal_signal,
            'arrival_trajectory_m': at_stop[1], 'final_trajectory_m': position[-1][1],
            'terminal_zero_speed_s': min(zeros, key=lambda clock: abs(clock - arrival))}


def verify_endpoint_connection(output, check, hashes):
    """Check SHA-sealed results after the queue verifies the run and frozen link."""
    names = output_names(check)
    fmt.require(names <= hashes.keys(), 'The original receipt must hash every endpoint connection output')
    files = OutputFiles(Path(output).resolve(strict=True), None, names, hashes, None)
    previous = _read_course(files, check['predecessor'])
    successor = _read_course(files, check['successor'])
    before, after = previous['course_id'], successor['course_id']
    movement, station = check['movement'], check['station_sign']
    minimum = fmt.number(check['minimum_hold_s'])
    fmt.require(before != after and movement in ('continue', 'reverse') and station
                and 0 <= minimum < 86400, 'Invalid frozen endpoint connection')
    fmt.require(previous['terminal']['station'] == successor['origin']['station'],
                'The original arrival and successor departure must share the reviewed station')
    same_signal = previous['terminal_signal']['label'] == successor['origin_signal']['label']
    fmt.require(same_signal == (movement == 'continue'),
                'The original main signal labels do not distinguish the reviewed movement')
    first_time, first_position = successor['position'][0]
    fmt.require(abs(successor['origin_signal']['observed_position_m']) <= .1 and abs(first_position) <= .17,
                'The original successor must begin at zero metres')

    message_text = files.read('OT_Messages.txt')
    events = lifecycle_messages(message_text, {before, after})
    # 0x65132c reports specification 0x27 on the no-match fallback in 0x64ca98.
    # The original English key used by OTMessageController is read from its executable.
    warnings = [row[3] for row in fmt.data_rows(message_text) if len(row) >= 4 and row[2] == after
                and 'itinerary changed after split at' in row[3].casefold()]
    fmt.require(not warnings, 'Original successor used a fallback Itinerary')
    activations = [event for event in events if event['course_id'] == after and event['kind'] == 'activation']
    fmt.require(len(activations) == 1, 'The original successor requires exactly one activation message')
    tolerance = min(previous['clock_tolerance_s'], successor['clock_tolerance_s'])
    motion = transition_motion(previous, successor, events, station, minimum, tolerance, linked=True)
    fmt.require(motion['verified'], f"Original endpoint connection failed: {motion['checks']}")
    fmt.require(motion['successor_stationary_interval']['duration_s'] + .02 >= minimum,
                'The original stationary hold was shorter than the required duration')

    def witness(course):
        return {key: course[key] for key in ('course_id', 'itinerary', 'origin_signal', 'terminal_signal',
                                               'arrival_trajectory_m', 'final_trajectory_m', 'terminal_zero_speed_s')}

    return {'verified': True, 'station_sign': station, 'movement': movement, 'minimum_hold_s': minimum,
            'predecessor': witness(previous), 'successor': witness(successor),
            'successor_first_trajectory': {'time_s': first_time, 'position_m': first_position},
            'motion': motion, 'output_sha256': files.hashes}
