"""Edit saved Route protection and signal controls within known layouts."""

from typing import Annotated

from pydantic import Field, StrictBool, StrictFloat, StrictInt, model_validator

from ..errors import APIError
from . import path_functions as path, route_factory, writer
from .bundle_tools import CourseBundles, Source
from .current_shunting_workflow.inventory import DOC3, end_layout, layout
from .graph_references import incoming_counts
from .itinerary_edit_tools import bound_dest_catalog, run_infrastructure_paths
from .movement_edits import _movement_project, verify_itinerary_movements
from .next_tools import NextFunctions, Save
from .operation_tools import I32, Changes, Name, RouteSelector
from .signal_protection.core import real
from .tools import Input, PathText, sha


Speed = Annotated[StrictFloat | StrictInt, Field(ge=0, le=1000, allow_inf_nan=False)]
Seconds = Annotated[StrictFloat | StrictInt, Field(ge=0, le=86400, allow_inf_nan=False)]
OCCUPIED_FLAGS = {
    'allow_occupied_entry': 1,
    'occupied_entry_use_speed': 2,
    'occupied_entry_use_time': 4,
    'discrete_for_moving_block': 8,
}
require = route_factory.require


class ProtectionChanges(Changes):
    allow_occupied_entry: StrictBool | None = None
    occupied_entry_use_speed: StrictBool | None = None
    occupied_entry_use_time: StrictBool | None = None
    discrete_for_moving_block: StrictBool | None = None
    occupied_entry_speed_kmh: Speed | None = None
    occupied_entry_wait_s: Seconds | None = None
    slow_speed_only_for_head: StrictBool | None = None
    release_group_end_ids: Annotated[list[I32], Field(min_length=2, max_length=1000)] | None = None
    slow_speed_zone_end_ids: Annotated[list[I32], Field(min_length=2, max_length=2)] | None = None
    clear_slow_speed_zone: StrictBool | None = None
    signal_aspects: Annotated[list[I32], Field(min_length=1, max_length=64)] | None = None


class EditRouteProtection(Save):
    source: Source
    route: RouteSelector
    changes: ProtectionChanges


class EditRouteMovement(Save):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=1, max_length=100)]
    target_document: Name
    dest_catalog: Source
    route: RouteSelector
    end_ids: Annotated[list[I32], Field(min_length=2, max_length=1000)]
    release_group_end_ids: Annotated[list[I32], Field(min_length=2, max_length=1000)]
    slow_speed_zone_end_ids: Annotated[list[I32], Field(min_length=2, max_length=2)] | None = None


class RouteZoneEnd(Input):
    document: Name
    end_id: I32


class EditCrossDocumentRoute(Input):
    project_run: Source
    documents: Annotated[dict[Name, Source], Field(min_length=2, max_length=100)]
    target_document: Name
    dest_catalog: Source
    route: RouteSelector
    primary_end_ids: Annotated[list[I32], Field(min_length=1, max_length=1000)]
    continuation_end_ids: Annotated[list[I32], Field(min_length=1, max_length=1000)]
    primary_release_group_end_ids: Annotated[list[I32], Field(max_length=1000)] | None = None
    continuation_release_group_end_ids: Annotated[list[I32], Field(max_length=1000)] | None = None
    slow_speed_zone_ends: Annotated[list[RouteZoneEnd], Field(max_length=2)] | None = None
    signal_aspects: Annotated[list[I32], Field(min_length=1, max_length=64)] | None = None
    preview_only: StrictBool = True
    target_directory: PathText | None = None

    @model_validator(mode='after')
    def check_output(self):
        if self.target_document not in self.documents:
            raise ValueError('The primary Route document must be supplied')
        if not self.preview_only and self.target_directory is None:
            raise ValueError('Saving requires a new bundle directory')
        if self.slow_speed_zone_ends is not None and len(self.slow_speed_zone_ends) not in (0, 2):
            raise ValueError('Supply two slow-zone endpoints or an empty list to clear the zone')
        return self


