"""Review and run serial batches of already-authored original simulation requests."""

from collections import defaultdict
from fnmatch import fnmatchcase
import json
from pathlib import Path
from time import sleep
from types import SimpleNamespace
from typing import Annotated

from pydantic import Field, StrictInt, model_validator

from . import native_execution as native
from .current_archive import catalogs, course_factories, native_monitoring, native_monitoring_formats, native_occupation_groups, writer
from .current_archive.bundle_tools import Source
from .current_archive.catalog_batch_reuse.course_batch import course_record
from .current_archive.consist_workflow.core import summary as consist_summary
from .current_archive.itinerary_edit_tools import EditableItineraryProject
from .current_archive.native_platform_join import frozen_options, platform_model_signal
from .current_archive.native_result_tools import EvaluateNativeRun, Name
from .current_archive.native_route_protection import TOOL as PROTECTION_TOOL, RouteProtection, frozen_routes
from .current_archive.native_route_protection import output_names as protection_output_names
from .current_archive.native_run_evaluation import basename, decode, plan as evaluation_plan, read_member, read_receipts, signal_position
from .current_archive.native_throat_passage import TOOL as THROAT_TOOL, ThroatPassage, frozen_passage, output_names
from .current_archive.network_operating_plan import _terminal_buffer_scope, resolve_visit_stop, route_trace
from .current_archive.prepare_contract.auxiliary import records
from .current_archive.saved_cross_platform_halts import _platform as connected_platform, _stop_markers
from .current_archive.saved_halt_creation import HEAD_OFFSETS
from .current_archive.saved_halt_location import HALT_TYPES, _observed_markers, _selected_marker
from .current_archive.shunting_workflow.core import plan_connections
from .current_archive.station_reference_edit import EndpointLinkReview
from .current_archive.tools import Input, PathText
from .errors import APIError
from .simulation_evidence import Control


JOIN_TOOL = 'opentrack_verify_native_platform_join'
CONTROL_TOOL = 'opentrack_simulation_control'
REQUIRED_OUTPUTS = ('OT_Protocol.*.txt', 'OT_Messages.txt', 'OT_CourseStatistics.txt', 'OT_StationStatistics.txt')
Sha256 = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


class MarkerExpectation(Input):
    course: Name
    station: Name
    document: Name
    signal_id: Annotated[StrictInt, Field(ge=0)]
    position_m: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    dwell_s: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    cross_document_scope: Source | None = None


class InstrumentPassage(Input):
    document: Name
    instrument_id: Annotated[StrictInt, Field(ge=0, le=2147483647)]
    end_id: Annotated[StrictInt, Field(ge=0, le=2147483647)]
    edge_ids: Annotated[list[Annotated[StrictInt, Field(ge=0, le=2147483647)]], Field(min_length=1, max_length=120)]
    course_id: Name
    direction_code: Annotated[StrictInt, Field(ge=1, le=2)] | None = None


class DirectedEndpointSignal(Input):
    document: Name
    end_id: Annotated[StrictInt, Field(ge=0)]
    signal_id: Annotated[StrictInt, Field(ge=0)]


class EndpointSignals(Input):
    course_id: Name
    origin: DirectedEndpointSignal
    terminal: DirectedEndpointSignal


class IntermediateSignal(DirectedEndpointSignal):
    course_id: Name


class QueueCase(Input):
    id: Annotated[str, Field(pattern=r'^[a-z0-9][a-z0-9-]{0,79}$')]
    request: PathText
    request_sha256: Sha256
    focus: PathText
    manual_checks: list[PathText] = Field(default_factory=list, max_length=20)
    required_files: list[PathText] = Field(default_factory=list, max_length=500)
    join_check: PathText | None = None
    join_check_sha256: Sha256 | None = None
    marker: MarkerExpectation | None = None
    throat_passage: ThroatPassage | None = None
    throat_passages: Annotated[list[ThroatPassage], Field(max_length=32)] = Field(default_factory=list)
    route_protection: RouteProtection | None = None
    instrument_passages: Annotated[list[InstrumentPassage], Field(max_length=16)] = Field(default_factory=list)
    endpoint_signals: EndpointSignals | None = None
    endpoint_links: Annotated[list[EndpointLinkReview], Field(max_length=100)] = Field(default_factory=list)
    intermediate_signals: Annotated[list[IntermediateSignal], Field(max_length=100)] = Field(default_factory=list)

    @model_validator(mode='after')
    def distinct_throat_courses(self):
        if self.throat_passage is not None and self.throat_passages:
            raise ValueError('Use either one throat_passage or a list of throat_passages')
        if len({passage.course_id for passage in self.throat_passages}) != len(self.throat_passages):
            raise ValueError('Use one native throat passage review per Course')
        return self

    @property
    def reviewed_throat_passages(self):
        return [self.throat_passage] if self.throat_passage is not None else self.throat_passages


class Queue(Input):
    schema_version: Annotated[StrictInt, Field(ge=1, le=1)]
    cases: Annotated[list[QueueCase], Field(min_length=1, max_length=200)]


