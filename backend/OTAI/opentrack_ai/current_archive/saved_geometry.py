"""Dependency-bound edits of current native worksheet graph objects."""

import math

from . import course_factories, native_monitoring, path_functions, route_factory, writer
from .graph_references import reference_inventory
from .itinerary_edit_tools import EditableItineraryProject
from .multi_document.core import ident, layout, need
from . import saved_station_areas
from .station_operations import _snapshot
from .tools import sha
from .zero_generation import native_signal_routes, topology


UNSET_KILOMETRE = -99999.0


def project_from(documents, paths, dest):
    project = EditableItineraryProject(
        documents, document_paths=paths,
        expected_hashes={name: sha(data) for name, data in documents.items()},
        complete_document_set=True,
    )
    project.check_dest_catalog(dest)
    return project


def model_id(obj):
    return obj.contents[0].value


def selected(project, document, ident, *classes):
    obj = project.model((document, ident))
    need(writer.kind(obj) in classes, f'Unexpected selected model class for {document}:{ident}')
    return obj


def position(obj):
    return [float(obj.contents[slot].value) for slot in (2, 3)]


def _end_shape(end):
    connector = writer.kind(end) == 'OTConnModel'
    topology.need(connector or writer.kind(end) == 'OTEndModel', 'Expected a native End or Connector')
    parents = [('OTEndModel', 7), ('OTGraphicModel', 1), ('NSObject', 0)]
    layout(end, ([('OTConnModel', 1)] if connector else []) + parents,
           route_factory.END + (['@', '@', 'i', 'i'] if connector else []))


def _locality(end):
    value = float(end.contents[14].value)
    need(math.isfinite(value), 'Saved kilometre point is not finite')
    return None if value == UNSET_KILOMETRE else value


def _vertex_details(end):
    signal = end.contents[11].value
    tracks = [end.contents[slot].value for slot in (9, 10) if end.contents[slot].value is not None]
    view = {
        'end_id': model_id(end),
        'type': writer.kind(end),
        'name': None if end.contents[18].value is None else path_functions.string(end.contents[18].value),
        'kilometre_point': _locality(end),
        'xy': position(end),
        'angle': float(end.contents[1].value),
        'alignment': [end.contents[slot].value for slot in (4, 5)],
        'incident_edge_ids': [model_id(track) for track in tracks],
        'incident_edge_exclusions': [
            {'edge_id': model_id(track),
             'target_edge_id': None if track.contents[13].value is None else model_id(track.contents[13].value),
             'source_edge_id': None if track.contents[14].value is None else model_id(track.contents[14].value)}
            for track in tracks if writer.kind(track) == 'OTEdgeModel' and track.clazz.version == 3
        ],
        'switch_time_s': float(end.contents[21].value),
        'default_second_leg': bool(end.contents[22].value),
        'detector_flags': list(end.contents[23].values),
        'safety_element_id': model_id(end.contents[7].value),
        'signal_id': None if signal is None else model_id(signal),
        'station_end_type': end.contents[20].value,
        'station_model_id': None if end.contents[12].value is None else model_id(end.contents[12].value),
        'station_sign': None if end.contents[12].value is None
        else path_functions.string(end.contents[12].value.contents[7].value),
    }
    if signal is not None and writer.kind(signal) == 'OTSignalModel' and signal.clazz.version == 11:
        route_factory.layout(signal, 'OTSignalModel', 11, route_factory.SIGNAL, graphic=True)
        view['signal_sight_m'] = signal.contents[9].values[1]
    if writer.kind(end) == 'OTConnModel':
        view['remote'] = {'document': path_functions.string(end.contents[25].value),
                          'end_id': end.contents[26].value}
    return view


def inspect_vertex(blob, end_id):
    root, _ = writer.load_next_compatible(blob)
    _, models = route_factory.document(root)
    first = models[end_id]
    _end_shape(first)
    second = models[first.contents[8].value]
    _end_shape(second)
    need(second is not first and second.contents[8].value == end_id, 'Nonreciprocal paired End')
    a, b = map(_vertex_details, (first, second))
    return {'ends': [a, b], 'pair_checks': {
        'same_position': a['xy'] == b['xy'],
        'same_kilometre_point': a['kilometre_point'] == b['kilometre_point'],
        'same_name': a['name'] == b['name'],
    }}


def set_vertex_details(project, document, operation):
    first = selected(project, document, operation['end_id'], 'OTEndModel', 'OTConnModel')
    second = project.model(project.related(project.key(first)))
    edited = (first, second) if operation['both_halves'] else (first,)
    before = [_vertex_details(end) for end in edited]
    changes = operation['changes']
    for end in edited:
        if 'name' in changes:
            end.contents[18].value = native_signal_routes.string(changes['name'])
        if 'kilometre_point' in changes:
            value = changes['kilometre_point']
            end.contents[14].value = topology.flt(UNSET_KILOMETRE if value is None else value, 'Kilometre point')
        if {'switch_time_s', 'default_second_leg'}.intersection(changes):
            need(writer.kind(end) == 'OTEndModel' and all(end.contents[slot].value is not None for slot in (9, 10)),
                 'Switch settings require a real two-branch ordinary End')
            if 'switch_time_s' in changes:
                end.contents[21].value = topology.flt(changes['switch_time_s'], 'Switch time')
            if 'default_second_leg' in changes:
                end.contents[22].value = int(changes['default_second_leg'])
    return {'before': before, 'after': [_vertex_details(end) for end in edited]}


