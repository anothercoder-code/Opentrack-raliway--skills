"""Check original split/join outputs against the frozen operating plan."""

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from math import ceil, floor
from pathlib import Path
import re

from verify_reference_platform_run import STOCK_EXE_SHA


FAILURE = re.compile(
    r'Composition changed after Split|Itinerary changed after Split|No more Engine after Split|'
    r'Phys\. Join not possible|No Join with Course|No Engine on Train|Split .*not possible',
    re.IGNORECASE,
)
RAW_LENGTH = re.compile(r'OTSimCourse kurs = (\S+)\s+(vor split|nach split|nach join)\s+laenge = ([0-9]+(?:\.[0-9]+)?)')
EVENT_TOLERANCE_S = 1.05
POSITION_ROUNDING_M = 0.5
MESSAGE_CLOCK = re.compile(r'(?:(\d{1,5}) / )?((?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d)', re.ASCII)


def _need(condition, description):
    if not condition:
        raise ValueError(description)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _seconds(clock):
    hours, minutes, seconds = map(int, clock.split(':'))
    return hours * 3600 + minutes * 60 + seconds


def absolute_message_clock(clock, arrival, departure, tolerance=EVENT_TOLERANCE_S):
    match = MESSAGE_CLOCK.fullmatch(clock)
    _need(match is not None, 'Unknown original composition message clock')
    day, local = match.groups()
    clock_s = _seconds(local)
    first = max(0, ceil((arrival - tolerance - clock_s) / 86400))
    last = floor((departure + tolerance - clock_s) / 86400)
    if day is not None:
        first = max(first, int(day))
        last = min(last, int(day))
    _need(first == last, 'Original composition message day is ambiguous or outside the selected stop')
    return first * 86400 + clock_s


def traction_rows(contents):
    for line in contents.splitlines():
        if not line or line.startswith('//'):
            continue
        cells = line.split('\t')
        _need(len(cells) >= 6, 'Malformed native traction evidence')
        yield tuple(float(cells[i]) for i in (0, 2, 3, 4, 5))


def traction_samples(rows, start, end):
    kept = {}
    for time_s, speed, acceleration, effort, resistance in rows:
        if start < time_s < end and 0 < speed <= 10 and acceleration > 0 and effort > 0:
            kept.setdefault(speed, (time_s, effort, resistance))
    return kept


def matching_departure_traction(event, course, event_seconds, contents):
    """Compare the original tractive effort at equal low speeds for identical powered units."""
    powered = [*event['initial_main']['formation'], *event['initial_other']['formation']]
    if not all(row['kind'] == 'engine' and row['name'] == powered[0]['name'] for row in powered):
        return None
    before_count = len(event['initial_main']['formation'])
    other_count = len(event['initial_other']['formation'])
    after_count = before_count + (other_count if event['kind'] == 'join' else -other_count)
    expected_ratio = after_count / before_count
    departures = {course['origin_event']['time_s']}
    departures.update(row['time_s'] for row in course['events'] if row['kind'] == 'Dep.')
    initial = max((stamp for stamp in departures if stamp < event_seconds), default=None)
    onward = min((stamp for stamp in departures if stamp > event_seconds), default=None)
    if initial is None or onward is None:
        return None

    rows = list(traction_rows(contents))
    before = traction_samples(rows, initial, min(initial + 6, event_seconds))
    after = traction_samples(rows, onward, onward + 6)
    compared = []
    for speed in sorted(before.keys() & after.keys()):
        t1, force1, resistance1 = before[speed]
        t2, force2, resistance2 = after[speed]
        ratio = force2 / force1
        compared.append({
            'speed_kmh': speed, 'before_time_s': t1, 'after_time_s': t2,
            'before_tractive_effort_kn': force1, 'after_tractive_effort_kn': force2,
            'before_resistance_kn': resistance1, 'after_resistance_kn': resistance2,
            'after_to_before_force_ratio': round(ratio, 6),
            'matches_identical_power_unit_count_ratio': abs(ratio - expected_ratio) <= 0.01,
        })
    if not compared:
        return None
    return {
        'expected_identical_power_unit_count_ratio': expected_ratio,
        'prior_departure_s': initial,
        'onward_departure_s': onward,
        'matching_speed_sample_count': len(compared),
        'tractive_effort_change_corrobates_archives': len(compared) >= 2 and all(
            item['matches_identical_power_unit_count_ratio'] for item in compared),
        'samples': compared[:12],
    }