def checked_json(root, name):
    path = native.child_path(root, name)
    raw = native.read_bounded(path, 4 * 1024 * 1024)
    return path, native.digest(raw), json.loads(raw)


def frozen_catalogs(members, relocation):
    def catalog(role):
        return writer.load_next_compatible(members[relocation['catalog_paths'][role]])[0]

    courses = {item['course_id']: item for item in map(course_record, catalogs.course_items(catalog('courses')))}
    stations = {sign: catalogs.text(row.contents[2].value) for sign, row in catalogs.station_items(catalog('stations')).items()}
    timetable = defaultdict(list)
    for row in course_factories.timetable(catalog('timetable')).values():
        timetable[catalogs.text(row.contents[1].value)].append(row)
    return catalog, courses, stations, timetable


def check_course_expectations(expected, courses, stations, timetable):
    for item in expected:
        cid = item['course_id']
        native.require(cid in courses and courses[cid]['enabled'] and cid in timetable,
                       f'{cid} is not an enabled scheduled original Course')
        rows = sorted(timetable[cid], key=lambda row: row.contents[3].value)
        names = [stations[catalogs.text(row.contents[5].value)] for row in rows]
        for key, observed in (('origin_station', names[0]), ('terminal_station', names[-1])):
            native.require(item.get(key) in (None, observed), f'{cid} planned {key} differs from declared endpoint')
        stops = [name for row, name in zip(rows, names, strict=True) if row.contents[10].value & 1]
        native.require(all(row['station'] in stops for row in item.get('required_stops', [])),
                       f'{cid} expected stop is absent from the frozen stopping rows')


def check_marker(root, marker, expected, catalog, courses, members, relocation):
    course = courses[marker.course]
    if marker.dwell_s == 0:
        matches = [item for item in expected if item['course_id'] == marker.course and item.get('terminal_stop')
                   and item.get('terminal_station') == marker.station and item.get('distance_m') is not None
                   and abs(item['distance_m'] + course['output_offset_m'] - marker.position_m)
                   <= (1.75 if item.get('distance_tolerance_m') is None else item['distance_tolerance_m'])]
    else:
        matches = [stop for item in expected if item['course_id'] == marker.course for stop in item.get('required_stops', [])
                   if stop['station'] == marker.station and stop['min_dwell_s'] >= marker.dwell_s
                   and stop.get('position_min_m') is not None and stop.get('position_max_m') is not None
                   and stop['position_min_m'] <= marker.position_m <= stop['position_max_m']]
    native.require(len(matches) == 1 and len(course['itineraries']) == 1,
                   'Marker requires one reviewed Course path and a matching timed stop position expectation')
    project = frozen_project(members, relocation)
    itinerary, = [item for item in project.dests if catalogs.text(item.contents[1].value) == course['itineraries'][0]]
    nodes, _ = project.dest_view(itinerary)
    signal = project.model((marker.document, marker.signal_id))
    end = signal.contents[7].value
    reference = project.key(end)
    signal_type = signal.contents[8].values[0]
    native.require(nodes.count(reference) == 1 and end.contents[11].value is signal
                   and signal_type in HALT_TYPES, 'Expected paired halt marker must occur on the frozen path')
    train, = [item for item in catalogs.train_items(catalog('trains')) if catalogs.text(item.contents[0].value) == course['train']]
    engines = {catalogs.text(item.contents[1].value): item for item in catalogs.engine_items(catalog('depot'))}
    length = consist_summary(train, engines)['length_m']
    proof = {'document': marker.document, 'signal_id': marker.signal_id, 'directional_end': list(reference),
             'signal_type': signal_type, 'train_length_m': length, 'minimum_dwell_s': marker.dwell_s}
    marker_axis = None
    distance = course['output_offset_m']
    if marker.dwell_s == 0:
        scope = _terminal_buffer_scope(project, nodes)
        native.require(scope is not None and marker.cross_document_scope is None and reference in nodes[scope[0]:-1],
                       'A marker with no planned dwell must belong to the reviewed physical buffer platform')
        trace = route_trace(project, itinerary)
        final = trace['visits'][-1]
        point = resolve_visit_stop(final, length)
        native.require(point is not None and point['signal_id'] == marker.signal_id and point['end_key'] == reference
                       and point['available_length_m'] >= length,
                       'The physical buffer platform selects a different marker or cannot berth the saved train')
        head = point['distance_m'] + distance
        native.require(abs(head - marker.position_m) <= .17, 'Frozen marker does not give the reviewed terminal stop position')
        return {**proof, 'marker_position_m': point['marker_distance_m'] + distance, 'position_m': head,
                'physical_buffer_end': list(final['physical_buffer_end']),
                'physical_buffer_position_m': trace['route_length_m'] + distance,
                'station_reference': list(final['end_key']), 'station_reference_position_m': final['distance_m'] + distance,
                'geometric_terminal_reference': final['geometric_terminal_reference']}
    if marker.cross_document_scope is not None:
        _, sha, scope = checked_json(root, marker.cross_document_scope.path)
        native.require(sha == marker.cross_document_scope.sha256,
                       'Reviewed cross-document platform scope SHA-256 differs')
        operation = scope['operation']
        platform, _, _, exit_id, _ = connected_platform(
            project, scope['target_document'], operation, allow_station_turnouts=True)
        start, = [i for i, key in enumerate(nodes) if key == platform[0]]
        native.require(nodes[start:start + len(platform)] == platform and reference in platform[:-1],
                       'The frozen Course must traverse the complete reviewed connected platform')
        markers = _stop_markers(project, platform[:-1])
        selected_id = marker.document, marker.signal_id
        platform_end = platform[-1]
    else:
        station = end.contents[12].value
        station_indices = [i for i, key in enumerate(nodes) if key[0] == marker.document
                           and project.model(key).contents[12].value is station and project.model(key).contents[20].value == 2]
        native.require(station is not None and len(station_indices) == 1,
                       'Expected marker must refer to one directional station reference')
        terminal = station_indices[0]
        reference_signal = project.model(nodes[terminal]).contents[11].value
        if reference_signal is None:
            trace = route_trace(project, itinerary)
            visit, = [row for row in trace['visits'] if row['end_key'] == nodes[terminal]]
            point = resolve_visit_stop(visit, length)
            native.require(not visit['halt_stop_issue'] and point is not None and point['signal_id'] == marker.signal_id
                           and point['end_key'] == reference and point['available_length_m'] >= length,
                           'Frozen directed platform selects a different marker or cannot berth the saved train')
            head = point['distance_m'] + distance
            native.require(abs(head - marker.position_m) <= .17,
                           'Frozen marker and train length do not match the reviewed head position before the platform exit')
            exit_point = visit['default_stop']
            return {**proof, 'marker_position_m': point['marker_distance_m'] + distance, 'position_m': head,
                    'platform_exit': list(exit_point['end_key']), 'platform_exit_position_m': exit_point['distance_m'] + distance,
                    'station_reference': list(nodes[terminal]), 'station_reference_position_m': visit['distance_m'] + distance}
        native.require(nodes.index(reference) < terminal, 'Expected marker must precede one directional station reference')
        start = terminal
        while start > 0 and nodes[start - 1][0] == marker.document and project.model(nodes[start - 1]).contents[12].value is station:
            start -= 1
        markers = _observed_markers([project.model(key) for key in nodes[start:terminal]])
        platform_end = nodes[terminal]
        exit_id = reference_signal.contents[0].value
        selected_id = marker.signal_id

    for first, second in zip(nodes, nodes[1:]):
        if first == reference:
            marker_axis = distance
        if first == platform_end:
            break
        distance += project.model(project.edge_between(first, second)).contents[9].values[1]
    native.require(marker_axis is not None and _selected_marker(markers, length, exit_id) == selected_id,
                   'Frozen directed platform selects a different marker for the saved train length')
    head = marker_axis + HEAD_OFFSETS.get(signal_type, 0) * length
    native.require(head <= distance and abs(head - marker.position_m) <= .17,
                   'Frozen marker and train length do not match the reviewed head position before the platform exit')
    return {**proof, 'marker_position_m': marker_axis, 'position_m': head,
            'platform_exit': list(platform_end), 'platform_exit_position_m': distance}