def _sighting_signal(project, document, end_id, signal_id):
    end = selected(project, document, end_id, 'OTEndModel')
    signal = selected(project, document, signal_id, 'OTSignalModel')
    route_factory.layout(signal, 'OTSignalModel', 11, route_factory.SIGNAL, graphic=True)
    need(signal.contents[7].value is end and end.contents[11].value is signal
         and signal.contents[8].values[0] in {1, 2, 3, 24, 25, 26, 27},
         'Select the exact directional End and its current main or distant signal')
    return signal


def set_signal_sight(project, document, operation):
    signal = _sighting_signal(project, document, operation['end_id'], operation['signal_id'])
    prior, sight = signal.contents[9].values[1], operation['sight_m']
    need(prior == operation['expected_sight_m'], 'Saved signal sight differs from the reviewed distance')
    need(type(sight) is int and 1 <= sight <= 100000 and sight != prior,
         'Choose a different positive whole-metre signal sight distance')
    signal.contents[9].values[1] = sight
    return {'end_id': operation['end_id'], 'signal_id': operation['signal_id'],
            'before_sight_m': prior, 'after_sight_m': sight}


def _verify_signal_sight(project, document, report, source_fingerprint):
    signal = _sighting_signal(project, document, report['end_id'], report['signal_id'])
    values = signal.contents[9].values
    need(values[1] == report['after_sight_m'], 'Fresh signal sight readback differs')
    values[1] = report['before_sight_m']
    try:
        need(writer.fingerprint(project.roots[document]) == source_fingerprint,
             'A non-sighting field or native object reference changed')
    finally:
        values[1] = report['after_sight_m']


def calculate_kilometre_points(project, operation):
    if operation['itinerary'] is not None:
        target, = [dest for dest in project.dests
                   if path_functions.string(dest.contents[1].value) == operation['itinerary']]
        route, _ = project.dest_view(target)
    else:
        route = [_connector_key(item) for item in operation['end_sequence']]
    need(len(route) >= 2 and len(route) == len(set(route)),
         'Choose a continuous directed movement without repeated Ends')
    for key in route:
        selected(project, *key, 'OTEndModel')
    first = route[0]
    origin = operation['start_km']
    if origin is None:
        raw = [_locality(project.model(key)) for key in (first, project.related(first))]
        present = {value for value in raw if value is not None}
        need(len(present) == 1, 'Supply start_km or one consistent saved kilometre point at the start')
        origin, = present
    direction = 1 if operation['direction'] == 'increasing' else -1
    distance = 0
    markings = {}

    def mark(key):
        value = origin + direction * distance / 1000
        need(-10000 <= value <= 10000, 'Calculated kilometre point outside supported range')
        stored = topology.flt(value, 'Calculated kilometre point')
        need(key not in markings or markings[key] == stored, 'Movement revisits a vertex with a different kilometre point')
        markings[key] = stored

    for a, b in zip(route, route[1:]):
        pair = project.related(a)
        mark(a)
        mark(pair)
        if writer.kind(project.model(pair)) == 'OTConnModel':
            remote = project.block_end(pair)
            mark(remote)
            mark(project.related(remote))
        edge = project.model(project.edge_between(a, b))
        distance += edge.contents[9].values[1]
    mark(route[-1])
    mark(project.related(route[-1]))
    changes = []
    for key, value in markings.items():
        end = project.model(key)
        prior = _locality(end)
        need(prior is None or math.isclose(prior, float(value), rel_tol=0.0, abs_tol=0.001)
             or operation['replace_conflicting'], f'Saved kilometre point conflicts at {key[0]}:{key[1]}')
        if prior != value:
            end.contents[14].value = value
            changes.append({'document': key[0], 'end_id': key[1], 'before_km': prior, 'after_km': value})
    need(changes, 'Calculated kilometre points are already stored')
    return {item['document'] for item in changes}, {
        'start_km': origin, 'direction': operation['direction'], 'physical_distance_m': distance,
        'marked_end_count': len(markings), 'changes': changes,
    }


def translate_end_graphics(end, origin, target):
    allowed = {(id(end), slot, 0) for slot in (2, 3)}
    marker = None
    signal = end.contents[11].value
    if signal is not None:
        offsets = [coord - base for coord, base in zip(position(signal), origin)]
        for slot, base, offset in zip((2, 3), target, offsets):
            value = topology.flt(float(base) + offset, 'Signal coordinate')
            need(math.isclose(float(value) - float(base), offset, rel_tol=1e-6, abs_tol=0.0001),
                 'Signal offset cannot be preserved at these float32 coordinates')
            signal.contents[slot].value = value
            allowed.add((id(signal), slot, 0))
        marker = {'id': model_id(signal), 'offset': offsets, 'xy': position(signal)}
    for slot, coordinate in zip((2, 3), target):
        end.contents[slot].value = coordinate
    return allowed, marker


def attached_measuring_instruments(project, document, ends):
    owners = [end for end in ends if end.contents[13].value is not None]
    if not owners:
        return []
    _, counts = reference_inventory(project.roots[document])
    attached = []
    for end in owners:
        instrument = end.contents[13].value
        need(writer.kind(instrument) == 'OTMeasuringModel', 'Unknown native measuring-instrument attachment')
        native_monitoring.instrument_shape(instrument)
        need(project.byid[document].get(model_id(instrument)) is instrument and instrument.contents[7].value is end
             and counts[id(instrument)] == 2, 'Measuring instrument does not have a unique reciprocal local End')
        edges = path_functions.mutable_array(instrument.contents[12].value)
        need(all(writer.kind(edge) == 'OTEdgeModel' and project.byid[document].get(model_id(edge)) is edge for edge in edges),
             'Measuring instrument has a foreign monitored Edge')
        attached.append((end, instrument))
    return attached


