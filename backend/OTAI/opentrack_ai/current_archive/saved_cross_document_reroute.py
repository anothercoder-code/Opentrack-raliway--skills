"""Reroute a saved two-document crossing over a reviewed alignment."""

from pathlib import PureWindowsPath

from . import native_occupation_groups, path_functions, writer
from .multi_document.core import ident, need
from .route_edit_tools import (_change_route_fragment, _move_continuation_between_owners,
                               _protection_values, _route_owner_counts, _route_shape, _zone_fragment_ids)
from .saved_crossing_dependencies import (exclusion_reviews, prepare_exclusions, transfer_occupation_groups,
                                           validate_exclusion_movements, verify_transfers, write_exclusions)
from .saved_crossing_instruments import (
    apply_instrument_edge_rebindings, prepare_instrument_edge_rebindings, relocated_instrument_ends, verify_instrument_edge_rebindings,
)
from .saved_geometry import _edge, _movement_geometry, model_id, replace_connectors
from .saved_track_replacement import _protection_manifest
from .saved_track_reroute import _rebind_sequence, _walk_span
from .saved_track_topology import _delete_isolated_vertices, _detach_edge_endpoints, _replace_models
from .saved_used_edge_profile import _map_margin_profiles, verify_margin_profiles


def _end_key(ref):
    return ref['document'], ref['end_id']


def _edge_key(ref):
    return ref['document'], ref['edge_id']


def _walk_crossing(project, start, references, reviewed_exclusions=None, *, reviewed_instruments=None,
                   reviewed_instrument_ends=()):
    first = start[0]
    transition = next((i for i, row in enumerate(references) if row['document'] != first), len(references))
    need(0 < transition < len(references), 'Select track on both sides of exactly one document boundary')
    left, right = references[:transition], references[transition:]
    remote = right[0]['document']
    need(all(row['document'] == remote for row in right), 'More than one original document boundary is unsupported')
    need(len({(row['document'], row['edge_id']) for row in references}) == len(references),
         'Repeated track in the selected crossing is unsupported')

    review = reviewed_exclusions or {}
    instruments = reviewed_instruments or {}
    local_ends, first_len, local_profile = _walk_span(project, first, start, [row['edge_id'] for row in left],
        reviewed_exclusions=review.get(first, ()), reviewed_instruments=instruments.get(first),
        reviewed_instrument_ends=reviewed_instrument_ends)
    outgoing = project.related(local_ends[-1])
    need(writer.kind(project.model(outgoing)) == 'OTConnModel', 'The first chain must end at a connector partner')
    incoming = project.block_end(outgoing)
    need(incoming[0] == remote and project.block_end(incoming) == outgoing, 'Crossing requires the reviewed reciprocal connector pair')
    after_crossing = project.related(incoming)
    for key in (local_ends[-1], after_crossing):
        end = project.model(key)
        need(writer.kind(end) == 'OTEndModel' and end.contents[20].value == 1
             and all(end.contents[i].value is None for i in (6, 11, 12, 13)),
             'Boundary approach Ends must be ordinary Ends without station, signal or measurement attachments')
    remote_ends, second_len, remote_profile = _walk_span(
        project, remote, after_crossing, [row['edge_id'] for row in right], reviewed_exclusions=review.get(remote, ()),
        reviewed_instruments=instruments.get(remote), reviewed_instrument_ends=reviewed_instrument_ends)
    total = first_len + second_len
    need(total <= 2147483647, 'Cross-document span exceeds the original signed distance range')
    profiles = [dict(document=name, **row) for name, part in ((first, local_profile), (remote, remote_profile))
                for row in part]
    return (*local_ends, *remote_ends), total, (outgoing, incoming), profiles


def _approved_boundaries(project, old_pair, new_pair, requested):
    allowable = {project.related(a): project.related(b) for a, b in zip(old_pair, new_pair, strict=True)}
    mapping = {_end_key(row['old']): _end_key(row['new']) for row in requested}
    need(len(mapping) == len(requested) and all(allowable.get(a) == b for a, b in mapping.items()),
         'Only matching original and replacement connector-boundary anchor pairs can be approved')
    return mapping


