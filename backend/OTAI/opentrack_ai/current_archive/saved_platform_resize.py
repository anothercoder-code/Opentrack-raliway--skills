"""Change active native platform lengths against one frozen set of movements and bookings."""

from . import catalogs, course_factories, native_connections, saved_station_areas, writer
from .catalog_batch_reuse.course_batch import course_record
from .consist_workflow.core import summary
from .itinerary_edit_tools import _margin_members
from .multi_document.core import ident, need
from .native_platform_topology import station_turnout_kind, track_legs
from .native_station_rebind import grouped_rows
from .network_operating_plan import _planned_rows, route_trace
from .operating_plan_edit import UNBOUND, text, timetable_time
from .prepare_contract import auxiliary
from .runfile_parameters import inspect_runfile
from .saved_geometry import _edge, _movement_manifest, _speed_table, project_from
from .saved_halt_location import reviewed_platform, reviewed_separate_exit
from .saved_used_edge_profile import map_margin_span_profiles, verify_margin_profiles
from .zero_operations.speed_preferences import index_for_course


OPERATING_FILES = {'courses', 'timetable', 'trains', 'depot', 'stations'}
MAX_METRES = 2147483647


def _check_platform_track(project, arrival, keys, platform):
    edges = [project.model(key) for key in platform]
    offset = len(arrival) - len(keys)
    need(len(set(platform)) == len(platform) and len(set(keys)) == len(keys) and arrival[offset:] == keys,
         'The reviewed platform must form one nonrepeating native directed arrival chain')
    turnouts = {index for index, kind in enumerate(('entry', *('interior' for _ in keys[1:-1]), 'exit'))
                if station_turnout_kind(project, arrival, offset + index) == kind}
    need(all(edge in legs and (len(legs) == 1 or position in turnouts)
             for index, (start, finish, edge) in enumerate(zip(keys[:-1], keys[1:], edges, strict=True))
             for position, half in ((index, project.actual_related(start)), (index + 1, finish))
             for legs in (track_legs(project.model(half)),)),
         'Each platform Edge must follow its native leg through a station-owned turnout or an ordinary End')
    tracks = {text(edge, 19) or '' for edge in edges}
    need(len(tracks) == 1, 'The directed platform must use a single track name or be consistently unlabeled')


def _checked_platform(project, document, operation):
    reviewed = operation['arrival_route']
    owner = reviewed['document'], reviewed['start_id']
    need(writer.kind(project.model(owner)) == 'OTEndModel', 'Review the saved primary arrival Route, not its continuation')
    route = project.owned(owner, 'OTRoute', (reviewed['name'], reviewed['array_id'], reviewed['start_id']))
    arrival = project.route_view(route)
    if (operation.get('action') == 'resize_used_terminal_platform_span' or operation.get('kind') == 'terminal'):
        from .saved_terminal_halts import _platform as terminal_platform

        keys, _, length, _, station_sign = terminal_platform(project, document, operation)
        platform = [(document, edge_id) for edge_id in operation['expected_platform_edge_ids']]
        reference_id = operation['station_reference_end_id']
        terminal = keys[-1] if reference_id is None else (document, reference_id)
    elif (operation.get('action') == 'resize_used_cross_document_platform_span'
            or operation.get('kind') == 'cross_document'):
        from .saved_cross_platform_halts import _platform as cross_document_platform

        keys, _, length, _, _ = cross_document_platform(project, document, operation, allow_station_turnouts=True)
        platform = [(row['document'], row['edge_id']) for row in operation['expected_platform_edge_ids']]
        terminal, station_sign = keys[-1], operation['expected_station_sign']
    else:
        station = saved_station_areas.station_model(project, document, operation['station_id'])
        exit_key = arrival[-1]
        if project.model(exit_key).contents[20].value == 2:
            end, members, edge_ids, _, length = reviewed_platform(project, document, station, operation, 2,
                                                                 allow_station_turnouts=True)
            keys = [project.key(member) for member in members]
            platform = [(document, edge_id) for edge_id in edge_ids]
            terminal = project.key(end)
        else:
            terminal, keys, platform, length = reviewed_separate_exit(project, document, station, route, operation)
        station_sign = text(station, 7)
    _check_platform_track(project, arrival, keys, platform)
    return terminal, platform, station_sign, length


