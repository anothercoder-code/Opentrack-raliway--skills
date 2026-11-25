"""Reroute independently selected native movements through a shared junction."""

from . import route_factory, writer
from .graph_references import incoming_counts
from .multi_document.core import ident, need
from .network_operating_plan import route_trace
from .route_edit_tools import _indications
from .saved_cross_document_reroute import (
    _edge_key, _end_key, _inspect_alignment, _retire_crossing_network, _rewrite_cross_routes, _walk_crossing,
)
from .saved_crossing_dependencies import (
    crossing_edge_changes, exclusion_reviews, extend_crossing_occupation_groups, prepare_exclusions,
    retain_crossing_exclusions, transfer_occupation_groups,
    validate_exclusion_movements, verify_transfers, write_exclusions,
)
from .saved_crossing_instruments import (
    apply_instrument_edge_rebindings, prepare_instrument_edge_rebindings, relocated_instrument_ends, verify_instrument_edge_rebindings,
)
from .saved_geometry import _movement_geometry, _movement_manifest, project_from
from .saved_multi_document_reroute import (
    _save_documents, _station_markers, _turnout_state, _update_turnouts, _verify_final_crossing_profiles,
)
from .saved_track_replacement import _protection_manifest
from .saved_track_reroute import _rebind_sequence
from .saved_used_edge_profile import map_margin_span_profiles, verify_margin_profiles


def _identity(kind, document, ref):
    start = ref['start_id']
    return kind, (document, start), (ref['name'], ref['array_id'], start)


def _metres(movement):
    return sum(distance for _, distance in movement[2])


def _route_plans(project, request, before, substitutions, replacement_length, choices, choice):
    changes, spans = {}, {}
    for ref in request['routes']:
        key = _identity('route', ref['document'], ref)
        need(key in before and key not in choices, 'Select each exact existing primary Route only once')
        original = before[key][0]
        revised, distance, occurrence = _rebind_sequence(project, original, substitutions)
        need(len(occurrence) == 1 and revised[0] == original[0] and revised[-1] == original[-1],
             'Each selected Route must use the complete former crossing once and keep both directional termini')
        first, last = occurrence[0]
        changes[key] = _planned_movement(project, before[key], revised, replacement_length - (last - first))
        if replacement_length != last - first:
            spans[key] = [(first, last, replacement_length)]
        need(distance == _metres(before[key]), 'Original Route distance disagrees with the movement graph')
        choices[key] = {choice}
    return changes, spans


def _planned_movement(project, original, nodes, distance_delta):
    need(len(set(nodes)) == len(nodes), 'Replacement revisits a directional End')
    need(_station_markers(project, nodes) == _station_markers(project, original[0]),
         'Replacement changes the order or occurrence of station markers')
    movement = nodes, original[1], _movement_geometry(project, nodes, check_safety=True)
    distance = _metres(movement)
    need(0 < distance <= 2147483647 and distance == _metres(original) + distance_delta,
         'Final movement distance differs from the reviewed alignment')
    return movement


def _compose(project, leaf_kind, original, before, expected, spans, choices):
    if leaf_kind == 'route' and any(ref.get('kind') == 'shunting' for _, ref in original[1]):
        return None
    keys = [_identity(leaf_kind, document, ref) for document, ref in original[1]]
    coverage = set().union(*(choices.get(key, set()) for key in keys))
    if not coverage:
        return None
    nodes, positions = [], []
    offset = 0
    for key in keys:
        chain = expected[key][0]
        need(not nodes or nodes[-1] == chain[0], 'Replacement disconnects native movement references')
        nodes.extend(chain[1:] if nodes else chain)
        positions.extend((offset + first, offset + last, length) for first, last, length in spans.get(key, ()))
        offset += _metres(before[key])
    need(offset == _metres(original), 'Original movement distance disagrees with its saved references')
    delta = sum(length - (last - first) for first, last, length in positions)
    return _planned_movement(project, original, nodes, delta), positions, coverage


