"""Effect of one frozen original incident compared to a matched completed original control."""

import re

from ..errors import APIError
from . import catalogs, incident_operations, native_evaluation_formats as fmt, native_signal_stop_effect as signal_stop, writer
from .incident_source import validate_set_graph
from .infrastructure_incidents.core import item_from_object, validate
from .native_headway_tools import Run, SpacingCourse, normalized_options
from .native_interlocking import FrozenRailwayRun, route_spans
from .native_result_tools import EvaluateNativeRunTools, Name
from .native_run_evaluation import basename, digest, read_receipts
from .native_station_throughput import configured_window
from .operating_plan_edit import text
from .project_workflow.relocation import relocate_destination_catalog
from .route_factory import wrapper
from .runfile_parameters import time_seconds
from .tools import Input


SUPPORTED = {'path_speed', 'train_tractive_effort', 'train_power_limit', 'signal_stop'}
PHYSICS_LOG_OPTION = 'Output Time/Dist./Speed/Power'


class EffectStudy(Input):
    control: Run
    incident: Run
    name: Name
    course: SpacingCourse


def course_bank(blob, selected_name):
    root = writer.load_next_compatible(blob)[0]
    incident_list, sets = validate_set_graph(root)
    found = [record for record in incident_list if text(record, 0) == selected_name]
    fmt.require(len(found) <= 1, 'Duplicate selected original Incident name')
    item = None
    if found:
        record, = found
        catalogs.shape(record, 'OTIncident', 12, incident_operations.SCHEMA)
        item = item_from_object(record)
        writer.set_elements(root.contents[1].value, [row for row in incident_list if row is not record])
        for group in sets.values():
            values = catalogs.array(group.contents[0].value)
            if record in values:
                writer.set_elements(group.contents[0].value, [row for row in values if row is not record])
    return root, item, writer.fingerprint(root)


def frozen_state(railway, evidence, selected_name):
    hashes = evidence['input_sha256']
    members = [name for name in hashes if name.lower().endswith('.run')]
    fmt.require(len(members) == 1, 'Expected exactly one frozen .run member')
    filepath = railway.settings['project_root']
    run_blob = railway.dependency(str(filepath / members[0]))
    options = normalized_options(run_blob, filepath)
    member_paths = dict(options)
    courses, item, course_hash = course_bank(railway.dependency(railway.settings['paths']['CourseFile']), selected_name)
    dest, _ = relocate_destination_catalog(railway.dependency(railway.settings['paths']['DestInfoFile']),
        source=filepath.as_posix(), target='D:/OpenTrackIncidentComparison',
        documents=[value for key, value in options if key == 'Infrastructure Document'])
    static = {name: sha for name, sha in hashes.items()
              if name not in {members[0], member_paths['CourseFile'], member_paths['DestInfoFile']}}
    state = ([item for item in options if item[0] != 'Incident'], static, digest(dest), course_hash)
    return state, courses, item, options


