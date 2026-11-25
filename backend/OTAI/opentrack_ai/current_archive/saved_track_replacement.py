"""Retire a used native Edge while preserving reviewed equivalent movement profiles."""

from . import path_functions, writer
from .multi_document.core import ident, need
from .route_edit_tools import _protection_values, _route_shape, _zone_fragment_ids
from .saved_geometry import _edge, _end_shape, _insert_movement_nodes, _movement_items, _speed_table, model_id
from .saved_track_topology import _detach_edge_endpoints, _replace_models


def _edge_labels(edge):
    return tuple(None if edge.contents[slot].value is None else path_functions.string(edge.contents[slot].value)
                 for slot in (19, 20))


def _selected_chain(project, first, last, replacement):
    cursor = first
    interior = []
    vertices = {model_id(first), first.contents[8].value, model_id(last), last.contents[8].value}
    for index, edge in enumerate(replacement):
        a, b = (edge.contents[slot].value for slot in (7, 8))
        need(cursor in (a, b), 'The replacement Edges are disconnected or in the wrong order')
        arrived = b if a is cursor else a
        if index == len(replacement) - 1:
            need(arrived is last, 'The replacement chain must rejoin the exact original directional End')
            continue
        cursor = project.model(project.related(project.key(arrived)))
        for obj in (arrived, cursor):
            _end_shape(obj)
            need(writer.kind(obj) == 'OTEndModel' and obj.contents[20].value == 1
                 and all(obj.contents[slot].value is None for slot in (6, 11, 12, 13)),
                 'Replacement interior must be ordinary track without signals, stations or instruments')
            need(obj.contents[9].value is not None and obj.contents[10].value is None,
                 'An extra switch branch in the replacement interior changes its operating profile')
            need(model_id(obj) not in vertices, 'The replacement must visit each interior double vertex once')
            vertices.add(model_id(obj))
        interior.append(arrived)
    return interior


def _protection_manifest(project, document):
    details = {}
    for owner, movement in _movement_items(project):
        if owner[0] != document:
            continue
        kind = writer.kind(movement)
        key = owner, kind, ident(movement)
        details[key] = {
            'timing_distance_flags': (*movement.contents[5].values[:4], movement.contents[5].values[5]),
            'occupied_entry': tuple(movement.contents[6].values),
            'overlap': (path_functions.string(movement.contents[7].value), movement.contents[9].value),
            'approach_thresholds': tuple(movement.contents[8].values),
        }
        if movement.clazz.superclass.version == 6:
            details[key]['reservation_and_release_distance_flags'] = tuple(movement.contents[10].values)
        if kind == 'OTRoute':
            flags = _route_shape(movement)
            details[key]['route_flags'] = movement.contents[flags].value
            details[key].update(_protection_values(movement, flags))
            details[key]['slow_speed_zone_fragment_end_ids'] = _zone_fragment_ids(movement, flags)
        else:
            details[key]['shunting_speed'] = movement.contents[11].value
    return details


def replace_used_edge(project, document, operation, before):
    old = _edge(project, document, operation)
    replacement_ids = operation['replacement_edge_ids']
    need(len(replacement_ids) >= 2 and len(set(replacement_ids)) == len(replacement_ids)
         and model_id(old) not in replacement_ids, 'Choose at least two distinct replacement Edges')
    replacement = [_edge(project, document, {'edge_id': ident}) for ident in replacement_ids]
    first, last = (old.contents[slot].value for slot in (7, 8))
    need(first.contents[12].value is None or first.contents[12].value is not last.contents[12].value,
         'Replacing a track inside a station area requires a separate stop-area contract')
    for end in (first, last):
        _end_shape(end)
        need(writer.kind(end) == 'OTEndModel', 'The old track requires two ordinary local directional Ends')
    for edge in (old, *replacement):
        _speed_table(edge)
        need(_edge_labels(edge) == _edge_labels(old), 'Replacement track and line names must match the original')
    inserts = {(first, last): _selected_chain(project, first, last, replacement),
               (last, first): _selected_chain(project, last, first, list(reversed(replacement)))}
    keys = {(project.key(a), project.key(b)): [project.key(end) for end in nodes]
            for (a, b), nodes in inserts.items()}
    expected = {}
    changed = []
    for identity, (sequence, refs, geometry) in before.items():
        new_seq = []
        for a, b in zip(sequence, sequence[1:]):
            new_seq.append(a)
            new_seq.extend(keys.get((project.actual_related(a), b), ()))
        new_seq.append(sequence[-1])
        expected[identity] = new_seq, refs, geometry
        if new_seq != sequence:
            changed.append({'kind': identity[0], 'owner': identity[1], 'identity': identity[2]})
    need(changed, 'This Edge has no active saved Route, Path, Itinerary or Shunting to reroute')
    protection_before = _protection_manifest(project, document)
    updated = _insert_movement_nodes(project, document, lambda a, b: inserts.get((a, b), ()), unique_arrays=True)
    need(updated, 'The identified saved movements could not be rebound in this document')
    # The initial Project caches Route traversal. The caller validates all rewritten
    # movements against the expected replacement on a newly decoded graph.
    _detach_edge_endpoints(old)
    _replace_models(project, document, [obj for obj in project.models[document] if obj is not old])
    report = {'retired_edge_id': model_id(old), 'replacement_edge_ids': replacement_ids,
              'former_end_ids': [model_id(first), model_id(last)],
              'replacement_via_end_ids': [model_id(end) for end in inserts[first, last]],
              'length_m': old.contents[9].values[1], 'rewritten_movements': updated,
              'affected_movement_identities': changed}
    return report, expected, protection_before


def verify_replacement(project, document, report, protection_before):
    need(report['retired_edge_id'] not in project.byid[document], 'Retired Edge survived the native readback')
    need(all(edge in project.byid[document] for edge in report['replacement_edge_ids']),
         'A selected replacement Edge is absent after native readback')
    need(_protection_manifest(project, document) == protection_before,
         'Signal indications, release groups, occupied entry or Shunting settings changed during replacement')
    report['signal_and_release_settings_preserved'] = True
