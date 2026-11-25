"""Select existing one-worksheet throat alignments by exact native Route identity."""

from collections import defaultdict

from . import native_occupation_groups, path_functions
from .multi_document.core import need
from .route_edit_tools import _route_shape, _zone_fragment_ids
from .saved_cross_document_reroute import _anchor_reviews, _update_fragment, _verify_joined_zone
from .saved_crossing_dependencies import (
    crossing_edge_changes, extend_crossing_occupation_groups, prepare_exclusions, retain_crossing_exclusions,
    transfer_occupation_groups, validate_exclusion_movements, verify_transfers, write_exclusions,
)
from .saved_geometry import _movement_manifest, project_from
from .saved_junction_reroute import (
    _check_witnesses, _compose, _exclusion_review, _identity, _metres, _planned_movement, _retained_routes,
    _route_edge_keys, _selected_berths, _verify_berths,
)
from .saved_multi_document_reroute import _save_documents
from .saved_track_replacement import _protection_manifest
from .saved_track_reroute import _walk_span
from .saved_used_edge_profile import map_margin_span_profiles, verify_margin_profiles


def _alignment(project, document, row, exclusions, *, observers=None, instrument_ends=()):
    old_ids = row['old_edge_ids']
    new_ids = row['replacement_edge_ids']
    need(len(set(old_ids)) == len(old_ids) and len(set(new_ids)) == len(new_ids) and set(new_ids) - set(old_ids),
         'Review nonrepeating track sequences and a genuinely different alternative')
    start = (document, row['start_end_id'])
    review = {'reviewed_exclusions': exclusions, 'reviewed_instruments': observers, 'reviewed_instrument_ends': instrument_ends}
    old, old_length, old_profile = _walk_span(project, document, start, old_ids, **review)
    new, new_length, new_profile = _walk_span(project, document, start, new_ids, **review)
    terminal = old[-1]
    need(old != new and terminal == new[-1], 'The alternative must reach the same original directional terminal End')
    first_area = project.model(start).contents[12].value
    need(first_area is None or first_area is not project.model(terminal).contents[12].value,
         'Use a station stopping-area edit for a span within one saved platform area')
    need(new_length == row['expected_replacement_length_m'] and row['expected_replacement_safety_element_ids'] == [
        item['safety_element_id'] for item in new_profile], 'Review the exact replacement distance and ordered Safety Elements')
    old_back, _, old_reverse = _walk_span(project, document, terminal, old_ids[::-1], **review)
    new_back, _, new_reverse = _walk_span(project, document, terminal, new_ids[::-1], **review)
    need(old_back[-1] == new_back[-1] == start, 'Both physical branches must also rejoin in reverse')
    oriented = {start: (old, new), terminal: (old_back, new_back)}
    anchors = _anchor_reviews(row.get('route_anchor_rebindings', ()), set(old + old_back), set(new + new_back))
    return oriented, anchors, {'start_end': start, 'terminal_end': terminal, 'old_profile': old_profile,
                                'replacement_profile': new_profile, 'old_reverse_profile': old_reverse,
                                'replacement_reverse_profile': new_reverse, 'old_length_m': old_length,
                                'replacement_length_m': new_length}


def _selected_spans(project, original, selected):
    positions = [0]
    for first, last in zip(original, original[1:]):
        length = project.model(project.edge_between(first, last)).contents[9].values[1]
        positions.append(positions[-1] + length)
    plans = []
    for index, oriented, length in selected:
        matches = []
        for first, direction in enumerate(original[:-1]):
            alternative = oriented.get(project.actual_related(direction))
            if alternative is not None:
                old, new = alternative
                last = first + len(old)
                if tuple(original[first + 1:last + 1]) == old:
                    matches.append((first, last, new, length, index))
        need(len(matches) == 1, 'Each Route selection must traverse its complete former alignment exactly once')
        plans.extend(matches)
    plans.sort()
    need(all(left[1] <= right[0] for left, right in zip(plans, plans[1:])),
         'Reviewed alignments overlap in the same original Route')
    revised, distances, cursor = [], [], 0
    for first, last, new, length, _ in plans:
        revised.extend(original[cursor:first + 1])
        revised.extend(new)
        cursor = last + 1
        if length != positions[last] - positions[first]:
            distances.append((positions[first], positions[last], length))
    revised.extend(original[cursor:])
    need(revised[0] == original[0] and revised[-1] == original[-1], 'Reroute must retain both exact native Route termini')
    return revised, distances, positions[-1]


