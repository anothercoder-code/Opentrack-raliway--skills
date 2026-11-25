"""Corroborate one external OTD reservation predicate in paired original runs."""

from pathlib import Path
import re
from typing import Annotated

from pydantic import Field

from ..errors import APIError
from . import catalogs, native_evaluation_formats as fmt, writer
from .catalog_batch_reuse.course_batch import course_record
from .dispatching_rules_otd import RuleRoute, route_ids
from .itinerary_edit_tools import EditableItineraryProject
from .multi_document.core import ident
from .native_headway_tools import Run, SpacingCourse
from .native_interlocking import FrozenRailwayRun
from .native_platform_join import planned_itineraries, platform_model_signal
from .native_result_tools import EvaluateNativeRunTools, Name
from .native_run_evaluation import basename, digest, read_member, read_receipts, signal_position
from .native_throat_passage import advances
from .network_composition_plan import itinerary_routes
from .next_tools import Ordinal
from .project_workflow.relocation import relocate_project
from .saved_dispatching_rule_rebinding import _footprint, _read
from .tools import Input


TOOL = 'opentrack_compare_native_otd_reservation_effect'
SECONDS_ROUNDING = 0.01
METRES_ROUNDING = 0.050001
SHA256 = re.compile(r'[0-9a-f]{64}')


class BoundRoute(RuleRoute):
    array_id: Ordinal


class ReservationWitness(Input):
    course_id: Name
    route: BoundRoute


class CompareNativeOTDReservationEffect(Input):
    control: Run
    enabled: Run
    course_outcomes: Annotated[list[SpacingCourse], Field(min_length=2, max_length=10000)]
    target: ReservationWitness
    holder: ReservationWitness
    expected_xml_sha256: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
    minimum_delay_s: Annotated[float, Field(ge=0.02, le=86400, allow_inf_nan=False)] = 1.0


def _launch(run, evidence, xml_sha, secure_bytes):
    from ..native_execution import OTD_RULE_MEMBER, scenario_command

    hashes = evidence['input_sha256']
    names = [name for name in hashes if name.lower().endswith('.run')]
    fmt.require(len(names) == 1, 'Expected one original frozen .run member')
    run_name, = names
    root = run.settings['project_root']
    fmt.require(Path(run.settings['paths']['OutputPath']) == root / 'output'
                and evidence.get('outcome') == 'exited' and evidence.get('prefs_file_changed') is False,
                'Require a completed original launcher job with its own output and stable Preferences')
    timetable = Path(run.settings['paths']['TimetableFile']).relative_to(root).as_posix()
    written = evidence.get('input_writebacks')
    fmt.require(isinstance(written, dict) and set(written) <= {timetable}
                and all(isinstance(value, str) and SHA256.fullmatch(value) for value in written.values()),
                'Original launcher recorded an unexpected input writeback')
    binding = evidence.get('dispatching_rules')
    policy = None
    if xml_sha is None:
        fmt.require(binding is None and OTD_RULE_MEMBER not in hashes, 'Control has active or frozen OTD rules')
    else:
        fmt.require(isinstance(binding, dict) and binding.get('scenario_member') == OTD_RULE_MEMBER
                    and binding.get('route_id_mode') in ('compound', 'route_name')
                    and binding.get('xml_sha256') == hashes.get(OTD_RULE_MEMBER) == xml_sha,
                    'Enabled launch does not bind the explicitly reviewed OTD XML')
        policy = run.dependency(str(root / OTD_RULE_MEMBER))
        fmt.require(digest(policy) == xml_sha, 'Enabled frozen OTD XML SHA-256 differs')
    command = evidence['command']
    fmt.require(isinstance(command, list) and command and isinstance(command[0], str)
                and Path(command[0]).name.casefold() == 'opentrack.exe', 'Invalid original launcher command')
    expected_command = scenario_command(Path(command[0]), root, {'run_file': run_name, 'dispatching_rules': binding},
                                        {OTD_RULE_MEMBER: policy} if policy is not None else {})
    fmt.require(command == expected_command, 'Original launch flags differ beyond the exact permitted OTD arguments')
    fmt.require(run.settings['delay_scenario'] == '0' and run.receipt['protocol']['delay_scenario'] == 'None',
                'Require completed original runs with random delays disabled')
    configuration = {name: run.dependency(str(root / name)) for name in hashes if name != OTD_RULE_MEMBER}
    effective, _ = relocate_project(configuration, source_root=root.as_posix(), target_root='D:/OpenTrackOTDEffect',
        run_file=run_name, expected_hashes={name: hashes[name] for name in configuration},
        project_type=EditableItineraryProject)
    original_receipt = Path(evidence['evidence_directory'])
    manifest = {name: digest(read_member(original_receipt, name, secure_bytes=secure_bytes))
                for name in ('before.json', 'process.json')}
    return {'xml': policy, 'binding': binding, 'configuration_sha256': {name: digest(data) for name, data in effective.items()},
            'receipt_sha256': manifest, 'command': command}


