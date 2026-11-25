"""Witness a physical same-direction join on one frozen platform."""

from collections import defaultdict
import re
from typing import Annotated

from pydantic import Field, StrictInt

from ..errors import APIError
from . import catalogs, native_evaluation_formats as fmt, writer
from .catalog_batch_reuse.course_batch import course_record
from .native_headway_tools import Run, SpacingCourse
from .native_incident_effects import printed_clock
from .native_interlocking import CLOCK_TOLERANCE, FrozenRailwayRun
from .native_occupied_entry_effects import holding_plateau, message_record, relevant_messages
from .native_result_tools import EvaluateNativeRunTools, Name
from .native_run_evaluation import basename, read_receipts
from .native_signal_stop_effect import POSITION_TOLERANCE_M
from .network_composition_plan import _arrival_route, _route_name
from .network_operating_plan import route_trace
from .shunting_workflow.core import plan_connections
from .tools import Input


class DirectedPlatform(Input):
    document: Name
    end_id: Annotated[StrictInt, Field(ge=0)]


class VerifyNativePlatformJoin(Input):
    run: Run
    receiver: SpacingCourse
    donor: SpacingCourse
    station_sign: Name
    main_visit_index: Annotated[StrictInt, Field(gt=0)] | None = None
    expected_platform: DirectedPlatform | None = None
    contact_tolerance_m: Annotated[float, Field(ge=.17, le=2, allow_inf_nan=False)] = .3


def planned_itineraries(text, choices, extension):
    labels = re.findall(r'^// Itineraries:[ \t]*(.*?)[ \t]*\r?$', text, re.M)
    expected = ' / '.join(f'{index}: {name}' for index, name in enumerate(choices, 1))
    fmt.require(labels == [expected], f'Original .{extension} planned Itinerary header differs from the frozen Course')
    return text


def platform_signals(text, course):
    fmt.headers(text, 'OT_Signals')
    fmt.course_header(text, 'Signal Positions', course)
    fmt.require(re.findall(r'^// x-Legend[ \t]*:[ \t]*\[([^\[\]\r\n]+)\][ \t]*\r?$', text, re.M) == ['km'],
                'The original platform signal legend must use kilometres')
    signals = defaultdict(list)
    for row in fmt.data_rows(text):
        fmt.require(len(row) in {3, 4}, 'Unexpected original signal position row')
        if row[1] in {'MS', 'MDS'}:
            fmt.require(len(row) == 4 and row[2], 'Malformed original physical main signal row')
            signals[row[2]].append((1000 * fmt.number(row[0]), row[1]))
    return signals


def platform_model_signal(project, end_key):
    end = project.model(end_key)
    signal = end.contents[11].value
    fmt.require(writer.kind(signal) == 'OTSignalModel' and signal.contents[7].value is end
                and signal.contents[8].values[0] in (1, 2, 24, 25, 26),
                'The platform requires a paired physical main signal on its directed station End')
    paired = project.byid[end_key[0]].get(end.contents[8].value)
    addition = writer.string(end.contents[18].value) or (
        writer.string(paired.contents[18].value) if paired is not None else None)
    name = writer.string(signal.contents[13].value)
    fmt.require(name, 'The platform main signal requires a saved name')
    return signal.contents[0].value, f'{addition}_{name}' if addition else name


def frozen_options(run, course, station, index, *, donor):
    result = []
    for label in run.preferences[course]:
        itinerary = run.itineraries[label]
        visits = route_trace(run.project, itinerary)['visits']
        matches = [i for i, visit in enumerate(visits)
                   if visit['station_sign'] == station and (index is None or index == i)]
        fmt.require(len(matches) == 1, 'The join station must have one identified visit per frozen Itinerary')
        occurrence, = matches
        fmt.require(occurrence == len(visits) - 1 if donor else 0 < occurrence < len(visits) - 1,
                    'The join must terminate the donor and occur at an interior receiver stop')
        visit = visits[occurrence]
        end = tuple(visit['end_key'])
        stop = visit.get('head_stop') or visit.get('default_stop')
        fmt.require(visit['stop_edge_key'] is not None and (stop is None or tuple(stop['end_key']) == end),
                    'Platform proof requires a stopping Edge at the directed station reference')
        signal_id, signal_label = platform_model_signal(run.project, end)
        arrival = _arrival_route(run.project, itinerary, end)
        result.append({**visit, 'end_key': end, 'itinerary': label, 'signal_id': signal_id,
                       'signal_label': signal_label, 'arrival_route': _route_name(arrival),
                       'arrival_route_owner': run.project.owners[id(arrival)]})
    return result


