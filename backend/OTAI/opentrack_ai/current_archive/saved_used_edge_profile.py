"""Change the operating profile of a used native track without changing its Ends."""

import math

from . import path_functions
from .graph_references import reference_inventory
from .itinerary_edit_tools import _float32, _margin_members, _margin_values
from .multi_document.core import ident, need
from .saved_geometry import _edge, _movement_manifest, _speed_table, model_id
from .saved_track_replacement import _protection_manifest
from .zero_generation import topology


def _profile(edge):
    metric = edge.contents[9].values
    return {
        'length_m': metric[1], 'radius_m': float(metric[2]), 'gradient_per_mille': float(metric[3]),
        'storage_end_ids': [model_id(edge.contents[slot].value) for slot in (7, 8)],
        'equal_directional_speed_flag': bool(edge.contents[11].value & 1),
        'speeds_kmh': {key: [row.contents[1].value, row.contents[2].value]
                       for key, row in _speed_table(edge).items()},
    }


def _selected_spans(project, sequence, edge_key):
    distance = 0
    spans = []
    for start, stop in zip(sequence, sequence[1:]):
        traversed = project.edge_between(start, stop)
        length = project.model(traversed).contents[9].values[1]
        if traversed == edge_key:
            spans.append((distance, distance + length))
        distance += length
    return distance, spans


def _mapped_position(position, spans):
    shift = 0
    for start, stop, new_length in spans:
        if position <= start:
            break
        if position < stop:
            return _float32(start + shift + (position - start) * new_length / (stop - start))
        shift += new_length - (stop - start)
    return _float32(position + shift)


def _map_margin_profiles(project, traversals, new_length, authorized):
    revised = {identity: (total, [(start, stop, new_length) for start, stop in spans])
               for identity, (total, spans) in traversals.items()}
    return map_margin_span_profiles(project, revised, authorized)


def map_margin_span_profiles(project, traversals, authorized):
    reports = []
    for definition in project.dests:
        owner = project.owners[id(definition)]
        identity = ('itinerary', owner, ident(definition))
        if identity not in traversals:
            continue
        wrapper, array, rows = _margin_members(definition)
        if not rows:
            continue
        total, spans = traversals[identity]
        before = _margin_values(rows)
        need(all(math.isfinite(row['position_m']) and math.isfinite(row['safety_margin_m']) for row in before),
             'An affected Itinerary has nonfinite safety-margin fields')
        if all(row['position_m'] <= spans[0][0] for row in before):
            continue
        need(authorized, 'Changing this distance requires explicit map_itinerary_safety_margins')
        positions = [row['position_m'] for row in before]
        need(all(0 <= value <= total for value in positions)
             and all(a <= b for a, b in zip(positions, positions[1:])),
             'Automatic safety-margin mapping requires sorted positions inside the original Itinerary')
        counts = reference_inventory(project.roots[owner[0]])[1]
        need(all(counts[id(obj)] == 1 for obj in (wrapper, array, *rows)),
             'An affected Itinerary shares safety-margin objects and needs separate review')
        mapped = [_mapped_position(value, spans) for value in positions]
        need(all(left == right or a < b for left, right, a, b
                 in zip(positions, positions[1:], mapped, mapped[1:])),
             'Float32 mapping would collapse distinct safety-margin positions')
        for row, value in zip(rows, mapped, strict=True):
            row.contents[0].values[0] = value
        reports.append({'document': owner[0], 'identity': identity[2], 'before': before, 'after': _margin_values(rows)})
    return reports


def _set_directional_speeds(edge, speeds, old):
    changes = {row['train_type']: (row['speed12_kmh'], row['speed21_kmh']) for row in speeds}
    need(len(changes) == len(speeds) and changes.keys() <= old.keys(),
         'Supply unique existing native train speed keys')
    need(all(a > 0 and b > 0 for a, b in changes.values()), 'Used track requires positive supplied directional speeds')
    if not changes:
        return
    table = path_functions.clone(edge.contents[16].value)
    for group in table.contents[2::2]:
        record = group.value
        key = path_functions.string(record.contents[0].value)
        if key in changes:
            selected = path_functions.clone(record)
            selected.contents[1].value, selected.contents[2].value = changes[key]
            group.value = selected
    edge.contents[16].value = table
    if any(row.contents[1].value != row.contents[2].value for row in _speed_table(edge).values()):
        edge.contents[11].value &= ~1


