"""Explicit saved Edge Exclusion and occupation transfers within a reroute."""

from collections import defaultdict

from . import native_occupation_groups as occupation, route_factory, writer
from .graph_references import incoming_counts
from .multi_document.core import need
from .saved_edge_exclusion import _check_cycle, _check_movements, _links, _safety_id, _write_links


def exclusion_reviews(rows, side):
    review = defaultdict(set)
    for row in rows:
        review[row['document']].add((row[f'{side}_source_edge_id'], row[f'{side}_target_edge_id']))
    return review


def _edges(project, document):
    _, models = route_factory.document(project.roots[document])
    return {key: edge for key, edge in models.items() if writer.kind(edge) == 'OTEdgeModel'}


def crossing_edge_changes(operation):
    old = {(row['document'], row['edge_id']) for row in operation['old_edges']}
    new = {(row['document'], row['edge_id']) for row in operation['replacement_edges']}
    return old - new, new - old


def prepare_exclusions(project, operation):
    rows = operation.get('exclusion_link_rebindings', ())
    old_review = exclusion_reviews(rows, 'old')
    new_review = exclusion_reviews(rows, 'new')
    old_only, new_only = crossing_edge_changes(operation)
    for row in rows:
        document = row['document']
        old_pair = tuple(row[f'old_{side}_edge_id'] for side in ('source', 'target'))
        new_pair = tuple(row[f'new_{side}_edge_id'] for side in ('source', 'target'))
        need(old_pair != new_pair and new_pair[0] != new_pair[1], 'Select a different reciprocal Edge Exclusion Link')
        for old, new in zip(old_pair, new_pair, strict=True):
            if (document, old) in old_only:
                need((document, new) in new_only, 'A former exclusion End must move to a reviewed same-worksheet replacement Edge')
            else:
                need(old == new and (document, new) not in new_only,
                     'Only the old-only crossing Edge side of a reviewed exclusion link can move')

    need(sum(map(len, old_review.values())) == len(rows) == sum(map(len, new_review.values())),
         'Review each original and replacement exclusion link once')
    detached, final = {}, {}
    for document, removals in old_review.items():
        edges = _edges(project, document)
        links = _links(edges)
        need(removals <= links.items(), 'The saved reciprocal exclusion link differs from the review')
        preserved = {source: target for source, target in links.items() if (source, target) not in removals}
        detached[document] = preserved.copy()
        for source, target in sorted(new_review[document]):
            need(source in edges and target in edges and source not in preserved and target not in preserved.values(),
                 'A replacement exclusion slot already belongs to a different link')
            need(_safety_id(edges[source]) != _safety_id(edges[target]),
                 'A replacement exclusion link selects the same exclusive Safety Element')
            preserved[source] = target
        for source, _ in new_review[document]:
            _check_cycle(preserved, source)
        final[document] = preserved
    return detached, final


def retain_crossing_exclusions(project, operation, detached, final):
    """Prove existing reciprocal links and bind the complete final maps for cold read."""
    involved = {(edge['document'], edge['edge_id']) for name in ('old_edges', 'replacement_edges')
                for edge in operation[name]}
    reviewed = defaultdict(set)
    for row in operation.get('retained_exclusion_links', ()):
        document = row['document']
        pair = row['source_edge_id'], row['target_edge_id']
        need(any((document, edge) in involved for edge in pair) and pair not in reviewed[document],
             'Review each retained exclusion once on a selected native crossing Edge')
        reviewed[document].add(pair)
    for document, pairs in reviewed.items():
        original = _links(_edges(project, document))
        need(pairs <= original.items(), 'The retained reciprocal Edge Exclusion Link differs from the review')
        need(pairs <= detached.get(document, original).items() and pairs <= final.get(document, original).items(),
             'A retained Edge Exclusion Link cannot be transferred in the same junction edit')
        final.setdefault(document, original)
    return reviewed


def write_exclusions(project, links_by_document):
    for document, links in links_by_document.items():
        edges = _edges(project, document)
        before = _links(edges)
        changed = set(before.items()).symmetric_difference(links.items())
        _write_links(edges, links, {item for pair in changed for item in pair})


def validate_exclusion_movements(project, documents, final, rows, movements, changed_movements):
    additions = exclusion_reviews(rows, 'new')
    retired_roles = {(row['document'], row[f'old_{side}_edge_id']) for row in rows for side in ('source', 'target')
                     if row[f'old_{side}_edge_id'] != row[f'new_{side}_edge_id']}
    if retired_roles:
        for (kind, _, identity), (sequence, _, _) in movements.items():
            need(all(project.edge_between(a, b) not in retired_roles for a, b in zip(sequence, sequence[1:])),
                 f'A saved {kind} {identity!r} still needs the former Edge Exclusion Link')
    for document in documents:
        edges = _edges(project, document)
        links = final.get(document, _links(edges))
        for source, target in links.items():
            examined = movements if (source, target) in additions.get(document, ()) else changed_movements
            _check_movements(project, document, examined, source, _safety_id(edges[target]))