def _route_shape(route):
    require(writer.kind(route) == 'OTRoute' and route.clazz.superclass is not None, 'Expected a native Route')
    version = route.clazz.superclass.version
    chain, encodings = path.SHAPES['OTRoute']
    require(version in (5, 6), 'Only saved SecurityArray versions 5 and 6 are supported')
    if version == 5:
        chain = [chain[0], ('OTSecurityArray', 5), *chain[2:]]
        encodings = encodings[:10] + encodings[11:]
    layout(route, chain, encodings)
    return 10 if version == 5 else 11


def _select_route(root, reference):
    version = root.clazz.version
    require(version in (3, 4), 'Expected a saved Document3 or Document4')
    layout(root, [('OTDocument', version), ('NSObject', 0)], DOC3 + (['@', '@'] if version == 4 else []))
    models = path.mutable_array(root.contents[2].value)
    by_id = {model.contents[0].value: model for model in models}
    require(len(by_id) == len(models), 'Duplicate document model identity')
    owner = by_id.get(reference['start_id'])
    require(owner is not None and writer.kind(owner) == 'OTEndModel', 'Expected an ordinary local Route owner')
    end_layout(owner)
    holder = owner.contents[15].value
    routes = route_factory.wrapper(holder, 'OTRouteList')
    counts = incoming_counts(root)
    require(counts[id(root)] == 0 and counts[id(holder)] == 1 and counts[id(holder.contents[0].value)] == 1,
            'Shared Route ownership list')
    for route in routes:
        _route_shape(route)
    matches = [route for route in routes if path.string(route.contents[1].value) == reference['name']]
    require(len(matches) == 1 and matches[0].contents[2].values == [reference['array_id'], reference['start_id']],
            'Route name and IDs must resolve exactly at its owner')
    route = matches[0]
    require(sum(item.contents[2].values == route.contents[2].values for item in routes) == 1,
            'Route identity is ambiguous in its owner list')
    for model in models:
        if model is not owner and writer.kind(model) in ('OTEndModel', 'OTConnModel', 'OTStationEndModel'):
            end_layout(model)
            other = model.contents[15].value
            require(other is None or route not in route_factory.wrapper(other, 'OTRouteList'),
                    'Route is present at a second owner')

    require(route.contents[5].values[4] == -1, 'A cross-document Route and its continuation must be edited together')
    nodes = path.mutable_array(route.contents[0].value)
    require(len(nodes) >= 2 and nodes[0] is owner and len(set(map(id, nodes))) == len(nodes),
            'Expected a simple local Route beginning at its owner')
    for node in nodes:
        require(writer.kind(node) == 'OTEndModel' and by_id.get(node.contents[0].value) is node,
                'Route End is not an ordinary local model')
        end_layout(node)
    return route, _route_shape(route), nodes, routes, counts, by_id


def _check_connections(nodes, by_id):
    for first, last in zip(nodes, nodes[1:]):
        paired = by_id.get(first.contents[8].value)
        require(paired is not None and writer.kind(paired) == 'OTEndModel', 'Missing local paired End')
        end_layout(paired)
        require(paired is not first and paired.contents[8].value == first.contents[0].value,
                'End pair is not reciprocal')
        valid = set()
        for edge in (paired.contents[9].value, paired.contents[10].value):
            if edge is not None:
                route_factory.layout(edge, 'OTEdgeModel', 3, route_factory.EDGE, graphic=True)
                ends = [edge.contents[index].value for index in (7, 8)]
                if last in ends and paired in ends:
                    require(by_id.get(edge.contents[0].value) is edge and edge.contents[9].values[1] > 0
                            and edge in (last.contents[9].value, last.contents[10].value),
                            'Route Edge is not a reciprocal positive-length document member')
                    valid.add(id(edge))
        require(len(valid) == 1, 'Disconnected or ambiguous local Route movement')


def _zone_nodes(nodes, ids):
    by_id = {node.contents[0].value: (index, node) for index, node in enumerate(nodes)}
    require(all(type(value) is int and value in by_id for value in ids), 'Select exact Ends of this Route')
    entries = [by_id[value] for value in ids]
    positions = [index for index, _ in entries]
    require(positions == sorted(set(positions)), 'Choose distinct Route Ends in movement order')
    return [node for _, node in entries]


def _indications(route):
    holder = route.contents[4].value
    items = route_factory.wrapper(holder, 'OTSigIndList')
    for item in items:
        route_factory.layout(item, 'OTSigInd', 0, ['i', '@'])
        require(item.contents[1].value is route, 'Signal indication does not belong to this Route')
    return holder, items


