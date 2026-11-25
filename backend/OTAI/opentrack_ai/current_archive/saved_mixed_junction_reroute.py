"""Plan local and crossing junction revisions against one immutable native graph."""

from collections import defaultdict

from . import native_occupation_groups
from .multi_document.core import need
from .saved_cross_document_reroute import (
    _edge_key, _end_key, _inspect_alignment, _retire_crossing_network, _rewrite_cross_routes, _walk_crossing,
)
from .saved_crossing_dependencies import (
    _edges, crossing_edge_changes, prepare_exclusions, retain_crossing_exclusions, validate_exclusion_movements,
    verify_transfers, write_exclusions,
)
from .saved_crossing_instruments import (
    apply_instrument_edge_rebindings, prepare_instrument_edge_rebindings, relocated_instrument_ends,
    verify_instrument_edge_rebindings,
)
from .saved_edge_exclusion import _links
from .saved_geometry import _movement_manifest, model_id, project_from
from .saved_junction_reroute import (
    _check_witnesses, _commit_continuations, _exclusion_review, _identity, _metres, _retained_routes,
    _route_edge_keys, _selected_berths, _verify_berths,
)
from .saved_local_junction_reroute import (
    _alignment, _collect_route_anchors, _compile_plans, _continuations, _migrate_occupation, _rewrite_routes,
    _verify_alignments, _verify_occupation,
)
from .saved_multi_document_reroute import _save_documents, _turnout_state, _update_turnouts, _verify_final_crossing_profiles
from .saved_track_replacement import _protection_manifest
from .saved_used_edge_profile import map_margin_span_profiles, verify_margin_profiles


def _dependency(crossings, local_alignments, operation):
    fields = (('old_edges', 'old_edge_ids'), ('replacement_edges', 'replacement_edge_ids'))
    local_branches = [{cross: [{'document': row['document'], 'edge_id': edge} for edge in row[local]]
                       for cross, local in fields} for row in local_alignments]
    branches = [*crossings, *local_branches]
    dependency = {field: [edge for row in branches for edge in row[field]] for field, _ in fields}
    dependency['crossings'] = branches
    dependency.update({key: operation.get(key, ()) for key in ('retained_exclusion_links', 'exclusion_link_rebindings',
                                                               'occupation_group_rebindings', 'occupation_group_extensions')})
    return dependency


def _fragment_keys(routes, continuations):
    keys = {(route[1], route[2]) for route in routes}
    keys.update((continuations[route][1], route[2]) for route in routes if route in continuations)
    return keys


def _select_routes(row, before, continuations, selected, anchors, oriented, length, review, index):
    keys = [_identity('route', item['document'], item) for item in row['routes']]
    need(keys and len(set(keys)) == len(keys) and all(key in before for key in keys),
         'Select each exact existing primary Route once per alignment')
    need(set(review) <= _fragment_keys(keys, continuations),
         'An anchor review belongs to a different Route than this alignment selects')
    _collect_route_anchors(anchors, review)
    for key in keys:
        selected[key].append((index, oriented, length))
    return keys


def _apply_route_fragments(project, crossing, allowed_documents, selected, anchors, continuations, expected, protection):
    main, pending, affected = [], [], set()
    final_continuations = continuations.copy()
    cross_keys = set()
    for report, boundary, keys in crossing:
        need(cross_keys.isdisjoint(keys), 'One native Route can own only one reviewed cross-document interval')
        cross_keys.update(keys)
        cross_anchors = {key: anchors.pop(key) for key in _fragment_keys(keys, continuations) if key in anchors}
        updated = _rewrite_cross_routes(project, {key: expected[key][0] for key in keys}, tuple(report['old_pair']),
                                        tuple(report['new_pair']), boundary, cross_anchors, protection, pending=pending)
        report['rewritten_routes'] = updated
        main.extend(updated)
        for key, row in zip(keys, updated, strict=True):
            final_continuations[key] = tuple(row['new_pair'])
            if row['primary_fragment_changed']:
                affected.add(row['route_owner'][0])
            if row['receiving_fragment_changed']:
                affected.add(row['new_pair'][1][0])
    local = _rewrite_routes(project, allowed_documents, expected, [key for key in selected if key not in cross_keys],
                            anchors, continuations, protection)
    affected.update(row['fragment_owner'][0] for row in local)
    _commit_continuations(project, pending, protection)
    return main, local, affected, final_continuations