def verify_occurrence(course, occurrence, clocks):
    """Bind all composition messages to one actual, distance-verified station stop."""
    station = occurrence['station']
    planned = occurrence['planned']
    distance = course['distance']
    factor = {'km': 1000, 'mi': 1609.344}[distance['units'][1]]
    reference_m = distance['first'][1] * factor + occurrence['distance_m']
    edge_length = occurrence['stop_edge_length_m']
    _need(edge_length > 0, 'Selected occurrence requires a validated directed stopping Edge')
    lower, upper = reference_m - edge_length - POSITION_ROUNDING_M, reference_m + POSITION_ROUNDING_M
    matches = []
    for a, d in zip(course['events'], course['events'][1:]):
        if (a['kind'], d['kind'], a['station'], d['station']) != ('Arr.', 'Dep.', station, station):
            continue
        if (a.get('planned_s'), d.get('planned_s')) != (planned['arrival_s'], planned['departure_s']):
            continue
        for plateau in course['stationary_intervals']:
            if (abs(plateau['start_s'] - a['time_s']) <= EVENT_TOLERANCE_S
                    and abs(plateau['end_s'] - d['time_s']) <= EVENT_TOLERANCE_S
                    and lower <= plateau['distance_reference_m'] <= upper):
                matches.append((a, d, plateau))
    _need(len(matches) == 1, 'Selected repeated occurrence lacks one exact original timetable and distance stop')
    arrival, departure, plateau = matches[0]
    a, d = arrival['time_s'], departure['time_s']
    instants = [absolute_message_clock(clock, a, d) if isinstance(clock, str) else clock for clock in clocks]
    _need(all(a - EVENT_TOLERANCE_S <= instant <= d + EVENT_TOLERANCE_S for instant in instants),
          'Original composition event occurred outside the selected repeated stop')
    return {'main_visit_index': occurrence['index'], 'previous_station_visits': occurrence['previous_visits'],
            'same_station_visit_indices': occurrence['same_station_visit_indices'], 'station': station,
            'planned_distance_m': occurrence['distance_m'], 'arrival': arrival, 'departure': departure,
            'expected_stopping_edge_interval_m': [lower, upper],
            'native_stopped_position_m': plateau['distance_reference_m'], 'native_event_times_s': instants,
            'verified': True}