def instrument_graphics(end, instrument):
    return {'end_id': model_id(end), 'id': model_id(instrument), 'xy': position(instrument),
            'alignment': [instrument.contents[slot].value for slot in (4, 5)],
            'angle': instrument.contents[1].value,
            'frame': [*instrument.contents[9].values, *instrument.contents[10].values],
            'edge_ids': [model_id(edge) for edge in path_functions.mutable_array(instrument.contents[12].value)]}


def _translate_measuring_instrument(end, instrument, origin, target):
    before = instrument_graphics(end, instrument)

    def translated(point):
        values = []
        for coordinate, old, new in zip(point, origin, target, strict=True):
            offset = coordinate - old
            value = topology.flt(new + offset, 'Measuring instrument coordinate')
            need(math.isclose(value - new, offset, rel_tol=1e-6, abs_tol=0.0001),
                 'Instrument offset cannot be preserved at these float32 coordinates')
            values.append(value)
        return values

    # The stock instrument window can have an all-zero deferred frame. In that
    # case reloading derives the display from its stored GraphicModel location.
    frame = before['frame']
    has_saved_frame = any(frame)
    need(all(map(math.isfinite, frame)) and (not has_saved_frame or min(frame[2:]) > 0),
         'Unrecognized native measuring-instrument frame')
    xy = translated(before['xy'])
    for slot, value in zip((2, 3), xy, strict=True):
        instrument.contents[slot].value = value
    allowed = {(id(instrument), slot, 0) for slot in (2, 3)}
    if has_saved_frame:
        instrument.contents[9].values = translated(frame[:2])
        allowed.update((id(instrument), 9, index) for index in (0, 1))
    return allowed, {'before': before, 'after': instrument_graphics(end, instrument)}


def move_vertex(project, document, operation):
    first = selected(project, document, operation['end_id'], 'OTEndModel', 'OTConnModel')
    second = project.model(project.related(project.key(first)))
    need(position(first) == position(second), 'Paired Ends have different saved coordinates')
    origin = position(first)
    target = [topology.flt(operation[axis], axis) for axis in ('x', 'y')]
    need(origin != target, 'New coordinates round to the existing position')
    need(all(math.isfinite(coord) for coord in origin), 'Source coordinates are not finite')
    allowed = set()
    before = _snapshot(project.roots[document])
    instruments = []
    for end, instrument in attached_measuring_instruments(project, document, (first, second)):
        fields, moved = _translate_measuring_instrument(end, instrument, origin, target)
        allowed.update(fields)
        instruments.append(moved)
    signals = []
    for end in (first, second):
        fields, marker = translate_end_graphics(end, origin, target)
        allowed.update(fields)
        if marker is not None:
            signals.append(marker)
    after = _snapshot(project.roots[document])
    need(before.keys() == after.keys() and all(after[key] == value for key, value in before.items()
                                              if key not in allowed),
         'A drawing translation changed unrelated native fields')
    return {'end_ids': [model_id(first), model_id(second)], 'before_xy': origin, 'after_xy': target,
            'signals': signals, 'instruments': instruments}


def _edge(project, document, operation, *, reviewed_exclusions=(), reviewed_instrument_observers=0):
    edge = selected(project, document, operation['edge_id'], 'OTEdgeModel')
    root = project.roots[document]
    _, incoming = reference_inventory(root)
    annotations = 0
    for slot, reverse in ((13, 14), (14, 13)):
        other = edge.contents[slot].value
        if other is not None:
            need(writer.kind(other) == 'OTEdgeModel' and project.byid[document].get(model_id(other)) is other
                 and other is not edge and other.contents[reverse].value is edge,
                 'Unexpected nonreciprocal Edge Exclusion Link')
            pair = (model_id(edge), model_id(other)) if slot == 13 else (model_id(other), model_id(edge))
            need(pair in reviewed_exclusions, 'A direct Edge Exclusion Link requires an explicit reviewed transfer')
            annotations += 1
    need(incoming[id(edge)] == 3 + annotations + reviewed_instrument_observers,
         'An Edge has archived observers besides its reviewed native attachments')
    need(all(edge.contents[index].value is None for index in (6, 17, 18)),
         'Linked track, direct exclusion or auxiliary Edge references require their own edit contract')
    profile, _, radius, gradient, loop_type, link_type = edge.contents[9].values
    need((profile, loop_type, link_type) == (1, 1, 1) and all(map(math.isfinite, (radius, gradient))),
         'Unsupported Edge profile or non-finite physical fields')
    return edge


def _speed_table(edge):
    table = edge.contents[16].value
    speeds = course_factories.dictionary(table)
    keys = [path_functions.string(key) for key in path_functions.mutable_array(edge.contents[15].value)]
    need(keys and len(set(keys)) == len(keys) and set(keys) == set(speeds),
         'Speed keys and dictionary do not match')
    for key, speed in speeds.items():
        route_factory.layout(speed, 'OTSpeed', 0, ['@', 'i', 'i', 'i'])
        need(path_functions.string(speed.contents[0].value) == key and speed.contents[3].value == 0,
             'Unsupported directional speed key or ancillary speed flags')
        need(all(type(speed.contents[i].value) is int for i in (1, 2)), 'Malformed directional speeds')
    return speeds


