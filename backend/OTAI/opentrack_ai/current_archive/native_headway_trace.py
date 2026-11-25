"""Subsecond observations from sealed original movement and reservation/release traces."""

from bisect import bisect_left, bisect_right
import re
from typing import Annotated

from pydantic import Field

from ..errors import APIError
from ..native_headway_plan import course_pair
from . import native_evaluation_formats as fmt
from .native_following import CLOCK_HALF_QUANTUM_S
from .native_headway_tools import Run, SpacingCourse
from .native_interlocking import FrozenInterlocking
from .native_interlocking_tools import Resource
from .native_result_tools import EvaluateNativeRunTools
from .native_run_evaluation import basename, read_receipts
from .runfile_parameters import inspect_runfile
from .tools import Input


METRES_HALF_QUANTUM = 0.050001
CLOCK_QUANTUM = 0.01
OPTIONS = ('Safety Margin', 'Communication Period', 'Optimization Period', 'Delay Scenario')


class TraceStudy(Input):
    leading_course: SpacingCourse
    following_course: SpacingCourse
    runs: Annotated[list[Run], Field(min_length=1, max_length=12)]
    checkpoints_m: Annotated[list[Annotated[float, Field(gt=0, allow_inf_nan=False)]],
                             Field(min_length=1, max_length=64)]
    monitored_resources: Annotated[list[Resource], Field(max_length=24)] = Field(default_factory=list)


def clock_range(before, after):
    return [round(max(0, before - CLOCK_HALF_QUANTUM_S), 6), round(after + CLOCK_HALF_QUANTUM_S, 6)]


def clock_difference(first, second):
    return [round(second[0] - first[1], 6), round(second[1] - first[0], 6)]


class Progress:
    def __init__(self, points):
        fmt.require(points and points[0][0] >= 0
                    and all(a[0] <= b[0] and a[1] <= b[1] for a, b in zip(points, points[1:])),
                    'A witnessed crossing needs a nondecreasing, nonempty original distance trace')
        self.points = points
        self.positions = [value for _, value in points]

    def crossing(self, coordinate):
        below = bisect_left(self.positions, coordinate - METRES_HALF_QUANTUM) - 1
        above = bisect_right(self.positions, coordinate + METRES_HALF_QUANTUM)
        if below < 0 or above == len(self.positions):
            return None
        a, b = self.points[below], self.points[above]
        return {'seconds': clock_range(a[0], b[0]), 'samples_s_m': [a, b]}

    def reservation_shape(self, spans, offset, step):
        ranges = sorted((span['from_m'] + offset, span['to_m'] + offset, key)
                        for key, entries in spans.items() for span in entries)
        starts = [item[0] for item in ranges]
        instant_changes = 0
        positioned_advances = 0
        witness = None
        for first, second in zip(self.points, self.points[1:]):
            elapsed = second[0] - first[0]
            if second[1] - first[1] <= 2 * METRES_HALF_QUANTUM:
                continue
            if elapsed == 0:
                instant_changes += 1
                continue
            if elapsed > step + CLOCK_QUANTUM + 0.000001:
                continue
            i = bisect_right(starts, first[1]) - 1
            if i >= 0 and ranges[i][0] + METRES_HALF_QUANTUM < first[1] <= second[1] < ranges[i][1] - METRES_HALF_QUANTUM:
                low, high, (document, element) = ranges[i]
                positioned_advances += 1
                if witness is None:
                    witness = {'document': document, 'safety_element_id': element,
                               'span_in_output_coordinate_m': [low, high], 'samples_s_m': [first, second]}
        return {'sample_count': len(self.points), 'same_printed_clock_advance_count': instant_changes,
                'progressive_advances_within_one_saved_element': positioned_advances,
                'first_progressive_advance': witness}


def original_points(railway, course, itinerary, extension):
    name = f'OT_{basename(course)}.{extension}'
    raw = railway.original_text(name)
    labels = re.findall(r'^// Itineraries:[ \t]*1:[ \t]*(.+?)[ \t]*\r?$', raw, re.M)
    fmt.require(labels == [itinerary], f'Original {extension} Itinerary differs from frozen Course {course}')
    parsed = fmt.series(raw, extension, course)
    expected = 'km/h' if extension == 'vt' else 'km'
    fmt.require(parsed['points'] and parsed['units'] == ['s', expected],
                f'Expected a nonempty metric original {extension} output for {course}')
    if extension == 'vt':
        return parsed['points']
    return [(stamp, round(value * 1000, 5)) for stamp, value in parsed['points']]


