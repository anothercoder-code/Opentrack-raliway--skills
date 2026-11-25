"""Insert a native worksheet into an in-use reciprocal connector crossing."""

from math import isfinite

from . import path_functions, route_factory, writer
from .graph_references import incoming_counts
from .itinerary_edit_tools import _float32, _margin_members, _margin_values
from .multi_document.core import ident, need, ref
from .multi_document.generate import inf, route as new_route
from .path_lifecycle_tools import _incident_bindings
from .route_discovery_tools import main_signal
from .route_edit_tools import _protection_values, _route_owner_counts, _route_shape, _zone_nodes
from .route_fetch_tools import _stable_inventory
from .route_lifecycle_tools import _guard_incidents
from .saved_geometry import _connector_key, _movement_geometry, _movement_manifest, project_from, replace_connectors
from .saved_inserted_occupied_timing import (
    apply_inserted_occupied_timing, check_inserted_occupied_timing, plan_inserted_occupied_timing,
)
from .saved_terminal_overlap import overlap_reference, set_overlap_reference, terminal_overlap
from .saved_timing_signal_split import DEFAULT_ROUTE_TIMING, stored_route_timing
from .saved_track_reroute import _walk_span
from .saved_used_edge_profile import verify_margin_profiles


DEFAULT_OCCUPIED_ENTRY = (0, 40.0, 0.0)


def _middle_chain(project, operation):
    west, east = (_connector_key(operation[field]) for field in ('middle_start', 'middle_finish'))
    need(west[0] == east[0] and west != east, 'Select two distinct connectors on the same inserted worksheet')
    sheet = west[0]
    first_ids, second_ids = operation['middle_first_edge_ids'], operation['middle_second_edge_ids']
    all_ids = first_ids + second_ids
    need(len(set(all_ids)) == len(all_ids), 'The intermediate track cannot repeat an Edge')
    for connector in (west, east):
        approach = project.model(project.related(connector))
        need(writer.kind(approach) == 'OTEndModel' and approach.contents[20].value == 1
             and all(approach.contents[i].value is None for i in (6, 11, 12, 13)),
             'Each intermediate connector needs a plain approach without station, signal or instrument ownership')
    first, first_m, first_profile = _walk_span(project, sheet, project.related(west), first_ids)
    second, second_m, second_profile = _walk_span(project, sheet, project.related(first[-1]), second_ids)
    reverse_second, _, _ = _walk_span(project, sheet, project.related(east), second_ids[::-1])
    reverse_first, _, _ = _walk_span(project, sheet, project.related(reverse_second[-1]), first_ids[::-1])
    need(second[-1] == project.related(east) and reverse_first[-1] == project.related(west)
         and project.related(first[-1]) == reverse_second[-1], 'Intermediate track does not join the reviewed Ends')
    split = first[-1], reverse_second[-1]
    for key in split:
        end = project.model(key)
        need(main_signal(end) and end.contents[20].value == 1
             and all(end.contents[i].value is None for i in (6, 12, 13)),
             'The new Route boundary must use ordinary paired main signals without station or instrument ownership')
        signal = end.contents[11].value
        show, _, flags, _ = signal.contents[9].values
        need(show == 2 and type(flags) is int and 0 <= flags <= 1023 and not flags & 2,
             'The new Route boundary must have the verified native signal show/profile')
        indications = route_factory.wrapper(signal.contents[10].value, 'OTSigIndList')
        need(sum(ind.contents[0].value == 0 and ind.contents[1].value is end for ind in indications) == 1,
             'Each intermediate signal requires its own track-speed aspect')
    need(first_m + second_m == operation['expected_middle_length_m']
         and [row['safety_element_id'] for row in first_profile + second_profile] == operation['expected_middle_safety_elements'],
         'Intermediate distance or ordered Safety Element IDs differ from the reviewed values')
    return (west, east), ((first, second), (reverse_second, reverse_first)), set(all_ids)


def _old_pair(project, operation, document, middle):
    pair = tuple(_connector_key(operation['old_pair'][end]) for end in ('a', 'b'))
    first, second = pair
    need(first[0] == document and len({first[0], second[0], middle[0][0]}) == 3,
         'Insert a different worksheet between the reviewed source and destination documents')
    need(project.block_end(first) == second and project.block_end(second) == first,
         'Expected the original exact reciprocal crossing')
    return pair


def _owner_array(project, key):
    counts = _route_owner_counts(project, key)
    return project.model(key).contents[15].value.contents[0].value, counts


