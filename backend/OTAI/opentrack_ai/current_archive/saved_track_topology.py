"""Expand a verified existing worksheet without replacing its native graph."""

import math

from . import path_functions, route_factory, writer
from .graph_references import reference_inventory
from .multi_document.core import need
from .saved_geometry import (_edge, _end_shape, _movement_items, _selected_elements, _set_element_members,
                             attached_measuring_instruments, instrument_graphics, model_id, position, selected,
                             translate_end_graphics)
from .station_operations import _snapshot
from .zero_generation import topology


def _replace_models(project, document, models):
    field = project.roots[document].contents[2]
    field.value = path_functions.array_like(field.value, models)


def _builder(project, document, shapes):
    builder = topology.Builder(shapes)
    need(builder.stream_version == project.versions[document], 'Worksheet and shape stream versions differ')
    existing_classes = {obj.clazz.name: topology.signature(obj.clazz) for obj in writer.objects(project.roots[document])}
    for sample in builder.protos.values():
        need(existing_classes.get(sample.clazz.name, topology.signature(sample.clazz)) == topology.signature(sample.clazz),
             'Shape class version conflicts with a class already in the worksheet')
    builder.high = max(project.byid[document], default=-1)
    return builder


def insert_vertex(project, document, operation, shapes):
    builder = _builder(project, document, shapes)
    ends = builder.vertex({
        'x': operation['x'], 'y': operation['y'], 'orientation': operation['orientation'],
        'names': operation['names'], 'insulated_joint': [False, False], 'axle_counter': [False, False],
    })
    _replace_models(project, document, [*project.models[document], *builder.models])
    return {'added_vertex_end_ids': list(map(model_id, ends)),
            'safety_element_ids': [model_id(end.contents[7].value) for end in ends]}


def _track_ends(project, document, end_ids, ignored_edge=None):
    first, last = [selected(project, document, ident, 'OTEndModel') for ident in end_ids]
    need(first is not last and first.contents[8].value != model_id(last),
         'Choose Ends from two distinct paired vertices')
    need(position(first) != position(last), 'Choose different graphic coordinates for the two Ends')
    for end, opposite in ((first, last), (last, first)):
        need(end.contents[13].value is None, 'An attached instrument observes the changed vertex')
        edges = [end.contents[slot].value for slot in (9, 10)
                 if end.contents[slot].value not in (None, ignored_edge)]
        need(len(edges) < 2, 'No additional track slot remains on this half-vertex')
        need(all(opposite not in [edge.contents[slot].value for slot in (7, 8)] for edge in edges),
             'A track already directly connects the selected two Ends')
    return first, last


def _isolate_groups(project, document, first, last, *, allow_regroup):
    groups = list(dict.fromkeys((first.contents[7].value, last.contents[7].value)))
    if len(groups) == 1:
        return groups
    for element, members in _selected_elements(project, document, list(map(model_id, groups))):
        need(allow_regroup or element is groups[0] or len(members) == 1,
             'Joining an existing Safety Element requires explicit allow_safety_regroup')
        _set_element_members(element, members)
    return groups


def insert_edge(project, document, operation, shapes):
    first, last = _track_ends(project, document, operation['end_ids'])
    _isolate_groups(project, document, first, last, allow_regroup=operation['allow_safety_regroup'])
    builder = _builder(project, document, shapes)
    builder.models = list(project.models[document])
    speeds = operation['speeds']
    keys = [row['train_type'] for row in speeds]
    need(len(keys) == len(set(keys)), 'Directional speed keys must be unique')
    edge = builder.edge({
        'track_type': 1, 'loop_type': 1, 'dlink_type': 1, 'length_m': operation['length_m'],
        'radius_m': operation['radius_m'], 'gradient_per_mille': operation['gradient_per_mille'],
        'equal_speed': all(item['speed12_kmh'] == item['speed21_kmh'] for item in speeds),
        'rack_rail': operation['rack_rail'], 'remark': operation['remark'], 'track_name': operation['track_name'],
        'line_name': operation['line_name'], 'speeds': speeds,
    }, first, last)
    _replace_models(project, document, builder.models)
    return {'edge_id': model_id(edge), 'end_ids': operation['end_ids'], 'length_m': operation['length_m'],
            'safety_element_id': model_id(first.contents[7].value)}


