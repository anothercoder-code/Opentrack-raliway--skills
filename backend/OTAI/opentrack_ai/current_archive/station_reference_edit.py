"""Relocate a native paired Station Vertex while retaining physical stopping locations."""

from collections import defaultdict
import math
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, model_validator

from ..errors import APIError
from . import catalogs, course_factories, path_functions, writer
from .consist_workflow.core import summary
from .multi_document.core import ident, need
from .multi_document_tools import Inventory, MultiDocumentTools, Ref
from .network_operating_plan import resolve_visit_stop, route_trace
from .next_tools import Ordinal
from .operation_tools import Name
from .operating_plan_edit import text
from .prepare_contract import preflight
from .project_candidate_publication import ProjectSave, project_target, publish_candidate, require_external_target
from .project_workflow.relocation import relocate_project
from .saved_geometry import _movement_manifest, model_id, project_from
from .saved_station_areas import end_pair, station_model
from .tools import Input, sha
from .zero_operations.speed_preferences import index_for_course


class EndpointRebinding(Input):
    itinerary: Name
    replacement_routes: Annotated[list[Ref], Field(min_length=1, max_length=500)]
    map_itinerary_safety_margins: StrictBool = False


class DirectedEnd(Input):
    document: Name
    end_id: Ordinal


RouteMetres = Annotated[StrictInt | StrictFloat, Field(ge=0, allow_inf_nan=False)]


class EndpointCourseReview(Input):
    course_id: Name
    expected_start: DirectedEnd
    replacement_start: DirectedEnd
    expected_terminal: DirectedEnd
    replacement_terminal: DirectedEnd
    expected_route_length_m: RouteMetres
    replacement_route_length_m: RouteMetres
    expected_terminal_head_m: RouteMetres
    replacement_terminal_head_m: RouteMetres


class EndpointLinkReview(Input):
    from_course: Name
    to_course: Name
    movement: Literal['continue', 'reverse']


class FormationBerthHead(DirectedEnd):
    signal_id: Ordinal
    edge_id: Ordinal
    edge_offset_m: RouteMetres
    platform_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=100)]
    available_length_m: RouteMetres


class FormationBerthRelocation(Input):
    expected_head: FormationBerthHead
    replacement_head: FormationBerthHead


class SavedFormationEventReview(Input):
    kind: Literal['split', 'join']
    main_course: Name
    other_course: Name
    station_sign: Name
    main_visit_index: Annotated[StrictInt, Field(gt=0, le=2000)]


class EndpointFormationReview(SavedFormationEventReview):
    split_berth_relocation: FormationBerthRelocation | None = None
    join_berth_relocation: FormationBerthRelocation | None = None


class StationMainSignalRelocation(Input):
    signal_id: Ordinal
    direction: Literal['forward', 'backward']


class RelocateStationReference(ProjectSave):
    source_project: Inventory
    document: Name
    station_id: Ordinal
    from_end_id: Ordinal
    to_end_id: Ordinal
    witness_itinerary: Name
    expected_edge_ids: Annotated[list[Ordinal], Field(min_length=1, max_length=100)]
    expected_shift_m: Annotated[StrictInt, Field(ge=-2147483647, le=2147483647)]
    endpoint_rebindings: Annotated[list[EndpointRebinding], Field(max_length=100)] = Field(default_factory=list)
    endpoint_course_reviews: Annotated[list[EndpointCourseReview], Field(max_length=2000)] = Field(default_factory=list)
    endpoint_link_reviews: Annotated[list[EndpointLinkReview], Field(max_length=1000)] = Field(default_factory=list)
    endpoint_formation_reviews: Annotated[list[EndpointFormationReview], Field(max_length=1000)] = Field(default_factory=list)
    main_signal_relocation: StationMainSignalRelocation | None = None

    @model_validator(mode='after')
    def matching_endpoint_reviews(self):
        reviewed_courses = self.endpoint_course_reviews or self.endpoint_link_reviews or self.endpoint_formation_reviews
        if reviewed_courses and not (self.endpoint_rebindings or self.main_signal_relocation):
            raise ValueError('Course reviews require reviewed Itinerary endpoint rebindings')
        if self.main_signal_relocation and (self.endpoint_rebindings or len(self.expected_edge_ids) != 1):
            raise ValueError('Moving the existing main signal requires one exact adjacent Edge and its native Route rebind')
        for event in self.endpoint_formation_reviews:
            if ((event.kind == 'split' and event.join_berth_relocation is not None)
                    or (event.kind == 'join' and event.split_berth_relocation is not None)):
                raise ValueError('The berth review must match the saved split or join action')
            berth = event.split_berth_relocation or event.join_berth_relocation
            if berth is None:
                continue
            signal = self.main_signal_relocation
            if (signal is None
                    or (berth.expected_head.document, berth.expected_head.end_id, berth.expected_head.signal_id)
                    != (self.document, self.from_end_id, signal.signal_id)
                    or (berth.replacement_head.document, berth.replacement_head.end_id, berth.replacement_head.signal_id)
                    != (self.document, self.to_end_id, signal.signal_id)):
                raise ValueError('A moved formation berth must use the exact original and revised directed Ends of the same main signal')
        return self


