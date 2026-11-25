"""Generate scheduled native Courses on an existing, explicit saved network."""

import math
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, StrictStr, model_validator

from ..errors import APIError
from . import catalogs as c, course_factories as cf, native_connections as connections, route_factory, writer as w
from .bundle_tools import CourseFields, Num, Source
from .consist_workflow.core import summary
from .first_service_templates import service_prototypes
from .itinerary_edit_tools import EditableItineraryProject
from .movement_edits import _movement_project
from .multi_document_tools import Inventory, MultiDocumentTools
from .network_composition_plan import bind_composition, configure_join_approaches
from .native_connected_platform import continued_berth_after_block
from .native_link_start import successor_start
from .native_platform_topology import same_platform_membership, station_turnout_kind, track_legs
from .native_reverse_split import reverse_origin_signal, verify_reverse_split
from .operating_plan_edit import dictionary_replace, need, set_sequence, text
from .operating_plan_edit_tools import Id, _selected_paths
from .prepare_contract import auxiliary, preflight
from .project_candidate_publication import ProjectSave, project_target, publish_candidate, require_external_target
from .project_workflow.relocation import relocate_project
from .runfile_parameters import inspect_runfile
from .shunting_workflow.core import vehicles
from .signal_type_workflow.core import MAIN, ROLES, STOP_LENGTHS, TYPES
from .stock_operations import CATEGORY_LAYOUT
from .tools import Input, sha
from .zero_operations.speed_preferences import read_train_types


AbsoluteSeconds = Annotated[StrictInt, Field(ge=0, le=366 * 86400)]
DirectedStationEnd = Annotated[tuple[Id, Annotated[StrictInt, Field(ge=0, le=2**31 - 1)]], Field(strict=False)]
HEAD_FACTORS = {TYPES['stop_head']: 0, TYPES['stop_center']: 0.5, TYPES['stop_tail']: 1}
HALT_TYPES = HEAD_FACTORS.keys() | STOP_LENGTHS.keys()


class Visit(Input):
    station_sign: Id
    arrival_s: AbsoluteSeconds
    departure_s: AbsoluteSeconds
    stop: StrictBool
    track_id: StrictStr = ''
    primary_reference_end: DirectedStationEnd | None = Field(
        default=None, description='Exact worksheet and directed End ID for this row of the primary Itinerary.',
    )


class Service(Input):
    course_id: Id
    train: Id
    itinerary: Id
    alternative_itineraries: list[Id] = Field(
        default_factory=list, max_length=32,
        description='Additional native itinerary names in decreasing priority after the primary itinerary.',
    )
    speed_type: Id
    visits: Annotated[list[Visit], Field(min_length=2, max_length=1000)]
    controls: CourseFields = Field(default_factory=CourseFields)

    @model_validator(mode='after')
    def explicit_speed_type(self):
        if 'speed_type' in self.controls.model_fields_set:
            raise ValueError('Set speed_type only on the Course plan')
        return self


class Turnround(Input):
    from_course: Id
    to_course: Id
    movement: Literal['reverse', 'continue'] = 'reverse'


class ReverseSplit(Input):
    parent_head_end: DirectedStationEnd
    parent_head_signal_id: Annotated[StrictInt, Field(ge=0, le=2**31 - 1)]
    child_origin_end: DirectedStationEnd
    child_origin_signal_id: Annotated[StrictInt, Field(ge=0, le=2**31 - 1)]
    detached_edge_id: Annotated[StrictInt, Field(ge=0, le=2**31 - 1)]
    retained_edge_id: Annotated[StrictInt, Field(ge=0, le=2**31 - 1)]


class CompositionEvent(Input):
    kind: Literal['split', 'join']
    main_course: Id
    other_course: Id
    station_sign: Id
    main_visit_index: Annotated[StrictInt, Field(
        ge=1, le=998, description='Zero-based timetable row of the main Course, required for a repeated station sign.'
    )] | None = None
    occupied_entry_speed_kmh: Annotated[Num, Field(gt=0, le=1000)] | None = None
    reverse_split: ReverseSplit | None = None

    @model_validator(mode='after')
    def explicit_reverse_split_visit(self):
        if self.reverse_split is not None and (self.kind != 'split' or self.main_visit_index is None):
            raise ValueError('A reverse split requires an explicitly selected intermediate split visit')
        return self


class GenerateNetworkPlan(ProjectSave):
    source_project: Inventory
    course_template_id: Id
    timetable_template_key: Annotated[StrictStr, Field(min_length=3, max_length=230)]
    course_template_archive: Source | None = None
    timetable_template_archive: Source | None = None
    mode: Literal['append', 'replace_plan'] = 'append'
    courses: Annotated[list[Service], Field(min_length=1, max_length=1000)]
    turnrounds: Annotated[list[Turnround], Field(max_length=1000)] = Field(default_factory=list)
    composition_events: Annotated[list[CompositionEvent], Field(max_length=64)] = Field(default_factory=list)
    connection_template: Source | None = None

    @model_validator(mode='after')
    def source_for_links(self):
        if bool(self.turnrounds or self.composition_events) != (self.connection_template is not None):
            raise ValueError('A native Connection template is required exactly when declaring train linkage')
        return self

    @model_validator(mode='after')
    def first_service_shape_pair(self):
        has_course = self.course_template_archive is not None
        has_timetable = self.timetable_template_archive is not None
        if has_course != has_timetable or (has_course and self.mode != 'append'):
            raise ValueError('Supply both first-service shape archives in append mode')
        return self


def _opposing_continued_block(end):
    signal = end.contents[11].value
    if signal is None or signal.contents[8].values[:2] != [TYPES['main'], ROLES['block']]:
        return False
    routes = route_factory.wrapper(end.contents[15].value, 'OTRouteList')
    # The native station-brake scan takes the signal of the directed End.
    # Admit this opposite through block only when the saved graph proves its continuation.
    return len(routes) == 1 and routes[0].contents[5].values[4] > 0


