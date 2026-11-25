"""Verify a linear continuous stock circulation against a sealed original OpenTrack run."""

from . import catalogs, course_factories, native_connections, native_evaluation_formats as fmt, writer
from .catalog_batch_reuse.course_batch import course_record
from .native_interlocking import CLOCK_TOLERANCE, FrozenRailwayRun, metres_trace
from .native_run_evaluation import basename
from .network_operating_plan import route_trace
from .operating_plan_edit import text, timetable_time
from .stock_operations import CATEGORY_LAYOUT


def transfer_days(planned_arrival, planned_departure, actual_arrival, actual_departure):
    planned = [planned_arrival // 86400, planned_departure // 86400]
    actual = [actual_arrival // 86400, actual_departure // 86400]
    return {'planned_day_offsets': planned, 'actual_day_offsets': actual,
            'planned_crosses_midnight': planned[0] < planned[1], 'crosses_midnight': actual[0] < actual[1]}


def transition_motion(previous, successor, events, station, minimum, tolerance, linked):
    arrival, departure = previous['terminal'], successor['origin']
    speed, position = successor['speed'], successor['position']
    activation = speed[0][0]
    departure_time = departure['time_s']
    start = departure_time if not linked else arrival['time_s']
    messages = [row for row in events if row['course_id'] == successor['course_id'] and row['station'] == station]
    ready = [row for row in messages if row['kind'] == 'ready']
    splits = [row for row in messages if row['kind'] == 'activation']
    hold = None
    if linked:
        candidates = [row for row in fmt.stationary_intervals(speed, position)
                      if abs(row['start_s'] - activation) <= CLOCK_TOLERANCE
                      and abs(row['end_s'] - departure_time) <= tolerance
                      and row['duration_s'] + tolerance >= minimum
                      and abs(row['distance_reference_m'] - position[0][1]) <= 0.17]
        if len(candidates) == 1:
            hold, = candidates
    # Stock messages print the time of day even when the timetable includes a day prefix.
    # The original absolute trajectory clock above independently binds the event to its day.
    day, within_day = divmod(start, 86400)
    clock = f'{within_day // 3600:02}:{within_day // 60 % 60:02}:{within_day % 60:02}'
    expected_clocks = {clock, f'{day} / {clock}'}
    checks = {
        'activation_matches_native_clock': abs(activation - start) <= tolerance
        and abs(activation - position[0][0]) <= CLOCK_TOLERANCE,
        'mode_matches_native_messages': len(ready) == 1 and ready[0]['clock'] in expected_clocks
        and (len(splits) == 1 and splits[0]['clock'] in expected_clocks if linked else not splits),
        'stationary_before_next_departure': hold is not None if linked else abs(activation - departure_time) <= tolerance,
        'next_course_starts_moving_after_departure': speed[0][1] == 0 and any(
            t >= departure_time - CLOCK_TOLERANCE and v > 0 for t, v in speed),
    }
    return {'verified': all(checks.values()), 'checks': checks, 'predecessor_actual_terminal': arrival,
            'successor_activation_s': activation, 'successor_stationary_interval': hold,
            'successor_actual_departure': departure, 'original_activation_messages': splits, 'original_ready_messages': ready}


def occupation_transition(cycles, current, following, movement, mode, motion, tolerance):
    first = [cycle for cycle in cycles if cycle['course_id'] == current]
    second = [cycle for cycle in cycles if cycle['course_id'] == following]
    fmt.require(len(first) == len(second) == 1, 'Select a monitor with exactly one cycle for each adjoining Course')
    old, = first
    new, = second
    for cycle in (old, new):
        reserve, release = cycle['reservation_s']
        enter, clear = cycle['occupation_s']
        fmt.require(None not in (reserve, release, enter, clear) and reserve <= enter < clear <= release,
                    'Native circulation requires complete positive-duration platform occupation cycles')
    old_clear, old_release = old['occupation_s'][1], old['reservation_s'][1]
    new_reserve, new_enter = new['reservation_s'][0], new['occupation_s'][0]
    departure = motion['successor_actual_departure']['time_s']
    arrival = motion['predecessor_actual_terminal']['time_s']
    if movement == 'continue' and mode == 'linked':
        simultaneous = max(old_clear, old_release, new_reserve, new_enter) - min(
            old_clear, old_release, new_reserve, new_enter) <= CLOCK_TOLERANCE
        consistent = simultaneous and abs(new_enter - motion['successor_activation_s']) <= tolerance
        consistent = consistent and new['occupation_s'][1] >= departure
    else:
        simultaneous = False
        consistent = old_clear <= old_release <= new_reserve <= new_enter and abs(new_reserve - departure) <= tolerance
    return {'verified': consistent and old_clear >= arrival - tolerance, 'continuous_monitored_handover': simultaneous,
            'predecessor': old, 'successor': new}


def lifecycle_messages(source, courses):
    fmt.headers(source, 'OT_messages')
    selected = []
    for row in fmt.data_rows(source):
        if len(row) != 5 or row[2] not in courses:
            continue
        level, clock, cid, message, location = row
        if level.strip().upper() != 'NORMAL' or not location.startswith('(') or not location.endswith(')'):
            continue
        station = location[1:-1]
        kind = {f'Course {cid}: Trains splitted at {station}': 'activation',
                f'Course {cid}: Ready for Simulation': 'ready'}.get(message.strip())
        if kind is not None:
            selected.append({'kind': kind, 'clock': clock, 'course_id': cid, 'station': station, 'message': message.strip()})
    return selected


def native_ports(timetable, course, length, expected):
    rows = sorted((row for row in timetable.values() if text(row, 1) == course), key=lambda row: row.contents[3].value)
    fmt.require(len(rows) == length and [row.contents[3].value for row in rows] == list(range(length)),
                f'Frozen timetable rows are incomplete for {course}')
    report = {}
    for index, row in enumerate(rows):
        links = [native_connections.record(value) for value in catalogs.array(row.contents[9].value)]
        station = text(row, 5)
        wanted = expected.get(index)
        if wanted is None:
            fmt.require(not links, f'Unexpected circulation connection on {course}#{index}')
            continue
        arrival_side, target, minimum = wanted
        fmt.require(len(links) == 1, f'An exact reciprocal circulation record is required at {course}#{index}')
        connection, = links
        fmt.require(connection['course_id'] == course and connection['target_course_id'] == target
                    and connection['station_sign'] == connection['target_station_sign'] == station
                    and connection['flags'] == (2 if arrival_side else 0)
                    and connection['time_reference_type'] == 0 and connection['dispatching_distance_km'] == 0
                    and connection['maximum_wait'] == ('HH:MM:SS' if arrival_side else None)
                    and connection['minimum_wait'] == native_connections.wait(minimum),
                    f'Frozen Connection6 differs from the declared linked sequence at {course}#{index}')
        report[f'{course}#{index}'] = connection
    return rows, report


def audit(output, evidence, request, secure_bytes=None):
    outcomes = request['courses']
    mode = request['mode']
    links = request['connections']
    course_ids = [basename(row['course_id']) for row in outcomes]
    fmt.require(len(course_ids) == len(set(course_ids)) and len(links) + 1 == len(course_ids),
                'Specify distinct Courses in circulation order and one movement between each pair')
    bound = FrozenRailwayRun(output, evidence, outcomes, secure_bytes)
    fmt.require(all(len(choices) == 1 for choices in bound.preferences.values()),
                'Circulation verification requires one saved Itinerary per Course')

    def catalog(key):
        return writer.load_next_compatible(bound.dependency(bound.settings['paths'][key]))[0]

    actual_courses = {row['course_id']: row for row in map(course_record, catalogs.course_items(catalog('CourseFile')))}
    train_ids = {actual_courses[cid]['train'] for cid in course_ids}
    fmt.require(len(train_ids) == 1, 'All Courses must use the same saved native Train identity')
    train, = train_ids
    trains = catalog('TrainFile')
    matched = [row for row in catalogs.train_items(trains) if text(row, 0) == train]
    stock, = matched
    categories = [catalogs.shape(row, 'OTTrainCategory', 19, CATEGORY_LAYOUT)
                  for row in catalogs.array(trains.contents[1].value) if text(row, 1) == text(stock, 3)]
    category, = categories
    minimum = fmt.number(category.contents[20].value)
    fmt.require(0 <= minimum < 86400, 'A finite nonnegative current Category minimum is required')
    timetable = course_factories.timetable(catalog('TimetableFile'))
    receipts = {row['course_id']: row for row in bound.receipt['courses']}
    events = lifecycle_messages(bound.original_text('OT_Messages.txt'), course_ids)
    prepared = []
    for index, (cid, outcome) in enumerate(zip(course_ids, outcomes)):
        itinerary, = bound.preferences[cid]
        route = route_trace(bound.project, bound.itineraries[itinerary])
        stops = route['visits']
        last = len(stops) - 1
        expected = {}
        if mode == 'linked' and index > 0:
            expected[0] = (False, course_ids[index - 1], minimum)
        if mode == 'linked' and index < len(course_ids) - 1:
            expected[last] = (True, course_ids[index + 1], minimum)
        rows, ports = native_ports(timetable, cid, len(stops), expected)
        fmt.require([text(row, 5) for row in rows] == [location['station_sign'] for location in stops],
                    f'Timetable station order differs from the frozen movement for {cid}')
        prefix = f'OT_{cid}'
        speed = fmt.series(bound.original_text(prefix + '.vt'), 'vt', cid)
        positions = metres_trace(bound.original_text(prefix + '.st1'), 'st1', cid, itinerary)
        factor = {'km/h': 1, 'mph': 1.609344}[speed['units'][1]]
        tolerance = outcome['event_tolerance_s']
        fmt.require(abs(positions[-1][1] - positions[0][1] - route['route_length_m'])
                    <= outcome.get('distance_tolerance_m', 1.75),
                    f'Original movement did not reach the frozen directed terminal for {cid}')
        receipt = receipts[cid]
        departure_s = timetable_time(rows[0], 'departure')
        arrival_s = timetable_time(rows[-1], 'arrival')
        fmt.require(departure_s is not None and arrival_s is not None
                    and receipt['origin_event'].get('planned_s') == departure_s
                    and receipt['last_observed_event'].get('planned_s') == arrival_s,
                    f'Original timetable endpoint clocks differ from frozen clocks and day offsets for {cid}')
        prepared.append({'course_id': cid, 'itinerary': itinerary, 'ports': ports,
                         'departure_s': departure_s, 'arrival_s': arrival_s,
                         'origin': receipt['origin_event'], 'terminal': receipt['last_observed_event'], 'position': positions,
                         'actual_distance_m': receipt['displacement_m'],
                         'terminal_stop': bool(rows[-1].contents[10].value & 1),
                         'clock_tolerance_s': tolerance, 'speed': [(t, v * factor) for t, v in speed['points']], **route})

    transfers = []
    for first, second, connection in zip(prepared, prepared[1:], links):
        a, b = first['visits'][-1], second['visits'][0]
        movement = connection['movement']
        expected_end = a['end_key'] if movement == 'continue' else bound.project.related(a['end_key'])
        fmt.require(first['terminal_stop'] and expected_end == b['end_key'] and a['station_sign'] == b['station_sign']
                    and first['arrival_s'] is not None and second['departure_s'] is not None
                    and 0 < second['departure_s'] - first['arrival_s'] >= minimum,
                    'Native route terminals, planned gap or directional successor do not make the declared transfer')
        resource, cycles = bound.resource(connection['resource'])
        monitored = {(resource['document'], edge) for edge in resource['edge_ids']}
        fmt.require(a['stop_edge_key'] in monitored and (movement != 'reverse' or second['edges'][0] in monitored),
                    'Native monitor must contain the actual stopping Edge and the returning Edge for a reversal')
        tolerance = min(first['clock_tolerance_s'], second['clock_tolerance_s'])
        motion = transition_motion(first, second, events, a['station_sign'], minimum, tolerance, mode == 'linked')
        occupation = occupation_transition(cycles, first['course_id'], second['course_id'], movement, mode, motion, tolerance)
        days = transfer_days(first['arrival_s'], second['departure_s'], first['terminal']['time_s'], second['origin']['time_s'])
        expected_midnight = connection.get('crosses_midnight')
        matched_midnight = expected_midnight is None or expected_midnight == days['crosses_midnight']
        transfers.append({'verified': motion['verified'] and occupation['verified'] and matched_midnight, 'movement': movement,
                          'predecessor': first['course_id'], 'successor': second['course_id'], 'station_sign': a['station_sign'],
                          'arrival_end': a['end_key'], 'departure_end': b['end_key'], 'monitor': resource,
                          'minimum_wait_s': minimum, 'planned_gap_s': second['departure_s'] - first['arrival_s'],
                          'expected_midnight_matched': matched_midnight, **days, 'motion': motion, 'occupation': occupation})
    return {'verified': all(transfer['verified'] for transfer in transfers), 'mode': mode, 'train': train,
            'train_category': text(category, 1), 'transfers': transfers,
            'courses': [{key: item[key] for key in ('course_id', 'itinerary', 'route_length_m', 'actual_distance_m',
                                                  'origin', 'terminal', 'ports')} for item in prepared],
            'provenance': bound.provenance, 'original_output_sha256': {**bound.receipt['output_sha256'], **bound.files.hashes}}