def _anchor_reviews(rows, old_ends, new_ends):
    reviews = {}
    for row in rows:
        owner = _end_key(row['fragment_owner'])
        ref = row['route']
        key = owner, (ref['name'], ref['array_id'], ref['start_id'])
        need(key not in reviews, 'Review each original Route fragment only once')
        anchors = {item['old_end_id']: item['new_end_id'] for item in row['anchors']}
        need(anchors and len(anchors) == len(row['anchors'])
             and len(set(anchors.values())) == len(anchors), 'Choose distinct original and replacement Route anchors')
        need(all(old != new and (owner[0], old) in old_ends and (owner[0], new) in new_ends
                 for old, new in anchors.items()), 'Route anchors must belong to the reviewed old and replacement crossing in the same document')
        reviews[key] = anchors
    return reviews


def _update_fragment(project, owner, route, new_keys, boundary_mapping, anchors, *, has_continuation):
    flags = _route_shape(route)
    fields = _protection_values(route, flags)
    old_nodes = path_functions.mutable_array(route.contents[0].value)
    local_ids = {key[1] for key in new_keys}
    release_ids = fields['release_group_end_ids']
    zone_ids = _zone_fragment_ids(route, flags)
    saved_anchor_ids = set(release_ids) | set(zone_ids)
    need(all(old in saved_anchor_ids and old not in local_ids and new in local_ids for old, new in anchors.items()),
         'Every reviewed anchor must replace an affected saved release or slow-zone End in this Route fragment')
    need(not any((owner[0], old) in boundary_mapping and old in release_ids for old in anchors),
         'Supply each release anchor through either the connector boundary or the exact Route review')
    releases = []
    remapped = []
    for old_id in release_ids:
        old = owner[0], old_id
        if old_id in local_ids:
            releases.append(old_id)
            continue
        replacement = (owner[0], anchors[old_id]) if old_id in anchors else boundary_mapping.get(old)
        need(replacement is not None and replacement[1] in local_ids and replacement[0] == owner[0],
             'A removed release anchor needs explicit matching connector-boundary or Route-anchor approval')
        releases.append(replacement[1])
        remapped.append({'old': old, 'new': replacement})
    revised_zone = None
    zone_remapped = []
    if anchors.keys() & set(zone_ids):
        revised_zone = [anchors.get(old, old) for old in zone_ids]
        zone_remapped = [{'old': (owner[0], old), 'new': (owner[0], new)}
                         for old, new in zip(zone_ids, revised_zone, strict=True) if old != new]
    if release_ids and anchors:
        for index in (0, -1):
            if release_ids[index] == model_id(old_nodes[index]):
                need(releases[index] == new_keys[index][1], 'A release boundary at a fragment end must remain at that end')
    need(len(new_keys) <= 1000 and len(set(new_keys)) == len(new_keys), 'Unsupported repeated or oversized Route fragment')
    counts = _route_owner_counts(project, owner)
    nodes = [project.model(key) for key in new_keys]
    changed = nodes != old_nodes
    if changed:
        _change_route_fragment(route, nodes, counts, releases, primary=has_continuation, zone_ids=revised_zone)
    settings = _protection_values(route, flags)
    settings['slow_speed_zone_fragment_end_ids'] = _zone_fragment_ids(route, flags)
    return settings, remapped, zone_remapped, changed


def _verify_joined_zone(sequence, left, right, left_doc, right_doc):
    joined = [(right_doc, remote) if remote is not None else (left_doc, local)
              for local, remote in zip(left, right, strict=True)]
    need(all(end in sequence for end in joined) and sequence.index(joined[0]) < sequence.index(joined[1]),
         'The original primary and continuation must compose one ordered slow-speed zone after migration')


