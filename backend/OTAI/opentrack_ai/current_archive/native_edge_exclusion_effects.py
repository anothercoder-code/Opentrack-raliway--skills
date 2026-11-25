"""Verify physical movement and reservation-only protection in original runs."""

from pathlib import Path
from typing import Annotated

from pydantic import Field

from ..errors import APIError
from . import native_evaluation_formats as fmt, native_exclusion, writer
from .native_headway_tools import Run, SpacingCourse, normalized_options
from .native_interlocking import CLOCK_TOLERANCE, FrozenInterlocking, overlap_seconds
from .native_result_tools import EvaluateNativeRunTools, Name
from .native_run_evaluation import basename, digest, read_receipts
from .project_workflow.relocation import relocate_destination_catalog
from .saved_edge_exclusion import set_edge_exclusion
from .tools import Input


EdgeID = Annotated[int, Field(ge=0, strict=True)]


class CompareNativeEdgeExclusion(Input):
    control: Run
    exclusion: Run
    document: Name
    source_edge_id: EdgeID
    target_edge_id: EdgeID
    source_group: Name
    target_group: Name
    source_course: SpacingCourse
    target_course: SpacingCourse
    movement_boundary_tolerance_m: Annotated[float, Field(ge=0.2, le=25, allow_inf_nan=False)] = 5.0


def frozen_inputs(run, evidence):
    hashes = evidence['input_sha256']
    configurations = [name for name in hashes if name.lower().endswith('.run')]
    fmt.require(len(configurations) == 1, 'Expected one original .run member')
    configuration, = configurations
    root = run.settings['project_root']
    options = normalized_options(run.dependency(str(root / configuration)), root)
    fmt.require([value for key, value in options if key == 'Delay Scenario'] == ['0']
                and run.receipt['protocol']['delay_scenario'] == 'None',
                'Controlled comparison requires original random delays disabled in both runs')
    sheets = [value for key, value in options if key == 'Infrastructure Document']
    paths = {Path(name).stem: (root / name).as_posix() for name in sheets}
    dest_path = run.settings['paths']['DestInfoFile']
    dest = run.dependency(dest_path)
    canonical, _ = relocate_destination_catalog(dest, source=root.as_posix(),
        target='D:/OpenTrackEdgeExclusionComparison', documents=sheets)
    replaced = {configuration, Path(dest_path).relative_to(root).as_posix(), *sheets}
    unchanged = {name: sha for name, sha in hashes.items() if name not in replaced}
    return {
        'common': (evidence['executable_sha256'], configuration, options, digest(canonical), unchanged),
        'paths': paths, 'sheets': {key: run.dependency(path) for key, path in paths.items()}, 'dest': dest,
    }


def check_only_link(control, exclusion, before, after, document, source, target):
    fmt.require(before['common'] == after['common'],
                'Original run settings, executable, destination graph or non-worksheet inputs differ')
    fmt.require(before['sheets'].keys() == after['sheets'].keys() and document in before['sheets'],
                'Original worksheet identities differ or the selected worksheet is missing')
    fmt.require([key for key, blob in before['sheets'].items() if blob != after['sheets'][key]] == [document],
                'The selected original worksheet must be the only changed worksheet')
    expected, written = set_edge_exclusion(before['sheets'], before['paths'], before['dest'], document, {
        'action': 'set_edge_exclusion', 'edge_id': source, 'target_edge_id': target,
        'expected_target_edge_id': None, 'expected_target_source_edge_id': None,
    })
    exact_bytes = expected[document] == after['sheets'][document]
    fmt.require(exact_bytes or writer.fingerprint(writer.load_next_compatible(expected[document])[0])
                == writer.fingerprint(exclusion.project.roots[document]),
                'Treatment worksheet differs from the isolated reciprocal Edge exclusion write')
    fmt.require(all(control.receipt['protocol'][key] == exclusion.receipt['protocol'][key]
                    for key in ('used_courses', 'listed_incidents')),
                'Original protocols disagree on used Courses or active Incidents')
    return {
        'document': document, 'source_edge_id': source, 'target_edge_id': target,
        'only_original_exclusion_references_changed': True, 'exact_replay_bytes_match': exact_bytes,
        'control_worksheet_sha256': digest(before['sheets'][document]),
        'exclusion_worksheet_sha256': digest(after['sheets'][document]),
        'replayed_worksheet_sha256': digest(expected[document]),
        'saved_movement_count_checked': written['movement_count_checked'],
    }