def _continuations(project):
    return {
        _identity('route', row['source_document'], row['route']): (
            (row['source_document'], row['source_connector']), (row['target_document'], row['target_connector']),
        ) for row in project.continuations
    }


def _collect_route_anchors(anchors, reviewed_anchors):
    for key, mapping in reviewed_anchors.items():
        reviewed = anchors.setdefault(key, {})
        need(reviewed.keys().isdisjoint(mapping) and set(reviewed.values()).isdisjoint(mapping.values()),
             'Review each moved release or slow-zone anchor once per native Route fragment')
        reviewed.update(mapping)


def _compile_plans(project, before, selected):
    expected, choices, distances = before.copy(), {}, {}
    for key, spans in selected.items():
        revised, offsets, original_length = _selected_spans(project, before[key][0], spans)
        need(original_length == _metres(before[key]), 'Original Route distance differs from its exact track sequence')
        delta = sum(length - (last - first) for first, last, length in offsets)
        expected[key] = _planned_movement(project, before[key], revised, delta)
        distances[key] = offsets
        choices[key] = {index for index, _, _ in spans}
    for kind, leaf_kind in (('path', 'route'), ('itinerary', 'path')):
        for key, movement in before.items():
            if key[0] == kind:
                compiled = _compose(project, leaf_kind, movement, before, expected, distances, choices)
                if compiled is not None:
                    expected[key], distances[key], choices[key] = compiled
    return expected, choices, distances


def _rewrite_routes(project, allowed_documents, expected, section_keys, anchors, continuations, protection):
    changes = []
    for key in section_keys:
        _, owner, identity = key
        sequence = expected[key][0]
        primary = project.owned(owner, 'OTRoute', identity)
        continuation = continuations.get(key)
        if continuation is None:
            need(all(end[0] == owner[0] for end in sequence), 'A local Route cannot acquire a continuation')
            fragments = [(owner, primary, sequence, False)]
        else:
            sender, receiver = continuation
            division = next(i for i, end in enumerate(sequence) if end[0] != owner[0])
            left, right = sequence[:division], sequence[division:]
            need(project.related(left[-1]) == sender and project.block_end(sender) == receiver
                 and all(end[0] == receiver[0] for end in right), 'Local reroute changed a reviewed native connector boundary')
            fragments = [(owner, primary, left, True), (receiver, project.owned(receiver, 'OTRoute', identity), right, False)]
        zones = []
        zones_changed = False
        changed_fragments = 0
        for fragment_owner, route, nodes, is_primary in fragments:
            old = [project.key(end) for end in path_functions.mutable_array(route.contents[0].value)]
            if old == nodes:
                zones.append(_zone_fragment_ids(route, _route_shape(route)))
                continue
            document = fragment_owner[0]
            need(document in allowed_documents[key], 'Local reroute changed a fragment on a worksheet outside this Route review')
            settings, release, zone, changed = _update_fragment(
                project, fragment_owner, route, nodes, {}, anchors.pop((fragment_owner, identity), {}),
                has_continuation=is_primary,
            )
            need(changed, 'The revised Route fragment did not change its directional track sequence')
            current = protection[document][fragment_owner, 'OTRoute', identity]
            for field in ('release_group_end_ids', 'slow_speed_zone_end_ids', 'slow_speed_zone_fragment_end_ids'):
                current[field] = settings[field]
            zones.append(settings['slow_speed_zone_fragment_end_ids'])
            zones_changed |= bool(zone)
            changed_fragments += 1
            changes.append({'route_owner': owner, 'fragment_owner': fragment_owner, 'identity': identity,
                            'before_end_ids': [end[1] for end in old], 'after_end_ids': [end[1] for end in nodes],
                            'rebound_release_boundaries': release, 'rebound_slow_speed_zone_ends': zone})
        need(changed_fragments > 0, 'A reviewed local Route must revise its native fragment')
        if zones_changed and continuation:
            _verify_joined_zone(sequence, *zones, fragments[0][0][0], fragments[1][0][0])
    need(not anchors, 'Every explicit native Route anchor review must match its affected fragment')
    return changes


