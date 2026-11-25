"""Reroute one continuous itinerary across multiple native document boundaries."""

from . import path_functions, writer
from .multi_document.core import need
from .saved_cross_document_reroute import _edge_key, _end_key, _walk_crossing
from .saved_crossing_dependencies import (exclusion_reviews, prepare_exclusions, transfer_occupation_groups,
                                           validate_exclusion_movements, verify_transfers, write_exclusions)
from .saved_geometry import _movement_manifest, model_id, project_from, set_vertex_details, transform
from .zero_generation.topology import flt


def _itinerary(project, name):
    matches = [obj for obj in project.dests if path_functions.string(obj.contents[1].value) == name]
    need(len(matches) == 1, 'Select one unambiguous existing witness Itinerary')
    return project.dest_view(matches[0])


def _interval(project, nodes, start, arrivals):
    matches = [(index, index + len(arrivals)) for index, node in enumerate(nodes[:-1])
               if project.actual_related(node) == start
               and tuple(nodes[index + 1:index + 1 + len(arrivals)]) == arrivals]
    need(len(matches) == 1, 'Each crossing span must occur exactly once on the witness Itinerary')
    return matches[0]


def _crossings(project, sequence):
    found = []
    for index, (a, b) in enumerate(zip(sequence, sequence[1:])):
        if a[0] != b[0]:
            outgoing = project.related(a)
            incoming = project.block_end(outgoing)
            need(incoming[0] == b[0], 'Witness connector does not reach the next document')
            found.append((index, (outgoing, incoming)))
    return found


def _station_markers(project, nodes):
    result = []
    for key in nodes:
        end = project.model(key)
        if end.contents[20].value == 2:
            station = end.contents[12].value
            need(station is not None and writer.kind(station) == 'OTStationModel', 'Unbound station marker in witness')
            result.append((key, path_functions.string(station.contents[7].value)))
    return result


def _distance(project, nodes):
    return sum(project.model(project.edge_between(a, b)).contents[9].values[1]
               for a, b in zip(nodes, nodes[1:]))


def _review_spans(project, nodes, crossings, batch_exclusions):
    selected = []
    for request in crossings:
        start = _end_key(request['start_end'])
        old_review = batch_exclusions or exclusion_reviews(request.get('exclusion_link_rebindings', ()), 'old')
        old_arrivals, _, old_pair, _ = _walk_crossing(project, start, request['old_edges'], old_review)
        replacement, _, new_pair, _ = _walk_crossing(project, start, request['replacement_edges'], old_review)
        first, last = _interval(project, nodes, start, old_arrivals)
        selected.append((first, last, old_pair, new_pair, replacement))
    need(all(previous[1] <= following[0] for previous, following in zip(selected, selected[1:])),
         'Crossing spans must be disjoint and follow the witness travel order')
    first_index, last_index = selected[0][0], selected[-1][1]
    old_crossings = _crossings(project, nodes)
    enclosed = [pair for index, pair in old_crossings if first_index <= index < last_index]
    need(enclosed == [row[2] for row in selected], 'Select every document boundary within the reviewed itinerary span')
    documents = [nodes[first_index][0], *(pair[1][0] for pair in enclosed)]
    need(len(documents) >= 3 and len(set(documents)) == len(documents),
         'Select a span crossing at least three distinct documents without revisiting a document')
    return selected, old_crossings, documents


def _save_documents(staged, project, names):
    for name in names:
        staged[name] = writer.dump_verified(project.roots[name], project.versions[name])


def _turnout_state(project, end_key):
    end = project.model(end_key)
    need(writer.kind(end) == 'OTEndModel' and all(end.contents[field].value is not None for field in (9, 10)),
         'Review a native directional End with both turnout legs present')
    edges = [model_id(end.contents[field].value) for field in (9, 10)]
    branch = end.contents[22].value
    need(branch in (0, 1), 'The turnout default leg is outside the verified native settings')
    return {'edge_ids': edges, 'default_edge_id': edges[branch], 'switch_time_s': float(end.contents[21].value)}