def assess_compositions(events, verified_courses, messages, native_debug='', native_traction=None,
                        native_occurrences=None):
    """Keep measured native body values separate from archive-derived consist accounting."""
    records = []
    for line in messages.splitlines():
        cols = line.split('\t')
        if len(cols) >= 5 and MESSAGE_CLOCK.fullmatch(cols[1].strip()):
            records.append(tuple(x.strip() for x in cols[:5]))
    debug_rows = {}
    for course, phase, value in RAW_LENGTH.findall(native_debug):
        debug_rows.setdefault((course, phase), []).append(float(value))
    counters = Counter((item['main_course'], 'nach ' + item['kind']) for item in events)
    counters.update((item['main_course'], 'vor split') for item in events if item['kind'] == 'split')
    consumed = Counter()

    def lengths(course, phase):
        key = course, phase
        values = debug_rows.get(key, [])
        if not values or counters[key] <= 1:
            return values
        _need(len(values) == counters[key], 'Native length samples cannot be bound to the repeated composition events')
        position = consumed[key]
        consumed[key] += 1
        return [values[position]]

    results = []
    previous = {}
    for event in events:
        kind, main, other = event['kind'], event['main_course'], event['other_course']
        station = event['station_sign']
        participants = [verified_courses[cid] for cid in (main, other)]
        _need(all(item['completion_verified'] for item in participants), 'Both linked Courses must complete in the original run')
        token = f'Trains {"splitted" if kind == "split" else "joined"} at {station}'
        actors = {other} if kind == 'split' else {main, other}
        confirmations = [row for row in records
                         if row[0] == 'NORMAL' and row[2] in actors and row[3].endswith(token)
                         and row[4] == f'({station})']
        _need(bool(confirmations), 'Original native composition event is missing')
        failures = [row for row in records if row[2] in (main, other) and FAILURE.search(row[3])]
        _need(not failures, 'Original reported a composition, route, engine, or physical-coupling failure')
        clocks = [row[1] for row in confirmations]
        occurrence = (native_occurrences or {}).get((main, other))
        selected_stop = (verify_occurrence(occurrence['raw_course'], occurrence, clocks)
                         if occurrence is not None else None)
        _need(selected_stop is not None or not any(row['time_s'] >= 86400 for item in participants for row in item['events']),
              'Cross-day composition needs a frozen, position-verified native stop')
        instants = (selected_stop['native_event_times_s'] if selected_stop else
                    [absolute_message_clock(clock, 0, 86399, tolerance=0) for clock in clocks])
        instant, clock = min(zip(instants, clocks))
        projected = event['projected_main_length_m']
        static_initial = event['initial_main']['length_m']
        if main in previous:
            prior_instant, prior_length = previous[main]
            _need(prior_instant < instant and prior_length == static_initial,
                  'Original events or archive composition are out of order for the repeated main Course')
        previous[main] = instant, projected
        for item in participants:
            _need(item['events'] and max(row['time_s'] for row in item['events']) >= instant,
                  'Original composition event follows a participant terminal outcome')
        if event.get('planned_departure_order') == 'main_then_child':
            child_departure = participants[1]['origin_event']['time_s']
            prior = [r['time_s'] for r in participants[0]['events']
                     if r['kind'] == 'Dep.' and instant <= r['time_s'] < child_departure]
            _need(prior, 'Original main did not depart before the split child')
        outgoing = lengths(main, 'nach ' + kind)
        incoming = lengths(main, 'vor split') if kind == 'split' else []
        _need(not outgoing or all(abs(x - projected) <= 0.05 for x in outgoing), 'Measured outgoing train length disagrees')
        _need(not incoming or all(abs(x - static_initial) <= 0.05 for x in incoming), 'Measured starting train length disagrees')
        motion = None if native_traction is None else native_traction.get(main)
        results.append({
            'kind': kind, 'main_course': main, 'other_course': other, 'station_sign': station,
            'event_clock': clock, 'event_time_s': instant, 'event_day_offset': instant // 86400,
            'event_log_rows': [r[3] for r in confirmations],
            'both_original_courses_completed': True,
            'archive_initial_main_length_m': static_initial,
            'archive_secondary_length_m': event['initial_other']['length_m'],
            'projected_main_length_m': projected,
            'native_measured_before_m': incoming or None,
            'native_measured_after_m': outgoing or None,
            'native_repeated_occurrence': selected_stop if occurrence and len(occurrence['same_station_visit_indices']) > 1 else None,
            'native_day_bound_occurrence': selected_stop if occurrence and occurrence.get('later_day') else None,
            'native_traction_comparison': matching_departure_traction(event, participants[0], instant, motion)
            if motion is not None else None,
        })
    _need(bool(results), 'Expected original composition events')
    return results