def _add_route(project, owner, identity, nodes, *, primary=False, original=None, groups=None, reserve_previous=False):
    array, _ = _owner_array(project, owner)
    items = path_functions.mutable_array(array)
    need(all(ref(item)['name'].casefold() != identity[0].casefold() and ident(item)[1:] != identity[1:]
             for item in items), 'A new Route is ambiguous at its reviewed owner')
    if original is None:
        models = [project.model(key) for key in nodes]
        new = new_route(*identity, models, len(nodes) if primary else -1, fragment=not primary)
        if groups is not None:
            array_group = new.contents[12].values
            array_group[0] = path_functions.array_like(array_group[0], _zone_nodes(models, groups))
        if reserve_previous:
            new.contents[11].value = 1
    else:
        new = original
        new.contents[1].value = path_functions.fresh_string(new.contents[1].value, identity[0])
        new.contents[2].values[:] = identity[1:]
    writer.set_elements(array, [*items, new])
    return new


def _route_profile(route):
    return {
        'timing': [*route.contents[5].values[:4], route.contents[5].values[5]],
        'occupied_entry': list(route.contents[6].values),
        'overlap': [path_functions.string(route.contents[7].value), route.contents[9].value],
        'approach': list(route.contents[8].values),
        'distance_flags': list(route.contents[10].values),
        'route_flags': route.contents[11].value,
        'description': path_functions.string(route.contents[3].value),
        **_protection_values(route, _route_shape(route)),
    }


def _metric_zone_aspect(nodes, aspects):
    need(len(aspects) == 1 and type(aspects[0]) is int, 'Preserving a slow-speed zone requires one fixed native aspect')
    code = aspects[0]
    speed = code * 10 if code < 1000 else code - 1000
    owner = nodes[0]
    signal = owner.contents[11].value
    need(signal is not None and signal.contents[9].values[0] == 2 and 10 <= speed <= 300,
         'A slow-speed zone requires a supported metric speed indication at the original start')
    indications = route_factory.wrapper(signal.contents[10].value, 'OTSigIndList')
    need(sum(ind.contents[0].value == code and ind.contents[1].value is owner for ind in indications) == 1,
         'The original starting signal does not own the selected speed indication')
    return code, speed


def _check_local_slow_zone(route, nodes, profile, expected_zone, primary, preserve):
    if expected_zone is None:
        need(all(value is None for value in route.contents[12].values[1:])
             and profile['signal_aspects'] == ([0] if primary else []),
             'A slow-speed zone or nonstandard signal aspect requires explicit local review')
        return
    need(primary and preserve and profile['slow_speed_zone_end_ids'] == expected_zone,
         'The declared slow-speed zone must exactly match both Ends of the retained primary Route')
    start, finish = _zone_nodes(nodes, expected_zone)
    need(start is not finish, 'A local slow-speed zone must extend between two different Ends')
    _metric_zone_aspect(nodes, profile['signal_aspects'])


def _stored_zone(project, route):
    return tuple(project.key(end) if end is not None else None for end in route.contents[12].values[1:])


def _plan_crossing_zone(project, primary, companion, split, approval, *, preserve):
    if approval is None:
        return None
    start, finish = (_connector_key(approval[field]) for field in ('start', 'finish'))
    need(preserve and _stored_zone(project, primary) == (start, None)
         and _stored_zone(project, companion) == (None, finish),
         'Review the original crossing slow-zone start in the primary and its finish in the receiving fragment')
    props = _protection_values(primary, _route_shape(primary))
    code, speed = _metric_zone_aspect(path_functions.mutable_array(primary.contents[0].value),
                                     props['signal_aspects'])
    need(speed == approval['expected_speed_kmh'], 'The reviewed crossing slow-zone speed differs from the original aspect')
    return {'start': start, 'split': split, 'finish': finish, 'native_aspect_code': code,
            'speed_kmh': speed, 'head_only': props['slow_speed_only_for_head']}


def _occupied_signal(project, key):
    end = project.model(key)
    signal = end.contents[11].value
    need(main_signal(end), 'The reviewed occupied-entry boundary must have a native main signal')
    route_factory.layout(signal, 'OTSignalModel', 11, route_factory.SIGNAL, graphic=True)
    show, _, flags, _ = signal.contents[9].values
    need(signal.contents[7].value is end and show == 2 and type(flags) is int and 0 <= flags <= 1023,
         'The occupied-entry main signal must have a verified local owner and metric profile')
    return signal, flags


def _occupied_stop(project, route, approved):
    sequence = project.route_view(route)
    terminal = _connector_key(approved['terminal_end'])
    need(len(sequence) >= 2 and sequence[-1] == terminal and sequence[-2][0] == terminal[0],
         'The reviewed occupied platform must be the original far-side terminal')
    edge = project.edge_between(sequence[-2], terminal)
    end = project.model(terminal)
    approach = project.model(sequence[-2])
    station = end.contents[12].value
    need(edge == (terminal[0], approved['stop_edge_id']) and end.contents[20].value == 2
         and approach.contents[20].value == 1 and main_signal(end)
         and station is not None and writer.kind(station) == 'OTStationModel' and approach.contents[12].value is station,
         'The reviewed occupied platform must match the exact directed station stopping Edge')
    return terminal, edge