def match_platform(options, observed, offset_m):
    labels = defaultdict(set)
    for option in options:
        labels[option['signal_label']].add(option['end_key'])
    fmt.require(all(len(ends) == 1 for ends in labels.values()),
                'Distinct candidate platforms cannot share an ambiguous original signal label')
    actual = labels.keys() & observed.keys()
    fmt.require(len(actual) == 1, 'Expected exactly one observed candidate platform main signal')
    label, = actual
    fmt.require(len(observed[label]) == 1, 'Original platform signal occurs more than once in the Course legend')
    (position_m, kind), = observed[label]
    matches = [option for option in options if option['signal_label'] == label
               and abs(option['distance_m'] + offset_m - position_m) <= POSITION_TOLERANCE_M]
    fmt.require(matches, 'Original platform signal kilometre differs from the frozen signed Course distance')
    edges = {tuple(option['stop_edge_key']) for option in matches}
    fmt.require(len(edges) == 1, 'Original platform signal admits conflicting stopping Edges')
    return matches, position_m, kind


def native_course_motion(run, course, offset_m):
    raw = {extension: planned_itineraries(run.original_text(f'OT_{basename(course)}.{extension}'),
                                         run.preferences[course], extension)
           for extension in ('st1', 'vt', 'sigpos')}
    positions = fmt.series(raw['st1'], 'st1', course)
    fmt.require(positions['units'][1] == 'km', 'The original platform distance trace must use kilometres')
    distance = [(time, metres * 1000) for time, metres in positions['points']]
    speed = fmt.series(raw['vt'], 'vt', course)['points']
    fmt.require(len(distance) >= 2 and len(speed) >= 2 and abs(distance[0][1] - offset_m) <= POSITION_TOLERANCE_M
                and all(a[1] <= b[1] for a, b in zip(distance, distance[1:])),
                'Original join requires a full forward trajectory on the saved Course distance axis')
    return {'distance': distance, 'speed': speed, 'signals': platform_signals(raw['sigpos'], course)}


def joint_contact(receiver, donor, receiver_signal_m, donor_signal_m, length_m, join_clock, tolerance):
    terminal_time, position = donor['distance'][-1]
    fmt.require(donor['speed'][-1][1] == 0 and abs(donor['speed'][-1][0] - terminal_time) <= CLOCK_TOLERANCE,
                'Original donor needs a terminal zero-speed sample at a recorded position')
    donor_stop = holding_plateau(donor, position, terminal_time, tolerance)
    contact_time = donor_stop['start_s']
    reported_time = printed_clock(join_clock, contact_time)
    fmt.require(abs(reported_time - contact_time) <= 1.01,
                'Paired original join messages do not match the observed donor stopping onset')
    stopped = holding_plateau(receiver, receiver_signal_m, contact_time, POSITION_TOLERANCE_M)
    gap = donor_signal_m - position
    fmt.require(stopped['start_s'] < contact_time and abs(gap - length_m) <= tolerance,
                'Original donor front does not reach the stopped receiver tail on this platform')
    donor_positions = dict(donor['distance'])
    fmt.require(any(time < contact_time and value > 0 and time in donor_positions
                    and donor_positions[time] < position - POSITION_TOLERANCE_M for time, value in donor['speed']),
                'Original donor must make a positive-speed approach before contact')
    receiver_positions = dict(receiver['distance'])
    onward = next(({'time_s': time, 'front_position_m': round(receiver_positions[time], 5)}
                   for time, speed in receiver['speed'] if time > contact_time and speed > 0
                   and time in receiver_positions and receiver_positions[time] > receiver_signal_m + POSITION_TOLERANCE_M), None)
    fmt.require(onward is not None, 'The original receiver must move beyond the platform after coupling')
    return {'contact_time_s': contact_time, 'reported_join_time_s': reported_time,
            'receiver_stationary': stopped, 'donor_terminal_stationary': donor_stop,
            'donor_front_m': round(position, 5), 'donor_front_behind_reference_m': round(gap, 5),
            'expected_receiver_body_length_m': length_m, 'receiver_onward_sample': onward}


def timetable_contact(receiver, donor, name, contact):
    fmt.require(name, 'The frozen station code must identify a saved station name')
    arrival = donor['last_observed_event']
    fmt.require(arrival['station'] == name and arrival['kind'] == 'Arr.'
                and abs(arrival['time_s'] - contact['contact_time_s']) <= 1.01,
                'Original donor terminal arrival does not corroborate the platform contact')
    endpoints = []
    for kind, key in (('Arr.', 'start_s'), ('Dep.', 'end_s')):
        events = [row for row in receiver['events'] if row['kind'] == kind and row['station'] == name
                  and abs(row['time_s'] - contact['receiver_stationary'][key]) <= 1.01]
        fmt.require(len(events) == 1, 'Original receiver arrival and departure must bound the witnessed platform stop')
        endpoints.append(events[0])
    return {'receiver_arrival': endpoints[0], 'receiver_departure': endpoints[1], 'donor_arrival': arrival}