def _platform_block_continuation(project, nodes, index, station, track):
    """Recognize an internal through block before a halt marker and the real exit."""
    key = nodes[index]
    end = project.model(key)
    signal = end.contents[11].value
    opposite = project.model(project.related(key))
    if (not track or signal is None or signal.contents[8].values[:2] != [TYPES['main'], ROLES['block']]
            or end.contents[7].value is opposite.contents[7].value):
        return False
    if continued_berth_after_block(project, nodes, index, track):
        return True
    routes = route_factory.wrapper(end.contents[15].value, 'OTRouteList')
    if len(routes) != 1 or routes[0].contents[5].values[4] != -1 or not routes[0].contents[11].value & 1:
        return False
    continuation = project.route_view(routes[0])
    if len(continuation) < 3 or continuation != nodes[index:index + len(continuation)]:
        return False
    exit_end = project.model(continuation[-1])
    exit_signal = exit_end.contents[11].value
    if (exit_end.contents[20].value != 2 or exit_end.contents[12].value is not station or exit_signal is None
            or exit_signal.contents[8].values[0] not in MAIN or exit_signal.contents[8].values[1] != ROLES['exit']):
        return False

    # The native scan (0063f6f0) only considers a non-exit main as a fallback
    # after a StationEndModel. Require ordinary pairs until the actual exit.
    has_halt = False
    for a, b in zip(continuation, continuation[1:]):
        arrival, departure = (project.model(k) for k in (a, project.related(a)))
        if (any(w.kind(half) != 'OTEndModel' or half.contents[12].value is not station
                or half.contents[20].value != 1 or half.contents[9].value is None or half.contents[10].value is not None
                for half in (arrival, departure)) or text(project.model(project.edge_between(a, b)), 19) != track):
            return False
        if a != key:
            marker = arrival.contents[11].value
            if marker is not None:
                if marker.contents[8].values[0] not in HALT_TYPES:
                    return False
                has_halt = True
    return has_halt


def _track_segment(project, previous, key, speed_index, vehicle_speed):
    edge_key = project.edge_between(previous, key)
    edge = project.model(edge_key)
    length = edge.contents[9].values[1]
    need(type(length) is int and length > 0, 'Positive native Edge length required')
    departure = project.model(project.actual_related(previous))
    endpoints = edge.contents[7].value, edge.contents[8].value
    need((departure, project.model(key)) in (endpoints, endpoints[::-1]),
         'Directed Edge endpoints differ from expanded movement')
    elapsed = 0
    limit = effective = None
    if speed_index is not None:
        speeds = cf.dictionary(edge.contents[16].value)
        need(speed_index in speeds, 'Course speed type does not exist on a traversed native Edge')
        speed = c.shape(speeds[speed_index], 'OTSpeed', 0, ['@', 'i', 'i', 'i'])
        limit = speed.contents[1 if departure is endpoints[0] else 2].value
        need(type(limit) is int and 0 < limit <= 10000, 'Positive native directional speed required')
        effective = min(limit, vehicle_speed)
        elapsed = length * 3.6 / effective
    return {'edge_key': edge_key, 'from_end_key': previous, 'to_end_key': key, 'length_m': length,
            'track_id': text(edge, 19), 'minimum_elapsed_s': elapsed,
            'directional_speed_limit_kmh': limit, 'effective_speed_limit_kmh': effective}


def _point_on_platform(profile, marker, train_length):
    kind = marker['signal_type']
    factor = HEAD_FACTORS.get(kind, 0)
    offset = factor * train_length
    head = marker['platform_position_m'] + offset
    need(head <= profile['length_m'], 'Selected halt marker would place the train head beyond the directed platform exit')
    point = {
        'signal_id': marker['signal_id'], 'end_key': marker['end_key'], 'signal_type': kind,
        'marker_distance_m': profile['start_distance_m'] + marker['platform_position_m'],
        'distance_m': profile['start_distance_m'] + head, 'head_offset_from_marker_m': offset,
        'available_length_m': head, 'target_speed_kmh': 0,
        'minimum_elapsed_s': profile['start_elapsed_s'], 'stop_edge_key': None, 'stop_edge_length_m': None,
        'head_edge_offset_m': None, 'track_id': None, 'head_end_key': marker['end_key'],
        'directional_speed_limit_kmh': None, 'effective_speed_limit_kmh': None,
    }
    traversed = 0
    for segment in profile['segments']:
        length = segment['length_m']
        distance_on_edge = min(length, head - traversed)
        if distance_on_edge <= 0:
            break
        point['minimum_elapsed_s'] += segment['minimum_elapsed_s'] * distance_on_edge / length
        point.update(stop_edge_key=segment['edge_key'], stop_edge_length_m=length,
                     head_edge_offset_m=distance_on_edge, track_id=segment['track_id'],
                     head_end_key=segment['to_end_key'] if distance_on_edge == length else None,
                     directional_speed_limit_kmh=segment['directional_speed_limit_kmh'],
                     effective_speed_limit_kmh=segment['effective_speed_limit_kmh'])
        traversed += length
    return point


def _platform_profile(segments, markers, exit_signal, exit_end, distance, seconds):
    positions = []
    length = 0
    for segment in segments:
        positions.append(length)
        length += segment['length_m']
    marks = [{'signal_type': kind, 'signal_id': identifier, 'end_key': segments[index]['from_end_key'],
              'platform_position_m': positions[index]} for index, (kind, identifier) in markers]
    profile = {'segments': segments, 'markers': marks, 'length_m': length, 'start_distance_m': distance,
               'start_elapsed_s': seconds,
               'exit': {'signal_type': exit_signal[0], 'signal_id': exit_signal[1], 'end_key': exit_end,
                        'platform_position_m': length}}
    default_stop = _point_on_platform(profile, profile['exit'], 0)
    general = [mark for mark in marks if mark['signal_type'] in HEAD_FACTORS]
    head = (_point_on_platform(profile, general[-1], 0)
            if general and general[-1]['signal_type'] == TYPES['stop_head'] else None)
    selected = head or default_stop
    return {'default_stop': default_stop, 'head_stop': head, 'halt_platform': profile if marks else None,
            'stop_edge_key': selected['stop_edge_key'], 'stop_edge_length_m': selected['stop_edge_length_m'],
            'stopping_track_id': selected['track_id'], 'stopping_area_edge_keys': [row['edge_key'] for row in segments],
            'stopping_area_length_m': length}


def resolve_visit_stop(location, train_length_m):
    profile = location.get('halt_platform')
    if profile is None:
        if location.get('unsigned_terminal_buffer'):
            return None
        return location.get('head_stop') or location.get('default_stop')
    from .saved_halt_location import _selected_marker

    markers = profile['markers']
    selected = _selected_marker([{'signal_id': index, 'signal_type': mark['signal_type']}
                                 for index, mark in enumerate(markers)], train_length_m, None)
    if selected is None and location.get('unsigned_terminal_buffer'):
        return None
    mark = markers[selected] if selected is not None else profile['exit']
    return _point_on_platform(profile, mark, train_length_m)


