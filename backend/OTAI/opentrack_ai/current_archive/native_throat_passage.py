"""Check monitored passage on a single frozen original cross-worksheet Itinerary."""

from bisect import bisect_left, bisect_right
from itertools import groupby
from typing import Annotated

from pydantic import Field, StrictInt

from ..errors import APIError
from . import catalogs, native_evaluation_formats as fmt, native_occupation_groups as groups, writer
from .catalog_batch_reuse.course_batch import course_record
from .native_interlocking import (
    CLOCK_TOLERANCE, STEP_POSITION_TOLERANCE_M, FrozenRailwayRun, decode_cycles, event_samples, front_position,
    metres_trace,
)
from .native_result_tools import CourseOutcome, EvaluateNativeRunTools, Name
from .native_run_evaluation import basename, read_receipts
from .tools import Input, PathText


TOOL = 'opentrack_verify_native_throat_passage'
EdgeID = Annotated[StrictInt, Field(ge=0, le=2147483647)]
REQUIRED_TRACES = ('st1', 'step1', 'step2')


class WorksheetBoundary(Input):
    from_document: Name
    from_end_id: EdgeID
    to_document: Name
    to_end_id: EdgeID


class GroupMembers(Input):
    document: Name
    group: Name
    edge_ids: Annotated[list[EdgeID], Field(min_length=1, max_length=120)]


class ThroatPassage(Input):
    course_id: Name
    boundaries: Annotated[list[WorksheetBoundary], Field(min_length=1, max_length=32)]
    groups: Annotated[list[GroupMembers], Field(min_length=1, max_length=16)]
    boundary_tolerance_m: Annotated[float, Field(ge=.2, le=10, allow_inf_nan=False)] = 5.0


class VerifyNativeThroatPassage(Input):
    output_directory: PathText
    evidence_directory: PathText
    course_outcome: CourseOutcome
    passage: ThroatPassage


def output_names(spec):
    course = basename(spec.course_id)
    return {f'OT_{course}.{extension}' for extension in REQUIRED_TRACES} | {
        f'OT_Occ_{groups.name(group.group)}.occ' for group in spec.groups
    }


def frozen_passage(project, course, spec):
    """Resolve true connector hops and every monitored Edge in directed path order."""
    fmt.require(course['course_id'] == spec.course_id and course['enabled'] and len(course['itineraries']) == 1,
                'Throat passage requires one enabled Course with one saved Itinerary')
    label, = course['itineraries']
    itinerary, = [item for item in project.dests if catalogs.text(item.contents[1].value) == label]
    nodes, _ = project.dest_view(itinerary)
    path, boundaries = [], []
    axis = origin = course['output_offset_m']
    for first, second in zip(nodes, nodes[1:]):
        edge = project.edge_between(first, second)
        if first[0] != second[0]:
            local = project.related(first)
            remote = project.block_end(local)
            fmt.require(remote[0] == second[0] and project.block_end(remote) == local,
                        'Cross-worksheet route does not have reciprocal native connectors')
            boundaries.append({'from_document': first[0], 'from_end_id': first[1],
                               'to_document': second[0], 'to_end_id': second[1],
                               'connectors': [list(local), list(remote)], 'distance_m': axis})
        end = axis + project.model(edge).contents[9].values[1]
        fmt.require(end > axis, 'Expected a positive physical Edge length')
        path.append((edge, axis, end))
        axis = end
    prescribed = [row.model_dump() for row in spec.boundaries]
    keys = ('from_document', 'from_end_id', 'to_document', 'to_end_id')
    fmt.require(prescribed == [{key: row[key] for key in keys} for row in boundaries],
                'Frozen ordered directed worksheet boundaries differ from the reviewed passage')

    selected = []
    names = [(document, group) for document, root in project.roots.items()
             for group in groups.records(root, document)]
    for ref in spec.groups:
        name = groups.name(ref.group)
        matches = [(document, row) for document, row in names if groups.name_key(row['name']) == groups.name_key(name)]
        fmt.require(len(matches) == 1 and matches[0][0] == ref.document,
                    'Missing or ambiguous frozen worksheet monitor')
        row = matches[0][1]
        fmt.require(row['selected'] and row['saved_document'] == ref.document and row['name'] == name
                    and not row['unresolved_edge_ids'] and len(set(ref.edge_ids)) == len(ref.edge_ids)
                    and sorted(row['edge_ids']) == sorted(ref.edge_ids),
                    'Frozen selected monitor differs from the reviewed original Edge membership')
        keys = {(ref.document, edge_id) for edge_id in ref.edge_ids}
        fmt.require(sum(edge in keys for edge, _, _ in path) == len(keys) and keys <= {edge for edge, _, _ in path},
                    'Each reviewed monitored Edge must be traversed exactly once')
        spans = []
        for monitored, chunk in groupby(path, lambda item: item[0] in keys):
            if monitored:
                block = list(chunk)
                spans.append({'from_m': block[0][1], 'to_m': block[-1][2],
                              'edge_ids': [edge[1] for edge, _, _ in block]})
        selected.append({'document': ref.document, 'group': name, 'spans': spans})
    fmt.require(len({row['group'] for row in selected}) == len(selected), 'Use each saved occupation group once')
    return {'course_id': spec.course_id, 'itinerary': label, 'origin_m': origin, 'terminal_m': axis,
            'boundaries': boundaries, 'groups': selected}


