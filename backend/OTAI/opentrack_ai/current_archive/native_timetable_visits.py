"""Bind native stop or pass evidence to a specific saved timetable occurrence."""

from bisect import bisect_left

from . import catalogs, course_factories, native_evaluation_formats as fmt, writer
from .native_interlocking import FrozenRailwayRun, metres_trace
from .native_run_evaluation import basename
from .network_operating_plan import route_trace
from .operating_plan_edit import text, timetable_time


def series_at(points, instant):
    """Read a trace at a clock bracketed by original observed samples."""
    index = bisect_left(points, instant, key=lambda sample: sample[0])
    if index < len(points) and points[index][0] == instant:
        return points[index][1]
    if index == 0 or index == len(points):
        return None
    start, first = points[index - 1]
    end, last = points[index]
    return first + (last - first) * (instant - start) / (end - start)


def same_event(event, station, kind, planned):
    return event['station'] == station and event['kind'] == kind and event.get('planned_s') == planned


def observe(events, speeds, positions, intervals, visit, saved, request, limits, after):
    station, scheduled_arrival, scheduled_departure = saved
    clock_tolerance, position_tolerance = limits
    reference = positions[0][1] + visit['distance_m']
    result = {'display_station': station, 'expected': request['expected'], 'verified': False,
              'station_reference_position_m': reference,
              'scheduled_arrival_s': scheduled_arrival, 'scheduled_departure_s': scheduled_departure}
    if request['expected'] == 'stop':
        prior = [event for event in events if event['time_s'] > after]
        hits = [(arrival, departure) for arrival, departure in zip(prior, prior[1:])
                if same_event(arrival, station, 'Arr.', scheduled_arrival)
                and same_event(departure, station, 'Dep.', scheduled_departure)]
        if len(hits) != 1:
            return result, after
        arrival, departure = hits[0]
        arrival_clock, departure_clock = arrival['time_s'], departure['time_s']
        lower = reference - (visit.get('stopping_area_length_m') or visit['stop_edge_length_m'])
        candidates = [row for row in intervals
                      if abs(row['start_s'] - arrival_clock) <= clock_tolerance
                      and abs(row['end_s'] - departure_clock) <= clock_tolerance
                      and lower - position_tolerance <= row['distance_reference_m'] <= reference + position_tolerance
                      and row['duration_s'] + 0.02 >= request['minimum_observed_dwell_s']]
        return {**result, 'arrival': arrival, 'departure': departure, 'verified': len(candidates) == 1,
                'stationary_intervals': candidates}, departure_clock

    # A Pass can also be printed at departure from a previous stop under the same station name.
    # Original planned-versus-actual reporting can assign that record to a later planned pass.
    station_events = [event for event in events if event['station'] == station]
    departure_clocks = {event['time_s'] for event in station_events if event['kind'] == 'Dep.'}
    physical_passages = []
    for passage in station_events:
        at = passage['time_s']
        if passage['kind'] != 'Pass' or at <= after or at in departure_clocks:
            continue
        before = series_at(positions, at - clock_tolerance)
        after_position = series_at(positions, at + clock_tolerance)
        speed = series_at(speeds, at)
        if (None not in (before, after_position, speed) and before < after_position and speed > 0
                and before - position_tolerance <= reference <= after_position + position_tolerance):
            physical_passages.append((passage, speed, [before, after_position]))
    if len(physical_passages) != 1:
        return result, after
    (passage, speed, bracket), = physical_passages
    return {**result, 'passage': passage, 'verified': True, 'observed_speed_kmh': speed,
            'distance_bracket_m': bracket,
            'original_planned_time_matches': passage.get('planned_s') == scheduled_arrival,
            'other_pass_events_reported_at_this_planned_time': [
                event for event in station_events if event != passage
                and same_event(event, station, 'Pass', scheduled_arrival)
            ]}, passage['time_s']


