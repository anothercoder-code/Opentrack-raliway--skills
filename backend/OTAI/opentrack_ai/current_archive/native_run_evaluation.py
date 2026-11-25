"""Evaluate selected English Windows OpenTrack 1.7 run outputs and frozen evidence."""

from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re

from . import native_evaluation_formats as fmt
from .runfile_parameters import time_seconds


STOCK_EXE_SHA = 'f1274d5c03ac7fe07196c999eb088e6de7414a1da55b0276d3956513c866f104'
MAX_BYTES = 128 * 1024 * 1024
ERROR_LEVELS = {'ERROR', 'SEVERE', 'FATAL'}
KNOWN_LEVELS = ERROR_LEVELS | {'NORMAL', 'WARNING', 'INFO', 'INFORMATION', 'NOTE'}
SAFE_FILE = re.compile(r'[^<>:"/\\|?*\x00-\x1f]+')
CATALOG_KEYS = {'DestInfoFile', 'DepotFile', 'TrainFile', 'CourseFile', 'StationFile', 'TimetableFile'}


def basename(name):
    fmt.require(isinstance(name, str) and 0 < len(name) <= 240 and SAFE_FILE.fullmatch(name)
                and name not in {'.', '..'} and not name.endswith(('.', ' ')), 'Invalid file or Course name')
    return name


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_member(root, name, *, nested=False, started=None, secure_bytes=None):
    parts = PurePosixPath(name).parts if nested else (basename(name),)
    fmt.require(parts and all(basename(part) for part in parts) and '/'.join(parts) == name,
                'Invalid evidence member path')
    candidate = root.joinpath(*parts)
    fmt.require(candidate.resolve(strict=True) == candidate and candidate.is_file(),
                'Evidence member must be an ordinary file below its declared root')
    before = candidate.stat()
    fmt.require(before.st_size <= MAX_BYTES, 'Evidence file exceeds size limit')
    fmt.require(started is None or before.st_mtime >= started - 2,
                'Native output predates the recorded launch')
    if secure_bytes is None:
        with candidate.open('rb') as file:
            opened = os.fstat(file.fileno())
            fmt.require((before.st_dev, before.st_ino) == (opened.st_dev, opened.st_ino),
                        'Evidence identity changed while opening')
            data = file.read(MAX_BYTES + 1)
    else:
        data = secure_bytes(candidate)
    after = candidate.stat()
    fmt.require(candidate.resolve(strict=True) == candidate
                and len(data) <= MAX_BYTES and len(data) == before.st_size
                and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Evidence file changed while read')
    return data


def decode(data):
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode('latin-1')


def plan(expectations):
    courses = []
    names = set()
    for item in expectations['courses']:
        expected = {'course_id': item} if isinstance(item, str) else dict(item)
        name = basename(expected['course_id'])
        fmt.require(name.casefold() not in names and len(name) <= 180, 'Duplicate or overlong expected Course')
        names.add(name.casefold())
        fmt.require(expected.get('terminal_event', 'Arr.') in {'Arr.', 'Pass'},
                    'Unsupported terminal event requirement')
        if expected.get('distance_tolerance_m') is not None:
            fmt.require(expected.get('distance_m') is not None
                        and fmt.number(expected['distance_tolerance_m']) >= 0,
                        'Distance tolerance requires an expected distance and a nonnegative finite value')
        for field in ('origin_station', 'terminal_station'):
            if expected.get(field) is not None:
                fmt.require(isinstance(expected[field], str) and expected[field].strip() == expected[field]
                            and expected[field], 'Expected station must be the exact nonempty display name')
        courses.append(expected)
    fmt.require(1 <= len(courses) <= 10000, 'Expect 1 to 10000 unique Courses')
    return courses


def frozen_configuration(blob, run_file, evidence, hashes):
    from .prepare_contract.auxiliary import records

    options = {}
    documents = []
    for key, value, _ in records(blob):
        if key in CATALOG_KEYS | {'OutputPath', 'Stop Time', 'Stop Day Offset', 'Delay Scenario'}:
            options[key] = value
        elif key == 'Infrastructure Document':
            documents.append(value)
    fmt.require(CATALOG_KEYS | {'OutputPath'} <= options.keys() and documents,
                'Frozen run lacks its explicit catalog, document or output paths')
    command = evidence.get('command', [])
    run_paths = [arg.split('=', 1)[1] for arg in command
                 if isinstance(arg, str) and arg.startswith('-runfile=')]
    fmt.require(len(run_paths) == 1, 'Recorded launch lacks one explicit run path')
    actual_path = Path(run_paths[0])
    relative_parts = PurePosixPath(run_file).parts
    project = actual_path.parents[len(relative_parts) - 1]
    fmt.require(actual_path.is_absolute() and project.joinpath(*relative_parts) == actual_path,
                'Launch path does not identify frozen run member')
    dependencies = [options[key] for key in CATALOG_KEYS] + documents
    for value in dependencies:
        dependency = Path(value)
        fmt.require(dependency.is_absolute() and dependency.is_relative_to(project)
                    and dependency.relative_to(project).as_posix() in hashes,
                    f'Frozen run dependency is not backed by inputs: {value}')
    return {'paths': {key: options[key] for key in CATALOG_KEYS | {'OutputPath'}},
            'topology_documents': documents, 'stop_clock': options.get('Stop Time'),
            'stop_day_offset': options.get('Stop Day Offset'), 'project_root': project,
            'delay_scenario': options.get('Delay Scenario')}


def bound_run(evidence, output, secure_bytes):
    if evidence is None:
        return None, None, {}, None, None
    fmt.require(type(evidence['exit_code']) is int, 'Process return code must be an integer')
    start = datetime.fromisoformat(evidence['started_utc'])
    fmt.require(start.utcoffset() is not None, 'Launch time must include a timezone')
    names = [basename(name) for name in evidence['output_files']]
    fmt.require(len(set(name.casefold() for name in names)) == len(names), 'Duplicate output-file names')
    if evidence.get('output_directory'):
        fmt.require(Path(evidence['output_directory']).resolve() == output, 'Process output directory mismatch')
    output_hashes = evidence.get('output_sha256', {})
    fmt.require(isinstance(output_hashes, dict) and set(output_hashes) <= set(names), 'Invalid output-hash inventory')
    hashes = evidence.get('input_sha256')
    evidence_location = evidence.get('evidence_directory')
    executable = evidence.get('executable_sha256')
    provenance = {'process_exit_code': evidence['exit_code'], 'archive_hashes_verified': False,
                  'executable_matches': executable == STOCK_EXE_SHA, 'frozen_member_count': 0}
    frozen = None
    if hashes and evidence_location is not None:
        evidence_root = Path(evidence_location).resolve(strict=True)
        inputs = (evidence_root / 'inputs').resolve(strict=True)
        fmt.require(inputs == evidence_root / 'inputs', 'Frozen inputs directory was redirected')
        fmt.require(isinstance(hashes, dict) and len(hashes) <= 2048, 'Invalid frozen input inventory')
        run_members = [name for name in hashes if name.lower().endswith('.run')]
        run_file = evidence.get('run_file')
        if run_file is None and len(run_members) == 1:
            run_file = run_members[0]
        fmt.require(run_file in run_members, 'Use one identified frozen original .run')
        for name, expected_hash in hashes.items():
            data = read_member(inputs, name, nested=True, secure_bytes=secure_bytes)
            fmt.require(digest(data) == expected_hash,
                        f'Frozen input hash mismatch for {name}')
            if name == run_file:
                frozen = frozen_configuration(data, run_file, evidence, hashes)
        provenance['archive_hashes_verified'] = True
        provenance['frozen_member_count'] = len(hashes)
        if executable is None:
            original_receipt = json.loads(read_member(evidence_root, 'before.json', secure_bytes=secure_bytes))
            fmt.require(original_receipt.get('input_sha256') == hashes
                        and original_receipt.get('started_utc') == evidence['started_utc'],
                        'Recorded launch and frozen input manifest differ')
            provenance['executable_matches'] = original_receipt.get('executable_sha256') == STOCK_EXE_SHA
    return start.timestamp(), set(names), output_hashes, provenance, frozen


def read_receipts(directory, *, secure_bytes=None):
    root = Path(directory).resolve(strict=True)
    before = json.loads(read_member(root, 'before.json', secure_bytes=secure_bytes))
    process = json.loads(read_member(root, 'process.json', secure_bytes=secure_bytes))
    fmt.require(isinstance(before, dict) and isinstance(process, dict), 'Expected original launch and process receipts')
    fmt.require(all(before[key] == process[key] for key in before.keys() & process.keys()),
                'Process receipt conflicts with the recorded launch')
    return {**before, **process, 'evidence_directory': root}


class OutputFiles:
    def __init__(self, output, started, names, expected_hashes, secure_bytes):
        self.output = output
        self.started = started
        self.names = names if names is not None else {p.name for p in output.iterdir() if p.is_file()}
        self.expected_hashes = expected_hashes
        self.secure_bytes = secure_bytes
        self.hashes = {}

    def read(self, name):
        fmt.require(name in self.names, f'Missing native output {name}')
        data = read_member(self.output, name, started=self.started, secure_bytes=self.secure_bytes)
        actual = digest(data)
        if name in self.expected_hashes:
            fmt.require(self.expected_hashes[name] == actual, f'Native output hash mismatch for {name}')
        self.hashes[name] = actual
        return decode(data)


def stop_requirements(events, intervals, speeds, stops, tolerance):
    results = []
    begin = 0
    for stop in stops:
        minimum = fmt.number(stop['min_dwell_s'])
        fmt.require(minimum > 0, 'Required stop dwell must be positive')
        candidates = ((i, arrival, departure) for i, (arrival, departure) in
                      enumerate(zip(events, events[1:])) if i >= begin
                      and (arrival['kind'], departure['kind']) == ('Arr.', 'Dep.')
                      and arrival['station'] == departure['station'] == stop['station'])
        detail = {'station': stop['station'], 'verified': False}
        for index, arrival, departure in candidates:
            begin = index + 2
            a, d = arrival['time_s'], departure['time_s']
            detail.update(arrival=arrival, departure=departure, actual_dwell_s=d - a)
            lower = stop.get('position_min_m', float('-inf'))
            upper = stop.get('position_max_m', float('inf'))
            fmt.require(lower <= upper, 'Invalid required stop position interval')
            plateau = next((row for row in intervals if abs(row['start_s'] - a) <= tolerance
                            and abs(row['end_s'] - d) <= tolerance
                            and row['duration_s'] + 0.02 >= minimum
                            and lower - 0.17 <= row['distance_reference_m'] <= upper + 0.17), None)
            if plateau is not None and any(time > plateau['end_s'] and speed > 0 for time, speed in speeds):
                detail.update(verified=True, stationary_interval=plateau, resumed_movement=True)
            break
        results.append(detail)
    return results


def course_result(files, expected, stats, window_end, include_series):
    cid = expected['course_id']
    prefix = f'OT_{cid}'
    events = fmt.timetable(files.read(prefix + '.tt'), cid)
    native_speed = fmt.series(files.read(prefix + '.vt'), 'vt', cid)
    native_distance = fmt.series(files.read(prefix + '.st1'), 'st1', cid)
    speed_factor = 1 if native_speed['units'][1] == 'km/h' else 1.609344
    distance_factor = 1000 if native_distance['units'][1] == 'km' else 1609.344
    speeds = [(time, value * speed_factor) for time, value in native_speed['points']]
    positions = [(time, value * distance_factor) for time, value in native_distance['points']]
    fmt.require(speeds and positions, 'Missing actual speed or position samples')
    fmt.require(all(a[1] <= b[1] for a, b in zip(positions, positions[1:])),
                'Course-path distance/time reference decreases')
    tolerance = fmt.number(expected.get('event_tolerance_s', 1.05))
    fmt.require(0.01 <= tolerance <= 5, 'Event-clock tolerance outside 0.01–5 seconds')
    origin = next((event for event in events if event['kind'] == 'Dep.'), None)
    terminal = events[-1] if events else None
    intervals = fmt.stationary_intervals(speeds, positions)
    displacement = positions[-1][1] - positions[0][1]
    stops = stop_requirements(events, intervals, speeds, expected.get('required_stops', []), tolerance)
    checks = {
        'departed': (origin is not None
                     and origin['station'] == expected.get('origin_station', origin['station'])),
        'terminal_station_named': bool(expected.get('terminal_station')),
        'terminal_event_matched': (terminal is not None and terminal['station'] == expected.get('terminal_station')
                                   and terminal['kind'] == expected.get('terminal_event', 'Arr.')),
        'required_stops_verified': all(item['verified'] for item in stops),
        'window_constraint_met': window_end is None or bool(terminal and terminal['time_s'] <= window_end),
        'course_statistics_matched': False,
        'motion_to_terminal': False,
        'terminal_stop_verified': False,
        'expected_distance_matched': False,
    }
    stat = stats[0] if len(stats) == 1 else None
    moved = bool(origin and terminal and displacement > 0 and
                 any(origin['time_s'] <= time <= terminal['time_s'] + tolerance and value > 0
                     for time, value in speeds))
    checks['motion_to_terminal'] = moved
    value = expected.get('distance_m')
    tolerance_m = expected.get('distance_tolerance_m')
    tolerance_m = 1.75 if tolerance_m is None else fmt.number(tolerance_m)
    difference_m = None if value is None else abs(fmt.number(value) - displacement)
    if stat is not None and origin and terminal:
        terminal_kind = expected.get('terminal_event', 'Arr.')
        require_stop = expected.get('terminal_stop', terminal_kind == 'Arr.')
        terminal_clock = stat['last_arrival_s'] if terminal_kind == 'Arr.' else stat['end_s']
        checks['course_statistics_matched'] = (abs(terminal_clock - terminal['time_s']) <= tolerance
                                              and abs(stat['first_departure_s'] - origin['time_s']) <= tolerance
                                              and abs(stat['distance_m'] - displacement) <= 1.75)
        last_motion = max((time for time, value in speeds if value > 0), default=-1)
        final_zero = next((time for time, value in speeds if value == 0 and time > last_motion
                           and abs(time - terminal['time_s']) <= tolerance), None)
        checks['terminal_stop_verified'] = (not require_stop or (final_zero is not None
                                            and any(abs(t - final_zero) <= tolerance and
                                                    abs(p - positions[-1][1]) <= 0.17 for t, p in positions)))
        checks['expected_distance_matched'] = difference_m is None or difference_m <= tolerance_m
    summary = {'course_id': cid, 'completion_verified': all(checks.values()), 'checks': checks,
               'events': events, 'required_stops': stops, 'stationary_intervals': intervals,
               'raw_statistics_rows': len(stats), 'statistics': stat, 'displacement_m': displacement,
               'expected_distance_m': value, 'distance_difference_m': difference_m,
               'distance_tolerance_m': tolerance_m if value is not None else None,
               'speed': fmt.series_summary(native_speed), 'distance': fmt.series_summary(native_distance),
               'origin_event': origin, 'last_observed_event': terminal}
    if include_series:
        summary['trajectory'] = {'speed_kmh': speeds, 'distance_reference_m': positions}
    return summary


def configured_window_matches(observed, window_end):
    if window_end is None:
        return None
    if not observed:
        return False
    shown = observed.rsplit(' - ', 1)[-1].strip()
    parts = re.fullmatch(r'(?:(\d{1,5})\s*/\s*)?([0-9]{2}:[0-9]{2}:[0-9]{2})', shown, re.ASCII)
    if parts is None:
        return False
    day, clock = parts.groups()
    try:
        return time_seconds(clock.encode('ascii'), (day or '0').encode('ascii')) == window_end
    except ValueError:
        return False


def protocol_matches_frozen_run(protocol, frozen, window_end):
    for key, value in frozen['paths'].items():
        fmt.require(protocol['paths'].get(key) is not None and Path(protocol['paths'][key]) == Path(value),
                    f'Original protocol {key} differs from frozen run')
    shown = {Path(value) for value in protocol['active_topology_files'] if Path(value).is_absolute()}
    fmt.require(shown == {Path(value) for value in frozen['topology_documents']},
                'Original protocol topology paths differ from frozen run')
    if frozen.get('delay_scenario') == '-1':
        fmt.require(protocol['delay_scenario'] == '-1', 'Original protocol does not confirm the frozen Defined delay scenario')
    if window_end is not None:
        day = frozen['stop_day_offset']
        clock = frozen['stop_clock']
        fmt.require(day is not None and clock is not None
                    and time_seconds(clock.encode('ascii'), day.encode('ascii')) == window_end,
                    'Absolute expected end differs from frozen .run day and clock')


def supplementary(files, courses, include_series):
    from . import native_monitoring_formats as monitoring

    report = {'course_series': {}, 'station_statistics': None, 'occupations': {}, 'occupation_statistics': None,
              'course_physical_series': {}, 'power_supplies': {}, 'instruments': {},
              'instrument_signals': {}, 'warnings': []}

    def optional(name, parser):
        if name not in files.names:
            return None
        try:
            return parser(files.read(name))
        except (OSError, ValueError, KeyError) as exc:
            report['warnings'].append({'file': name, 'reason': str(exc)})
            return None

    report['station_statistics'] = optional('OT_StationStatistics.txt', fmt.station_statistics)
    report['occupation_statistics'] = optional('OT_OccStatistics.txt', monitoring.occupation_statistics)
    for name in sorted(files.names):
        if name.startswith('OT_') and name.endswith('.Pt'):
            data = optional(name, monitoring.power_supply)
            if data is not None:
                report['power_supplies'][name] = data if include_series else {'name': data['name'], **data['summary']}
        if name.startswith('OT_') and name.endswith('.ins'):
            data = optional(name, monitoring.instruments)
            if data is not None:
                report['instruments'][name] = data if include_series else {key: value for key, value in data.items()
                                                                          if key != 'records'}
        if name.startswith('OT_') and name.endswith('.sig'):
            data = optional(name, monitoring.instrument_signals)
            if data is not None:
                report['instrument_signals'][name] = {'signal': data['signal'], 'record_count': len(data['records']),
                                                      **({'records': data['records']} if include_series else {})}
        if name.startswith('OT_Occ_') and name.endswith('.occ'):
            data = optional(name, fmt.occupations)
            if data is None:
                continue
            cycles, invalid = fmt.occupation_intervals(data)
            durations = [cycle['occupation_s'][1] - cycle['occupation_s'][0] for cycle in cycles
                         if None not in cycle['occupation_s']]
            entry = {'events_by_type': dict(Counter(row['event'] for row in data)),
                     'unknown_clock_count': sum(row['time_s'] is None for row in data),
                     'courses': sorted({row['course_id'] for row in data}),
                     'recorded_cycles': len(cycles), 'incomplete_or_invalid_cycles': invalid,
                     'cycles_with_both_occupation_clocks': len(durations),
                     'sum_logged_occupation_duration_s': sum(durations)}
            if include_series:
                entry['events'] = data
                entry['intervals'] = cycles
            report['occupations'][name] = entry
    for cid in courses:
        measurements = {}
        for extension in fmt.SERIES.keys() - {'vt', 'st1'}:
            name = f'OT_{cid}.{extension}'
            data = optional(name, lambda raw: fmt.series(raw, extension, cid))
            if data is not None:
                measurements[extension] = data if include_series else fmt.series_summary(data)
        if measurements:
            report['course_series'][cid] = measurements
        physical = optional(f'OT_{cid}.tsvP', lambda raw: fmt.physical_series(raw, cid))
        if physical:
            report['course_physical_series'][cid] = {
                'sample_count': len(physical), 'first': physical[0], 'last': physical[-1],
                'peak_power_in_kw': max(row['power_input_kw'] for row in physical),
                'energy_input_change_mj': physical[-1]['energy_input_mj'] - physical[0]['energy_input_mj'],
                **({'samples': physical} if include_series else {}),
            }
    return report


def incident_outcome(req, listed, events):
    target = req.get('target')
    course = req.get('course_id')
    start_clock, stop_clock = req.get('started_clock'), req.get('stopped_clock')
    fmt.require(target is not None or not any((course, start_clock, stop_clock)),
                'Specify the original incident message target when requiring its Course or clocks')
    for clock in (start_clock, stop_clock):
        if clock is not None:
            fmt.require(isinstance(clock, str) and re.fullmatch(r'[0-9]{2}:[0-5][0-9]:[0-5][0-9]', clock),
                        'Expected incident clock must use the native HH:MM:SS form')
    matches = [event for event in events if event['subject'] == target
               and (course is None or event['course_id'] == course)]
    started_event = stopped_event = None
    for event in matches:
        if event['transition'] == 'started' and (start_clock is None or event['clock'] == start_clock):
            started_event = event
        if started_event and event['transition'] == 'stopped' and (stop_clock is None or event['clock'] == stop_clock):
            stopped_event = event
            break
    return dict(name=req['name'], protocol_listed=listed, message_target=target,
                started_observed=started_event is not None,
                stopped_observed=stopped_event is not None,
                start_event=started_event, stop_event=stopped_event,
                expectation_met=listed and (target is None or stopped_event is not None))


def physical_peaks(requirements, files, selected_courses, launch):
    fmt.require(launch and isinstance(requirements, list) and len(requirements) <= 128,
                'Physical checks require a bound original run and at most 128 requirements')
    results = []
    trajectories = {}
    for item in requirements:
        cid = item['course_id']
        quantity = item['quantity']
        fmt.require(cid in selected_courses, 'Physical check Course must appear in the expected Course outcomes')
        fmt.require(quantity in {'tractive_effort_kn', 'mechanical_power_kw', 'power_input_kw'},
                    'Unsupported native physical quantity')
        begin, end = map(fmt.number, (item['begin_s'], item['end_s']))
        fmt.require(0 <= begin < end, 'Expected physical window must increase')
        minimum = item.get('minimum_moving_samples', 1)
        fmt.require(type(minimum) is int and 1 <= minimum <= 1000000, 'Invalid minimum moving sample count')
        lower = fmt.number(item['peak_min']) if item.get('peak_min') is not None else None
        upper = fmt.number(item['peak_max']) if item.get('peak_max') is not None else None
        fmt.require((lower is not None or upper is not None) and (lower is None or upper is None or lower <= upper),
                    'Specify at least one ordered physical peak limit')
        if cid not in trajectories:
            name = f'OT_{cid}.tsvP'
            fmt.require(name in files.expected_hashes, 'Physical check requires a launcher SHA-256 for the output')
            trajectories[cid] = fmt.physical_series(files.read(name), cid)
        moving = [row for row in trajectories[cid] if begin <= row['time_s'] <= end and row['speed_kmh'] > 0]
        sample = max(moving, key=lambda row: row[quantity], default=None)
        peak = sample[quantity] if sample is not None else None
        verified = len(moving) >= minimum and (lower is None or peak >= lower) and (upper is None or peak <= upper)
        results.append({'course_id': cid, 'quantity': quantity, 'window_s': [begin, end],
                        'moving_samples': len(moving), 'minimum_moving_samples': minimum,
                        'peak_min': lower, 'peak_max': upper, 'observed_peak': peak,
                        'observed_peak_time_s': sample['time_s'] if sample is not None else None, 'verified': verified})
    return results


def signal_position(text, course, label):
    fmt.headers(text, 'OT_Signals')
    fmt.course_header(text, 'Signal Positions', course)
    fmt.require(re.findall(r'^// x-Legend[ \t]*:[ \t]*\[([^\[\]\r\n]+)\]\s*$', text, re.M) == ['km'],
                'Original signal positions must use kilometres')
    matches = []
    for row in fmt.data_rows(text):
        fmt.require(len(row) in {3, 4}, 'Unexpected original signal position row')
        if row[2] == label:
            fmt.require(len(row) == 4 and row[1] in {'MS', 'MDS'},
                        'Reservation headway requires an original main signal')
            matches.append(fmt.number(row[0]))
    fmt.require(len(matches) == 1, 'Expected one exact main signal label in the recorded Course path')
    return matches[0]


def signal_reservation_clock(files, course, label):
    legend, reservation = (f'OT_{course}{suffix}' for suffix in ('.sigpos', '.step1'))
    fmt.require({legend, reservation} <= files.expected_hashes.keys(),
                'Reservation headway requires launcher SHA-256 for both original signal and reservation files')
    position = signal_position(files.read(legend), course, label)
    parsed = fmt.series(files.read(reservation), 'step1', course)
    points = parsed['points']
    fmt.require(parsed['units'] == ['s', 'km'] and points,
                'Use original reservation records in seconds and kilometres')
    # The final vertical point can stand alone at the terminal. A horizontal
    # spatial increment at one recorded clock is the actual reservation.
    times = [a[0] for a, b in zip(points, points[1:]) if a[0] == b[0] and a[1] == position < b[1]]
    fmt.require(len(times) == 1, 'Expected one recorded reservation starting at the selected signal')
    return position, times[0]


def frozen_signal_identities(requirements, frozen, evidence, secure_bytes):
    from . import native_monitoring, writer

    labels = {item['signal_label'] for item in requirements}
    found = {}
    inputs = evidence['evidence_directory'] / 'inputs'
    for name in frozen['topology_documents']:
        path = Path(name)
        relative = path.relative_to(frozen['project_root']).as_posix()
        data = read_member(inputs, relative, nested=True, secure_bytes=secure_bytes)
        fmt.require(digest(data) == evidence['input_sha256'][relative], 'Frozen signal worksheet differs from its manifest')
        document, _ = writer.load_next_compatible(data)
        _, models = native_monitoring.models(document)
        for signal_id, signal in models.items():
            if writer.kind(signal) != 'OTSignalModel':
                continue
            owner = signal.contents[7].value
            fmt.require(owner is not None and owner.contents[11].value is signal,
                        'Frozen signal does not match its directional End')
            branch = models.get(owner.contents[8].value)
            addition = writer.string(owner.contents[18].value) or (
                writer.string(branch.contents[18].value) if branch is not None else None)
            name = writer.string(signal.contents[13].value)
            label = f'{addition}_{name}' if addition and name else addition or name
            if label in labels:
                fmt.require(label not in found, f'Original signal label is ambiguous across frozen worksheets: {label}')
                found[label] = {'document': path.stem, 'signal_model_id': signal_id}
    fmt.require(set(found) == labels, 'Could not bind all selected signal labels to frozen original worksheets')
    return found


def signal_reservation_headways(requirements, files, selected_courses, launch):
    fmt.require(launch and isinstance(requirements, list) and len(requirements) <= 128,
                'Reservation headways require a bound original run and at most 128 requirements')
    results = []
    positions = {}
    for item in requirements:
        leading, following, label = item['leading_course'], item['following_course'], item['signal_label']
        fmt.require(leading != following and {leading, following} <= selected_courses,
                    'Reservation headway requires two distinct expected Courses')
        fmt.require(isinstance(label, str) and 0 < len(label) <= 180, 'Specify the exact original signal label')
        minimum = fmt.number(item['minimum_s'])
        fmt.require(minimum > 0, 'Reservation headway must be positive')
        for course in (leading, following):
            key = (course, label)
            if key not in positions:
                positions[key] = signal_reservation_clock(files, course, label)
        lead, follow = positions[leading, label], positions[following, label]
        headway = round(follow[1] - lead[1], 2)
        results.append({'signal_label': label, 'leading_course': leading, 'following_course': following,
                        'minimum_s': minimum, 'headway_s': headway, 'timestamp_tolerance_s': .01,
                        'leading_position_km': lead[0], 'following_position_km': follow[0],
                        'leading_reservation_s': lead[1], 'following_reservation_s': follow[1],
                        'verified': headway + .010001 >= minimum})
    return results


def evaluate_run(output_dir, expectations, evidence=None, *, secure_bytes=None):
    """Evaluate raw outputs. Only a proven original launch with declared arrivals can pass."""
    output = Path(output_dir).resolve(strict=True)
    fmt.require(output.is_dir(), 'Native output directory is missing')
    expected = plan(expectations)
    started, names, output_hashes, provenance, frozen = bound_run(evidence, output, secure_bytes)
    files = OutputFiles(output, started, names, output_hashes, secure_bytes)
    errors = []
    stats = {}
    messages = None
    protocol = None
    for name, parser in (('OT_CourseStatistics.txt', fmt.course_statistics),
                         ('OT_Messages.txt', fmt.messages)):
        try:
            data = parser(files.read(name))
            if name == 'OT_Messages.txt':
                messages = data
            else:
                stats = data
        except (OSError, ValueError, KeyError) as exc:
            errors.append(f'{name}: {exc}')
    candidates = sorted(name for name in files.names if re.fullmatch(r'OT_Protocol\.[^/\\]+\.txt', name))
    try:
        fmt.require(len(candidates) == 1, 'Expected exactly one native protocol file for this run')
        protocol = fmt.protocol(files.read(candidates[0]))
        fmt.require(Path(protocol['paths']['OutputPath']).resolve() == output, 'Protocol output path mismatch')
    except (OSError, ValueError, KeyError) as exc:
        errors.append(f'Native protocol: {exc}')
    window_end = expectations.get('window_end_s')
    if window_end is not None:
        window_end = fmt.number(window_end)
        fmt.require(window_end > 0 and window_end.is_integer(), 'Expected absolute window end must be integer seconds')
    configured = configured_window_matches((protocol or {}).get('configured_window'), window_end)
    if configured is False:
        errors.append('Native protocol configured end clock differs from expectation')
    frozen_protocol_match = False
    if protocol is not None and frozen is not None:
        try:
            protocol_matches_frozen_run(protocol, frozen, window_end)
            frozen_protocol_match = True
        except (ValueError, KeyError) as exc:
            errors.append(f'Native readback binding: {exc}')
    if provenance is not None:
        provenance['protocol_matches_frozen_run'] = frozen_protocol_match
    end_message = False
    if messages is not None:
        levels = messages['levels'].keys()
        if not levels or levels & ERROR_LEVELS or levels - KNOWN_LEVELS:
            errors.append('Native message log is empty or contains error or unrecognized severity')
        lifecycle = [item['message'] for item in messages['lifecycle']]
        if not any(text.startswith('Start of Simulation') for text in lifecycle):
            errors.append('Native message log lacks Start of Simulation')
        if any(text.lower().startswith('cancel') for text in lifecycle):
            errors.append('Native simulation was canceled')
        if any(re.search(r'\bdeadlock\b', item['message'], re.I) for item in messages['diagnostics']):
            errors.append('Native message log mentions a deadlock; review runtime evidence')
        end_message = any(text.startswith('End of Simulation') for text in lifecycle)
    if expectations.get('require_end_message', False) and not end_message:
        errors.append('Native runtime did not record an explicit end message')
    incidents_seen = {item['name'] for item in (protocol or {}).get('listed_incidents', [])}
    incident_checks = []
    info = (messages or {}).get('incident_events', [])
    for requirement in expectations.get('expected_incidents', []):
        req = {'name': requirement} if isinstance(requirement, str) else requirement
        outcome = incident_outcome(req, req['name'] in incidents_seen, info)
        if not outcome['expectation_met']:
            errors.append(f'Expected incident evidence missing for {req["name"]}')
        incident_checks.append(outcome)
    used = set((protocol or {}).get('used_courses', []))
    include_series = expectations.get('include_series', False)
    results = []
    for course in expected:
        cid = course['course_id']
        try:
            record = course_result(files, course, stats.get(cid, []), window_end, include_series)
            record['checks']['used_course_listed'] = cid in used
            record['completion_verified'] = all(record['checks'].values())
            results.append(record)
        except (OSError, ValueError, KeyError) as exc:
            results.append({'course_id': cid, 'completion_verified': False, 'error': str(exc)})
    verified_courses = sum(item['completion_verified'] for item in results)
    launch = bool(provenance and provenance['process_exit_code'] == 0 and provenance['archive_hashes_verified']
                  and provenance['executable_matches'] and frozen_protocol_match)
    selected_courses = {course['course_id'] for course in expected}
    peaks = []
    if expectations.get('expected_physical_peaks'):
        try:
            peaks = physical_peaks(expectations['expected_physical_peaks'], files, selected_courses, launch)
            for peak in peaks:
                if not peak['verified']:
                    errors.append(f'Original physical peak check failed: {peak["course_id"]} {peak["quantity"]}')
        except (OSError, ValueError, TypeError, KeyError) as exc:
            errors.append(f'Native physical evidence: {exc}')
    headways = []
    if expectations.get('expected_signal_reservation_headways'):
        try:
            requirements = expectations['expected_signal_reservation_headways']
            headways = signal_reservation_headways(requirements, files, selected_courses, launch)
            identities = frozen_signal_identities(requirements, frozen, evidence, secure_bytes)
            for item in headways:
                item.update(identities[item['signal_label']])
                if not item['verified']:
                    errors.append(f'Original signal reservation headway check failed: {item["signal_label"]}')
        except (OSError, ValueError, TypeError, KeyError) as exc:
            errors.append(f'Native signal reservation evidence: {exc}')
    separations = []
    if expectations.get('expected_following_separations'):
        from . import native_following

        try:
            fmt.require(launch, 'Following checks require a bound original launch')
            separations = native_following.audit(expectations['expected_following_separations'], files, results,
                frozen, evidence, read_member=read_member, digest=digest, secure_bytes=secure_bytes)
            for item in separations:
                if not item['verified']:
                    errors.append(f'Original reference separation failed: {item["leading_course"]} to {item["following_course"]}')
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            errors.append(f'Native following evidence: {exc}')
    exclusive = []
    if expectations.get('exclusive_occupation_groups'):
        from . import native_exclusion

        try:
            exclusive = native_exclusion.audit(expectations['exclusive_occupation_groups'], files, frozen, evidence,
                read_member=read_member, digest=digest, basename=basename, secure_bytes=secure_bytes)
            for resource in exclusive:
                if not resource['verified']:
                    errors.append(f'Original exclusive resource check failed: {resource["resource"]}')
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            errors.append(f'Native exclusive resource evidence: {exc}')
    extra = supplementary(files, [course['course_id'] for course in expected], include_series) \
        if expectations.get('include_supplementary', False) else None
    return {'native_run_verified': launch and not errors and verified_courses == len(expected),
            'scope': 'Declared Course outcomes, optional incidents, physical peaks, headways, reference gaps and logged exclusive resources.',
            'verified_course_count': verified_courses, 'expected_course_count': len(expected),
            'all_expected_courses_completed': verified_courses == len(expected), 'courses': results,
            'messages': messages, 'protocol': protocol, 'incident_expectations': incident_checks,
            'exclusive_occupation_groups': exclusive, 'physical_peaks': peaks,
            'signal_reservation_headways': headways,
            'following_separations': separations,
            'configured_end_clock_matches': configured, 'end_message_observed': end_message,
            'provenance': provenance, 'errors': errors, 'supplementary': extra,
            'output_sha256': dict(files.hashes)}
