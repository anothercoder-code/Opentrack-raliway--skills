"""Whole-input checks for native local Shunting structural edits."""
from .. import path_append, path_functions as paths, route_factory, writer
from ..graph_references import incoming_counts
from ..multi_document.core import layout
from . import core


def _matched_reference(info, reference, match_ids):
    return (paths.string(info.contents[0].value) == reference['name'] or
            (match_ids and info.contents[1].values == [reference['array_id'], reference['start_id']]))


def _check_external_references(roots, catalog, document, reference, *, own_info=None):
    for owner, root in roots.items():
        for obj in writer.objects(root):
            kind = writer.kind(obj)
            if kind == 'OTArrayExtInfo':
                layout(obj, [('OTArrayExtInfo', 0), ('OTArrayInfo', 0), ('NSObject', 0)], ['@', 'ii', '@'])
                label = paths.string(obj.contents[2].value)
                core.need(not _matched_reference(obj, reference, label.casefold() == document.casefold()),
                          'Shunting is referenced by a saved external movement record')
            elif kind == 'OTArrayInfo' and obj is not own_info:
                route_factory.layout(obj, 'OTArrayInfo', 0, ['@', 'ii'])
                core.need(not _matched_reference(obj, reference, owner == document),
                          'Shunting is referenced by a saved movement record')
            elif kind == 'OTShunting' or (kind == 'OTRoute' and (owner != document or own_info is None)):
                core.need(paths.string(obj.contents[7].value) != reference['name'],
                          'An existing Overlap could resolve to this Shunting')
    for row in route_factory.wrapper(catalog, 'OTDestInfoList'):
        layout(row, [('OTDestInfo', 1), ('NSObject', 0)], ['i', '@', '@', 'i', '@'])
        for info in paths.mutable_array(row.contents[4].value):
            layout(info, [('OTArrayExtInfo', 0), ('OTArrayInfo', 0), ('NSObject', 0)], ['@', 'ii', '@'])
            label = paths.string(info.contents[2].value)
            core.need(not _matched_reference(info, reference, label.casefold() == document.casefold()),
                      'Shunting is referenced by the bound DestInfo catalog')


def _route(root, reference, models):
    route = paths.select(root, 'OTRoute', **reference)
    nodes = path_append.route_nodes(route, models)
    wrapper = nodes[0].contents[15].value
    counts = incoming_counts(root)
    core.need(counts[id(wrapper)] == counts[id(wrapper.contents[0].value)] == 1,
              'Shared Route owner or backing array')
    for obj in writer.objects(root):
        if writer.kind(obj) == 'OTRouteList' and obj is not wrapper:
            core.need(route not in route_factory.wrapper(obj, 'OTRouteList'), 'Route has multiple owners')
    return route, nodes


def _named_overlap(rows, nodes, name, start_id):
    terminal = nodes[-1].contents[0].value
    expected_id = terminal if start_id < 0 else start_id
    matches = [row for row in rows if core.identity(row[0])['start_id'] == expected_id
               and core.identity(row[0])['name'] == name]
    core.need(len(matches) == 1, 'Stored Overlap name does not identify exactly one Shunting at its selected End')
    return matches[0]


def _linked_routes(root, reference, shunting_nodes, rows, models):
    relations = []
    for obj in writer.objects(root):
        if writer.kind(obj) != 'OTRoute' or paths.string(obj.contents[7].value) != reference['name']:
            continue
        route_ref = core.identity(obj)
        route, route_nodes = _route(root, route_ref, models)
        resolved = _named_overlap(rows, route_nodes, reference['name'], route.contents[9].value)
        if core.identity(resolved[0]) == reference:
            relations.append(route_ref)
            core.need(not any(node in route_nodes[:-1] for node in shunting_nodes),
                      'The replacement Overlap would re-enter the owning Route before its terminal End')
    return relations


