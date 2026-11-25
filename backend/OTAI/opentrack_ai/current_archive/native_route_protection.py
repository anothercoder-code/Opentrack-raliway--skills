"""Bind a saved cross-worksheet speed zone and release groups to original output."""

from bisect import bisect_left, bisect_right
from typing import Annotated

from pydantic import Field

from ..errors import APIError
from . import catalogs, native_evaluation_formats as fmt, path_functions, writer
from .catalog_batch_reuse.course_batch import course_record
from .multi_document.core import ident
from .native_interlocking import CLOCK_TOLERANCE, STEP_POSITION_TOLERANCE_M, FrozenRailwayRun, metres_trace
from .native_platform_join import planned_itineraries, platform_model_signal
from .native_result_tools import CourseOutcome, EvaluateNativeRunTools, Name
from .native_run_evaluation import basename, read_receipts
from .native_throat_passage import EdgeID, advances, crossing_samples
from .network_composition_plan import itinerary_routes
from .route_edit_tools import _protection_values, _route_shape
from .saved_document_insertion import _metric_zone_aspect
from .tools import Input, PathText


TOOL = 'opentrack_verify_native_route_protection'
TRACE_EXTENSIONS = ('st1', 'vt', 'sigpos', 'step1', 'step2')
POSITION_TOLERANCE_M = 1.0
SPEED_ROUNDING_KMH = 0.2


class RouteEnd(Input):
    document: Name
    end_id: EdgeID

    def key(self):
        return self.document, self.end_id


class ProtectedRoute(Input):
    document: Name
    route_name: Name
    array_id: EdgeID
    start_id: EdgeID
    zone_start: RouteEnd
    zone_end: RouteEnd
    release_group_starts: Annotated[list[RouteEnd], Field(min_length=2, max_length=100)]
    aspect_code: EdgeID


class RouteProtection(Input):
    course_id: Name
    routes: Annotated[list[ProtectedRoute], Field(min_length=1, max_length=8)]


class VerifyNativeRouteProtection(Input):
    output_directory: PathText
    evidence_directory: PathText
    course_outcome: CourseOutcome
    protection: RouteProtection


def output_names(spec):
    return {f'OT_{basename(spec.course_id)}.{kind}' for kind in TRACE_EXTENSIONS}


def saved_protection(project, route):
    release, start, end = route.contents[_route_shape(route) + 1].values
    groups = [project.key(item) for item in path_functions.mutable_array(release)]
    zone = (project.key(start) if start is not None else None, project.key(end) if end is not None else None)
    return groups, zone


def frozen_routes(project, course, spec):
    fmt.require(course['course_id'] == spec.course_id and course['enabled'] and len(course['itineraries']) == 1,
                'One enabled Course with one saved Itinerary is required')
    label, = course['itineraries']
    itinerary, = [item for item in project.dests if catalogs.text(item.contents[1].value) == label]
    nodes, _ = project.dest_view(itinerary)
    axis = {nodes[0]: course['output_offset_m']}
    for first, second in zip(nodes, nodes[1:]):
        edge = project.model(project.edge_between(first, second))
        axis[second] = axis[first] + edge.contents[9].values[1]
    fmt.require(len(axis) == len(nodes) and all(a < b for a, b in zip(axis.values(), list(axis.values())[1:])),
                'The original motion axis must have unique, increasing native Ends')
    selected = list(itinerary_routes(project, itinerary))
    seen, output = set(), []
    for item in spec.routes:
        owner = item.document, item.start_id
        ref = item.route_name, item.array_id, item.start_id
        route, = [row for row in selected if project.owners[id(row)] == owner and ident(row) == ref]
        fmt.require(id(route) not in seen, 'Select a protected Route only once')
        seen.add(id(route))
        route_nodes = project.route_view(route)
        crossings = [(a, b) for a, b in zip(route_nodes, route_nodes[1:]) if a[0] != b[0]]
        fmt.require(len(crossings) == 1, 'Select a native Route with exactly one worksheet continuation')
        before, after = crossings[0]
        local = project.related(before)
        remote = project.block_end(local)
        fmt.require(remote[0] == after[0] and project.block_end(remote) == local,
                    'Frozen Route lacks reciprocal native connectors')
        fragment = project.owned(remote, 'OTRoute', ref)
        local_release, (local_start, local_end) = saved_protection(project, route)
        remote_release, (remote_start, remote_end) = saved_protection(project, fragment)
        start = remote_start if remote_start is not None else local_start
        end = remote_end if remote_end is not None else local_end
        fmt.require((start, end) == (item.zone_start.key(), item.zone_end.key())
                    and axis[start] < axis[before] < axis[end],
                    'Native merged slow zone differs from the reviewed cross-worksheet interval')
        release = local_release + remote_release
        fmt.require(release == [anchor.key() for anchor in item.release_group_starts]
                    and all(axis[a] < axis[b] for a, b in zip(release, release[1:])),
                    'Frozen merged release group starts differ from their reviewed exact order')
        profile = _protection_values(route, _route_shape(route))
        fmt.require(profile['signal_aspects'] == [item.aspect_code], 'Frozen Route does not select the reviewed single aspect')
        _, signal_label = platform_model_signal(project, owner)
        signal = project.model(owner).contents[11].value
        fmt.require(signal.contents[9].values[0] == 2, 'Only the original metric signal legend is supported')
        cap = None
        if item.aspect_code:
            _, cap = _metric_zone_aspect(path_functions.mutable_array(route.contents[0].value), profile['signal_aspects'])
        output.append({'route': item.route_name, 'origin_signal': signal_label,
                       'route_start_m': axis[owner], 'aspect_code': item.aspect_code, 'fixed_speed_kmh': cap,
                       'head_only': profile['slow_speed_only_for_head'],
                       'zone_end_keys': [list(start), list(end)], 'zone_m': [axis[start], axis[end]],
                       'crossing_m': axis[before], 'connector_ends': [list(local), list(remote)],
                       'release_group_starts': [{'end': list(key), 'distance_m': axis[key]} for key in release]})
    return {'course_id': spec.course_id, 'itinerary': label, 'origin_m': axis[nodes[0]], 'terminal_m': axis[nodes[-1]],
            'routes': output}


