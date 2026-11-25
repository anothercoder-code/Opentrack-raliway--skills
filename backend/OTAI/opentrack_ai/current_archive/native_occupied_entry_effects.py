"""Compare original permission and denial of a speed-limited entry for a planned join."""

from typing import Annotated

from pydantic import Field

from ..errors import APIError
from . import native_evaluation_formats as fmt, writer
from .native_edge_exclusion_effects import frozen_inputs
from .native_headway_tools import Run, SpacingCourse
from .native_incident_effects import printed_clock
from .native_interlocking import CLOCK_TOLERANCE, FrozenRailwayRun, metres_trace
from .native_result_tools import EvaluateNativeRunTools, Name
from .native_run_evaluation import basename, read_receipts, signal_position
from .native_signal_stop_effect import frozen_signal, itinerary_output
from .native_station_throughput import configured_window
from .network_composition_plan import _arrival_route, _entry_signal, _route_name
from .network_operating_plan import route_trace
from .shunting_workflow.core import plan_connections
from .tools import Input


class CompareNativeOccupiedEntry(Input):
    permitted: Run
    denied: Run
    receiver: SpacingCourse
    donor: SpacingCourse
    station_sign: Name
    contact_tolerance_m: Annotated[float, Field(ge=.17, le=2, allow_inf_nan=False)] = .3


def static_join(run, receiver, donor, station):
    roles = {'timetable': 'Timetable', 'courses': 'Course', 'trains': 'Train', 'stations': 'Station', 'depot': 'Depot'}
    banks = {role: run.dependency(run.settings['paths'][key + 'File']) for role, key in roles.items()}
    request = {'schema': 'split-join-timetable-plan/1', 'accept_unverified_spatial_and_dynamic_execution': True,
               'operations': [{'kind': 'join', 'main_course': receiver, 'other_course': donor, 'station_sign': station}]}
    _, checked = plan_connections(banks, request, verify_existing=True, sequential_main=True)
    event, = checked['events']
    project = run.project
    labels = {}
    visits = {}
    for course in (receiver, donor):
        fmt.require(len(run.preferences[course]) == 1, 'Select Courses with one directed frozen Itinerary each')
        labels[course], = run.preferences[course]
        trace = route_trace(project, run.itineraries[labels[course]])
        matches = [item for item in trace['visits'] if item['station_sign'] == station]
        fmt.require(len(matches) == 1, 'Select one unambiguous platform occurrence in each frozen Itinerary')
        visits[course], = matches
        if course == donor:
            fmt.require(matches[0] == trace['visits'][-1], 'Supply Course must terminate at the selected platform')
    main, other = visits[receiver], visits[donor]
    fmt.require(main['end_key'] == other['end_key'] and main['stop_edge_key'] == other['stop_edge_key']
                and main['stop_edge_length_m'] >= event['projected_main_length_m'],
                'Both Courses must use the same directed platform and fit on its stopping Edge')
    arrival = _arrival_route(project, run.itineraries[labels[donor]], other['end_key'])
    flags, speed, wait = arrival.contents[6].values
    fmt.require(flags == 3 and speed > 0, 'Select an ordinary speed-limited occupied-entry Route')
    document, signal = _entry_signal(project, arrival)
    identity = {'document': document, 'model_id': signal.contents[0].value}
    return {'event': event, 'visits': visits, 'itineraries': labels, 'route': _route_name(arrival),
            'saved_speed_kmh': speed, 'saved_wait_s': wait, 'signal_identity': identity}


