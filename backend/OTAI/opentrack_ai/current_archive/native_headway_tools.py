"""Compare planned departure intervals using sealed original simulation runs."""

from pathlib import Path
from typing import Annotated

from pydantic import Field

from ..errors import APIError
from ..native_headway_plan import course_pair
from . import native_evaluation_formats as fmt
from .catalog_batch_reuse.catalog_batch import apply_batch
from .native_following import trajectory
from .native_result_tools import CourseOutcome, EvaluateNativeRunTools, Name
from .native_run_evaluation import (
    OutputFiles, digest, evaluate_run, frozen_configuration, read_member, read_receipts,
)
from .prepare_contract.auxiliary import records
from .project_workflow.relocation import relocate_destination_catalog
from .tools import Input, PathText


CATALOG_FILES = {
    'depot': 'DepotFile', 'trains': 'TrainFile', 'courses': 'CourseFile',
    'dest': 'DestInfoFile', 'stations': 'StationFile', 'timetable': 'TimetableFile',
}
PATH_RECORDS = frozenset(CATALOG_FILES.values()) | {
    'Infrastructure Document', 'Train Diagram Document', 'Document Set Document', 'OutputPath',
}


class Run(Input):
    output_directory: PathText
    evidence_directory: PathText


class SpacingCourse(CourseOutcome):
    origin_station: Name
    terminal_station: Name
    distance_m: Annotated[float, Field(gt=0, allow_inf_nan=False)]


class Study(Input):
    leading_course: SpacingCourse
    following_course: SpacingCourse
    runs: Annotated[list[Run], Field(min_length=2, max_length=32)]
    maximum_delay_s: Annotated[int, Field(ge=0, le=3600, strict=True)] = 5


def normalized_options(run, root):
    options = []
    for key, value, _ in records(run):
        if key is None:
            continue
        if key in PATH_RECORDS:
            path = Path(value)
            fmt.require(path.is_relative_to(root), 'Run path is outside the frozen project')
            value = path.relative_to(root).as_posix()
        options.append((key, value))
    return options


def measure_course(course):
    departure = course['origin_event']
    terminal = course['last_observed_event']
    timing = [event for event in course['events'] if event.get('planned_s') is not None]
    fmt.require(timing and departure in timing and terminal in timing,
                'Both endpoints require native planned and actual timing')
    worst = max(timing, key=lambda event: event['time_s'] - event['planned_s'])
    return {
        'departure_s': departure['time_s'], 'planned_departure_s': departure['planned_s'],
        'arrival_s': terminal['time_s'], 'maximum_lateness_s': worst['time_s'] - worst['planned_s'],
        'worst_timing_event': worst,
    }