def _check_witnesses(witnesses, before, expected, choices, count):
    itinerary_keys = {key[2][0]: key for key in before if key[0] == 'itinerary'}
    covered = set()
    result = {}
    for name, target in witnesses.items():
        key = itinerary_keys.get(name)
        used = choices.get(key, set())
        need(used and _metres(expected[key]) == target,
             f'Witness Itinerary {name!r} must use a reviewed branch and reach its exact expected distance')
        covered.update(used)
        result[name] = {'before_length_m': _metres(before[key]), 'after_length_m': target,
                        'crossing_indices': sorted(used)}
    need(covered == set(range(count)), 'Each reviewed crossing needs a saved witness Itinerary')
    return result


def _exclusion_review(rows, side, retained):
    review = exclusion_reviews(rows, side)
    for document, pairs in retained.items():
        review[document].update(pairs)
    return review


def _route_edge_keys(project, movement):
    nodes = movement[0]
    return [project.edge_between(a, b) for a, b in zip(nodes, nodes[1:])]


def _selected_berths(project, choices):
    names = {key[2][0] for key in choices if key[0] == 'itinerary'}
    result = {}
    for itinerary in project.dests:
        name = ident(itinerary)[0]
        if name not in names:
            continue
        visits = route_trace(project, itinerary)['visits']
        rows = []
        for visit in visits:
            row = {key: visit[key] for key in ('station_sign', 'end_key', 'incoming_track_id', 'stop_edge_key',
                   'stop_edge_length_m', 'stopping_area_edge_keys', 'stopping_area_length_m', 'halt_stop_issue')}
            halt = visit.get('halt_platform')
            if halt is not None:
                row['halt_platform'] = {key: halt[key] for key in ('length_m', 'markers', 'exit')}
                row['halt_platform']['start_relative_m'] = halt['start_distance_m'] - visit['distance_m']
            rows.append({'reference_distance_m': visit['distance_m'], 'profile': row})
        result[name] = rows
    return result


def _verify_berths(before, after):
    need(before.keys() == after.keys(), 'Cold read lost a reviewed selected Itinerary')
    result = {}
    for name, first in before.items():
        last = after[name]
        need([row['profile'] for row in first] == [row['profile'] for row in last],
             f'The reviewed alternative changes a directed station stop or berth in Itinerary {name!r}')
        result[name] = [{**new['profile'], 'before_reference_distance_m': old['reference_distance_m'],
                         'after_reference_distance_m': new['reference_distance_m']}
                        for old, new in zip(first, last, strict=True)]
    return result


def _retained_routes(project, kept_routes, old_only, protection):
    retained = []
    for (_, owner, route_id), edges in kept_routes.items():
        if old_only.isdisjoint(edges):
            continue
        reference = {'name': route_id[0], 'array_id': route_id[1], 'start_id': route_id[2]}
        owners = [owner] + [(row['target_document'], row['target_connector']) for row in project.continuations
                            if row['source_document'] == owner[0] and row['route'] == reference]
        for document in {fragment[0] for fragment in owners}.difference(protection):
            protection[document] = _protection_manifest(project, document)
        retained.append({'route_owner': owner, 'identity': route_id, 'directed_edge_keys': edges,
                         'fragments': [{'owner': fragment, 'protection': protection[fragment[0]][
                             (fragment, 'OTRoute', route_id)]} for fragment in owners]})
    return retained


