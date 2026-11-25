"""Rebind saved Itinerary endpoints to a paired station reference without editing Routes."""

from collections import defaultdict
import math

from . import path_functions, writer
from .graph_references import incoming_counts
from .itinerary_edit_tools import _float32, _margin_members, _margin_values, _project
from .itinerary_lifecycle_tools import _catalog_array, _catalog_row, _copy_margins, _owner_array, _snapshot
from .multi_document.core import ident, need, ref, sha
from .multi_document.generate import inf
from .multi_document.operations import exact_reference
from .path_lifecycle_tools import Changes, _allocated_path, _guard_fresh_identity, _name_available
from .saved_geometry import _movement_manifest


def _station_pair(project, moved):
    need(isinstance(moved, dict) and len(moved) == 2 and len(set(moved.values())) == 2 and set(moved).isdisjoint(moved.values()),
         'Review one old and one revised paired station reference')
    old, new = next(iter(moved.items()))
    need(moved.get(project.related(old)) == project.related(new), 'Review both original and revised native direction halves')
    memberships = {}
    for keys, kind in ((moved, 1), (moved.values(), 2)):
        for key in keys:
            node = project.model(key)
            station = node.contents[12].value
            need(writer.kind(node) == 'OTEndModel' and writer.kind(station) == 'OTStationModel'
                 and project.key(station)[0] == key[0] and node.contents[20].value == kind,
                 'Use a demoted ordinary old pair and the promoted new reference pair in the same station')
            sign = path_functions.string(station.contents[7].value)
            need(bool(sign) and (key[0] not in memberships or memberships[key[0]] == (project.key(station), sign)),
                 'Moving a station reference must retain the same native station area on each selected worksheet')
            memberships[key[0]] = project.key(station), sign
    need(len({sign for _, sign in memberships.values()}) == 1, 'The revised reference has a different station sign')
    return {name: values[0] for name, values in memberships.items()}


def _route_sequence(project, references):
    need(type(references) is list and 1 <= len(references) <= 1000, 'Review a bounded ordered replacement Route sequence')
    selected, nodes, keys = [], [], []
    for reference in references:
        document, identity = exact_reference(reference)
        owner = document, identity[2]
        route = project.owned(owner, 'OTRoute', identity)
        actual = project.route_view(route)
        need(writer.kind(project.model(owner)) == 'OTEndModel' and actual[0] == owner
             and (not nodes or nodes[-1] == owner),
             'Replacement Routes must connect at exact primary directed Ends')
        nodes.extend(actual[1:] if nodes else actual)
        keys.append((document, identity))
        selected.append((document, route))
    need(len(nodes) <= 10000 and len(nodes) == len(set(nodes)), 'Endpoint rebinding requires a bounded nonrepeating Itinerary')
    return selected, nodes, keys


def _station_segment(project, segment, memberships, moved):
    approved = set(moved) | set(moved.values())
    for node in segment:
        model = project.model(node)
        station = model.contents[12].value
        need(writer.kind(model) == 'OTEndModel' and station is not None and project.key(station) == memberships.get(node[0])
             and (node in approved or model.contents[20].value == 1),
             'An added or removed endpoint prefix/suffix leaves the reviewed native station area')
    distance = 0
    for start, finish in zip(segment, segment[1:]):
        outgoing = project.model(project.actual_related(start))
        arrival = project.model(finish)
        key = project.edge_between(start, finish)
        edge = project.model(key)
        need(all(half.contents[9].value is edge and half.contents[10].value is None for half in (outgoing, arrival))
             and outgoing.contents[12].value is arrival.contents[12].value,
             'An added or removed endpoint prefix/suffix requires one nonbranching native track')
        distance += edge.contents[9].values[1]
    return distance