def _protection_values(route, flags):
    occupied, speed, wait = route.contents[6].values
    release, zone_start, zone_end = route.contents[flags + 1].values
    return {
        **{name: bool(occupied & bit) for name, bit in OCCUPIED_FLAGS.items()},
        'occupied_entry_speed_kmh': speed,
        'occupied_entry_wait_s': wait,
        'slow_speed_only_for_head': bool(route.contents[flags].value & 2),
        'release_group_end_ids': [node.contents[0].value for node in path.mutable_array(release)],
        'slow_speed_zone_end_ids': [zone_start.contents[0].value, zone_end.contents[0].value]
        if zone_start is not None and zone_end is not None else None,
        'signal_aspects': [item.contents[0].value for item in _indications(route)[1]],
    }


def _zone_fragment_ids(route, flags):
    return [node.contents[0].value if node is not None else None
            for node in route.contents[flags + 1].values[1:]]


def _replace_indications(route, aspects, owner_routes, nodes, counts, by_id, *, require_signal_match=False):
    owner = nodes[0]
    signal = owner.contents[11].value
    route_factory.layout(signal, 'OTSignalModel', 11, route_factory.SIGNAL, graphic=True)
    require(signal.contents[7].value is owner and by_id.get(signal.contents[0].value) is signal
            and signal.contents[8].values[0] in (1, 2, 24, 25, 26),
            'Route lacks a reciprocal local main signal')
    holder, existing = _indications(route)
    require(counts[id(holder)] == 1 and counts[id(holder.contents[0].value)] == 1
            and existing and all(counts[id(item)] == 1 for item in existing),
            'Signal indications need an exclusively owned native template')
    # A Route can only use aspect codes observed at its own main signal. Do
    # not manufacture code meanings from a different signalling system.
    observed = {item.contents[0].value for candidate in owner_routes for item in _indications(candidate)[1]}
    if require_signal_match:
        from .signal_operating_fields import _indication_records

        _, signal_codes = _indication_records(signal.contents[10].value, owner)
        observed.intersection_update(signal_codes)
    require(1 <= len(aspects) <= min(64, len(observed)) and len(set(aspects)) == len(aspects)
            and set(aspects) <= observed, 'Use distinct aspect codes already present at this main signal')
    records = []
    for code in aspects:
        item = path.clone(existing[0])
        item.contents[0].value = code
        records.append(item)
    replacement = path.clone(holder)
    replacement.contents[0].value = path.array_like(holder.contents[0].value, records)
    return replacement