def crossing_samples(points, positions, distance):
    """Return actual bracketing samples, including both sides of a possible plateau."""
    before = bisect_left(positions, distance)
    after = bisect_right(positions, distance)
    fmt.require(before > 0 and after < len(points) and points[before - 1][0] < points[after][0],
                f'No original front movement bracket at {distance:g} m')
    return [list(points[before - 1]), list(points[after])]


def advances(points):
    return [{'time_s': t, 'from_m': lower, 'to_m': upper}
            for (t, lower), (later, upper) in zip(points, points[1:]) if t == later and lower < upper]


def matching_clock(instant, expected):
    return abs(instant - expected) <= CLOCK_TOLERANCE


def group_passage(group, cycles, traces, reserve_steps, release_steps, tolerance):
    """Witness each physical span against a recorded native aggregate occupation cycle."""
    observed = []
    by_span = [[] for _ in group['spans']]
    for cycle in cycles:
        reserve, release = cycle['reservation_s']
        enter, clear = cycle['occupation_s']
        fmt.require(None not in (reserve, release, enter, clear) and reserve <= enter < clear <= release,
                    'Expected a complete positive-duration original occupation cycle')
        first = front_position(traces['st1'], enter)
        last = front_position(traces['st1'], clear)
        covered = [index for index, span in enumerate(group['spans'])
                   if first <= span['from_m'] + tolerance and last >= span['to_m'] - tolerance]
        fmt.require(covered and last > first and abs(first - group['spans'][covered[0]]['from_m']) <= tolerance,
                    'Original occupation front positions do not match the frozen monitored spans')
        start = group['spans'][covered[0]]['from_m']
        authority = [step for step in reserve_steps if matching_clock(step['time_s'], reserve)
                     and step['from_m'] - STEP_POSITION_TOLERANCE_M <= start
                     < step['to_m'] - STEP_POSITION_TOLERANCE_M]
        fmt.require(authority, 'Original monitor reservation lacks a corresponding Route authority advance')
        release_at_clock = [step for step in release_steps if matching_clock(step['time_s'], release)]
        release_evidence = [step for step in release_at_clock
                            if any(step['from_m'] < group['spans'][index]['to_m'] - STEP_POSITION_TOLERANCE_M
                                    and step['to_m'] > group['spans'][index]['from_m'] + STEP_POSITION_TOLERANCE_M
                                    for index in covered)]
        terminal_record = (not release_at_clock and matching_clock(traces['step2'][-1][0], release)
                           and matching_clock(traces['step1'][-1][0], release)
                           and traces['st1'][-1][0] <= release + CLOCK_TOLERANCE
                           and len(event_samples(traces['step2'], release)) == 1)
        fmt.require(release_evidence or terminal_record,
                    'Original monitor release lacks a matching Route advance or simulation-end trace clock')
        for index in covered:
            by_span[index].append(len(observed))
        observed.append({**cycle, 'occupation_front_m': [round(first, 5), round(last, 5)],
                         'native_reservation_advances': authority, 'monitored_span_indices': covered,
                         'native_release_advances': release_evidence, 'simulation_end_release_clock_only': terminal_record})
    fmt.require(all(len(items) == 1 for items in by_span),
                'Original cycles must cover each frozen monitored span exactly once')
    return {**group, 'cycles': observed}


