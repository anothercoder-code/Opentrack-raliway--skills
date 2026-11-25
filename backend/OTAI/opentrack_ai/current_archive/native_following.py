"""Bound the reference-distance gap between two original Courses on one Itinerary."""

from bisect import bisect_left, bisect_right
from math import floor
from pathlib import Path
import re

from . import catalogs, native_evaluation_formats as fmt, writer
from .catalog_batch_reuse.course_batch import course_record


# The original .st1 records print clocks to 0.01 s and km to four decimals.
CLOCK_HALF_QUANTUM_S = 0.005001
POSITION_COMBINED_ROUNDING_M = 0.100001


def reference_gap(leader, follower, begin, end):
    fmt.require(0 <= begin < end, 'Following check requires an increasing absolute time window')
    for points in (leader, follower):
        fmt.require(points and points[0][0] <= begin - CLOCK_HALF_QUANTUM_S
                    and points[-1][0] >= end + CLOCK_HALF_QUANTUM_S
                    and all(a[0] <= b[0] and a[1] <= b[1] for a, b in zip(points, points[1:])),
                    'Both original trajectories must enclose the window and have nondecreasing reference distance')
    times_leader = [time for time, _ in leader]
    times_follower = [time for time, _ in follower]
    bounds = sorted({begin, end, *(time for time in times_leader if begin < time < end),
                     *(time for time in times_follower if begin < time < end)})
    bound = float('inf')
    witness = None
    for first, last in zip(bounds, bounds[1:]):
        earlier = bisect_right(times_leader, first - CLOCK_HALF_QUANTUM_S) - 1
        later = bisect_left(times_follower, last + CLOCK_HALF_QUANTUM_S)
        leader_pos = leader[earlier][1]
        follower_pos = follower[later][1]
        distance = (leader_pos - follower_pos) * 1000 - POSITION_COMBINED_ROUNDING_M
        if distance < bound:
            bound = distance
            witness = {'interval_s': [first, last], 'leading_sample': leader[earlier],
                       'following_sample': follower[later]}
    return {'reference_gap_lower_bound_m': floor(bound * 1000) / 1000,
            'interval_count': len(bounds) - 1, 'least_gap_witness': witness,
            'sample_units': ['s', 'km']}


def trajectory(files, course, itinerary):
    name = f'OT_{course}.st1'
    fmt.require(name in files.expected_hashes, 'Following check requires launcher SHA-256 for original trajectories')
    text = files.read(name)
    header = re.findall(r'^// Itineraries: [ \t]*1:[ \t]*(.+?)[ \t]*\r?$', text, re.M)
    fmt.require(header == [itinerary], 'Original trajectory header differs from the single frozen Itinerary')
    parsed = fmt.series(text, 'st1', course)
    fmt.require(parsed['units'] == ['s', 'km'], 'Following checks use original seconds and kilometres')
    return parsed['points']


def audit(specs, files, results, frozen, evidence, *, read_member, digest, secure_bytes):
    fmt.require(frozen is not None and evidence is not None and isinstance(specs, list) and 1 <= len(specs) <= 64,
                'Following checks require frozen original inputs and 1 to 64 windows')
    bindings = Path(frozen['paths']['CourseFile']).relative_to(frozen['project_root']).as_posix()
    data = read_member(evidence['evidence_directory'] / 'inputs', bindings, nested=True, secure_bytes=secure_bytes)
    fmt.require(digest(data) == evidence['input_sha256'][bindings], 'Frozen Course catalog differs from its manifest')
    frozen_courses = {}
    for item in catalogs.course_items(writer.load_next_compatible(data)[0]):
        record = course_record(item)
        identifier = record['course_id']
        fmt.require(identifier not in frozen_courses, 'Duplicate Course in frozen catalog')
        frozen_courses[identifier] = record
    outcome = {item['course_id']: item for item in results if item['completion_verified']}
    cached = {}
    observed = []
    for req in specs:
        first, second = req['leading_course'], req['following_course']
        begin, end = map(fmt.number, (req['begin_s'], req['end_s']))
        minimum = fmt.number(req['minimum_reference_gap_m'])
        fmt.require(first != second and {first, second} <= outcome.keys() and minimum > 0,
                    'Select two completed Courses and a positive reference gap')
        lead, follow = frozen_courses[first], frozen_courses[second]
        fmt.require(len(lead['itineraries']) == 1 and lead['itineraries'] == follow['itineraries']
                    and lead['output_offset_m'] == follow['output_offset_m'],
                    'Both Courses must use one identical directed Itinerary and output offset')
        itinerary, = lead['itineraries']
        fmt.require(all(outcome[cid]['origin_event']['time_s'] < begin < end <
                        outcome[cid]['last_observed_event']['time_s'] for cid in (first, second)),
                    'Following window must be strictly within the actual shared operation time')
        for cid in (first, second):
            if cid not in cached:
                cached[cid] = trajectory(files, cid, itinerary)
        gap = reference_gap(cached[first], cached[second], begin, end)
        observed.append({'leading_course': first, 'following_course': second, 'window_s': [begin, end],
                         'itinerary': itinerary, 'spacing_modes': [lead['spacing_mode'], follow['spacing_mode']],
                         'minimum_reference_gap_m': minimum, **gap,
                         'verified': gap['reference_gap_lower_bound_m'] >= minimum})
    return observed
