import pytest

from opentrack_ai.current_archive import native_occupation_groups as groups, route_factory as route, writer as w
from opentrack_ai.current_archive.zero_generation import native_signal_routes as ns


def graphic(kind, version, layout, ident):
    defaults = {'i': 0, 'f': 0.0, '@': None}
    obj = ns.obj([(kind, version), ('OTGraphicModel', 1), ('NSObject', 0)],
                 [(encoding, [defaults[field] for field in encoding]) for encoding in layout])
    obj.contents[0].value = ident
    return obj


def worksheet():
    root = ns.obj([('OTDocument', 4), ('NSObject', 0)],
                  [('i', [0]) for _ in range(21)])
    models = []
    for i, ident in enumerate((20, 32768)):
        edge = graphic('OTEdgeModel', 3, route.EDGE, ident)
        block = graphic('OTElement', 0, ['i', 'f', 'f', 'f', 'i', 'i', '@', '@'], 3 * i + 1)
        models.extend((edge, block))
        for index in (7, 8):
            end = graphic('OTEndModel', 7, route.END, 3 * i + index - 5)
            end.contents[7].value = block
            end.contents[9].value = edge
            edge.contents[index].value = end
            models.append(end)
    root.contents[2] = w.TypedValue(b'@', ns.arr(models))
    root.contents[12] = w.TypedValue(b'@', ns.wrapped('OTOccInfoList', []))
    return root


def test_typed_native_multi_edge_group_and_selection_roundtrip():
    root = worksheet()
    source = w.dump_verified(root)
    saved, report = groups.transform(source, 'RDG', [
        {'action': 'create', 'name': 'P9_Monitor', 'edge_ids': [20, 32768]},
        {'action': 'create', 'name': 'Other', 'edge_ids': [20], 'selected': False},
    ])
    assert report['before'] == []
    assert report['after'] == [
        {'name': 'P9_Monitor', 'document': 'RDG', 'saved_document': 'RDG', 'edge_ids': [20, 32768],
         'selected': True, 'label_id': None, 'unresolved_edge_ids': []},
        {'name': 'Other', 'document': 'RDG', 'saved_document': 'RDG', 'edge_ids': [20],
         'selected': False, 'label_id': None, 'unresolved_edge_ids': []},
    ]
    reloaded, _ = w.load(saved)
    assert w.fingerprint(reloaded.contents[2].value) == w.fingerprint(root.contents[2].value)
    _, _, items = groups.entries(reloaded)
    numbers = w.elements(items[0].contents[2].value)
    assert [entry.contents[1].encodings for entry in numbers] == [[b's'], [b'i']]

    updated, changes = groups.transform(saved, 'RDG', [
        {'action': 'update', 'name': 'P9_Monitor', 'edge_ids': [32768], 'selected': False},
    ])
    assert changes['before'] == report['after']
    assert changes['after'][0]['edge_ids'] == [32768]
    assert changes['after'][0]['selected'] is False
    assert changes['after'][1] == changes['before'][1]
    assert groups.records(w.load(updated)[0], 'RDG') == changes['after']


def test_updates_preserve_existing_map_label_and_saved_document():
    root = worksheet()
    existing = ns.obj(groups.GROUP_CLASS, [('@', [ns.string('Previous')]), ('@', [ns.string('OldStem')]),
                                           ('@', [groups.edge_array([20])]), ('i', [1]), ('i', [91])])
    _, array, _ = groups.entries(root)
    w.set_elements(array, [existing])
    _, report = groups.transform(w.dump_verified(root), 'RDG', [
        {'action': 'update', 'name': 'Previous', 'selected': False},
    ])
    assert report['after'][0] == {**report['before'][0], 'selected': False}


def test_cannot_activate_preexisting_group_with_unresolved_edge():
    root = worksheet()
    group = ns.obj(groups.GROUP_CLASS, [('@', [ns.string('Old')]), ('@', [ns.string('RDG')]),
                                        ('@', [groups.edge_array([99])]), ('i', [0]), ('i', [-1])])
    _, array, _ = groups.entries(root)
    w.set_elements(array, [group])
    assert groups.records(root, 'RDG')[0]['unresolved_edge_ids'] == [99]
    with pytest.raises(ValueError, match='Local Edge 99'):
        groups.transform(w.dump_verified(root), 'RDG', [{'action': 'update', 'name': 'Old', 'selected': True}])


@pytest.mark.parametrize(('ids', 'message'), [([20, 20], 'distinct'), ([1], 'Local Edge'), ([123], 'Local Edge')])
def test_guards_non_edge_or_duplicate_ids(ids, message):
    with pytest.raises(ValueError, match=message):
        groups.transform(w.dump_verified(worksheet()), 'RDG', [
            {'action': 'create', 'name': 'Test', 'edge_ids': ids},
        ])


def test_guards_name_collision_reused_group_list_and_detached_end():
    root = worksheet()
    op = {'action': 'create', 'name': 'P9', 'edge_ids': [20]}
    with pytest.raises(ValueError, match='already exists'):
        groups.transform(w.dump_verified(root), 'RDG', [op, {**op, 'name': 'p9'}])

    root.contents[13] = w.TypedValue(b'@', root.contents[12].value.contents[0].value)
    with pytest.raises(ValueError, match='shared'):
        groups.transform(w.dump_verified(root), 'RDG', [op])

    root = worksheet()
    _, models = route.document(root)
    models[20].contents[7].value.contents[9].value = None
    with pytest.raises(ValueError, match='reciprocal local End'):
        groups.transform(w.dump_verified(root), 'RDG', [op])