def frozen_project(members, relocation):
    docs = {Path(name).stem: members[name] for name in relocation['documents']}
    paths = {Path(name).stem: relocation['execution_root'] + '/' + name for name in relocation['documents']}
    project = EditableItineraryProject(docs, document_paths=paths,
        expected_hashes={key: native.digest(data) for key, data in docs.items()}, complete_document_set=True)
    project.check_dest_catalog(members[relocation['catalog_paths']['dest']])
    return project


def check_instrument_passages(specs, members, relocation, courses, outcomes):
    project = frozen_project(members, relocation)
    course_ids = {item['course_id'] for item in outcomes if item.get('terminal_station')}
    checks = []
    for spec in specs:
        native.require(spec.course_id in course_ids, 'Instrument passage requires a matching Course terminal')
        course = courses[spec.course_id]
        native.require(len(course['itineraries']) == 1, 'Instrument passage requires one reviewed Course itinerary')
        label, = course['itineraries']
        destination, = [item for item in project.dests if catalogs.text(item.contents[1].value) == label]
        nodes, _ = project.dest_view(destination)
        records = native_monitoring.records(project.roots[spec.document])['instruments']
        instruments = [record for record in records if record['id'] == spec.instrument_id]
        native.require(len(instruments) == 1, 'Expected one exact instrument in the frozen worksheet')
        instrument, = instruments
        native.require(instrument['end_id'] == spec.end_id and instrument['edge_ids'] == spec.edge_ids,
                       'The frozen instrument End or ordered Edge membership differs from the reviewed passage')
        anchor = spec.document, spec.end_id
        saved_direction = instrument['direction_code']
        directions = ([1 for node in nodes if saved_direction in (1, 3) and node == anchor]
                      + [2 for node in nodes if saved_direction in (2, 3) and project.actual_related(node) == anchor])
        if spec.direction_code is not None:
            directions = [direction for direction in directions if direction == spec.direction_code]
        native.require(len(directions) == 1, 'Expected one eligible passage at the instrument or its paired directional End')
        name = native_monitoring.label(instrument['name'])
        output = basename(f'OT_Ins_{name}_{spec.document}_{spec.instrument_id}.ins'.replace(' ', '_'))
        checks.append({**spec.model_dump(exclude_none=True), 'direction_code': directions[0], 'output': output})
    return checks