def _separate_platform_stop(project, nodes, index, distance, seconds, speed_index, vehicle_speed):
    """Resolve one exit on a contiguous platform whose reference vertex has no signal."""
    def grouped(first_index):
        first, last = nodes[first_index:first_index + 2]
        entry = project.model(first)
        departure = project.model(project.actual_related(first))
        target = project.model(last)
        area = entry.contents[12].value
        return (all(end.contents[20].value in (1, 2) for end in (entry, departure, target))
                and same_platform_membership(project, first, last, area, departure.contents[12].value)
                and departure.contents[12].value is target.contents[12].value
                and (len(track_legs(departure)) == 1
                     or station_turnout_kind(project, nodes, first_index) in ('entry', 'interior'))
                and (len(track_legs(target)) == 1
                     or station_turnout_kind(project, nodes, first_index + 1) in ('exit', 'interior')))

    lower = upper = index
    while lower > 0 and grouped(lower - 1):
        lower -= 1
    while upper < len(nodes) - 1 and grouped(upper):
        upper += 1
    region = nodes[lower:upper + 1]
    anchor = index - lower
    signals = {i: signal for i, node in enumerate(region)
               if (signal := project.model(node).contents[11].value) is not None}
    exits = [i for i, signal in signals.items()
             if signal.contents[8].values[0] in MAIN and signal.contents[8].values[1] == 4]
    if len(exits) != 1:
        return {'halt_stop_issue': 'Separate station reference requires one directed exit signal on its contiguous platform'}
    exit_index, = exits
    earlier_mains = [i for i, signal in signals.items() if i < exit_index
                     and signal.contents[8].values[0] in MAIN]
    entry_index = max(earlier_mains, default=-1) + 1
    if not entry_index < exit_index or anchor < entry_index:
        return {'halt_stop_issue': 'Separate station reference is outside the reviewed platform approach'}
    halts = [(i, sig) for i, sig in signals.items()
             if i >= entry_index and sig.contents[8].values[0] in HALT_TYPES]
    if any(i >= exit_index for i, _ in halts):
        return {'halt_stop_issue': 'Separate station reference requires all directed halt markers before its one exit'}
    segments = [_track_segment(project, a, b, speed_index, vehicle_speed) for a, b in zip(region, region[1:])]
    preceding = segments[entry_index:anchor]
    start_m = distance - sum(segment['length_m'] for segment in preceding)
    start_s = seconds - sum(segment['minimum_elapsed_s'] for segment in preceding)
    exit_signal = signals[exit_index]
    return _platform_profile(segments[entry_index:exit_index],
                             [(i - entry_index, (sig.contents[8].values[0], sig.contents[0].value)) for i, sig in halts],
                             (exit_signal.contents[8].values[0], exit_signal.contents[0].value),
                             region[exit_index], start_m, start_s)


def _terminal_buffer_scope(project, nodes):
    """Recognize a final, station-owned single-track physical buffer and its reference."""
    key = nodes[-1]
    end, pair = (project.model(ref) for ref in (key, project.related(key)))
    area = end.contents[12].value
    if (w.kind(area) != 'OTStationModel' or pair.contents[12].value is not area
            or any(half.contents[20].value != 1 for half in (end, pair))
            or len(track_legs(end)) != 1 or not route_factory.physical_buffer(end, pair)):
        return None
    signal = end.contents[11].value
    if signal is not None and signal.contents[8].values[:2] != [TYPES['main'], ROLES['exit']]:
        return None
    first = len(nodes) - 1
    while first > 0:
        key_before = nodes[first - 1]
        related = project.related(key_before)
        if key_before[0] != key[0] or related != project.actual_related(key_before):
            break
        halves = project.model(key_before), project.model(related)
        if any(w.kind(half) != 'OTEndModel' or half.contents[12].value is not area or len(track_legs(half)) != 1
               for half in halves):
            break
        kind = halves[0].contents[20].value
        if kind not in (1, 2) or kind != halves[1].contents[20].value:
            break
        first -= 1
        incoming_signal = halves[0].contents[11].value
        if incoming_signal is not None and incoming_signal.contents[8].values[0] in MAIN:
            break
    terminal = len(nodes) - 1
    references = [i for i in range(first, terminal) if project.model(nodes[i]).contents[20].value == 2]
    if (first > terminal - 2 or len(references) > 1 or references == [first]
            or signal is not None and not references):
        return None
    return first, references[0] if references else terminal


def _terminal_buffer_stop(project, nodes, entry, distance, seconds, speed_index, vehicle_speed, *, reference):
    chain = nodes[entry:]
    segments = [_track_segment(project, first, second, speed_index, vehicle_speed) for first, second in zip(chain, chain[1:])]
    signals = [project.model(key).contents[11].value for key in chain]
    markers = [(index, (sig.contents[8].values[0], sig.contents[0].value))
               for index, sig in enumerate(signals[:-1]) if sig is not None and sig.contents[8].values[0] in HALT_TYPES]
    end = signals[-1]
    exit_signal = (end.contents[8].values[0], end.contents[0].value) if end is not None else (None, None)
    start_m = distance - sum(segment['length_m'] for segment in segments)
    start_s = seconds - sum(segment['minimum_elapsed_s'] for segment in segments)
    info = _platform_profile(segments, markers, exit_signal, chain[-1], start_m, start_s)
    return {**info, 'physical_buffer_end': chain[-1], 'unsigned_terminal_buffer': end is None,
            'geometric_terminal_reference': reference == len(nodes) - 1}