def edit_protection(data, reference, changes):
    require(type(changes) is dict and changes and changes.keys() <= ProtectionChanges.model_fields.keys(),
            'At least one supported protection field is required')
    root, version = writer.load_next_compatible(data)
    route, flags, nodes, owner_routes, counts, by_id = _select_route(root, reference)
    before = _protection_values(route, flags)
    group = flags + 1
    snapshots = {index: list(route.contents[index].values) for index in (4, 6, flags, group)}
    expected = dict(changes)

    if OCCUPIED_FLAGS.keys() & changes.keys():
        old = route.contents[6].values[0]
        require(type(old) is int and 0 <= old <= 15, 'Unknown occupied-entry flag encoding')
        for field, bit in OCCUPIED_FLAGS.items():
            if field in changes:
                old = old | bit if changes[field] else old & ~bit
        route.contents[6].values[0] = old
    for field, index in (('occupied_entry_speed_kmh', 1), ('occupied_entry_wait_s', 2)):
        if field in changes:
            expected[field] = route.contents[6].values[index] = real(changes[field])
    if 'slow_speed_only_for_head' in changes:
        value = route.contents[flags].value
        require(type(value) is int and 0 <= value <= 3, 'Unknown Route reservation/head flag encoding')
        route.contents[flags].value = (value & ~2) | (2 if changes['slow_speed_only_for_head'] else 0)

    if {'release_group_end_ids', 'slow_speed_zone_end_ids', 'clear_slow_speed_zone'} & changes.keys():
        _check_connections(nodes, by_id)
    if 'release_group_end_ids' in changes:
        boundaries = _zone_nodes(nodes, changes['release_group_end_ids'])
        require(len(boundaries) >= 2 and boundaries[0] is nodes[0] and boundaries[-1] is nodes[-1],
                'Release boundaries must include the first and last End of the Route')
        original = route.contents[group].values[0]
        require(counts[id(original)] == 1, 'Shared Route release boundary list')
        route.contents[group].values[0] = path.array_like(original, boundaries)
    if 'slow_speed_zone_end_ids' in changes:
        require(not changes.get('clear_slow_speed_zone'), 'Choose a new slow-speed zone or clear it')
        route.contents[group].values[1:] = _zone_nodes(nodes, changes['slow_speed_zone_end_ids'])
    if 'clear_slow_speed_zone' in changes:
        require(changes['clear_slow_speed_zone'] is True, 'Omit clear_slow_speed_zone when retaining the zone')
        route.contents[group].values[1:] = [None, None]
        del expected['clear_slow_speed_zone']
        expected['slow_speed_zone_end_ids'] = None
    if 'signal_aspects' in changes:
        route.contents[4].value = _replace_indications(route, changes['signal_aspects'], owner_routes, nodes, counts, by_id)

    output = writer.dump_verified(root, version)
    reloaded, _ = writer.load_next_compatible(output)
    saved, saved_flags, *_ = _select_route(reloaded, reference)
    after = _protection_values(saved, saved_flags)
    require(after == {**before, **expected}, 'Route protection fields differ after archive reload')
    for index, values in snapshots.items():
        route.contents[index].values[:] = values
    old_root, old_version = writer.load_next_compatible(data)
    require(writer.dump_verified(root, version) == writer.dump_verified(old_root, old_version),
            'Unexpected change outside the selected Route protection fields')
    return output, {'operation': 'edit_route_protection', 'route': reference, 'before': before,
                    'after': after, 'running_time_revalidation_required': True, 'native_runtime_verified': False}


def _path_movements(project):
    return {(project.owners[id(item)], path.string(item.contents[1].value), item.contents[2].values[0]):
            project.path_view(item)[0] for item in project.paths_objects}


def _affected_movements(before, after):
    before_paths, after_paths = _path_movements(before), _path_movements(after)
    require(before_paths.keys() == after_paths.keys(), 'Movement edit changed Path identities')
    paths = [{'document': owner[0], 'start_id': owner[1], 'name': name, 'array_id': array_id}
             for (owner, name, array_id), original in before_paths.items()
             if original != after_paths[owner, name, array_id]]
    return {'paths': paths, 'itineraries': verify_itinerary_movements(before, after)}


def edit_movement(documents, document_paths, catalog, target, reference, end_ids, release_ids, zone_ids=None):
    project = _movement_project(documents, document_paths, catalog)
    root, version = project.roots[target], project.versions[target]
    route, flags, old_nodes, _, counts, _ = _select_route(root, reference)
    require(len(end_ids) >= 2 and len(set(end_ids)) == len(end_ids)
            and all(type(value) is int for value in end_ids), 'Use a simple sequence of directional Ends')
    keys = [(target, end_id) for end_id in end_ids]
    old_keys = project.route_view(route)
    require(keys[0] == old_keys[0] and keys[-1] == old_keys[-1],
            'Route movement must preserve its two directional main-signal Ends')
    nodes = [project.model(key) for key in keys]
    release_nodes = _zone_nodes(nodes, release_ids)
    require(len(release_nodes) >= 2 and release_nodes[0] is nodes[0] and release_nodes[-1] is nodes[-1],
            'Release boundaries must include the first and last End')

    protection = route.contents[flags + 1].values
    old_zone = protection[1:]
    if zone_ids is None and any(node is not None for node in old_zone):
        require(all(node in nodes for node in old_zone), 'Existing slow-speed zone leaves the new Route; specify new endpoints')
        zone_ids = [node.contents[0].value for node in old_zone]
    zone = [None, None] if zone_ids is None else _zone_nodes(nodes, zone_ids)
    require(len(zone) == 2, 'Slow-speed zone requires exactly two directional Ends')
    old_path = route.contents[0].value
    old_protection = list(protection)
    require(counts[id(old_path)] == 1 and counts[id(protection[0])] == 1, 'Shared Route movement or release list')
    route.contents[0].value = path.array_like(old_path, nodes)
    protection[:] = [path.array_like(protection[0], release_nodes), *zone]
    output = writer.dump_verified(root, version)

    checked = _movement_project({**documents, target: output}, document_paths, catalog)
    saved, saved_flags, _, _, _, _ = _select_route(checked.roots[target], reference)
    fields = _protection_values(saved, saved_flags)
    require(checked.route_view(saved) == keys and fields['release_group_end_ids'] == release_ids
            and fields['slow_speed_zone_end_ids'] == zone_ids, 'Route movement or boundaries differ after reload')
    affected = _affected_movements(project, checked)
    route.contents[0].value = old_path
    protection[:] = old_protection
    original_root, original_version = writer.load_next_compatible(documents[target])
    require(writer.dump_verified(root, version) == writer.dump_verified(original_root, original_version),
            'Unexpected change outside the Route movement and boundaries')
    return output, {'operation': 'replace_route_movement', 'route': reference, 'old_end_ids':
        [node.contents[0].value for node in old_nodes], 'new_end_ids': end_ids,
        'affected': affected,
        'running_time_revalidation_required': True, 'native_runtime_verified': False}