class PlatformJoinTools(EvaluateNativeRunTools):
    def verify_join(self, args):
        try:
            receiver, donor = args.receiver.course_id, args.donor.course_id
            fmt.require(receiver != donor, 'Select two distinct original Courses')
            spec = args.run
            evidence = read_receipts(self.directory(spec.evidence_directory), secure_bytes=self.secure_bytes)
            expectations = [item.model_dump(exclude_none=True) for item in (args.receiver, args.donor)]
            run = FrozenRailwayRun(self.directory(spec.output_directory), evidence, expectations, self.secure_bytes)
            roles = {'timetable': 'Timetable', 'courses': 'Course', 'trains': 'Train', 'stations': 'Station', 'depot': 'Depot'}
            banks = {role: run.dependency(run.settings['paths'][key + 'File']) for role, key in roles.items()}
            station = args.station_sign
            operation = {'kind': 'join', 'main_course': receiver, 'other_course': donor, 'station_sign': station}
            if args.main_visit_index is not None:
                operation['main_visit_index'] = args.main_visit_index
            _, plan = plan_connections(banks, {'schema': 'split-join-timetable-plan/1',
                    'accept_unverified_spatial_and_dynamic_execution': True, 'operations': [operation]},
                    verify_existing=True, sequential_main=True)
            event, = plan['events']
            courses = writer.load_next_compatible(banks['courses'])[0]
            offsets = {row['course_id']: row['output_offset_m'] for row in map(course_record, catalogs.course_items(courses))}
            motions = {course: native_course_motion(run, course, offsets[course]) for course in (receiver, donor)}
            options = [frozen_options(run, course, station, event['main_visit_index'] if course == receiver else None,
                                      donor=course == donor) for course in (receiver, donor)]
            (main, main_m, main_kind), (other, other_m, other_kind) = [
                match_platform(choices, motions[course]['signals'], offsets[course])
                for choices, course in zip(options, (receiver, donor), strict=True)]
            end, edge = main[0]['end_key'], main[0]['stop_edge_key']
            fmt.require(end == other[0]['end_key'] and edge == other[0]['stop_edge_key']
                        and min(option['stop_edge_length_m'] for option in main + other) >= event['projected_main_length_m'],
                        'Original Courses must converge on the same directed platform Edge and fit after joining')
            if args.expected_platform is not None:
                fmt.require(end == (args.expected_platform.document, args.expected_platform.end_id),
                            'Original physical join occurred at a different directed platform')

            fmt.headers(run.original_text('OT_Messages.txt'), 'OT_messages')
            lines = relevant_messages(run, receiver, donor)
            paired = [row for row in lines if row[3] == f'Trains joined at {station}']
            fmt.require(len(paired) == 2 and {row[2] for row in paired} == {receiver, donor}
                        and paired[0][1] == paired[1][1]
                        and all(row[0] == 'NORMAL' and row[4] == f'({station})' for row in paired),
                        'Original output needs one paired physical join message for both Courses at the station')
            contact = joint_contact(motions[receiver], motions[donor], main_m, other_m,
                                    event['initial_main']['length_m'], paired[0][1], args.contact_tolerance_m)
            outcome = {row['course_id']: row for row in run.receipt['courses']}
            stations = catalogs.station_items(writer.load_next_compatible(banks['stations'])[0])
            name = catalogs.text(stations[station].contents[2].value)
            clocks = timetable_contact(outcome[receiver], outcome[donor], name, contact)
            origins = {course: outcome[course]['origin_event']['time_s'] for course in (receiver, donor)}
            for _, clock, course, message, _ in lines:
                if message.startswith(('Trains joined', 'Trains splitted')):
                    instant = printed_clock(clock, contact['contact_time_s'])
                    fmt.require(not origins[course] < instant < contact['reported_join_time_s'],
                                'Earlier in-course formation change needs independent stock accounting at this join')

            def witness(matches, position_m, kind):
                return {'signal_id': matches[0]['signal_id'], 'signal_label': matches[0]['signal_label'],
                        'signal_type': kind, 'original_signal_position_m': round(position_m, 5),
                        'compatible_saved_itineraries': [item['itinerary'] for item in matches],
                        'compatible_saved_approaches': [{'name': item['arrival_route'], 'owner': item['arrival_route_owner']}
                                                        for item in matches]}

            return {'native_same_platform_join_verified': True, 'station_sign': station, 'station_name': name,
                    'directed_platform_end': list(end), 'stopping_edge': list(edge),
                    'track_id': main[0]['incoming_track_id'], 'saved_join_event': event,
                    'receiver': {'course_id': receiver, **witness(main, main_m, main_kind)},
                    'donor': {'course_id': donor, **witness(other, other_m, other_kind)},
                    'original_join_messages': [message_record(row) for row in paired], **contact,
                    'original_timetable_events': clocks,
                    'input_sha256': evidence['input_sha256'], 'output_sha256': run.files.hashes,
                    'executable_sha256': evidence['executable_sha256']}
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_PLATFORM_JOIN_INVALID', 'Could not verify a bound original physical platform join',
                           str(exc)[:550]) from exc