def _retire(project, operation, alignments, retired_edges, expected, reviewed_instrument_ends):
    isolated = [_end_key(ref) for ref in operation.get('retire_isolated_ends', ())]
    if not operation.get('retire_original'):
        need(not isolated, 'Retiring isolated Ends requires explicit junction retirement')
        return []
    need(retired_edges, 'The junction has no old-only track to retire')
    old_pairs = {tuple(sorted(row['old_pair'])) for row, _, _, _ in alignments}
    new_pairs = {tuple(sorted(row['new_pair'])) for row, _, _, _ in alignments}
    terminals = {end for row, _, _, _ in alignments for end in (row['start_end'], row['terminal_end'])}
    protected = {end for pair in old_pairs | new_pairs for end in pair} | terminals
    protected |= {project.related(end) for end in protected}
    old_interior = {vertex for _, substitutions, _, _ in alignments for old, _, _ in substitutions.values()
                    for vertex in old[:-1]}
    eligible = (old_interior | {project.related(end) for end in old_interior}) - protected
    need(set(isolated) <= eligible, 'Select only isolated interior End pairs from the reviewed former crossings')
    return _retire_crossing_network(project, sorted(retired_edges), isolated, sorted(old_pairs - new_pairs), expected,
                                    reviewed_instrument_ends=reviewed_instrument_ends)


def _refresh_profiles(project, reports, final_reviews, instrument_observers, instrument_ends):
    for row in reports:
        for label, start, terminal, pair in (
            ('new_profile', row['start_end'], row['terminal_end'], tuple(row['new_pair'])),
            ('new_reverse_profile', row['terminal_end'], row['start_end'], tuple(reversed(row['new_pair']))),
        ):
            arrivals, length, actual_pair, profile = _walk_crossing(
                project, start, row[label], final_reviews, reviewed_instruments=instrument_observers,
                reviewed_instrument_ends=instrument_ends)
            need(arrivals[-1] == terminal and actual_pair == pair and length == row['new_length_m'],
                 'Final crossing topology or length differs from the reviewed branch')
            fields = ('document', 'edge_id', 'length_m', 'safety_element_id', 'gradient_per_mille', 'radius_m', 'speeds_kmh')
            need(all(all(a[field] == b[field] for field in fields)
                     for a, b in zip(row[label], profile, strict=True)),
                 'Final crossing physics or safety elements differ from the reviewed branch')
            row[label] = profile


def _commit_continuations(project, pending, protection):
    moved = [(fragment, old[0], new[0]) for fragment, old, new, _ in pending if old != new]
    departing = {}
    arriving = {}
    for fragment, old, new in moved:
        departing.setdefault(old, set()).add(fragment)
        arriving.setdefault(new, []).append(fragment)
    owners = departing.keys() | arriving.keys()
    counts = {name: incoming_counts(project.roots[name]) for name in {owner[0] for owner in owners}}
    planned = {}
    for owner in sorted(owners):
        holder = project.model(owner).contents[15].value
        current = route_factory.wrapper(holder, 'OTRouteList')
        array = holder.contents[0].value
        refs = counts[owner[0]]
        leaving = departing.get(owner, set())
        need(refs[id(holder)] == refs[id(array)] == 1, 'Continuation owner Route lists are shared')
        need(leaving <= set(current) and all(refs[id(part)] == 1 + len(_indications(part)[1]) for part in leaving),
             'A continuation has other direct saved references or no longer belongs to its reviewed connector')
        revised = [part for part in current if part not in leaving] + arriving.get(owner, [])
        identities = [ident(part) for part in revised]
        need(len({item[0] for item in identities}) == len({item[1:] for item in identities}) == len(identities),
             'Final receiving connector has an ambiguous continuation name or ID')
        planned[owner] = array, revised
    for array, revised in planned.values():
        writer.set_elements(array, revised)
    for _, old, _, _ in pending:
        protection[old[0][0]].pop(old)
    for _, _, new, settings in pending:
        protection[new[0][0]][new] = settings