def _endpoint_change(project, before, after, moved, memberships):
    need(len(before) == len(set(before)) and len(before) >= 2 and len(after) >= 2,
         'Endpoint rebinding requires a nonrepeating original Itinerary')
    expected = moved.get(before[0], before[0]), moved.get(before[-1], before[-1])
    need((after[0], after[-1]) == expected and (before[0], before[-1]) != expected,
         'Replacement Routes must start and end at the exact reviewed revised directional Ends')
    starts, ends, deltas = [0, 0], [len(before) - 1, len(after) - 1], [0, 0]
    for i, (original, revised) in enumerate(((before[0], after[0]), (before[-1], after[-1]))):
        if original == revised:
            continue
        if revised in before:
            index = before.index(revised)
            span = before[:index + 1] if i == 0 else before[index:]
            (starts if i == 0 else ends)[0] = index
            deltas[i] = -_station_segment(project, span, memberships, moved)
        else:
            need(original in after, 'A replacement extension must reach its exact former directional endpoint')
            index = after.index(original)
            span = after[:index + 1] if i == 0 else after[index:]
            (starts if i == 0 else ends)[1] = index
            deltas[i] = _station_segment(project, span, memberships, moved)
    core = before[starts[0]:ends[0] + 1]
    need(len(core) >= 2 and after[starts[1]:ends[1] + 1] == core,
         'Endpoint rebinding must preserve the common directed movement without an interior detour')
    old_edges = [project.edge_between(a, b) for a, b in zip(before, before[1:])]
    new_edges = [project.edge_between(a, b) for a, b in zip(after, after[1:])]
    need(old_edges[starts[0]:ends[0]] == new_edges[starts[1]:ends[1]],
         'A common physical Edge changed within the reviewed endpoint rebind')
    return {'preserved_directed_ends': core, 'prefix_length_change_m': deltas[0], 'suffix_length_change_m': deltas[1],
            'original_directed_edges': old_edges, 'revised_directed_edges': new_edges}


def _path_index(project):
    index = defaultdict(list)
    for path in project.paths_objects:
        document, _ = project.owners[id(path)]
        _, routes = project.path_view(path)
        if any('kind' in row for _, row in routes):
            continue
        keys = tuple((doc, (row['name'], row['array_id'], row['start_id'])) for doc, row in routes)
        index[keys[0]].append((keys, document, path))
    return index


def _select_paths(project, catalog, changes, selected, approved, original_paths, index):
    def reusable(start):
        routes = approved[start:]
        options = [item for item in index[routes[0]] if item[0] == tuple(routes[:len(item[0])])]
        return min(options, key=lambda item: (-len(item[0]), id(item[2]) not in original_paths, item[1], ident(item[2])),
                   default=None)

    result, created = [], []
    start = 0
    while start < len(approved):
        existing = reusable(start)
        if existing is not None:
            keys, document, path = existing
            result.append((document, path))
            start += len(keys)
            continue
        end = next((i for i in range(start + 1, len(approved)) if reusable(i) is not None), len(approved))
        document, (_, _, end_id) = approved[start]
        root = project.roots[document]
        owner = project.model((document, end_id))
        highwater = owner.contents[19].value
        suffix = sha(f'{document}:{end_id}'.encode('utf-8'))[:12]
        name = f'P:StationReference:{suffix}:{highwater + 1}'
        _name_available(project, catalog, name)
        owner, holder, path = _allocated_path(project, name, '', selected[start:end], [(document, end_id)])
        identity = {'document': document, **ref(path)}
        _guard_fresh_identity(project, catalog, identity)
        changes.contents(root, holder, path_functions.mutable_array(holder) + [path])
        changes.group(root, owner.contents[19], [identity['array_id']])
        keys = tuple(approved[start:end])
        index[keys[0]].append((keys, document, path))
        result.append((document, path))
        created.append(identity)
        start = end
    return result, created


def _existing_path_objects(project, definition):
    _, refs = project.dest_view(definition)
    return {id(project.itinerary_path((document, route['start_id']), (route['name'], route['array_id'], route['start_id'])))
            for document, route in refs}


def _route_refs_of(saved_project, definition):
    _, references = saved_project.dest_view(definition)
    return [dict(document=doc, **route) for owner, reference in references
            for doc, route in saved_project.path_view(saved_project.itinerary_path(
                (owner, reference['start_id']), (reference['name'], reference['array_id'], reference['start_id'])))[1]]