def _plan_occupied_entry(project, primary, companion, owner, split, approval, *, preserve):
    if approval is None:
        return None
    from .saved_occupied_signal_split import occupied_entry_values

    values = occupied_entry_values(approval)
    mode = 'speed-only' if values[0] == 3 else 'stop-and-wait'
    need(preserve and tuple(primary.contents[6].values) == tuple(companion.contents[6].values) == values,
         f'Occupied entry requires the reviewed {mode} setting on both original Route fragments')
    terminal, edge = _occupied_stop(project, primary, approval)
    source, source_flags = _occupied_signal(project, owner)
    relay, relay_flags = _occupied_signal(project, split)
    counts = incoming_counts(project.roots[split[0]])
    need(source_flags & 1 and not relay_flags & 1 and counts[id(relay)] == 2
         and not route_factory.wrapper(project.model(split).contents[15].value, 'OTRouteList'),
         'Preserving terminal occupied entry requires an enabled original signal and a dedicated unused relay signal')
    return {'terminal': terminal, 'stop_edge': edge, 'values': values, 'original_signal_id': source.contents[0].value,
            'original_signal_flags': source_flags, 'relay_signal_id': relay.contents[0].value,
            'relay_signal_flags': relay_flags | 1}


def _occupied_berth(project, route, approval, banks, run_bytes):
    from .saved_occupied_signal_split import verify_occupied_signal_split

    nodes = project.route_view(route)
    return verify_occupied_signal_split(project, route, nodes, nodes[-2], approval, banks, run_bytes)


def _review_occupied_handoff(project, front, arrival, original, review, banks, run_bytes, length):
    from .saved_terminal_overlap import _edge_locking_resources

    def resources(route):
        nodes = project.route_view(route)
        edges = [project.edge_between(a, b) for a, b in zip(nodes, nodes[1:])]
        elements, exclusions = _edge_locking_resources(project, edges)
        return elements | exclusions

    need(not resources(front) & resources(arrival),
         'Inserted occupied entry requires independent approach and terminal Safety Elements and Edge exclusions')
    saved = _occupied_berth(project, arrival, review, banks, run_bytes)
    before_berth, after_berth = original['berth'], saved['berth']
    distances = ('head_distance_m', 'donor_contact_distance_m', 'donor_nominal_head_distance_m')
    need(after_berth == {**before_berth, **{key: before_berth[key] + length for key in distances}}
         and all(original[key] == saved[key] for key in
                 ('values', 'receiver_course', 'donor_course', 'station_sign',
                  'receiver_length_m', 'donor_length_m', 'combined_length_m')),
         'Inserted occupied entry must preserve the local berth, formation and exact movement distance increase')
    return {'before': original, 'after': saved, 'inserted_length_m': length}


def _local_protection(route, *, primary, preserve, expected_zone=None, crossing_zone=False, approved_overlap=False,
                      approved_occupied=False):
    profile = _protection_values(route, _route_shape(route))
    nodes = path_functions.mutable_array(route.contents[0].value)
    releases = profile['release_group_end_ids']
    first = nodes[0].contents[0].value
    last = nodes[-1].contents[0].value
    length, speed = route.contents[8].values
    release_s, reserve_s = route.contents[5].values[2:4]
    need(route.clazz.superclass.version == 6
         and route.contents[5].values[:2] == [0, 400] and route.contents[5].values[5] == 0
         and (approved_occupied or tuple(route.contents[6].values) == DEFAULT_OCCUPIED_ENTRY)
         and route.contents[10].values == [5000, 0, 0],
         'A Route has occupied-entry or distance protection requiring separate review')
    need(approved_overlap or overlap_reference(route) == ('', -1),
         'A Route overlap needs explicit terminal review before insertion')
    if crossing_zone:
        need(preserve and expected_zone is None and (primary or not profile['signal_aspects']),
             'A crossing slow zone needs explicit preservation and a plain receiving signal profile')
    else:
        _check_local_slow_zone(route, nodes, profile, expected_zone, primary, preserve)
    _zone_nodes(nodes, releases)
    if preserve:
        if primary:
            need(all(type(value) is int and 0 <= value <= 86400 for value in (release_s, reserve_s))
                 and all(isfinite(value) and 0 <= value <= 1e7 for value in (length, speed))
                 and route.contents[11].value in ((0, 1, 2, 3) if crossing_zone or expected_zone is not None else (0, 1))
                 and releases and releases[0] == first,
                 'The retained Route needs known timing, approach and ordered release anchors')
        else:
            need((release_s, reserve_s, length, speed, route.contents[11].value) == (5, 0, 0.0, 0.0, 0)
                 and (not releases or releases[-1] == last),
                 'The original receiving fragment has nonlocal protection or misses its terminal release anchor')
    else:
        need((release_s, reserve_s, length, speed, route.contents[11].value) == (5, 0, 0.0, 0.0, 0)
             and releases == ([first] if primary else [])
             and (primary or path_functions.string(route.contents[3].value) == ''),
             'Nondefault continuation protection requires explicit preserve_local_protection')
    return releases