def bound_occurrences(loaded, events, inputs, verified_courses, output, process, evaluation):
    from opentrack_ai.current_archive import catalogs, course_factories, native_connections, writer
    from opentrack_ai.current_archive import native_evaluation_formats as fmt
    from opentrack_ai.current_archive.native_run_evaluation import decode, read_member
    from opentrack_ai.current_archive.operating_plan_edit import timetable_time

    services = {item['course_id']: item['visits'] for item in loaded.get('services', [])}
    indexed = []
    for event in events:
        main, other, sign = event['main_course'], event['other_course'], event['station_sign']
        visits = services.get(main, [])
        indices = [index for index, visit in enumerate(visits) if visit['station_sign'] == sign]
        later_day = any(row['time_s'] >= 86400 for cid in (main, other) for row in verified_courses[cid]['events'])
        if len(indices) > 1 or later_day:
            index = event.get('main_visit_index')
            _need(index in indices and event['main_row'] == f'{main}#{index}'
                  and event['main_previous_station_visits'] == indices.index(index),
                  'Published repeated or cross-day composition must identify an exact local native timetable row')
            indexed.append((event, (main, other), indices, index, later_day))
    if not indexed:
        return {}

    def bound_member(member):
        data = read_member(inputs, member, nested=True)
        _need(_digest(data) == loaded['files'][member]['sha256'], f'Frozen original member differs from build: {member}')
        return data

    for member in loaded['files']:
        if member.endswith('.opentrack'):
            bound_member(member)
    timetable, = [name for name in loaded['files'] if name.endswith('.timetable')]
    stations, = [name for name in loaded['files'] if name.endswith('.stations')]
    table = course_factories.timetable(writer.load_next_compatible(bound_member(timetable))[0])
    station_catalog = catalogs.station_items(writer.load_next_compatible(bound_member(stations))[0])
    requirements = {}
    native_courses = {}

    def native_text(course, extension):
        filename = f'OT_{course}.{extension}'
        data = read_member(output, filename)
        _need(_digest(data) == process['output_sha256'][filename] == evaluation['output_sha256'][filename],
              f'Original sealed occurrence output differs: {filename}')
        return decode(data)

    for event, (main, other), indices, index, later_day in indexed:
        sign = event['station_sign']
        keys = [f'{main}#{i}' for i in indices]
        bound_rows = []
        for key in keys:
            row = table[key]
            _need(catalogs.text(row.contents[5].value) == sign, 'Frozen timetable station differs at repeated occurrence')
            for connection in catalogs.array(row.contents[9].value):
                record = native_connections.record(connection)
                if record['target_course_id'] == other:
                    bound_rows.append((key, record['flags'], record['station_sign'], record['target_station_sign']))
        _need(bound_rows == [(event['main_row'], 1 if event['kind'] == 'join' else 2, sign, sign)],
              'Frozen original timetable does not bind the counterpart exclusively to the selected occurrence')
        partner = table[event['other_row']]
        counterpart = [native_connections.record(obj) for obj in catalogs.array(partner.contents[9].value)]
        _need(len(counterpart) == 1 and counterpart[0]['course_id'] == other
              and counterpart[0]['target_course_id'] == main and counterpart[0]['flags'] == int(event['kind'] == 'join')
              and counterpart[0]['station_sign'] == counterpart[0]['target_station_sign'] == sign,
              'Frozen original timetable does not bind the reciprocal composition row')
        row = table[event['main_row']]
        planned = services[main][index]['planned']
        _need(timetable_time(row, 'arrival') == planned['arrival_s']
              and timetable_time(row, 'departure') == planned['departure_s'],
              'Frozen absolute timetable clocks differ from the planned composition stop')
        _need(verified_courses[main]['completion_verified'], 'Original repeated Course did not complete')
        if main not in native_courses:
            distance = fmt.series(native_text(main, 'st1'), 'st1', main)
            speed = fmt.series(native_text(main, 'vt'), 'vt', main)
            factor = {'km': 1000, 'mi': 1609.344}[distance['units'][1]]
            native_courses[main] = {
                'events': fmt.timetable(native_text(main, 'tt'), main),
                'distance': fmt.series_summary(distance),
                'stationary_intervals': fmt.stationary_intervals(
                    speed['points'], [(instant, value * factor) for instant, value in distance['points']]),
            }
        requirements[main, other] = {
            **services[main][index], 'index': index, 'previous_visits': indices.index(index),
            'same_station_visit_indices': indices, 'station': catalogs.text(station_catalog[sign].contents[2].value),
            'raw_course': native_courses[main], 'later_day': later_day,
        }
    return requirements