def printed_clock(value, expected):
    found = re.fullmatch(r'(?:(\d{1,5})\s*/\s*)?([0-9]{2}:[0-9]{2}:[0-9]{2})', value.strip(), re.ASCII)
    fmt.require(found is not None, 'Malformed original event clock')
    day, clock = found.groups()
    if day is not None:
        return time_seconds(clock.encode('ascii'), day.encode('ascii'))
    at = time_seconds(clock.encode('ascii'), b'0')
    expected_day = int(expected // 86400)
    return min((86400 * candidate + at for candidate in range(max(0, expected_day - 1), expected_day + 2)),
               key=lambda value: (abs(value - expected), value))


def verified_activation(railway, item, course, target, tolerance):
    span = [time_seconds(item[side + '_time'].encode('ascii'), str(item[side + '_day']).encode('ascii'))
            for side in ('begin', 'end')]
    records = railway.receipt['protocol']['listed_incidents']
    fmt.require(len(records) == 1 and records[0]['name'] == item['name'],
                'Original protocol must list only the selected incident')
    displayed = [printed_clock(records[0][tag], expected) for tag, expected in zip(('start', 'end'), span)]
    fmt.require(displayed == span and span[0] < span[1], 'Original incident protocol differs from the frozen window')
    logs = fmt.messages(railway.original_text('OT_Messages.txt'))['incident_events']
    fmt.require([event['transition'] for event in logs] == ['started', 'stopped']
                and all(event['course_id'] == course and event['subject'] == target for event in logs),
                'Original activation log does not identify both transitions of the selected incident and target')
    observed = [printed_clock(event['clock'], expected) for event, expected in zip(logs, span)]
    fmt.require(all(abs(actual - expected) <= tolerance for actual, expected in zip(observed, span)),
                'Original incident transition exceeds the configured clock tolerance')
    return span, observed, logs


def longitudinal_scope(railway, item, cid, itinerary):
    project = railway.project
    definition = railway.itineraries[itinerary]
    if item['type'] != 'path_speed':
        fmt.require(item['course_id'] == cid, 'Selected train incident targets a different Course')
        return [0, route_spans(project, definition)[1]], {'course_id': cid}, item['name']

    identity = item['document'], item['start_end_id']
    owner = project.model(identity)
    choice, = [path for path in wrapper(owner.contents[17].value, 'OTPathList')
               if path.contents[2].values == [item['array_id'], item['start_end_id']]]
    name = text(choice, 1)
    _, paths = project.dest_view(definition)
    count = 0
    at = 0
    covered = None
    for document, info in paths:
        nodes, _ = project.path_view(project.itinerary_path(
            (document, info['start_id']), (info['name'], info['array_id'], info['start_id'])))
        metres = sum(project.model(project.edge_between(a, b)).contents[9].values[1] for a, b in zip(nodes, nodes[1:]))
        if (document, info['name'], info['array_id'], info['start_id']) == (identity[0], name, item['array_id'], identity[1]):
            covered = [at, at + metres]
            count += 1
        at += metres
    fmt.require(count == 1 and covered[0] < covered[1], 'Selected original Itinerary needs exactly one occurrence of the frozen incident Path')
    return covered, {'document': identity[0], 'start_end_id': identity[1], 'array_id': item['array_id'],
                     'path': name}, 'Path ' + name


def samples(railway, cid, itinerary):
    raw = railway.original_text(f'OT_{basename(cid)}.tsvP')
    labels = re.findall(r'^// Itineraries:[ \t]*1:[ \t]*(.+?)[ \t]*\r?$', raw, re.M)
    fmt.require(labels == [itinerary], 'Original physics output does not use the checked Itinerary')
    values = fmt.physical_series(raw, cid)
    fmt.require(values and all(a['time_s'] <= b['time_s'] and a['distance_km'] <= b['distance_km']
                    for a, b in zip(values, values[1:])), 'Original physics trace is empty or not a forward running-distance series')
    return values


def moving_samples(rows, seconds, metres, offset):
    begin, end = seconds
    low, high = metres
    return [row for row in rows if begin <= row['time_s'] <= end and row['speed_kmh'] > 0
            and low <= row['distance_km'] * 1000 - offset <= high]


def common_exposure(control, incident, seconds, scope, offset):
    raw = [moving_samples(rows, seconds, scope, offset) for rows in (control, incident)]
    fmt.require(all(len(rows) >= 2 for rows in raw), 'Both original runs must traverse the selected incident window')
    bounds = [max(rows[0]['distance_km'] for rows in raw) * 1000 - offset,
              min(rows[-1]['distance_km'] for rows in raw) * 1000 - offset]
    fmt.require(bounds[0] < bounds[1], 'Matched original runs do not cover common distance in the active window')
    common = [moving_samples(rows, seconds, bounds, offset) for rows in raw]
    fmt.require(all(len(rows) >= 2 for rows in common), 'Common incident window has insufficient moving observations')
    return bounds, common[0], common[1]


def peak(rows, quantity):
    point = max(rows, key=lambda row: row[quantity], default=None)
    return None if point is None else {key: point[key] for key in ('time_s', 'distance_km', quantity)}


def traction_comparison(control, incident, factor):
    def speeds(rows):
        result = {}
        for row in rows:
            speed, force = row['speed_kmh'], row['tractive_effort_kn']
            if row['acceleration_mps2'] > 0 and force > 0 and (speed not in result or force > result[speed]['tractive_effort_kn']):
                result[speed] = row
        return result

    a, b = speeds(control), speeds(incident)
    ratios = {speed: b[speed]['tractive_effort_kn'] / a[speed]['tractive_effort_kn'] for speed in sorted(a.keys() & b.keys())}
    matching = [speed for speed, ratio in ratios.items() if abs(ratio - factor) <= .002]
    witnesses = [{'speed_kmh': speed, 'control_sample': a[speed], 'incident_sample': b[speed],
                  'observed_force_ratio': round(ratios[speed], 6)}
                 for speed in matching[:3]]
    return {'saved_tractive_effort_factor': factor, 'matched_printed_speed_count': len(ratios),
            'matching_factor_count': len(matching), 'compared_speed_witnesses': witnesses,
            'verified_effect': factor < 1 and len(matching) >= 3}


def signal_stop_comparison(control, incident, item, course, itinerary, step, offset):
    duration = item.get('stop_duration_s')
    fmt.require(item['stop_probability_percentage'] == 100 and duration is not None and duration > 0,
                'Signal stop comparison requires a positive fixed duration and 100 percent stop probability')
    identity = signal_stop.frozen_signal(incident, item, itinerary, offset)
    declared, observed, logs = verified_activation(incident, item, None, 'Signal Stop ' + identity['signal_name'], step + 1.01)
    fmt.require(all(event['location'] == f"({identity['document']})" for event in logs),
                'Original Signal Stop activation does not identify the frozen worksheet')
    active = [max(declared[0], observed[0]), min(declared[1], observed[1])]
    before, after = [signal_stop.movement(run, course, itinerary, identity) for run in (control, incident)]
    cutoff = active[0] - step - 1.01
    identical_counts = {}
    for field in ('distances', 'speeds'):
        earlier, later = ([row for row in case[field] if row[0] < cutoff] for case in (before, after))
        fmt.require(earlier and earlier == later, f'Original course {field} differ before signal stop activation')
        identical_counts[field] = len(earlier)
    warnings = [signal_stop.stop_warnings(run.original_text('OT_Messages.txt'), course, identity)
                for run in (control, incident)]
    fmt.require(not warnings[0] and len(warnings[1]) == 1,
                'Original treatment must alone report a stop at the exact frozen Signal and Course')
    warning, = warnings[1]
    clock = printed_clock(warning['clock'], before['reservation_s'])
    result = signal_stop.matched_stop(before, after, active, clock, duration, step)
    return {**result, 'frozen_target': identity, 'declared_incident_window_s': declared,
            'original_activation_log_s': observed, 'original_activation_messages': logs,
            'active_measurement_window_s': active, 'original_stop_warning': {**warning, 'time_s': clock},
            'matching_preincident_distance_samples': identical_counts['distances'],
            'matching_preincident_speed_samples': identical_counts['speeds']}


def study_receipt(control, incident, control_evidence, incident_evidence, course, itinerary, item):
    return {'course_id': course, 'original_itinerary': itinerary, 'incident': item,
            'verified_one_incident_input_difference': True,
            'control_terminal_clock': control.receipt['courses'][0]['last_observed_event']['time_s'],
            'incident_terminal_clock': incident.receipt['courses'][0]['last_observed_event']['time_s'],
            'control_input_sha256': control_evidence['input_sha256'], 'incident_input_sha256': incident_evidence['input_sha256'],
            'control_output_sha256': {**control.receipt['output_sha256'], **control.files.hashes},
            'incident_output_sha256': {**incident.receipt['output_sha256'], **incident.files.hashes}}


def checked_inputs(plain, applied, kind):
    if plain == applied:
        return None
    if kind == 'signal_stop' and plain[1:] == applied[1:]:
        # The original run-file handler assigns this key to the physics logger.
        # This comparison only measures the separate speed, position and reservation streams.
        stripped, output = [], []
        for options in (plain[0], applied[0]):
            stripped.append([row for row in options if row[0] != PHYSICS_LOG_OPTION])
            output.append([value for key, value in options if key == PHYSICS_LOG_OPTION])
        if stripped[0] == stripped[1] and all(rows in ([], ['0'], ['1']) for rows in output):
            return {'option': PHYSICS_LOG_OPTION, 'control': output[0][0] if output[0] else None,
                    'incident': output[1][0] if output[1] else None}
    raise ValueError('Original control changes more than the selected Incident and allowed relocation or logging')


def measure(control, incident, control_evidence, incident_evidence, name, cid):
    plain_state, _, plain_item, config_a = frozen_state(control, control_evidence, name)
    applied_state, bank, item, config_b = frozen_state(incident, incident_evidence, name)
    fmt.require(plain_item in (None, item), 'Frozen control contains a different definition of the selected Incident')
    output_difference = checked_inputs(plain_state, applied_state, item['type'] if item else None)
    fmt.require(not [value for key, value in config_a if key == 'Incident']
                and [value for key, value in config_b if key == 'Incident'] == [name]
                and not control.receipt['protocol']['listed_incidents']
                and not fmt.messages(control.original_text('OT_Messages.txt'))['incident_events'],
                'Control must have no active events and treatment must activate only the selected Incident')
    fmt.require(item and item['enabled'] and item['type'] in SUPPORTED and item['probability_percentage'] == 100
                and not item.keys() & {'begin_distribution', 'duration_distribution', 'periodic', 'head_only', 'discrete_moving_block'},
                'Expected a supported deterministic whole-train native Incident12 record')
    fmt.require(dict(config_b).get('Delay Scenario') == '0'
                and all(str(case.receipt['protocol']['delay_scenario']).casefold() in {'0', 'none'}
                        for case in (control, incident))
                and control.receipt['protocol']['used_courses'] == incident.receipt['protocol']['used_courses'],
                'Paired executions must use the same original Course roster under Delay Scenario 0')
    window = configured_window(incident, incident_evidence)
    validate(item, incident.project, window, bank)
    choices = incident.preferences[cid]
    fmt.require(len(choices) == 1 and choices == control.preferences[cid], 'Select one common directed original Itinerary')
    itinerary, = choices
    step = fmt.number(dict(config_b)['Step'])
    fmt.require(step > 0, 'Positive frozen simulation step required')
    row, = [row for row in catalogs.course_items(bank) if text(row, 0) == cid]
    offset = row.contents[7].values[0]
    if item['type'] == 'signal_stop':
        result = signal_stop_comparison(control, incident, item, cid, itinerary, step, offset)
        return {**study_receipt(control, incident, control_evidence, incident_evidence, cid, itinerary, item),
                **result, 'verified_one_incident_input_difference': output_difference is None,
                'verified_one_simulation_incident_difference': True, 'physics_log_option_difference': output_difference}

    interval_m, identity, message = longitudinal_scope(incident, item, cid, itinerary)
    tolerance = 1.01 + step
    declared, observed, logs = verified_activation(incident, item, None if item['type'] == 'path_speed' else cid,
                                                    message, tolerance)
    if item['type'] == 'path_speed':
        fmt.require(all(event['location'] == f"({identity['document']})" for event in logs),
                    'Original Path activation does not name the frozen owning worksheet')
    active = [max(declared[0], observed[0]) + tolerance, min(declared[1], observed[1]) - tolerance]
    fmt.require(active[0] < active[1], 'Incident is too short for independent interior observations')
    fixed, changed = samples(control, cid, itinerary), samples(incident, cid, itinerary)
    cutoff = min(declared[0], observed[0]) - tolerance
    before_a, before_b = ([sample for sample in values if sample['time_s'] < cutoff] for values in (fixed, changed))
    fmt.require(before_a == before_b, 'Original physical traces disagree before the verified incident')
    common, a, b = common_exposure(fixed, changed, active, interval_m, offset)
    kind = item['type']
    quantity = {'path_speed': 'speed_kmh', 'train_power_limit': 'mechanical_power_kw',
                'train_tractive_effort': 'tractive_effort_kn'}[kind]
    base_peak, changed_peak = peak(a, quantity), peak(b, quantity)
    during_movement = moving_samples(changed, active, interval_m, offset)
    after_movement = moving_samples(changed, [max(declared[1], observed[1]) + tolerance, window[1]], interval_m, offset)
    before_movement = moving_samples(changed, [window[0], min(declared[0], observed[0]) - tolerance], interval_m, offset)
    active_peak = peak(during_movement, quantity)
    if kind == 'train_tractive_effort':
        result = traction_comparison(a, b, item['tractive_effort_factor'])
    else:
        option = 'reduced_speed_kmh' if kind == 'path_speed' else 'limited_power_kw'
        limit = item[option]
        epsilon = .050001 if kind == 'path_speed' else max(.001, limit * .000001)
        result = {'saved_limit': limit, 'effect_measurement_tolerance': epsilon,
                  'verified_effect': active_peak[quantity] <= limit + epsilon and base_peak[quantity] > limit + epsilon
                                     and changed_peak[quantity] >= limit - epsilon}
    return {**study_receipt(control, incident, control_evidence, incident_evidence, cid, itinerary, item),
            'frozen_target': identity,
            'declared_incident_window_s': declared, 'original_activation_log_s': observed,
            'original_activation_messages': logs, 'active_measurement_window_s': active,
            'frozen_target_distance_m': interval_m, 'common_observed_distance_m': [round(x, 6) for x in common],
            'quantity': quantity, 'control_common_moving_samples': len(a), 'incident_common_moving_samples': len(b),
            'control_common_peak': base_peak, 'incident_common_peak': changed_peak,
            'incident_before_peak': peak(before_movement, quantity), 'incident_active_peak': active_peak,
            'incident_after_peak': peak(after_movement, quantity),
            'matching_preincident_trace_samples': len(before_a), **result}


class EffectTools(EvaluateNativeRunTools):
    def compare(self, args):
        try:
            outcomes = [args.course.model_dump(exclude_none=True)]
            evidences = [read_receipts(self.directory(spec.evidence_directory), secure_bytes=self.secure_bytes)
                         for spec in (args.control, args.incident)]
            control, incident = [FrozenRailwayRun(self.directory(spec.output_directory), evidence, outcomes, self.secure_bytes)
                                 for spec, evidence in zip((args.control, args.incident), evidences)]
            return measure(control, incident, *evidences, args.name, args.course.course_id)
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('NATIVE_INCIDENT_EFFECT_INVALID', 'Could not compare sealed original incident effects',
                           str(exc)[:600]) from exc