def _change_route_fragment(route, nodes, counts, release_ids, *, primary, zone_ids=None):
    group = route.contents[_route_shape(route) + 1].values
    old_nodes = route.contents[0].value
    old_groups, *zone = group
    old_index = route.contents[5].values[4]
    require(counts[id(old_nodes)] == 1 and counts[id(old_groups)] == 1,
            'Route movement or release group list is shared')
    new_zone = zone
    if zone_ids is not None:
        by_id = {node.contents[0].value: node for node in nodes}
        require(len(zone_ids) == 2 and all(value is None or value in by_id for value in zone_ids),
                'Choose slow-speed zone endpoints in the saved fragment')
        new_zone = [by_id[value] if value is not None else None for value in zone_ids]
    require(len(new_zone) == 2 and all(end is None or end in nodes for end in new_zone),
            'Existing slow-speed zone endpoints must remain in this fragment')
    require(None in new_zone or nodes.index(new_zone[0]) < nodes.index(new_zone[1])
            or (primary and new_zone[0] is nodes[-1] and new_zone[1] is nodes[-1]),
            'Slow-speed zone order changes in this fragment')
    if release_ids is None:
        releases = path.mutable_array(old_groups)
        require(all(end in nodes for end in releases), 'Supply new release group Ends for the changed fragment')
        releases = _zone_nodes(nodes, [end.contents[0].value for end in releases])
    else:
        releases = _zone_nodes(nodes, release_ids)
    route.contents[0].value = path.array_like(old_nodes, nodes)
    group[0] = path.array_like(old_groups, releases)
    group[1:] = new_zone
    if primary:
        route.contents[5].values[4] = len(nodes)

    def restore():
        route.contents[0].value = old_nodes
        group[0] = old_groups
        group[1:] = zone
        route.contents[5].values[4] = old_index

    return [end.contents[0].value for end in releases], restore


def _move_continuation_between_owners(project, fragment, old_owner, new_owner, identity):
    if old_owner == new_owner:
        return lambda: None
    old_holder = project.model(old_owner).contents[15].value
    new_holder = project.model(new_owner).contents[15].value
    old_items = route_factory.wrapper(old_holder, 'OTRouteList')
    new_items = route_factory.wrapper(new_holder, 'OTRouteList')
    counts = incoming_counts(project.roots[new_owner[0]])
    require(all(counts[id(holder)] == 1 and counts[id(holder.contents[0].value)] == 1
                for holder in (old_holder, new_holder)), 'Continuation owner Route lists are shared')
    require(all(path.string(item.contents[1].value) != identity[0]
                and item.contents[2].values != list(identity[1:]) for item in new_items),
            'New receiving connector has an ambiguous continuation name or ID')
    require(counts[id(fragment)] == 1 + len(_indications(fragment)[1]),
            'Continuation has other direct saved references')
    writer.set_elements(old_holder.contents[0].value, [item for item in old_items if item is not fragment])
    writer.set_elements(new_holder.contents[0].value, [*new_items, fragment])

    def restore():
        writer.set_elements(old_holder.contents[0].value, old_items)
        writer.set_elements(new_holder.contents[0].value, new_items)

    return restore