def verified_traversals(run, courses, references, edges, tolerance):
    traversals = [run.traversal(course, reference, tolerance) for course, reference in zip(courses, references)]
    keys = [(row['document'], row['safety_element_id']) for row in traversals]
    fmt.require(keys[0] != keys[1], 'Monitors must identify two separate frozen Safety Elements')
    fmt.require(all(edge in row['route_edge_ids'] for edge, row in zip(edges, traversals)),
                'Original movements must physically traverse the exact selected Edges')
    fmt.require(all(key not in run.routes[course]['spans'] for course, key in zip(courses, reversed(keys))),
                'The selected Courses must each traverse only their respective monitored Safety Element')
    return traversals


def protection_effect(source, target, before, after, control_cycles, treatment_cycles):
    fmt.require(not any(row['course_id'] == source for row in control_cycles),
                'The source Course already has a native target authority without the selected link')
    added = [row for row in treatment_cycles if row['course_id'] == source]
    fmt.require(len(added) == 1 and added[0]['occupation_s'] == [None, None]
                and None not in added[0]['reservation_s'],
                'Expected one added original target reservation-only cycle for the source Course')
    protected, = added
    linked_start, linked_end = protected['reservation_s']
    fmt.require(linked_start < linked_end and all(abs(a - b) <= CLOCK_TOLERANCE
                for a, b in zip(protected['reservation_s'], after[0]['reservation_s'])),
                'Added target protection does not match the original physical source authority clocks')
    fmt.require(all(None not in row['reservation_s'] for row in treatment_cycles),
                'Treatment target occupation trace contains an incomplete original authority cycle')
    ordered = sorted(treatment_cycles, key=lambda row: (row['reservation_s'], row['course_id']))
    consecutive = any(a == protected and b['course_id'] == target and b['reservation_s'] == after[1]['reservation_s']
                      for a, b in zip(ordered, ordered[1:]))
    handover = round(after[1]['reservation_s'][0] - linked_end, 5)
    delay = round(after[1]['reservation_s'][0] - before[1]['reservation_s'][0], 5)
    physical_before, physical_after = (overlap_seconds(a['occupation_s'], b['occupation_s']) for a, b in (before, after))
    baseline_reservation = overlap_seconds(before[0]['reservation_s'], before[1]['reservation_s'])
    earlier_overlap = overlap_seconds(protected['reservation_s'], before[1]['reservation_s'])
    conflicts = native_exclusion.overlaps(treatment_cycles, 'reservation_s')
    source_unchanged = all(before[0][field] == after[0][field] for field in ('reservation_s', 'occupation_s'))
    checks = {
        'source_movement_clocks_unchanged': source_unchanged,
        'control_occupation_overlap_observed': physical_before > CLOCK_TOLERANCE,
        'treatment_occupation_overlap_removed': physical_after == 0,
        'control_target_authority_overlaps_linked_protection': earlier_overlap > CLOCK_TOLERANCE,
        'treatment_target_reservation_delayed': delay > CLOCK_TOLERANCE,
        'protected_then_target_authorities_consecutive': consecutive and handover >= 0,
        'no_treatment_target_authority_overlap': not conflicts['overlapping_cycle_count'],
    }
    return {
        'native_direct_exclusion_verified': all(checks.values()), 'checks': checks,
        'original_target_protection_only_cycle': protected, 'target_authority_handover_s': handover,
        'target_reservation_delay_s': delay, 'control_physical_overlap_s': physical_before,
        'exclusion_physical_overlap_s': physical_after, 'control_cross_resource_reservation_overlap_s': baseline_reservation,
        'control_target_overlap_with_treatment_protection_s': earlier_overlap,
        'exclusion_target_authority_trace': conflicts,
    }