def reroute_junction_track_spans(documents, document_paths, dest_catalog, target, operation):
    project = project_from(documents, document_paths, dest_catalog)
    before = _movement_manifest(project)
    expected, choices, spans = before.copy(), {}, {}
    requests = operation['crossings']
    single_crossing = len(requests) == 1
    if single_crossing:
        need(requests[0].get('connector_policy') == 'retain_pair' and len(requests[0]['routes']) == 1
             and not operation.get('retire_original') and not operation.get('retire_isolated_ends'),
             'A single junction edit requires one exact Route, the original connector pair and both alignments retained')
    dependency = {field: [edge for row in requests for edge in row[field]] for field in ('old_edges', 'replacement_edges')}
    dependency['crossings'] = requests
    links = operation.get('exclusion_link_rebindings', ())
    dependency.update(exclusion_link_rebindings=links, occupation_group_rebindings=operation.get('occupation_group_rebindings', ()),
                      retained_exclusion_links=operation.get('retained_exclusion_links', ()),
                      occupation_group_extensions=operation.get('occupation_group_extensions', ()))
    detached, final_exclusions = prepare_exclusions(project, dependency)
    retained_exclusions = retain_crossing_exclusions(project, dependency, detached, final_exclusions)
    instrument_plan, former_observers, final_observers = prepare_instrument_edge_rebindings(
        project, dependency, operation.get('instrument_edge_rebindings', ()))
    old_review = _exclusion_review(links, 'old', retained_exclusions)
    final_review = _exclusion_review(links, 'new', retained_exclusions)
    alignments, route_changes = [], []
    for index, request in enumerate(requests):
        alignment = _inspect_alignment(project, request, old_review, reviewed_instruments=former_observers,
                                       reviewed_instrument_ends=relocated_instrument_ends(instrument_plan))
        report, substitutions, _, _ = alignment
        movements, route_spans = _route_plans(project, request, before, substitutions,
                                             report['new_length_m'], choices, index)
        alignments.append(alignment)
        route_changes.append({key: value[0] for key, value in movements.items()})
        expected.update(movements)
        spans.update(route_spans)

    crossing_documents = {end[0] for report, _, _, _ in alignments for end in report['old_pair']}
    need(target in crossing_documents, 'Target document must participate in the junction')
    for kind, leaf_kind in (('path', 'route'), ('itinerary', 'path')):
        for key, original_movement in before.items():
            if key[0] != kind:
                continue
            compiled = _compose(project, leaf_kind, original_movement, before, expected, spans, choices)
            if compiled is not None:
                expected[key], spans[key], choices[key] = compiled
    witnesses = _check_witnesses(operation['witness_itineraries'], before, expected, choices, len(requests))
    validate_exclusion_movements(project, crossing_documents, final_exclusions, links, expected,
                                 {key: expected[key] for key in choices})

    protection = {name: _protection_manifest(project, name) for name in crossing_documents}
    kept_routes = {}
    if single_crossing or dependency['occupation_group_extensions']:
        kept_routes = {key: _route_edge_keys(project, value) for key, value in before.items()
                       if key[0] == 'route' and key not in choices}
    retained_edges = set().union(*kept_routes.values())
    retained = []
    berths = {}
    if single_crossing:
        old_only, _ = crossing_edge_changes(dependency)
        retained = _retained_routes(project, kept_routes, old_only, protection)
        need(retained, 'A single selected Route requires an unedited saved Route remaining on the original physical alignment')
        need(all((row['document'], item['old_edge_id']) not in retained_edges
                 for row in dependency['occupation_group_rebindings'] for item in row['edge_rebindings']),
             'An occupation transfer cannot remove a monitor Edge still used by an unedited saved Route')
        berths = _selected_berths(project, choices)
    extensions = []
    if dependency['occupation_group_extensions']:
        edited_edges = {edge for key in choices if key[0] == 'route' for edge in _route_edge_keys(project, expected[key])}
        extensions = extend_crossing_occupation_groups(project, dependency, retained_edges, edited_edges)
    affected = set()
    pending = []
    for alignment, routes in zip(alignments, route_changes, strict=True):
        report, _, release, anchors = alignment
        rewritten = _rewrite_cross_routes(project, routes, tuple(report['old_pair']), tuple(report['new_pair']),
                                          release, anchors, protection, pending=pending)
        report['rewritten_routes'] = rewritten
        affected.update(row['route_owner'][0] for row in rewritten if row['primary_fragment_changed'])
        affected.update(row['new_pair'][1][0] for row in rewritten if row['receiving_fragment_changed'])
    _commit_continuations(project, pending, protection)
    traversals = {key: (_metres(before[key]), rows) for key, rows in spans.items() if key[0] == 'itinerary' and rows}
    margins = map_margin_span_profiles(project, traversals, operation.get('map_itinerary_safety_margins') is True)
    groups = transfer_occupation_groups(project, dependency)
    instruments = apply_instrument_edge_rebindings(project, instrument_plan)
    write_exclusions(project, detached)
    reviewed_ends = {project.model((row.document, row.new_end_id)) for row in instrument_plan}
    retirement = _retire(project, operation, alignments, crossing_edge_changes(dependency)[0], expected, reviewed_ends)
    write_exclusions(project, final_exclusions)
    selected_edges = {_edge_key(row) for field in ('old_edges', 'replacement_edges') for row in dependency[field]}
    turnouts = {}
    if operation.get('turnout_updates'):
        original = project_from(documents, document_paths, dest_catalog)
        turnouts = _update_turnouts(original, project, operation, selected_edges)
    affected.update(detached)
    affected.update(row['document'] for row in [*margins, *retirement])
    affected.update(row['after']['document'] for row in [*groups, *extensions])
    affected.update(row['document'] for row in instruments)
    affected.update(key[0] for key in turnouts)

    reports = [report for report, _, _, _ in alignments]
    final_ends = relocated_instrument_ends(instrument_plan, after=True)
    _refresh_profiles(project, reports, final_review, final_observers, final_ends)
    staged = dict(documents)
    _save_documents(staged, project, affected)
    checked = project_from(staged, document_paths, dest_catalog)
    need(_movement_manifest(checked) == expected, 'Cold read changed saved movement identities, geometry or references')
    _verify_final_crossing_profiles(
        checked, reports, final_review, {}, reviewed_instruments=final_observers,
        reviewed_instrument_ends=final_ends)
    for row in retirement:
        removed = {*row['removed_edge_ids'], *row['removed_end_ids'], *row['removed_safety_element_ids']}
        need(removed.isdisjoint(checked.byid[row['document']]), 'A retired junction model survived cold read')
    for name, snapshot in protection.items():
        need(_protection_manifest(checked, name) == snapshot, 'Cold read changed unreviewed Route protection')
    for row in turnouts.values():
        need(_turnout_state(checked, row['end']) == row['after'], 'Turnout settings differ after cold read')
    exclusion_maps = {name: sorted(values.items()) for name, values in final_exclusions.items()}
    verify_transfers(checked, exclusion_maps, [*groups, *extensions])
    verify_instrument_edge_rebindings(checked, instrument_plan)
    verify_margin_profiles(checked, margins)
    outputs = {name: staged[name] for name in sorted(affected) if staged[name] != documents[name]}
    retained_report = {}
    if single_crossing:
        # The full movement and protection comparisons above verify these
        # exact readbacks, including any unedited receiving fragments.
        retained_report = {'retained_alignment_routes': retained,
                           'selected_station_stops': _verify_berths(berths, _selected_berths(checked, choices))}
    return outputs, {
        'action': operation['action'], 'document': target, 'changed_documents': list(outputs),
        'witness_itineraries': witnesses, 'crossing_edits': reports, 'retirement': retirement,
        'movement_count_checked': len(before), 'movement_count_changed': len(choices),
        'mapped_safety_margin_profiles': margins, 'turnout_updates': list(turnouts.values()),
        'dependency_transfers': {'verified_exclusion_maps': exclusion_maps, 'occupation_group_rebindings': groups,
                                 'retained_exclusion_links': list(dependency['retained_exclusion_links']),
                                 'occupation_group_extensions': extensions,
                                 'instrument_edge_rebindings': instruments, 'native_readback_verified': True},
        'continuation_ownership_verified': True,
        'destination_catalog_unchanged': True, 'native_execution_tested': False,
        **retained_report,
    }