def _route_owner_counts(project, owner):
    root = project.roots[owner[0]]
    holder = project.model(owner).contents[15].value
    counts = incoming_counts(root)
    require(counts[id(root)] == 0 and counts[id(holder)] == 1 and counts[id(holder.contents[0].value)] == 1,
            'Document or Route ownership list is shared')
    return counts


def _zone_fragments(left, right, zone):
    if zone is None:
        return None, None
    if not zone:
        return [None, None], [None, None]
    chain = [*left, *right]
    require(len(zone) == 2 and all(key in chain for key in zone) and chain.index(zone[0]) < chain.index(zone[1]),
            'The slow-speed zone must run forward along the saved Route')
    start, finish = zone
    if finish in left:
        return [start[1], finish[1]], [None, None]
    if start in right:
        return [None, None], [start[1], finish[1]]
    return [start[1], left[-1][1]], [None, finish[1]]


def edit_cross_document_movement(documents, document_paths, catalog, target, reference,
                                 primary_end_ids, continuation_end_ids,
                                 primary_release_group_end_ids=None, continuation_release_group_end_ids=None,
                                 *, slow_speed_zone_ends=None, signal_aspects=None):
    project = _movement_project(documents, document_paths, catalog)
    identity = (reference['name'], reference['array_id'], reference['start_id'])
    owner = (target, reference['start_id'])
    primary = project.owned(owner, 'OTRoute', identity)
    old_chain = project.route_view(primary)
    records = [row for row in project.continuations if row['source_document'] == target and row['route'] == reference]
    require(len(records) == 1, 'Expected one existing cross-document Route continuation')
    original = records[0]
    remote = original['target_document']
    old_remote_owner = (remote, original['target_connector'])
    fragment = project.owned(old_remote_owner, 'OTRoute', identity)
    primary_before = [item.contents[0].value for item in _indications(primary)[1]]
    primary_after = primary_before if signal_aspects is None else signal_aspects
    continuation_aspects = [item.contents[0].value for item in _indications(fragment)[1]]
    for ids in (primary_end_ids, continuation_end_ids):
        require(1 <= len(ids) <= 1000 and all(type(end_id) is int for end_id in ids),
                'Explicit bounded directional End IDs required for both saved fragments')
    left = [(target, end_id) for end_id in primary_end_ids]
    right = [(remote, end_id) for end_id in continuation_end_ids]
    chain = [*left, *right]
    require(left and right and len(set(chain)) == len(chain), 'Use two nonempty, nonrepeating saved fragments')
    require(chain[0] == old_chain[0] and chain[-1] == old_chain[-1],
            'Route movement must preserve its two directional main-signal Ends')
    nodes = [project.model(key) for key in chain]
    require(all(writer.kind(node) == 'OTEndModel' for node in nodes), 'Choose ordinary directional End objects')
    connector = project.related(left[-1])
    receiving_connector = project.block_end(connector)
    require(receiving_connector[0] == remote, 'The chosen connector does not pair these two documents')
    for previous, following in zip(chain, chain[1:]):
        project.edge_between(previous, following)

    new_zone = None if slow_speed_zone_ends is None else [(row['document'], row['end_id']) for row in slow_speed_zone_ends]
    primary_zone, receiving_zone = _zone_fragments(left, right, new_zone)
    snapshots = {}
    boundaries = {}
    zones = {}
    for saved_owner, route, ends, requested, zone, first in (
            (owner, primary, nodes[:len(left)], primary_release_group_end_ids, primary_zone, True),
            (old_remote_owner, fragment, nodes[len(left):], continuation_release_group_end_ids, receiving_zone, False)):
        name = saved_owner[0]
        boundaries[name], snapshots[name] = _change_route_fragment(
            route, ends, _route_owner_counts(project, saved_owner), requested, primary=first, zone_ids=zone)
        zones[name] = _zone_fragment_ids(route, _route_shape(route))
    if primary_release_group_end_ids is not None or continuation_release_group_end_ids is not None:
        release_keys = [(name, end_id) for name in (target, remote) for end_id in boundaries[name]]
        require(release_keys and release_keys[0] == chain[0] and release_keys[-1] == chain[-1],
                'Explicit release groups must cover the Route start and terminal End')
    previous_indications = primary.contents[4].value
    if signal_aspects is not None:
        owner_routes = route_factory.wrapper(project.model(owner).contents[15].value, 'OTRouteList')
        primary.contents[4].value = _replace_indications(primary, signal_aspects, owner_routes, nodes,
                                                         _route_owner_counts(project, owner), project.byid[target],
                                                         require_signal_match=True)
    undo_move = _move_continuation_between_owners(project, fragment, old_remote_owner, receiving_connector, identity)
    outputs = {name: writer.dump_verified(project.roots[name], project.versions[name]) for name in (target, remote)}
    checked = _movement_project({**documents, **outputs}, document_paths, catalog)
    saved_primary = checked.owned(owner, 'OTRoute', identity)
    saved_fragment = checked.owned(receiving_connector, 'OTRoute', identity)
    require(checked.route_view(saved_primary) == chain and checked.route_view(saved_fragment) == right
            and saved_primary.contents[5].values[4] == len(left),
            'Saved paired Route continuity differs after fresh reload')
    for name, route in ((target, saved_primary), (remote, saved_fragment)):
        flags = _route_shape(route)
        saved = _protection_values(route, flags)
        require(saved['release_group_end_ids'] == boundaries[name], 'Saved release boundaries differ after reload')
        require(_zone_fragment_ids(route, flags) == zones[name], 'Saved slow-speed zone fragments differ after reload')
        expected_aspects = primary_after if route is saved_primary else continuation_aspects
        require(saved['signal_aspects'] == expected_aspects, 'Saved primary or continuation indications differ after reload')
    affected = _affected_movements(project, checked)

    undo_move()
    primary.contents[4].value = previous_indications
    for name, restore in snapshots.items():
        restore()
        old_root, old_version = writer.load_next_compatible(documents[name])
        require(writer.dump_verified(project.roots[name], project.versions[name]) == writer.dump_verified(old_root, old_version),
                'Unexpected change outside the selected Route movement and continuation owner')
    return outputs, {'operation': 'replace_cross_document_route_movement', 'route': reference,
                     'old_directional_ends': old_chain, 'new_directional_ends': chain,
                     'old_connector_pair': [(target, original['source_connector']), old_remote_owner],
                     'new_connector_pair': [connector, receiving_connector],
                     'release_group_end_ids': boundaries, 'slow_speed_zone_fragment_end_ids': zones, 'affected': affected,
                     'primary_signal_aspects': {'before': primary_before, 'after': primary_after},
                     'continuation_signal_aspects': continuation_aspects,
                     'dest_catalog_unchanged': True, 'running_time_revalidation_required': True,
                     'native_runtime_verified': False}