def _rewrite_cross_routes(project, changed_routes, old_pair, new_pair, mapping, anchors, protection,
                          *, pending=None):
    changes = []
    for identity, sequence in changed_routes.items():
        _, owner, route_id = identity
        primary = project.owned(owner, 'OTRoute', route_id)
        records = [row for row in project.continuations if row['source_document'] == owner[0]
                   and row['route'] == {'name': route_id[0], 'array_id': route_id[1], 'start_id': route_id[2]}]
        need(len(records) == 1, 'Each edited main Route must have exactly one original continuation')
        original, = records
        old_receiver = original['target_document'], original['target_connector']
        old_sender = owner[0], original['source_connector']
        need((old_sender, old_receiver) in (old_pair, old_pair[::-1]), 'Route does not own the selected original crossing')
        split = next(i for i, key in enumerate(sequence) if key[0] != owner[0])
        left, right = sequence[:split], sequence[split:]
        need(all(key[0] == old_receiver[0] for key in right), 'Replacement changes Route document order')
        new_sender = project.related(left[-1])
        new_receiver = project.block_end(new_sender)
        need((new_sender, new_receiver) in (new_pair, new_pair[::-1]), 'Route does not use the reviewed replacement crossing')
        fragment = project.owned(old_receiver, 'OTRoute', route_id)
        left_anchors = anchors.pop((owner, route_id), {})
        right_anchors = anchors.pop((old_receiver, route_id), {})
        left_settings, left_remapped, left_zone, left_changed = _update_fragment(
            project, owner, primary, left, mapping, left_anchors, has_continuation=True)
        right_settings, right_remapped, right_zone, right_changed = _update_fragment(
            project, old_receiver, fragment, right, mapping, right_anchors, has_continuation=False)
        if left_zone or right_zone:
            _verify_joined_zone(sequence, left_settings['slow_speed_zone_fragment_end_ids'],
                                right_settings['slow_speed_zone_fragment_end_ids'], owner[0], old_receiver[0])
        primary_key = owner, 'OTRoute', route_id
        old_key = old_receiver, 'OTRoute', route_id
        new_key = new_receiver, 'OTRoute', route_id
        protection_fields = ('release_group_end_ids', 'slow_speed_zone_end_ids', 'slow_speed_zone_fragment_end_ids')
        for field in protection_fields:
            protection[owner[0]][primary_key][field] = left_settings[field]
        fragment_settings = {**protection[old_receiver[0]][old_key],
                             **{field: right_settings[field] for field in protection_fields}}
        if pending is None:
            _move_continuation_between_owners(project, fragment, old_receiver, new_receiver, route_id)
            protection[old_receiver[0]].pop(old_key)
            protection[new_receiver[0]][new_key] = fragment_settings
        else:
            pending.append((fragment, old_key, new_key, fragment_settings))
        changes.append({'route_owner': owner, 'identity': route_id, 'old_pair': [old_sender, old_receiver],
                        'new_pair': [new_sender, new_receiver], 'primary_end_ids': [key[1] for key in left],
                        'continuation_end_ids': [key[1] for key in right], 'rebound_release_boundaries': [*left_remapped, *right_remapped],
                        'rebound_slow_speed_zone_ends': [*left_zone, *right_zone],
                        'primary_fragment_changed': left_changed,
                        'receiving_fragment_changed': right_changed or old_receiver != new_receiver})
    need(not anchors, 'Some Route-anchor reviews did not match a changed original fragment')
    return changes


def _retire_crossing(project, operation, old, old_pair, expected, *, retain_pair, reviewed_instrument_ends=()):
    replacement = set(map(_edge_key, operation['replacement_edges']))
    retired_by_document = {document: [] for document, _ in old_pair}
    for key in map(_edge_key, operation['old_edges']):
        if key not in replacement:
            retired_by_document[key[0]].append(key[1])
    retired_edges = [(document, edge_id) for document, ids in retired_by_document.items() for edge_id in ids]
    if retain_pair:
        need(retired_edges, 'Select at least one old-only Edge when retiring track around a retained connector pair')
    else:
        need(all(retired_by_document.values()), 'Retirement requires old-only track on both crossing approaches')

    boundary = {end for connector in old_pair for end in (connector, project.related(connector))}
    eligible = {end for vertex in old[:-1] for end in (vertex, project.related(vertex))} - boundary
    isolated = [_end_key(ref) for ref in operation.get('retire_isolated_ends', ())]
    need(set(isolated) <= eligible, 'Select only reviewed isolated interior pairs of the former crossing')
    connector_pairs = [] if retain_pair else [old_pair]
    return _retire_crossing_network(
        project, retired_edges, isolated, connector_pairs, expected, reviewed_instrument_ends=reviewed_instrument_ends)