def _incident_edges(end, document):
    return [(document, model_id(end.contents[slot].value)) for slot in (9, 10)
            if end.contents[slot].value is not None]


def _mixed_retirement(project, operation, crossings, local_reports, old_only, expected, exclusion_maps, instrument_ends):
    listed = list(map(_edge_key, operation.get('retire_edges', ())))
    all_former = operation.get('retire_original', False)
    isolated = list(map(_end_key, operation.get('retire_isolated_ends', ())))
    use_retirement = bool(listed) or all_former
    need(not isolated or use_retirement, 'Select former track retirement before removing its isolated vertices')
    if not use_retirement:
        return set(), [], {}, []
    need(not (listed and all_former) and len(set(listed)) == len(listed),
         'Choose one retirement mode and select each reviewed former Edge once')
    retired = set(old_only) if all_former else set(listed)
    need(retired and retired <= old_only, 'Retire only selected former-only tracks in the mixed junction')
    need(all(not any((document, edge) in retired for edge in pair)
             for document, pairs in exclusion_maps.items() for pair in pairs),
         'An Edge selected for retirement still owns a reciprocal exclusion link')

    old_pairs = {tuple(sorted(row['old_pair'])) for row in crossings}
    new_pairs = {tuple(sorted(row['new_pair'])) for row in crossings}
    ends = {}
    for edge_key in sorted(retired):
        edge = project.model(edge_key)
        for slot in (7, 8):
            end = edge.contents[slot].value
            key = project.key(end)
            ends[key] = _incident_edges(end, key[0])
    protected = {end for pair in old_pairs | new_pairs for end in pair}
    protected.update(row[key] for row in [*crossings, *local_reports] for key in ('start_end', 'terminal_end'))
    protected |= {project.related(end) for end in protected}
    eligible = (ends.keys() | {project.related(end) for end in ends}) - protected
    need(set(isolated) <= eligible, 'Select ordinary isolated pairs belonging to the retiring former track')

    connectors = []
    for pair in sorted(old_pairs):
        approaches = [project.related(end) for end in pair]
        abandoned = [bool(incident) and set(incident) <= retired for incident in
                     (_incident_edges(project.model(end), end[0]) for end in approaches)]
        if any(abandoned):
            need(all(abandoned) and pair not in new_pairs,
                 'Retire both unused approaches before removing a former reciprocal connector pair')
            connectors.append(pair)
    collapsed = {}
    for end, incident in sorted(ends.items()):
        kept = [edge for edge in incident if edge not in retired]
        if len(incident) == 2 and len(kept) == 1:
            original_turnout = _turnout_state(project, end)
            collapsed[end] = {'end': end, 'former_turnout': original_turnout, 'retained_edge_id': kept[0][1]}
    report = _retire_crossing_network(project, sorted(retired), isolated, connectors, expected,
                                     reviewed_instrument_ends=instrument_ends)
    return retired, report, collapsed, connectors


def _verify_retirement(checked, report, collapsed):
    for row in report:
        ids = {*row['removed_edge_ids'], *row['removed_end_ids'], *row['removed_safety_element_ids']}
        need(ids.isdisjoint(checked.byid[row['document']]), 'A retired mixed-junction model survived cold read')
    for key, row in collapsed.items():
        end = checked.model(key)
        need(_incident_edges(end, key[0]) == [(key[0], row['retained_edge_id'])]
             and end.contents[10].value is None and end.contents[22].value == 0
             and float(end.contents[21].value) == row['former_turnout']['switch_time_s'],
             'A former turnout did not collapse to the exact surviving native Edge')


