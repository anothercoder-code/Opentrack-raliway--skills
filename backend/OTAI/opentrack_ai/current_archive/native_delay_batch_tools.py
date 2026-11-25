"""Aggregate timetable and resource evidence from isolated original scenario runs."""

import json
from collections import defaultdict
from math import ceil
from pathlib import Path
from statistics import mean, median
from typing import Annotated

from pydantic import Field, StrictBool, StrictInt

from ..errors import APIError
from . import native_delay_plots, native_evaluation_formats as fmt, native_occupation_groups as groups, writer
from .native_headway_tools import normalized_options
from .native_job_inputs import FrozenJobInputs
from .native_monitoring_formats import occupation_statistics
from .native_result_tools import EvaluateNativeRunTools, Name
from .native_run_evaluation import (
    OutputFiles, bound_run, digest, evaluate_run, plan, read_member, read_receipts,
)
from .project_workflow.relocation import relocate_destination_catalog
from .runfile_parameters import time_seconds
from .tools import Input, PathText


class Resource(Input):
    document: Name
    name: Name


class SummarizeBatch(Input):
    job_directory: PathText
    resources: Annotated[list[Resource], Field(max_length=24)] = Field(default_factory=list)
    latest_arrival_s: Annotated[StrictInt, Field(
        ge=0, le=86400, description='Maximum lateness at the terminal relative to its planned arrival, in seconds',
    )] = 180
    original_delay_plots: StrictBool = False
    confidence_level: Annotated[float, Field(ge=.5, lt=1, allow_inf_nan=False)] = .95


def distribution(samples):
    ordered = sorted(samples)
    return {
        'samples': len(ordered), 'minimum': ordered[0], 'maximum': ordered[-1],
        'mean': mean(ordered), 'median': median(ordered), 'p95_nearest_rank': ordered[ceil(0.95 * len(ordered)) - 1],
    } if ordered else None


def union_seconds(spans, window):
    # Use observed wall time for the resource, even where two members are occupied together.
    lower, upper = window
    merged_end = lower
    seconds = 0.0
    for first, last in sorted(spans):
        fmt.require(lower - 0.011 <= first <= last <= upper + 0.011,
                    'Occupation clock is outside the frozen run window')
        first, last = max(first, lower), min(last, upper)
        seconds += max(0.0, last - max(merged_end, first))
        merged_end = max(merged_end, last)
    return round(seconds, 2)


def timing_samples(evaluation, threshold):
    result = []
    missing = []
    for course in evaluation['courses']:
        if not course['completion_verified']:
            continue
        departure, terminal = course['origin_event'], course['last_observed_event']
        if departure.get('planned_s') is None or terminal.get('planned_s') is None:
            missing.append(course['course_id'])
            continue
        lateness = terminal['time_s'] - terminal['planned_s']
        result.append({'course_id': course['course_id'], 'departure_delay_s': departure['time_s'] - departure['planned_s'],
                       'terminal_delay_s': lateness, 'terminal_within_threshold': lateness <= threshold})
    return result, missing