def _plan_routes(project, pair, middle, parts, operation, operating_banks=None, run_bytes=None):
    plans = operation['routes']
    requested = {(row['route']['document'], row['route']['name'], row['route']['array_id'], row['route']['start_id']): row
                 for row in plans}
    need(len(requested) == len(plans), 'Each affected primary Route must occur exactly once')
    selected = {}
    names, known_ids = _stable_inventory(project)
    allocated = {}
    for row in project.continuations:
        sender = row['source_document'], row['source_connector']
        receiver = row['target_document'], row['target_connector']
        if (sender, receiver) not in (pair, pair[::-1]):
            continue
        index = pair.index(sender)
        native_ref = row['route']
        owner = sender[0], native_ref['start_id']
        identity = native_ref['name'], native_ref['array_id'], native_ref['start_id']
        approval = requested.get((sender[0], *identity))
        need(approval is not None, 'Review every existing Route crossing the selected connectors')
        primary = project.owned(owner, 'OTRoute', identity)
        continuation = project.owned(receiver, 'OTRoute', identity)
        preserve = approval.get('preserve_local_protection', False)
        first, second = parts[index]
        split = first[-1]
        occupied_review = approval.get('expected_occupied_entry')
        timing_review = approval.get('expected_occupied_entry_timing')
        occupied = _plan_occupied_entry(project, primary, continuation, owner, split, occupied_review, preserve=preserve)
        wait = occupied is not None and occupied['values'][0] == 7
        reviewed_overlap = approval.get('expected_terminal_overlap')
        overlap = None
        old_overlap_reference = overlap_reference(primary)
        if reviewed_overlap is not None:
            overlap = terminal_overlap(project, primary, reviewed_overlap)
            shunting = overlap['shunting']
            need(preserve and old_overlap_reference in ((shunting['name'], shunting['start_id']), (shunting['name'], -1))
                 and overlap_reference(continuation) == ('', -1),
                 'The reviewed overlap must match the primary’s original binding and have no competing companion bind')
        crossing_zone = _plan_crossing_zone(project, primary, continuation, split,
                                            approval.get('expected_cross_document_slow_zone'), preserve=preserve)
        if occupied is not None:
            need(overlap is None and crossing_zone is None and approval.get('expected_local_slow_zone_end_ids') is None
                 and not approval.get('reserve_with_previous'), 'Combined terminal occupied-entry protections require separate review')
            if timing_review is None:
                need(stored_route_timing(primary) == DEFAULT_ROUTE_TIMING and (not wait or primary.contents[11].value == 0),
                     'Inserted occupied entry without reviewed timing requires default original timing and independent reservation')
        berth = None
        timed_entry = None
        if timing_review is not None:
            need(occupied is not None and all(key in occupied_review for key in (
                'receiver_course', 'donor_course', 'station_sign', 'expected_safety_element_id'))
                 and approval.get('middle_entry_release_end_ids') is None
                 and approval.get('middle_exit_release_end_ids') is None,
                 'Inserted occupied-entry timing needs a fully reviewed berth and implicit terminal release')
        if wait or timing_review is not None:
            berth = _occupied_berth(project, primary, occupied_review, operating_banks, run_bytes)
        if timing_review is not None:
            timed_entry = plan_inserted_occupied_timing(project, primary, continuation, berth, timing_review,
                                                        operating_banks, [*first, split, *second])
        local_releases = _local_protection(primary, primary=True, preserve=preserve,
                                           expected_zone=approval.get('expected_local_slow_zone_end_ids'),
                                           crossing_zone=crossing_zone is not None,
                                           approved_overlap=overlap is not None, approved_occupied=occupied is not None)
        remote_releases = _local_protection(continuation, primary=False, preserve=preserve,
                                            crossing_zone=crossing_zone is not None, approved_occupied=occupied is not None)
        entry_groups = approval.get('middle_entry_release_end_ids')
        exit_groups = approval.get('middle_exit_release_end_ids')
        if entry_groups is not None:
            _zone_nodes([project.model(key) for key in first], entry_groups)
            need(entry_groups[-1] == split[1], 'Middle entry release anchors must include the new terminal signal')
        if exit_groups is not None:
            _zone_nodes([project.model(key) for key in (split, *second)], exit_groups)
            need(exit_groups[0] == split[1] and remote_releases,
                 'Explicit middle exit release groups need the new start and the preserved outer terminal anchor')
        if len(local_releases) > 1 or remote_releases:
            need(remote_releases and entry_groups is not None,
                 'An existing grouped Route needs its original terminal and explicit middle entry release anchors')
        new_owner = project.model(split)
        if split not in allocated:
            path_functions.guard_counter_references(project.roots[split[0]], new_owner, allow_local_shunting=True)
        new_id = allocated.get(split, new_owner.contents[19].value) + 1
        name = approval['continued_name']
        need(new_id <= 2147483647 and (new_id, split[1]) not in known_ids[split[0].casefold()],
             'The new intermediate Route ID collides with an exact saved reference')
        need(name.casefold() not in names, 'An intermediate Route name already exists or would capture a reference')
        allocated[split] = new_id
        names.add(name.casefold())
        array, counts = _owner_array(project, receiver)
        need(counts[id(continuation)] == 1, 'The old receiving fragment has external object owners')
        terminal = tuple(project.route_view(continuation))
        origin = tuple(project.route_view(primary)[:-len(terminal)])
        original_profile = _route_profile(primary)
        if overlap is not None:
            original_profile['overlap'] = ['', -1]
        if occupied is not None:
            original_profile.update(occupied_entry=list(DEFAULT_OCCUPIED_ENTRY), allow_occupied_entry=False,
                                    occupied_entry_use_speed=False, occupied_entry_use_time=False,
                                    occupied_entry_speed_kmh=40.0, occupied_entry_wait_s=0.0)
        if timed_entry is not None:
            original_profile['approach'] = [0.0, 0.0]
        selected[sender[0], *identity] = {
            'owner': owner, 'old_identity': identity, 'old_array': array, 'old_fragment': continuation,
            'old_primary': primary,
            'middle_receiver': middle[index], 'new_identity': (name, new_id, split[1]), 'middle_owner': split,
            'destination_receiver': receiver, 'first_leg': origin + first, 'second_leg': (split, *second, *terminal),
            'first_nodes': first, 'second_nodes': (split, *second), 'terminal_nodes': terminal,
            'original_protection': original_profile, 'receiving_protection': _route_profile(continuation),
            'entry_groups': entry_groups, 'exit_groups': exit_groups,
            'reserve_previous': approval.get('reserve_with_previous', False),
            'crossing_zone': crossing_zone,
            'terminal_overlap': overlap, 'terminal_overlap_reference': old_overlap_reference,
            'occupied_entry': occupied,
            'occupied_berth': berth, 'occupied_review': occupied_review if berth is not None else None,
            'occupied_timing': timed_entry,
        }
    need(selected.keys() == requested.keys() and selected, 'Supply the precise set of operational Routes on the old pair')
    return selected, allocated


