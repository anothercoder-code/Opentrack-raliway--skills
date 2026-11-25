"""OpenTrack Track Inspector Cal. for a reviewed batch of native Edges."""

import math
import struct

from .multi_document.core import need
from .saved_geometry import _edge, _locality, _movement_manifest, model_id
from .saved_track_replacement import _protection_manifest
from .saved_used_edge_profile import map_margin_span_profiles, verify_margin_profiles


def _endpoint_mark(project, end):
    key = project.key(end)
    value = _locality(end)
    source = key
    if value is None:
        source = project.actual_related(key)
        value = _locality(project.model(source))
    return {'end': key, 'kilometre_source': None if value is None else source, 'kilometres': value}


def _calculation(project, edge):
    marks = [_endpoint_mark(project, edge.contents[slot].value) for slot in (7, 8)]
    a, b = (row['kilometres'] for row in marks)
    if a is None or b is None:
        return marks, None
    # Stock OTEdgeModel stores the signed metre difference in float32, then
    # passes its absolute value to the native half-away-from-zero converter.
    value = struct.unpack('<f', struct.pack('<f', (b - a) * 1000))[0]
    return marks, math.floor(abs(value) + 0.5)


def _movement_changes(project, before, changes):
    movements = []
    traversals = {}
    for identity, (sequence, _, _) in before.items():
        distance = 0
        revised = 0
        spans = []
        for a, b in zip(sequence, sequence[1:]):
            key = project.edge_between(a, b)
            length = project.model(key).contents[9].values[1]
            new_length = changes.get(key, length)
            if new_length != length:
                spans.append((distance, distance + length, new_length))
            distance += length
            revised += new_length
        if spans:
            need(0 < revised <= 2147483647, 'Calculated running distance exceeds the native signed range')
            traversals[identity] = distance, spans
            movements.append({'kind': identity[0], 'owner': identity[1], 'identity': identity[2],
                              'before_distance_m': distance, 'after_distance_m': revised,
                              'changed_track_traversals': len(spans)})
    return traversals, movements


def calculate_edge_lengths(project, document, operation, before):
    selected = operation['edges']
    ids = [row['edge_id'] for row in selected]
    need(ids and len(ids) == len(set(ids)), 'Select distinct Edge IDs in the current worksheet')
    results = []
    physical_changes = {}
    for row in selected:
        edge = _edge(project, document, row)
        old = edge.contents[9].values[1]
        need(0 < old < 2147483647 and old == row['expected_length_m'], 'The saved Edge length differs from the reviewed length')
        marks, length = _calculation(project, edge)
        expected = row.get('expected_calculated_length_m')
        need(expected is None or expected == length, 'The calculated length differs from the reviewed value')
        if length is not None and length != old:
            need(0 < length < 2147483647, 'The two kilometre points do not define a positive native length')
            a, b = (edge.contents[slot].value for slot in (7, 8))
            need(a.contents[12].value is None or a.contents[12].value is not b.contents[12].value,
                 'Calculating the length of a station berth requires a separate stopping-area contract')
            physical_changes[(document, model_id(edge))] = length
        results.append({'edge_id': model_id(edge), 'before_length_m': old,
                        'calculated_length_m': length, 'saved_length_m': old if length is None else length,
                        'status': 'missing_kilometres' if length is None else 'unchanged' if length == old else 'changed',
                        'endpoints': marks})
    traversals, movement_reports = _movement_changes(project, before, physical_changes)
    protections = {name: _protection_manifest(project, name) for name in {document, *(identity[1][0] for identity in traversals)}}
    margin_reports = map_margin_span_profiles(project, traversals, operation.get('map_itinerary_safety_margins') is True)
    for key, length in physical_changes.items():
        project.model(key).contents[9].values[1] = length
    expected_manifest = _movement_manifest(project)
    reported_distances = {(row['kind'], row['owner'], row['identity']): row['after_distance_m'] for row in movement_reports}
    for identity, (sequence, refs, profile) in before.items():
        updated = expected_manifest[identity]
        distance = reported_distances.get(identity)
        if distance is None:
            need(updated == (sequence, refs, profile), 'An unrelated movement geometry changed')
        else:
            need(updated[:2] == (sequence, refs) and sum(row[1] for row in updated[2]) == distance,
                 'A saved movement differs from its reviewed kilometration distance')
    affected = {document, *(row['document'] for row in margin_reports)} if physical_changes else set()
    report = {'edges': results, 'movements': movement_reports, 'mapped_safety_margin_profiles': margin_reports}
    return affected, report, expected_manifest, protections


def verify_calculated_lengths(project, document, report, protections):
    for row in report['edges']:
        edge = _edge(project, document, row)
        marks, length = _calculation(project, edge)
        need(edge.contents[9].values[1] == row['saved_length_m'] and marks == row['endpoints']
             and length == row['calculated_length_m'], 'Calculated native length or chainage source differs after readback')
    for name, expected in protections.items():
        need(_protection_manifest(project, name) == expected, 'Saved signal or release settings changed')
    verify_margin_profiles(project, report['mapped_safety_margin_profiles'])
    report['chainage_and_signal_protections_verified'] = True