def check_signal_difference(permitted, denied, permitted_evidence, denied_evidence, signal):
    before = frozen_inputs(denied, denied_evidence)
    after = frozen_inputs(permitted, permitted_evidence)
    fmt.require(before['common'] == after['common'] and before['sheets'].keys() == after['sheets'].keys(),
                'Original control and treatment must agree on options, destination graph and non-worksheet inputs')
    fmt.require(all(denied.receipt['protocol'][key] == permitted.receipt['protocol'][key]
                    for key in ('used_courses', 'listed_incidents')),
                'Original protocols disagree on same-run Courses or Incidents')
    document, mid = signal['document'], signal['model_id']
    changed = [name for name in before['sheets'] if before['sheets'][name] != after['sheets'][name]]
    fmt.require(changed == [document], 'Only the selected entrance signal worksheet may differ in the original runs')
    control = denied.project.model((document, mid))
    treatment = permitted.project.model((document, mid))
    old = control.contents[9].values[2]
    new = treatment.contents[9].values[2]
    fmt.require(new == old | 1 and old != new, 'Original comparison must enable only the entrance occupied-entry bit')
    try:
        control.contents[9].values[2] = new
        fmt.require(writer.fingerprint(denied.project.roots[document]) == writer.fingerprint(permitted.project.roots[document]),
                    'The original signal permission was accompanied by other worksheet edits')
    finally:
        control.contents[9].values[2] = old
    return {'document': document, 'signal_model_id': mid, 'denied_flags': old, 'permitted_flags': new}


def traces(run, course, itinerary):
    files = {key: itinerary_output(run.original_text(f'OT_{basename(course)}.{key}'), itinerary, key)
             for key in ('st1', 'vt')}
    distance = metres_trace(files['st1'], 'st1', course, itinerary)
    native_speed = fmt.series(files['vt'], 'vt', course)
    scale = 1 if native_speed['units'][1] == 'km/h' else 1.609344
    speed = [(clock, value * scale) for clock, value in native_speed['points']]
    fmt.require(len(speed) >= 2 and all(a[1] <= b[1] for a, b in zip(distance, distance[1:]))
                and speed[-1][1] == 0 and abs(speed[-1][0] - distance[-1][0]) <= CLOCK_TOLERANCE,
                'Original course needs a full forward distance and terminal zero-speed observation')
    return {'distance': distance, 'speed': speed, 'origin_m': distance[0][1],
            'rounded_speed_tolerance_kmh': .050001 * scale}


def outbound_authorities(run, course, itinerary, signal, position):
    raw = lambda extension: itinerary_output(run.original_text(f'OT_{basename(course)}.{extension}'), itinerary, extension)
    recorded = signal_position(raw('sigpos'), course, signal['signal_label']) * 1000
    fmt.require(abs(recorded - signal['expected_position_m']) <= .17 and recorded == position,
                'Recorded original entrance signal differs from the frozen distance axis')
    points = metres_trace(raw('step1'), 'step1', course, itinerary)
    following = [(a[0], b[1]) for a, b in zip(points, points[1:]) if a[0] == b[0] and abs(a[1] - position) <= .17
                 and b[1] > a[1] + .17]
    return following, max(distance for _, distance in points)


def measured_cap(motion, start, target, cap):
    speeds = dict(motion['speed'])
    observations = [(clock, distance, speeds[clock]) for clock, distance in motion['distance']
                    if start < distance <= target and clock in speeds and speeds[clock] > 0]
    fmt.require(observations, 'No co-timed original positive-speed and position measurements inside the approach')
    tolerance = motion['rounded_speed_tolerance_kmh']
    max_speed = max(speed for _, _, speed in observations)
    witness = [row for row in observations if abs(row[2] - cap) <= tolerance]
    fmt.require(max_speed <= cap + tolerance and len(witness) >= 2 and witness[0][1] < witness[-1][1],
                'Actual occupied-entry movement did not show the selected saved speed limit over a distance range')
    return {'maximum_measured_speed_kmh': round(max_speed, 5), 'matching_sample_count': len(witness),
            'matching_position_range_m': [round(witness[0][1], 5), round(witness[-1][1], 5)]}