def _mapped_margins(project, definition, reviewed, counts, authorized):
    wrapper, array, rows = _margin_members(definition)
    if not rows:
        return None
    need(authorized, 'Endpoint rebinding with saved distance-based safety margins requires map_itinerary_safety_margins')
    need(all(counts[id(obj)] == 1 for obj in (wrapper, array, *rows)),
         'The reviewed Itinerary shares native safety-margin objects')
    old_length = sum(project.model(key).contents[9].values[1] for key in reviewed['original_directed_edges'])
    prefix = reviewed['prefix_length_change_m']
    suffix = reviewed['suffix_length_change_m']
    first, last = max(0, -prefix), old_length + min(0, suffix)
    original = _margin_values(rows)
    positions = [row['position_m'] for row in original]
    need(all(0 <= value <= old_length for value in positions)
         and all(a <= b for a, b in zip(positions, positions[1:]))
         and all(math.isfinite(row['safety_margin_m']) for row in original),
         'Safety-margin positions must be sorted within the original route and the values finite')
    retained = [row for row in original if first <= row['position_m'] <= last]
    if first > 0 and not any(row['position_m'] == first for row in retained):
        previous = next((row for row in reversed(original) if row['position_m'] < first), None)
        if previous is not None:
            retained.insert(0, {**previous, 'position_m': float(first)})
    revised = [{**row, 'position_m': _float32(row['position_m'] + prefix)} for row in retained]
    source_positions = sorted({float(first), float(last), *(row['position_m'] for row in retained)})
    target_positions = [_float32(value + prefix) for value in source_positions]
    need(all(a < b for a, b in zip(target_positions, target_positions[1:])),
         'Float32 mapping would collapse distinct safety-margin positions or a common route boundary')
    return {'before': original, 'after': revised,
            'shared_original_span_m': [first, last], 'shared_revised_span_m': [first + prefix, last + prefix]}


def _replace_definition(project, catalog, changes, definition, entry, selected, margin_rows):
    owner = project.owners[id(definition)][0]
    old_root = project.roots[owner]
    origin_list, origin_rows = _owner_array(old_root, definition)
    name = ident(definition)[0]
    target_doc = selected[0][0]
    target_root = project.roots[target_doc]
    references = [{'document': doc, **ref(path)} for doc, path in selected]
    moved = path_functions.clone(definition)
    moved.contents[0].value = path_functions.array_like(definition.contents[0].value, [selected[0][1]])
    moved.contents[4].value = path_functions.array_like(definition.contents[4].value, [inf(path, doc) for doc, path in selected])
    if margin_rows is not None or target_doc != owner:
        moved.contents[5].value = _copy_margins(definition, margin_rows)
    if target_doc == owner:
        changes.contents(old_root, origin_list, [moved if item is definition else item for item in origin_rows])
    else:
        need(ident(definition)[1:] == (-1, -1), 'A worksheet-owned destination identity needs a separate migration review')
        target_list, target_rows = _owner_array(target_root)
        changes.contents(old_root, origin_list, [item for item in origin_rows if item is not definition])
        changes.contents(target_root, target_list, target_rows + [moved])
    new_row = _catalog_row(name, project.paths[target_doc], references)
    catalog_list, rows, counts = _catalog_array(catalog)
    need(counts[id(entry)] == 1, 'Selected native DestInfo row has another owner')
    changes.contents(catalog, catalog_list, [new_row if item is entry else item for item in rows])
    return target_doc, moved, references