def front_at_clock(points, times, instant):
    i = bisect_left(times, instant)
    j = bisect_right(times, instant)
    if i < j:
        fmt.require(points[i][1] == points[j - 1][1], 'Conflicting original front positions at the release clock')
        return [list(points[i]), list(points[j - 1])]
    fmt.require(0 < i < len(times), 'Release clock lies outside the original front movement')
    return [list(points[i - 1]), list(points[i])]


def zone_landmark(front, positions, distance, frozen):
    if distance in (frozen['origin_m'], frozen['terminal_m']):
        point = front[0] if distance == frozen['origin_m'] else front[-1]
        return {'distance_m': distance, 'course_endpoint_s_m': list(point)}
    return {'distance_m': distance, 'front_bracket_s_m': crossing_samples(front, positions, distance)}


def joined_motion(speeds, front):
    speed_factor = 1.609344 if speeds['units'][1] == 'mph' else 1
    timed_speeds = {}
    for clock, speed in speeds['points']:
        fmt.require(timed_speeds.setdefault(clock, speed) == speed, 'Conflicting original speed values at one clock')
    return [(clock, position, timed_speeds[clock] * speed_factor) for clock, position in front if clock in timed_speeds]


def speed_window(motion, start, end, cap):
    samples = [(t, p, s) for t, p, s in motion if start + POSITION_TOLERANCE_M < p < end - POSITION_TOLERANCE_M]
    fmt.require(len(samples) >= 2 and samples[0][1] < samples[-1][1],
                'Insufficient matched native speed and distance samples inside one worksheet portion of the slow zone')
    peak = max(s for _, _, s in samples)
    cap_count = None
    if cap is not None:
        cap_count = len({p for _, p, s in samples if abs(s - cap) <= SPEED_ROUNDING_KMH})
        fmt.require(peak <= cap + SPEED_ROUNDING_KMH and cap_count >= 2,
                    'Observed original speed does not corroborate a fixed speed on both sides of the slow zone')
    return {'from_m': start, 'to_m': end, 'sample_count': len(samples), 'peak_kmh': round(peak, 5),
            'near_fixed_speed_samples': cap_count, 'first_s_m': list(samples[0][:2]), 'last_s_m': list(samples[-1][:2])}


def signal_legend(text, course, itinerary, route):
    planned_itineraries(text, [itinerary], 'sigpos')
    fmt.headers(text, 'OT_Signals')
    fmt.course_header(text, 'Signal Positions', course)
    fmt.require(text.count('// x-Legend: [km]') == 1, 'Expected an original metric signal legend')
    rows = [row for row in fmt.data_rows(text) if len(row) == 4 and row[1] in {'MS', 'MDS'}
            and row[2] == route['origin_signal']]
    fmt.require(len(rows) == 1 and abs(fmt.number(rows[0][0]) * 1000 - route['route_start_m']) <= STEP_POSITION_TOLERANCE_M,
                'Original signal legend does not bind the frozen Route origin')
    expected = str(route['fixed_speed_kmh']) if route['fixed_speed_kmh'] is not None else 'TS'
    fmt.require(rows[0][3] == expected, 'The original Route indication legend differs from the frozen single aspect')
    return rows[0][3]