def _prepare_middle_zone_signals(project, selected):
    from collections import defaultdict

    from .signal_operating_fields import _append_indications, _indication_records

    requested = defaultdict(set)
    for row in selected.values():
        if row['crossing_zone'] is not None:
            requested[row['middle_owner']].add(row['crossing_zone']['native_aspect_code'])
    for key, expected in requested.items():
        owner = project.model(key)
        signal = owner.contents[11].value
        holder = signal.contents[10].value
        existing, codes = _indication_records(holder, owner)
        missing = sorted(expected - set(codes))
        if not missing:
            continue
        counts = incoming_counts(project.roots[key[0]])
        need(counts[id(holder)] == counts[id(holder.contents[0].value)] == 1
             and not route_factory.wrapper(owner.contents[15].value, 'OTRouteList')
             and len(existing) + len(missing) <= 64,
             'Adding middle speed aspects requires an exclusive signal list and no existing Routes at that signal')
        signal.contents[10].value = _append_indications(holder, existing, missing, owner)


def _split_crossing_zone(project, entry, middle_primary, zone):
    boundary = project.model(zone['split'])
    entry.contents[12].values[2] = boundary
    middle_primary.contents[12].values[1] = boundary
    indication, = route_factory.wrapper(middle_primary.contents[4].value, 'OTSigIndList')
    indication.contents[0].value = zone['native_aspect_code']
    if zone['head_only']:
        middle_primary.contents[11].value |= 2


def _rebind_movement(project, sequence, pair, parts):
    nodes = [sequence[0]]
    distance = 0
    crossings = []
    for a, b in zip(sequence, sequence[1:]):
        if a[0] != b[0]:
            connector = project.related(a)
            if connector in pair:
                first, second = parts[pair.index(connector)]
                nodes.extend((*first, *second))
                crossings.append(distance)
        distance += project.model(project.edge_between(a, b)).contents[9].values[1]
        nodes.append(b)
    need(len(set(nodes)) == len(nodes), 'The extended movement repeats a directional End')
    return nodes, distance, crossings