def _retire_crossing_network(project, retired_edges, isolated, connector_pairs, expected, *, reviewed_instrument_ends=()):
    retired_by_document = {}
    for name, edge_id in retired_edges:
        retired_by_document.setdefault(name, []).append(edge_id)
    end_pairs = [*isolated, *(vertex for pair in connector_pairs for vertex in pair)]
    retired_ends = {end for vertex in end_pairs for end in (vertex, project.related(vertex))}
    need(len(retired_ends) == 2 * len(end_pairs), 'Select each retired crossing vertex pair only once')
    retired_keys = set(retired_edges)
    for label, (sequence, _, _) in expected.items():
        need(retired_ends.isdisjoint(sequence)
             and all(project.edge_between(a, b) not in retired_keys for a, b in zip(sequence, sequence[1:])),
             f'A saved {label[0]} {label[2]!r} still refers to part of the retired crossing')

    by_name = {name.casefold(): set(ids) for name, ids in retired_by_document.items()}
    for sheet, root in project.roots.items():
        for row in native_occupation_groups.records(root, sheet):
            observed = PureWindowsPath(row['saved_document']).name.casefold().removesuffix('.opentrack')
            monitored = by_name.get(sheet.casefold(), set()) | by_name.get(observed, set())
            need(monitored.isdisjoint(row['edge_ids']),
                 f'Saved occupation monitor {row["name"]!r} still refers to a retired crossing Edge')

    if connector_pairs:
        unlink = []
        for (left_doc, left_end), (right_doc, right_end) in connector_pairs:
            unlink.append({'a': {'document': left_doc, 'end_id': left_end},
                           'b': {'document': right_doc, 'end_id': right_end}})
        replace_connectors(project, {'unlink': unlink, 'link': []})
    report = []
    for document, _ in end_pairs:
        retired_by_document.setdefault(document, [])
    for document, edge_ids in retired_by_document.items():
        vertex_ids = [ident for name, ident in end_pairs if name == document]
        if not edge_ids and not vertex_ids:
            continue
        edges = [_edge(project, document, {'edge_id': edge_id}) for edge_id in edge_ids]
        for edge in edges:
            _detach_edge_endpoints(edge, reviewed_instrument_ends=reviewed_instrument_ends)
        retired = set(edges)
        _replace_models(project, document, [obj for obj in project.models[document] if obj not in retired])
        vertices = _delete_isolated_vertices(project, document, vertex_ids)
        report.append({'document': document, 'removed_edge_ids': list(map(model_id, edges)), **vertices})
    return report


def _inspect_alignment(project, operation, old_review, *, reviewed_instruments=None, reviewed_instrument_ends=()):
    start = _end_key(operation['start_end'])
    old_refs, new_refs = operation['old_edges'], operation['replacement_edges']
    instrument_review = {'reviewed_instruments': reviewed_instruments, 'reviewed_instrument_ends': reviewed_instrument_ends}
    old, old_length, old_pair, old_profile = _walk_crossing(project, start, old_refs, old_review, **instrument_review)
    new, new_length, new_pair, new_profile = _walk_crossing(project, start, new_refs, old_review, **instrument_review)
    terminal = old[-1]
    retain_pair = operation.get('connector_policy') == 'retain_pair'
    if retain_pair:
        need(new[-1] == terminal and new_pair == old_pair and set(map(_edge_key, new_refs)) - set(map(_edge_key, old_refs)),
             'A retained crossing requires an unchanged connector pair and a genuinely different track to the same directed End')
        need(not operation.get('release_boundary_rebindings'), 'A retained connector pair has no boundary anchor to rebind')
    else:
        need(new[-1] == terminal and set(old_pair).isdisjoint(new_pair),
             'Replacement must reach the same directional End via a different reciprocal pair')
    approved = [(row['document'], row['element_id']) for row in operation['expected_replacement_safety_elements']]
    actual = [(row['document'], row['safety_element_id']) for row in new_profile]
    need(approved == actual and operation['expected_replacement_length_m'] == new_length,
         'Replacement crossing length or ordered document Safety Element IDs differ from the reviewed values')
    old_reverse, _, reverse_pair, _ = _walk_crossing(project, terminal, old_refs[::-1], old_review, **instrument_review)
    new_reverse, _, new_reverse_pair, new_reverse_profile = _walk_crossing(project, terminal, new_refs[::-1], old_review,
                                                                           **instrument_review)
    need(old_reverse[-1] == new_reverse[-1] == start and reverse_pair == old_pair[::-1]
         and new_reverse_pair == new_pair[::-1], 'Reverse crossing differs from the original reciprocal chain')
    report = {'start_end': start, 'terminal_end': terminal, 'old_pair': list(old_pair), 'new_pair': list(new_pair),
              'connector_policy': 'retain_pair' if retain_pair else 'replace_pair',
              'old_profile': old_profile, 'new_profile': new_profile, 'new_reverse_profile': new_reverse_profile,
              'old_length_m': old_length, 'new_length_m': new_length}
    substitutions = {start: (old, new, old_length), terminal: (old_reverse, new_reverse, old_length)}
    boundary_mapping = _approved_boundaries(project, old_pair, new_pair, operation.get('release_boundary_rebindings', ()))
    anchors = _anchor_reviews(operation.get('route_anchor_rebindings', ()),
                              set(old) | set(old_reverse), set(new) | set(new_reverse))
    return report, substitutions, boundary_mapping, anchors