def reverse_edge(project, document, operation):
    edge = _edge(project, document, operation)
    first, last = (edge.contents[i].value for i in (7, 8))
    old_speeds = _speed_table(edge)
    # Duplicate the speed dictionary and records so a neighbouring Edge's
    # shared table is never changed as a side effect of reversal.
    table = path_functions.clone(edge.contents[16].value)
    groups = list(table.contents)
    for position in range(2, len(groups), 2):
        speed = path_functions.clone(groups[position].value)
        speed.contents[1].value, speed.contents[2].value = speed.contents[2].value, speed.contents[1].value
        groups[position].value = speed
    edge.contents[16].value = table
    edge.contents[7].value, edge.contents[8].value = last, first
    gradient = float(edge.contents[9].values[3])
    edge.contents[9].values[3] = topology.flt(-gradient, 'Reversed gradient')
    need(all([record.contents[1].value, record.contents[2].value]
             == [old_speeds[key].contents[2].value, old_speeds[key].contents[1].value]
             for key, record in _speed_table(edge).items()), 'Reversed speed table proof failed')
    return {'edge_id': model_id(edge), 'before_end_ids': [model_id(first), model_id(last)],
            'after_end_ids': [model_id(last), model_id(first)],
            'length_m': edge.contents[9].values[1], 'before_gradient_per_mille': gradient,
            'after_gradient_per_mille': edge.contents[9].values[3]}


def _movement_items(project):
    for route in project.routes:
        yield project.owners[id(route)], route
    for marker in project.shunting_movements:
        owner, name = marker
        models = route_factory.wrapper(project.model(owner).contents[16].value, 'OTShuntingList')
        path, = [item for item in models if ident(item)[0] == name]
        body, = path_functions.mutable_array(path.contents[0].value)
        yield owner, body


def _insert_movement_nodes(project, document, insert_for, *, unique_arrays=False):
    counts = reference_inventory(project.roots[document])[1] if unique_arrays else None
    updated = []
    for owner, movement in _movement_items(project):
        if owner[0] != document:
            continue
        array = movement.contents[0].value
        nodes = path_functions.mutable_array(array)
        changed = []
        # A continuation's first ordinary saved End is reached from its
        # connector's local pair. A normal movement begins at its owner End.
        if writer.kind(project.model(owner)) == 'OTConnModel':
            changed.extend(insert_for(project.model(project.related(owner)), nodes[0]))
        for current, following in zip(nodes, nodes[1:]):
            changed.append(current)
            changed.extend(insert_for(project.model(project.actual_related(project.key(current))), following))
        changed.append(nodes[-1])
        if changed != nodes:
            need(counts is None or counts[id(array)] == 1, 'A movement shares its native End sequence array')
            need(not unique_arrays or len(set(changed)) == len(set(nodes)) + len(changed) - len(nodes),
                 'A replacement would repeat a directional End within its saved Route or Shunting')
            movement.contents[0].value = path_functions.array_like(array, changed)
            if movement.contents[5].values[4] != -1:
                movement.contents[5].values[4] = len(changed)
            updated.append({'kind': writer.kind(movement), 'owner': owner,
                            'name': path_functions.string(movement.contents[1].value)})
    return updated


def _split_platform_context(project, document, operation, first, last):
    from .saved_cross_platform_halts import _platform, _station_areas, _stop_markers

    reference = operation['reference_document']
    members, distances, length, exit_signal, connectors = _platform(project, reference, operation)
    key = document, operation['edge_id']
    edges = [project.edge_between(a, b) for a, b in zip(members, members[1:])]
    need(edges.count(key) == 1, 'The selected Edge must occur once on the reviewed connected platform')
    station = _station_areas(project, reference, operation).get(document)
    need(station is not None and all(writer.kind(end) == 'OTEndModel'
         and end.contents[12].value is station and end.contents[20].value in (1, 2)
         for end in (first, last)), 'Both stored Edge halves must carry the selected local station area')
    index = edges.index(key)
    stored_ends = project.key(first), project.key(last)
    travelled_ends = project.actual_related(members[index]), members[index + 1]
    need(travelled_ends in (stored_ends, stored_ends[::-1]), 'The selected Edge traverses unexpected native halves')
    forward = travelled_ends == stored_ends
    markers = [(row, distances[(row['document'], row['end_id'])]) for row in _stop_markers(project, members[:-1])]
    return station, (edges, index, forward, length, exit_signal, connectors, markers)


def _verify_cross_platform_split(project, document, operation, report):
    from .saved_cross_platform_halts import _platform, _station_areas, _stop_markers
    from .saved_station_areas import end_pair

    reference = operation['reference_document']
    expected = report['cross_platform']
    updated = {**operation, 'expected_platform_edge_ids': expected['ordered_edges']}
    members, distances, length, exit_signal, connectors = _platform(project, reference, updated)
    markers = [(row, distances[(row['document'], row['end_id'])]) for row in _stop_markers(project, members[:-1])]
    need((length, exit_signal, connectors, markers) == (expected['length_m'], expected['exit_signal'],
         expected['connector_pair'], expected['halt_markers']), 'Splitting the platform changed a native stop or connector')
    station = _station_areas(project, reference, operation)[document]
    for end_id in report['new_end_ids']:
        end = project.model((document, end_id))
        end_pair(project, document, end)
        need(end.contents[12].value is station and end.contents[20].value == 1,
             'The inserted paired platform halves must retain local station membership')