class NativeDelayBatch(EvaluateNativeRunTools):
    def examine_scenario(self, job, scenario, run_file, expectation, requested, window_threshold, source,
                         include_original_plots=False):
        trial = job / 'runs' / str(scenario)
        frozen_dir = trial / 'evidence'
        output = trial / 'project' / 'output'
        evidence = read_receipts(frozen_dir, secure_bytes=self.secure_bytes)
        fmt.require(evidence.get('outcome') == 'exited' and evidence['exit_code'] == 0,
                    'Original scenario process did not exit successfully')
        source.validate_launch(output.parent, evidence, scenario)
        started, names, sealed, provenance, frozen = bound_run(evidence, output, self.secure_bytes)
        fmt.require(provenance['executable_matches'] and provenance['archive_hashes_verified'],
                    'Scenario is missing sealed original inputs or executable')
        manifest = evidence['input_sha256']
        root = frozen['project_root']
        fmt.require(root == output.parent and frozen_dir / 'inputs' == (frozen_dir / 'inputs').resolve(strict=True),
                    'Scenario paths do not identify this original job')

        def frozen_member(name):
            blob = read_member(frozen_dir / 'inputs', name, nested=True, secure_bytes=self.secure_bytes)
            fmt.require(digest(blob) == manifest[name], f'Frozen member changed: {name}')
            return blob

        options = normalized_options(frozen_member(run_file), root)
        values = dict(options)
        fmt.require(values.get('Delay Scenario') == str(scenario), 'Frozen Delay Scenario differs from job trial')
        window = tuple(time_seconds(values[f'{kind} Time'].encode('ascii'),
                                    values.get(f'{kind} Day Offset', '0').encode('ascii')) for kind in ('Start', 'Stop'))
        fmt.require(window[0] < window[1], 'Invalid frozen original run window')
        dest_file = values['DestInfoFile']
        normalized_dest, _ = relocate_destination_catalog(
            frozen_member(dest_file), source=root.as_posix(), target='D:/OpenTrackBatchEvidence',
            documents=[value for key, value in options if key == 'Infrastructure Document'],
        )
        persistent = {key: value for key, value in manifest.items() if key not in {run_file, dest_file}}
        fmt.require(all(source.effective_inventory[name] == persistent[name] for name in persistent
                        if name != values['TimetableFile']), 'Scenario modified a persistent source archive')
        config = ([item for item in options if item[0] != 'Delay Scenario'], persistent, digest(normalized_dest))
        evaluation = evaluate_run(output, expectation, evidence, secure_bytes=self.secure_bytes)
        fmt.require(evaluation['provenance']['protocol_matches_frozen_run']
                    and evaluation['output_sha256'].items() <= sealed.items(),
                    'Original result files lack launcher seals or protocol provenance')
        protocol = evaluation['protocol']
        label = str(protocol['delay_scenario']).casefold()
        fmt.require(label in ({'0', 'none'} if scenario == 0 else {str(scenario)}),
                    'Original protocol did not report the requested scenario')

        files = OutputFiles(output, started, names, sealed, self.secure_bytes)
        results = self.occupation_rows(requested, options, frozen_member, files, window)
        protocol_groups = {row['name']: row for row in protocol['occupation_statistics']}
        for row in results['rows']:
            observed = row['native_statistics']
            original = protocol_groups.get(row['name'])
            if observed is not None and original is not None:
                fmt.require(observed['occupation_count'] == original['count']
                            and observed['average_reservation_percentage'] == original['mean_reservation_pct'],
                            'Original occupation protocol disagrees with its statistics file')
        timing, missing = timing_samples(evaluation, window_threshold)
        plots = {}
        if include_original_plots and evaluation['native_run_verified']:
            plots['original_delay_plots'] = native_delay_plots.verified_plots(
                files, evaluation, frozen_member(values['StationFile']), scenario,
            )
        return config, {
            'scenario': scenario, 'all_selected_courses_verified': evaluation['native_run_verified'],
            'course_count_verified': evaluation['verified_course_count'],
            'course_timings': timing, 'completed_courses_missing_planned_times': missing,
            'errors': evaluation['errors'],
            'simulation_window_s': window, 'native_occupation_time_slot': results['slot'], 'resources': results['rows'],
            'input_sha256': manifest, 'output_sha256': {**evaluation['output_sha256'], **files.hashes}, **plots,
        }

    @staticmethod
    def occupation_rows(requested, options, frozen_member, files, window):
        if not requested:
            return {'rows': [], 'slot': None}
        matches = {}
        for key, relative in options:
            if key != 'Infrastructure Document':
                continue
            document = Path(relative).stem
            root, _ = writer.load_next_compatible(frozen_member(relative))
            for record in groups.records(root, document):
                name = record['name']
                if groups.name_key(name) not in requested:
                    continue
                identity = groups.name_key(name)
                fmt.require(identity not in matches and requested[identity] == (document, name)
                            and record['selected'] and record['saved_document'] == document,
                            'Original monitoring group is ambiguous, unselected or on a different worksheet')
                _, inventory = groups.models(root)
                groups.verify_edges(inventory, record['edge_ids'])
                matches[identity] = record['edge_ids']
        fmt.require(matches.keys() == requested.keys(), 'Could not bind all monitoring groups to frozen worksheets')

        def sealed(name):
            fmt.require(name in files.expected_hashes, f'Unknown or unsealed original result {name}')
            return files.read(name)

        actual = occupation_statistics(sealed('OT_OccStatistics.txt'))
        statistics = {row['name']: row for row in actual['records']}
        rows = []
        for identity, (document, name) in requested.items():
            native = statistics.get(name)
            filename = f'OT_Occ_{name}.occ'
            item = {'document': document, 'name': name, 'edge_ids': matches[identity],
                    'native_statistics': native, 'reservation_union_s': None, 'occupation_union_s': None}
            if filename in files.names:
                events = fmt.occupations(sealed(filename))
                fmt.require(all(event['resource'] == name for event in events), 'Occupation resource does not match frozen group')
                cycles, unpaired = fmt.occupation_intervals(events)
                item.update(complete_cycles=len(cycles), unpaired_events=unpaired)
                if not unpaired and all(event['time_s'] is not None for event in events):
                    for phase in ('reservation', 'occupation'):
                        item[f'{phase}_union_s'] = union_seconds([cycle[f'{phase}_s'] for cycle in cycles], window)
            rows.append(item)
        return {'rows': rows, 'slot': actual['time_slot']}

    def summarize(self, args):
        job = self.directory(args.job_directory)
        try:
            request = json.loads(read_member(job, 'request.json', secure_bytes=self.secure_bytes))
            state = json.loads(read_member(job, 'state.json', secure_bytes=self.secure_bytes))
            scenarios = request['scenarios']
            fmt.require(request['mode'] == 'batch' and 2 <= len(scenarios) <= 201
                        and len(set(scenarios)) == len(scenarios)
                        and all(type(number) is int and 0 <= number <= 200 for number in scenarios)
                        and sum(scenario > 0 for scenario in scenarios) >= 2,
                        'Choose a batch with two or more distinct original random scenarios 1–200')
            fmt.require(state['state'] == 'completed' and [row['scenario'] for row in state['runs']] == scenarios,
                        'The declared native batch must have reached terminal state for every scenario')
            expectation = request['expectations']
            selected = plan(expectation)
            fmt.require(all(course.get('origin_station') and course.get('terminal_station') for course in selected)
                        and len(scenarios) * (len(selected) + len(args.resources)) <= 20000,
                        'Give named origin and terminal for each expected Course within the evidence budget')
            requested = {groups.name_key(groups.name(item.name)): (item.document, item.name) for item in args.resources}
            fmt.require(len(requested) == len(args.resources), 'Select distinct named monitoring groups')
            run_file = request['run_file']
            source = FrozenJobInputs(self.root, job, self.path(request['project_directory']), request, self.secure_bytes)

            first = scenarios[0]
            expected_anchor = source.reproduce(job / 'runs' / str(first) / 'project', first)
            config = None
            observed = []
            for scenario in scenarios:
                signature, result = self.examine_scenario(job, scenario, run_file, expectation, requested,
                                                          args.latest_arrival_s, source, args.original_delay_plots)
                fmt.require(config is None or signature == config, 'Frozen scenario settings or inputs differ beyond relocation and Delay Scenario')
                if scenario == first:
                    fmt.require(result['input_sha256'] == expected_anchor,
                                'Could not reproduce the first original trial from its sealed job source')
                config = signature
                observed.append(result)
            verified = [row for row in observed if row['scenario'] > 0 and row['all_selected_courses_verified']]
            if verified:
                time_slot = verified[0]['native_occupation_time_slot']
                fmt.require(all(row['native_occupation_time_slot'] == time_slot for row in verified),
                            'Original occupation time-slot settings differ across numbered trials')
            summary = aggregate(args.latest_arrival_s, job.relative_to(self.root).as_posix(), observed, verified)
            if args.original_delay_plots:
                summary['original_delay_plot_summary'] = native_delay_plots.named_summary(
                    observed, args.latest_arrival_s, args.confidence_level, distribution,
                )
            return {**summary, 'source_sha256': source.inventory, 'first_scenario_reproduced_from_source': first,
                    'executable_sha256': source.exe_sha256, 'dispatching_rules': source.binding}
        except (ValueError, OSError, KeyError, IndexError, TypeError, OverflowError) as exc:
            raise APIError('NATIVE_DELAY_BATCH_INVALID', 'Could not summarize sealed original delay scenarios',
                           str(exc)[:500]) from exc