def reroute_mixed_junction_track_spans(documents, document_paths, dest_catalog, target, operation):
    crossings = operation['crossings']
    local_alignments = operation['local_alignments']
    need(crossings and local_alignments and len(crossings) + len(local_alignments) <= 12,
         'A mixed junction requires native crossing and local alignments, bounded to twelve in total')
    project = project_from(documents, document_paths, dest_catalog)
    before = _movement_manifest(project)
    old_continuations = _continuations(project)
    dependency = _dependency(crossings, local_alignments, operation)
    selected_edges = {(item['document'], item['edge_id']) for field in ('old_edges', 'replacement_edges')
                      for item in dependency[field]}
    selected_documents = {document for document, _ in selected_edges}
    need(target in selected_documents and selected_documents <= set(documents), 'Review an exact participating worksheet')
    links = dependency['exclusion_link_rebindings']
    detached, final_exclusions = prepare_exclusions(project, dependency)
    retained_exclusions = retain_crossing_exclusions(project, dependency, detached, final_exclusions)
    exclusion_maps = {name: sorted((final_exclusions[name] if name in final_exclusions else _links(_edges(project, name))).items())
                      for name in selected_documents}
    old_reviews = _exclusion_review(links, 'old', retained_exclusions)
    new_reviews = _exclusion_review(links, 'new', retained_exclusions)
    instruments, former_observers, final_observers = prepare_instrument_edge_rebindings(
        project, dependency, operation.get('instrument_edge_rebindings', ()))
    original_instrument_ends = relocated_instrument_ends(instruments)
    final_instrument_ends = relocated_instrument_ends(instruments, after=True)
    selected, anchors, allowed_documents = defaultdict(list), {}, defaultdict(set)

    planned_crossings, retained_profiles = [], []
    for index, row in enumerate(crossings):
        report, substitutions, boundary, review = _inspect_alignment(
            project, row, old_reviews, reviewed_instruments=former_observers, reviewed_instrument_ends=original_instrument_ends)
        oriented = {key: (old, new) for key, (old, new, _) in substitutions.items()}
        keys = _select_routes(row, before, old_continuations, selected, anchors, oriented, report['new_length_m'], review, index)
        planned_crossings.append((report, boundary, keys))
        _, _, _, reverse_profile = _walk_crossing(
            project, report['terminal_end'], row['old_edges'][::-1], old_reviews, reviewed_instruments=former_observers,
            reviewed_instrument_ends=original_instrument_ends)
        retained_profiles.append({'start_end': report['start_end'], 'terminal_end': report['terminal_end'],
                                  'new_pair': report['old_pair'], 'new_profile': report['old_profile'],
                                  'new_reverse_profile': reverse_profile})
    local_reports = []
    for index, row in enumerate(local_alignments, start=len(crossings)):
        document = row['document']
        oriented, review, report = _alignment(project, document, row, old_reviews.get(document, ()),
                                              observers=former_observers.get(document), instrument_ends=original_instrument_ends)
        keys = _select_routes(row, before, old_continuations, selected, anchors, oriented,
                              report['replacement_length_m'], review, index)
        local_reports.append(report)
        for key in keys:
            allowed_documents[key].add(document)

    expected, choices, distances = _compile_plans(project, before, selected)
    witnesses = _check_witnesses(operation['witness_itineraries'], before, expected, choices,
                                len(crossings) + len(local_alignments))
    berths = _selected_berths(project, choices)
    validate_exclusion_movements(project, selected_documents, final_exclusions, links, expected,
                                 {key: expected[key] for key in choices})
    transferred_blocks = {(row['document'], edge['old_edge_id']) for row in operation.get('track_incident_rebindings', ())
                          for edge in row['edge_rebindings']}
    if transferred_blocks:
        need(all(transferred_blocks.isdisjoint(_route_edge_keys(project, movement)) for key, movement in expected.items()
                 if key[0] in ('route', 'shunting')),
             'A track blockage cannot leave an original Edge that a final Route or Shunting still traverses')
    protection = {name: _protection_manifest(project, name) for name in selected_documents}
    old_only, _ = crossing_edge_changes(dependency)
    kept = {key: _route_edge_keys(project, movement) for key, movement in before.items() if key[0] == 'route' and key not in selected}
    retained = _retained_routes(project, kept, old_only, protection)
    occupation = {name: native_occupation_groups.records(project.roots[name], name) for name in selected_documents}
    groups, extensions = _migrate_occupation(project, dependency, selected, expected)
    changes, local_changes, affected, final_continuations = _apply_route_fragments(
        project, planned_crossings, allowed_documents, selected, anchors, old_continuations, expected, protection)
    itineraries = {key: (_metres(before[key]), spans) for key, spans in distances.items() if key[0] == 'itinerary' and spans}
    margins = map_margin_span_profiles(project, itineraries, operation.get('map_itinerary_safety_margins') is True)
    instrument_changes = apply_instrument_edge_rebindings(project, instruments)
    write_exclusions(project, detached)
    crossing_reports = [report for report, _, _ in planned_crossings]
    reviewed_end_objects = {project.model((row.document, row.new_end_id)) for row in instruments}
    retired, retirement, collapsed, retired_pairs = _mixed_retirement(
        project, operation, crossing_reports, local_reports, old_only, expected, exclusion_maps, reviewed_end_objects)
    write_exclusions(project, final_exclusions)
    turnout_updates = operation.get('turnout_updates')
    turnouts = _update_turnouts(project_from(documents, document_paths, dest_catalog), project, operation,
                               selected_edges) if turnout_updates else {}
    affected.update(detached)
    affected.update(row['document'] for row in [*margins, *instrument_changes])
    affected.update(row['document'] for row in retirement)
    affected.update(row['after']['document'] for row in [*groups, *extensions])
    affected.update(key[0] for key in turnouts)
    staged = dict(documents)
    _save_documents(staged, project, affected)
    checked = project_from(staged, document_paths, dest_catalog)
    need(_movement_manifest(checked) == expected, 'Cold read changed the planned native movement graph or exact references')
    need(_continuations(checked) == final_continuations, 'Cold read changed an unreviewed native continuation owner')
    for name, expected_protection in protection.items():
        need(_protection_manifest(checked, name) == expected_protection, 'Cold read changed unreviewed Route protection')
    for key, review in turnouts.items():
        need(_turnout_state(checked, key) == review['after'], 'Cold read changed the exact reviewed turnout state')
    retained_profiles = [step for step in retained_profiles if retired.isdisjoint(
        (row['document'], row['edge_id']) for row in step['new_profile'])]
    _verify_final_crossing_profiles(checked, [*crossing_reports, *retained_profiles], new_reviews, turnouts,
                                    reviewed_instruments=final_observers, reviewed_instrument_ends=final_instrument_ends,
                                    collapsed_turnouts=collapsed)
    _verify_alignments(checked, local_reports, new_reviews, turnouts=turnouts, observers=final_observers,
                       instrument_ends=final_instrument_ends, retired_edges=retired, collapsed_turnouts=collapsed)
    _verify_retirement(checked, retirement, collapsed)
    verify_transfers(checked, exclusion_maps, [*groups, *extensions])
    _verify_occupation(checked, occupation, [*groups, *extensions])
    verify_instrument_edge_rebindings(checked, instruments)
    verify_margin_profiles(checked, margins)
    stops = _verify_berths(berths, _selected_berths(checked, choices))
    outputs = {name: staged[name] for name in sorted(affected) if staged[name] != documents[name]}
    return outputs, {
        'action': operation['action'], 'document': target, 'mixed_junction': True, 'changed_documents': list(outputs),
        'crossing_edits': crossing_reports, 'local_alignments': local_reports, 'witness_itineraries': witnesses,
        'crossing_rewritten_routes': changes, 'local_rewritten_routes': local_changes,
        'selected_station_stops': stops, 'retained_alignment_routes': retained, 'movement_count_checked': len(before),
        'movement_count_changed': len(choices), 'mapped_safety_margin_profiles': margins, 'turnout_updates': list(turnouts.values()),
        'retirement': retirement, 'retired_connector_pairs': retired_pairs,
        'retired_turnouts': list(collapsed.values()), 'original_track_chains_retained': not retired,
        'continuation_ownership_verified': True,
        'destination_catalog_unchanged': True, 'native_execution_tested': False,
        'dependency_transfers': {'verified_exclusion_maps': exclusion_maps, 'occupation_group_rebindings': groups,
                                 'retained_exclusion_links': list(dependency['retained_exclusion_links']),
                                 'occupation_group_extensions': extensions, 'instrument_edge_rebindings': instrument_changes,
                                 'native_readback_verified': True},
    }