def _update_turnouts(original, staged, operation, selected_edges):
    reviewed = {}
    for item in operation.get('turnout_updates', ()):
        key = _end_key(item['end'])
        need(key not in reviewed, 'Select each directional turnout once')
        before = _turnout_state(original, key)
        edges = before['edge_ids']
        need(any((key[0], edge) in selected_edges for edge in edges), 'Select a turnout belonging to the reviewed crossing rails')
        need(before == {'edge_ids': item['expected_edge_ids'], 'default_edge_id': item['expected_default_edge_id'],
                        'switch_time_s': flt(item['expected_switch_time_s'], 'Reviewed turnout switch time')},
             'The original turnout legs, default, or throw time differ from the exact review')
        need(before == _turnout_state(staged, key), 'Both reviewed turnout legs must remain available after reroute and retirement')
        target = item['default_edge_id']
        need(target in edges, 'The requested default must be one of the two retained native turnout legs')
        set_vertex_details(staged, key[0], {'end_id': key[1], 'both_halves': False,
                           'changes': {'switch_time_s': item['switch_time_s'], 'default_second_leg': target == edges[1]}})
        reviewed[key] = {'end': key, 'before': before, 'after': _turnout_state(staged, key)}
    return reviewed


def _verify_final_crossing_profiles(project, steps, exclusions, turnouts, *, reviewed_instruments=None,
                                    reviewed_instrument_ends=(), collapsed_turnouts=()):
    for step in steps:
        for label, start, terminal, pair in (
                ('new_profile', step['start_end'], step['terminal_end'], tuple(step['new_pair'])),
                ('new_reverse_profile', step['terminal_end'], step['start_end'], tuple(reversed(step['new_pair'])))):
            original = step[label]
            ends, _, actual_pair, revised = _walk_crossing(
                project, start, original, exclusions, reviewed_instruments=reviewed_instruments,
                reviewed_instrument_ends=reviewed_instrument_ends)
            need(ends[-1] == terminal and actual_pair == pair, 'A final crossing no longer reaches its reviewed directed End')
            for before, after in zip(original, revised, strict=True):
                switch = before['switch']
                if switch is not None:
                    key = before['document'], switch['end_id']
                    reviewed = turnouts.get(key)
                    if reviewed is not None:
                        target = reviewed['after']
                        switch = {**switch, 'switch_time_s': target['switch_time_s'],
                                  'default_leg': target['edge_ids'].index(target['default_edge_id']) + 1}
                    elif key in collapsed_turnouts:
                        switch = None
                need(after == {**before, 'switch': switch}, 'A final crossing profile changed beyond the reviewed turnout settings')
            step[label] = revised