def aggregate(threshold, path, observed, verified):
    timings = defaultdict(list)
    resources = defaultdict(list)
    for case in verified:
        for row in case['course_timings']:
            timings[row['course_id']].append(row)
        for row in case['resources']:
            resources[row['document'], row['name']].append(row)
    return {
        'job_directory': path, 'terminal_lateness_threshold_s': threshold,
        'verified_numbered_scenarios': [row['scenario'] for row in verified],
        'excluded_numbered_scenarios': [row['scenario'] for row in observed
                                        if row['scenario'] > 0 and row not in verified],
        'observations': observed,
        'course_statistics': [summarize_course(course, rows) for course, rows in sorted(timings.items())],
        'resource_statistics': [summarize_resource(document, name, rows)
                                for (document, name), rows in sorted(resources.items())],
    }


def summarize_course(course, rows):
    within = sum(row['terminal_within_threshold'] for row in rows)
    return {
        'course_id': course, 'departure_delay_s': distribution([row['departure_delay_s'] for row in rows]),
        'terminal_delay_s': distribution([row['terminal_delay_s'] for row in rows]),
        'within_threshold_count': within, 'within_threshold_pct': 100 * within / len(rows),
        'timing_sample_count': len(rows),
    }


def summarize_resource(document, name, rows):
    native = [row['native_statistics'] for row in rows if row['native_statistics'] is not None]
    summary = {
        'document': document, 'name': name, 'verified_trials': len(rows),
        'native_occupation_count': distribution([row['occupation_count'] for row in native]),
        'native_average_reservation_pct': distribution([row['average_reservation_percentage'] for row in native]),
    }
    for phase in ('reservation', 'occupation'):
        column = f'{phase}_union_s'
        samples = [row[column] for row in rows if row[column] is not None]
        summary[column] = distribution(samples)
        summary[f'{phase}_total_s'] = round(sum(samples), 2) if samples else None
    return summary


def tool_definitions(root):
    service = NativeDelayBatch(root)
    return [('opentrack_summarize_native_delay_batch',
             'Recheck a completed launcher-sealed batch of original delay scenarios and aggregate observed '
             'Course punctuality and track occupation. Optionally corroborate the nine original delay plots and '
             'summarize fractional terminal lateness and conditional scenario-level confidence. '
             'Scenario zero is a separate control. Read only.',
             SummarizeBatch, service.summarize)]
