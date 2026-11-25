"""Typed saved occupation monitors. Original OpenTrack performs logging at run time."""

import re

from . import path_functions as paths, route_factory as route, writer as w
from .graph_references import incoming_counts
from .native_monitoring import models
from .zero_generation import native_signal_routes as ns


GROUP_CLASS = [('OTOccInfo', 2), ('NSObject', 0)]
ARRAY_CLASS = [('NSArray', 0), ('NSObject', 0)]
NUMBER_CLASS = [('NSNumber', 0), ('NSValue', 0), ('NSObject', 0)]
END_CLASSES = {'OTEndModel', 'OTConnModel', 'OTStationEndModel'}
SAFE_NAME = r'[A-Za-z0-9][A-Za-z0-9_-]{0,59}'


def name(value):
    route.require(isinstance(value, str) and re.fullmatch(SAFE_NAME, value),
                  'Use 1 to 60 ASCII letters, digits, underscores or hyphens, starting with a letter or digit')
    return value


def number(value):
    kind = b's' if value <= 32767 else b'i'
    return w.GenericArchivedObject(ns.cls(NUMBER_CLASS), None, [
        w.TypedValue(b'*', w.CString(w.SharedString(kind))), w.TypedValue(kind, value),
    ])


def edge_number(obj):
    paths.hierarchy(obj, NUMBER_CLASS)
    route.require(len(obj.contents) == 2 and obj.contents[0].encodings == [b'*']
                  and obj.contents[1].encodings in ([b's'], [b'i']), 'Unsupported saved Edge identifier')
    kind = obj.contents[1].encodings[0]
    token = obj.contents[0].value
    route.require(isinstance(token, w.CString) and token.token.data == kind, 'Inconsistent Edge identifier encoding')
    return ns.integer(obj.contents[1].value)


def entries(root):
    route.require(root.contents[12].encodings == [b'@'], 'Unrecognized saved occupation monitor slot')
    wrapper = root.contents[12].value
    items = route.wrapper(wrapper, 'OTOccInfoList')
    return wrapper, wrapper.contents[0].value, items


def group_record(obj, models_by_id, document):
    paths.hierarchy(obj, GROUP_CLASS)
    route.require([group.encodings for group in obj.contents] == [[b'@'], [b'@'], [b'@'], [b'i'], [b'i']],
                  'Unsupported OTOccInfo v2 layout')
    group_name, saved_document = (w.string(obj.contents[index].value) for index in (0, 1))
    route.require(group_name and saved_document, 'Missing occupation group name or worksheet identity')
    array = obj.contents[2].value
    paths.hierarchy(array, ARRAY_CLASS if w.kind(array) == 'NSArray' else [('NSMutableArray', 0), *ARRAY_CLASS])
    edge_ids = [edge_number(item) for item in w.elements(array)]
    selected, label_id = (obj.contents[index].value for index in (3, 4))
    route.require(selected in (0, 1) and -1 <= label_id <= 2_147_483_647, 'Invalid occupation group settings')
    return {'name': group_name, 'document': document, 'saved_document': saved_document,
            'selected': bool(selected), 'edge_ids': edge_ids, 'label_id': label_id if label_id >= 0 else None,
            'unresolved_edge_ids': [value for value in edge_ids if w.kind(models_by_id.get(value)) != 'OTEdgeModel']}


def records(root, document):
    _, models_by_id = models(root)
    _, _, groups = entries(root)
    return [group_record(obj, models_by_id, document) for obj in groups]


def verify_edges(models_by_id, edge_ids):
    route.require(1 <= len(edge_ids) <= 10000 and len(edge_ids) == len(set(edge_ids)),
                  'Provide distinct local Edge IDs')
    for edge_id in edge_ids:
        edge = models_by_id.get(ns.integer(edge_id))
        route.require(w.kind(edge) == 'OTEdgeModel', f'Local Edge {edge_id} was not found')
        route.layout(edge, 'OTEdgeModel', 3, route.EDGE, graphic=True)
        for index in (7, 8):
            end = edge.contents[index].value
            route.require(w.kind(end) in END_CLASSES and models_by_id.get(end.contents[0].value) is end
                          and any(end.contents[slot].value is edge for slot in (9, 10)),
                          f'Edge {edge_id} lacks a reciprocal local End')
            element = end.contents[7].value
            route.require(w.kind(element) == 'OTElement' and models_by_id.get(element.contents[0].value) is element,
                          f'Edge {edge_id} lacks a local Safety Element')


def edge_array(edge_ids):
    return ns.obj(ARRAY_CLASS, [('i', [len(edge_ids)]), *[('@', [number(value)]) for value in edge_ids]])


def name_key(name):
    return name.replace(' ', '_').casefold()


def transform(source, document, operations):
    root, version = w.load_next_compatible(source)
    _, models_by_id = route.document(root)
    wrapper, array, saved_groups = entries(root)
    groups = list(saved_groups)
    references = incoming_counts(root)
    route.require(references[id(wrapper)] == references[id(array)] == 1, 'Occupation list is shared with another archive slot')
    before = [group_record(item, models_by_id, document) for item in groups]
    indexed = {}
    for index, record in enumerate(before):
        key = name_key(record['name'])
        route.require(key not in indexed, 'Worksheet has names that can collide in original occupation output')
        indexed[key] = index
    for operation in operations:
        group_name = name(operation['name'])
        key = name_key(group_name)
        edge_ids = operation.get('edge_ids')
        selected = operation.get('selected')
        if edge_ids is not None:
            verify_edges(models_by_id, edge_ids)
        if selected is not None:
            route.require(type(selected) is bool, 'Provide a boolean selection value')
        if operation['action'] == 'create':
            route.require(key not in indexed, f'Occupation name already exists in the worksheet: {group_name}')
            route.require(edge_ids is not None, 'Creation requires local Edge IDs')
            indexed[key] = len(groups)
            groups.append(ns.obj(GROUP_CLASS, [('@', [ns.string(group_name)]), ('@', [ns.string(document)]),
                                               ('@', [edge_array(edge_ids)]), ('i', [int(selected is not False)]),
                                               ('i', [-1])]))
        elif operation['action'] == 'update':
            route.require(key in indexed, f'Unknown occupation group: {group_name}')
            route.require(edge_ids is not None or selected is not None, 'Supply Edge IDs or a selection value')
            obj = groups[indexed[key]]
            route.require(w.string(obj.contents[0].value) == group_name, 'Use the exact saved occupation name')
            route.require(references.get(id(obj), 1) == 1, 'Occupation group is shared with another archive slot')
            if edge_ids is not None:
                obj.contents[2].value = edge_array(edge_ids)
            elif selected is True:
                verify_edges(models_by_id, [edge_number(item) for item in w.elements(obj.contents[2].value)])
            if selected is not None:
                obj.contents[3].value = int(selected)
        else:
            raise ValueError('Unknown occupation group operation')
    w.set_elements(array, groups)
    expected = records(root, document)
    output = w.dump_verified(root, version)
    actual = records(w.load_next_compatible(output)[0], document)
    route.require(actual == expected, 'Occupation group readback differs from saved settings')
    return output, {'before': before, 'after': actual, 'native_execution_verified': False}