def _preferences(control, enabled):
    keys = ('prefs_sha256_before', 'prefs_sha256_after')
    present = [key in row for row in (control, enabled) for key in keys]
    if not any(present):
        return {'same_frozen_preferences_verified': False, 'launchers_reported_no_writeback': True}
    fmt.require(all(present), 'Paired original Preferences SHA-256 evidence is incomplete')
    digests = [row[key] for row in (control, enabled) for key in keys]
    fmt.require(all(value == digests[0] for value in digests)
                and (digests[0] is None or isinstance(digests[0], str) and SHA256.fullmatch(digests[0])),
                'Original Preferences SHA-256 differs between launches')
    return {'same_frozen_preferences_verified': True, 'sha256': digests[0], 'launchers_reported_no_writeback': True}


def _isolate_policy(blob, project, mode, target, holder):
    _, _, root, _ = _read(blob)
    identifiers = route_ids(project, mode)
    target_id, holder_id = (identifiers[item.route.key()] for item in (target, holder))
    definitions, routes = root
    fmt.require(len(definitions) == len(routes) == 1 and target_id != holder_id,
                'Effect isolation requires exactly one OTD Route assignment and ruleset')
    ruleset, = definitions
    assignment, = routes
    fmt.require(assignment.attrib == {'id': target_id, 'routeRuleSetID': ruleset.attrib['id']} and len(ruleset) == 1,
                'The sole OTD exclusion rule must govern the exact target Route')
    rule, = ruleset
    fmt.require(not rule.attrib and len(rule) == 1
                and rule[0].attrib == {'routeID': holder_id, 'routeReservationState': 'reserved'},
                'The sole predicate must explicitly test the reviewed other Route reservation')
    return {'ruleset': ruleset.attrib['id'], 'applies_to': target_id, 'reserved_predicate_on': holder_id}


def _exact_advance(points, begin_m, end_m, kind, course):
    fmt.require(all(earlier[1] <= later[1] and (earlier[0] == later[0] or earlier[1] == later[1])
                    for earlier, later in zip(points, points[1:])),
                f'Original .{kind} for {course} is not a nondecreasing staircase')
    matches = [row for row in advances(points) if abs(row['from_m'] - begin_m) <= METRES_ROUNDING
               and abs(row['to_m'] - end_m) <= METRES_ROUNDING]
    fmt.require(len(matches) == 1,
                f'Expected one exact .{kind} advance on {course} from {begin_m:g} to {end_m:g} m')
    return matches[0]