def _movement_dependencies(project, document, edge):
    edge_key = (document, model_id(edge))
    for owner, movement in _movement_items(project):
        nodes = [project.key(obj) for obj in path_functions.mutable_array(movement.contents[0].value)]
        # A continuation starts at the ordinary saved End after its owning
        # connector. Its primary Route's expanded chain covers that first leg.
        if writer.kind(movement) == 'OTRoute' and writer.kind(project.model(owner)) == 'OTEndModel':
            nodes = project.route_view(movement)
        if any(project.edge_between(a, b) == edge_key for a, b in zip(nodes, nodes[1:])):
            path = path_functions.string(movement.contents[1].value)
            raise ValueError(f"Track is used by saved movement '{path}'")


def _detach_edge_endpoints(edge, *, reviewed_instrument_ends=()):
    first, last = (edge.contents[slot].value for slot in (7, 8))
    need(first.contents[12].value is None or first.contents[12].value is not last.contents[12].value,
         'A station-area Edge requires an explicit station area edit')
    for end in (first, last):
        instrument = end.contents[13].value
        if instrument is not None:
            need(end in reviewed_instrument_ends and writer.kind(instrument) == 'OTMeasuringModel'
                 and instrument.contents[7].value is end
                 and edge not in path_functions.mutable_array(instrument.contents[12].value)
                 and any(writer.kind(end.contents[slot].value) == 'OTEdgeModel'
                         and end.contents[slot].value is not edge for slot in (9, 10)),
                 'Track endpoints carry measuring instruments')
    for end in (first, last):
        other = [end.contents[slot].value for slot in (9, 10) if end.contents[slot].value is not edge]
        end.contents[9].value, end.contents[10].value = other[0], None
        # With one leg left the former 'choose branch two' flag would point at
        # nothing. Retain the rest of the End's feature settings.
        end.contents[22].value = 0
    return edge, first, last


def _detach_edge(project, document, operation):
    edge = _edge(project, document, operation)
    _movement_dependencies(project, document, edge)
    return _detach_edge_endpoints(edge)


def delete_edge(project, document, operation):
    edge, first, last = _detach_edge(project, document, operation)
    _replace_models(project, document, [obj for obj in project.models[document] if obj is not edge])
    return {'removed_edge_id': model_id(edge), 'former_end_ids': [model_id(first), model_id(last)],
            'previous_safety_groups_kept': True}


def rechain_edge(project, document, operation):
    edge = _edge(project, document, operation)
    first, last = _track_ends(project, document, operation['end_ids'], ignored_edge=edge)
    need({obj.contents[0].value for obj in (first, last)}
         != {edge.contents[slot].value.contents[0].value for slot in (7, 8)},
         'Use the reversal action to change storage direction without changing the two Ends')
    old_defaults = {end: end.contents[10 if end.contents[22].value else 9].value for end in (first, last)}
    edge, previous_first, previous_last = _detach_edge(project, document, operation)
    groups = _isolate_groups(project, document, first, last, allow_regroup=operation['allow_safety_regroup'])
    edge.contents[7].value, edge.contents[8].value = first, last
    for end in (first, last):
        slot = 9 if end.contents[9].value is None else 10
        end.contents[slot].value = edge
        end.contents[22].value = int(end.contents[10].value is not None
                                     and end.contents[10].value is old_defaults[end])
    if len(groups) == 2:
        first_group, retired = groups
        _set_element_members(first_group, [*path_functions.mutable_array(first_group.contents[7].value),
                                           *path_functions.mutable_array(retired.contents[7].value)])
        _replace_models(project, document, [obj for obj in project.models[document] if obj is not retired])
    return {'edge_id': model_id(edge), 'former_end_ids': [model_id(previous_first), model_id(previous_last)],
            'end_ids': operation['end_ids'], 'length_m': edge.contents[9].values[1]}


