"""Reroute occupied definitions through a reviewed alternative native track chain."""

import math
from pathlib import PureWindowsPath

from . import native_occupation_groups, path_functions, writer
from .graph_references import reference_inventory
from .multi_document.core import ident, need
from .route_edit_tools import _change_route_fragment
from .saved_crossing_instruments import (
    apply_instrument_edge_rebindings, prepare_instrument_edge_rebindings, relocated_instrument_ends, verify_instrument_edge_rebindings,
)
from .saved_geometry import _edge, _end_shape, _movement_geometry, _movement_items, _speed_table, model_id
from .saved_track_replacement import _protection_manifest
from .saved_track_topology import _delete_isolated_vertices, _detach_edge_endpoints, _replace_models
from .saved_used_edge_profile import _map_margin_profiles, verify_margin_profiles


def _walk_span(project, document, start, edge_ids, *, reviewed_exclusions=(), reviewed_instruments=None,
               reviewed_instrument_ends=()):
    travelled = set()
    arrivals = []
    profiles = []
    cursor = project.model(start)
    _end_shape(cursor)
    need(writer.kind(cursor) == 'OTEndModel' and start[0] == document, 'Select a local directional track End')
    travelled.update((start, project.related(start)))
    instruments = reviewed_instruments or {}
    for index, edge_id in enumerate(edge_ids):
        edge = _edge(project, document, {'edge_id': edge_id}, reviewed_exclusions=reviewed_exclusions,
                     reviewed_instrument_observers=instruments.get(edge_id, 0))
        a, b = (edge.contents[slot].value for slot in (7, 8))
        need(cursor in (a, b), 'The selected track chain is disconnected or out of order')
        along = cursor is a
        arrived = b if along else a
        arrived_key = project.key(arrived)
        pair_key = project.related(arrived_key)
        need(arrived_key not in travelled and pair_key not in travelled, 'A selected span revisits a double vertex')
        travelled.update((arrived_key, pair_key))
        arrivals.append(arrived_key)
        switch = None
        if cursor.contents[10].value is not None:
            switch_time = float(cursor.contents[21].value)
            default_second = cursor.contents[22].value
            need(math.isfinite(switch_time) and switch_time >= 0 and default_second in (0, 1),
                 'The selected chain encounters unverified switch settings')
            switch = {'end_id': model_id(cursor), 'selected_leg': 1 if cursor.contents[9].value is edge else 2,
                      'default_leg': default_second + 1, 'switch_time_s': switch_time}
        metric = edge.contents[9].values
        profiles.append({'edge_id': edge_id, 'length_m': metric[1], 'radius_m': float(metric[2]),
                         'gradient_per_mille': float(metric[3] if along else -metric[3]),
                         'safety_element_id': model_id(cursor.contents[7].value), 'switch': switch,
                         'speeds_kmh': {key: row.contents[1 if along else 2].value
                                        for key, row in _speed_table(edge).items()}})
        if index != len(edge_ids) - 1:
            cursor = project.model(pair_key)
            for obj in (arrived, cursor):
                _end_shape(obj)
                need(writer.kind(obj) == 'OTEndModel' and obj.contents[20].value == 1
                     and all(obj.contents[slot].value is None for slot in (6, 11, 12))
                     and (obj.contents[13].value is None or project.key(obj) in reviewed_instrument_ends),
                     'Span interiors must be ordinary Ends without stations, signals or instruments except reviewed instrument transfers')
    total = sum(row['length_m'] for row in profiles)
    need(0 < total <= 2147483647, 'Track span length outside native signed range')
    return tuple(arrivals), total, profiles


def _rebind_sequence(project, nodes, substitutions):
    result = [nodes[0]]
    position = 0
    spans = []
    index = 0
    while index < len(nodes) - 1:
        change = substitutions.get(project.actual_related(nodes[index]))
        if change is not None:
            old, new, old_length = change
            if tuple(nodes[index + 1:index + 1 + len(old)]) == old:
                result.extend(new)
                spans.append((position, position + old_length))
                position += old_length
                index += len(old)
                continue
        before, after = nodes[index:index + 2]
        position += project.model(project.edge_between(before, after)).contents[9].values[1]
        result.append(after)
        index += 1
    return result, position, spans