def _select_pairs(project, args, station):
    old = args.document, args.from_end_id
    new = args.document, args.to_end_id
    pairs = [end_pair(project, args.document, project.model(key)) for key in (old, new)]
    need(all(half.contents[12].value is station and half.contents[20].value == kind
             for pair, kind in zip(pairs, (2, 1), strict=True) for half in pair),
         'Choose one reference pair and a different ordinary pair in the same station area')
    return pairs


def _prove_span(project, args, nodes, old, new, station):
    need(nodes.count(old) == nodes.count(new) == 1,
         'Witness Itinerary must traverse both selected Ends exactly once in the reviewed direction')
    first, last = nodes.index(old), nodes.index(new)
    before, after = sorted((first, last))
    span = nodes[before:after + 1]
    for key in span:
        pair = end_pair(project, args.document, project.model(key))
        need(all(half.contents[12].value is station and half.contents[20].value == (2 if key == old else 1)
                 and half.contents[10].value is None for half in pair),
             'Reference migration must follow one continuous, nonbranching station track')
    edges = [project.edge_between(a, b) for a, b in zip(span, span[1:])]
    distance = sum(project.model(edge).contents[9].values[1] for edge in edges)
    signed = distance if first < last else -distance
    need([edge[1] for edge in edges] == args.expected_edge_ids and signed == args.expected_shift_m,
         'Witness platform Edge order or signed distance differs from the reviewed migration')
    return signed


def _station_occurrences(project, nodes):
    return [key for key in nodes if project.model(key).contents[20].value == 2]


def _stop_on(project, visit, train_length_m):
    explicit = resolve_visit_stop(visit, train_length_m)
    if explicit is not None:
        return explicit
    signal = project.model(visit['end_key']).contents[11].value
    return {'signal_id': model_id(signal) if signal is not None else None, 'end_key': visit['end_key'],
            'stop_edge_key': visit['stop_edge_key'], 'distance_m': visit['distance_m'],
            'available_length_m': visit['stopping_area_length_m'], 'minimum_elapsed_s': visit['minimum_elapsed_s']}