def verify_run(run, course, spec):
    frozen = frozen_passage(run.project, course, spec)
    course_name = basename(spec.course_id)
    traces = {kind: metres_trace(run.original_text(f'OT_{course_name}.{kind}'), kind, course_name, frozen['itinerary'])
              for kind in REQUIRED_TRACES}
    motion = traces['st1']
    positions = [distance for _, distance in motion]
    tolerance = spec.boundary_tolerance_m
    fmt.require(positions == sorted(positions) and abs(positions[0] - frozen['origin_m']) <= tolerance
                and abs(positions[-1] - frozen['terminal_m']) <= tolerance,
                'Original movement is not monotonic on the complete frozen Itinerary')
    reservation, release = (advances(traces[kind]) for kind in ('step1', 'step2'))
    crossings = []
    for row in frozen['boundaries']:
        distance = row['distance_m']
        samples = crossing_samples(motion, positions, distance)
        authorities = [step for step in reservation if step['time_s'] <= samples[0][0] + CLOCK_TOLERANCE
                       and step['from_m'] - STEP_POSITION_TOLERANCE_M <= distance
                       < step['to_m'] - STEP_POSITION_TOLERANCE_M]
        fmt.require(authorities, 'A worksheet boundary lacks an original Route reservation before the passage bracket')
        crossings.append({**row, 'front_bracket_s_m': [[time, round(position, 6)] for time, position in samples],
                          'observed_authority': authorities[0]})
    fmt.require(all(first['front_bracket_s_m'][1][0] <= second['front_bracket_s_m'][0][0]
                    for first, second in zip(crossings, crossings[1:])),
                'Original crossing brackets do not independently establish the worksheet boundary order')
    occupation = []
    for group in frozen['groups']:
        name = group['group']
        cycles = decode_cycles(run.original_text(f'OT_Occ_{name}.occ'), name)
        occupation.append(group_passage(group, [row for row in cycles if row['course_id'] == course_name],
                                        traces, reservation, release, tolerance))
    return {'native_throat_passage_verified': True, 'native_course_completion_verified': True,
            'provenance': run.provenance, 'course_id': course_name, 'itinerary': frozen['itinerary'],
            'boundaries': crossings, 'groups': occupation,
            'original_output_sha256': {**run.receipt['output_sha256'], **run.files.hashes}}


class NativeThroatPassageTools(EvaluateNativeRunTools):
    def verify_passage(self, args):
        try:
            fmt.require(args.course_outcome.course_id == args.passage.course_id
                        and args.course_outcome.terminal_station is not None, 'Supply the matching original Course outcome')
            output = self.directory(args.output_directory)
            evidence = read_receipts(self.directory(args.evidence_directory), secure_bytes=self.secure_bytes)
            run = FrozenRailwayRun(output, evidence, [args.course_outcome.model_dump(exclude_none=True)], self.secure_bytes)
            root, _ = writer.load_next_compatible(run.dependency(run.settings['paths']['CourseFile']))
            course, = [row for row in map(course_record, catalogs.course_items(root))
                       if row['course_id'] == args.passage.course_id]
            return verify_run(run, course, args.passage)
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_THROAT_PASSAGE_INVALID', 'Could not verify the bound original worksheet passage',
                           str(exc)[:500]) from exc
