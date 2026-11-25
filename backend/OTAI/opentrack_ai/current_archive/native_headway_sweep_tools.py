"""Verify integer headway runs and locate a witnessed authority restriction."""

import json
from pathlib import Path
import re
from typing import Annotated

from pydantic import Field, StrictInt

from ..errors import APIError
from ..native_headway_plan import headway_shift, sweep_courses
from ..simulation_evidence import HeadwaySweep
from . import catalogs, native_evaluation_formats as fmt, native_occupation_groups, writer
from .native_headway_tools import NativeHeadwayTools, Run
from .native_interlocking import FrozenInterlocking, authority_handover, metres_trace
from .native_interlocking_tools import Resource
from .native_job_inputs import FrozenJobInputs
from .native_run_evaluation import basename, digest, read_member, read_receipts
from .tools import Input, PathText


EXACT_CLOCKS = 0.011


class ReadSweep(Input):
    job_directories: Annotated[list[PathText], Field(min_length=1, max_length=32)]
    maximum_delay_s: Annotated[StrictInt, Field(ge=0, le=3600)] = 5
    monitored_resources: Annotated[list[Resource], Field(max_length=24)] = Field(default_factory=list)


def measured_section(reservations, releases, planned_departure, actual_departure):
    if len(reservations) < 2:
        return None
    (when, origin), (next_clock, end) = reservations[:2]
    if when != next_clock or end <= origin or not actual_departure <= when < actual_departure + 1:
        return None
    previous = [(t, start, last) for (t, start), (same, last) in zip(releases, releases[1:])
                if t == same and abs(start - origin) <= .2 and abs(last - end) <= .2
                and planned_departure <= t <= when and when - t <= 1]
    if len(previous) != 1:
        return None
    return {'from_m': origin, 'to_m': end, 'leading_release_s': previous[0][0],
            'following_reservation_s': when, 'handover_gap_s': round(when - previous[0][0], 2)}


def minimum_in_grid(measurements, threshold):
    sorted_trials = sorted(measurements, key=lambda sample: sample['planned_departure_headway_s'])
    numbers = [sample['planned_departure_headway_s'] for sample in sorted_trials]
    fmt.require(numbers and numbers == list(range(numbers[0], numbers[-1] + 1)),
                'Sweep must cover every integer without duplicate candidates between its endpoints')
    for sample in sorted_trials:
        sample['passes'] = all(sample[role]['maximum_lateness_s'] <= threshold
                               for role in ('leading', 'following'))
    first = next((i for i, sample in enumerate(sorted_trials) if sample['passes']), None)
    passing = sorted_trials[first] if first is not None else None
    just_below = sorted_trials[first - 1] if first else None
    return numbers, sorted_trials, passing, just_below


def aligned_block_boundary(blocked, passing, blocked_departure, passing_departure, step_s):
    fmt.require(blocked['verified'] and passing['verified'],
                'Both trials need complete, consecutive and exclusive monitored authorities')
    offset = blocked_departure - passing_departure
    leading_release = blocked['leading']['reservation_s'][1]
    observed_reservation = blocked['following']['reservation_s'][0]
    aligned_reservation = passing['following']['reservation_s'][0] + offset
    observed_entry = blocked['following']['occupation_s'][0]
    aligned_entry = passing['following']['occupation_s'][0] + offset
    fmt.require(abs(leading_release - passing['leading']['reservation_s'][1]) <= EXACT_CLOCKS,
                'The leading train must release the shared block at the same time in both trials')
    fmt.require(0 < step_s and -EXACT_CLOCKS <= blocked['handover_gap_s'] <= step_s + EXACT_CLOCKS,
                'The failing follower did not acquire the resource within one simulation step of release')
    fmt.require(aligned_reservation < leading_release - EXACT_CLOCKS
                and aligned_entry + EXACT_CLOCKS < observed_entry,
                'The passing timeline must place reservation before failing-case release and entry earlier after alignment')
    return {'passing_reservation_aligned_s': round(aligned_reservation, 5),
            'failing_following_reservation_s': observed_reservation,
            'passing_entry_aligned_s': round(aligned_entry, 5),
            'failing_following_entry_s': observed_entry,
            'observed_extra_entry_time_s': round(observed_entry - aligned_entry, 5)}