def reroute_multi_document_track_span(documents, document_paths, dest_catalog, target, operation):
    requests = operation['crossings']
    need(len(requests) >= 2 and requests[0]['start_end']['document'] == target,
         'Choose the first crossing document as the target of this multi-document edit')
    name = operation['witness_itinerary']
    original = project_from(documents, document_paths, dest_catalog)
    old_nodes, old_refs = _itinerary(original, name)
    batch_links = operation.get('exclusion_link_rebindings', ())
    batch_groups = operation.get('occupation_group_rebindings', ())
    need(not (batch_links or batch_groups) or not any(row.get('exclusion_link_rebindings')
             or row.get('occupation_group_rebindings') for row in requests),
         'Review crossing dependencies at batch scope or individual crossing scope')
    reviewed, old_crossings, span_documents = _review_spans(original, old_nodes, requests, exclusion_reviews(batch_links, 'old'))
    old_markers = _station_markers(original, old_nodes)
    old_distance = _distance(original, old_nodes)
    old_movements = _movement_manifest(original)
    staged = dict(documents)
    dependency_batch = {field: [edge for request in requests for edge in request[field]]
                        for field in ('old_edges', 'replacement_edges')}
    dependency_batch.update(exclusion_link_rebindings=batch_links, occupation_group_rebindings=batch_groups)
    detached, new_links = prepare_exclusions(original, dependency_batch)
    group_changes = transfer_occupation_groups(original, dependency_batch)
    write_exclusions(original, detached)
    pretransfer_names = set(detached) | {row['after']['document'] for row in group_changes}
    _save_documents(staged, original, pretransfer_names)
    report = []
    for request in requests:
        updates, receipt = transform(staged, document_paths, dest_catalog, request['start_end']['document'],
                                     {**request, 'action': 'reroute_cross_document_track_span'})
        staged.update(updates)
        report.append(receipt)

    checked = project_from(staged, document_paths, dest_catalog)
    selected_edges = {_edge_key(edge) for field in ('old_edges', 'replacement_edges') for edge in dependency_batch[field]}
    updated_turnouts = _update_turnouts(original, checked, operation, selected_edges)
    final_exclusions, final_groups = {}, {}
    for row in report:
        dependencies = row.get('dependency_transfers', {})
        final_exclusions.update(dependencies.get('verified_exclusion_maps', {}))
        for group in dependencies.get('occupation_group_rebindings', ()):
            final_groups[group['after']['document'], group['after']['name']] = group
    if new_links:
        movements = _movement_manifest(checked)
        changed = {key: movement for key, movement in movements.items() if old_movements[key] != movement}
        validate_exclusion_movements(checked, new_links.keys(), new_links, batch_links, movements, changed)
        write_exclusions(checked, new_links)
        final_exclusions.update({name: sorted(links.items()) for name, links in new_links.items()})
    for group in group_changes:
        final_groups[group['after']['document'], group['after']['name']] = group
    finalized = set(new_links) | {key[0] for key in updated_turnouts}
    if finalized:
        _save_documents(staged, checked, finalized)
        checked = project_from(staged, document_paths, dest_catalog)
    verify_transfers(checked, final_exclusions, final_groups.values())
    for key, item in updated_turnouts.items():
        need(_turnout_state(checked, key) == item['after'], 'Turnout legs, default, or throw time failed cold reread')
    if finalized:
        _verify_final_crossing_profiles(checked, report, final_exclusions, updated_turnouts)
    new_nodes, new_refs = _itinerary(checked, name)
    new_distance = _distance(checked, new_nodes)
    need(new_refs == old_refs and new_nodes[0] == old_nodes[0] and new_nodes[-1] == old_nodes[-1],
         'The witness Path identities or enclosing directional Ends changed')
    need(_station_markers(checked, new_nodes) == old_markers, 'A witness station marker moved or changed occurrence order')
    need(new_distance == operation['expected_witness_length_m']
         and new_distance == old_distance + sum(row['new_length_m'] - row['old_length_m'] for row in report),
         'Final witness distance differs from the reviewed replacements')
    replacements = {row[2]: row[3] for row in reviewed}
    expected_crossings = [replacements.get(pair, pair) for _, pair in old_crossings]
    need([pair for _, pair in _crossings(checked, new_nodes)] == expected_crossings,
         'The ordered final connector crossings differ from the reviewed itinerary')
    new_intervals = [_interval(checked, new_nodes, _end_key(request['start_end']), row[4])
                     for request, row in zip(requests, reviewed, strict=True)]
    need(all(previous[1] <= following[0] for previous, following in zip(new_intervals, new_intervals[1:])),
         'New crossing spans no longer follow the reviewed order')
    new_movements = _movement_manifest(checked)
    need(old_movements.keys() == new_movements.keys()
         and all(old_movements[key][1] == new_movements[key][1] for key in old_movements),
         'A native Route, Path, Itinerary or Shunting identity or binding changed')
    outputs = {doc: staged[doc] for doc in sorted(staged) if staged[doc] != documents[doc]}
    need(all(doc in outputs for row in report for doc in row['changed_documents']),
         'A changed document did not persist its reviewed Route fragments')
    return outputs, {
        'action': operation['action'], 'document': target, 'changed_documents': sorted(outputs),
        'witness_itinerary': name, 'witness_old_length_m': old_distance, 'witness_new_length_m': new_distance,
        'witness_station_markers': old_markers, 'witness_crossing_documents': span_documents,
        'original_connector_pairs': [pair for _, pair in old_crossings],
        'replacement_connector_pairs': expected_crossings, 'crossing_edits': report,
        'batch_dependency_transfers': {'exclusion_link_rebindings': list(batch_links),
            'verified_exclusion_maps': {name: sorted(links.items()) for name, links in new_links.items()},
            'occupation_group_rebindings': group_changes, 'native_readback_verified': True},
        'turnout_updates': list(updated_turnouts.values()),
        'movement_count_checked': len(old_movements), 'destination_catalog_unchanged': True,
        'safety_regrouped': False, 'native_execution_tested': False,
    }