def read_instrument_passages(output, scenario, checks, hashes):
    results = []
    for check in checks:
        name = check['output']
        data = read_member(output, name)
        native.require(native.digest(data) == hashes.get(name), f'Original instrument output changed: {name}')
        records = native_monitoring_formats.instruments(decode(data))['records']
        matches = [row for row in records if row['kind'] == 'train_record' and row['scenario'] == scenario
                   and row['course_id'] == check['course_id']
                   and check.get('direction_code', row['direction_code']) == row['direction_code']]
        native.require(bool(matches), f'No native instrument record for {check["course_id"]} in {name}')
        results.append({**check, 'sha256': hashes[name], 'observations': matches})
    return results


def check_endpoint_signals(spec, project, course):
    native.require(course['enabled'] and len(course['itineraries']) == 1,
                   'Endpoint signals require one enabled Course with one reviewed Itinerary')
    destination, = [item for item in project.dests if catalogs.text(item.contents[1].value) == course['itineraries'][0]]
    nodes, _ = project.dest_view(destination)
    geometry_length = sum(project.model(project.edge_between(a, b)).contents[9].values[1]
                          for a, b in zip(nodes, nodes[1:]))
    offset = course['output_offset_m']
    ends = {}
    for role, key, position in (('origin', nodes[0], offset), ('terminal', nodes[-1], offset + geometry_length)):
        review = getattr(spec, role)
        native.require(key == (review.document, review.end_id),
                       'Frozen Itinerary endpoint differs from the reviewed directed End')
        signal_id, label = platform_model_signal(project, key)
        native.require(signal_id == review.signal_id, 'Frozen endpoint carries a different native main signal')
        ends[role] = {**review.model_dump(), 'label': label, 'position_m': position}
    return {'course_id': spec.course_id, 'output': f'OT_{basename(spec.course_id)}.sigpos', **ends}


def read_endpoint_signals(output, check, hashes):
    name = check['output']
    data = read_member(output, name)
    native.require(native.digest(data) == hashes.get(name), f'Original signal output changed: {name}')
    legend = decode(data)
    results = {}
    for role in ('origin', 'terminal'):
        expected = check[role]
        observed = signal_position(legend, check['course_id'], expected['label']) * 1000
        native.require(abs(observed - expected['position_m']) <= .1,
                       f'The original {role} signal differs from the frozen course chainage')
        results[role] = {**expected, 'observed_position_m': observed}
    return {'course_id': check['course_id'], 'sha256': hashes[name], **results}


def check_intermediate_signals(reviews, project, courses, outcomes):
    expected = {item['course_id'] for item in outcomes
                if item.get('origin_station') and item.get('terminal_station')}
    destinations = {catalogs.text(item.contents[1].value): item for item in project.dests}
    checked = []
    seen = set()
    for review in reviews:
        cid = review.course_id
        native.require(cid in expected and cid in courses, 'Intermediate signals require expected Course completion')
        course = courses[cid]
        native.require(course['enabled'] and len(course['itineraries']) == 1,
                       'Intermediate signals require one enabled Course with one reviewed Itinerary')
        itinerary, = course['itineraries']
        nodes, _ = project.dest_view(destinations[itinerary])
        key = review.document, review.end_id
        native.require((cid, key) not in seen and nodes.count(key) == 1 and key in nodes[1:-1],
                       'Select a unique intermediate directed End on the frozen Course Itinerary')
        seen.add((cid, key))
        signal, label = platform_model_signal(project, key)
        native.require(signal == review.signal_id, 'Frozen intermediate End carries a different native main signal')
        prefix = nodes[:nodes.index(key) + 1]
        position = course['output_offset_m'] + sum(project.model(project.edge_between(a, b)).contents[9].values[1]
                                                   for a, b in zip(prefix, prefix[1:]))
        base = f'OT_{basename(cid)}'
        checked.append({**review.model_dump(), 'itinerary': itinerary, 'label': label, 'position_m': position,
                        'outputs': [base + '.sigpos', base + '.st1']})
    return checked