def target_observations(before, after, span, protection, tolerance):
    protect_start, _ = protection['reservation_s']
    reserve, _ = span['reservation_s']
    trace = after['distance']
    earliest_position = trace['first'][1] * (1000 if trace['units'][1] == 'km' else 1609.344)
    stopped = [row for row in after['stationary_intervals']
               if protect_start <= row['start_s'] < reserve
               and abs(row['end_s'] - reserve) <= CLOCK_TOLERANCE
               and earliest_position < row['distance_reference_m'] < span['from_m'] - tolerance]
    stationary = None
    if len(stopped) == 1:
        row, = stopped
        stationary = {**row, 'duration_s': round(row['duration_s'], 5),
                      'distance_reference_m': round(row['distance_reference_m'], 5),
                      'control_stop_at_same_position': any(
                          abs(previous['distance_reference_m'] - row['distance_reference_m']) <= tolerance
                          for previous in before['stationary_intervals'])}
    return {
        'verified_approach_stop_ending_at_target_authority': stationary,
        'original_terminal_event_change_s': after['last_observed_event']['time_s']
                                             - before['last_observed_event']['time_s'],
    }


def analyze(control, exclusion, args, inputs):
    document = basename(args['document'])
    groups = [args['source_group'], args['target_group']]
    edges = [args['source_edge_id'], args['target_edge_id']]
    courses = [args[side]['course_id'] for side in ('source_course', 'target_course')]
    fmt.require(len(set(courses)) == len(set(edges)) == len(set(groups)) == 2,
                'Select distinct source and target Courses, Edges and monitor groups')
    before, after = inputs
    change = check_only_link(control, exclusion, before, after, document, *edges)
    refs = [{'document': document, 'group': group} for group in groups]
    tolerance = args['movement_boundary_tolerance_m']
    prior, linked = [verified_traversals(run, courses, refs, edges, tolerance) for run in (control, exclusion)]
    target_cycles = [run.resource(refs[1])[1] for run in (control, exclusion)]
    effect = protection_effect(*courses, prior, linked, *target_cycles)
    target_results = [next(row for row in run.receipt['courses'] if row['course_id'] == courses[1])
                      for run in (control, exclusion)]
    observations = target_observations(*target_results, linked[1], effect['original_target_protection_only_cycle'], tolerance)
    return {**effect, 'saved_change': change, 'target_observations': observations,
            'source_course_id': courses[0], 'target_course_id': courses[1],
            'control': run_result(control, prior), 'exclusion': run_result(exclusion, linked),
            'scope': 'One added same-worksheet direct Edge exclusion with separate witnessed physical traversals.'}


def run_result(run, traversals):
    return {
        'traversals': traversals, 'provenance': run.provenance,
        'output_sha256': {**run.receipt['output_sha256'], **run.files.hashes},
        'original_used_course_count': len(run.receipt['protocol']['used_courses']),
        'independently_verified_courses': run.receipt['courses'],
    }


class NativeEdgeExclusionTools(EvaluateNativeRunTools):
    def compare(self, args):
        try:
            request = args.model_dump(exclude_none=True)
            expectations = [request['source_course'], request['target_course']]
            runs = []
            inputs = []
            for spec in (args.control, args.exclusion):
                evidence = read_receipts(self.directory(spec.evidence_directory), secure_bytes=self.secure_bytes)
                run = FrozenInterlocking(self.directory(spec.output_directory), evidence, expectations, self.secure_bytes)
                runs.append(run)
                inputs.append(frozen_inputs(run, evidence))
            return analyze(*runs, request, inputs)
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_EDGE_EXCLUSION_INVALID', 'Could not compare bound original Edge exclusion effects',
                           str(exc)[:500]) from exc