def release_boundaries(route, run, front, times, reserved, released):
    results = []
    for marker in route['release_group_starts']:
        distance = marker['distance_m']
        matches = [step for step in released if abs(step['to_m'] - distance) <= STEP_POSITION_TOLERANCE_M]
        fmt.require(len(matches) <= 1, 'Ambiguous original Route release frontier at a frozen boundary')
        if not matches:
            fmt.require(distance in (run['origin_m'], run['terminal_m']),
                        f'No original release advance reaches the reviewed {distance:g} m group boundary')
            results.append({**marker, 'kind': 'course_endpoint_archive_anchor'})
            continue
        step, = matches
        bracket = front_at_clock(front, times, step['time_s'])
        fmt.require(bracket[0][1] >= distance - POSITION_TOLERANCE_M
                    and any(authority['time_s'] <= step['time_s'] + CLOCK_TOLERANCE
                            and authority['from_m'] <= distance + STEP_POSITION_TOLERANCE_M
                            and authority['to_m'] >= distance - STEP_POSITION_TOLERANCE_M for authority in reserved),
                    'Release frontier lacks prior original reservation or downstream front movement')
        results.append({**marker, 'kind': 'native_release_advance', 'advance': step, 'front_bracket_s_m': bracket})
    clocks = [item['advance']['time_s'] for item in results if item['kind'] == 'native_release_advance']
    fmt.require(clocks and all(a <= b for a, b in zip(clocks, clocks[1:])),
                'Original release advances did not reach the reviewed boundaries in order')
    return results


def verify_run(run, course, spec):
    frozen = frozen_routes(run.project, course, spec)
    label, cid = frozen['itinerary'], basename(spec.course_id)
    raw = {kind: run.original_text(f'OT_{cid}.{kind}') for kind in TRACE_EXTENSIONS}
    front, reservation, release = (metres_trace(raw[kind], kind, cid, label) for kind in ('st1', 'step1', 'step2'))
    positions = [p for _, p in front]
    times = [t for t, _ in front]
    fmt.require(positions == sorted(positions) and abs(positions[0] - frozen['origin_m']) <= POSITION_TOLERANCE_M
                and abs(positions[-1] - frozen['terminal_m']) <= POSITION_TOLERANCE_M,
                'Original front movement differs from the frozen Route axis')
    speed = fmt.series(planned_itineraries(raw['vt'], [label], 'vt'), 'vt', cid)
    speeds = joined_motion(speed, front)
    reserved, released = advances(reservation), advances(release)
    routes = []
    for route in frozen['routes']:
        start, end = route['zone_m']
        boundary = route['crossing_m']
        crossing = crossing_samples(front, positions, boundary)
        fmt.require(any(step['time_s'] <= crossing[0][0] + CLOCK_TOLERANCE
                        and step['from_m'] - STEP_POSITION_TOLERANCE_M <= boundary < step['to_m'] for step in reserved),
                    'Original cross-worksheet passage lacks prior Route authority')
        cap = route['fixed_speed_kmh']
        legend = signal_legend(raw['sigpos'], cid, label, route)
        windows = [speed_window(speeds, left, right, cap) for left, right in ((start, boundary), (boundary, end))]
        routes.append({**route, 'crossing_front_bracket_s_m': crossing, 'original_route_indication_legend': legend,
                       'observed_zone_landmarks': [zone_landmark(front, positions, point, frozen) for point in (start, end)],
                       'speed_observation': 'fixed_cap_corroborated' if cap is not None else 'no_fixed_signal_cap_reviewed',
                       'speed_samples_by_worksheet_portion': windows,
                       'release_group_starts': release_boundaries(route, frozen, front, times, reserved, released)})
    return {**frozen, 'routes': routes, 'native_route_protection_verified': True, 'provenance': run.provenance,
            'original_output_sha256': {**run.receipt['output_sha256'], **run.files.hashes}}


class NativeRouteProtectionTools(EvaluateNativeRunTools):
    def verify_protection(self, args):
        try:
            fmt.require(args.course_outcome.course_id == args.protection.course_id and args.course_outcome.terminal_station is not None,
                        'Supply a matching terminal outcome for the original Course')
            output = self.directory(args.output_directory)
            evidence = read_receipts(self.directory(args.evidence_directory), secure_bytes=self.secure_bytes)
            run = FrozenRailwayRun(output, evidence, [args.course_outcome.model_dump(exclude_none=True)], self.secure_bytes)
            root, _ = writer.load_next_compatible(run.dependency(run.settings['paths']['CourseFile']))
            course, = [row for row in map(course_record, catalogs.course_items(root))
                       if row['course_id'] == args.protection.course_id]
            return verify_run(run, course, args.protection)
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_ROUTE_PROTECTION_INVALID', 'Could not verify bound original Route protection',
                           str(exc)[:500]) from exc