def read_intermediate_signals(output, checks, hashes):
    from .current_archive.native_interlocking import metres_trace
    from .current_archive.native_platform_join import planned_itineraries
    from .current_archive.native_run_evaluation import OutputFiles

    files = OutputFiles(Path(output).resolve(strict=True), None, set(hashes), hashes, None)
    trajectories = {}
    results = []
    for check in checks:
        cid, itinerary = check['course_id'], check['itinerary']
        if cid not in trajectories:
            legend, trajectory = check['outputs']
            trajectories[cid] = (planned_itineraries(files.read(legend), [itinerary], 'sigpos'),
                                 metres_trace(files.read(trajectory), 'st1', cid, itinerary))
        text, samples = trajectories[cid]
        observed = signal_position(text, cid, check['label']) * 1000
        native.require(abs(observed - check['position_m']) <= .1,
                       'The original intermediate signal differs from the frozen Course chainage')
        bracket = next(([left, right] for left, right in zip(samples, samples[1:])
                        if left[0] < right[0] and left[1] <= observed < right[1]), None)
        native.require(bracket is not None and samples[0][1] < observed,
                       'The original Course trajectory did not pass the intermediate signal')
        results.append({**check, 'observed_position_m': observed, 'original_passage_bracket': bracket,
                        'sha256': {name: hashes[name] for name in check['outputs']}})
    return results


def check_endpoint_links(reviews, members, relocation, run_name, courses, outcomes, stations):
    from .current_archive.saved_platform_resize import OPERATING_FILES
    from .current_archive.station_reference_operating import frozen_endpoint_turnrounds

    project = frozen_project(members, relocation)
    banks = {role: members[relocation['catalog_paths'][role]] for role in OPERATING_FILES}
    links, geometry, native_links = frozen_endpoint_turnrounds(
        banks, members[run_name], project, [row.model_dump() for row in reviews])
    planned = {item['course_id']: item for item in outcomes}
    results, witnesses = [], {}

    def witness(cid):
        if cid in witnesses:
            return witnesses[cid]
        observed, course = geometry[cid], courses[cid]
        expected = planned.get(cid, {})
        native.require(expected.get('origin_station') and expected.get('terminal_station')
                       and expected.get('terminal_event', 'Arr.') == 'Arr.',
                       'Linked Courses require declared origin and arrival at the expected final station')
        head = observed['terminal_head_m'] + course['output_offset_m']
        native.require(expected.get('distance_m') is not None and abs(expected['distance_m'] - head) <= .1,
                       'Linked Course terminal head must match the reviewed runtime distance')
        ends = {}
        for role, field in (('origin', 'start'), ('terminal', 'terminal')):
            endpoint = observed[field]
            signal_id, _ = platform_model_signal(project, (endpoint['document'], endpoint['end_id']))
            ends[role] = {**endpoint, 'signal_id': signal_id}
        checked = check_endpoint_signals(EndpointSignals.model_validate({'course_id': cid, **ends}), project, course)
        witnesses[cid] = {**checked, 'itinerary': course['itineraries'][0],
                          'origin_station': expected['origin_station'], 'terminal_station': expected['terminal_station'],
                          'terminal_head_m': head}
        return witnesses[cid]

    for link, native_link in zip(links, native_links, strict=True):
        predecessor, successor = witness(link['from_course']), witness(link['to_course'])
        station = stations[link['station_sign']]
        native.require(predecessor['terminal_station'] == successor['origin_station'] == station,
                       'Linked arrival and departure must use the same frozen native station display name')
        native.require(successor['origin']['position_m'] == 0, 'Linked Course runtime evidence uses the native zero origin')
        results.append({'station_sign': link['station_sign'], 'movement': link['movement'],
                        'minimum_hold_s': link['minimum_hold_s'], 'predecessor': predecessor,
                        'successor': successor, 'frozen_link': native_link['after']})
    return results


def check_join(model, courses, members, relocation):
    receiver, donor = model.receiver.course_id, model.donor.course_id
    project = frozen_project(members, relocation)
    banks = {role: members[relocation['catalog_paths'][role]] for role in ('timetable', 'courses', 'trains', 'stations', 'depot')}
    operation = {'kind': 'join', 'main_course': receiver, 'other_course': donor, 'station_sign': model.station_sign}
    if model.main_visit_index is not None:
        operation['main_visit_index'] = model.main_visit_index
    _, verified = plan_connections(banks, {'schema': 'split-join-timetable-plan/1',
        'accept_unverified_spatial_and_dynamic_execution': True, 'operations': [operation]},
        verify_existing=True, sequential_main=True)
    event, = verified['events']
    context = SimpleNamespace(project=project, preferences={cid: courses[cid]['itineraries'] for cid in (receiver, donor)},
                              itineraries={catalogs.text(item.contents[1].value): item for item in project.dests})
    end = model.expected_platform.document, model.expected_platform.end_id
    options = [frozen_options(context, cid, model.station_sign, None if is_donor else event['main_visit_index'], donor=is_donor)
               for cid, is_donor in ((receiver, False), (donor, True))]
    matching = [{tuple(item['stop_edge_key']) for item in choices if item['end_key'] == end} for choices in options]
    native.require(len(matching[0]) == 1 and matching[0] == matching[1],
                   'Both Courses must have a saved option for the reviewed join platform and stopping Edge')
    return {'directed_platform_end': list(end), 'stopping_edge': list(next(iter(matching[0]))),
            'formation_length_before_m': event['initial_main']['length_m'],
            'projected_formation_length_m': event['projected_main_length_m']}