def replace_movement(data, reference, end_ids, description=None):
    root, version, _, rows = core.load(data)
    models, _ = route_factory.document(root)
    path, body, old_nodes, old_edges = core.select(rows, reference)
    nodes, _ = core.movement(root, end_ids)
    core.need(nodes[0] is old_nodes[0], 'The Shunting owner End must remain the same')
    counts = incoming_counts(root)
    old_array = body.contents[0].value
    core.need(counts[id(path)] == 1 and counts[id(body)] == 2 and counts[id(old_array)] == 1,
              'Shared automatic Path, Shunting body or End array')
    bound_routes = _linked_routes(root, reference, nodes, rows, models)
    before = core.detail((path, body, old_nodes, old_edges))
    old_path_description, old_body_description = path.contents[3].value, body.contents[3].value
    body.contents[0].value = paths.array_like(old_array, nodes)
    if description is not None:
        path.contents[3].value = paths.fresh_string(old_path_description, description)
        body.contents[3].value = (path.contents[3].value if old_body_description is old_path_description
                                  else paths.fresh_string(old_body_description, description))

    output = writer.dump_verified(root, version)
    fresh, _, _, fresh_rows = core.load(output)
    saved = core.select(fresh_rows, reference)
    after = core.detail(saved)
    core.need(after['end_ids'] == end_ids and after['description'] == (description if description is not None
                                                                     else before['description']),
              'Shunting movement readback differs')
    if description is not None:
        core.need(paths.string(saved[1].contents[3].value) == description, 'Shunting body description readback differs')
    fresh_models, _ = route_factory.document(fresh)
    core.need(_linked_routes(fresh, reference, saved[2], fresh_rows, fresh_models) == bound_routes,
              'Saved Overlap links differ from the original references')

    body.contents[0].value = old_array
    path.contents[3].value = old_path_description
    body.contents[3].value = old_body_description
    original, original_version = writer.load(data)
    core.need(writer.dump_verified(root, version) == writer.dump_verified(original, original_version),
              'Unexpected edits outside the selected Shunting movement')
    return output, core.receipt(data, output, 'replace_local_shunting_movement', {
        'before': before, 'after': after, 'overlap_routes': bound_routes,
        'operating_validation_required': bool(bound_routes and before['end_ids'] != end_ids),
    })


def edit_structure(documents, catalog, document, action, spec):
    data = documents[document]
    root, _, _, rows = core.load(data)
    models, _ = route_factory.document(root)
    roots = {name: writer.load_next_compatible(blob)[0] for name, blob in documents.items() if name != document}
    roots[document] = root
    for member in roots.values():
        route_factory.document(member)
    catalog_root, _ = writer.load_next_compatible(catalog)
    route_factory.wrapper(catalog_root, 'OTDestInfoList')

    if action == 'create':
        core.need(spec['name'].isascii() and spec['name'].isprintable(), 'New Shunting names use printable ASCII')
        nodes, _ = core.movement(root, spec['end_ids'])
        owner = nodes[0]
        paths.guard_counter_references(root, owner, allow_local_shunting=True)
        reference = {'name': spec['name'], 'array_id': core.scalar(owner.contents[19].value, -1, 2147483646) + 1,
                     'start_id': owner.contents[0].value}
        _check_external_references(roots, catalog_root, document, reference)
        return core.create(data, spec)
    if action in ('delete', 'replace_movement'):
        reference = spec['shunting']
        path = core.select(rows, reference)[0]
        own_info, = paths.mutable_array(path.contents[4].value)
        _check_external_references(roots, catalog_root, document, reference, own_info=own_info)
        if action == 'delete':
            return core.delete(data, reference)
        return replace_movement(data, reference, spec['end_ids'], spec.get('description'))

    core.need(action in ('bind_overlap', 'unbind_overlap'), 'Unknown Shunting structural action')
    route, nodes = _route(root, spec['route'], models)
    reference = spec.get('shunting')
    if action == 'bind_overlap':
        selected = core.select(rows, reference)
        core.need(_named_overlap(rows, nodes, reference['name'], reference['start_id'])[0] is selected[0],
                  'Selected Shunting differs from the stored Overlap lookup')
    output, receipt = core.bind_overlap(data, spec['route'], reference, spec.get('selection_policy', 'route_terminal'))
    fresh, _, _, fresh_rows = core.load(output)
    refreshed_models, _ = route_factory.document(fresh)
    saved_route, saved_nodes = _route(fresh, spec['route'], refreshed_models)
    saved_name = paths.string(saved_route.contents[7].value)
    saved_start = saved_route.contents[9].value
    if reference is not None:
        core.need(core.identity(_named_overlap(fresh_rows, saved_nodes, saved_name, saved_start)[0]) == reference,
                  'Saved Overlap resolves to a different Shunting')
    receipt['details']['before_overlap'] = {'name': paths.string(route.contents[7].value),
                                             'start_id': route.contents[9].value}
    return output, receipt
