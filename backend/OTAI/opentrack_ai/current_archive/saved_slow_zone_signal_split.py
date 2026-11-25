"""Resolve finite native slow-speed zones before and after inserting a main Signal."""

from . import path_functions
from .multi_document.core import ident, need, ref
from .route_edit_tools import _protection_values, _route_shape
from .saved_document_insertion import _metric_zone_aspect, _stored_zone
from .signal_operating_fields import _append_indications, _indication_records


def raw_zone_pointers(project, section, document):
    return [project.model(key) if key is not None else None for key in section['raw_zone_anchors'][document]]


def _effective_zone(raw, movement):
    primary, receiving = movement[0][0], movement[-1][0]
    return tuple(remote if remote is not None else local for local, remote in
                 zip(raw[primary], raw[receiving], strict=True))


def _zone_interval(project, movement, bounds):
    if bounds == (None, None):
        return [], None
    start, finish = map(movement.index, bounds)
    edges = [project.edge_between(a, b) for a, b in zip(movement, movement[1:])]
    lengths = [project.model(edge).contents[9].values[1] for edge in edges[:finish]]
    return edges[start:finish], [sum(lengths[:start]), sum(lengths)]


def _section(project, movement, interval, source_raw, head_only, code):
    primary, receiving = movement[0][0], movement[-1][0]
    anchors = {document: [None, None] for document in (primary, receiving)}
    for slot, bound in enumerate(interval):
        if bound is None:
            continue
        anchors[bound[0]][slot] = bound
        old_anchor = source_raw.get(primary, (None, None))[slot]
        if bound[0] != primary and old_anchor in movement:
            # The remote anchor continues to override this original local handoff anchor.
            anchors[primary][slot] = old_anchor
    zone_edges, distances = _zone_interval(project, movement, interval)
    return {'effective_zone_anchors': interval, 'raw_zone_anchors': anchors, 'zone_edges': zone_edges,
            'zone_m_from_route_origin': distances, 'head_only': head_only if zone_edges else False,
            'aspect_code': code if zone_edges else 0}


def review_slow_zone_split(project, primary, fragment, movement, split, review):
    raw = {movement[0][0]: _stored_zone(project, primary)}
    if fragment is not None:
        raw[movement[-1][0]] = _stored_zone(project, fragment)
    original = tuple((review[label]['document'], review[label]['end_id']) for label in ('start', 'finish'))
    need(_effective_zone(raw, movement) == original and all(key in movement for key in original),
         'The reviewed Ends differ from the effective original slow-speed zone after continuation load')
    start, finish = map(movement.index, original)
    need(start < finish, 'Select a finite slow-speed zone in the original direction')
    nodes = path_functions.mutable_array(primary.contents[0].value)
    code, speed = _metric_zone_aspect(nodes, _protection_values(primary, _route_shape(primary))['signal_aspects'])
    head_only = bool(primary.contents[11].value & 2)
    need(code == review['expected_native_aspect_code'] and speed == review['expected_speed_kmh']
         and head_only == review['expected_head_only'], 'The reviewed native aspect, speed or head-only flag differs')
    cut = movement.index(split)
    upstream = (original[0], movement[min(finish, cut)]) if start < cut else (None, None)
    downstream = (movement[max(start, cut)], original[1]) if cut < finish else (None, None)
    _, signal_codes = _indication_records(nodes[0].contents[11].value.contents[10].value, nodes[0])
    need(upstream[0] is not None or 0 in signal_codes,
         'An ordinary upstream Route needs track-speed code 0 already available at its original signal')
    front = _section(project, movement[:cut + 1], upstream, raw, head_only, code)
    rear = _section(project, movement[cut:], downstream, raw, head_only, code)
    old_edges, old_zone_m = _zone_interval(project, movement, original)
    need(front['zone_edges'] + rear['zone_edges'] == old_edges, 'The split must partition the original slow-zone Edges')
    position = 'crossing' if start < cut < finish else ('upstream' if finish <= cut else 'downstream')
    return {'position': position, 'original_raw_zone_anchors': raw, 'original_effective_zone_anchors': original,
            'original_zone_edges': old_edges, 'original_zone_m_from_route_origin': old_zone_m,
            'original_signal_aspect_codes': signal_codes, 'aspect_code': code, 'speed_kmh': speed, 'head_only': head_only,
            'upstream': front, 'downstream': rear}


def extend_relay_indications(signal, owner, section):
    code = section['aspect_code']
    if code:
        holder = signal.contents[10].value
        existing, _ = _indication_records(holder, owner)
        signal.contents[10].value = _append_indications(holder, existing, [code], owner)


def check_slow_section(project, primary, section, *, reserve_with_previous, expected_signal_codes=None):
    movement = project.route_view(primary)
    owner = project.owners[id(primary)]
    raw = {owner[0]: list(_stored_zone(project, primary))}
    if movement[-1][0] != owner[0]:
        rows = [row for row in project.continuations if row['source_document'] == owner[0] and row['route'] == ref(primary)]
        need(len(rows) == 1, 'Expected one exact receiving slow-zone fragment')
        row, = rows
        part = project.owned((row['target_document'], row['target_connector']), 'OTRoute', ident(primary))
        raw[row['target_document']] = list(_stored_zone(project, part))
    bounds = _effective_zone(raw, movement)
    flags = int(reserve_with_previous) | (2 if section['head_only'] else 0)
    need(raw == section['raw_zone_anchors'] and bounds == section['effective_zone_anchors']
         and primary.contents[11].value == flags,
         'The primary or receiving saved slow-zone bounds or flags differ after native readback')
    nodes = path_functions.mutable_array(primary.contents[0].value)
    aspects = _protection_values(primary, _route_shape(primary))['signal_aspects']
    _, signal_codes = _indication_records(nodes[0].contents[11].value.contents[10].value, nodes[0])
    need(aspects == [section['aspect_code']] and section['aspect_code'] in signal_codes
         and (expected_signal_codes is None or signal_codes == expected_signal_codes),
         'The effective Route and starting Signal do not share the reviewed aspect')
    edges, zone_m = _zone_interval(project, movement, bounds)
    need((edges, zone_m) == (section['zone_edges'], section['zone_m_from_route_origin']),
         'The original slow-speed interval Edges or chainage differ after native readback')
    return edges