def rebind_station_reference_endpoints(documents, paths, dest_blob, moved, requests):
    """Save approved existing-Route sequences after the paired Station Vertex type change."""
    need(type(requests) is list and 1 <= len(requests) <= 1000, 'Review each affected native Itinerary endpoint explicitly')
    project = _project(documents, paths, dest_blob)
    memberships = _station_pair(project, moved)
    catalog, version = writer.load_next_compatible(dest_blob)
    _, rows, _ = _catalog_array(catalog)
    entries = {path_functions.string(row.contents[1].value): row for row in rows}
    definitions = {ident(item)[0]: item for item in project.dests}
    baseline = {name: _snapshot(project, item) for name, item in definitions.items()}
    before_movements = _movement_manifest(project)
    graph_roots = {**project.roots, '$dest_catalog': catalog}
    fingerprints = {name: writer.fingerprint(root) for name, root in graph_roots.items()}
    changes = Changes()
    used = set()
    reports, created = [], []
    path_index = _path_index(project)
    expected = dict(baseline)
    for request in requests:
        required = {'itinerary', 'replacement_routes'}
        need(type(request) is dict and required <= request.keys()
             and request.keys() <= required | {'map_itinerary_safety_margins'}
             and type(request.get('map_itinerary_safety_margins', False)) is bool,
             'Each review needs an exact Itinerary name and its ordered replacement Routes')
        name = request['itinerary']
        need(name in definitions and name in entries and name not in used, 'Select a distinct existing Itinerary for endpoint review')
        used.add(name)
        definition = definitions[name]
        need(all('kind' not in row for row in _route_refs_of(project, definition)),
             'Endpoint rebinding of an Itinerary containing Shunting requires a separate operation')
        previous = baseline[name]['movement']
        selected, movement, approved = _route_sequence(project, request['replacement_routes'])
        reviewed = _endpoint_change(project, previous, movement, moved, memberships)
        old_owner = baseline[name]['owner']
        root = project.roots[old_owner]
        counts = incoming_counts(root)
        need(all(counts[id(definition.contents[slot].value)] == 1 for slot in (0, 4)),
             'The reviewed Itinerary shares a native first-Path or ExtInfo array')
        margins = _mapped_margins(project, definition, reviewed, counts, request.get('map_itinerary_safety_margins', False))
        new_margins = None if margins is None else margins['after']
        selected_paths, new_paths = _select_paths(project, catalog, changes, selected, approved,
                                                 _existing_path_objects(project, definition), path_index)
        owner, replacement, references = _replace_definition(project, catalog, changes, definition, entries[name],
                                                              selected_paths, new_margins)
        expected[name] = {'owner': owner, 'definition': path_functions.info(replacement), 'movement': movement,
                          'safety_margins': [] if new_margins is None else new_margins}
        reports.append({'itinerary': name, 'old_owner': old_owner, 'new_owner': owner, 'original_start': previous[0],
                        'original_end': previous[-1], 'replacement_start': movement[0], 'replacement_end': movement[-1],
                        'replacement_routes': request['replacement_routes'], 'replacement_paths': references,
                        'mapped_safety_margins': margins, **reviewed})
        created.extend(new_paths)
    output = {name: writer.dump_verified(root, project.versions[name]) for name, root in project.roots.items()
              if id(root) in changes.touched}
    new_catalog = writer.dump_verified(catalog, version)
    fresh = _project({**documents, **output}, paths, new_catalog)
    actual = {ident(item)[0]: item for item in fresh.dests}
    need({name: _snapshot(fresh, item) for name, item in actual.items()} == expected,
         'A native Itinerary or its exact ordered Path binding differs after archive reload')
    for row in reports:
        need(_route_refs_of(fresh, actual[row['itinerary']]) == row['replacement_routes'],
             'The native Route list differs from the approved direction after reload')
    after_movements = _movement_manifest(fresh)
    new_keys = {('path', (row['document'], row['start_id']), (row['name'], row['array_id'], row['start_id'])) for row in created}
    original_routes_and_paths = {key for key in before_movements if key[0] != 'itinerary'}
    revised_routes_and_paths = {key for key in after_movements if key[0] != 'itinerary'}
    need(revised_routes_and_paths == original_routes_and_paths | new_keys,
         'The native Route/Path closure added or lost an unexpected saved movement')
    need(all(after_movements.get(key) == value for key, value in before_movements.items()
             if key[0] != 'itinerary' or key[2][0] not in used),
         'An original Route, shared Path, or unselected Itinerary changed during endpoint rebinding')
    changes.restore()
    need(all(writer.fingerprint(root) == fingerprints[name] for name, root in graph_roots.items()),
         'A field outside the reviewed native endpoint transaction changed')
    return output, new_catalog, {'endpoint_rebindings': reports, 'created_paths': created, 'changed_documents': sorted(output),
                                 'catalog_bindings_verified': True, 'original_routes_and_paths_preserved': True,
                                 'unselected_itineraries_preserved': True, 'native_runtime_verified': False}