def _selected_changes(project, document, platform, old_length, operation, *, allow_redistribution=False):
    requested = [((row.get('document', document), row['edge_id']), row) for row in operation['edges']]
    need(1 <= len(requested) <= 32 and len({key for key, _ in requested}) == len(requested),
         'Review each changed platform Edge once')
    need(operation['expected_platform_length_m'] == old_length, 'The original physical platform length differs from the review')
    result = {}
    for key, row in requested:
        need(key in platform, 'An edited Edge is outside the reviewed directed platform')
        edge = _edge(project, key[0], row)
        _speed_table(edge)
        need(all(edge.contents[slot].value.contents[13].value is None for slot in (7, 8)),
             'A measuring instrument is attached to the selected platform Edge')
        former, revised = row['expected_length_m'], row['length_m']
        need(edge.contents[9].values[1] == former, 'A saved platform Edge length differs from the review')
        need(type(revised) is int and 0 < revised < MAX_METRES and former != revised,
             'Each requested platform Edge requires a different positive native length')
        result[key] = former, revised
    total = old_length + sum(revised - former for former, revised in result.values())
    need(0 < total < MAX_METRES and (allow_redistribution or total != old_length)
         and total == operation['replacement_platform_length_m'],
         'Changed Edge lengths do not produce the reviewed replacement physical platform length')
    return result


def _movement_spans(project, movements, changes):
    affected = {}
    for identity, (nodes, _, _) in movements.items():
        distance = 0
        spans = []
        for start, end in zip(nodes, nodes[1:]):
            key = project.edge_between(start, end)
            former = project.model(key).contents[9].values[1]
            limit = distance + former
            if key in changes:
                spans.append((distance, limit, changes[key][1]))
            distance = limit
        if spans:
            new = distance + sum(revised - (end - start) for start, end, revised in spans)
            need(0 < new < MAX_METRES, f'Resized platform exceeds native movement distance for {identity}')
            affected[identity] = distance, spans
    return affected


def _operating_data(inputs, run_bytes, affected_itineraries, *, linked_course_ids=(), verified_connection_rows=(),
                    verified_interval_rows=(), allow_moving_block=False):
    need(isinstance(inputs, dict) and set(inputs) == OPERATING_FILES and all(type(raw) is bytes for raw in inputs.values())
         and type(run_bytes) is bytes, 'Exact run-bound Course, Timetable, rolling stock, and Station catalogs are required')
    roots = {role: writer.load_next_compatible(raw)[0] for role, raw in inputs.items()}
    clock = inspect_runfile(auxiliary.core_bytes(auxiliary.records(run_bytes)))
    need(clock['editable'], 'The frozen native run requires an explicit operating time window')
    bounds = clock['numeric']['start_seconds'], clock['numeric']['stop_seconds'] + 1
    courses = list(map(course_record, catalogs.course_items(roots['courses'])))
    selected = {row['course_id']: row for row in courses
                if row['enabled'] and (row['course_id'] in linked_course_ids
                                       or affected_itineraries.intersection(row['itineraries']))}
    need(set(linked_course_ids) <= selected.keys(), 'A reviewed link requires each connected native Course to be enabled')
    table = grouped_rows(course_factories.timetable(roots['timetable']))
    for cid, rows in table.items():
        for row in rows:
            interval = text(row, 2)
            need(interval in UNBOUND or (cid, row.contents[3].value) in verified_interval_rows
                 or not (cid in selected or interval in selected),
                 f'An affected Course uses a native interval timetable reference: {cid}')
            for index, connection in enumerate(catalogs.array(row.contents[9].value)):
                linked = native_connections.record(connection)
                need((cid, row.contents[3].value, index) in verified_connection_rows
                     or not (cid in selected or linked['target_course_id'] in selected),
                     f'An affected Course has a native Connection requiring a separate formation review: {cid}')
    need(selected and selected.keys() <= table.keys(), 'The resized platform must have a fully booked, enabled affected Course')
    stations = catalogs.station_items(roots['stations'])
    trains = {text(item, 0): item for item in catalogs.train_items(roots['trains'])}
    depot = {text(item, 1): item for item in catalogs.engine_items(roots['depot'])}
    classes = {}
    for cid, course in selected.items():
        need(len(course['itineraries']) == 1 and course['train'] in trains,
             f'Affected Course needs one saved Itinerary and one consist: {cid}')
        need(course['spacing_mode_code'] == 0
             or (allow_moving_block and cid not in linked_course_ids and course['spacing_mode'] in ('moving', 'moving_cbtc')),
             f'Affected Course needs fixed-block spacing or a reviewed independent moving-block endpoint: {cid}')
        rows = table[cid]
        need([row.contents[3].value for row in rows] == list(range(len(rows))) and len(rows) >= 2,
             f'Expected consecutive planned timetable visits for {cid}')
        visits = []
        for index, row in enumerate(rows):
            arrival, departure = (timetable_time(row, role) for role in ('arrival', 'departure'))
            need(arrival is not None and departure is not None, f'An affected course has an incomplete planned time: {cid}#{index}')
            track = text(row, 18) or ''
            visits.append({'station_sign': text(row, 5), 'arrival_s': arrival, 'departure_s': departure,
                           'stop': bool(row.contents[10].value & 1), 'track_id': track if index else ''})
        stock = summary(trains[course['train']], depot)
        classes[cid] = (course['itineraries'][0], stock, str(index_for_course(run_bytes, course['speed_type'])), visits)
    return classes, stations, bounds