def route_trace(project, itinerary, speed_index=None, vehicle_speed=None, *, reviewed_reverse_origin=None):
    def signal_on(end):
        signal = end.contents[11].value
        return None if signal is None else (signal.contents[8].values[0], signal.contents[0].value)

    nodes, paths = project.dest_view(itinerary)
    need(2 <= len(nodes) <= 10000, 'Select a finite expanded Itinerary with at least two directed Ends')
    if reviewed_reverse_origin is not None:
        need(nodes[0] == reviewed_reverse_origin, 'The reviewed reverse split origin is not the Itinerary first End')
        reverse_origin_signal(project, reviewed_reverse_origin)
    buffer_scope = _terminal_buffer_scope(project, nodes)
    buffer_reference = None if buffer_scope is None else buffer_scope[1]
    visits, edges, node_distances = [], [], [0]
    platform_approach = []
    area_station = None
    distance = seconds = 0
    previous = None
    for node_index, key in enumerate(nodes):
        end = project.model(key)
        approach = None
        if previous is not None:
            approach = _track_segment(project, previous, key, speed_index, vehicle_speed)
            approach['start_distance_m'] = distance
            approach['start_elapsed_s'] = seconds
            half = project.model(project.actual_related(previous))
            seconds += approach['minimum_elapsed_s']
            distance += approach['length_m']
            edges.append(approach['edge_key'])
            node_distances.append(distance)
            entry = project.model(previous)
            station = entry.contents[12].value
            incoming_station = half.contents[12].value
            same_worksheet = previous[0] == key[0]
            directed_signal = signal_on(entry)
            reverse_signal = signal_on(half)
            continues_platform = (directed_signal is not None and directed_signal[0] in MAIN and same_worksheet
                                  and station is not None and area_station is station and platform_approach
                                  and platform_approach[-1][0]['track_id'] == approach['track_id']
                                  and _platform_block_continuation(project, nodes, node_index - 1, station,
                                                                   approach['track_id']))
            simple_pair = all(len(track_legs(model)) == 1 for model in (entry, half))
            turnout = None if simple_pair else station_turnout_kind(project, nodes, node_index - 1)
            facing_platform_exit = (turnout == 'entry' and reverse_signal is not None and reverse_signal[0] in MAIN
                                    and half.contents[11].value.contents[8].values[1] == ROLES['exit'])
            ordinary_pair = (
                same_platform_membership(project, previous, key, station, incoming_station)
                and all(model.contents[20].value == 1 for model in (entry, half))
                and (simple_pair or turnout in ('entry', 'interior'))
                and (directed_signal is None or directed_signal[0] in HALT_TYPES or continues_platform)
                and (reverse_signal is None or reverse_signal[0] in HALT_TYPES
                     or facing_platform_exit or (same_worksheet and _opposing_continued_block(half)))
            )
            if station is not area_station or not ordinary_pair:
                platform_approach.clear()
            area_station = incoming_station if ordinary_pair else None
            if ordinary_pair:
                platform_approach.append((approach, None if continues_platform else directed_signal))
        if end.contents[20].value == 2 or node_index == buffer_reference or node_index == 0 and key == reviewed_reverse_origin:
            station = end.contents[12].value
            need(station is not None and w.kind(station) == 'OTStationModel', 'Unbound station reference End')
            stop_edge = None
            if approach is not None and node_index != buffer_reference:
                same_sheet_approach = (same_worksheet and entry.contents[20].value == 1
                                       and entry.contents[12].value is station)
                cross_sheet_approach = not same_worksheet and ordinary_pair and incoming_station is station
                if (same_sheet_approach or cross_sheet_approach) and end.contents[11].value is not None:
                    stop_edge = approach
            stop_info = {'stop_edge_key': None, 'stop_edge_length_m': None, 'stopping_area_edge_keys': [],
                         'stopping_area_length_m': None, 'head_stop': None, 'halt_stop_issue': None}
            if stop_edge is not None:
                reviewed = platform_approach if area_station is station else [(stop_edge, None)]
                segments = [segment for segment, _ in reviewed]
                marks = [(i, signal) for i, (_, signal) in enumerate(reviewed) if signal is not None]
                first = segments[0]
                stop_info.update(_platform_profile(segments, marks, signal_on(end), key,
                                                   first['start_distance_m'], first['start_elapsed_s']))
                if marks and (signal_on(end)[0] not in MAIN or end.contents[11].value.contents[8].values[1] != 4):
                    stop_info['halt_stop_issue'] = 'A directed halt marker requires the reviewed main exit signal'
                for next_index in range(node_index + 1, len(nodes)):
                    next_key = nodes[next_index]
                    next_end = project.model(next_key)
                    if (next_end.contents[20].value != 1
                            or not same_platform_membership(project, key, next_key, station, next_end.contents[12].value)):
                        break
                    next_signal = signal_on(next_end)
                    if next_signal and next_signal[0] in HALT_TYPES:
                        stop_info['halt_stop_issue'] = 'A directed halt marker beyond the station reference needs a different stopping contract'
                        break
            visit = {
                'station_sign': text(station, 7), 'end_key': key, 'previous_end_key': previous,
                'incoming_track_id': approach['track_id'] if approach else None,
                'distance_m': distance, 'minimum_elapsed_s': seconds, **stop_info,
            }
            if node_index != buffer_reference and end.contents[11].value is None and 0 < node_index < len(nodes) - 1:
                visit.update(_separate_platform_stop(project, nodes, node_index, distance, seconds,
                                                     speed_index, vehicle_speed))
            visits.append(visit)
        previous = key
    final_reference = nodes[-1] if buffer_scope is None else nodes[buffer_reference]
    need(len(visits) >= 2 and visits[0]['end_key'] == nodes[0] and visits[-1]['end_key'] == final_reference,
         'Itinerary must begin at a native station reference and finish at a native station reference or reviewed physical buffer')
    if buffer_scope is not None:
        visits[-1].update(_terminal_buffer_stop(project, nodes, buffer_scope[0], distance, seconds, speed_index,
                                                vehicle_speed, reference=buffer_reference))
    return {
        'visits': visits, 'route_length_m': distance, 'minimum_edge_travel_s': seconds,
        'path_count': len(paths), 'edges': edges, 'node_count': len(nodes),
        'repeated_end_count': len(nodes) - len(set(nodes)), 'closed_walk': nodes[0] == nodes[-1],
        '_directed_nodes': nodes, '_node_distances_m': node_distances,
    }