def verify_projected_transfers(build, evaluation, output, evidence, events):
    from opentrack_ai.current_archive import catalogs, course_factories, native_connections, native_evaluation_formats as fmt, writer
    from opentrack_ai.current_archive.native_circulation import lifecycle_messages, transition_motion
    from opentrack_ai.current_archive.native_interlocking import FrozenRailwayRun, metres_trace
    from opentrack_ai.current_archive.network_operating_plan import route_trace
    from opentrack_ai.current_archive.operating_plan_edit import text
    from opentrack_ai.current_archive.shunting_workflow.core import vehicles

    outcomes = []
    prior = {state['course_id']: state for state in evaluation['courses']}
    for cid, state in prior.items():
        terminal = state['last_observed_event']
        outcome = {'course_id': cid, 'origin_station': state['origin_event']['station'],
                   'terminal_station': terminal['station'], 'terminal_event': terminal['kind']}
        if state['expected_distance_m'] is not None:
            outcome.update(distance_m=state['expected_distance_m'], distance_tolerance_m=state['distance_tolerance_m'])
        outcomes.append(outcome)
    run = FrozenRailwayRun(output, evidence, outcomes, secure_bytes=None)

    def catalog(role):
        return writer.load_next_compatible(run.dependency(run.settings['paths'][role]))[0]

    timetable = course_factories.timetable(catalog('TimetableFile'))
    trains = {text(item, 0): item for item in catalogs.train_items(catalog('TrainFile'))}
    depot = {text(item, 1): item for item in catalogs.engine_items(catalog('DepotFile'))}
    course_stock = {text(item, 0): text(item, 3) for item in catalogs.course_items(catalog('CourseFile'))}

    def identity(component):
        key = component['name'] if component['kind'] == 'engine' else component['signature_sha256']
        return component['kind'], key

    messages = lifecycle_messages(run.original_text('OT_Messages.txt'), list(prior))
    details = []
    for transfer in build['projected_formation_transfers']:
        first, second = transfer['from_course'], transfer['to_course']
        old_route, = run.preferences[first]
        new_route, = run.preferences[second]
        old_visits = route_trace(run.project, run.itineraries[old_route])['visits']
        new_trace = route_trace(run.project, run.itineraries[new_route])
        origin = new_trace['visits'][0]
        terminal = old_visits[-1]
        sign = terminal['station_sign']
        reverse = transfer['movement'] == 'reverse'
        required_end = run.project.related(terminal['end_key']) if reverse else terminal['end_key']
        _need(required_end == origin['end_key'] and sign == origin['station_sign']
              and (not reverse or terminal['stop_edge_key'] == new_trace['edges'][0]),
              'Projected formations need the exact same directed End or a paired reversal over the same stopping Edge')
        _need(course_stock[first] == transfer['from_declared_train'] and course_stock[second] == transfer['to_declared_train'],
              'Frozen Course stock differs from the projected transfer declarations')
        declared = vehicles(trains[course_stock[second]], depot)
        _need([identity(row[3]) for row in declared] == [identity(row) for row in transfer['formation']],
              'Frozen native successor stock differs from the projected ordered formation')
        engines = [row[3]['name'] for row in declared if row[1] == 'engine']
        first_row = f'{first}#{len(old_visits)-1}'
        second_row = f'{second}#0'
        assertions = [(first_row, first, second, 2), (second_row, second, first, 0)]
        ports = {}
        for key, cid, target, flag in assertions:
            connection, = catalogs.array(timetable[key].contents[9].value)
            record = native_connections.record(connection)
            _need(record['course_id'] == cid and record['target_course_id'] == target and record['flags'] == flag
                  and record['station_sign'] == record['target_station_sign'] == sign,
                  'Frozen reciprocal current Connection6 differs from projected circulation')
            ports[key] = record
        wait = course_factories.clock(ports[first_row]['minimum_wait'])
        _need(wait == course_factories.clock(ports[second_row]['minimum_wait']) and wait >= 0,
              'Expected the same explicit minimum wait for both transfer ends')
        successor_speed = fmt.series(run.original_text(f'OT_{second}.vt'), 'vt', second)
        successor_position = metres_trace(run.original_text(f'OT_{second}.st1'), 'st1', second, new_route)
        successor = {'course_id': second, 'origin': prior[second]['origin_event'],
                     'speed': successor_speed['points'], 'position': successor_position}
        motion = transition_motion({'terminal': prior[first]['last_observed_event']}, successor,
                                   messages, sign, wait, EVENT_TOLERANCE_S, True)
        _need(motion['verified'], 'Original arrival, activation, stationary hold or restart differs from the projected transfer')
        initial = max(event['time_s'] for event in prior[first]['events'] if event['kind'] == 'Dep.')
        restart = successor['origin']['time_s']
        traction_names = f'OT_{first}.tsvP', f'OT_{second}.tsvP'
        common, ratios, force_pairs = [], [], []
        if not reverse or all(name in run.hashes for name in traction_names):
            before = traction_samples(traction_rows(run.original_text(traction_names[0])), initial, initial + 6)
            after = traction_samples(traction_rows(run.original_text(traction_names[1])), restart, restart + 6)
            common = sorted(before.keys() & after.keys())
            force_pairs = [{'speed_kmh': speed, 'preceding_tractive_effort_kn': before[speed][1],
                            'successor_tractive_effort_kn': after[speed][1]} for speed in common]
            ratios = [round(after[speed][1] / before[speed][1], 6) for speed in common]
        _need(reverse or (len(ratios) >= 3 and all(abs(ratio - 1) <= .01 for ratio in ratios)),
              'Original tractive effort does not substantiate retained stock across same-direction transfer')
        outgoing_events = [item for item in events if item['main_course'] == first]
        later_events = [item for item in events if item['main_course'] == second]
        _need(outgoing_events and outgoing_events[-1]['event_time_s'] < initial < motion['successor_activation_s']
              and all(restart < item['event_time_s'] for item in later_events),
              'Verified original composition events do not surround the continuation in order')
        details.append({**transfer, 'station_sign': sign, 'reference_end': terminal['end_key'],
                        'departure_end': origin['end_key'], 'initial_departure_edge': new_trace['edges'][0],
                        'frozen_successor_engine_array_order': engines, 'native_connections': ports,
                        'native_motion': motion, 'matched_traction_speed_kmh': common, 'after_to_before_force_ratios': ratios,
                        'matched_native_tractive_effort': force_pairs,
                        'original_output_sha256': dict(run.files.hashes)})
    return details