def _course_berths(project, operating, platforms):
    courses, stations, bounds = operating
    destinations = {ident(item)[0]: item for item in project.dests}
    reviewed = {terminal: {} for terminal in platforms}
    other = {}
    for cid, (label, stock, speed_index, planned) in courses.items():
        trace = route_trace(project, destinations[label], speed_index, stock['maximum_speed_kmh'])
        resolved = []
        try:
            _planned_rows({'visits': planned}, trace, stock, stations, '', *bounds, resolved_visits=resolved)
        except ValueError as exc:
            raise ValueError(f'Course {cid}: {exc}') from exc
        for visit in resolved:
            if not visit['planned']['stop'] or visit['visit_index'] == 0:
                continue
            key = cid, visit['visit_index']
            point = visit['stopping_point']
            terminal = visit['end_key']
            if terminal not in platforms:
                other[key] = (visit['stopping_area_length_m'], visit['stopping_area_edge_keys'], None if point is None else
                              (point['signal_id'], point['stop_edge_key'], point['available_length_m']))
                continue
            platform, platform_length = platforms[terminal]
            need(visit['stopping_area_edge_keys'] == platform and visit['stopping_area_length_m'] == platform_length
                 and point is not None and point['stop_edge_key'] in platform,
                 f'Affected Course {cid} does not stop on the one reviewed directed platform')
            reviewed[terminal][key] = {
                'course_id': cid, 'visit_index': visit['visit_index'], 'station_sign': visit['station_sign'],
                'train_length_m': stock['length_m'], 'reference_end': terminal,
                'reference_distance_m': visit['distance_m'], 'head_distance_m': point['distance_m'],
                'available_length_m': point['available_length_m'], 'stop_edge': point['stop_edge_key'],
                'stop_signal_id': point['signal_id'], 'stop_marker_distance_m': point['marker_distance_m'],
                'head_offset_from_marker_m': point['head_offset_from_marker_m'],
                'planned_arrival_s': visit['planned']['arrival_s'], 'planned_departure_s': visit['planned']['departure_s'],
                'minimum_arrival_leg_s': visit['leg_minimum_elapsed_s'],
            }
    return reviewed, other


def _course_stops(project, operating, terminal, platform, platform_length):
    reviewed, other = _course_berths(project, operating, {terminal: (platform, platform_length)})
    return reviewed[terminal], other


def _review_stops(before, after, approved):
    need(before.keys() == after.keys() and before, 'The revised physical platform must retain the booked visits')
    reviews = {(row['course_id'], row['visit_index']): row for row in approved}
    need(len(reviews) == len(approved) and reviews.keys() == before.keys(),
         'Review every affected booked platform visit exactly once')
    for key, review in reviews.items():
        old, new = before[key], after[key]
        need(review['expected_train_length_m'] == old['train_length_m'] == new['train_length_m'],
             f'Reviewed original formation length differs for {key[0]}#{key[1]}')
        fields = ('reference_distance_m', 'head_distance_m', 'available_length_m')
        need(all(review['expected_' + field] == old[field] and review['replacement_' + field] == new[field]
                 for field in fields), f'Reviewed native platform stop position or available length differs for {key[0]}#{key[1]}')
    return [{'before': row, 'after': after[key]} for key, row in before.items()]


def _verify_movements(before, after, affected):
    need(before.keys() == after.keys(), 'Native movement identities changed during platform resize')
    reviewed = []
    for identity, (old_nodes, old_refs, old_geometry) in before.items():
        nodes, refs, geometry = after[identity]
        if identity not in affected:
            need((old_nodes, old_refs, old_geometry) == (nodes, refs, geometry), 'An unrelated native movement changed')
            continue
        old_total, spans = affected[identity]
        new_total = old_total + sum(revised - (end - start) for start, end, revised in spans)
        need((nodes, refs) == (old_nodes, old_refs) and [profile for profile, _ in geometry] == [profile for profile, _ in old_geometry]
             and sum(length for _, length in geometry) == new_total,
             f'Native movement differs from the approved directed length change for {identity}')
        reviewed.append({'kind': identity[0], 'owner': identity[1], 'identity': identity[2],
                         'before_distance_m': old_total, 'after_distance_m': new_total, 'changed_edge_traversals': len(spans)})
    return reviewed