def relevant_messages(run, receiver, donor):
    lines = fmt.data_rows(run.original_text('OT_Messages.txt'))
    return [(level, clock, course, message.removeprefix(f'Course {course}: '), details[0] if details else None)
            for level, clock, course, message, *details in lines if course in (receiver, donor)]


def message_record(row):
    return dict(zip(('level', 'clock', 'course_id', 'message', 'location'), row))


def holding_plateau(motion, position, timestamp, tolerance):
    intervals = fmt.stationary_intervals(motion['speed'], motion['distance'])
    found = [row for row in intervals if abs(row['distance_reference_m'] - position) <= tolerance
             and row['start_s'] <= timestamp <= row['end_s']]
    fmt.require(len(found) == 1, 'Original train lacks one witnessed stationary interval at the expected position')
    return found[0]


def physical_join(permitted, denied, deny_window, definitions, receiver, donor, station, tolerance):
    labels, visits = definitions['itineraries'], definitions['visits']
    motions = [{cid: traces(run, cid, labels[cid]) for cid in (receiver, donor)} for run in (permitted, denied)]
    yes, no = motions
    axis = [case[donor]['origin_m'] for case in motions]
    fmt.require(axis[0] == axis[1], 'Original donor distance origin differs between the two cases')
    signal = frozen_signal(permitted, definitions['signal_identity'], labels[donor], axis[0])
    signal_m = signal['expected_position_m']
    authorities = [outbound_authorities(run, donor, labels[donor], signal, signal_m) for run in (permitted, denied)]
    (reserved, _), (blocked, last_limit) = authorities
    donor_platform = axis[0] + visits[donor]['distance_m']
    fmt.require(len(reserved) == 1 and reserved[0][1] + .17 >= donor_platform and not blocked
                and last_limit <= signal_m + .17,
                'Original allowed case must reserve the platform while the denied case has no authority beyond the signal')
    reserve_time, _ = reserved[0]
    original_yes, original_no = [relevant_messages(run, receiver, donor) for run in (permitted, denied)]
    joins = [row for row in original_yes if row[3].startswith(('Trains joined', 'Trains splitted'))]
    fmt.require(len(joins) == 2 and {row[2] for row in joins} == {receiver, donor}
                and all(row[0] == 'NORMAL' and row[3] == f'Trains joined at {station}' and row[4] == f'({station})'
                        for row in joins) and joins[0][1] == joins[1][1]
                and not any(row[3].startswith(('Trains joined', 'Trains splitted')) for row in original_no),
                'Original messages must identify exactly one paired physical join and no denied join')
    donor_time, donor_contact = yes[donor]['distance'][-1]
    join_time = printed_clock(joins[0][1], donor_time)
    receiver_front = yes[receiver]['origin_m'] + visits[receiver]['distance_m']
    receiver_at_entry = holding_plateau(yes[receiver], receiver_front, reserve_time, tolerance)
    original_gap = donor_platform - donor_contact
    length = definitions['event']['initial_main']['length_m']
    fmt.require(abs(original_gap - length) <= tolerance and reserve_time < donor_time <= receiver_at_entry['end_s']
                and abs(join_time - donor_time) <= 1.01,
                'Original joining position or time does not match the occupied platform and receiver body length')
    fmt.require(any(clock > join_time and speed > 0 for clock, speed in yes[receiver]['speed']),
                'Original receiver did not depart after the join')
    no_donor_time, no_donor_position = no[donor]['distance'][-1]
    fmt.require(abs(no_donor_position - signal_m) <= tolerance and abs(no_donor_time - deny_window[1]) <= 1.01,
                'Denied donor must remain at the entrance signal until the original run ends')
    stop = holding_plateau(no[donor], signal_m, no_donor_time, tolerance)
    name, label = signal['signal_name'], signal['signal_label']
    prefix = label.removesuffix('_' + name)
    aliases = {f'Stop at Signal {candidate}' for candidate in (name, label, f'{name}_{prefix}' if label != name else name)}
    warnings = [row for row in original_no if row[0] == 'WARNING' and row[2] == donor
                and row[3] in aliases and row[4] == f'({signal["document"]})']
    terminated = [row for row in original_no if row[0] == 'WARNING' and row[3] == 'Terminated before End of Itinerary']
    fmt.require(len(warnings) == 1 and abs(printed_clock(warnings[0][1], stop['start_s']) - stop['start_s']) <= 1.01
                and len(terminated) == 2 and {row[2] for row in terminated} == {receiver, donor}
                and all(abs(printed_clock(row[1], no_donor_time) - no_donor_time) <= 1.01 for row in terminated),
                'Denied original output lacks the exact signal stop or expected incomplete-service warnings')
    denied_front = no[receiver]['origin_m'] + visits[receiver]['distance_m']
    denied_plateau = holding_plateau(no[receiver], denied_front, no_donor_time, tolerance)
    fmt.require(denied_plateau['start_s'] < reserve_time,
                'Denied receiver must already be stopped before the permitted-case authority clock')
    return {'signal': signal, 'donor_allowed_authority_s': reserve_time,
            'allowed_join_s': join_time, 'allowed_join_messages': [message_record(row) for row in joins],
            'allowed_receiver_stationary_at_platform': receiver_at_entry,
            'allowed_donor_contact_position_m': round(donor_contact, 5),
            'allowed_contact_gap_m': round(original_gap, 5), 'saved_receiver_length_m': length,
            'allowed_speed_evidence': measured_cap(yes[donor], signal_m, donor_contact, definitions['saved_speed_kmh']),
            'denied_stop_warning': message_record(warnings[0]), 'denied_donor_stationary_at_signal': stop,
            'denied_receiver_still_at_platform': denied_plateau,
            'denied_termination_warnings': [message_record(row) for row in terminated]}