def verify(build, native_run, *, expectations=None):
    loaded = json.loads(build.read_bytes())
    if 'ok' in loaded:
        _need(loaded['ok'] is True, 'Build receipt records a failed native generation')
        loaded = loaded['result']
    groups = loaded.get('composition_events') or loaded.get('connections')
    _need(loaded.get('saved') is True and isinstance(groups, dict), 'A published native composition build is required')
    evidence = native_run / 'evidence'
    before = json.loads((evidence / 'before.json').read_bytes())
    process = json.loads((evidence / 'process.json').read_bytes())
    output = Path(process['output_directory']).resolve()
    _need(output.is_relative_to(native_run.resolve()), 'Original output is outside the verified run directory')
    if expectations is None:
        run = json.loads((evidence / 'evaluation.json').read_bytes())
    else:
        from opentrack_ai.current_archive.native_run_evaluation import evaluate_run

        run = evaluate_run(output, expectations, {**before, **process, 'evidence_directory': evidence})
    _need(before['executable_sha256'] == STOCK_EXE_SHA and process['exit_code'] == 0 and run['native_run_verified'],
          'Original run does not have successful verified engine evidence')
    for extension in ('.courses', '.timetable', '.trains', '.depot'):
        member, = [name for name in loaded['files'] if name.endswith(extension)]
        expected = loaded['files'][member]['sha256']
        _need(before['input_sha256'][member] == expected and _digest((evidence / 'inputs' / member).read_bytes()) == expected,
              f'Original run did not receive the published {extension} archive')
    msg = (output / 'OT_Messages.txt').read_bytes()
    _need(_digest(msg) == run['output_sha256']['OT_Messages.txt'], 'Original protocol message file changed since evaluation')
    debug = '\n'.join((evidence / name).read_bytes().decode('latin-1') for name in ('stdout.txt', 'stderr.txt'))
    traction = {}
    traction_hashes = {}
    started = datetime.fromisoformat(before['started_utc']).timestamp()
    for event in groups['events']:
        cid = event['main_course']
        _need(re.fullmatch(r'[\x20-\x7E]+', cid) and not any(x in cid for x in '/\\:'), 'Invalid native output Course identity')
        filename = f'OT_{cid}.tsvP'
        path = output / filename
        if filename in process['output_files'] and path.stat().st_mtime >= started - 2:
            raw = path.read_bytes()
            checksum = _digest(raw)
            _need(run['output_sha256'].get(filename, checksum) == checksum,
                  'Native traction output changed since evaluation')
            _need(process.get('output_sha256', {}).get(filename, checksum) == checksum,
                  'Native traction output differs from original launch hashes')
            traction[cid] = raw.decode('latin-1')
            traction_hashes[filename] = checksum
    verified_courses = {item['course_id']: item for item in run['courses']}
    occurrence_specs = bound_occurrences(loaded, groups['events'], evidence / 'inputs', verified_courses,
                                         output, process, run)
    if occurrence_specs:
        _need(_digest(msg) == process['output_sha256']['OT_Messages.txt'],
              'Original composition messages differ from original launch hashes')
    results = assess_compositions(groups['events'], verified_courses, msg.decode('latin-1'), debug, traction,
                                  occurrence_specs)
    transfers = verify_projected_transfers(loaded, run, output, {**before, **process, 'evidence_directory': evidence},
                                           results) if loaded.get('projected_formation_transfers') else []
    return {
        'native_composition_events_verified': True,
        'events': results,
        'native_projected_formation_transfers': transfers,
        'message_sha256': _digest(msg),
        'traction_output_sha256': traction_hashes,
        'native_repeated_occurrence_count': sum(len(item['same_station_visit_indices']) > 1
                                                for item in occurrence_specs.values()),
        'native_day_bound_occurrence_count': sum(item['later_day'] for item in occurrence_specs.values()),
        'separate_length_measurements_required_where_absent': any(item['native_measured_after_m'] is None for item in results),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--native-run', type=Path, required=True)
    parser.add_argument('--expectations', type=Path, help='Re-evaluate original outputs with the explicit Course expectations')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend' / 'OTAI'))
    expectations = None if args.expectations is None else json.loads(args.expectations.read_bytes())
    payload = json.dumps(verify(args.build, args.native_run, expectations=expectations),
                         indent=2, ensure_ascii=False) + '\n'
    if args.report is not None:
        with args.report.open('x', encoding='utf-8') as output:
            output.write(payload)
    print(payload, end='')