def split_edge(project, document, operation, shapes):
    edge = _edge(project, document, operation)
    _speed_table(edge)
    first, last = (edge.contents[slot].value for slot in (7, 8))
    station = None
    cross_platform = None
    if operation['action'] == 'split_platform_edge':
        station = saved_station_areas.platform_split_station(project, document, operation, first, last)
    elif operation['action'] == 'split_cross_document_platform_edge':
        need(edge.contents[9].values[1] == operation['expected_edge_length_m'],
             'The connected platform Edge length differs from the review')
        station, cross_platform = _split_platform_context(project, document, operation, first, last)
    else:
        need(first.contents[12].value is None or first.contents[12].value is not last.contents[12].value,
             'Use split_platform_edge for an Edge contained in a saved station area')
    total, division = edge.contents[9].values[1], operation['first_length_m']
    need(0 < division < total, 'Both new links must have positive physical length')
    before_xy, after_xy = position(first), position(last)
    dx, dy = (b - a for a, b in zip(before_xy, after_xy))
    need((dx == 0) != (dy == 0), 'This split requires a nonzero horizontal or vertical drawing segment')
    fraction = division / total
    midpoint = [topology.flt(a + (b - a) * fraction, 'Split coordinate')
                for a, b in zip(before_xy, after_xy)]
    need(midpoint != before_xy and midpoint != after_xy, 'Drawing precision collapses one split link')
    builder = topology.Builder(shapes)
    need(builder.stream_version == project.versions[document], 'Shape and worksheet stream versions differ')
    builder.high = max(project.byid[document])
    new_pair = builder.vertex({
        'x': float(midpoint[0]), 'y': float(midpoint[1]), 'orientation': 'horizontal' if dy == 0 else 'vertical',
        'names': ['', ''], 'insulated_joint': [False, False], 'axle_counter': [False, False],
    })
    def alignment(end):
        return tuple(end.contents[slot].value for slot in (4, 5))
    by_alignment = {alignment(end): end for end in new_pair}
    need({alignment(first), alignment(last)} == by_alignment.keys(),
         'Original Ends must have opposite reviewed alignments matching the drawing axis')
    left, right = by_alignment[alignment(last)], by_alignment[alignment(first)]
    new_edge = path_functions.clone(edge)
    need(builder.high < 2147483646, 'Graphic ID exhausted')
    new_edge.contents[0].value = builder.high + 1
    new_edge.contents[7].value = right
    new_edge.contents[9].values[1] = total - division
    edge.contents[8].value = left
    edge.contents[9].values[1] = division
    last_slot, = [slot for slot in (9, 10) if last.contents[slot].value is edge]
    last.contents[last_slot].value = new_edge
    left.contents[9].value, right.contents[9].value = edge, new_edge
    safety = first.contents[7].value
    need(last.contents[7].value is safety, 'Split would change the original exclusive track section')
    holder = safety.contents[7].value
    safety.contents[7].value = path_functions.array_like(holder, [*path_functions.mutable_array(holder), left, right])
    left.contents[7].value = right.contents[7].value = safety
    if station is not None:
        for half in (left, right):
            need(half.contents[20].value == 1, 'New platform vertex must be an ordinary Native End')
            half.contents[12].value = station
    inserts = {(first, last): (left,), (last, first): (right,)}
    updated = _insert_movement_nodes(project, document, lambda a, b: inserts.get((a, b), ()))
    collection = project.roots[document].contents[2]
    collection.value = path_functions.array_like(collection.value, [*project.models[document], left, right, new_edge])
    inserted_ids = [model_id(left), model_id(right)]
    report = {'edge_id': model_id(edge), 'new_edge_id': model_id(new_edge), 'new_end_ids': inserted_ids,
              'lengths_m': [division, total - division], 'safety_element_id': model_id(safety), 'movements': updated}
    if station is not None:
        report.update(station_id=model_id(station), station_sign=path_functions.string(station.contents[7].value),
                      station_member_end_ids_added=inserted_ids)
    if cross_platform is not None:
        edges, index, forward, length, exit_signal, connectors, markers = cross_platform
        pieces = [edges[index], (document, model_id(new_edge))]
        edges[index:index + 1] = pieces if forward else reversed(pieces)
        report['cross_platform'] = {'ordered_edges': [{'document': name, 'edge_id': edge_id} for name, edge_id in edges],
                                    'length_m': length, 'exit_signal': exit_signal, 'connector_pair': connectors,
                                    'halt_markers': markers}
    return report


def _connector_key(value):
    return value['document'], value['end_id']


def _unoccupied_connector_end(project, key, counts):
    end = selected(project, *key, 'OTEndModel', 'OTConnModel')
    need(all(end.contents[index].value is None for index in (9, 10, 11, 12, 13)),
         'Connector side is occupied by track, a signal, station membership or a measuring instrument')
    related_key = project.related(key)
    related = selected(project, *related_key, 'OTEndModel')
    need(related.contents[11].value is None and end.contents[20].value == 1,
         'Connector requires a plain paired End without a signal')
    need(counts[key[0]][id(end)] == 2,
         'A connector End has archived observers besides the owner document and Safety Element')
    need(all(not route_factory.wrapper(end.contents[slot].value, kind)
             for slot, kind in ((15, 'OTRouteList'), (16, 'OTShuntingList'), (17, 'OTPathList'))),
         'Connector End owns saved movement definitions')
    return end


def replace_connectors(project, operation):
    unlink = [tuple(_connector_key(pair[field]) for field in ('a', 'b')) for pair in operation['unlink']]
    link = [tuple(_connector_key(pair[field]) for field in ('a', 'b')) for pair in operation['link']]
    removing = [key for pair in unlink for key in pair]
    adding = [key for pair in link for key in pair]
    need(removing or adding, 'Supply at least one exact connector pair to remove or add')
    need(len(set(removing)) == len(removing) and len(set(adding)) == len(adding),
         'A connector endpoint may occur only once on each side of the edit')
    need({frozenset(pair) for pair in unlink}.isdisjoint(map(frozenset, link)),
         'Do not re-add the identical connector pair')
    affected = {key[0] for key in removing + adding}
    counts = {name: reference_inventory(project.roots[name])[1] for name in affected}
    ends = {key: _unoccupied_connector_end(project, key, counts) for key in set(removing + adding)}
    for a, b in unlink:
        need(project.block_end(a) == b and project.block_end(b) == a, 'Expected exact reciprocal existing pair')
    for a, b in link:
        need(a[0] != b[0], 'Only external two-document connector pairs are supported')
        need(all(key in removing or writer.kind(ends[key]) == 'OTEndModel' for key in (a, b)),
             'Unlink an existing connector before assigning a new partner')
    for key in removing:
        end = ends[key]
        end.clazz = end.clazz.superclass
        end.contents = end.contents[:24]
    for a, b in link:
        for key, remote in ((a, b), (b, a)):
            end = ends[key]
            end.clazz = writer.Class(b'OTConnModel', 1, end.clazz)
            end.contents += [writer.TypedValue(b'@', native_signal_routes.string('')),
                             writer.TypedValue(b'@', native_signal_routes.string(remote[0])),
                             writer.TypedValue(b'i', remote[1]), writer.TypedValue(b'i', 0)]
    return affected, {'removed_pairs': unlink, 'added_pairs': link}