def _planned_rows(entry, trace, consist, stations, template_key, lower, upper, *, split_origin_stop=False,
                  deferred_formation_length=False, primary=True, formation_by_visit=None, resolved_visits=None,
                  verified_split_berth_indices=(), verified_join_berth_indices=()):
    visits = entry['visits']
    need([v['station_sign'] for v in visits] == [v['station_sign'] for v in trace['visits']],
         'Every native station occurrence must be supplied in exact itinerary order')
    rows = []
    previous = None
    previous_elapsed = None
    for index, (v, location) in enumerate(zip(visits, trace['visits'])):
        a, d = v['arrival_s'], v['departure_s']
        need(v['station_sign'] in stations, 'Planned station is missing from native station catalog')
        need(lower <= a <= d < upper, 'Planned arrival/departure is outside run window or inverted')
        arrival_length, departure_length = (formation_by_visit[index] if formation_by_visit is not None
                                            else (consist['length_m'], consist['length_m']))
        stop_point = None
        if v['stop'] and index > 0:
            need(not location.get('halt_stop_issue'), location.get('halt_stop_issue'))
            stop_point = resolve_visit_stop(location, arrival_length)
            need(not location.get('unsigned_terminal_buffer') or stop_point is not None,
                 'A booked stop at an unsigned physical buffer requires an eligible native halt marker')
        if stop_point is not None:
            track = stop_point.get('track_id', location['incoming_track_id'])
        elif v['stop']:
            track = location.get('stopping_track_id', location['incoming_track_id'])
        else:
            track = location['incoming_track_id']
        need(not v.get('track_id') or v['track_id'] == track or index == 0 and split_origin_stop,
             'Requested track must match the saved incoming Edge of the directed occurrence')
        anchor = v.get('primary_reference_end') if primary else None
        need(anchor is None or tuple(anchor) == location['end_key'],
             f'Primary directed station reference differs from the saved occurrence at timetable row {index}')
        elapsed = stop_point['minimum_elapsed_s'] if stop_point is not None else location['minimum_elapsed_s']
        minimum = None if previous_elapsed is None else elapsed - previous_elapsed
        if previous is None:
            need(a == d and v['stop'] == split_origin_stop,
                 'Origin is an unambiguous departure, or a stopped child activated by an explicit split')
        else:
            need(minimum >= -1e-6 and a > previous and a - previous + 1e-6 >= minimum,
                 'Planned leg violates the saved directed Edge/vehicle speed lower bound')
        if v['stop'] and index > 0:
            area_length = stop_point['available_length_m'] if stop_point is not None else location['stopping_area_length_m']
            required_length = max(arrival_length, departure_length)
            need(area_length is not None and (deferred_formation_length or area_length >= required_length),
                 f'Directed station stopping area is absent or too short for visit {index} at {v["station_sign"]}')
            if (arrival_length != departure_length and stop_point is not None
                    and index not in verified_split_berth_indices and index not in verified_join_berth_indices):
                need(stop_point['head_edge_offset_m'] is not None and stop_point['head_edge_offset_m'] >= required_length,
                     f'Composition must fit behind its actual head point on the directed stopping Edge at visit {index}')
            need(index == len(visits) - 1 or d > a, 'Intermediate stop requires positive planned dwell')
        elif not v['stop']:
            need(a == d, 'Pass-through occurrence cannot dwell')
        need(index < len(visits) - 1 or a == d, 'Terminal cannot carry a departure dwell; link a successor Course')
        ad, ac = divmod(a, 86400)
        dd, dc = divmod(d, 86400)
        rows.append({
            'template_key': template_key, 'station_sign': v['station_sign'],
            'arrival': _clock(ac), 'departure': _clock(dc), 'arrival_day_offset': ad, 'departure_day_offset': dd,
            'stop_at_station': v['stop'], 'timing_station': True, 'dwell_s': d - a, 'track_id': v.get('track_id', ''),
            'mean_delay_s': 0, 'distribution_name': '', 'delta_mass_t': 0, 'interval_reference_course_id': None,
            'interval_offset_s': 0,
        })
        if resolved_visits is not None:
            observed = {key: value for key, value in location.items() if key != 'halt_platform'}
            if stop_point is not None:
                observed.update(stop_edge_key=stop_point['stop_edge_key'],
                                stop_edge_length_m=stop_point['stop_edge_length_m'],
                                stopping_track_id=track)
            resolved_visits.append({
                **observed, 'visit_index': index, 'planned': v,
                'arrival_consist_length_m': arrival_length, 'departure_consist_length_m': departure_length,
                'stopping_point': stop_point, 'event_distance_m': (
                    stop_point['distance_m'] if stop_point is not None else location.get('distance_m')),
                'event_minimum_elapsed_s': elapsed, 'leg_minimum_elapsed_s': minimum,
            })
        previous = d
        previous_elapsed = elapsed
    return rows


def _clock(seconds):
    return f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}'


def _composition_visit_lengths(args, stock_by_course):
    """Project incoming and outgoing lengths for the same visits later bound natively."""
    courses = {item.course_id: item for item in args.courses}
    indexed = {}
    for event in args.composition_events:
        need(event.main_course in courses and event.other_course in courses and event.main_course != event.other_course,
             'A composition event requires two distinct planned Courses')
        plan = courses[event.main_course]
        if event.main_visit_index is None:
            positions = [i for i, v in enumerate(plan.visits) if v.station_sign == event.station_sign]
            need(len(positions) == 1, 'Choose one exact main Course composition visit')
            index, = positions
        else:
            index = event.main_visit_index
        need(0 < index < len(plan.visits) - 1 and plan.visits[index].station_sign == event.station_sign,
             'Composition must bind an exact intermediate main Course visit')
        changes = indexed.setdefault(event.main_course, {})
        need(index not in changes, 'A planned main Course visit can have only one composition event')
        length = stock_by_course[event.other_course]['length_m']
        changes[index] = length if event.kind == 'join' else -length
    schedules = {}
    for cid, changes in indexed.items():
        current = stock_by_course[cid]['length_m']
        schedule = []
        for index in range(len(courses[cid].visits)):
            outgoing = current + changes.get(index, 0)
            need(outgoing > 0, 'Composition leaves no moving formation for the main Course')
            schedule.append((current, outgoing))
            current = outgoing
        schedules[cid] = schedule
    return schedules