def _affected_operating_rows(state, sign, before, after, definitions, active_names, moved, formation_berths):
    archives = {role: writer.load_next_compatible(state['files'][state['roles'][role]])[0]
                for role in ('courses', 'timetable', 'trains', 'depot', 'stations')}
    rows = defaultdict(list)
    for row in course_factories.timetable(archives['timetable']).values():
        rows[text(row, 1)].append(row)
    stock = {text(item, 0): item for item in catalogs.train_items(archives['trains'])}
    depot = {text(item, 1): item for item in catalogs.engine_items(archives['depot'])}
    stations = catalogs.station_items(archives['stations'])
    need(sign in stations, 'Selected StationModel is absent from the run StationFile')
    results, cached = [], {}
    for course in catalogs.course_items(archives['courses']):
        names = [catalogs.text(item) for item in catalogs.array(course.contents[2].value)]
        for name in (name for name in names if name in active_names):
            course_id, train = text(course, 0), text(course, 3)
            rolling_stock = summary(stock[train], depot)
            speed = str(index_for_course(state['run'], text(course, 4)))
            max_speed = rolling_stock['maximum_speed_kmh']
            key = name, speed, max_speed
            if key not in cached:
                cached[key] = tuple(route_trace(project, definitions[side][name], speed, max_speed)
                                    for side, project in enumerate((before, after)))
            original, revised = cached[key]
            plan = sorted(rows[course_id], key=lambda row: row.contents[3].value)
            signs = [text(row, 5) for row in plan]
            need(signs == [visit['station_sign'] for visit in original['visits']]
                 == [visit['station_sign'] for visit in revised['visits']],
                 f'Scheduled Course {course_id!r} must retain its original ordered Station occurrences')
            for step, (old, new) in enumerate(zip(original['visits'], revised['visits'], strict=True)):
                if old['end_key'] not in moved:
                    continue
                row = plan[step]
                need(new['end_key'] == moved[old['end_key']] and new['station_sign'] == sign,
                     'A scheduled Station occurrence resolves to a different directed track')
                track = text(row, 18)
                stop = bool(row.contents[10].value & 1)
                requested_track = new.get('stopping_track_id', new['incoming_track_id']) if stop else new['incoming_track_id']
                need(not track or track == requested_track, f'Scheduled track differs for {course_id}#{step}')
                stop_distance = None
                berth = formation_berths.get((course_id, step))
                arrival_length = rolling_stock['length_m'] if berth is None else berth['after']['arrival_length_m']
                if stop:
                    previous_stop = _stop_on(before, old, arrival_length)
                    revised_stop = _stop_on(after, new, arrival_length)
                    need(not old['halt_stop_issue'] and not new['halt_stop_issue']
                         and revised_stop['available_length_m'] is not None
                         and revised_stop['available_length_m'] >= arrival_length,
                         f'The booked formation has no reviewed stopping area for {course_id}#{step}')
                    if berth is None:
                        need(all(previous_stop[field] == revised_stop[field]
                                 for field in ('signal_id', 'end_key', 'stop_edge_key', 'distance_m'))
                             and math.isclose(previous_stop['minimum_elapsed_s'], revised_stop['minimum_elapsed_s'], abs_tol=1e-7),
                             f'Relocating the reference would change the physical stop for {course_id}#{step}')
                    else:
                        need(len(names) == 1 and (previous_stop['distance_m'], revised_stop['distance_m'])
                             == (berth['before']['head_distance_m'], berth['after']['head_distance_m']),
                             f'The formation review must cover the exact booked stop for {course_id}#{step}')
                    stop_distance = revised_stop['distance_m']
                results.append({'course_id': course_id, 'itinerary': name, 'station_index': step,
                                'train_length_m': arrival_length, 'scheduled_stop': stop,
                                'previous_reference_m': old['distance_m'], 'new_reference_m': new['distance_m'],
                                'physical_stop_m': stop_distance, 'physical_stop_unchanged': stop and berth is None})
    return results


def _replace_reference_type(before, moved, source, paths, dest_blob, document):
    root = before.roots[document]
    fingerprint = writer.fingerprint(root)
    for keys, kind in ((moved, 1), (moved.values(), 2)):
        for key in keys:
            before.model(key).contents[20].value = kind
    documents = {document: writer.dump_verified(root, before.versions[document])}
    shifted = project_from({**source, **documents}, paths, dest_blob)
    for keys, kind in ((moved, 2), (moved.values(), 1)):
        for key in keys:
            before.model(key).contents[20].value = kind
    need(writer.fingerprint(root) == fingerprint and _movement_manifest(before) == _movement_manifest(shifted),
         'Reference migration changed track geometry or unrelated native fields')
    return documents, shifted