def _rewrite_local_definitions(project, document, substitutions):
    counts = reference_inventory(project.roots[document])[1]
    rewritten = []
    for owner, movement in _movement_items(project):
        if owner[0] != document:
            continue
        array = movement.contents[0].value
        old_nodes = path_functions.mutable_array(array)
        saved_keys = [project.key(obj) for obj in old_nodes]
        continuation = writer.kind(project.model(owner)) == 'OTConnModel'
        keys = [owner, *saved_keys] if continuation else saved_keys
        reviewed, _, spans = _rebind_sequence(project, keys, substitutions)
        if not spans:
            continue
        new_keys = reviewed[1:] if continuation else reviewed
        kind = writer.kind(movement)
        need(len(new_keys) <= 1000 and len(set(new_keys)) == len(new_keys),
             'Reroute would repeat a saved directional End or exceed the supported fragment size')
        nodes = [project.model(key) for key in new_keys]
        if kind == 'OTRoute':
            has_continuation_index = movement.contents[5].values[4] != -1
            try:
                _change_route_fragment(movement, nodes, counts, None, primary=has_continuation_index)
            except ValueError as exc:
                raise ValueError(f"Reroute must preserve all release-group and slow-zone anchors: {exc}") from exc
        else:
            need(counts[id(array)] == 1, 'A Shunting shares its saved End sequence')
            movement.contents[0].value = path_functions.array_like(array, nodes)
        rewritten.append({'kind': kind, 'owner': owner, 'identity': ident(movement),
                          'before_end_ids': [key[1] for key in saved_keys],
                          'after_end_ids': [key[1] for key in new_keys]})
    need(rewritten, 'The selected travel span is not entirely contained in a saved local fragment')
    return rewritten


def _retire_original_span(project, document, operation, original_interior, expected, *, reviewed_instrument_ends=()):
    replacement = set(operation['replacement_edge_ids'])
    retired_ids = [edge_id for edge_id in operation['old_edge_ids'] if edge_id not in replacement]
    retired_set = set(retired_ids)
    retired_keys = {(document, edge_id) for edge_id in retired_ids}
    need(retired_ids, 'The completely retargeted chain has no old-only Edge to retire')
    for label, (sequence, _, _) in expected.items():
        need(all(project.edge_between(a, b) not in retired_keys for a, b in zip(sequence, sequence[1:])),
             f'A saved {label[0]} {label[2]!r} still traverses an Edge selected for retirement')
    for sheet, root in project.roots.items():
        for row in native_occupation_groups.records(root, sheet):
            observed_sheet = PureWindowsPath(row['saved_document']).name.casefold().removesuffix('.opentrack')
            if observed_sheet == document.casefold() or sheet == document:
                need(retired_set.isdisjoint(row['edge_ids']),
                     f'Saved occupation monitor {row["name"]!r} still refers to a retired Edge')
    retired_ends = operation.get('retire_isolated_end_ids', ())
    eligible = {end[1] for vertex in original_interior for end in (vertex, project.related(vertex))}
    need(set(retired_ends) <= eligible, 'Only confirmed interior pairs of the retired span can be removed')

    edges = [_edge(project, document, {'edge_id': ident}) for ident in retired_ids]
    detached = []
    for edge in edges:
        _, first, last = _detach_edge_endpoints(edge, reviewed_instrument_ends=reviewed_instrument_ends)
        detached.append({'edge_id': model_id(edge), 'former_end_ids': [model_id(first), model_id(last)]})
    retired = set(edges)
    _replace_models(project, document, [obj for obj in project.models[document] if obj not in retired])
    removed_vertices = _delete_isolated_vertices(project, document, retired_ends) if retired_ends else {}
    return {'edges': detached, **removed_vertices}