def _turnround_commands(plan_by_course, link_pairs, projected_transfers):
    outgoing, incoming, result = set(), set(), []
    for link in link_pairs:
        before = link['from_course']
        after = link['to_course']
        need(before in plan_by_course and after in plan_by_course and before != after
             and before not in outgoing and after not in incoming,
             'Physical train links require one distinct predecessor/successor per Course')
        a, b = plan_by_course[before], plan_by_course[after]
        stop, start = a['visits'][-1], b['visits'][0]
        same_stock = a['train'] == b['train'] or (before, after) in projected_transfers
        need(stop['stop'] and same_stock, 'Linked services require a terminal stop and matching successor stock')
        minimum = a['minimum_turnround_s']
        need(start['departure_s'] > stop['arrival_s'] and start['departure_s'] - stop['arrival_s'] >= minimum,
             'Linked turnround requires a forward gap at least the saved Category minimum')
        incoming.add(after)
        outgoing.add(before)
        result.append(connections.Command('turnround_to', before, len(a['visits']) - 1, after))
    return result


def _projected_turnrounds(links, composition, plans, trains, depot):
    events = composition['events'] if composition else []
    active = {event['main_course']: event for event in events}
    detached = {event['other_course'] for event in events if event['kind'] == 'split'}
    consumed = {event['other_course'] for event in events if event['kind'] == 'join'}
    receipts = {}

    def key(row):
        return (row['kind'], row['name'] if row['kind'] == 'engine' else row['signature_sha256'])

    for link in links:
        before, after = link['from_course'], link['to_course']
        need(before not in consumed and after not in detached,
             'A terminal transfer cannot reuse a join-supply exit or a split-child origin')
        if before not in active:
            continue
        a, b = plans[before], plans[after]
        previous, successor = trains[a['train']], trains[b['train']]
        event = active[before]
        remaining = event['projected_main_formation']
        declared = [row[3] for row in vehicles(successor, depot)]
        reverse = link['movement'] == 'reverse'
        if reverse:
            need(remaining[0]['kind'] == remaining[-1]['kind'] == 'engine',
                 'Post-composition reversal requires a powered vehicle at both ends of the retained formation')
        ordered = remaining[::-1] if reverse else remaining
        need(text(previous, 3) == text(successor, 3) and [key(row) for row in ordered] == [key(row) for row in declared],
             'Successor must declare the exact ordered post-composition stock for its travel direction and the same Category')
        receipts[(before, after)] = {'from_course': before, 'to_course': after, 'movement': link['movement'],
                                     'from_declared_train': a['train'], 'to_declared_train': b['train'],
                                     'last_composition_row': event['main_row'],
                                     'projected_length_m': event['projected_main_length_m'],
                                     'predecessor_formation': remaining,
                                     'formation': [{**row, 'accounting_index': index} for index, row in enumerate(ordered, 1)]}
    return receipts


def _review_reverse_splits(args, project, itineraries, stock_by_course):
    services = {item.course_id: item for item in args.courses}
    receipts = {}
    for event in args.composition_events:
        review = event.reverse_split
        if review is None:
            continue
        pair = event.main_course, event.other_course
        need(sum(bool(set(pair).intersection((item.main_course, item.other_course)))
                 for item in args.composition_events) == 1,
             'A reviewed reverse split needs an isolated parent and child formation event')
        mother, child = (services[cid] for cid in pair)
        need(not mother.alternative_itineraries and not child.alternative_itineraries
             and mother.visits[event.main_visit_index].stop and child.visits[0].stop
             and child.visits[0].primary_reference_end == review.child_origin_end,
             'Review one saved Itinerary per reverse split Course and bind the exact child first timetable End')
        before, after = itineraries[mother.itinerary], itineraries[child.itinerary]
        receipts[pair] = verify_reverse_split(
            project, event, before, after, route_trace(project, before),
            route_trace(project, after, reviewed_reverse_origin=review.child_origin_end),
            stock_by_course[pair[0]], stock_by_course[pair[1]], event.main_visit_index,
        )
    return receipts