def _delete_isolated_vertices(project, document, end_ids):
    ends = set()
    for end_id in end_ids:
        first = selected(project, document, end_id, 'OTEndModel')
        second = selected(project, *project.related(project.key(first)), 'OTEndModel')
        need(first not in ends and second not in ends, 'Select each isolated paired vertex only once')
        ends.update((first, second))
    counts = reference_inventory(project.roots[document])[1]
    for end in ends:
        need(counts[id(end)] == 2
             and all(end.contents[slot].value is None for slot in (6, 9, 10, 11, 12, 13)),
             'The selected vertex still has track, metadata, an instrument or another graph observer')
        need(all(not route_factory.wrapper(end.contents[slot].value, name) for slot, name
                 in ((15, 'OTRouteList'), (16, 'OTShuntingList'), (17, 'OTPathList'))),
             'The selected vertex owns saved movement definitions')
    groups = list(dict.fromkeys(end.contents[7].value for end in sorted(ends, key=model_id)))
    retired = set(ends)
    for group, members in _selected_elements(project, document, list(map(model_id, groups))):
        live = [end for end in members if end not in ends]
        if live:
            _set_element_members(group, live)
        else:
            retired.add(group)
    live_models = path_functions.mutable_array(project.roots[document].contents[2].value)
    _replace_models(project, document, [obj for obj in live_models if obj not in retired])
    return {'removed_end_ids': sorted(map(model_id, ends)),
            'removed_safety_element_ids': sorted(model_id(obj) for obj in retired - ends)}


def delete_vertex(project, document, operation):
    first = operation['end_id']
    report = _delete_isolated_vertices(project, document, [first])
    report['removed_end_ids'] = [first, project.related((document, first))[1]]
    return report


def _alignment(end):
    return tuple(end.contents[slot].value for slot in (4, 5))


def _cut_attachments(end):
    return {
        'end_id': model_id(end),
        'edge_ids': [model_id(end.contents[i].value) for i in (9, 10) if end.contents[i].value is not None],
        'signal_id': None if end.contents[11].value is None else model_id(end.contents[11].value),
        'safety_element_id': model_id(end.contents[7].value),
    }


def cut_double_vertex(project, document, operation, shapes, active_departures):
    first = selected(project, document, operation['end_id'], 'OTEndModel')
    second = selected(project, *project.related(project.key(first)), 'OTEndModel')
    for end in (first, second):
        _end_shape(end)
        need(end.contents[20].value == 1 and end.contents[12].value is None,
             'A station vertex or area member requires its own cut contract')
        need(all(end.contents[slot].value is None for slot in (6, 13)),
             'A measured vertex or one with graphic attachments requires its own cut contract')
        need(project.key(end) not in active_departures,
             'A saved movement depends on passage through this double vertex')
    attachments = [_cut_attachments(end) for end in (first, second)]
    need(not set(attachments[0]['edge_ids']).intersection(attachments[1]['edge_ids']),
         'The existing halves already share a physical track Edge')

    origin = position(first)
    need(origin == position(second) and all(map(math.isfinite, origin)), 'Different paired coordinates')
    target = [topology.flt(operation[axis], axis) for axis in ('second_x', 'second_y')]
    need(all(target != position(end) for end in project.models[document]
             if writer.kind(end) in ('OTEndModel', 'OTConnModel')),
         'Choose an unoccupied position for the separated pair')
    alignments = {_alignment(first), _alignment(second)}
    horizontal = {(1, 0), (2, 0)}
    need(alignments in (horizontal, {(0, 3), (0, 4)}), 'Choose a reciprocal horizontal or vertical double vertex')

    builder = _builder(project, document, shapes)
    new_ends = builder.vertex({'x': origin[0], 'y': origin[1],
        'orientation': 'horizontal' if alignments == horizontal else 'vertical',
        'names': ['', ''], 'insulated_joint': [False, False], 'axle_counter': [False, False]})
    by_alignment = {_alignment(end): end for end in new_ends}
    new_first, new_second = by_alignment[_alignment(second)], by_alignment[_alignment(first)]
    for old, new in ((first, new_first), (second, new_second)):
        old.contents[8].value = model_id(new)
        new.contents[8].value = model_id(old)
    _, marker = translate_end_graphics(second, origin, target)
    for slot, coord in zip((2, 3), target):
        new_second.contents[slot].value = coord
    _replace_models(project, document, [*project.models[document], *builder.models])
    return {
        'former_end_ids': [model_id(first), model_id(second)],
        'separated_pairs': [[model_id(first), model_id(new_first)], [model_id(second), model_id(new_second)]],
        'pair_positions': [origin, target],
        'preserved_attachments': attachments,
        'moved_signal': marker,
    }


