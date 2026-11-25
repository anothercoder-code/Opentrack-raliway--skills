"""Readers for English Windows OpenTrack 1.7 evaluation files."""

from collections import Counter, defaultdict
from itertools import groupby
import math
import re


MAX_ROWS = 2_000_000
OCCUPATION_TIMELINE = ('SR', 'EP', 'SO', 'EO', 'ER')
OCCUPATION_REQUIRED = set(OCCUPATION_TIMELINE) - {'EP'}
SERIES = {
    'vt': ('OT_vt', 'Speed/Time', {'s'}, {'km/h', 'mph'}),
    'vs': ('OT_vs', 'Speed/Distance', {'km', 'mi'}, {'km/h', 'mph'}),
    'st1': ('OT_st1', 'Distance/Time', {'s'}, {'km', 'mi'}),
    'step1': ('OT_step1', 'Route Reservation', {'s'}, {'km', 'mi'}),
    'step2': ('OT_step2', 'Route Release', {'s'}, {'km', 'mi'}),
    'at': ('OT_at', 'Acceleration/Time', {'s'}, {'m/s^2', 'ft/s^2'}),
    'as': ('OT_as', 'Acceleration/Distance', {'km', 'mi'}, {'m/s^2', 'ft/s^2'}),
    'Ps': ('OT_Ps', 'Mech.Power/Distance', {'km', 'mi'}, {'kW'}),
    'Pis': ('OT_Pis', 'Power In/Distance', {'km', 'mi'}, {'kW'}),
    'Wis': ('OT_Wis', 'Energy In/Distance', {'km', 'mi'}, {'MJ'}),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def number(field):
    value = float(field)
    require(math.isfinite(value), 'Non-finite numeric field')
    return value


def integer(field):
    require(re.fullmatch(r'-?\d+', field), 'Expected integer field')
    return int(field)


def headers(text, descriptor):
    require(any(line.startswith('// Produced by OpenTrack: ') for line in text.splitlines()[:8]),
            'Missing original producer header')
    require(re.search(r'^// Desc\.\s*:\s*' + re.escape(descriptor) + r'\s*$', text, re.M),
            f'Missing {descriptor} descriptor')


def data_rows(text):
    for index, line in enumerate(text.splitlines()):
        require(index < MAX_ROWS, 'Native file exceeds row limit')
        if line.strip() and not line.startswith('//'):
            yield [value.strip() for value in line.split('\t')]


def course_header(text, title, course):
    require(re.search(r'^// ' + re.escape(title) + r' of Course\s*:\s*'
                      + re.escape(course) + r'\s*$', text, re.M), 'Native Course header mismatch')


def timetable(text, course):
    headers(text, 'OT_tt')
    course_header(text, 'Timetable', course)
    lines = text.splitlines()
    headings = [line.strip() for line in lines]
    first = headings.index('Actual Timetable')
    end = headings.index('Actual Timetable vs. Planned Timetable', first + 1)
    events = []
    for row in data_rows('\n'.join(lines[first + 1:end])):
        require(len(row) >= 4 and row[0] and row[1] in {'Dep.', 'Arr.', 'Pass'},
                'Unexpected actual timetable row')
        instant = integer(row[3])
        require(instant >= 0 and (not events or instant >= events[-1]['time_s']),
                'Out-of-order actual timetable event')
        events.append({'station': row[0], 'kind': row[1], 'clock': row[2], 'time_s': instant})
    actual_index = {(row['station'], row['kind'], row['time_s']): [] for row in events}
    for event in events:
        actual_index[(event['station'], event['kind'], event['time_s'])].append(event)
    for row in data_rows('\n'.join(lines[end + 1:])):
        if len(row) < 6 or row[1] not in {'Dep.', 'Arr.', 'Pass'}:
            continue
        instant = integer(row[5])
        keyed = actual_index.get((row[0], row[1], instant), [])
        event = next((item for item in keyed if 'planned_s' not in item), None)
        if event is not None:
            planned = integer(row[3])
            event['planned_s'] = planned if planned >= 0 else None
            if len(row) > 7 and planned >= 0:
                event['delay_s'] = integer(row[7])
    return events


def course_statistics(text):
    headers(text, 'OT_coursestat')
    data = defaultdict(list)
    units = {}
    for row in data_rows(text):
        if len(row) >= 23 and row[5] == '[HH:MM:SS]':
            units = {'distance': row[21].strip('[]'), 'speed': row[22].strip('[]')}
        if len(row) != 26 or row[0] in {'Course', '', 'Total'}:
            continue
        require(units.get('distance') in {'km', 'mi'} and units.get('speed') in {'km/h', 'mph'},
                'Missing Course statistics units')
        distance_factor = 1000 if units['distance'] == 'km' else 1609.344
        speed_factor = 1 if units['speed'] == 'km/h' else 1.609344
        data[row[0]].append({
            'first_departure_clock': row[7], 'first_departure_s': integer(row[8]),
            'last_arrival_clock': row[9], 'last_arrival_s': integer(row[10]),
            'end_clock': row[11], 'end_s': integer(row[12]),
            'distance_m': number(row[21]) * distance_factor,
            'mean_speed_kmh': number(row[22]) * speed_factor,
            'station_stops': integer(row[23]), 'route_brakings': integer(row[24]),
            'signal_stops': integer(row[25]),
        })
    return dict(data)


def station_statistics(text):
    headers(text, 'OT_stationstat')
    stations = []
    switches = []
    in_switches = False
    for row in data_rows(text):
        if row[0] == 'Switch ID':
            in_switches = True
            continue
        if len(row) == 4 and not in_switches and row[0] != 'Station':
            stations.append(dict(station=row[0], arrivals=integer(row[1]),
                                 departures=integer(row[2]), passes=integer(row[3])))
        elif len(row) == 5 and in_switches:
            switches.append(dict(switch_id=integer(row[0]), document=row[1], vertex=row[2],
                                 station=row[3] or None, operations=integer(row[4])))
        elif row[0] != 'Station':
            raise ValueError('Unexpected station statistics record')
    return {'stations': stations, 'switches': switches}


def messages(text):
    headers(text, 'OT_messages')
    levels = Counter()
    incidents = []
    diagnostics = []
    lifecycle = []
    for row in data_rows(text):
        require(len(row) in {4, 5}, 'Unexpected native message record')
        level, clock, course, message, *details = row
        level = level.upper()
        require(re.fullmatch('[A-Z]+', level), 'Unexpected message type')
        levels[level] += 1
        event = {'level': level, 'clock': clock, 'course_id': course or None, 'message': message,
                 'location': details[0] if details else None}
        detail = message.removeprefix(f'Course {course}: ') if course else message
        transition = re.fullmatch(r'Incident (started|stopped): (.+)', detail)
        if transition:
            incidents.append({**event, 'transition': transition[1], 'subject': transition[2]})
        if re.search(r'^(Start|End|Cancel\w*) (?:of )?Simulation\b', message, re.I):
            lifecycle.append(event)
        if level in {'WARNING', 'ERROR', 'FATAL', 'SEVERE'} or re.search(r'\bdeadlock\b', message, re.I):
            diagnostics.append(event)
    return {'levels': dict(levels), 'lifecycle': lifecycle, 'incident_events': incidents,
            'diagnostic_count': len(diagnostics), 'diagnostics': diagnostics[:200]}


def protocol(text):
    headers(text, 'OT_protocol')
    result = dict(configured_window=None, first_process=None, last_process=None, delay_scenario=None,
                  used_courses=[], listed_incidents=[], occupation_statistics=[], paths={},
                  active_topology_files=[], instrument_statistics=[])
    section = None
    sections = {'Databases:', 'OutputPath:', 'Used Courses:', 'Occupations:', 'Incidents:',
                'Scenario:', 'Instruments:', 'Open Topology-Files:', 'Train Speed Types:'}
    for row in data_rows(text):
        first = row[0]
        if first in sections:
            section = first
            continue
        if section == 'Databases:' and ':' in first:
            key, val = first.split(':', 1)
            result['paths'][key.strip()] = val.strip()
        elif section == 'OutputPath:':
            result['paths']['OutputPath'] = first
        elif section == 'Scenario:' and ':' in first:
            key, value = map(str.strip, first.split(':', 1))
            normalized = {'Simulation Time': 'configured_window', 'First Process': 'first_process',
                          'Last Process': 'last_process', 'Delay Scenario': 'delay_scenario'}.get(key)
            if normalized:
                result[normalized] = value
        elif section == 'Used Courses:' and len(row) == 2:
            result['used_courses'].append(first)
        elif section == 'Occupations:' and len(row) == 8:
            result['occupation_statistics'].append(dict(
                name=first, count=integer(row[1]), mean_trains_per_hour=number(row[2]),
                max_trains_per_hour=number(row[3]), time_slot_trains_per_hour=number(row[4]),
                mean_reservation_pct=number(row[5]), max_reservation_pct=number(row[6]),
                time_slot_reservation_pct=number(row[7]),
            ))
        elif section == 'Instruments:' and len(row) == 3:
            count, headway = integer(row[1]), number(row[2])
            require(count >= 0 and (headway == -1 or headway >= 0), 'Invalid original instrument summary')
            result['instrument_statistics'].append(dict(name=first, trains=count,
                                                        minimum_headway_s=None if headway == -1 else headway))
        elif section == 'Incidents:' and len(row) >= 3:
            result['listed_incidents'].append(dict(name=first, start=row[1], end=row[2]))
        elif section == 'Open Topology-Files:':
            result['active_topology_files'].append(first)
    return result


def series(text, extension, course):
    descriptor, title, x_units, y_units = SERIES[extension]
    headers(text, descriptor)
    course_header(text, title, course)
    units = []
    for axis, choices in (('x', x_units), ('y', y_units)):
        found = re.findall(r'^// ' + axis + r'-Legend[ \t]*:[ \t]*\[([^\[\]\r\n]+)\][ \t]*\r?$', text, re.M)
        require(len(found) == 1 and found[0] in choices, 'Unexpected native series unit')
        units.append(found[0])
    points = []
    for row in data_rows(text):
        require(len(row) == 2, 'Native series must have exactly two fields')
        x, y = map(number, row)
        require(not points or x >= points[-1][0], 'Native series clocks or distances decrease')
        if extension in {'vt', 'st1'}:
            require(x >= 0, 'Invalid time value')
        if extension in {'vt', 'vs'}:
            require(y >= 0, 'Invalid speed value')
        points.append((x, y))
    return {'units': units, 'points': points}


def series_summary(series_data):
    points = series_data['points']
    summary = {'sample_count': len(points), 'units': series_data['units']}
    if points:
        values = [value for _, value in points]
        summary.update(first=points[0], last=points[-1], minimum=min(values), maximum=max(values))
    return summary


def stationary_intervals(speeds, positions):
    """Read compressed plateaux by their recorded endpoints and interior samples."""
    intervals = []
    position_by_time = defaultdict(list)
    position_index = {}
    for index, (time, distance) in enumerate(positions):
        position_index.setdefault(time, index)
        position_by_time[time].append(distance)
    for zero, points in groupby(speeds, key=lambda point: point[1] == 0):
        if not zero:
            continue
        group = list(points)
        start, end = group[0][0], group[-1][0]
        if start == end or start not in position_index or end not in position_index:
            continue
        end_index = position_index[end] + len(position_by_time[end])
        distances = [position for _, position in positions[position_index[start]:end_index]]
        if max(distances) - min(distances) <= 0.17:
            intervals.append({'start_s': start, 'end_s': end, 'duration_s': end - start,
                              'distance_reference_m': distances[0]})
    return intervals


def occupations(text):
    headers(text, 'OT_occ')
    events = []
    for row in data_rows(text):
        require(len(row) == 4 and row[1] and row[2] in OCCUPATION_TIMELINE and row[3],
                'Unknown occupation event format')
        time = number(row[0])
        require(time >= 0 or (time == -1 and row[2] != 'EP'), 'Unknown negative occupation clock')
        events.append(dict(time_s=time if time >= 0 else None, resource=row[1],
                           event=row[2], course_id=row[3]))
    return events


def occupation_intervals(events):
    """Pair native reservation and occupation states within the same resource and Course."""
    pending = {}
    cycles = []
    invalid = 0
    for event in events:
        key = event['resource'], event['course_id']
        code = event['event']
        if code == 'SR':
            invalid += key in pending
            pending[key] = {}
        state = pending.get(key)
        if state is None or code in state:
            invalid += 1
            continue
        state[code] = event['time_s']
        if code != 'ER':
            continue
        pending.pop(key)
        resource, course_id = key
        order = [state[k] for k in OCCUPATION_TIMELINE if state.get(k) is not None]
        if not OCCUPATION_REQUIRED <= state.keys() or not all(a <= b for a, b in zip(order, order[1:])):
            invalid += 1
            continue
        cycle = {'resource': resource, 'course_id': course_id, 'reservation_s': [state['SR'], state['ER']],
                 'occupation_s': [state['SO'], state['EO']]}
        if 'EP' in state:
            cycle['pre_reservation_s'] = [state['SR'], state['EP']]
        cycles.append(cycle)
    return cycles, invalid + len(pending)


def physical_series(text, course=None):
    headers(text, 'OT_tsvP')
    if course is not None:
        require(re.search(r'^// Time/Distance/.+ of Course:\s*' + re.escape(course) + r'\s*$', text, re.M),
                'Native physical Course header mismatch')
    else:
        require('// Col. 0: Course-ID' in text, 'Missing network physical output Course column')
    required_units = ('[s]', '[km]', '[km/h]', '[m/s^2]', '[kN]', '[kW]', '[MJ]')
    header = '\n'.join(text.splitlines()[:35])
    require(all(unit in header for unit in required_units), 'Unsupported physical output units')
    fields = ('time_s', 'distance_km', 'speed_kmh', 'acceleration_mps2', 'tractive_effort_kn',
              'resistance_kn', 'mechanical_power_kw', 'power_input_kw', 'energy_input_mj')
    results = []
    for row in data_rows(text):
        require(len(row) == (10 if course is not None else 11), 'Unexpected physical record')
        specific_course = course if course is not None else row.pop(0)
        require(specific_course, 'Missing Course identity in physical record')
        results.append({'course_id': specific_course, **dict(zip(fields, map(number, row[:9]))),
                        'power_district': row[9] or None})
    return results
