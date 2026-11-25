"""Witness a fixed original signal hold on an otherwise unchanged station departure."""

import re

from . import native_evaluation_formats as fmt, writer
from .native_interlocking import CLOCK_TOLERANCE, metres_trace
from .native_run_evaluation import basename, signal_reservation_clock


POSITION_TOLERANCE_M = 0.17


def frozen_signal(railway, item, itinerary, offset):
    project = railway.project
    document = item['document']
    signal = project.model((document, item['model_id']))
    owner = signal.contents[7].value
    owner_key = project.key(owner)
    fmt.require(owner_key[0] == document and owner.contents[11].value is signal,
                'Frozen incident Signal does not match its owning directional End')
    nodes, _ = project.dest_view(railway.itineraries[itinerary])
    fmt.require(nodes.count(owner_key) == 1 and owner_key != nodes[-1],
                'Frozen incident Signal must occur once before the selected Itinerary terminal')
    distance = offset
    for first, second in zip(nodes, nodes[1:]):
        if first == owner_key:
            break
        edge = project.model(project.edge_between(first, second))
        distance += edge.contents[9].values[1]

    paired = project.byid[document].get(owner.contents[8].value)
    prefix = writer.string(owner.contents[18].value) or (
        writer.string(paired.contents[18].value) if paired is not None else None)
    name = writer.string(signal.contents[13].value)
    fmt.require(name, 'Frozen incident Signal requires its original displayed name')
    return {'document': document, 'signal_model_id': item['model_id'], 'directional_end_id': owner_key[1],
            'signal_name': name, 'signal_label': f'{prefix}_{name}' if prefix else name,
            'expected_position_m': distance}


def itinerary_output(text, itinerary, extension):
    labels = re.findall(r'^// Itineraries:[ \t]*1:[ \t]*(.+?)[ \t]*\r?$', text, re.M)
    fmt.require(labels == [itinerary], f'Original .{extension} output does not identify the frozen Itinerary')
    return text


def movement(railway, course, itinerary, signal):
    course_name = basename(course)
    files = {extension: itinerary_output(railway.original_text(f'OT_{course_name}.{extension}'), itinerary, extension)
             for extension in ('sigpos', 'step1', 'st1', 'vt')}
    position, reserved = signal_reservation_clock(railway.files, course_name, signal['signal_label'])
    position *= 1000
    fmt.require(abs(position - signal['expected_position_m']) <= POSITION_TOLERANCE_M,
                'Original main signal position differs from its frozen directed Itinerary position')
    outcome, = railway.receipt['courses']
    candidates = [row for row in outcome['stationary_intervals']
                  if abs(row['distance_reference_m'] - position) <= POSITION_TOLERANCE_M
                  and abs(row['end_s'] - reserved) <= CLOCK_TOLERANCE]
    fmt.require(len(candidates) == 1, 'Expected one original zero-speed interval ending at the selected reservation')
    dwell, = candidates
    distances = metres_trace(files['st1'], 'st1', course, itinerary)
    speed_trace = fmt.series(files['vt'], 'vt', course)
    speeds = speed_trace['points']
    # Require original, paired moving measurements after the reservation, on the
    # outward side of the signal. Sparse or compressed data is never interpolated.
    moving = {clock: metres for clock, metres in distances if clock > reserved and metres > position + POSITION_TOLERANCE_M}
    resumed = next(({'time_s': clock, 'position_m': round(moving[clock], 5),
                     'reported_speed': speed, 'speed_unit': speed_trace['units'][1]}
                    for clock, speed in speeds if speed > 0 and clock in moving), None)
    fmt.require(resumed, 'Original movement did not resume beyond the selected signal')
    return {'position_m': position, 'reservation_s': reserved, 'stationary': dwell, 'resumed': resumed,
            'distances': distances, 'speeds': speeds, 'outcome': outcome}


def stop_warnings(raw, course, signal):
    fmt.headers(raw, 'OT_messages')
    prefix = f'Course {course}: Stop at Signal {signal["signal_name"]} at '
    return [dict(clock=clock, message=message, location=details[0])
            for level, clock, cid, message, *details in fmt.data_rows(raw)
            if level == 'WARNING' and cid == course and message.startswith(prefix)
            and details == [f'({signal["document"]})']]


def departure(case, tolerance):
    matches = [event for event in case['outcome']['events'] if event['kind'] == 'Dep.'
               and event['planned_s'] is not None and abs(event['time_s'] - case['reservation_s']) <= tolerance]
    fmt.require(len(matches) == 1, 'Expected a unique planned departure near the witnessed signal reservation')
    return matches[0]


def matched_stop(before, after, active_window, stop_clock, fixed_stop_s, step):
    tolerance = step + 1.01
    fmt.require(before['position_m'] == after['position_m']
                and abs(before['stationary']['start_s'] - after['stationary']['start_s']) <= CLOCK_TOLERANCE,
                'Original runs do not share a common station stop at the selected signal')
    first, later = [departure(case, tolerance) for case in (before, after)]
    fmt.require(all(first[field] == later[field] for field in ('station', 'planned_s')),
                'Original comparisons must apply to one common planned station departure')
    earlier, delayed = [case['reservation_s'] for case in (before, after)]
    resumed = after['resumed']['time_s']
    fmt.require(abs(stop_clock - earlier) <= tolerance and active_window[0] <= stop_clock <= earlier + tolerance
                and earlier < delayed < resumed < active_window[1],
                'Original stop and resumed movement do not corroborate a finite hold within the active incident')
    extension = round(after['stationary']['duration_s'] - before['stationary']['duration_s'], 5)
    wait_tolerance = 2 * step + 2 * CLOCK_TOLERANCE
    return {
        'quantity': 'fixed_signal_hold_s',
        'saved_stop_duration_s': fixed_stop_s, 'stop_duration_tolerance_s': round(wait_tolerance, 5),
        'additional_stationary_time_s': extension, 'control_signal_reservation_s': earlier,
        'incident_signal_reservation_s': delayed, 'signal_reservation_change_s': round(delayed - earlier, 5),
        'control_stationary_time_s': round(before['stationary']['duration_s'], 5),
        'incident_stationary_time_s': round(after['stationary']['duration_s'], 5),
        'control_departure_event': first, 'incident_departure_event': later,
        'departure_event_change_s': later['time_s'] - first['time_s'],
        'control_first_running_sample_past_signal': before['resumed'],
        'incident_first_running_sample_past_signal': after['resumed'],
        'control_signal_stops': before['outcome']['statistics']['signal_stops'],
        'incident_signal_stops': after['outcome']['statistics']['signal_stops'],
        'verified_effect': abs(extension - fixed_stop_s) <= wait_tolerance
                           and later['time_s'] > first['time_s']
                           and after['outcome']['statistics']['signal_stops'] == before['outcome']['statistics']['signal_stops'] + 1,
    }