def _map_inserted_margins(project, owner, identity, position, old_distance, length, request):
    definition, = [obj for obj in project.dests if project.owners[id(obj)] == owner and ident(obj) == identity]
    wrapper, array, rows = _margin_members(definition)
    before = _margin_values(rows)
    positions = [row['position_m'] for row in before]
    need(all(isfinite(row['safety_margin_m']) and 0 <= row['position_m'] <= old_distance for row in before)
         and positions == sorted(positions), 'Invalid or unordered saved Itinerary safety margins')
    if not positions or positions[-1] < position:
        return None
    need(request is not None and request['expected_insertion_position_m'] == position,
         'The affected Itinerary has distance-based safety margins that require explicit remapping at the exact insertion position')
    need(request['at_boundary'] in ('upstream', 'downstream'), 'Choose the side of the insertion for its exact-boundary point')
    counts = incoming_counts(project.roots[owner[0]])
    need(all(counts[id(obj)] == 1 for obj in (wrapper, array, *rows)),
         'An affected Itinerary shares its safety-margin objects')
    move_at_boundary = request['at_boundary'] == 'downstream'
    new_positions = [_float32(value + length) if value > position or (value == position and move_at_boundary)
                     else value for value in positions]
    need(all(left == right or a < b for left, right, a, b
             in zip(positions, positions[1:], new_positions, new_positions[1:])),
         'The insertion would collapse distinct float32 safety-margin positions')
    for row, old, new in zip(rows, positions, new_positions, strict=True):
        if old != new:
            row.contents[0].values[0] = new
    return {'document': owner[0], 'identity': identity, 'insertion_position_m': position,
            'at_boundary': request['at_boundary'], 'before': before, 'after': _margin_values(rows)}


def _dependent_edits(project, before, pair, parts, selected, courses, middle_edges, operation):
    expected, rewrites = {}, {}
    margin_requests = operation.get('safety_margin_mappings', ())
    margins = {row['itinerary']: row for row in margin_requests}
    need(len(margins) == len(margin_requests), 'Each affected Itinerary safety-margin mapping must be unique')
    mapped = []
    for key, (sequence, references, _) in before.items():
        need(all(project.edge_between(a, b) not in middle_edges for a, b in zip(sequence, sequence[1:])),
             'The selected middle track already participates in a saved movement')
        if key[0] == 'route':
            owner, identity = key[1:]
            route = selected.get((owner[0], *identity))
            if route is not None:
                expected[key] = (list(route['first_leg']), None)
                expected['route', route['middle_owner'], route['new_identity']] = (list(route['second_leg']), None)
            else:
                expected[key] = (sequence, references)
            continue
        reviewed, distance, positions = _rebind_movement(project, sequence, pair, parts)
        need(len(positions) <= 1, 'An affected movement crosses the selected connector pair more than once')
        expected[key] = (reviewed, references)
        if not positions:
            continue
        kind, owner, identity = key
        if kind == 'itinerary':
            report = _map_inserted_margins(project, owner, identity, positions[0], distance,
                                           operation['expected_middle_length_m'], margins.get(identity[0]))
            if report is not None:
                mapped.append(report)
                del margins[identity[0]]
        elif kind == 'path':
            path = project.owned(owner, 'OTPath', identity)
            if not operation.get('path_speed_event_extensions'):
                _incident_bindings(courses, project, {'document': owner[0], **ref(path)})
            counts = incoming_counts(project.roots[owner[0]])
            need(counts[id(path.contents[4].value)] == 1, 'The dependent Path shares its Route references')
            changed = []
            for document, reference in references:
                route_id = document, reference['name'], reference['array_id'], reference['start_id']
                changed.append((document, reference))
                if route_id in selected:
                    continuation = selected[route_id]
                    name, array_id, start_id = continuation['new_identity']
                    changed.append((continuation['middle_owner'][0],
                                    {'name': name, 'array_id': array_id, 'start_id': start_id}))
            need(len(changed) > len(references), 'The affected Path has no exact primary Route to split')
            rewrites[key] = (path, changed)
            expected[key] = (reviewed, changed)
        else:
            raise ValueError('A non-Route movement cannot cross the inserted worksheet directly')
    need(not margins, 'A safety-margin mapping does not match a dependent Itinerary with points at or after the insertion')
    return expected, rewrites, mapped