class OccupiedEntryTools(EvaluateNativeRunTools):
    def compare(self, args):
        try:
            receiver, donor = args.receiver.course_id, args.donor.course_id
            fmt.require(receiver != donor, 'Select distinct receiving and supplying Courses')
            outcomes = [item.model_dump(exclude_none=True) for item in (args.receiver, args.donor)]
            allowed, denied = (args.permitted, args.denied)
            a, b = [read_receipts(self.directory(spec.evidence_directory), secure_bytes=self.secure_bytes)
                    for spec in (allowed, denied)]
            permitted_run = FrozenRailwayRun(self.directory(allowed.output_directory), a, outcomes, self.secure_bytes)
            denied_run = FrozenRailwayRun(self.directory(denied.output_directory), b, outcomes, self.secure_bytes,
                                         expected_completion=False)
            definitions = static_join(permitted_run, receiver, donor, args.station_sign)
            difference = check_signal_difference(permitted_run, denied_run, a, b, definitions['signal_identity'])
            physical = physical_join(permitted_run, denied_run, configured_window(denied_run, b), definitions,
                                     receiver, donor, args.station_sign, args.contact_tolerance_m)
            return {'native_occupied_entry_verified': True, 'signal_only_difference': difference,
                    'scope': 'A fixed-speed incoming Route and one planned join at an occupied platform.',
                    'station_sign': args.station_sign, 'receiver_course_id': receiver, 'donor_course_id': donor,
                    'frozen_join': definitions['event'], 'route': definitions['route'],
                    'saved_speed_kmh': definitions['saved_speed_kmh'], **physical,
                    'permitted_output_sha256': {**permitted_run.receipt['output_sha256'], **permitted_run.files.hashes},
                    'denied_output_sha256': {**denied_run.receipt['output_sha256'], **denied_run.files.hashes},
                    'permitted_input_sha256': a['input_sha256'], 'denied_input_sha256': b['input_sha256']}
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_OCCUPIED_ENTRY_INVALID', 'Could not compare bound original occupied-entry and join effects',
                           str(exc)[:600]) from exc