def edit_used_edge_profile(project, document, operation, before):
    edge = _edge(project, document, operation)
    old = _profile(edge)
    first, last = (edge.contents[slot].value for slot in (7, 8))
    need(first.contents[12].value is None or first.contents[12].value is not last.contents[12].value,
         'Editing an in-station berth requires a separate stopping-area contract')
    need(first.contents[13].value is None and last.contents[13].value is None,
         'An attached measurement instrument observes the edited track')
    requested_length = operation.get('length_m')
    length = old['length_m'] if requested_length is None else requested_length
    need(type(length) is int and 0 < length < 2147483647, 'Positive native track length is required')
    delta = length - old['length_m']
    traversals = {}
    for identity, (sequence, _, _) in before.items():
        total, spans = _selected_spans(project, sequence, (document, model_id(edge)))
        if spans:
            traversals[identity] = total, spans
    need(traversals, 'This Edge has no active saved Route, Path, Itinerary or Shunting')
    need(all(0 < total + len(spans) * delta <= 2147483647 for total, spans in traversals.values()),
         'Edited movement distance exceeds the native signed range')
    protection_documents = {document, *(identity[1][0] for identity in traversals)}
    protection = {name: _protection_manifest(project, name) for name in protection_documents}

    edge.contents[9].values[1] = length
    for name, slot in (('radius_m', 2), ('gradient_per_mille', 3)):
        value = operation.get(name)
        if value is not None:
            wire = topology.flt(value, name)
            need(name != 'radius_m' or wire >= 0, 'Radius must be nonnegative')
            edge.contents[9].values[slot] = wire
    _set_directional_speeds(edge, operation.get('speeds') or [], old['speeds_kmh'])
    new = _profile(edge)
    need(old != new, 'Track profile already has the requested saved values')
    margin_reports = []
    if delta:
        margin_reports = _map_margin_profiles(project, traversals, length,
                                             operation.get('map_itinerary_safety_margins') is True)
    affected_documents = {document, *(row['document'] for row in margin_reports)}
    expected = _movement_manifest(project)
    need(before.keys() == expected.keys(), 'Movement catalogue changed during track profile edit')
    movements = []
    for identity, (sequence, refs, geometry) in before.items():
        if identity not in traversals:
            need(expected[identity] == (sequence, refs, geometry), 'An unrelated movement changed profile')
            continue
        _, spans = traversals[identity]
        old_distance = sum(segment[1] for segment in geometry)
        new_sequence, new_refs, new_geometry = expected[identity]
        new_distance = sum(segment[1] for segment in new_geometry)
        need((sequence, refs) == (new_sequence, new_refs) and new_distance == old_distance + delta * len(spans),
             'Edited track did not propagate to the expected saved movement distance')
        movements.append({'kind': identity[0], 'owner': identity[1], 'identity': identity[2],
                          'before_distance_m': old_distance, 'after_distance_m': new_distance,
                          'edited_track_traversals': len(spans)})
    report = {'edge_id': model_id(edge), 'before': old, 'after': new, 'movements': movements,
              'mapped_safety_margin_profiles': margin_reports}
    return affected_documents, report, expected, protection


def verify_margin_profiles(project, profiles):
    for row in profiles:
        definition, = [dest for dest in project.dests if project.owners[id(dest)][0] == row['document']
                       and ident(dest) == row['identity']]
        need(_margin_values(_margin_members(definition)[2]) == row['after'],
             'Mapped safety-margin values differ after native readback')


def verify_used_edge_profile(project, document, report, protection):
    need(_profile(_edge(project, document, report)) == report['after'], 'Edited profile differs after native readback')
    for document_name, manifest in protection.items():
        need(_protection_manifest(project, document_name) == manifest, 'Saved signal or release settings changed')
    verify_margin_profiles(project, report['mapped_safety_margin_profiles'])
    report['signal_and_release_settings_preserved'] = True