def first_positive_sample(points):
    index = next((i for i, (_, speed) in enumerate(points) if speed > 0), None)
    fmt.require(index is not None, 'Original speed trace never reports movement')
    return {'first_positive_sample_s_kmh': points[index],
            'previous_sample_s_kmh': points[index - 1] if index else None}


def trace_settings(railway, evidence):
    members = [name for name in evidence['input_sha256'] if name.lower().endswith('.run')]
    fmt.require(len(members) == 1, 'Headway trace requires one frozen .run member')
    run = railway.dependency(str(railway.settings['project_root'] / members[0]))
    inspected = inspect_runfile(run)
    fmt.require(inspected['editable'], 'Frozen simulation step is outside the supported .run format')
    frozen_step = float(inspected['parameters'][b'Step'])
    protocol_name, = [name for name in railway.receipt['output_sha256'] if name.startswith('OT_Protocol.')]
    protocol = railway.original_text(protocol_name)
    printed, = re.findall(r'^Simulation Step[ \t]*:[ \t]*([0-9]+(?:\.[0-9]+)?)[ \t]+s[ \t]*\r?$',
                          protocol, re.M)
    decimals = len(printed.partition('.')[2])
    fmt.require(float(printed) > 0 and abs(frozen_step - float(printed)) <= .5 * 10**-decimals + 1e-8,
                'Original protocol step differs from frozen simulation settings')
    options = inspected['editable_options']
    return {'configured_step_s': frozen_step, 'configured_float32_step_s': inspected['numeric']['step_seconds_float32'],
            'original_protocol_step_s': float(printed), 'original_protocol_step_text': printed,
            'frozen_spacing_options': {key: options[key.encode()].decode('ascii') if options[key.encode()] is not None
                                       else None for key in OPTIONS}}


def inspect_monitor(railway, reference, courses, route, progress, offset, step):
    bound, cycles = railway.resource(reference)
    key = bound['document'], bound['safety_element_id']
    spans = route['spans'].get(key, [])
    fmt.require(len(spans) == 1 and len(cycles) == 2 and [row['course_id'] for row in cycles] == courses,
                'Use an original monitor covering one directed span and the exact two ordered Courses')
    span, = spans
    entries = {}
    for cycle in cycles:
        reservation, release = cycle['reservation_s']
        enter, clear = cycle['occupation_s']
        fmt.require(None not in (reservation, enter, clear, release) and reservation <= enter < clear <= release,
                    'Require both complete original reservation and occupation cycles')
        name = cycle['course_id']
        crossing = progress[name].crossing(span['from_m'] + offset)
        fmt.require(crossing is not None and crossing['seconds'][0] - step <= enter <= crossing['seconds'][1] + step,
                    'Occupation entry lacks a corresponding original train passage within one configured step')
        entries[name] = crossing
    released = cycles[0]['reservation_s'][1]
    reserved = cycles[1]['reservation_s'][0]
    interval = clock_difference(clock_range(released, released), clock_range(reserved, reserved))
    return {**bound, **span, 'cycles': cycles, 'entry_passage_bounds': entries,
            'leading_release_to_following_reservation_printed_s': round(reserved - released, 2),
            'leading_release_to_following_reservation_bounds_s': interval,
            'positive_gap_shorter_than_configured_step': 0 < interval[0] < interval[1] < step}