def _check_inverse(fresh, originals, changes, margins):
    verify_margin_profiles(fresh, margins)
    for key, (length, revised) in changes.items():
        metric = fresh.model(key).contents[9].values
        need(metric[1] == revised, 'An exact platform Edge length differs after native archive readback')
        metric[1] = length
    definitions = {(fresh.owners[id(item)][0], ident(item)): item for item in fresh.dests}
    for review in margins:
        definition = definitions[review['document'], review['identity']]
        for row, former in zip(_margin_members(definition)[2], review['before'], strict=True):
            row.contents[0].values[0] = former['position_m']
    need(all(writer.fingerprint(fresh.roots[name]) == original for name, original in originals.items()),
         'A saved field outside reviewed platform lengths and mapped margin locations changed')


def resize_used_platform_span(documents, paths, dest, document, operation, operating_inputs, run_bytes):
    project = project_from(documents, paths, dest)
    combined = operation['action'] == 'resize_used_platforms'
    sections = operation['platforms'] if combined else [{**operation, 'document': document}]
    if combined:
        need(2 <= len(sections) <= 32 and document in {scope['document'] for scope in sections},
             'Review two or more platform scopes including the target worksheet')
    scopes, changes = {}, {}
    for scope in sections:
        name = scope['document']
        terminal, platform, station_sign, length = _checked_platform(project, name, scope)
        need(terminal not in scopes, 'Review each directed platform reference only once')
        edits = _selected_changes(project, name, platform, length, scope, allow_redistribution=combined)
        for edge, pair in edits.items():
            need(changes.setdefault(edge, pair) == pair,
                 'Overlapping platform reviews must agree on every shared Edge length')
        scopes[terminal] = scope, platform, station_sign, length, edits
    need(all(changes.keys() & set(platform) == edits.keys() for _, platform, _, _, edits in scopes.values()),
         'Review every changed Edge on each directed platform it affects')

    before = _movement_manifest(project)
    affected = _movement_spans(project, before, changes)
    itinerary_names = {key[2][0] for key in affected if key[0] == 'itinerary'}
    operating = _operating_data(operating_inputs, run_bytes, itinerary_names)
    old, former_others = _course_berths(project, operating, {
        key: (platform, length) for key, (_, platform, _, length, _) in scopes.items()})
    originals = {name: writer.fingerprint(root) for name, root in project.roots.items()}
    margins = map_margin_span_profiles(project, affected, operation.get('map_itinerary_safety_margins') is True)
    for key, (_, revised) in changes.items():
        project.model(key).contents[9].values[1] = revised
    affected_sheets = {*(key[0] for key in changes), *(row['document'] for row in margins)}
    outputs = {name: writer.dump_verified(project.roots[name], project.versions[name]) for name in sorted(affected_sheets)}
    fresh = project_from({**documents, **outputs}, paths, dest)
    new_platforms = {}
    for terminal, (scope, platform, station_sign, _, _) in scopes.items():
        expected_length = scope['replacement_platform_length_m']
        need(_checked_platform(fresh, scope['document'], scope) == (terminal, platform, station_sign, expected_length),
             'The original directed station reference, platform Edge order or total length differs after cold read')
        new_platforms[terminal] = platform, expected_length
    moves = _verify_movements(before, _movement_manifest(fresh), affected)
    new, revised_others = _course_berths(fresh, operating, new_platforms)
    need(former_others == revised_others, 'Resizing the reviewed platform changes another booked stopping area')
    reports = []
    for terminal, (scope, _, station_sign, length, _) in scopes.items():
        details = {'document': scope['document'], 'station_sign': station_sign,
                   'station_id': project.model(terminal).contents[12].value.contents[0].value,
                   'station_reference_end': terminal, 'platform_edge_ids': scope['expected_platform_edge_ids'],
                   'original_platform_length_m': length,
                   'replacement_platform_length_m': scope['replacement_platform_length_m'], 'edges': scope['edges'],
                   'verified_platform_visits': _review_stops(old[terminal], new[terminal], scope['visit_reviews'])}
        if 'expected_buffer_end_id' in scope:
            details.update(physical_buffer_end=(scope['document'], scope['expected_buffer_end_id']),
                           unchanged_buffer_signal_id=scope['expected_buffer_signal_id'],
                           reference_is_geometry_only=scope['station_reference_end_id'] is None)
        reports.append(details)
    _check_inverse(fresh, originals, changes, margins)
    report = {'platforms': reports} if combined else reports[0]
    return outputs, {'action': operation['action'], 'document': document, **report, 'reviewed_movements': moves,
                     'checked_operating_courses': list(operating[0]), 'mapped_safety_margin_profiles': margins,
                     'changed_documents': sorted(outputs), 'destination_catalog_unchanged': True,
                     'nonselected_graph_verified': True, 'native_execution_tested': False}
