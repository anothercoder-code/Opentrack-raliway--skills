"""Edit the original same-worksheet directed Edge Inspector Exclusion Link."""

from . import writer
from .multi_document.core import need
from .saved_geometry import _movement_manifest, model_id, project_from


OUTGOING, INCOMING = 13, 14


def _links(edges):
    outgoing = {}
    for edge_id, edge in edges.items():
        for slot, reverse_slot in ((OUTGOING, INCOMING), (INCOMING, OUTGOING)):
            linked = edge.contents[slot].value
            if linked is None:
                continue
            need(writer.kind(linked) == 'OTEdgeModel', 'An exclusion reference must point to a native Edge')
            linked_id = model_id(linked)
            need(edges.get(linked_id) is linked and linked is not edge and linked.contents[reverse_slot].value is edge,
                 'The worksheet already contains a nonlocal, self, or nonreciprocal Edge exclusion link')
            if slot == OUTGOING:
                outgoing[edge_id] = linked_id
    return outgoing


def _safety_id(edge):
    return model_id(edge.contents[7].value.contents[7].value)


def _check_cycle(links, source):
    visited = set()
    while source in links:
        need(source not in visited, 'An exclusion link cannot create a directed cycle')
        visited.add(source)
        source = links[source]


def _check_movements(project, document, movements, source, linked_safety):
    affected = []
    for (kind, owner, identity), (sequence, _, profile) in movements.items():
        if not any(project.edge_between(a, b) == (document, source) for a, b in zip(sequence, sequence[1:])):
            continue
        need(all(record[0][-1] != (document, linked_safety) for record in profile),
             f'The exclusion would reserve an existing traversal resource of saved {kind} {identity!r}')
        affected.append({'kind': kind, 'owner': owner, 'identity': identity})
    return affected


def _write_links(edges, links, touched):
    inbound = {target: source for source, target in links.items()}
    for edge_id in touched:
        edge = edges[edge_id]
        edge.contents[OUTGOING].value = edges.get(links.get(edge_id))
        edge.contents[INCOMING].value = edges.get(inbound.get(edge_id))


def set_edge_exclusion(documents, paths, dest, document, operation):
    project = project_from(documents, paths, dest)
    root = project.roots[document]
    edges = {number: obj for number, obj in project.byid[document].items() if writer.kind(obj) == 'OTEdgeModel'}
    original = _links(edges)
    updated = original.copy()
    source, target = operation['edge_id'], operation['target_edge_id']
    previous = original.get(source)
    need(source in edges and (target is None or target in edges and target != source),
         'Select separate current Edge IDs in the same worksheet')
    need(previous == operation['expected_target_edge_id'] and previous != target,
         'The original target differs from the review or the exclusion is already set')
    inbound = {edge_id: origin for origin, edge_id in original.items()}
    displaced = inbound.get(target)
    need(displaced == operation.get('expected_target_source_edge_id'),
         'Review the exact prior source for the target Edge before replacing its exclusion link')

    previous_graph = writer.fingerprint(root)
    before = _movement_manifest(project)
    touched = {source}
    if previous is not None:
        del updated[source]
        touched.add(previous)
    affected = []
    if target is not None:
        if displaced is not None:
            del updated[displaced]
            touched.add(displaced)
        linked_safety = _safety_id(edges[target])
        need(_safety_id(edges[source]) != linked_safety, 'The two Edges already use the same exclusive Safety Element')
        updated[source] = target
        _check_cycle(updated, source)
        affected = _check_movements(project, document, before, source, linked_safety)
        touched.add(target)
    _write_links(edges, updated, touched)
    output = writer.dump_verified(root, project.versions[document])
    checked = project_from({**documents, document: output}, paths, dest)
    fresh_edges = {edge_id: checked.model((document, edge_id)) for edge_id in edges}
    need(_links(fresh_edges) == updated and _movement_manifest(checked) == before,
         'The native exclusion links or other saved movement data differ after readback')
    _write_links(fresh_edges, original, touched)
    need(writer.fingerprint(checked.roots[document]) == previous_graph,
         'An object or reference besides the reviewed original exclusion links changed')
    return {document: output}, {
        'action': operation['action'], 'document': document, 'changed_documents': [document],
        'edge_id': source, 'before_target_edge_id': previous, 'target_edge_id': target,
        'removed_target_source_edge_id': displaced, 'protected_movements': affected,
        'movement_count_checked': len(before), 'nonselected_graph_verified': True,
        'destination_catalog_unchanged': True, 'native_execution_tested': False,
    }