def reroute_used_track_span(project, document, operation, before):
    old_edges = operation['old_edge_ids']
    new_edges = operation['replacement_edge_ids']
    need(old_edges and new_edges and len(set(old_edges)) == len(old_edges)
         and len(set(new_edges)) == len(new_edges) and set(new_edges) - set(old_edges),
         'Select ordered nonrepeating spans and at least one genuinely different replacement Edge')
    dependency = {
        'old_edges': [{'document': document, 'edge_id': edge} for edge in old_edges],
        'replacement_edges': [{'document': document, 'edge_id': edge} for edge in new_edges],
    }
    instrument_plan, former_observers, final_observers = prepare_instrument_edge_rebindings(
        project, dependency, operation.get('instrument_edge_rebindings', ()))
    former = {'reviewed_instruments': former_observers.get(document), 'reviewed_instrument_ends': relocated_instrument_ends(instrument_plan)}
    final = {'reviewed_instruments': final_observers.get(document), 'reviewed_instrument_ends': relocated_instrument_ends(instrument_plan, after=True)}
    start = (document, operation['start_end_id'])
    old, old_length, old_profiles = _walk_span(project, document, start, old_edges, **former)
    new, new_length, new_profiles = _walk_span(project, document, start, new_edges, **former)
    end = old[-1]
    need(new[-1] == end and old != new, 'Replacement must rejoin the original directed outer End via a different chain')
    first, last = map(project.model, (start, end))
    need(first.contents[12].value is None or first.contents[12].value is not last.contents[12].value,
         'A track span inside a station stopping area requires its own contract')
    need(operation['expected_replacement_length_m'] == new_length
         and operation['expected_replacement_safety_element_ids'] == [row['safety_element_id'] for row in new_profiles],
         'Replacement length or ordered Safety Element IDs differ from the reviewed values')
    old_reverse, _, _ = _walk_span(project, document, end, old_edges[::-1], **former)
    new_reverse, _, reverse_profiles = _walk_span(project, document, end, new_edges[::-1], **former)
    need(old_reverse[-1] == new_reverse[-1] == start, 'Reverse movement must close at the original End')
    substitutions = {start: (old, new, old_length), end: (old_reverse, new_reverse, old_length)}

    expected = before.copy()
    traversals = {}
    summary = []
    delta = new_length - old_length
    for identity, (sequence, refs, _) in before.items():
        rebound, distance, spans = _rebind_sequence(project, sequence, substitutions)
        if not spans:
            continue
        geometry = _movement_geometry(project, rebound, check_safety=True)
        revised_distance = sum(segment[1] for segment in geometry)
        need(0 < revised_distance <= 2147483647 and revised_distance == distance + delta * len(spans),
             'Reroute distance differs from the selected native spans')
        traversals[identity] = distance, spans
        expected[identity] = rebound, refs, geometry
        summary.append({'kind': identity[0], 'owner': identity[1], 'identity': identity[2],
                        'before_distance_m': distance, 'after_distance_m': revised_distance,
                        'rerouted_span_traversals': len(spans)})
    need(traversals, 'No saved Route, Shunting, Path or Itinerary crosses the whole selected span')
    protection = {name: _protection_manifest(project, name)
                  for name in {document, *(identity[1][0] for identity in traversals)}}
    changes = _rewrite_local_definitions(project, document, substitutions)
    margins = []
    if delta:
        margins = _map_margin_profiles(project, traversals, new_length,
                                      operation.get('map_itinerary_safety_margins') is True)
    affected = {document, *(row['document'] for row in margins)}
    report = {'start_end_id': start[1], 'terminal_end_id': end[1], 'old_span': old_profiles,
              'replacement_span': new_profiles, 'replacement_reverse_span': reverse_profiles,
              'old_span_length_m': old_length, 'replacement_span_length_m': new_length,
              'rewritten_movements': changes, 'affected_movement_distances': summary,
              'mapped_safety_margin_profiles': margins, 'original_track_chain_retained': True}
    if instrument_plan:
        report['dependency_transfers'] = {
            'instrument_edge_rebindings': apply_instrument_edge_rebindings(project, instrument_plan),
        }
    if operation.get('retire_original'):
        reviewed_ends = {project.model((row.document, row.new_end_id)) for row in instrument_plan}
        report['retirement'] = _retire_original_span(
            project, document, operation, old[:-1], expected, reviewed_instrument_ends=reviewed_ends)
        report['original_track_chain_retained'] = False
        report['replacement_span'] = _walk_span(project, document, start, new_edges, **final)[2]
        report['replacement_reverse_span'] = _walk_span(
            project, document, end, new_edges[::-1], **final)[2]
    else:
        need(not operation.get('retire_isolated_end_ids'), 'Retiring original vertices requires explicit track retirement')
    return affected, report, expected, protection, (instrument_plan, final_observers.get(document))


def verify_reroute(project, document, report, protection, instrument_review):
    instrument_plan, reviewed_instruments = instrument_review
    reviewed_ends = relocated_instrument_ends(instrument_plan, after=True)
    labels = ['replacement_span']
    if report['original_track_chain_retained']:
        labels.append('old_span')
    else:
        retirement = report['retirement']
        removed = {row['edge_id'] for row in retirement['edges']}
        removed.update(retirement.get('removed_end_ids', ()))
        removed.update(retirement.get('removed_safety_element_ids', ()))
        need(removed.isdisjoint(project.byid[document]), 'A retired track or isolated vertex survived native readback')
    for label in labels:
        edge_ids = [row['edge_id'] for row in report[label]]
        arrivals, _, profiles = _walk_span(
            project, document, (document, report['start_end_id']), edge_ids, reviewed_instruments=reviewed_instruments,
            reviewed_instrument_ends=reviewed_ends)
        need(arrivals[-1] == (document, report['terminal_end_id']) and profiles == report[label],
             'The original or replacement track alignment changed after native readback')
    reversed_ids = [row['edge_id'] for row in report['replacement_reverse_span']]
    reverse_arrivals, _, reverse_profiles = _walk_span(
        project, document, (document, report['terminal_end_id']), reversed_ids, reviewed_instruments=reviewed_instruments,
        reviewed_instrument_ends=reviewed_ends)
    need(reverse_arrivals[-1] == (document, report['start_end_id'])
         and reverse_profiles == report['replacement_reverse_span'],
         'The reverse replacement profile changed after native readback')
    for name, manifest in protection.items():
        need(_protection_manifest(project, name) == manifest, 'Signal indications or release settings changed')
    verify_margin_profiles(project, report['mapped_safety_margin_profiles'])
    if instrument_plan:
        verify_instrument_edge_rebindings(project, instrument_plan)
        report['dependency_transfers']['native_readback_verified'] = True
    report['signal_and_release_settings_preserved'] = True