def check_trial(root, registry, case, draft, scenario):
    request = draft.request
    project, evidence, members, relocation, reset, _ = native.preview_scenario(
        draft.job, draft.project, draft.inputs, request, scenario,
        dispatching_xml=draft.dispatching_files.get(native.otd.XML_FILE))
    output = project / 'output'
    output_name, evidence_name = [path.relative_to(root).as_posix() for path in (output, evidence)]
    arguments = {**request['expectations'], 'output_directory': output_name, 'evidence_directory': evidence_name}
    expectations = EvaluateNativeRun.model_validate(arguments)
    courses_expected = evaluation_plan(expectations.model_dump(exclude_none=True))
    catalog, courses, stations, timetable = frozen_catalogs(members, relocation)
    check_course_expectations(courses_expected, courses, stations, timetable)
    expected = {*REQUIRED_OUTPUTS, *case.required_files}
    throat_passages = case.reviewed_throat_passages
    for passage in throat_passages:
        expected.update(output_names(passage))
    if case.route_protection is not None:
        expected.update(protection_output_names(case.route_protection))
    values = {key: value for key, value, _ in records(members[request['run_file']])}
    instruments = []
    if case.instrument_passages:
        native.require(values.get('Show Instruments') == '1', 'Enable original instrument updates for passage records')
        instruments = check_instrument_passages(case.instrument_passages, members, relocation, courses, courses_expected)
    expected.update(item['output'] for item in instruments)
    has_legend = values.get('Output Station- & Signalpositions') == '1'
    endpoint_links = []
    if case.endpoint_links:
        from .current_archive.native_endpoint_connections import output_names as endpoint_link_outputs

        endpoint_links = check_endpoint_links(case.endpoint_links, members, relocation, request['run_file'],
                                              courses, courses_expected, stations)
        expected.update(name for link in endpoint_links for name in endpoint_link_outputs(link))
    endpoint_signals = None
    if case.endpoint_signals:
        review = case.endpoint_signals
        native.require(any(item['course_id'] == review.course_id and item.get('origin_station') and item.get('terminal_station')
                           for item in courses_expected), 'Endpoint signals need matching Course origin and termination expectations')
        endpoint_signals = check_endpoint_signals(review, frozen_project(members, relocation), courses[review.course_id])
        expected.add(endpoint_signals['output'])
    intermediate_signals = []
    if case.intermediate_signals:
        intermediate_signals = check_intermediate_signals(case.intermediate_signals,
            frozen_project(members, relocation), courses, courses_expected)
        expected.update(name for check in intermediate_signals for name in check['outputs'])
    for item in courses_expected:
        prefix = 'OT_' + basename(item['course_id'])
        expected.update(prefix + ext for ext in ('.tt', '.vt', '.st1'))
        if has_legend:
            expected.add(prefix + '.sigpos')
    for name in expected:
        basename(name.replace('*', 'preview'))
        native.require('*' not in name or name == 'OT_Protocol.*.txt', 'Only the protocol timestamp may use an output wildcard')
        if name.endswith('.sigpos'):
            native.require(has_legend, 'The verified scenario does not enable the required signal positions')
        if name.endswith(('.step1', '.step2')):
            native.require(values.get('Output Route Occ.') == '1', 'The required route authority traces are disabled')
        if name.endswith('.ins'):
            native.require(values.get('Output Instruments') == '1', 'The required native instrument output is disabled')
    occupation_files = {name for name in expected if name.startswith('OT_Occ_') and name.endswith('.occ')}
    if occupation_files:
        selected = []
        for name in relocation['documents']:
            document = Path(name).stem
            worksheet = writer.load_next_compatible(members[name])[0]
            selected.extend(f'OT_Occ_{group["name"]}.occ' for group in native_occupation_groups.records(worksheet, document)
                            if group['selected'] and group['saved_document'] == document)
        native.require(all(selected.count(name) == 1 for name in occupation_files),
                       'A required occupation file lacks one uniquely selected worksheet monitor')

    hashes = {name: native.digest(raw) for name, raw in members.items()}
    source_settings = {key: value for key, value, _ in records(draft.inputs[request['run_file']]) if key is not None}
    setting_changes = {key: {'source': source_settings.get(key), 'run_copy': value} for key, value in values.items()
                       if key is not None and key not in native.run_bundle.PATH_KEYS and source_settings.get(key) != value}
    trial = {'scenario': scenario, 'project_directory': project.as_posix(), 'evidence_directory': evidence.as_posix(),
             'output_directory': output.as_posix(), 'run_file': (project / request['run_file']).as_posix(),
             'required_outputs': sorted(expected), 'effective_input_sha256': hashes,
             'staged_members_different_from_source': sorted(name for name, sha in hashes.items()
                                                             if request['source_sha256'].get(name) != sha),
             'run_copy_option_changes': setting_changes, 'reset_actual_timetable_rows': reset,
             'relocated_archive_path_counts': relocation['path_changes'],
             'command_preview': native.scenario_command(draft.executable, project, request, members)}
    if instruments:
        trial['instrument_passages'] = instruments
    if endpoint_signals:
        trial['endpoint_signals'] = endpoint_signals
    if intermediate_signals:
        trial['intermediate_signals'] = intermediate_signals
    if endpoint_links:
        trial['endpoint_links'] = endpoint_links
    if case.marker is not None:
        trial['frozen_halt_marker'] = check_marker(root, case.marker, courses_expected, catalog, courses, members, relocation)
    if throat_passages:
        project = frozen_project(members, relocation)
        outcomes = {row['course_id']: row for row in courses_expected}
        frozen, checks = [], []
        for passage in throat_passages:
            course = outcomes.get(passage.course_id)
            native.require(course is not None and course.get('terminal_station'),
                           'Native throat passage requires the matching Course terminal')
            frozen.append(frozen_passage(project, courses[passage.course_id], passage))
            checks.append({'output_directory': output_name, 'evidence_directory': evidence_name,
                           'course_outcome': course, 'passage': passage.model_dump()})
        if case.throat_passage is not None:
            trial['frozen_throat_passage'], trial['throat_passage_check'] = frozen[0], checks[0]
        else:
            trial['frozen_throat_passages'], trial['throat_passage_checks'] = frozen, checks
    if case.route_protection is not None:
        protection = case.route_protection
        course, = [row for row in courses_expected if row['course_id'] == protection.course_id]
        native.require(course.get('terminal_station') and values.get('Output Speed/Time') == '1'
                       and values.get('Output Distance/Time') == '1',
                       'Native Route protection requires matching Course, speed and distance traces')
        trial['frozen_route_protection'] = frozen_routes(
            frozen_project(members, relocation), courses[protection.course_id], protection)
        trial['route_protection_check'] = {'output_directory': output_name, 'evidence_directory': evidence_name,
                                           'course_outcome': course, 'protection': protection.model_dump()}
    if case.join_check:
        path, sha, args = checked_json(root, case.join_check)
        native.require(sha == case.join_check_sha256, 'Queued platform verifier request SHA-256 differs')
        model = registry.tools[JOIN_TOOL].model.model_validate(args)
        native.require(model.run.output_directory == output_name and model.run.evidence_directory == evidence_name,
                       'Native platform join check does not target this run output and evidence')
        by_id = {row['course_id']: row for row in courses_expected}
        for role in (model.receiver, model.donor):
            native.require(role.model_dump(exclude_none=True) == by_id.get(role.course_id),
                           'Platform join verifier Course expectations differ from this simulation request')
        native.require(model.expected_platform is not None and has_legend,
                       'Platform join requires a specific directed platform and signal position output')
        trial['frozen_join_platform'] = check_join(model, courses, members, relocation)
        trial['post_run_tool'] = {'name': JOIN_TOOL, 'request_path': path.as_posix(), 'request_sha256': sha, 'arguments': args}
    return trial