def _replace_reference_and_signal(args, state, source, paths, dest_blob, moved, distance):
    from .saved_main_signal_location import relocate_station_main_signal

    request = {'action': 'relocate_main_signal', **args.main_signal_relocation.model_dump(),
               'from_end_id': args.from_end_id, 'to_end_id': args.to_end_id, 'expected_edge_id': args.expected_edge_ids[0]}
    changed, receipt = relocate_station_main_signal(
        source, paths, dest_blob, args.document, request, state['files'][state['roles']['courses']],
        station_id=args.station_id)
    reviewed = receipt['station_reference_rebound']
    need(dict(zip(reviewed['previous_ends'], reviewed['replacement_ends'], strict=True)) == moved
         and receipt['signal_shift_m'] == distance, 'Saved main signal moved along a different reference span')
    revised_catalog = changed.pop('$dest_catalog', dest_blob)
    endpoint_names = {row['itinerary'] for row in receipt['changed_itinerary_endpoints']}
    return changed, revised_catalog, receipt, endpoint_names


def relocate_reference(args, state):
    source = state['documents']
    paths = state['document_paths']
    dest_blob = state['files'][state['roles']['dest']]
    before = project_from(source, paths, dest_blob)
    if args.document not in source:
        raise ValueError('Select a worksheet bound by the native run')
    station = station_model(before, args.document, args.station_id)
    sign = path_functions.string(station.contents[7].value)
    original_pair, target_pair = _select_pairs(before, args, station)
    moved = {before.key(old): before.key(new) for old, new in zip(original_pair, target_pair, strict=True)}
    original_dests = {ident(item)[0]: item for item in before.dests}
    need(args.witness_itinerary in original_dests, 'Witness Itinerary is absent from the native project')
    witness, _ = before.dest_view(original_dests[args.witness_itinerary])
    old, new = (args.document, args.from_end_id), (args.document, args.to_end_id)
    distance = _prove_span(before, args, witness, old, new, station)
    courses, _ = writer.load_next_compatible(state['files'][state['roles']['courses']])
    configured = {catalogs.text(item) for course in catalogs.course_items(courses)
                  for item in catalogs.array(course.contents[2].value)}
    endpoint_report = signal_report = None
    revised_catalog = dest_blob
    if args.main_signal_relocation:
        documents, revised_catalog, signal_report, endpoint_names = _replace_reference_and_signal(
            args, state, source, paths, dest_blob, moved, distance)
        after = project_from({**source, **documents}, paths, revised_catalog)
    else:
        documents, after = _replace_reference_type(before, moved, source, paths, dest_blob, args.document)
        endpoint_names = {request.itinerary for request in args.endpoint_rebindings}
        need(len(endpoint_names) == len(args.endpoint_rebindings), 'Review each rebound Itinerary once')
    required = set()
    for name in configured:
        itinerary = original_dests[name]
        nodes, _ = before.dest_view(itinerary)
        if nodes[0] in moved or nodes[-1] in moved:
            required.add(name)
    need(required <= endpoint_names, f'Provide the Route sequence for each booked Itinerary endpoint: {sorted(required - endpoint_names)}')
    if args.endpoint_rebindings:
        from .station_reference_rebinding import rebind_station_reference_endpoints

        rewired, revised_catalog, endpoint_report = rebind_station_reference_endpoints(
            {**source, **documents}, paths, dest_blob, moved, [row.model_dump() for row in args.endpoint_rebindings])
        documents.update(rewired)
        after = project_from({**source, **documents}, paths, revised_catalog)
    for keys, kind in ((moved, 1), (moved.values(), 2)):
        for key in keys:
            saved = after.model(key)
            need(saved.contents[20].value == kind and model_id(saved.contents[12].value) == args.station_id,
                 'Native readback did not preserve paired Station association')
    revised_dests = {ident(item)[0]: item for item in after.dests}
    affected, inactive = set(), []
    changed_ends = set(moved) | set(moved.values())
    for name, itinerary in original_dests.items():
        nodes, _ = before.dest_view(itinerary)
        if not changed_ends.intersection(nodes):
            continue
        previous = _station_occurrences(before, nodes)
        expected = [moved.get(key, key) for key in previous]
        revised_nodes, _ = after.dest_view(revised_dests[name])
        revised = _station_occurrences(after, revised_nodes)
        if name in configured or name in endpoint_names:
            need(revised == expected, f'Saved Course Itinerary {name!r} would gain or lose a Station occurrence')
            if name not in endpoint_names:
                affected.add(name)
        elif revised != expected or nodes[0] in moved or nodes[-1] in moved:
            inactive.append(name)
    course_reviews, link_reviews, formation_reviews, formation_berths = [], [], [], {}
    if endpoint_names:
        from .station_reference_operating import review_endpoint_courses

        course_reviews, link_reviews, formation_reviews, formation_berths = review_endpoint_courses(
            state, before, after, moved, endpoint_names, [row.model_dump() for row in args.endpoint_course_reviews],
            [row.model_dump() for row in args.endpoint_link_reviews],
            [row.model_dump(exclude_none=True) for row in args.endpoint_formation_reviews])
    operating = _affected_operating_rows(state, sign, before, after,
                                         (original_dests, revised_dests), affected, moved, formation_berths)
    return documents, revised_catalog, {'station_sign': sign, 'document': args.document, 'signed_reference_shift_m': distance,
                    'original_reference_end_ids': [key[1] for key in moved],
                    'revised_reference_end_ids': [key[1] for key in moved.values()],
                    'unchanged_native_route_path_itinerary_graph': not (endpoint_names or signal_report),
                    'itinerary_endpoint_rebindings': endpoint_report, 'main_signal_relocation': signal_report,
                    'endpoint_course_reviews': course_reviews,
                    'endpoint_link_reviews': link_reviews, 'endpoint_formation_reviews': formation_reviews,
                    'scheduled_visit_bindings': operating, 'unassigned_changed_itineraries': sorted(inactive),
                    'native_execution_tested': False}