def insert_document_span(documents, document_paths, catalog, document, operation, courses, run_bytes=None, *,
                         operating_banks=None):
    need(courses is not None, 'The original run-bound CourseList is required for endpoint reconnection')
    project = project_from(documents, document_paths, catalog)
    before = _movement_manifest(project)
    middle, parts, edges = _middle_chain(project, operation)
    pair = _old_pair(project, operation, document, middle)
    berth_reviews = [row for row in operation['routes'] if row.get('expected_occupied_entry_timing') is not None
                     or (row.get('expected_occupied_entry') or {}).get('expected_wait_s') is not None]
    need(not berth_reviews or (len(berth_reviews) == 1 and type(operating_banks) is dict
         and operating_banks.get('courses') == courses),
         'Review one inserted occupied-entry berth against the exact bound five operating archives')
    selected, allocated = _plan_routes(project, pair, middle, parts, operation, operating_banks, run_bytes)
    middle_edges = {(middle[0][0], edge) for edge in edges}
    expected, rewrites, mapped = _dependent_edits(project, before, pair, parts, selected, courses, middle_edges, operation)
    event_approvals = operation.get('path_speed_event_extensions', ())
    preserved_events = []
    if event_approvals:
        from .saved_path_speed_extensions import path_speed_extensions

        preserved_events = path_speed_extensions(project, courses, run_bytes, event_approvals, rewrites)
    ids = {(key[0].casefold(), key[3], key[2]) for key in selected}
    ids.update((row['middle_owner'][0].casefold(), row['middle_owner'][1], row['new_identity'][1])
               for row in selected.values())
    names = {row['old_identity'][0] for row in selected.values()} | {row['new_identity'][0] for row in selected.values()}
    _guard_incidents(courses, ids, names)
    _prepare_middle_zone_signals(project, selected)

    for row in selected.values():
        array = row['old_array']
        writer.set_elements(array, [item for item in path_functions.mutable_array(array)
                                    if item is not row['old_fragment']])
    new_pairs = [(outer, inner) for outer, inner in zip(pair, middle, strict=True)]

    def pair_request(ends):
        return {letter: {'document': key[0], 'end_id': key[1]} for letter, key in zip(('a', 'b'), ends, strict=True)}

    changed_documents, _ = replace_connectors(
        project, {'unlink': [pair_request(pair)], 'link': [pair_request(ends) for ends in new_pairs]})
    added = {}
    for row in selected.values():
        entry = _add_route(project, row['middle_receiver'], row['old_identity'], row['first_nodes'],
                           groups=row['entry_groups'])
        new = _add_route(project, row['middle_owner'], row['new_identity'], row['second_nodes'], primary=True,
                         groups=row['exit_groups'], reserve_previous=row['reserve_previous'])
        _add_route(project, row['destination_receiver'], row['new_identity'], row['terminal_nodes'],
                   original=row['old_fragment'])
        if row['crossing_zone'] is not None:
            _split_crossing_zone(project, entry, new, row['crossing_zone'])
        if row['terminal_overlap'] is not None:
            set_overlap_reference(row['old_primary'], ('', -1))
            set_overlap_reference(new, row['terminal_overlap_reference'])
        occupied = row['occupied_entry']
        if occupied is not None:
            row['old_primary'].contents[6].values[:] = DEFAULT_OCCUPIED_ENTRY
            new.contents[6].values[:] = occupied['values']
            project.model(row['middle_owner']).contents[11].value.contents[9].values[2] = occupied['relay_signal_flags']
        if row['occupied_timing'] is not None:
            apply_inserted_occupied_timing(row['old_primary'], new, row['occupied_timing']['timing'])
        row['middle_entry_protection'] = _route_profile(entry)
        row['middle_exit_protection'] = _route_profile(new)
        new_ref = ref(new)
        added[row['middle_owner'][0], new_ref['name'], new_ref['array_id'], new_ref['start_id']] = new
    for owner, allocated_id in allocated.items():
        project.model(owner).contents[19].value = allocated_id
    for key, (path, references) in rewrites.items():
        infos = []
        for sheet, reference in references:
            identity = reference['name'], reference['array_id'], reference['start_id']
            resolved = added.get((sheet, *identity))
            if resolved is None:
                resolved = project.owned((sheet, identity[2]), 'OTRoute', identity)
            infos.append(inf(resolved))
        path.contents[4].value = path_functions.array_like(path.contents[4].value, infos)
        changed_documents.add(key[1][0])
    changed_documents.update(row['document'] for row in mapped)

    output = {name: writer.dump_verified(project.roots[name], project.versions[name]) for name in sorted(changed_documents)}
    fresh = project_from({**documents, **output}, document_paths, catalog)
    after = _movement_manifest(fresh)
    need(after.keys() == expected.keys()
         and all(after[key][:2] == specification for key, specification in expected.items()),
         'A native movement or ordered Route/Path reference differs after reloading the insertion')
    for key, (sequence, refs, geometry) in before.items():
        if after[key][:2] == (sequence, refs):
            need(after[key][2] == geometry, 'An unrelated movement lost its directional operating profile')
        elif key[0] in ('itinerary', 'path'):
            expected_distance = sum(row[1] for row in geometry) + operation['expected_middle_length_m']
            need(expected_distance <= 2147483647 and sum(row[1] for row in after[key][2]) == expected_distance,
                 'The dependent movement does not gain exactly the reviewed inserted length')
    need(all(fresh.block_end(a) == b and fresh.block_end(b) == a for a, b in new_pairs),
         'The reloaded connector endpoints differ from the reviewed reconnection')
    verify_margin_profiles(fresh, mapped)
    if preserved_events:
        need(path_speed_extensions(fresh, courses, run_bytes, event_approvals, rewrites) == preserved_events,
             'The same original Path-speed Incidents did not resolve after native readback')
    for row in selected.values():
        for owner, identity, profile in (
            (row['owner'], row['old_identity'], row['original_protection']),
            (row['middle_receiver'], row['old_identity'], row['middle_entry_protection']),
            (row['middle_owner'], row['new_identity'], row['middle_exit_protection']),
            (row['destination_receiver'], row['new_identity'], row['receiving_protection']),
        ):
            need(_route_profile(fresh.owned(owner, 'OTRoute', identity)) == profile,
                 'An original or newly approved Route protection profile differs after native readback')
        zone = row['crossing_zone']
        if zone is not None:
            fragments = ((row['owner'], row['old_identity'], (zone['start'], None)),
                         (row['middle_receiver'], row['old_identity'], (None, zone['split'])),
                         (row['middle_owner'], row['new_identity'], (zone['split'], None)),
                         (row['destination_receiver'], row['new_identity'], (None, zone['finish'])))
            need(all(_stored_zone(fresh, fresh.owned(owner, 'OTRoute', identity)) == expected
                     for owner, identity, expected in fragments),
                 'Saved source, relay or terminal slow-zone anchors differ after native readback')
            signal = fresh.model(zone['split']).contents[11].value
            need(sum(ind.contents[0].value == zone['native_aspect_code']
                     and ind.contents[1].value is fresh.model(zone['split'])
                     for ind in route_factory.wrapper(signal.contents[10].value, 'OTSigIndList')) == 1,
                 'The new relay signal does not own the exact saved speed aspect')
        if row['terminal_overlap'] is not None:
            successor = fresh.owned(row['middle_owner'], 'OTRoute', row['new_identity'])
            need(overlap_reference(successor) == row['terminal_overlap_reference']
                 and terminal_overlap(fresh, successor, row['terminal_overlap']) == row['terminal_overlap'],
                 'The overlap target or its original resources changed after native readback')
        occupied = row['occupied_entry']
        if occupied is not None:
            successor = fresh.owned(row['middle_owner'], 'OTRoute', row['new_identity'])
            source, source_flags = _occupied_signal(fresh, row['owner'])
            relay, relay_flags = _occupied_signal(fresh, row['middle_owner'])
            terminal, edge = occupied['terminal'], occupied['stop_edge']
            approved = {'terminal_end': {'document': terminal[0], 'end_id': terminal[1]}, 'stop_edge_id': edge[1]}
            need(_occupied_stop(fresh, successor, approved) == (terminal, edge)
                 and (source.contents[0].value, source_flags) == (occupied['original_signal_id'], occupied['original_signal_flags'])
                 and (relay.contents[0].value, relay_flags) == (occupied['relay_signal_id'], occupied['relay_signal_flags']),
                 'Occupied-entry terminal or authorized signals differ after native readback')
            if row['occupied_berth'] is not None:
                front = fresh.owned(row['owner'], 'OTRoute', row['old_identity'])
                need(front.contents[11].value == successor.contents[11].value == 0
                     and tuple(successor.contents[6].values) == occupied['values']
                     and tuple(front.contents[6].values) == DEFAULT_OCCUPIED_ENTRY,
                     'The independently reserved successor must exclusively own the reviewed occupied entry')
                handoff = _review_occupied_handoff(
                    fresh, front, successor, row['occupied_berth'], row['occupied_review'],
                    operating_banks, run_bytes, operation['expected_middle_length_m'])
                occupied['reviewed_wait_berth' if occupied['values'][0] == 7 else 'reviewed_speed_berth'] = handoff
                if row['occupied_timing'] is not None:
                    front_fragment = fresh.owned(row['middle_receiver'], 'OTRoute', row['old_identity'])
                    terminal_fragment = fresh.owned(row['destination_receiver'], 'OTRoute', row['new_identity'])
                    occupied['reviewed_timing'] = check_inserted_occupied_timing(
                        fresh, front, front_fragment, successor, terminal_fragment, handoff, row['occupied_timing'])
    return output, {
        'action': operation['action'], 'document': document, 'inserted_document': middle[0][0],
        'removed_direct_crossing': pair, 'new_connector_pairs': new_pairs,
        'inserted_length_m': operation['expected_middle_length_m'],
        'rewritten_routes': [{'retained_owner': row['owner'], 'retained_route': row['old_identity'],
                              'intermediate_owner': row['middle_owner'], 'added_route': row['new_identity'],
                              'retained_protection': row['original_protection'],
                              'preserved_receiving_protection': row['receiving_protection'],
                              'middle_entry_protection': row['middle_entry_protection'],
                              'middle_exit_protection': row['middle_exit_protection'],
                              **({'transferred_terminal_overlap': row['terminal_overlap']}
                                 if row['terminal_overlap'] else {}),
                              **({'transferred_occupied_entry': row['occupied_entry']} if row['occupied_entry'] else {}),
                              **({'split_cross_document_slow_zone': row['crossing_zone']} if row['crossing_zone'] else {})}
                             for row in selected.values()],
        'rewritten_paths': [{'owner': key[1], 'path': key[2]} for key in rewrites],
        'itinerary_and_catalog_references_preserved': True, 'changed_documents': sorted(output),
        'mapped_safety_margin_profiles': mapped,
        'extended_path_speed_events': preserved_events,
        'movement_count_checked': len(after), 'native_execution_tested': False,
    }