def reroute_cross_document_track_span(project, document, operation, before):
    exclusion_rows = operation.get('exclusion_link_rebindings', ())
    old_review = exclusion_reviews(exclusion_rows, 'old')
    detached, final_exclusions = prepare_exclusions(project, operation)
    instrument_plan, former_observers, final_observers = prepare_instrument_edge_rebindings(
        project, operation, operation.get('instrument_edge_rebindings', ()))
    report, substitutions, boundary_mapping, anchors = _inspect_alignment(
        project, operation, old_review, reviewed_instruments=former_observers,
        reviewed_instrument_ends=relocated_instrument_ends(instrument_plan))
    start, terminal = report['start_end'], report['terminal_end']
    need(start[0] == document, 'Target document must match the start End')
    old_pair, new_pair = tuple(report['old_pair']), tuple(report['new_pair'])
    old_length, new_length = report['old_length_m'], report['new_length_m']
    retain_pair = report['connector_policy'] == 'retain_pair'
    traversals = {}
    expected = before.copy()
    changed_routes = {}
    movement_report = []
    delta = new_length - old_length
    for identity, (sequence, refs, _) in before.items():
        rebound, distance, spans = _rebind_sequence(project, sequence, substitutions)
        if not spans:
            continue
        geometry = _movement_geometry(project, rebound, check_safety=True)
        revised_distance = sum(row[1] for row in geometry)
        need(0 < revised_distance <= 2147483647 and revised_distance == distance + len(spans) * delta,
             'New movement distance differs from the reviewed crossing')
        if identity[0] == 'route':
            need(rebound[0] == sequence[0] and rebound[-1] == sequence[-1], 'Route signals must remain at both outer Ends')
            changed_routes[identity] = rebound
        traversals[identity] = distance, spans
        expected[identity] = rebound, refs, geometry
        movement_report.append({'kind': identity[0], 'owner': identity[1], 'identity': identity[2],
                                'before_distance_m': distance, 'after_distance_m': revised_distance})
    need(changed_routes, 'No saved original Route uses the complete selected crossing')
    crossing_documents = {document, terminal[0]}
    validate_exclusion_movements(project, crossing_documents, final_exclusions, exclusion_rows, expected,
                                 {identity: expected[identity] for identity in traversals})
    protection = {name: _protection_manifest(project, name) for name in crossing_documents}
    changed = _rewrite_cross_routes(project, changed_routes, old_pair, new_pair, boundary_mapping, anchors, protection)
    margins = []
    if delta:
        margins = _map_margin_profiles(project, traversals, new_length,
                                      operation.get('map_itinerary_safety_margins') is True)
    affected = {row['document'] for row in margins}
    if retain_pair:
        affected.update(row['route_owner'][0] for row in changed if row['primary_fragment_changed'])
        affected.update(row['new_pair'][1][0] for row in changed if row['receiving_fragment_changed'])
    else:
        affected.update(crossing_documents)
    report.update(rewritten_routes=changed, affected_movement_distances=movement_report,
                  mapped_safety_margin_profiles=margins)
    occupation = transfer_occupation_groups(project, operation)
    instruments = apply_instrument_edge_rebindings(project, instrument_plan)
    write_exclusions(project, detached)
    if operation.get('retire_original'):
        old = substitutions[start][0]
        new_refs = operation['replacement_edges']
        reviewed_ends = {project.model((row.document, row.new_end_id)) for row in instrument_plan}
        report['retirement'] = _retire_crossing(
            project, operation, old, old_pair, expected, retain_pair=retain_pair, reviewed_instrument_ends=reviewed_ends)
        affected.update(row['document'] for row in report['retirement'])
        review = {'reviewed_instruments': final_observers,
                  'reviewed_instrument_ends': relocated_instrument_ends(instrument_plan, after=True)}
        report['new_profile'] = _walk_crossing(project, start, new_refs, **review)[3]
        report['new_reverse_profile'] = _walk_crossing(project, terminal, new_refs[::-1], **review)[3]
    else:
        need(not operation.get('retire_isolated_ends'), 'Retiring interior Ends requires explicit crossing retirement')
    write_exclusions(project, final_exclusions)
    affected.update(row['after']['document'] for row in occupation)
    affected.update(row['document'] for row in instruments)
    affected.update(final_exclusions)
    if exclusion_rows or occupation or instruments:
        report['dependency_transfers'] = {'exclusion_link_rebindings': list(exclusion_rows),
            'verified_exclusion_maps': {name: sorted(links.items()) for name, links in final_exclusions.items()},
            'occupation_group_rebindings': occupation}
        if instruments:
            report['dependency_transfers']['instrument_edge_rebindings'] = instruments
    return affected, report, expected, protection, (instrument_plan, final_observers)