class NativeHeadwayTools(EvaluateNativeRunTools):
    def checked_run(self, spec, pair, mode='same_itinerary', *, evidence=None):
        if evidence is None:
            evidence = read_receipts(self.directory(spec.evidence_directory), secure_bytes=self.secure_bytes)
        output = self.directory(spec.output_directory)
        manifest = evidence['input_sha256']
        run_files = [member for member in manifest if member.lower().endswith('.run')]
        fmt.require(len(run_files) == 1, 'Headway comparison requires one frozen run file')
        run_file, = run_files
        inputs = evidence['evidence_directory'] / 'inputs'

        def verified_input(member):
            blob = read_member(inputs, member, nested=True, secure_bytes=self.secure_bytes)
            fmt.require(digest(blob) == manifest[member], f'Frozen input changed for {member}')
            return blob

        results = evaluate_run(output, {'courses': pair}, evidence, secure_bytes=self.secure_bytes)
        fmt.require(results['native_run_verified'],
                    f"Both Courses must complete in every original simulation: {results['errors']}")
        fmt.require(results['output_sha256'].items() <= evidence['output_sha256'].items(),
                    'Comparison requires every used result to be sealed by the original runner')
        run_blob = verified_input(run_file)
        config = frozen_configuration(run_blob, run_file, evidence, manifest)
        options = normalized_options(run_blob, config['project_root'])
        fmt.require(dict(options).get('Delay Scenario') == '0', 'Use native Delay Scenario 0 for the comparison')
        bindings = {key: Path(config['paths'][option]).relative_to(config['project_root']).as_posix()
                    for key, option in CATALOG_FILES.items()}
        blobs = {key: verified_input(member) for key, member in bindings.items()}
        ids = [item['course_id'] for item in pair]
        fmt.require(sorted(results['protocol']['used_courses']) == sorted(ids),
                    'Only the two selected Courses may be in the original execution')
        lead, follow = course_pair(blobs['courses'], ids, mode)
        labels = {item['course_id']: item['itineraries'][0] for item in (lead, follow)}
        files = OutputFiles(output, None, set(evidence['output_files']), evidence['output_sha256'], self.secure_bytes)
        for course_id, label in labels.items():
            trajectory(files, course_id, label)
        first, second = map(measure_course, results['courses'])
        planned = second['planned_departure_s'] - first['planned_departure_s']
        actual = second['departure_s'] - first['departure_s']
        fmt.require(planned > 0 and (mode == 'shared_fixed_block' or actual > 0),
                    'Require an ordered planned pair, and the same departure order in a same-Itinerary run')
        unchanged = {member: value for member, value in manifest.items()
                     if member not in {run_file, bindings['timetable']}}
        normalized_destinations, _ = relocate_destination_catalog(
            blobs['dest'], source=config['project_root'].as_posix(), target='D:/OpenTrackHeadwayRoot',
            documents=[value for key, value in options if key == 'Infrastructure Document'],
        )
        unchanged[bindings['dest']] = digest(normalized_destinations)
        return (options, unchanged, bindings), blobs, {
            'planned_departure_headway_s': planned, 'actual_departure_headway_s': actual,
            'leading': first, 'following': second,
            **({'itinerary': labels[ids[0]]} if mode == 'same_itinerary' else {'itineraries': labels}),
            'spacing_mode': lead['spacing_mode'], 'evidence_directory': spec.evidence_directory,
            'frozen_timetable_sha256': manifest[bindings['timetable']],
            'output_sha256': results['output_sha256'],
        }

    def compare(self, args):
        pair = [item.model_dump(exclude_none=True) for item in (args.leading_course, args.following_course)]
        try:
            fmt.require(pair[0]['course_id'] != pair[1]['course_id']
                        and all(pair[0][key] == pair[1][key] for key in ('origin_station', 'terminal_station', 'distance_m')),
                        'Use distinct Courses with the same exact endpoints and length')
            baseline, base_blobs, base = self.checked_run(args.runs[0], pair)
            measurements = [base]
            seen = {base['planned_departure_headway_s']}
            for spec in args.runs[1:]:
                configuration, _, sample = self.checked_run(spec, pair)
                fmt.require(configuration == baseline, 'Run settings, other members or catalog paths differ')
                planned = sample['planned_departure_headway_s']
                fmt.require(planned not in seen, 'Each tested departure interval must be distinct')
                seen.add(planned)
                shift = planned - base['planned_departure_headway_s']
                shifted, _ = apply_batch(base_blobs, [{
                    'kind': 'shift_timetable_rows', 'course_ids': [pair[1]['course_id']], 'seconds': shift,
                }])
                fmt.require(digest(shifted['timetable']) == sample['frozen_timetable_sha256']
                            and sample['leading']['planned_departure_s'] == base['leading']['planned_departure_s'],
                            'Only the exact native planned shift of the follower timetable may differ')
                measurements.append(sample)
            measurements.sort(key=lambda sample: sample['planned_departure_headway_s'])
            for sample in measurements:
                sample['passes'] = all(sample[role]['maximum_lateness_s'] <= args.maximum_delay_s
                                       for role in ('leading', 'following'))
            passing = [sample['planned_departure_headway_s'] for sample in measurements if sample['passes']]
            return {
                'maximum_delay_s': args.maximum_delay_s,
                'minimum_passing_tested_headway_s': min(passing, default=None),
                'continuous_minimum_or_critical_block_verified': False,
                'runs': measurements,
            }
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_HEADWAY_INVALID', 'Could not compare bound original headway runs',
                           str(exc)[:500]) from exc


def tool_definitions(root):
    from .native_headway_trace import TraceStudy, TraceTools
    from .native_station_throughput import ThroughputStudy, ThroughputTools

    service = NativeHeadwayTools(root)
    trace = TraceTools(root)
    throughput = ThroughputTools(root)
    return [('opentrack_compare_native_headway_runs',
             'Compare distinct planned departure gaps in completed sealed original simulations. '
             'Only a uniform planned shift of the follower timetable may vary. Report the smallest '
             'tested gap passing the timing threshold. Read-only comparison of the supplied runs.',
             Study, service.compare),
            ('opentrack_measure_native_headway_trace',
             'Measure timestamp and distance rounding bounds on one common directed Itinerary in sealed original runs. '
             'Report sampled train passage, reservation and release frontiers, frozen spacing modes and optional '
             'native occupation-group handovers. Does not launch the simulator.',
             TraceStudy, trace.measure),
            ('opentrack_measure_native_station_throughput',
             'Reconcile all original Course timetable events against sealed Station Statistics. '
             'Report station and terminal event counts and measured rolling peaks in absolute time windows. '
             'No new original execution or capacity extrapolation.',
             ThroughputStudy, throughput.measure)]