def _course_witness(run, spec, course):
    cid = basename(spec.course_id)
    fmt.require(len(run.preferences[cid]) == 1 and course['spacing_mode_code'] == 0,
                'Course witness requires one saved Itinerary and fixed-block spacing')
    itinerary_name, = run.preferences[cid]
    project = run.project
    itinerary = run.itineraries[itinerary_name]
    direction, _ = project.dest_view(itinerary)
    identity = spec.route.route_name, spec.route.array_id, spec.route.start_end_id
    routes = [row for row in itinerary_routes(project, itinerary)
              if project.owners[id(row)] == spec.route.key()[:2] and ident(row) == identity]
    fmt.require(len(routes) == 1 and len(set(direction)) == len(direction), 'Expected one exact owned main Route on the frozen Itinerary')
    selected, = routes
    route_nodes = project.route_view(selected)
    index = direction.index(route_nodes[0])
    fmt.require(direction[index:index + len(route_nodes)] == route_nodes
                and direction[0] != route_nodes[0] and direction[-1] != route_nodes[-1],
                'Select a complete intermediate Route, away from simulation-start and terminal release shortcuts')
    axis = {direction[0]: fmt.number(course['output_offset_m'])}
    for begin, end in zip(direction, direction[1:]):
        edge = project.model(project.edge_between(begin, end))
        axis[end] = axis[begin] + edge.contents[9].values[1]
    anchors = []
    for end in (route_nodes[0], route_nodes[-1]):
        signal_id, label = platform_model_signal(project, end)
        anchors.append({'document': end[0], 'end_id': end[1], 'signal_model_id': signal_id,
                        'label': label, 'distance_m': axis[end]})
    prefix = f'OT_{cid}'
    raw = {ext: planned_itineraries(run.original_text(f'{prefix}.{ext}'), [itinerary_name], ext)
           for ext in ('sigpos', 'step1', 'step2')}
    fmt.require(all(re.findall(r'^// Train:[ \t]*(.*?)[ \t]*\r?$', text, re.M) == [course['train']]
                    for text in raw.values()), 'Original authority output Train differs from the frozen Course')
    for signal in anchors:
        position_m = 1000 * signal_position(raw['sigpos'], cid, signal['label'])
        fmt.require(abs(position_m - signal['distance_m']) <= METRES_ROUNDING,
                    'Original signal legend position differs from the exact saved Route endpoint')
    start, finish = (item['distance_m'] for item in anchors)
    windows = {}
    for ext in ('step1', 'step2'):
        trace = fmt.series(raw[ext], ext, cid)
        fmt.require(trace['units'] == ['s', 'km'] and trace['points'], 'Original authority traces require seconds and kilometres')
        points = [(stamp, value * 1000) for stamp, value in trace['points']]
        windows[ext] = _exact_advance(points, start, finish, ext, cid)
    reserved, released = (windows[ext]['time_s'] for ext in ('step1', 'step2'))
    fmt.require(reserved >= 0 and released > reserved, 'Original Route authority must have a complete positive holding interval')
    return {'course_id': cid, 'itinerary': itinerary_name, 'route': spec.route.model_dump(), 'signals': anchors,
            'resources': _footprint(project, selected), 'reservation_s': reserved, 'release_s': released,
            'native_advances': windows, 'output_sha256': {f'{prefix}.{ext}': run.hashes[f'{prefix}.{ext}'] for ext in raw}}


def _compare_timing(control, enabled, minimum_delay_s):
    before_target, before_holder = control
    after_target, after_holder = enabled
    target_key, release_key = 'reservation_s', 'release_s'
    base, switched = before_target[target_key], after_target[target_key]
    delay = round(switched - base, 5)
    gap = round(switched - after_holder[release_key], 5)
    checks = {
        'control_authority_granted_during_holder_reservation': (
            before_holder[target_key] + SECONDS_ROUNDING < base < before_holder[release_key] - SECONDS_ROUNDING),
        'holder_reservation_and_release_unchanged': all(
            abs(round(before_holder[key] - after_holder[key], 5)) <= SECONDS_ROUNDING
            for key in (target_key, release_key)),
        'enabled_authority_granted_only_after_holder_release': gap >= 0,
        'enabled_authority_delayed': delay >= minimum_delay_s,
    }
    return {'native_otd_reservation_effect_verified': all(checks.values()), 'checks': checks,
            'target_reservation_delay_s': delay, 'enabled_release_to_target_reservation_s': gap,
            'observed_control_before_holder_release_s': round(before_holder[release_key] - base, 5)}


def _check_separate_resources(observations):
    def safety_of(row):
        footprint = row['resources']
        movements = [footprint['movement'], *(part['overlap']['movement'] for part in footprint['parts'] if part['overlap'])]
        direct = {key for movement in movements for key, _ in movement['safety_elements']}
        links = {link['safety_element'] for movement in movements for leg in movement['legs']
                 for link in (leg['exclusion_target'], leg['exclusion_source']) if link is not None}
        return direct, links

    (first, first_links), (second, second_links) = map(safety_of, observations)
    fmt.require(first.isdisjoint(second | second_links) and second.isdisjoint(first_links),
                'The two OTD Route witnesses must have disjoint saved occupation and direct exclusion resources')


def _evaluate(output, evidence, outcomes, xml_sha, target, holder, secure_bytes):
    run = FrozenRailwayRun(output, evidence, outcomes, secure_bytes)
    fmt.require(set(run.receipt['protocol']['used_courses']) == {row['course_id'] for row in outcomes},
                'The original completion expectations must cover every used Course')
    launch = _launch(run, evidence, xml_sha, secure_bytes)
    root, _ = writer.load_next_compatible(run.dependency(run.settings['paths']['CourseFile']))
    saved = {row['course_id']: row for row in map(course_record, catalogs.course_items(root))}
    observations = tuple(_course_witness(run, spec, saved[spec.course_id]) for spec in (target, holder))
    _check_separate_resources(observations)
    return run, launch, observations