def verify_cut(project, document, report):
    for pair, coordinate, attachments in zip(report['separated_pairs'], report['pair_positions'],
                                             report['preserved_attachments'], strict=True):
        kept, cap = (project.model((document, end_id)) for end_id in pair)
        need(project.related((document, pair[0])) == (document, pair[1])
             and project.related((document, pair[1])) == (document, pair[0])
             and position(kept) == position(cap) == coordinate,
             'Separated vertex pair did not survive native readback')
        need(_cut_attachments(kept) == attachments and all(cap.contents[i].value is None for i in (9, 10, 11)),
             'The cut moved an attachment or introduced a bridging leg')
    report['no_connecting_edge_created'] = True


def rotate_vertex(project, document, operation):
    first = selected(project, document, operation['end_id'], 'OTEndModel', 'OTConnModel')
    second = project.model(project.related(project.key(first)))
    pivot = position(first)
    need(pivot == position(second) and all(map(math.isfinite, pivot)), 'Different paired coordinates')
    delta = operation['delta_degrees']
    need(delta in (-90, 90), 'Original End rotation uses one quarter-turn')
    # Original OTEndView rotateGraphic:draw: stores orientation in loc.align,
    # and OTSignalView handleRotate: uses the owner's resulting alignment.
    ccw = {(1, 0): (0, 3), (2, 0): (0, 4), (0, 3): (2, 0), (0, 4): (1, 0)}
    orientation = ccw if delta == 90 else {new: old for old, new in ccw.items()}
    root = project.roots[document]
    before = _snapshot(root)
    allowed = set()
    affected = []
    # Stock OTMeasuringView inherits the no-op graphic rotation. Its display
    # frame and model placement are independent of the rotated End alignment.
    instruments = [instrument_graphics(end, instrument) for end, instrument in
                   attached_measuring_instruments(project, document, (first, second))]
    for end in (first, second):
        attached = end.contents[11].value
        alignment = tuple(end.contents[slot].value for slot in (4, 5))
        need(alignment in orientation, 'End orientation lies outside the reviewed native quarter-turn domain')
        target_alignment = orientation[alignment]
        for obj in (end, attached):
            if obj is None:
                continue
            need(tuple(obj.contents[slot].value for slot in (4, 5)) == alignment,
                 'Signal orientation disagrees with its owning End')
            for slot, coord in zip((4, 5), target_alignment):
                obj.contents[slot].value = coord
                allowed.add((id(obj), slot, 0))
            if obj is attached:
                x, y = (p - q for p, q in zip(position(obj), pivot))
                sign = delta // 90
                target = [pivot[0] - y * sign, pivot[1] + x * sign]
                for slot, coord in zip((2, 3), target):
                    value = topology.flt(coord, 'Rotated signal coordinate')
                    need(math.isclose(float(value), coord, rel_tol=0.0, abs_tol=0.0001),
                         'Signal rotation loses its offset at these stored coordinates')
                    obj.contents[slot].value = value
                    allowed.add((id(obj), slot, 0))
            affected.append({'model_id': model_id(obj), 'xy': position(obj),
                             'before_alignment': alignment, 'after_alignment': target_alignment})
    after = _snapshot(root)
    need(before.keys() == after.keys() and all(after[key] == value for key, value in before.items() if key not in allowed),
         'Rotation changed unrelated native fields')
    return {'pivot_xy': pivot, 'delta_degrees': delta, 'objects': affected,
            'instruments': [{'before': row, 'after': row} for row in instruments]}