def _verify_alignments(checked, reports, exclusions, *, turnouts=None, observers=None, instrument_ends=(),
                       retired_edges=(), collapsed_turnouts=()):
    for report in reports:
        document = report['start_end'][0]
        for label in ('old_profile', 'replacement_profile', 'old_reverse_profile', 'replacement_reverse_profile'):
            reverse = label.endswith('reverse_profile')
            start, terminal = (report['terminal_end'], report['start_end']) if reverse else (report['start_end'], report['terminal_end'])
            profile = report[label]
            if any((document, row['edge_id']) in retired_edges for row in profile):
                need(label.startswith('old_'), 'A final local alignment contains a retired Edge')
                continue
            ends, _, actual = _walk_span(checked, document, start, [row['edge_id'] for row in profile],
                                        reviewed_exclusions=exclusions.get(document, ()),
                                        reviewed_instruments=(observers or {}).get(document),
                                        reviewed_instrument_ends=instrument_ends)
            revised = []
            for row in profile:
                switch = row['switch']
                if switch is not None:
                    key = document, switch['end_id']
                    reviewed = (turnouts or {}).get(key)
                    if reviewed is not None:
                        desired = reviewed['after']
                        switch = {**switch, 'switch_time_s': desired['switch_time_s'],
                                  'default_leg': desired['edge_ids'].index(desired['default_edge_id']) + 1}
                    elif key in collapsed_turnouts:
                        switch = None
                revised.append({**row, 'switch': switch})
            need(ends[-1] == terminal and actual == revised, 'Cold read changed a retained local alignment or turnout profile')
            report[label] = actual


def _migrate_occupation(project, dependency, requested_routes, expected):
    if not dependency['occupation_group_rebindings'] and not dependency['occupation_group_extensions']:
        return [], []
    final_route_edges = {edge for key, movement in expected.items() if key[0] == 'route'
                         for edge in _route_edge_keys(project, movement)}
    if dependency['occupation_group_rebindings']:
        remaining = final_route_edges | {edge for key, movement in expected.items() if key[0] == 'shunting'
                                         for edge in _route_edge_keys(project, movement)}
        need(all((row['document'], item['old_edge_id']) not in remaining
                 for row in dependency['occupation_group_rebindings'] for item in row['edge_rebindings']),
             'An occupation transfer cannot remove a monitor Edge still traversed by a final Route or Shunting')
    edited_edges = {edge for key in requested_routes for edge in _route_edge_keys(project, expected[key])}
    groups = transfer_occupation_groups(project, dependency)
    extensions = extend_crossing_occupation_groups(project, dependency, final_route_edges, edited_edges)
    return groups, extensions


def _verify_occupation(checked, before, groups):
    updated = {(row['after']['document'], row['after']['name']): row['after'] for row in groups}
    for document, rows in before.items():
        need(native_occupation_groups.records(checked.roots[document], document) ==
             [updated.get((document, row['name']), row) for row in rows],
             'Cold read changed an unreviewed occupation monitor or monitor order')