class RouteProtectionEdits(NextFunctions, CourseBundles):
    def edit(self, args):
        source, data, _, _ = self.checked(args.source)
        if source.suffix != '.opentrack' or (not args.preview_only and self.path(args.target_path).suffix != '.opentrack'):
            raise APIError('DOCUMENT_SCOPE', 'Route protection editing requires .opentrack documents')
        try:
            output, report = edit_protection(data, args.route.model_dump(), args.changes.model_dump(exclude_unset=True))
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('CURRENT_ROUTE_PROTECTION_EDIT', str(exc)[:500]) from exc
        return self.finish(args, source, data, output, report)

    def movement(self, args):
        inputs = {name: self.checked(spec) for name, spec in args.documents.items()}
        if args.target_document not in inputs or len({item[0] for item in inputs.values()}) != len(inputs):
            raise APIError('DOCUMENT_SCOPE', 'Supply distinct project documents including the target')
        if not args.preview_only and self.path(args.target_path).suffix != '.opentrack':
            raise APIError('DOCUMENT_SCOPE', 'A new .opentrack target is required')
        run_path, run, check_scope, scope = self.checked_document_list(args, inputs)
        catalog_path, catalog, _, _ = self.checked(args.dest_catalog)
        bound_dest_catalog(self, run_path, run, catalog_path)
        source, data, _, _ = inputs[args.target_document]
        try:
            output, report = edit_movement({name: item[1] for name, item in inputs.items()},
                run_infrastructure_paths(run), catalog, args.target_document, args.route.model_dump(),
                args.end_ids, args.release_group_end_ids, args.slow_speed_zone_end_ids)
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('CURRENT_ROUTE_MOVEMENT_EDIT', str(exc)[:500]) from exc
        report['document_scope'] = scope
        dependencies = {run_path: run, catalog_path: catalog, **{item[0]: item[1] for name, item in inputs.items()
                                                               if name != args.target_document}}
        return self.finish(args, source, data, output, report, dependencies, check_scope)

    def cross_document_movement(self, args):
        inputs = {name: self.checked(spec) for name, spec in args.documents.items()}
        if len({item[0] for item in inputs.values()}) != len(inputs):
            raise APIError('DOCUMENT_SCOPE', 'Supply distinct project infrastructure documents')
        run_path, run, check_scope, scope = self.checked_document_list(args, inputs)
        catalog_path, catalog, _, _ = self.checked(args.dest_catalog)
        bound_dest_catalog(self, run_path, run, catalog_path)
        if args.target_directory is not None and self.path(args.target_directory).is_relative_to(run_path.parent):
            raise APIError('DOCUMENT_SCOPE', 'Publish the paired archives outside the source project')
        try:
            outputs, report = edit_cross_document_movement(
                {name: item[1] for name, item in inputs.items()}, run_infrastructure_paths(run), catalog,
                args.target_document, args.route.model_dump(), args.primary_end_ids, args.continuation_end_ids,
                args.primary_release_group_end_ids, args.continuation_release_group_end_ids,
                slow_speed_zone_ends=None if args.slow_speed_zone_ends is None
                else [row.model_dump() for row in args.slow_speed_zone_ends],
                signal_aspects=args.signal_aspects,
            )
        except (ValueError, TypeError, KeyError, IndexError, OverflowError) as exc:
            raise APIError('CURRENT_CROSS_DOCUMENT_ROUTE_EDIT', str(exc)[:500]) from exc
        members = {inputs[name][0].name: blob for name, blob in outputs.items()}
        dependencies = {run_path: run, catalog_path: catalog, **{item[0]: item[1] for item in inputs.values()}}
        manifest = {'format': 'opentrack-cross-document-route-edit-v1',
                    'files': {name: {'sha256': sha(blob), 'bytes': len(blob)} for name, blob in members.items()},
                    'replacement_for': {inputs[name][0].name: str(inputs[name][0].relative_to(self.root)) for name in outputs},
                    'sources': {str(source.relative_to(self.root)): {'sha256': sha(blob)} for source, blob in dependencies.items()},
                    'document_scope': scope, 'complete_relocated_project': False}
        result = {'preview_only': args.preview_only, 'saved': False, 'manifest': manifest,
                  'bundle_type': 'Cross-document Route archive pair', 'change_report': report,
                  'fresh_archive_reload_verified': True, 'native_application_started': False,
                  'complete_relocated_project': False}
        return self.publish_bundle(inputs=dependencies, members=members, manifest=manifest, result=result,
                                   target_directory=args.target_directory, scope_check=check_scope,
                                   windows_publication=True)


def tool_definitions(root):
    service = RouteProtectionEdits(root)
    return [('opentrack_edit_current_route_protection',
             'Edit saved local Route occupied-entry and moving-block flags, slow-speed zone and head-only '
             'flag, ordered release boundaries and existing main-signal aspect codes. Known Document3/4 '
             'SecurityArray5/6; preview or save a new verified .opentrack copy.',
             EditRouteProtection, service.edit, False, False),
            ('opentrack_replace_current_route_movement',
             'Replace a Route movement between the same two directional main signals in one document. '
             'Recheck run-bound infrastructure, Paths, Itineraries and DestInfo. Requires explicit release '
             'boundaries; reports affected movements for runtime review. Preview or fresh archive copy.',
             EditRouteMovement, service.movement, False, False),
            ('opentrack_replace_current_cross_document_route_movement',
             'Reroute the two existing saved fragments of a Route across one document boundary. Preserve '
             'or explicitly set its release groups, directed slow-speed zone and primary signal aspects. Preserve '
             'directional endpoints and all Path/Itinerary and DestInfo identities. Preview or atomically '
             'save both paired .opentrack documents in a new directory.',
             EditCrossDocumentRoute, service.cross_document_movement, False, False)]