def verify_cross_document_reroute(project, report, protection, instrument_review):
    instrument_plan, final_observers = instrument_review
    final_ends = relocated_instrument_ends(instrument_plan, after=True)
    dependencies = report.get('dependency_transfers', {})
    final_review = exclusion_reviews(dependencies.get('exclusion_link_rebindings', ()), 'new')
    verify_transfers(project, dependencies.get('verified_exclusion_maps', {}), dependencies.get('occupation_group_rebindings', ()))
    profiles = [('new_profile', tuple(report['new_pair'])),
                ('new_reverse_profile', tuple(reversed(report['new_pair'])))]
    if 'retirement' in report:
        for row in report['retirement']:
            removed = {*row['removed_edge_ids'], *row['removed_end_ids'], *row['removed_safety_element_ids']}
            need(removed.isdisjoint(project.byid[row['document']]), 'A retired crossing model survived native readback')
    else:
        profiles.append(('old_profile', tuple(report['old_pair'])))
    for label, pair in profiles:
        reverse = label == 'new_reverse_profile'
        start, terminal = (report['terminal_end'], report['start_end']) if reverse else (report['start_end'], report['terminal_end'])
        arrivals, _, connectors, profiles = _walk_crossing(
            project, start, report[label], final_review, reviewed_instruments=final_observers,
            reviewed_instrument_ends=final_ends)
        need(arrivals[-1] == terminal and connectors == pair and profiles == report[label],
             'Paired connector or directional profile differs after readback')
    for name, manifest in protection.items():
        need(_protection_manifest(project, name) == manifest, 'Saved protection settings changed beyond approved boundary anchors')
    for row in report['rewritten_routes']:
        owner = row['new_pair'][1]
        saved = project.owned(owner, 'OTRoute', row['identity'])
        need(project.route_view(saved) == [(owner[0], end) for end in row['continuation_end_ids']],
             'Native continuation owner or fragment differs after readback')
    verify_margin_profiles(project, report['mapped_safety_margin_profiles'])
    if instrument_plan:
        verify_instrument_edge_rebindings(project, instrument_plan)
    report['original_connector_pair_retained'] = report['connector_policy'] == 'retain_pair' or 'retirement' not in report
    report['continuation_ownership_verified'] = True
    if dependencies:
        dependencies['native_readback_verified'] = True