def _occupation_binding(project, row):
    document, name = row['document'], row['name']
    root = project.roots[document]
    _, indexed = route_factory.document(root)
    wrapper, array, groups = occupation.entries(root)
    matches = [(group, record) for group in groups if
               (record := occupation.group_record(group, indexed, document))['name'] == name]
    need(len(matches) == 1, 'Select the exact unique saved occupation group name')
    obj, before = matches[0]
    need(before['saved_document'] == document and not before['unresolved_edge_ids'],
         'Confirm an occupation group whose observed Edges resolve in its owning worksheet')
    need(before['edge_ids'] == row['expected_edge_ids'], 'The saved occupation Edge order differs from the review')
    counts = incoming_counts(root)
    need(all(counts[id(item)] == 1 for item in (wrapper, array, obj)), 'Occupation group uses shared saved objects')
    return indexed, obj, before


def transfer_occupation_groups(project, operation):
    old_only, new_only = crossing_edge_changes(operation)
    rows = operation.get('occupation_group_rebindings', ())
    keys = {(row['document'], row['name']) for row in rows}
    need(len(keys) == len(rows), 'Review each occupation group only once')
    receipts = []
    for row in rows:
        document = row['document']
        need(any(key[0] == document for key in old_only), 'The occupation group must be local to the selected crossing')
        indexed, obj, before = _occupation_binding(project, row)
        mapping = {item['old_edge_id']: item['new_edge_ids'] for item in row['edge_rebindings']}
        need(len(mapping) == len(row['edge_rebindings']) and mapping.keys() <= set(before['edge_ids']),
             'Select each existing old-only group Edge at most once')
        need(all((document, old) in old_only and new and all((document, edge) in new_only for edge in new)
                 for old, new in mapping.items()), 'Occupation group Edges must move from the old alignment to a local replacement')
        revised = [part for edge in before['edge_ids'] for part in mapping.get(edge, [edge])]
        need(len(set(revised)) == len(revised), 'The transferred occupation group would repeat an Edge')
        occupation.verify_edges(indexed, revised)
        obj.contents[2].value = occupation.edge_array(revised)
        receipts.append({'before': before, 'after': {**before, 'edge_ids': revised}})
    return receipts


def extend_crossing_occupation_groups(project, operation, kept_route_edges, edited_route_edges):
    rows = operation.get('occupation_group_extensions', ())
    keys = [(row['document'], row['name']) for row in rows]
    transferred = {(row['document'], row['name']) for row in operation.get('occupation_group_rebindings', ())}
    need(len(set(keys)) == len(keys) and set(keys).isdisjoint(transferred),
         'Review each occupation group once, as either an extension or a transfer')
    old_only, new_only = crossing_edge_changes(operation)
    receipts = []
    for row in rows:
        document = row['document']
        need(any(doc == document for doc, _ in old_only), 'The occupation extension must be in the selected crossing')
        indexed, obj, before = _occupation_binding(project, row)
        existing = before['edge_ids']
        old_members = [edge for edge in existing if (document, edge) in old_only]
        additions = row['added_edge_ids']
        need(old_members and all((document, edge) in kept_route_edges for edge in old_members),
             'Each old alignment monitor member must remain in use by a saved Route')
        need(additions and len(set(additions)) == len(additions) and set(existing).isdisjoint(additions)
             and all((document, edge) in new_only and (document, edge) in edited_route_edges for edge in additions),
             'Add only distinct new alignment Edges used by an edited saved Route')
        anchor = row.get('insert_before_edge_id')
        need(anchor is None or anchor in existing, 'The occupation extension anchor must be an existing reviewed group Edge')
        index = len(existing) if anchor is None else existing.index(anchor)
        revised = [*existing[:index], *additions, *existing[index:]]
        occupation.verify_edges(indexed, revised)
        obj.contents[2].value = occupation.edge_array(revised)
        receipts.append({'before': before, 'after': {**before, 'edge_ids': revised},
                         'retained_old_edge_ids': old_members, 'added_edge_ids': additions})
    return receipts


def verify_transfers(project, links, groups):
    for document, expected in links.items():
        actual = _links(_edges(project, document))
        need(sorted(actual.items()) == expected, 'A moved or unrelated native Edge Exclusion Link changed after readback')
    for row in groups:
        expected = row['after']
        matching = [record for record in occupation.records(project.roots[expected['document']], expected['document'])
                    if record['name'] == expected['name']]
        need(matching == [expected], 'Transferred occupation group differs after native readback')