def verify_otd_reservation_effect(control_output, control_evidence, enabled_output, enabled_evidence, *, course_outcomes,
                                  expected_xml_sha256, target, holder, minimum_delay_s=1.0, secure_bytes=None):
    """Evaluate completed, SHA-bound original outputs without launching OpenTrack."""
    target = ReservationWitness.model_validate(target)
    holder = ReservationWitness.model_validate(holder)
    fmt.require(target.course_id != holder.course_id and target.route != holder.route,
                'Select distinct original Courses and Route witnesses')
    fmt.require(isinstance(expected_xml_sha256, str) and SHA256.fullmatch(expected_xml_sha256),
                'Explicit exact SHA-256 for the reviewed enabled OTD XML required')
    minimum = fmt.number(minimum_delay_s)
    fmt.require(0.02 <= minimum <= 86400, 'Expected a positive, measurable minimum authority delay')
    control_output, enabled_output = (Path(item).resolve(strict=True) for item in (control_output, enabled_output))
    control_evidence, enabled_evidence = (Path(item).resolve(strict=True) for item in (control_evidence, enabled_evidence))
    fmt.require(control_evidence != enabled_evidence and control_output != enabled_output,
                'Control and enabled runs must use independent evidence and native output directories')
    before = read_receipts(control_evidence, secure_bytes=secure_bytes)
    after = read_receipts(enabled_evidence, secure_bytes=secure_bytes)
    fmt.require(before['pid'] != after['pid'] or before['started_utc'] != after['started_utc'],
                'Expected two independent original process launches')
    outcomes = [SpacingCourse.model_validate(row).model_dump(exclude_none=True) for row in course_outcomes]
    fmt.require({target.course_id, holder.course_id} <= {row['course_id'] for row in outcomes},
                'Supply terminal completion expectations for both witness Courses')
    original, control_setup, control = _evaluate(control_output, before, outcomes, None, target, holder, secure_bytes)
    enabled, enabled_setup, treatment = _evaluate(enabled_output, after, outcomes, expected_xml_sha256, target, holder, secure_bytes)
    fmt.require(control_setup['configuration_sha256'] == enabled_setup['configuration_sha256'],
                'Paired original run configuration or native archive input differs beyond OTD and relocation')
    fmt.require(all(original.receipt['protocol'][key] == enabled.receipt['protocol'][key]
                    for key in ('used_courses', 'listed_incidents', 'configured_window')),
                'Paired original protocols disagree on used Courses, Incidents or simulation window')
    fmt.require(all(a['route'] == b['route'] and a['resources'] == b['resources'] and a['signals'] == b['signals']
                    for a, b in zip(control, treatment)), 'Paired original Route identity, axis or resources differ')
    mode = enabled_setup['binding']['route_id_mode']
    policy = _isolate_policy(enabled_setup['xml'], enabled.project, mode, target, holder)
    preferences = _preferences(before, after)
    comparison = _compare_timing(control, treatment, minimum)
    comparison['checks']['frozen_original_preferences_match'] = preferences['same_frozen_preferences_verified']
    comparison['native_otd_reservation_effect_verified'] = all(comparison['checks'].values())
    return {**comparison, 'policy': {**policy, 'xml_sha256': expected_xml_sha256, 'route_id_mode': mode},
            'preferences': preferences, 'witness_safety_resources_independent': True,
            'completed_courses_per_run': len(outcomes), 'matched_frozen_input_sha256': control_setup['configuration_sha256'],
            'control': {'target': control[0], 'holder': control[1], 'launch': {key: control_setup[key] for key in ('command', 'receipt_sha256')}},
            'enabled': {'target': treatment[0], 'holder': treatment[1], 'launch': {key: enabled_setup[key] for key in ('command', 'receipt_sha256')}}}


class NativeOTDReservationEffectTools(EvaluateNativeRunTools):
    def compare(self, args):
        try:
            return verify_otd_reservation_effect(
                self.directory(args.control.output_directory), self.directory(args.control.evidence_directory),
                self.directory(args.enabled.output_directory), self.directory(args.enabled.evidence_directory),
                course_outcomes=args.course_outcomes, expected_xml_sha256=args.expected_xml_sha256, target=args.target,
                holder=args.holder, minimum_delay_s=args.minimum_delay_s, secure_bytes=self.secure_bytes)
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_OTD_RESERVATION_EFFECT_INVALID',
                           'Could not verify paired original OTD reservation evidence', str(exc)[:500]) from exc


def tool_definitions(root):
    return [(TOOL, 'Compare completed original OTD control and enabled launches against one isolated reserved-Route '
             'rule, exact frozen Course itineraries and hashed native reservation/release events. Read only.',
             CompareNativeOTDReservationEffect, NativeOTDReservationEffectTools(root).compare)]