def reroute_local_junction_track_spans(documents, document_paths, dest_catalog, document, operation):
    project = project_from(documents, document_paths, dest_catalog)
    before = _movement_manifest(project)
    requests = operation['alignments']
    dependency = {
        'old_edges': [{'document': document, 'edge_id': edge_id} for row in requests for edge_id in row['old_edge_ids']],
        'replacement_edges': [{'document': document, 'edge_id': edge_id} for row in requests for edge_id in row['replacement_edge_ids']],
        **{key: operation.get(key, ()) for key in ('exclusion_link_rebindings', 'retained_exclusion_links',
           'occupation_group_rebindings', 'occupation_group_extensions')},
    }
    links = dependency['exclusion_link_rebindings']
    detached, final_exclusions = prepare_exclusions(project, dependency)
    retained_exclusions = retain_crossing_exclusions(project, dependency, detached, final_exclusions)
    old_exclusions = _exclusion_review(links, 'old', retained_exclusions).get(document, ())
    final_review = _exclusion_review(links, 'new', retained_exclusions).get(document, ())
    selected, anchors, reports = defaultdict(list), {}, []
    for index, row in enumerate(requests):
        oriented, reviewed_anchors, report = _alignment(project, document, row, old_exclusions)
        reports.append(report)
        keys = [_identity('route', item['document'], item) for item in row['routes']]
        need(keys and len(set(keys)) == len(keys) and all(key in before for key in keys),
             'Select each exact primary Route once per local alignment')
        for key in keys:
            selected[key].append((index, oriented, report['replacement_length_m']))
        _collect_route_anchors(anchors, reviewed_anchors)

    expected, choices, distances = _compile_plans(project, before, selected)
    witnesses = _check_witnesses(operation['witness_itineraries'], before, expected, choices, len(requests))
    validate_exclusion_movements(project, {document}, final_exclusions, links, expected,
                                 {key: expected[key] for key in choices})

    protection = {document: _protection_manifest(project, document)}
    old_only, _ = crossing_edge_changes(dependency)
    kept_routes = {key: _route_edge_keys(project, movement) for key, movement in before.items()
                   if key[0] == 'route' and key not in choices}
    retained = _retained_routes(project, kept_routes, old_only, protection)
    berths = _selected_berths(project, choices)
    occupation = {document: native_occupation_groups.records(project.roots[document], document)}
    groups, extensions = _migrate_occupation(project, dependency, selected, expected)
    continuations = _continuations(project)
    changes = _rewrite_routes(project, {key: {document} for key in selected}, expected, selected, anchors,
                              continuations, protection)
    itineraries = {key: (_metres(before[key]), rows) for key, rows in distances.items() if key[0] == 'itinerary' and rows}
    margins = map_margin_span_profiles(project, itineraries, operation.get('map_itinerary_safety_margins') is True)
    write_exclusions(project, detached)
    write_exclusions(project, final_exclusions)

    affected = {document, *(row['document'] for row in margins)}
    staged = dict(documents)
    _save_documents(staged, project, affected)
    checked = project_from(staged, document_paths, dest_catalog)
    need(_movement_manifest(checked) == expected, 'Cold read changed native movements or exact Path and Itinerary references')
    need(_continuations(checked) == continuations, 'Cold read changed native Route continuation ownership')
    for name, expected_protection in protection.items():
        need(_protection_manifest(checked, name) == expected_protection, 'Cold read changed unreviewed Route protection')
    _verify_alignments(checked, reports, {document: final_review})
    verified_berths = _verify_berths(berths, _selected_berths(checked, choices))
    exclusion_maps = {name: sorted(values.items()) for name, values in final_exclusions.items()}
    verify_transfers(checked, exclusion_maps, [*groups, *extensions])
    _verify_occupation(checked, occupation, [*groups, *extensions])
    verify_margin_profiles(checked, margins)
    outputs = {name: staged[name] for name in sorted(affected) if staged[name] != documents[name]}
    return outputs, {
        'action': operation['action'], 'document': document, 'changed_documents': list(outputs),
        'witness_itineraries': witnesses, 'alignments': reports, 'rewritten_routes': changes,
        'retained_alignment_routes': retained, 'selected_station_stops': verified_berths,
        'movement_count_checked': len(before), 'movement_count_changed': len(choices),
        'mapped_safety_margin_profiles': margins, 'original_track_chains_retained': True,
        'dependency_transfers': {'verified_exclusion_maps': exclusion_maps, 'occupation_group_rebindings': groups,
                                 'retained_exclusion_links': list(dependency['retained_exclusion_links']),
                                 'occupation_group_extensions': extensions, 'native_readback_verified': True},
        'continuation_ownership_verified': True, 'destination_catalog_unchanged': True, 'native_execution_tested': False,
    }