def review(root, registry, queue, selected):
    cases = {case.id: case for case in queue.cases}
    native.require(len(cases) == len(queue.cases), 'Queue case IDs must be unique')
    native.require(not selected or set(selected) <= cases.keys(), 'A requested case ID is absent from the queue')
    report, job_paths, source_paths = [], [], []
    for case in queue.cases:
        if selected and case.id not in selected:
            continue
        case_report = {'id': case.id, 'focus': case.focus, 'manual_checks': case.manual_checks}
        try:
            path, sha, arguments = checked_json(root, case.request)
            case_report.update(request_path=path.as_posix(), request_sha256=sha)
            native.require(sha == case.request_sha256, 'Queued simulation request SHA-256 differs')
            native.require(bool(case.join_check) == bool(case.join_check_sha256), 'A verifier request requires its reviewed SHA-256')
            args = Control.model_validate(arguments)
            native.require(args.action == 'start' and args.source_sha256 and args.expectations and args.headway_sweep is None,
                           'Queue entries require a SHA-bound ordinary native start request with outcome expectations')
            draft = native.plan_start(root, args)
            job_paths.append((case.id, draft.job))
            source_paths.append(draft.project)
            case_report.update(source_directory=draft.project.as_posix(), job_directory=draft.job.as_posix(),
                               mode=draft.request['mode'], source_sha256=draft.request['source_sha256'],
                               executable_sha256=native.STOCK_EXE_SHA, dispatching_rules=draft.request.get('dispatching_rules'),
                               arguments=arguments, expectations=draft.request['expectations'])
            case_report['trials'] = [check_trial(root, registry, case, draft, scenario) for scenario in draft.request['scenarios']]
            case_report['state'] = 'ready'
        except (ValueError, OSError, KeyError, IndexError, TypeError, APIError) as exc:
            case_report.update(state='blocked', reason=str(exc)[:900])
        report.append(case_report)
    for row in report:
        job = next((path for identifier, path in job_paths if identifier == row['id']), None)
        if job is not None and (any(job.is_relative_to(path) or path.is_relative_to(job) for path in source_paths)
                                or any(identifier != row['id'] and (job.is_relative_to(path) or path.is_relative_to(job))
                                       for identifier, path in job_paths)):
            row.update(state='blocked', reason='Prospective job overlaps a reviewed source or another job')
    return report