def measure_trace(railway, evidence, pair, positions, monitors):
    ids = [item['course_id'] for item in pair]
    fmt.require(sorted(railway.receipt['protocol']['used_courses']) == sorted(ids),
                'Original execution must contain the exact two selected Courses')
    lead, follow = course_pair(railway.dependency(railway.settings['paths']['CourseFile']), ids, 'same_itinerary')
    fmt.require(lead['spacing_mode'] in {'discrete', 'moving', 'moving_cbtc'}, 'Unsupported frozen native spacing mode')
    offset = lead['output_offset_m']
    itinerary, = lead['itineraries']
    route = railway.routes[ids[0]]
    fmt.require(all(0 < value < route['length_m'] for value in positions),
                'Choose checkpoints strictly inside the common directed route')
    settings = trace_settings(railway, evidence)
    step = settings['configured_step_s']
    traces, courses = {}, {}
    for outcome, report in zip(pair, railway.receipt['courses'], strict=True):
        name = outcome['course_id']
        fmt.require(report['course_id'] == name, 'Original Course evaluation order differs')
        shapes = {ext: Progress(original_points(railway, name, itinerary, ext)) for ext in ('st1', 'step1', 'step2')}
        actual = shapes['st1'].positions
        fmt.require(abs(actual[0] - offset) <= METRES_HALF_QUANTUM
                    and abs(actual[-1] - actual[0] - route['length_m']) <= report['distance_tolerance_m'],
                    'Recorded origin/reference or total displacement differs from the frozen route')
        traces[name] = shapes
        courses[name] = {'origin_tt': report['origin_event'],
                         'first_reported_motion': first_positive_sample(original_points(railway, name, itinerary, 'vt')),
                         'reservation_output': shapes['step1'].reservation_shape(route['spans'], offset, step),
                         'release_output': shapes['step2'].reservation_shape(route['spans'], offset, step)}
    checkpoints = []
    for position in sorted(positions):
        coordinate = position + offset
        a, b = (traces[name]['st1'].crossing(coordinate) for name in ids)
        fmt.require(a is not None and b is not None, 'Original movement traces do not bracket the requested checkpoint')
        released = traces[ids[0]]['step2'].crossing(coordinate)
        reserved = traces[ids[1]]['step1'].crossing(coordinate)
        elements = [{'document': document, 'safety_element_id': element, **span}
                    for (document, element), spans in route['spans'].items() for span in spans
                    if span['from_m'] <= position <= span['to_m']]
        fmt.require(elements, 'Requested distance does not bind to a saved route Safety Element')
        checkpoints.append({'metres_from_route_origin': position, 'output_coordinate_m': coordinate,
                            'saved_safety_elements': elements,
                            'leading_passage': a, 'following_passage': b,
                            'passage_headway_bounds_s': clock_difference(a['seconds'], b['seconds']),
                            'leading_release_trace_crossing': released, 'following_reservation_trace_crossing': reserved,
                            'release_to_reservation_trace_bounds_s': (
                                clock_difference(released['seconds'], reserved['seconds']) if released and reserved else None),
                            })
    origins = [courses[name]['origin_tt'] for name in ids]
    fmt.require(origins[0]['time_s'] <= origins[1]['time_s'], 'Original departures must be in declared order')
    planned = [row['planned_s'] for row in origins]
    groups = [inspect_monitor(railway, ref, ids, route, {name: traces[name]['st1'] for name in ids}, offset, step)
              for ref in monitors]
    metric = [courses[name]['first_reported_motion']['first_positive_sample_s_kmh'][0] for name in ids]
    return {**settings, 'itinerary': itinerary, 'route_length_m': route['length_m'], 'spacing_mode': lead['spacing_mode'],
            'planned_departure_headway_s': planned[1] - planned[0] if None not in planned else None,
            'original_tt_departure_headway_s': origins[1]['time_s'] - origins[0]['time_s'],
            'first_reported_positive_speed_sample_gap_s': round(metric[1] - metric[0], 2),
            'courses': courses, 'checkpoints': checkpoints, 'monitored_handover': groups,
            'frozen_input_sha256': evidence['input_sha256'],
            'original_output_sha256': {**railway.receipt['output_sha256'], **railway.files.hashes}}


class TraceTools(EvaluateNativeRunTools):
    def measure(self, args):
        pair = [item.model_dump(exclude_none=True) for item in (args.leading_course, args.following_course)]
        try:
            fmt.require(pair[0]['course_id'] != pair[1]['course_id']
                        and all(pair[0][key] == pair[1][key] for key in ('origin_station', 'terminal_station', 'distance_m')),
                        'Use distinct Courses on the same directed route with explicit matching endpoints and length')
            fmt.require(len(set(args.checkpoints_m)) == len(args.checkpoints_m), 'Select distinct checkpoints')
            fmt.require(len({item.evidence_directory for item in args.runs}) == len(args.runs),
                        'Select each original run once')
            monitors = [item.model_dump() for item in args.monitored_resources]
            fmt.require(len({(item['document'], item['group']) for item in monitors}) == len(monitors),
                        'Select each original occupation monitor once')
            results = []
            for spec in args.runs:
                evidence = read_receipts(self.directory(spec.evidence_directory), secure_bytes=self.secure_bytes)
                railway = FrozenInterlocking(self.directory(spec.output_directory), evidence, pair, self.secure_bytes)
                results.append({'evidence_directory': spec.evidence_directory,
                                **measure_trace(railway, evidence, pair, args.checkpoints_m, monitors)})
            return {'runs': results, 'clock_output_resolution_s': CLOCK_QUANTUM, 'distance_output_resolution_m': 0.1,
                    'fractional_planned_headway_or_capacity_limit_verified': False}
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_HEADWAY_TRACE_INVALID', 'Could not measure original samples on the bound Itinerary',
                           str(exc)[:600]) from exc