class StationReferenceTools(MultiDocumentTools):
    def relocate(self, args):
        target = project_target(self, args)
        state = self.load_project(args.source_project, minimum_documents=1)
        require_external_target(target, state['base'])
        run_name = args.source_project.run_file
        try:
            updated, revised_catalog, details = relocate_reference(args, state)
            members = {name: state['files'][name] for name in state['selected']}
            member = state['document_members'][args.document]
            for document, content in updated.items():
                members[state['document_members'][document]] = content
            members[state['roles']['dest']] = revised_catalog
            root = state['root']
            if target is not None:
                from .itinerary_edit_tools import EditableItineraryProject

                members, _ = relocate_project(members, source_root=root, target_root=target.as_posix(),
                                              run_file=run_name, expected_hashes={k: sha(v) for k, v in members.items()},
                                              project_type=EditableItineraryProject)
                root = target.as_posix()
            validation = preflight.check(members[run_name], lambda path: members[path.removeprefix(root + '/')])
            need(validation['passed_static_subset'], f'Native candidate preflight failed: {validation["errors"]}')
        except (ValueError, TypeError, IndexError, KeyError, OverflowError) as error:
            raise APIError('STATION_REFERENCE_RELOCATION', str(error)[:500]) from error
        result = {'preview_only': args.preview_only, 'saved': False, 'change_report': details,
                  'native_preflight_passed': True, 'updated_worksheet_sha256': sha(members[member]),
                  'updated_destination_catalog_sha256': sha(members[state['roles']['dest']]),
                  'course_and_timetable_bytes_preserved': True}
        self.recheck(state)
        if args.preview_only:
            return result
        return publish_candidate(self, target, members, result, lambda: self.recheck(state))


def tool_definitions(root):
    service = StationReferenceTools(root)
    return [('opentrack_relocate_native_station_reference',
             'Move a paired Station Vertex along one station track. Rebind reviewed Itinerary endpoints to existing '
             'native Routes and verify booked origins, head stops and reviewed fixed-formation turnrounds before saving.',
             RelocateStationReference, service.relocate, False, False)]
