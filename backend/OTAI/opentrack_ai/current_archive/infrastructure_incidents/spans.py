"""Original kilometre and route-relative incident targets."""

import math
import re
import struct

from .. import incident_operations as storage, path_functions, writer
from ..multi_document.core import ident


TRACK_TYPES = (6, 7, 8)
SPAN_TYPES = (*TRACK_TYPES, 13)
DISTANCE = r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?'
# Route (from-to) aliases begin/end Track ID, leaving Line ID unused.
TRACK_FIELDS = ('line_id', 'line_id', 'track_id', 'track_id', 'begin_km', 'end_km')
ROUTE_FIELDS = (None, None, 'begin_route', 'end_route', 'begin_offset_km', 'end_offset_km')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def metres(text):
    storage.text(text, nonempty=True)
    require(len(text) <= 32 and re.fullmatch(DISTANCE, text), 'Expected a decimal kilometre string')
    value = float(text)
    require(math.isfinite(value) and abs(value) < 99999, 'Kilometre value outside the finite original locality domain')
    return f32(f32(value) * 1000)


def encoded_fields(item, code):
    fields = TRACK_FIELDS if code in TRACK_TYPES else ROUTE_FIELDS if code == 13 else (None,) * 6
    return [item.get(field, '') for field in fields]


def saved_fields(cells, code):
    fields = TRACK_FIELDS if code in TRACK_TYPES else ROUTE_FIELDS
    if code in TRACK_TYPES:
        require(all(path_functions.string(cells[a].value) == path_functions.string(cells[b].value)
                    for a, b in ((8, 9), (10, 11))), 'Beginning and ending line and track must match')
    return {field: path_functions.string(cells[slot].value)
            for slot, field in enumerate(fields, 8) if field is not None}


def edge_locality(project, end):
    # OpenTrack takes the locality of actualRelated first, then this End.
    other = project.model(project.actual_related(project.key(end)))
    for obj in (other, end):
        km = obj.contents[14].value
        require(math.isfinite(km), 'Nonfinite saved End locality')
        if km != -99999.0:
            return f32(km * 1000)
    return None


def track_edges(project, item):
    line = storage.text(item['line_id'])
    track = storage.text(item['track_id'])
    begin, end = metres(item['begin_km']), metres(item['end_km'])
    forward = begin <= end
    low, high = sorted((begin, end))
    selected = []
    for doc, models in project.models.items():
        for edge in models:
            if writer.kind(edge) != 'OTEdgeModel':
                continue
            if line and (edge.contents[20].value is None or path_functions.string(edge.contents[20].value) != line):
                continue
            if track and (edge.contents[19].value is None or path_functions.string(edge.contents[19].value) != track):
                continue
            anchor = edge_locality(project, edge.contents[7 if forward else 8].value)
            if anchor is None:
                continue
            length = edge.contents[9].values[1]
            entry, exit = (anchor, f32(anchor + length)) if forward else (f32(anchor - length), anchor)
            matched = entry <= low < exit if low == high else entry < high and low < exit
            if matched:
                selected.append({'document': doc, 'edge_id': edge.contents[0].value,
                                 'kilometre_interval_m': [entry, exit]})
    require(selected, 'No original edge overlaps the specified line, track and kilometre range')
    direction = 'point' if begin == end else 'increasing' if forward else 'decreasing'
    return {'begin_m': begin, 'end_m': end, 'direction': direction, 'edges': selected}


def route_bounds(project, item):
    bounds = []
    for side in ('begin', 'end'):
        name = storage.text(item[f'{side}_route'], nonempty=True)
        selected = [route for route in project.routes if ident(route)[0] == name
                    and writer.kind(project.model(project.owners[id(route)])) == 'OTEndModel']
        require(len(selected) == 1, f'Route-relative incident requires an unambiguous native Route: {name}')
        route = selected[0]
        nodes = project.route_view(route)
        length = sum(project.model(project.edge_between(a, b)).contents[9].values[1]
                     for a, b in zip(nodes, nodes[1:]))
        offset = metres(item[f'{side}_offset_km'])
        require(0 <= offset <= length, f'Incident offset outside the original Route: {name}')
        bounds.append({'route': name, 'document': nodes[0][0], 'start_end_id': nodes[0][1],
                       'offset_m': offset, 'length_m': length})
    require(bounds[0]['route'] != bounds[1]['route'] or bounds[0]['offset_m'] <= bounds[1]['offset_m'],
            'The end offset precedes the beginning on the same Route')
    return {'begin': bounds[0], 'end': bounds[1]}