def verify_outputs(root, trial):
    evidence = read_receipts(Path(trial['evidence_directory']))
    native.require(evidence['exit_code'] == 0 and evidence['outcome'] == 'exited'
                   and evidence['executable_sha256'] == native.STOCK_EXE_SHA
                   and evidence['input_sha256'] == trial['effective_input_sha256']
                   and evidence['command'] == trial['command_preview'], 'Original run differs from the reviewed launch or input hashes')
    output = Path(trial['output_directory'])
    native.require(output.is_relative_to(root) and Path(evidence['output_directory']) == output,
                   'Original process output path differs from the reviewed work directory')
    files = {}
    for pattern in trial['required_outputs']:
        matches = [name for name in evidence['output_sha256']
                   if (fnmatchcase(name, pattern) if pattern == 'OT_Protocol.*.txt' else name == pattern)]
        native.require(len(matches) == 1, f'Original receipt lacks one required output: {pattern}')
        name, = matches
        sha = native.digest(read_member(output, name))
        native.require(sha == evidence['output_sha256'][name], f'Original output changed after completion: {name}')
        files[name] = sha
    return files


def verify_throat_passages(registry, checks):
    results = []
    for check in checks:
        outcome = registry.envelope(THROAT_TOOL, check)
        native.require(outcome.get('ok') and outcome['result']['native_throat_passage_verified'], str(outcome.get('error')))
        results.append(outcome['result'])
    return results


def execute_case(root, registry, row, announce, *, pause=sleep):
    path, sha, arguments = checked_json(root, Path(row['request_path']).relative_to(root).as_posix())
    native.require(sha == row['request_sha256'] and arguments == row['arguments'], f'Reviewed request changed: {path.name}')
    task = arguments['job_directory']
    announce(f'{row["id"]}: starting {row["mode"]} worker at {row["job_directory"]}')
    started = registry.envelope(CONTROL_TOOL, arguments)
    native.require(started.get('ok'), str(started.get('error')))
    while True:
        delivery = registry.envelope(CONTROL_TOOL, {'action': 'status', 'job_directory': task})
        native.require(delivery.get('ok'), str(delivery.get('error')))
        state = delivery['result']
        if state['state'] in native.TERMINAL_STATES | {'worker_lost'}:
            break
        pause(2)
    result = {'worker_state': state['state'], 'native_course_expectations_verified': state.get('native_simulation_verified', False),
              'worker_result': state, 'trials': []}
    for trial in row['trials']:
        observed = {'scenario': trial['scenario']}
        try:
            observed['output_sha256'] = verify_outputs(root, trial)
            if 'post_run_tool' in trial:
                check = trial['post_run_tool']
                _, check_sha, payload = checked_json(root, Path(check['request_path']).relative_to(root).as_posix())
                native.require(check_sha == check['request_sha256'] and payload == check['arguments'], 'Reviewed verification request changed')
                outcome = registry.envelope(check['name'], payload)
                native.require(outcome.get('ok') and outcome['result']['native_same_platform_join_verified'], str(outcome.get('error')))
                observed['platform_join'] = outcome['result']
            if 'throat_passage_check' in trial:
                observed['throat_passage'] = verify_throat_passages(registry, [trial['throat_passage_check']])[0]
            if 'throat_passage_checks' in trial:
                observed['throat_passages'] = verify_throat_passages(registry, trial['throat_passage_checks'])
            if 'route_protection_check' in trial:
                outcome = registry.envelope(PROTECTION_TOOL, trial['route_protection_check'])
                native.require(outcome.get('ok') and outcome['result']['native_route_protection_verified'], str(outcome.get('error')))
                observed['route_protection'] = outcome['result']
            if 'instrument_passages' in trial:
                observed['instrument_passages'] = read_instrument_passages(
                    Path(trial['output_directory']), trial['scenario'], trial['instrument_passages'], observed['output_sha256'])
            if 'endpoint_signals' in trial:
                observed['endpoint_signals'] = read_endpoint_signals(
                    Path(trial['output_directory']), trial['endpoint_signals'], observed['output_sha256'])
            if 'intermediate_signals' in trial:
                observed['intermediate_signals'] = read_intermediate_signals(
                    Path(trial['output_directory']), trial['intermediate_signals'], observed['output_sha256'])
            if 'endpoint_links' in trial:
                from .current_archive.native_endpoint_connections import verify_endpoint_connection

                observed['endpoint_links'] = [verify_endpoint_connection(Path(trial['output_directory']), link,
                                             observed['output_sha256']) for link in trial['endpoint_links']]
            observed['passed'] = True
        except (ValueError, OSError, KeyError, IndexError, TypeError) as exc:
            observed.update(passed=False, reason=str(exc)[:900])
        result['trials'].append(observed)
    result['automatic_checks_passed'] = (state['state'] == 'completed' and result['native_course_expectations_verified']
                                         and all(trial['passed'] for trial in result['trials']))
    return result