def _selected_elements(project, document, elements):
    need(len(set(elements)) == len(elements), 'Select distinct Safety Element IDs')
    counts = reference_inventory(project.roots[document])[1]
    selected_elements = []
    for ident in elements:
        element = selected(project, document, ident, 'OTElement')
        members = path_functions.mutable_array(element.contents[7].value)
        need(members and counts[id(element)] == len(members) + 1 and element.contents[6].value is None,
             'Safety Element is empty or has unsupported observers or graphic references')
        selected_elements.append((element, members))
    return selected_elements


def _set_element_members(element, members):
    element.contents[7].value = path_functions.array_like(element.contents[7].value, members)
    for end in members:
        end.contents[7].value = element


def merge_safety_elements(project, document, operation):
    groups = _selected_elements(project, document, operation['element_ids'])
    need(len(groups) >= 2, 'Select at least two Safety Elements to group')
    element = groups[0][0]
    affected = {obj for obj, _ in groups[1:]}
    members = [member for _, subset in groups for member in subset]
    _set_element_members(element, members)
    collection = project.roots[document].contents[2]
    collection.value = path_functions.array_like(collection.value, [obj for obj in project.models[document]
                                                                     if obj not in affected])
    return {'preserved_element_id': model_id(element), 'retired_element_ids': sorted(map(model_id, affected)),
            'end_ids': sorted(map(model_id, members))}


def reset_safety_element(project, document, operation):
    (element, members), = _selected_elements(project, document, [operation['element_id']])
    membership = set(members)
    remaining = membership.copy()
    components = []
    for end in sorted(members, key=model_id):
        if end not in remaining:
            continue
        remaining.remove(end)
        component = [end]
        for member in component:
            for slot in (9, 10):
                edge = member.contents[slot].value
                if edge is None:
                    continue
                first, last = (edge.contents[i].value for i in (7, 8))
                other = last if first is member else first
                need(other in membership, 'An Edge crosses the Safety Element that would be reset')
                if other in remaining:
                    remaining.remove(other)
                    component.append(other)
        components.append(component)
    need(len(components) > 1, 'Safety Element already represents a single physical half-End component')
    high = max(project.byid[document])
    need(high + len(components) - 1 < 2147483647, 'Graphic ID exhausted')
    new_elements = []
    for index, subset in enumerate(components):
        group = element if index == 0 else path_functions.clone(element)
        if index:
            group.contents[0].value = high + index
            new_elements.append(group)
        _set_element_members(group, sorted(subset, key=model_id))
    collection = project.roots[document].contents[2]
    collection.value = path_functions.array_like(collection.value, [*project.models[document], *new_elements])
    return {'preserved_element_id': model_id(element), 'new_element_ids': list(map(model_id, new_elements)),
            'end_groups': [sorted(map(model_id, component)) for component in components]}


def _movement_geometry(project, sequence, check_safety):
    result = []
    for a, b in zip(sequence, sequence[1:]):
        travel_from = project.actual_related(a)
        edge = project.model(project.edge_between(a, b))
        along = edge.contents[7].value is project.model(travel_from)
        metric = edge.contents[9].values
        speeds = course_factories.dictionary(edge.contents[16].value)
        profile = (
            metric[0], metric[2], metric[3] if along else -metric[3], metric[4], metric[5],
            tuple(edge.contents[10].values), edge.contents[11].value,
            tuple((name, row.contents[1 if along else 2].value) for name, row in sorted(speeds.items())),
            project.key(edge.contents[7].value.contents[7].value) if check_safety else None,
        )
        if result and result[-1][0] == profile:
            _, previous = result.pop()
            result.append((profile, previous + metric[1]))
        else:
            result.append((profile, metric[1]))
    return result


def _movement_manifest(project, inserted=(), *, check_safety=True):
    omitted = set(inserted)
    manifest = {}

    def add(key, nodes, refs=None):
        geometry = _movement_geometry(project, nodes, check_safety)
        manifest[key] = ([node for node in nodes if node not in omitted], refs, geometry)

    for route in project.routes:
        owner = project.owners[id(route)]
        if writer.kind(project.model(owner)) == 'OTEndModel':
            add(('route', owner, ident(route)), project.route_view(route))
    for path in project.paths_objects:
        owner = project.owners[id(path)]
        nodes, refs = project.path_view(path)
        add(('path', owner, ident(path)), nodes, refs)
    for dest in project.dests:
        nodes, refs = project.dest_view(dest)
        add(('itinerary', project.owners[id(dest)], ident(dest)), nodes, refs)
    for owner, name in project.shunting_movements:
        add(('shunting', owner, name), project.shunting_movements[owner, name])
    return manifest