def original_shared_monitors(reference, shared_elements):
    """Find recorded groups that can cover both directed paths on a shared element."""
    by_document = {}
    for span in shared_elements:
        edges = {edge for side in ('leading_spans', 'following_spans')
                 for section in span[side] for edge in section['route_edge_ids']}
        by_document.setdefault(span['document'], []).append(edges)
    monitors = []
    for document, spans in by_document.items():
        for group in native_occupation_groups.records(reference.project.roots[document], document):
            if (group['selected'] and group['saved_document'] == document
                    and f"OT_Occ_{group['name']}.occ" in reference.hashes
                    and any(edges <= set(group['edge_ids']) for edges in spans)):
                monitors.append(Resource(document=document, group=group['name']))
    return monitors


class SweepEvidence(NativeHeadwayTools):
    def original_json(self, folder, name):
        return json.loads(read_member(folder, name, secure_bytes=self.secure_bytes))

    def job(self, root):
        request = self.original_json(root, 'request.json')
        state = self.original_json(root, 'state.json')
        sweep = HeadwaySweep.model_validate(request['headway_sweep']).model_dump()
        candidates = list(range(sweep['minimum_s'], sweep['maximum_s'] + 1))
        fmt.require(request['mode'] == 'batch' and request['scenarios'] == [0]
                    and state['state'] == 'completed' and state['native_simulation_verified']
                    and 1 <= len(candidates) <= 600 and candidates[0] > 0
                    and [trial['planned_departure_headway_s'] for trial in state['runs']] == candidates,
                    'Selected original sweep was not completed and verified for every declared candidate')
        pair = sweep_courses(request['expectations'], sweep)
        source = FrozenJobInputs(self.root, root, self.path(request['project_directory']), request, self.secure_bytes)
        first = root / 'runs' / str(candidates[0])
        anchor = source.reproduce(first / 'project', 0, headway_s=candidates[0])
        expected = read_receipts(first / 'evidence', secure_bytes=self.secure_bytes)
        source.validate_launch(first / 'project', expected, 0, headway_s=candidates[0])
        fmt.require(anchor == expected['input_sha256'],
                    'First original trial in this sweep cannot be reproduced from its sealed source')
        return pair, source, candidates, sweep['comparison_mode']

    def report(self, args):
        try:
            pair, source, baseline, base_blobs, first = None, None, None, None, None
            mode = dispatching_rules = exe_sha256 = None
            trials, visited = [], set()
            for folder in args.job_directories:
                root = self.directory(folder)
                fmt.require(root not in visited, 'Choose each job once')
                visited.add(root)
                names, job_inputs, numbers, job_mode = self.job(root)
                if pair is None:
                    pair, source, mode = names, job_inputs.inventory, job_mode
                    dispatching_rules, exe_sha256 = job_inputs.binding, job_inputs.exe_sha256
                fmt.require(job_inputs.binding == dispatching_rules and job_inputs.exe_sha256 == exe_sha256,
                            'Choose sweeps with the exact same engine fingerprint and OTD rule binding')
                fmt.require(names == pair and job_inputs.inventory == source and mode == job_mode
                            and len(trials) + len(numbers) <= 600,
                            'Choose sweeps with the same mode, bound Courses and exact before-state within 600 trials')
                for gap in numbers:
                    trial = root / 'runs' / str(gap)
                    spec = Run(output_directory=(trial / 'project' / 'output').relative_to(self.root).as_posix(),
                               evidence_directory=(trial / 'evidence').relative_to(self.root).as_posix())
                    evidence = read_receipts(trial / 'evidence', secure_bytes=self.secure_bytes)
                    job_inputs.validate_launch(trial / 'project', evidence, 0, headway_s=gap)
                    config, blobs, observed = self.checked_run(spec, pair, mode, evidence=evidence)
                    fmt.require(observed['planned_departure_headway_s'] == gap, 'Original output gap differs from sealed candidate')
                    if baseline is None:
                        baseline, base_blobs, first = config, blobs, gap
                    fmt.require(config == baseline, 'Original options or fixed project inputs differ across trials')
                    # Both endpoint clocks and the follower's complete native schedule are checked.
                    shifted = headway_shift(base_blobs, {'leading_course_id': pair[0]['course_id'],
                                                        'following_course_id': pair[1]['course_id']}, gap)
                    fmt.require(digest(shifted) == observed['frozen_timetable_sha256'],
                                'Timetable includes a change beyond the exact native follower shift')
                    trials.append(observed)
            numbers, trials, passing, failing = minimum_in_grid(trials, args.maximum_delay_s)
            limit = None
            reason = None
            shared = {}
            if failing is not None and mode == 'same_itinerary':
                try:
                    fmt.require(failing['leading']['maximum_lateness_s'] <= args.maximum_delay_s,
                                'The leading Course also exceeds the timing threshold at the failure boundary')
                    limit = self.limiting_origin(failing, pair, args.monitored_resources)
                except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
                    reason = str(exc)[:400]
            if mode == 'shared_fixed_block':
                reference = self.frozen_interlocking(passing or trials[0], pair)
                leading_spans, following_spans = (reference.routes[row['course_id']]['spans'] for row in pair)
                common = sorted(leading_spans.keys() & following_spans.keys())
                fmt.require(common, 'The different fixed-block Itineraries do not share any saved Safety Element')
                shared = {'shared_safety_elements': [
                    {'document': doc, 'safety_element_id': element, 'leading_spans': leading_spans[(doc, element)],
                     'following_spans': following_spans[(doc, element)]} for doc, element in common
                ], 'observed_shared_block_limitations': [], 'unverified_shared_block_resources': []}
                if failing is not None:
                    monitors = args.monitored_resources or original_shared_monitors(
                        reference, shared['shared_safety_elements'])
                    if monitors:
                        self.shared_limits(shared, reference, failing, passing, pair, monitors,
                                           args.maximum_delay_s, fmt.number(dict(baseline[0])['Step']))
            return {'comparison_mode': mode, 'maximum_delay_s': args.maximum_delay_s,
                    'verified_integer_range_s': [numbers[0], numbers[-1]],
                    'candidate_count': len(numbers), 'source_sha256': source, 'first_reproduced_gap_s': first,
                    'executable_sha256': exe_sha256, 'dispatching_rules': dispatching_rules,
                    'minimum_passing_integer_headway_s': passing['planned_departure_headway_s'] if passing else None,
                    'all_smaller_positive_integer_intervals_checked': bool(passing and numbers[0] == 1),
                    'observed_origin_limitation': limit, 'origin_limitation_unverified_reason': reason,
                    **shared, 'runs': trials}
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_HEADWAY_SWEEP_INVALID', 'Could not verify original headway sweep', str(exc)[:500]) from exc

    def frozen_interlocking(self, trial, pair):
        folder = self.directory(trial['evidence_directory'])
        evidence = read_receipts(folder, secure_bytes=self.secure_bytes)
        return FrozenInterlocking(folder.parent / 'project' / 'output', evidence, pair, self.secure_bytes)

    def shared_limits(self, report, reference, failing, passing, pair, monitors, threshold, step_s):
        suspect = self.frozen_interlocking(failing, pair)
        leader, follower = [row['course_id'] for row in pair]
        for document, group in dict.fromkeys((item.document, item.group) for item in monitors):
            request = {'leading_course': leader, 'following_course': follower,
                       'resource': {'document': document, 'group': group}, 'minimum_gap_s': 0}
            try:
                fmt.require(failing['leading']['maximum_lateness_s'] <= threshold
                            and all(trial[role]['departure_s'] == trial[role]['planned_departure_s']
                                    for trial in (failing, passing) for role in ('leading', 'following')),
                            'The adjacent failure needs on-time departures and excess lateness downstream only')
                blocked = authority_handover(suspect, request, 5)
                clear = authority_handover(reference, request, 5)
                fmt.require(all(blocked[role]['from_m'] > suspect.traces[cid]['st1'][0][1] + .2
                                for role, cid in (('leading', leader), ('following', follower))),
                            'The shared resource must be downstream of both route origins')
                aligned = aligned_block_boundary(blocked, clear, failing['following']['departure_s'],
                                                 passing['following']['departure_s'], step_s)
                report['observed_shared_block_limitations'].append({
                    'case_failing_headway_s': failing['planned_departure_headway_s'],
                    'case_passing_headway_s': passing['planned_departure_headway_s'],
                    'failing_handover': blocked, 'passing_handover': clear, **aligned,
                })
            except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
                report['unverified_shared_block_resources'].append({
                    'document': document, 'group': group, 'reason': str(exc)[:400],
                })
        report['shared_block_original_output_sha256'] = {
            'failing': suspect.files.hashes, 'passing': reference.files.hashes,
        }

    def limiting_origin(self, failed, pair, monitors):
        leader, follower = [item['course_id'] for item in pair]
        event = failed['following']['worst_timing_event']
        clock, actual = (failed['following'][key] for key in ('planned_departure_s', 'departure_s'))
        fmt.require(event['kind'] == 'Dep.' and event['station'] == pair[1]['origin_station']
                    and event['time_s'] == actual and clock < actual,
                    'Original timing failure at the tested boundary is not an origin departure hold')
        railway = self.frozen_interlocking(failed, pair)
        label = failed['itinerary']
        trip = lambda cid, ext: railway.original_text(f'OT_{basename(cid)}.{ext}')
        reservation = metres_trace(trip(follower, 'step1'), 'step1', follower, label)
        release = metres_trace(trip(leader, 'step2'), 'step2', leader, label)
        section = measured_section(reservation, release, clock, actual)
        fmt.require(section is not None, 'Origin reservation has no matching original preceding release')
        stop_message = [message for message in fmt.messages(railway.original_text('OT_Messages.txt'))['diagnostics']
                        if message['course_id'] == follower and message['clock'] == f'{clock // 3600 % 24:02}:{clock // 60 % 60:02}:{clock % 60:02}'
                        and ': Stop at Signal ' in message['message']]
        fmt.require(len(stop_message) == 1, 'Original origin hold needs one signal stop message at the planned departure')
        signal = re.search(r': Stop at Signal (.+?) at ', stop_message[0]['message'])
        fmt.require(signal is not None, 'Unknown original signal-stop message format')
        nodes, _ = railway.project.dest_view(railway.itineraries[label])
        origin_end = railway.project.model(nodes[0])
        signal_model = origin_end.contents[11].value
        fmt.require(writer.kind(signal_model) == 'OTSignalModel'
                    and signal_model.contents[7].value is origin_end
                    and catalogs.text(signal_model.contents[13].value) == signal[1],
                    'Original stop signal does not match the frozen directed origin')
        speed = fmt.series(trip(follower, 'vt'), 'vt', follower)['points']
        positions = dict(metres_trace(trip(follower, 'st1'), 'st1', follower, label))
        waiting = [(t, v) for t, v in speed if clock <= t <= section['following_reservation_s'] + EXACT_CLOCKS]
        fmt.require(len(waiting) >= 2 and abs(waiting[0][0] - clock) <= EXACT_CLOCKS
                    and abs(waiting[-1][0] - section['following_reservation_s']) <= EXACT_CLOCKS
                    and all(v == 0 and abs(positions[t] - section['from_m']) <= .2 for t, v in waiting),
                    'Original zero-speed and position samples must bracket the whole wait')
        origin = positions[waiting[0][0]]
        resources = [{'document': key[0], 'safety_element_id': key[1], **span}
                     for key, spans in railway.routes[follower]['spans'].items() for span in spans
                     if span['from_m'] + origin >= section['from_m'] - .2
                     and span['to_m'] + origin <= section['to_m'] + .2]
        fmt.require(resources, 'No saved Safety Elements match the original starting section')
        monitored = []
        for item in monitors:
            comparison = authority_handover(railway, {'leading_course': leader, 'following_course': follower,
                'resource': item.model_dump(), 'minimum_gap_s': 0}, 5)
            fmt.require(comparison['verified']
                        and abs(comparison['leading']['reservation_s'][1] - section['leading_release_s']) <= EXACT_CLOCKS
                        and abs(comparison['following']['reservation_s'][0] - section['following_reservation_s']) <= EXACT_CLOCKS,
                        'The monitored authority events do not match this release section')
            monitored.append(comparison)
        return {**section, 'boundary_failing_interval_s': failed['planned_departure_headway_s'],
                'origin_signal': signal[1], 'origin_end': nodes[0], 'original_signal_message': stop_message[0],
                'stationary_samples': len(waiting), 'stationary_wait_s': round(waiting[-1][0] - waiting[0][0], 2),
                'saved_safety_elements': resources,
                'monitored_handover': monitored, 'original_output_sha256': railway.files.hashes}


def tool_definitions(root):
    service = SweepEvidence(root)
    return [('opentrack_evaluate_native_headway_sweep',
             'Certify the minimum passing integer headway in a complete original sweep. '
             'Check every native timetable shift and report corroborated origin restrictions or '
             'monitored downstream shared fixed-block authority at the adjacent failure boundary.',
             ReadSweep, service.report)]