def build_catalogs(state, project, args, connection_template=None, *, first_service_archives=None):
    roles = state['roles']
    blobs = state['files']
    roots = {role: w.load_next_compatible(blobs[name]) for role, name in roles.items()}
    course_list, course_version = roots['courses']
    timetable, timetable_version = roots['timetable']
    course_prototype = timetable_prototype = None
    if first_service_archives is not None:
        need(args.mode == 'append' and course_list.contents[0].value == 17
             and not c.course_items(course_list) and not cf.timetable(timetable),
             'First-service shape archives require empty current destination Course and Timetable catalogues in append mode')
        course_prototype, timetable_prototype = service_prototypes(
            *first_service_archives, args.course_template_id, args.timetable_template_key)
    trains = roots['trains'][0]
    depot = {text(item, 1): item for item in c.engine_items(roots['depot'][0])}
    known_trains = {text(item, 0): item for item in c.train_items(trains)}
    categories = {text(c.shape(item, 'OTTrainCategory', 19, CATEGORY_LAYOUT), 1): item
                  for item in c.array(trains.contents[1].value)}
    stations = c.station_items(roots['stations'][0])
    itineraries = {text(item, 1): item for item in project.dests}
    train_types = {value.casefold(): str(index) for index, value in enumerate(read_train_types(state['run']))}
    rt = inspect_runfile(auxiliary.core_bytes(auxiliary.records(state['run'])))
    need(rt['editable'], 'Explicit valid original run window required')
    lower, upper = rt['numeric']['start_seconds'], rt['numeric']['stop_seconds']
    if args.mode == 'replace_plan':
        need(not c.array(course_list.contents[1].value) and not c.array(course_list.contents[2].value)
             and not any(name.endswith('.otsimcor') for name in state['selected']),
             'Replace plan requires no existing Incidents, Incident Sets or selected Train Diagram data')
    need(sum(len(item.visits) for item in args.courses) <= 20000, 'Maximum 20000 explicit station visits per plan')
    plan_by_course, traces, details, trace_cache = {}, {}, [], {}
    split_origins = {item.other_course for item in args.composition_events if item.kind == 'split'}
    linked = {cid for event in args.composition_events for cid in (event.main_course, event.other_course)}
    linked.update(cid for event in args.turnrounds for cid in (event.from_course, event.to_course))
    train_summaries = {name: summary(known_trains[name], depot) for name in {item.train for item in args.courses}}
    stock_by_course = {item.course_id: train_summaries[item.train] for item in args.courses}
    lengths = _composition_visit_lengths(args, stock_by_course)
    reverse_splits = _review_reverse_splits(args, project, itineraries, stock_by_course)
    reverse_origins = {child: receipt['native_birth']['birth_end_key'] for (_, child), receipt in reverse_splits.items()}
    reverse_parent_visits = {parent: (receipt['native_birth']['from_visit_index'],)
                             for (parent, _), receipt in reverse_splits.items()}
    preferences = {}
    for item in args.courses:
        entry = item.model_dump()
        cid, train, name = item.course_id, item.train, item.itinerary
        need(cid not in plan_by_course, 'Duplicate planned Course ID')
        stock = known_trains[train]
        vehicle = stock_by_course[cid]
        category = categories[text(stock, 3)]
        need(not (category.contents[0].values[1] & 0x20), 'Train Category forces stops at every station; explicit plan would be ambiguous')
        minimum = float(category.contents[20].value)
        need(math.isfinite(minimum) and minimum >= 0, 'Nonfinite/negative native Category connection time is outside this planning profile')
        entry['minimum_turnround_s'] = minimum
        plan_by_course[cid] = entry
        index = train_types[item.speed_type.casefold()]
        names = [name, *item.alternative_itineraries]
        need(len(set(names)) == len(names), 'Course itinerary preferences must contain distinct native names')
        need(len(names) == 1 or cid not in linked,
             'Alternative itineraries for linked formations require independently checked stopping locations')
        options = []
        for candidate in names:
            reviewed_origin = reverse_origins.get(cid)
            cache_key = (candidate, index, vehicle['maximum_speed_kmh'], reviewed_origin)
            if cache_key not in trace_cache:
                trace_cache[cache_key] = route_trace(project, itineraries[candidate], index, vehicle['maximum_speed_kmh'],
                                                     reviewed_reverse_origin=reviewed_origin)
            options.append(trace_cache[cache_key])
        trace = options[0]
        traces[cid] = trace
        resolved = []
        stops = _planned_rows(entry, trace, vehicle, stations, args.timetable_template_key, lower, upper,
                              split_origin_stop=cid in split_origins, formation_by_visit=lengths.get(cid),
                              resolved_visits=resolved, verified_split_berth_indices=reverse_parent_visits.get(cid, ()))
        alternative_reports = []
        for candidate in options[1:]:
            need(candidate['visits'][0]['end_key'] == trace['visits'][0]['end_key'],
                 'Alternative itineraries must start at the same directed station reference')
            alternative = []
            _planned_rows(entry, candidate, vehicle, stations, args.timetable_template_key, lower, upper,
                          primary=False, resolved_visits=alternative)
            alternative_reports.append(alternative)
        preferences[cid] = names
        controls = {**item.controls.model_dump(exclude_unset=True), 'speed_type': item.speed_type}
        controls.setdefault('train_number', cid)
        controls.setdefault('enabled', True)
        need(controls['enabled'], 'A generated scheduled Course must be enabled')
        course_list = cf.new_course(course_list, trains, roots['dest'][0], template_id=args.course_template_id,
                                    course_id=cid, train=train, itineraries=names, fields=controls,
                                    template_record=course_prototype)
        timetable = cf.new_timetable(timetable, course_list, roots['stations'][0], course_id=cid, stops=stops,
                                     template_record=timetable_prototype)
        details.append({'course_id': cid, 'train': train, 'itinerary': name, 'speed_type': item.speed_type,
                        'speed_table_index': index, 'consist_length_m': vehicle['length_m'],
                        'maximum_speed_kmh': vehicle['maximum_speed_kmh'], 'engine_names': vehicle['engine_array_order'],
                        'route_length_m': trace['route_length_m'], 'path_count': trace['path_count'],
                        'repeated_end_count': trace['repeated_end_count'], 'closed_walk': trace['closed_walk'],
                        'visits': resolved})
        if len(names) > 1:
            details[-1]['itinerary_preferences'] = [
                {'itinerary': candidate, 'priority': priority, 'route_length_m': option['route_length_m'],
                 'visits': visits}
                for priority, (candidate, option, visits) in enumerate(zip(names, options, [resolved, *alternative_reports]), 1)
            ]
    if args.mode == 'replace_plan':
        set_sequence(course_list, 4, [item for item in c.course_items(course_list) if text(item, 0) in plan_by_course])
        dictionary_replace(timetable, [(key, row) for key, row in cf.timetable(timetable).items()
                                       if text(row, 1) in plan_by_course])
    out_courses = w.dump_verified(course_list, course_version)
    actual_courses = c.course_items(w.load_next_compatible(out_courses)[0])
    saved = {text(item, 0): [c.text(value) for value in c.array(item.contents[2].value)]
             for item in actual_courses if text(item, 0) in preferences}
    need(saved == preferences, 'Fresh native Course readback differs from planned itinerary order')
    if first_service_archives is not None:
        need(len(actual_courses) == len(preferences), 'First-service Course readback includes an unplanned record')
    out_timetable = w.dump_verified(timetable, timetable_version)
    composition_report = None
    by_course = {item['course_id']: item for item in details}
    linked_starts = []

    def bind_start(before, after, row, movement):
        predecessor, successor = by_course[before], by_course[after]
        start = successor_start(
            project, itineraries[predecessor['itinerary']], itineraries[successor['itinerary']],
            traces[before], traces[after], predecessor['visits'][row], successor['visits'][0],
            movement, (before, after),
        )
        start['successor_itinerary'] = successor['itinerary']
        linked_starts.append(start)
        return start

    if args.composition_events:
        out_timetable, composition_report = bind_composition(
            project, [event.model_dump(exclude={'occupied_entry_speed_kmh', 'reverse_split'}, exclude_none=True)
                      for event in args.composition_events],
            by_course, itineraries, {
                'courses': out_courses, 'trains': blobs[roles['trains']], 'stations': blobs[roles['stations']],
                'depot': blobs[roles['depot']], 'timetable': out_timetable, 'connection_template': connection_template,
            },
            reverse_splits=reverse_splits,
        )
        for cid, clearance in composition_report['receiver_stopping_clearance'].items():
            schedule = lengths[cid]
            need(all(schedule[visit['visit_index']] == (visit['arrival_length_m'], visit['departure_length_m'])
                     for visit in clearance), 'Native composition bindings disagree with the planned approach lengths')
        for item in composition_report['events']:
            if item['kind'] == 'split':
                pair = item['main_course'], item['other_course']
                if pair in reverse_splits:
                    birth = {**reverse_splits[pair]['native_birth'],
                             'successor_itinerary': by_course[pair[1]]['itinerary']}
                    item['native_successor_start'] = birth
                    linked_starts.append(birth)
                else:
                    item['native_successor_start'] = bind_start(*pair, item['main_visit_index'], 'continue')
    command_report = None
    transfers = {}
    if args.turnrounds:
        links = [item.model_dump() for item in args.turnrounds]
        transfers = _projected_turnrounds(links, composition_report, plan_by_course, known_trains, depot)
        commands = _turnround_commands(plan_by_course, links, transfers)
        for item in links:
            bind_start(item['from_course'], item['to_course'], -1, item['movement'])
        out_timetable, command_report = connections.apply({
            'courses': out_courses, 'trains': blobs[roles['trains']], 'stations': blobs[roles['stations']],
            'timetable': out_timetable, 'connection_template': connection_template,
        }, commands)
    fresh = cf.timetable(w.load_next_compatible(out_timetable)[0])
    if first_service_archives is not None:
        expected_keys = {f'{item["course_id"]}#{index}' for item in details for index in range(len(item['visits']))}
        need(fresh.keys() == expected_keys, 'First-service Timetable readback includes an unplanned record')
    for report in details:
        cid = report['course_id']
        for index, location in enumerate(report['visits']):
            row = fresh[f'{cid}#{index}']
            planned = location['planned']
            need(text(row, 5) == planned['station_sign'] and row.contents[10].value == 2 + int(planned['stop'])
                 and text(row, 6) == _clock(planned['arrival_s'] % 86400)
                 and text(row, 7) == _clock(planned['departure_s'] % 86400)
                 and row.contents[15].values == [planned['arrival_s'] // 86400, planned['departure_s'] // 86400, 0, 0],
                 'Fresh timetable occurrence does not match the validated request')
    return {roles['courses']: out_courses, roles['timetable']: out_timetable}, {
        'services': details, 'course_count': len(details), 'turnrounds': command_report,
        'linked_movements': [item.model_dump() for item in args.turnrounds],
        'native_linked_starts': linked_starts,
        'composition_events': composition_report,
        'projected_formation_transfers': list(transfers.values()),
        'static_course_route_validation': True,
        'capacity_deadlock_or_native_runtime_verified': False,
    }


class ExistingNetworkPlanTools(MultiDocumentTools):
    def generate(self, args):
        state = self.load_project(args.source_project, minimum_documents=1)
        target = project_target(self, args)
        require_external_target(target, state['base'])
        if target is not None and state['base'].is_relative_to(target):
            raise APIError('PROJECT_TARGET_BINDING', 'The publication target cannot contain the source project')
        run_name = args.source_project.run_file
        connection_blob = None
        if args.connection_template is not None:
            path = self.path(args.connection_template.path)
            connection_blob = self.secure_bytes(path)
            if sha(connection_blob) != args.connection_template.sha256:
                raise APIError('SOURCE_CHANGED', 'Native Connection template SHA differs')
            state['inputs'][path] = connection_blob
        first_service_archives = None
        if args.course_template_archive is not None:
            seeds = []
            for source, suffix in ((args.course_template_archive, '.courses'), (args.timetable_template_archive, '.timetable')):
                path = self.path(source.path)
                blob = self.secure_bytes(path)
                if path.suffix != suffix or sha(blob) != source.sha256 or (path in state['inputs'] and state['inputs'][path] != blob):
                    raise APIError('NETWORK_FIRST_SERVICE_SOURCE', f'Require a stable SHA-bound native {suffix} shape archive')
                state['inputs'][path] = blob
                seeds.append(blob)
            first_service_archives = tuple(seeds)
        try:
            _selected_paths(state, auxiliary.records(state['run']))
            project = _movement_project(state['documents'], state['document_paths'],
                                        state['files'][state['roles']['dest']], allow_external_destinations=True)
            candidate, project, occupied_entry_edits = configure_join_approaches(state, project, args)
            updates, report = build_catalogs(candidate, project, args, connection_blob,
                                             first_service_archives=first_service_archives)
            if first_service_archives is not None:
                report['first_service_shapes'] = {
                    'course_archive': args.course_template_archive.model_dump(), 'course_template_id': args.course_template_id,
                    'timetable_archive': args.timetable_template_archive.model_dump(),
                    'timetable_template_key': args.timetable_template_key,
                    'native_initialized_defaults': True, 'donor_services_or_references_copied': False,
                }
            report['native_occupied_entry_edits'] = occupied_entry_edits
            members = {name: updates.get(name, candidate['files'][name]) for name in state['selected']}
            execution_root = state['root']
            if target is not None:
                execution_root = target.as_posix()
                members, relocation = relocate_project(members, source_root=state['root'], target_root=execution_root,
                    run_file=run_name, expected_hashes={name: sha(blob) for name, blob in members.items()},
                    discard_unrelated_destinations=True, project_type=EditableItineraryProject)
                report['relocation'] = relocation

            def read_bound(path):
                need(path.startswith(execution_root + '/'), 'Invalid preflight path outside exact execution root')
                return members[path[len(execution_root) + 1:]]

            checked = preflight.check(members[run_name], read_bound)
            if target is not None:
                need(checked['passed_static_subset'], f'Generated native candidate failed original-run preflight: {checked["errors"]}')
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
            raise APIError('NETWORK_PLAN_INVALID', str(error)[:800]) from error
        result = {
            **report, 'preview_only': args.preview_only, 'saved': False, 'execution_root': execution_root,
            'native_execution': False, 'static_simulation_preflight': checked['passed_static_subset'],
            'preflight_errors': checked['errors'],
            'files': {name: {'sha256': sha(blob), 'bytes': len(blob)} for name, blob in members.items()},
        }
        if args.preview_only:
            self.recheck(state)
            return result
        return publish_candidate(self, target, members, result, lambda: self.recheck(state))


def tool_definitions(root):
    service = ExistingNetworkPlanTools(root)
    return [('opentrack_generate_existing_network_operating_plan',
             'Generate and publish a new native .run snapshot for explicit mixed Train and Course plans on one or multiple '
             'existing documents. Empty Course and Timetable catalogues can use two SHA-bound native shape donors. '
             'Validate each ordered branch, merge or finite revisiting itinerary from native Ends, '
             'directional speed/length and stopping areas. Optional reciprocal reversals, continuations, ordered splits and joins. Static preflight only.',
             GenerateNetworkPlan, service.generate, False, False)]