def transform(documents, document_paths, dest, document, operation, shapes=None, drawing_donor=None, courses=None,
              run_bytes=None, platform_inputs=None):
    from . import (saved_cross_document_reroute, saved_drawing_decoration, saved_kilometration_lengths,
                   saved_track_replacement, saved_track_reroute, saved_track_topology, saved_used_edge_profile)

    action = operation['action']
    if action == 'relocate_cross_document_measuring_instrument':
        from .saved_interdocument_instrument import relocate_cross_document_measuring_instrument
        return relocate_cross_document_measuring_instrument(documents, document_paths, dest, document, operation)
    if action == 'reroute_junction_track_spans':
        if operation.get('local_alignments'):
            from .saved_mixed_junction_reroute import reroute_mixed_junction_track_spans
            return reroute_mixed_junction_track_spans(documents, document_paths, dest, document, operation)
        from .saved_junction_reroute import reroute_junction_track_spans
        return reroute_junction_track_spans(documents, document_paths, dest, document, operation)
    if action == 'reroute_local_junction_track_spans':
        from .saved_local_junction_reroute import reroute_local_junction_track_spans
        return reroute_local_junction_track_spans(documents, document_paths, dest, document, operation)
    if action == 'reroute_multi_document_track_span':
        from .saved_multi_document_reroute import reroute_multi_document_track_span
        return reroute_multi_document_track_span(documents, document_paths, dest, document, operation)
    if action == 'insert_operational_document_span':
        from .saved_document_insertion import insert_document_span
        return insert_document_span(documents, document_paths, dest, document, operation, courses, run_bytes,
                                    operating_banks=platform_inputs)
    if action == 'bind_cross_document_terminal_overlap':
        from .saved_terminal_overlap import bind_cross_document_terminal_overlap
        return bind_cross_document_terminal_overlap(documents, document_paths, dest, document, operation, courses)
    if action == 'set_edge_exclusion':
        from .saved_edge_exclusion import set_edge_exclusion
        return set_edge_exclusion(documents, document_paths, dest, document, operation)
    if action == 'relocate_station_halt_signal':
        from .saved_halt_location import relocate_station_halt_signal
        review = {} if platform_inputs is None else {'platform_inputs': platform_inputs, 'run_bytes': run_bytes}
        return relocate_station_halt_signal(documents, document_paths, dest, document, operation, **review)
    if action == 'create_station_halt_signals':
        from .saved_halt_creation import create_station_halt_signals
        return create_station_halt_signals(documents, document_paths, dest, document, operation, shapes,
                                           platform_inputs=platform_inputs, run_bytes=run_bytes)
    if action == 'create_terminal_station_halt_signals':
        from .saved_terminal_halts import create_terminal_station_halt_signals
        return create_terminal_station_halt_signals(documents, document_paths, dest, document, operation, shapes)
    if action == 'relocate_terminal_station_halt_signal':
        from .saved_terminal_halts import relocate_terminal_station_halt_signal
        return relocate_terminal_station_halt_signal(documents, document_paths, dest, document, operation,
                                                    platform_inputs=platform_inputs, run_bytes=run_bytes)
    if action == 'create_cross_document_station_halt_signals':
        from .saved_cross_platform_halts import create_cross_document_station_halt_signals
        return create_cross_document_station_halt_signals(documents, document_paths, dest, document, operation, shapes)
    if action == 'relocate_cross_document_station_halt_signal':
        from .saved_cross_platform_halts import relocate_cross_document_station_halt_signal
        review = {} if platform_inputs is None else {'platform_inputs': platform_inputs, 'run_bytes': run_bytes}
        return relocate_cross_document_station_halt_signal(documents, document_paths, dest, document, operation, courses, **review)
    if action == 'replace_used_platform_edge':
        from .saved_platform_replacement import replace_used_platform_edge
        return replace_used_platform_edge(documents, document_paths, dest, document, operation, shapes)
    if action == 'replace_used_station_track_set':
        from .saved_station_track_set import replace_used_station_track_set
        return replace_used_station_track_set(documents, document_paths, dest, document, operation, shapes)
    if action in ('resize_used_platform_span', 'resize_used_terminal_platform_span',
                  'resize_used_cross_document_platform_span', 'resize_used_platforms'):
        from .saved_platform_resize import resize_used_platform_span
        return resize_used_platform_span(documents, document_paths, dest, document, operation, platform_inputs, run_bytes)
    if action == 'relocate_main_signal':
        from .saved_main_signal_location import relocate_main_signal
        return relocate_main_signal(documents, document_paths, dest, document, operation, courses)
    if action == 'create_main_signal':
        if operation.get('halt_relocation') is not None:
            from .saved_signal_halt_transaction import insert_signal_and_relocate_halt

            return insert_signal_and_relocate_halt(documents, document_paths, dest, document, operation, courses,
                                                   operating_banks=platform_inputs, run_bytes=run_bytes)
        if operation.get('split_route') is not None:
            from .saved_main_signal_split import insert_signal_in_saved_route

            return insert_signal_in_saved_route(documents, document_paths, dest, document, operation, courses,
                                                operating_banks=platform_inputs, run_bytes=run_bytes)
        from .saved_main_signal_create import create_saved_main_signal
        return create_saved_main_signal(documents, document_paths, dest, document, operation, courses)

    project = project_from(documents, document_paths, dest)
    check_safety = (action not in ('merge_safety_elements', 'reset_safety_element')
                    and not operation.get('allow_safety_regroup', False))
    before = _movement_manifest(project, check_safety=check_safety)
    expected = before
    affected = {document}
    if action == 'set_signal_sight':
        sighting_before = writer.fingerprint(project.roots[document])
    edits = {'move_vertex': move_vertex, 'reverse_edge': reverse_edge,
             'set_vertex_details': set_vertex_details,
             'set_signal_sight': set_signal_sight,
             'merge_safety_elements': merge_safety_elements, 'reset_safety_element': reset_safety_element,
             'rotate_vertex': saved_track_topology.rotate_vertex,
             'delete_edge': saved_track_topology.delete_edge, 'delete_vertex': saved_track_topology.delete_vertex,
             'rechain_edge': saved_track_topology.rechain_edge,
             'edit_decoration': saved_drawing_decoration.edit_decoration}
    donor_edits = {'split_edge': split_edge, 'split_platform_edge': split_edge,
                   'split_cross_document_platform_edge': split_edge,
                   'insert_vertex': saved_track_topology.insert_vertex,
                   'insert_edge': saved_track_topology.insert_edge}
    if action in donor_edits:
        report = donor_edits[action](project, document, operation, shapes)
    elif action == 'import_decoration':
        report = saved_drawing_decoration.import_decoration(project, document, operation, drawing_donor)
    elif action == 'replace_connectors':
        affected, report = replace_connectors(project, operation)
        need(document in affected, 'The target document must participate in the connector edit')
    elif action == 'calculate_kilometre_points':
        affected, report = calculate_kilometre_points(project, operation)
        need(document in affected, 'The target document must have a calculated kilometre point change')
    elif action == 'edit_station_area':
        active = {node for sequence, _, _ in before.values() for node in sequence}
        if operation['remove_end_ids']:
            active.update(project.related(key) for key in tuple(active))
        report = saved_station_areas.edit_members(project, document, operation, active)
    elif action == 'convert_station_reference':
        reference_before = writer.fingerprint(project.roots[document])
        report = saved_station_areas.convert_reference(project, document, operation)
    elif action == 'cut_double_vertex':
        active_departures = {node for sequence, _, _ in before.values() for node in sequence[:-1]}
        report = saved_track_topology.cut_double_vertex(project, document, operation, shapes, active_departures)
    elif action == 'replace_used_edge':
        report, expected, protection_before = saved_track_replacement.replace_used_edge(
            project, document, operation, before)
    elif action == 'edit_used_edge_profile':
        affected, report, expected, protection_before = saved_used_edge_profile.edit_used_edge_profile(
            project, document, operation, before)
    elif action == 'calculate_edge_lengths_from_kilometration':
        affected, report, expected, protection_before = saved_kilometration_lengths.calculate_edge_lengths(
            project, document, operation, before)
    elif action == 'reroute_used_track_span':
        affected, report, expected, protection_before, instrument_review = saved_track_reroute.reroute_used_track_span(
            project, document, operation, before)
    elif action == 'reroute_cross_document_track_span':
        result = saved_cross_document_reroute.reroute_cross_document_track_span(
            project, document, operation, before)
        affected, report, expected, protection_before, instrument_review = result
    else:
        report = edits[action](project, document, operation)
    output = {name: writer.dump_verified(project.roots[name], project.versions[name]) for name in sorted(affected)}
    checked = project_from({**documents, **output}, document_paths, dest)
    inserted = [(document, ident) for ident in report.get('new_end_ids', ())]
    need(_movement_manifest(checked, inserted, check_safety=check_safety) == expected,
         'A Route, Path, Itinerary or Shunting changed movement references, distance, directional physics or unrelated safety groups')
    if action in ('move_vertex', 'rotate_vertex') and report['instruments']:
        reviewed = [row['after'] for row in report['instruments']]
        owners = [checked.model((document, row['end_id'])) for row in reviewed]
        attached = attached_measuring_instruments(checked, document, owners)
        need([instrument_graphics(end, instrument) for end, instrument in attached] == reviewed,
             'Measuring instrument geometry or binding changed after native readback')
        report['instrument_graphics_verified'] = True
    if action == 'replace_connectors':
        for a, b in report['added_pairs']:
            need(checked.block_end(a) == b and checked.block_end(b) == a, 'Connector writeback failed')
    if action in ('split_platform_edge', 'edit_station_area'):
        saved_station_areas.verify_members(checked, document, report)
    if action == 'split_cross_document_platform_edge':
        _verify_cross_platform_split(checked, document, operation, report)
    if action == 'convert_station_reference':
        saved_station_areas.verify_reference(checked, document, report, reference_before)
        report['nonselected_graph_verified'] = True
    if action == 'set_signal_sight':
        _verify_signal_sight(checked, document, report, sighting_before)
        report['nonselected_graph_verified'] = True
    if action == 'cut_double_vertex':
        saved_track_topology.verify_cut(checked, document, report)
    if action in ('edit_decoration', 'import_decoration') and 'drawing_style_after' in report:
        saved_drawing_decoration.verify_style(checked, document, report)
    if action == 'replace_used_edge':
        saved_track_replacement.verify_replacement(checked, document, report, protection_before)
    if action == 'edit_used_edge_profile':
        saved_used_edge_profile.verify_used_edge_profile(checked, document, report, protection_before)
    if action == 'calculate_edge_lengths_from_kilometration':
        saved_kilometration_lengths.verify_calculated_lengths(checked, document, report, protection_before)
    if action == 'reroute_used_track_span':
        saved_track_reroute.verify_reroute(checked, document, report, protection_before, instrument_review)
    if action == 'reroute_cross_document_track_span':
        saved_cross_document_reroute.verify_cross_document_reroute(checked, report, protection_before, instrument_review)
    return output, {
        'action': action, 'document': document, 'changed_documents': sorted(affected), **report,
        'movement_count_checked': len(before), 'destination_catalog_unchanged': True,
        'safety_regrouped': not check_safety, 'native_execution_tested': False,
    }