def audit(output, evidence, request, secure_bytes=None):
    outcome = request['course']
    cid = basename(outcome['course_id'])
    run = FrozenRailwayRun(output, evidence, [outcome], secure_bytes)
    choices = run.preferences[cid]
    fmt.require(len(choices) == 1, 'Select an ordinary Course with one saved Itinerary')
    label, = choices
    trace = route_trace(run.project, run.itineraries[label])
    station_file = run.dependency(run.settings['paths']['StationFile'])
    timetable_file = run.dependency(run.settings['paths']['TimetableFile'])
    station_catalog = catalogs.station_items(writer.load_next_compatible(station_file)[0])
    timetable = course_factories.timetable(writer.load_next_compatible(timetable_file)[0])
    rows = sorted((row for row in timetable.values() if text(row, 1) == cid), key=lambda row: row.contents[3].value)
    visits = trace['visits']
    fmt.require(len(rows) == len(visits) and [row.contents[3].value for row in rows] == list(range(len(visits)))
                and [text(row, 5) for row in rows] == [visit['station_sign'] for visit in visits]
                and all(not catalogs.array(row.contents[9].value) for row in rows),
                'Select an unlinked Course with complete frozen rows in exact directed Itinerary order')
    requested = request['visits']
    indices = [row['visit_index'] for row in requested]
    fmt.require(indices == sorted(set(indices)) and indices[0] >= 1 and indices[-1] < len(visits) - 1,
                'Select unique, strictly ordered intermediate visit indices')

    prefix = f'OT_{cid}'
    events = fmt.timetable(run.original_text(prefix + '.tt'), cid)
    positions = metres_trace(run.original_text(prefix + '.st1'), 'st1', cid, label)
    speed_trace = fmt.series(run.original_text(prefix + '.vt'), 'vt', cid)
    factor = {'km/h': 1.0, 'mph': 1.609344}[speed_trace['units'][1]]
    speeds = [(time, value * factor) for time, value in speed_trace['points']]
    distance_tolerance = outcome.get('distance_tolerance_m', request['position_tolerance_m'])
    fmt.require(abs(positions[-1][1] - positions[0][1] - trace['route_length_m']) <= distance_tolerance,
                'Original trajectory does not cover the saved directed Itinerary')
    intervals = fmt.stationary_intervals(speeds, positions)
    limits = (outcome['event_tolerance_s'], request['position_tolerance_m'])
    checked = []
    actual_after = -1
    planned_after = -1
    for check in requested:
        index = check['visit_index']
        row = rows[index]
        visit = visits[index]
        station = writer.string(station_catalog[visit['station_sign']].contents[2].value)
        flags = row.contents[10].value
        expected_stop = check['expected'] == 'stop'
        arrival = timetable_time(row, 'arrival')
        departure = timetable_time(row, 'departure')
        fmt.require(text(row, 5) == check['station_sign'] and tuple(check['reference_end']) == visit['end_key']
                    and flags & 2 and bool(flags & 1) == expected_stop
                    and (visit['stop_edge_length_m'] is not None or not expected_stop)
                    and arrival is not None and departure is not None and planned_after < arrival <= departure
                    and (departure > arrival) == expected_stop,
                    f'Frozen mode, time or directed station reference disagrees at timetable row {index}')
        planned_after = departure
        observed, actual_after = observe(events, speeds, positions, intervals, visit, (station, arrival, departure),
                                         check, limits, actual_after)
        checked.append({**observed, 'visit_index': index, 'station_sign': visit['station_sign'],
                        'reference_end': visit['end_key'], 'platform_edge': visit['stop_edge_key'],
                        'stopping_area_edges': visit.get('stopping_area_edge_keys') or
                        ([visit['stop_edge_key']] if visit['stop_edge_key'] else []),
                        'incoming_track_id': visit['incoming_track_id']})
    return {'verified': all(row['verified'] for row in checked), 'course_id': cid, 'itinerary': label,
            'route_length_m': trace['route_length_m'], 'visits': checked, 'provenance': run.provenance,
            'original_output_sha256': {**run.receipt['output_sha256'], **run.files.hashes}}
